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
    )


class TestTemplateRationale:
    def test_basic_template(self):
        sig = _make_signal()
        result = _template_rationale(sig)
        assert result.count("\n") == 2
        assert result.startswith("- Hours:")
        assert "- Experience:" in result
        assert result.endswith("- Distance: 3.2 miles from facility")
        assert "6.0h" in result

    def test_ot_warning(self):
        sig = _make_signal(would_trigger_ot=True)
        result = _template_rationale(sig)
        assert "would trigger OT" in result

    def test_floating_status(self):
        sig = _make_signal()
        sig.is_home_unit = False
        sig.home_unit = "U-LT1"
        sig.home_unit_typology = "LT"
        sig.clinical_fit_description = ""
        result = _template_rationale(sig)
        assert "floating" in result.lower() or "U-LT1" in result


class TestGenerateRationales:
    @pytest.mark.asyncio
    async def test_fallback_on_ollama_error(self):
        """When Ollama is unreachable, fall back to template."""
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
        assert rationales[0].startswith("- Hours:")
        assert rationales[1].startswith("- Hours:")
        assert "- Experience:" in rationales[0]
        assert "- Distance:" in rationales[1]

    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        settings = Settings(ollama_model="qwen3.5:9b")
        rationales, source = await generate_rationales(
            [], "U-SA1", "SUBACUTE", "DAY", "2026-04-09", settings
        )
        assert rationales == []
        assert source == "template"

    @pytest.mark.asyncio
    async def test_successful_llm_response(self):
        """Mock a successful Ollama response."""
        settings = Settings(ollama_model="qwen3.5:9b")
        candidates = [_make_signal(rank=1)]

        mock_response = MagicMock()
        mock_response.message.content = (
            '{"candidates": [{"rank": 1, "rationale": '
            '"- Hours: 6.0h of straight time remaining this week\\n'
            '- Experience: CNA — Home unit match\\n'
            '- Distance: 3.2 miles from facility"}]}'
        )

        with patch("ollama.AsyncClient.chat", new=AsyncMock(return_value=mock_response)):
            rationales, source = await generate_rationales(
                candidates, "U-SA1", "SUBACUTE", "DAY", "2026-04-09", settings
            )

        assert source == "llm"
        assert len(rationales) == 1
        assert rationales[0].startswith("- Hours:")

    @pytest.mark.asyncio
    async def test_llm_distance_is_overwritten_with_computed_value(self):
        settings = Settings(ollama_model="qwen3.5:9b")
        candidates = [_make_signal(rank=1)]

        mock_response = MagicMock()
        mock_response.message.content = (
            '{"candidates": [{"rank": 1, "rationale": '
            '"- Hours: 6.0h of straight time remaining this week\\n'
            '- Experience: CNA — Home unit match\\n'
            '- Distance: 0.0 miles from facility"}]}'
        )

        with patch("ollama.AsyncClient.chat", new=AsyncMock(return_value=mock_response)):
            rationales, source = await generate_rationales(
                candidates, "U-SA1", "SUBACUTE", "DAY", "2026-04-09", settings
            )

        assert source == "llm"
        assert rationales == [
            "- Hours: 6.0h of straight time remaining this week\n"
            "- Experience: CNA — Home unit match\n"
            "- Distance: 3.2 miles from facility"
        ]
