"""Rationale generation via local LLM (Ollama) with template fallback.

Generates concise bullet-point explanations per ranked candidate using
the same scoring signals that produced the ranking.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import structlog

from app.config import Settings

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a staffing coordinator assistant at a skilled nursing facility.
For each candidate in the list, write EXACTLY 3 bullet points explaining why they are
ranked at this position. Use this format for each candidate:
- Hours this month: X.X h worked (Y.Y h remaining this cycle)
- Experience: [License] — [clinical fit description using Short-Term / Long-Term language]
- Distance: Z.Z miles from facility
Lead with the primary drivers: overtime headroom (the top priority), unit-type
experience (Short-Term vs Long-Term), and float status. Distance is a minor
tiebreaker, so mention it only in the final bullet.
Use the facility's vocabulary: say "Short-Term" and "Long-Term" (never "subacute" or
"LT"). Speak in plain coordinator language — no jargon, no hedging.
/no_think"""

_TYPOLOGY_LABEL = {"LT": "Long-Term", "SUBACUTE": "Short-Term"}


def _typology_label(value: str) -> str:
    return _TYPOLOGY_LABEL.get(value, value)


@dataclass
class CandidateSignals:
    """Scoring signals for one candidate, used to build the LLM prompt."""

    rank: int
    name: str
    license: str
    employment_class: str
    home_unit: str
    home_unit_typology: str
    target_unit: str
    target_unit_typology: str
    ot_headroom_normalized: float
    ot_headroom_description: str  # e.g. "6.0 hours of straight time remaining"
    would_trigger_ot: bool
    distance_miles: float
    clinical_fit_score: float
    clinical_fit_description: str  # e.g. "Short-Term-trained covering Long-Term"
    is_home_unit: bool
    float_penalty: float
    total_score: float


def _build_prompt(
    candidates: list[CandidateSignals],
    unit_id: str,
    unit_typology: str,
    shift_label: str,
    shift_date: str,
) -> str:
    """Build the user message with all candidate data."""
    lines = [
        f"Call-out: Unit {unit_id} ({_typology_label(unit_typology)}), {shift_label} shift on {shift_date}",
        "",
        "Candidates (ranked by score):",
    ]
    for c in candidates:
        lines.append("")
        lines.append(f"{c.rank}. {c.name} ({c.license}, {c.employment_class})")
        lines.append(f"   Home unit: {c.home_unit} ({_typology_label(c.home_unit_typology)})")
        lines.append(f"   OT headroom: {c.ot_headroom_description}")
        lines.append(f"   Would trigger OT: {'yes' if c.would_trigger_ot else 'no'}")
        lines.append(f"   Clinical fit: {c.clinical_fit_description}")
        lines.append(f"   Float status: {'home unit' if c.is_home_unit else 'floating'}")
        lines.append(f"   Score: {c.total_score:.3f}")
        lines.append(f"   Distance (tiebreaker only): {c.distance_miles:.1f} miles from facility")

    lines.append("")
    lines.append(
        "Return a JSON object with a 'candidates' array. Each element must have "
        "'rank' (int) and 'rationale' (string, exactly 3 bullet points using this format):\n"
        "- Hours this month: X.X h worked (Y.Y h remaining this cycle)\n"
        "- Experience: [License] — [clinical fit description using Short-Term / Long-Term language]\n"
        "- Distance: Z.Z miles from facility"
    )
    return "\n".join(lines)


def _template_rationale(c: CandidateSignals) -> str:
    """Fallback template-based rationale when Ollama is unavailable.

    Returns exactly 3 bullet points per candidate.
    """
    clinical_desc = c.clinical_fit_description if c.clinical_fit_description else (
        "Home unit match"
        if c.is_home_unit
        else f"Floating from {c.home_unit} ({_typology_label(c.home_unit_typology)})"
    )

    lines = [
        f"- Hours: {c.ot_headroom_description}",
        f"- Experience: {c.license} — {clinical_desc}",
        f"- Distance: {c.distance_miles:.1f} miles from facility",
    ]
    return "\n".join(lines)


def _authoritative_distance_line(distance_miles: float) -> str:
    """Return the canonical distance bullet from the computed score input."""
    return f"- Distance: {distance_miles:.1f} miles from facility"


def _normalize_rationale(c: CandidateSignals, rationale: str) -> str:
    """Preserve coordinator-friendly prose while enforcing the true distance line.

    The LLM occasionally paraphrases or hallucinates the distance bullet. The UI
    renders the stored rationale text directly, so we replace that line with the
    exact computed mileage before returning it to callers.
    """
    lines = rationale.splitlines()
    distance_line = _authoritative_distance_line(c.distance_miles)

    replaced = False
    normalized: list[str] = []
    for line in lines:
        if line.strip().startswith("- Distance:"):
            normalized.append(distance_line)
            replaced = True
        else:
            normalized.append(line)

    if not replaced:
        normalized.append(distance_line)

    return "\n".join(normalized)


async def warm_ollama(settings: Settings) -> None:
    """Preload the Ollama model so the first real request doesn't pay cold-load cost.

    Fire-and-forget: logs success or failure but never raises. Safe to call from
    FastAPI lifespan startup. Uses a generous timeout because the very first load
    of a multi-GB model can take 20-60s on CPU.
    """
    try:
        from ollama import AsyncClient

        client = AsyncClient(host=settings.ollama_base_url)
        await asyncio.wait_for(
            client.chat(
                model=settings.ollama_model,
                messages=[{"role": "user", "content": "ok"}],
                think=False,
                options={"temperature": 0.0, "num_predict": 1},
            ),
            timeout=settings.ollama_warmup_timeout,
        )
        logger.info("ollama_warmup_complete", model=settings.ollama_model)
    except Exception as e:
        logger.warning(
            "ollama_warmup_failed",
            error=repr(e),
            error_type=type(e).__name__,
            model=settings.ollama_model,
        )


async def generate_rationales(
    candidates: list[CandidateSignals],
    unit_id: str,
    unit_typology: str,
    shift_label: str,
    shift_date: str,
    settings: Settings,
) -> tuple[list[str], str]:
    """Generate rationales for ranked candidates.

    Returns:
        (rationales, source) where source is "llm" or "template"
    """
    if not candidates:
        return [], "template"

    prompt = _build_prompt(candidates, unit_id, unit_typology, shift_label, shift_date)

    try:
        from ollama import AsyncClient

        from pydantic import BaseModel

        class CandidateRationale(BaseModel):
            rank: int
            rationale: str

        class RationaleResponse(BaseModel):
            candidates: list[CandidateRationale]

        client = AsyncClient(host=settings.ollama_base_url)
        response = await asyncio.wait_for(
            client.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                think=False,
                format="json",
                options={"temperature": settings.ollama_temperature},
            ),
            timeout=settings.ollama_timeout,
        )

        content = response.message.content
        if content is None:
            raise ValueError("Ollama returned an empty response")

        result = RationaleResponse.model_validate_json(content)

        rationale_map = {r.rank: r.rationale for r in result.candidates}
        rationales = [
            _normalize_rationale(c, rationale_map.get(c.rank, _template_rationale(c)))
            for c in candidates
        ]

        logger.info("rationale_generated", source="llm", count=len(rationales))
        return rationales, "llm"

    except Exception as e:
        logger.warning(
            "ollama_failed_using_template_fallback",
            error=repr(e),
            error_type=type(e).__name__,
        )
        rationales = [_template_rationale(c) for c in candidates]
        return rationales, "template"
