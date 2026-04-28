"""Structured rationale generation via local LLM (Ollama) with template fallback.

Produces a typed ``Rationale`` (see ``app/schemas/rationale.py``) per
candidate so the UI can render labeled chips, sections, and warnings instead
of a free-text bullet block.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import structlog

from app.config import Settings
from app.schemas.rationale import Rationale

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a staffing coordinator assistant at a skilled nursing facility.
For each ranked candidate, return a structured rationale that helps a human
scheduler instantly understand why this candidate was surfaced.

Use this exact JSON schema:
{
  "candidates": [
    {
      "rank": <int>,
      "headline": "<10-14 words, plain coordinator language, no jargon, NO numbers>",
      "reasons": ["<insight bullet>", ...],
      "risks": ["<watch-out>", ...]
    }
  ]
}

The UI already renders workload (hours/shifts this month, OT headroom, peak
load), clinical fit, float status, distance, and tenure as visual chips and
charts. Your job is to add CONTEXT the visuals don't carry — never repeat
the numbers.

Rules:
- Speak in plain coordinator language. Say "Short-Term" / "Long-Term" (never
  "subacute" or "LT").
- Do NOT invent numbers. Do NOT cite shift counts, hours, miles, or
  thresholds in headline/reasons/risks — those appear in the chart.
- "headline": one sentence describing the candidate's situation
  (home-unit / cross-trained / cross-typology / would-trigger-OT, etc.).
- "reasons" 0-3 short bullets covering things the chart can't show:
  cross-training history, recent absence from work, tenure context,
  per-diem equity, willingness signals, etc. NEVER repeat numeric data
  that the chart already shows. Empty array if nothing notable.
- "risks" 0-3 short bullets. Empty array if no real concern.
- Return only valid JSON.
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
    ot_headroom_description: str
    would_trigger_ot: bool
    distance_miles: float
    clinical_fit_score: float
    clinical_fit_description: str
    is_home_unit: bool
    float_penalty: float
    total_score: float
    # Month-level signals (mirror the workload monitor)
    scheduled_shifts_this_month: int = 0
    scheduled_hours_this_month: float = 0.0
    home_unit_shifts_this_month: int = 0
    float_shifts_this_month: int = 0
    peak_load_label: str = ""  # e.g. "8 shifts / peak biweek" or "30.0h / peak week"
    projected_overtime_label: str = "None projected"
    days_since_last_shift: Optional[int] = None
    tenure_years: Optional[float] = None


# ---------------------------------------------------------------------------
# Template fallback
# ---------------------------------------------------------------------------


def _template_rationale(c: CandidateSignals) -> Rationale:
    """Deterministic structured rationale used when the LLM is unavailable.

    The UI renders workload, fit, distance, and tenure visually — so this
    function intentionally does NOT repeat those numbers. Reasons should
    surface insight that the visuals alone don't carry.
    """
    typology_label = _typology_label(c.home_unit_typology)
    target_typology_label = _typology_label(c.target_unit_typology)

    # Headline — one sentence, no numbers (numbers live in the chart).
    if c.would_trigger_ot:
        headline = "Strong fit, but selecting would push them into overtime"
    elif c.is_home_unit:
        headline = f"Home-unit {c.license} — best clinical and workload fit"
    elif "cross-trained" in (c.clinical_fit_description or "").lower():
        headline = f"Cross-trained {c.license} — has covered this unit before"
    elif "same unit type" in (c.clinical_fit_description or "").lower():
        headline = f"{c.license} from a same-type {target_typology_label} unit"
    elif "clinical risk" in (c.clinical_fit_description or "").lower():
        headline = f"{c.license} available, but cross-typology cover carries clinical risk"
    elif "acceptable" in (c.clinical_fit_description or "").lower():
        headline = f"{c.license} from {typology_label} — acceptable cross-cover"
    else:
        headline = f"{c.license} from {typology_label}"

    # Reasons — only insights NOT visible in the chart/fit-line.
    reasons: list[str] = []
    desc_lower = (c.clinical_fit_description or "").lower()
    if "cross-trained" in desc_lower and not c.is_home_unit:
        reasons.append("Already cross-trained for this unit")
    if (
        c.employment_class == "PER_DIEM"
        and c.days_since_last_shift is not None
        and c.days_since_last_shift >= 14
    ):
        reasons.append(
            f"Per-diem who hasn't worked in {c.days_since_last_shift} days — equity boost"
        )
    if c.tenure_years is not None and c.tenure_years >= 5 and not c.is_home_unit:
        reasons.append(
            f"Senior staff ({c.tenure_years:.0f}+ yrs) — handles cross-unit cover well"
        )
    if c.is_home_unit and not c.would_trigger_ot:
        reasons.append("No floating, no overtime — lowest-friction option")

    # Risks — coordinator-actionable warnings.
    risks: list[str] = []
    if c.would_trigger_ot:
        risks.append("Selecting this candidate would trigger overtime")
    elif c.ot_headroom_normalized < 0.3:
        risks.append("Approaching the OT threshold — close to the line")

    if "clinical risk" in desc_lower:
        risks.append("Long-Term-only experience covering Short-Term — clinical risk")
    elif "acceptable" in desc_lower:
        risks.append("Cross-typology cover — acceptable but not ideal")

    return Rationale(
        headline=headline,
        highlights=[],
        reasons=reasons,
        risks=risks,
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_prompt(
    candidates: list[CandidateSignals],
    unit_id: str,
    unit_typology: str,
    shift_label: str,
    shift_date: str,
) -> str:
    lines = [
        f"Call-out: Unit {unit_id} ({_typology_label(unit_typology)}), {shift_label} shift on {shift_date}",
        "",
        "Candidates (ranked by score):",
    ]
    for c in candidates:
        lines.append("")
        lines.append(f"{c.rank}. {c.name} ({c.license}, {c.employment_class})")
        lines.append(f"   Home unit: {c.home_unit} ({_typology_label(c.home_unit_typology)})")
        lines.append(
            f"   Hours this month: {c.scheduled_shifts_this_month} shifts · "
            f"{c.scheduled_hours_this_month:.1f}h"
        )
        lines.append(f"   Peak load: {c.peak_load_label or 'n/a'}")
        lines.append(f"   Projected OT: {c.projected_overtime_label}")
        lines.append(f"   OT headroom: {c.ot_headroom_description}")
        lines.append(f"   Would trigger OT: {'yes' if c.would_trigger_ot else 'no'}")
        lines.append(f"   Clinical fit: {c.clinical_fit_description}")
        lines.append(
            f"   Float status: {'home unit' if c.is_home_unit else 'floating to ' + c.target_unit}"
        )
        lines.append(f"   Distance: {c.distance_miles:.1f} miles from facility")
        if c.tenure_years is not None:
            lines.append(f"   Tenure: {c.tenure_years:.1f} yr")
        if c.days_since_last_shift is not None:
            lines.append(f"   Days since last shift: {c.days_since_last_shift}")
        lines.append(f"   Score: {c.total_score:.3f}")

    lines.append("")
    lines.append(
        "Return ONLY a valid JSON object with a 'candidates' array following "
        "the schema in the system prompt. Do not include any prose outside JSON."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM normalization
# ---------------------------------------------------------------------------


def _normalize_rationale(c: CandidateSignals, llm_rationale: Rationale) -> Rationale:
    """Trust the LLM's narrative but fall back to the deterministic template
    when fields come back empty."""
    template = _template_rationale(c)
    headline = llm_rationale.headline.strip() or template.headline
    reasons = [r.strip() for r in llm_rationale.reasons if r and r.strip()][:3]
    if not reasons:
        reasons = template.reasons
    risks = [r.strip() for r in llm_rationale.risks if r and r.strip()][:3]
    return Rationale(
        headline=headline,
        highlights=[],
        reasons=reasons,
        risks=risks,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def warm_ollama(settings: Settings) -> None:
    """Preload the Ollama model so the first real request doesn't pay cold-load cost."""
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
) -> tuple[list[Rationale], str]:
    """Generate structured rationales for ranked candidates.

    Returns:
        (rationales, source) where source is "llm" or "template".
    """
    if not candidates:
        return [], "template"

    prompt = _build_prompt(candidates, unit_id, unit_typology, shift_label, shift_date)

    try:
        from ollama import AsyncClient
        from pydantic import BaseModel

        class _LLMRationale(BaseModel):
            rank: int
            headline: str = ""
            reasons: list[str] = []
            risks: list[str] = []

        class _LLMResponse(BaseModel):
            candidates: list[_LLMRationale]

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

        parsed = _LLMResponse.model_validate_json(content)
        llm_map = {r.rank: r for r in parsed.candidates}

        rationales: list[Rationale] = []
        for c in candidates:
            llm = llm_map.get(c.rank)
            if llm is None:
                rationales.append(_template_rationale(c))
                continue
            rationales.append(
                _normalize_rationale(
                    c,
                    Rationale(
                        headline=llm.headline,
                        highlights=[],
                        reasons=llm.reasons,
                        risks=llm.risks,
                    ),
                )
            )

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
