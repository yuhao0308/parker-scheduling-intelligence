"""Rationale generation via local LLM (Ollama) with template fallback.

Generates concise bullet-point explanations per ranked candidate using
the same scoring signals that produced the ranking.
"""

from __future__ import annotations

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
"LT"). Speak in plain coordinator language — no jargon, no hedging."""

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
        import ollama as ollama_client

        from pydantic import BaseModel

        class CandidateRationale(BaseModel):
            rank: int
            rationale: str

        class RationaleResponse(BaseModel):
            candidates: list[CandidateRationale]

        response = ollama_client.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            format=RationaleResponse.model_json_schema(),
            options={"temperature": settings.ollama_temperature},
        )

        content = response.message.content
        if content is None:
            raise ValueError("Ollama returned an empty response")

        result = RationaleResponse.model_validate_json(content)

        rationale_map = {r.rank: r.rationale for r in result.candidates}
        rationales = [rationale_map.get(c.rank, _template_rationale(c)) for c in candidates]

        logger.info("rationale_generated", source="llm", count=len(rationales))
        return rationales, "llm"

    except Exception as e:
        logger.warning("ollama_failed_using_template_fallback", error=str(e))
        rationales = [_template_rationale(c) for c in candidates]
        return rationales, "template"
