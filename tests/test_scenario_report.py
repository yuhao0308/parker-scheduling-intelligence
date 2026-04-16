from __future__ import annotations

from tests.scenarios.reporting import write_report_bundle
from tests.scenarios.runtime import run_scenario_suite
from tests.scenarios.specs import SCENARIOS


async def test_scenario_suite_matches_expected_classifications(tmp_path):
    report = await run_scenario_suite()

    assert report.summary["total"] == len(SCENARIOS)
    assert report.summary["fail"] == 0

    expected = {scenario.id: scenario.result_classification for scenario in SCENARIOS}
    actual = {scenario.id: scenario.actual_classification for scenario in report.scenarios}
    assert actual == expected

    output_paths = write_report_bundle(report, tmp_path)
    assert output_paths["json"].exists()
    assert output_paths["markdown"].exists()
    assert output_paths["html"].exists()

    markdown = output_paths["markdown"].read_text(encoding="utf-8")
    assert "Scheduling Scenario Report" in markdown
    assert "Minimum-hours-first fairness is still a known gap" in markdown
