"""Tests for rationale generation — LLM and template fallback."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.rationale import (
    CandidateSignals,
    _template_rationale,
    generate_rationales,
)


def _make_signal(rank=1, name="Maria R.", would_trigger_ot=False):
    return CandidateSignals(
        rank=rank,
        name=name,
        license="CNA",
        employment_class="FT",
        home_unit="U-SA1",
        home_unit_typology="SUBACUTE",
        target_unit="U-SA1",
        target_unit_typology="SUBACUTE",
        ot_headroom_normalized=0.8,
        ot_headroom_description=(
            "0.0h remaining this week (would trigger OT)"
            if would_trigger_ot
            else "6.0h of straight time remaining this week"
        ),
        would_trigger_ot=would_trigger_ot,
        distance_miles=3.2,
        clinical_fit_score=1.0,
        clinical_fit_description="home unit — perfect fit",
        is_home_unit=True,
        float_penalty=0.0,
        total_score=0.87,
        scheduled_shifts_this_month=12,
        scheduled_hours_this_month=90.0,
        peak_load_label="30.0h / peak week",
        projected_overtime_label="None projected",
    )


class TestTemplateRationale:
    def test_template_does_not_repeat_chart_data(self):
        """Reasons must NOT cite numeric data the UI chart already shows."""
        sig = _make_signal()
        result = _template_rationale(sig)
        assert result.headline
        body = " ".join(result.reasons + result.risks).lower()
        # No numeric data should leak into prose — that's the chart's job.
        assert "miles" not in body
        assert "h remaining" not in body
        assert "shifts remaining" not in body
        # Highlights array is reserved for backwards-compat only.
        assert result.highlights == []

    def test_ot_warning_appears_in_risks(self):
        sig = _make_signal(would_trigger_ot=True)
        result = _template_rationale(sig)
        assert any("overtime" in r.lower() for r in result.risks)

    def test_cross_trained_surfaces_in_reasons(self):
        sig = _make_signal()
        sig.is_home_unit = False
        sig.home_unit = "U-LT1"
        sig.home_unit_typology = "LT"
        sig.clinical_fit_description = "cross-trained for this unit"
        result = _template_rationale(sig)
        assert any("cross-trained" in r.lower() for r in result.reasons)


class TestGenerateRationales:
    @pytest.mark.asyncio
    async def test_fallback_on_ollama_error(self):
        settings = Settings(ollama_model="qwen3.5:9b")
        candidates = [_make_signal(rank=1), _make_signal(rank=2, name="James T.")]

        with patch(
            "ollama.AsyncClient.chat",
            new=AsyncMock(side_effect=Exception("Connection refused")),
        ):
            rationales, source = await generate_rationales(
                candidates, "U-SA1", "SUBACUTE", "DAY", "2026-04-09", settings
            )

        assert source == "template"
        assert len(rationales) == 2
        for r in rationales:
            assert r.headline

    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        settings = Settings(ollama_model="qwen3.5:9b")
        rationales, source = await generate_rationales(
            [], "U-SA1", "SUBACUTE", "DAY", "2026-04-09", settings
        )
        assert rationales == []
        assert source == "template"

    @pytest.mark.asyncio
    async def test_llm_response_keeps_narrative_drops_numeric_highlights(self):
        settings = Settings(ollama_model="qwen3.5:9b")
        candidates = [_make_signal(rank=1)]

        mock_response = MagicMock()
        mock_response.message.content = (
            '{"candidates": [{"rank": 1, '
            '"headline": "Home-unit CNA — best clinical fit", '
            '"reasons": ["Already on home unit, no float needed"], '
            '"risks": []}]}'
        )

        with patch("ollama.AsyncClient.chat", new=AsyncMock(return_value=mock_response)):
            rationales, source = await generate_rationales(
                candidates, "U-SA1", "SUBACUTE", "DAY", "2026-04-09", settings
            )

        assert source == "llm"
        assert rationales[0].headline == "Home-unit CNA — best clinical fit"
        assert rationales[0].reasons == ["Already on home unit, no float needed"]
        assert rationales[0].highlights == []
