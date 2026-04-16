from __future__ import annotations

import json
from html import escape
from pathlib import Path

from tests.scenarios.models import ScenarioResult, ScenarioRunReport


def _status_badge(status: str) -> str:
    colors = {
        "pass": "#166534",
        "gap": "#92400e",
        "fail": "#991b1b",
    }
    background = {
        "pass": "#dcfce7",
        "gap": "#fef3c7",
        "fail": "#fee2e2",
    }
    return (
        f"<span style=\"display:inline-block;padding:0.25rem 0.6rem;border-radius:999px;"
        f"font-weight:600;color:{colors[status]};background:{background[status]};\">"
        f"{escape(status.upper())}</span>"
    )


def build_markdown_report(report: ScenarioRunReport) -> str:
    lines = [
        "# Scheduling Scenario Report",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        "",
        "## Summary",
        "",
        f"- Pass: {report.summary['pass']}",
        f"- Gap: {report.summary['gap']}",
        f"- Fail: {report.summary['fail']}",
        f"- Total: {report.summary['total']}",
        "",
    ]

    for scenario in report.scenarios:
        lines.extend(
            [
                f"## {scenario.title}",
                "",
                f"- ID: `{scenario.id}`",
                f"- Expected classification: `{scenario.expected_classification}`",
                f"- Actual classification: `{scenario.actual_classification}`",
                f"- Business rule: {scenario.business_rule}",
                "",
                "### Request",
                "",
                "```json",
                json.dumps(scenario.request, indent=2),
                "```",
                "",
                "### Assertions",
                "",
            ]
        )
        for assertion in scenario.assertions:
            marker = "PASS" if assertion.passed else "MISS"
            lines.append(
                f"- [{marker}] {assertion.description}  \n  Detail: `{assertion.detail}`"
            )
        lines.append("")

    return "\n".join(lines)


def _scenario_html_card(scenario: ScenarioResult) -> str:
    assertion_items = "".join(
        (
            "<li>"
            f"<strong>{'PASS' if assertion.passed else 'MISS'}</strong> "
            f"{escape(assertion.description)}"
            f"<div style=\"margin-top:0.35rem;color:#475569;\">{escape(assertion.detail)}</div>"
            "</li>"
        )
        for assertion in scenario.assertions
    )

    return f"""
    <section style="background:white;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin-bottom:20px;box-shadow:0 10px 30px rgba(15,23,42,0.05);">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:start;">
        <div>
          <h2 style="margin:0 0 8px 0;font-size:1.25rem;">{escape(scenario.title)}</h2>
          <div style="color:#475569;font-size:0.95rem;">{escape(scenario.business_rule)}</div>
        </div>
        <div>{_status_badge(scenario.actual_classification)}</div>
      </div>
      <div style="margin-top:16px;color:#0f172a;">
        <div><strong>ID:</strong> <code>{escape(scenario.id)}</code></div>
        <div><strong>Expected:</strong> <code>{escape(scenario.expected_classification)}</code></div>
      </div>
      <div style="margin-top:16px;">
        <strong>Request</strong>
        <pre style="white-space:pre-wrap;background:#f8fafc;border-radius:12px;padding:12px;border:1px solid #e2e8f0;overflow:auto;">{escape(json.dumps(scenario.request, indent=2))}</pre>
      </div>
      <div style="margin-top:16px;">
        <strong>Assertions</strong>
        <ul style="padding-left:1.1rem;line-height:1.45;">{assertion_items}</ul>
      </div>
    </section>
    """


def build_html_report(report: ScenarioRunReport) -> str:
    cards = "\n".join(_scenario_html_card(scenario) for scenario in report.scenarios)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Scheduling Scenario Report</title>
  </head>
  <body style="margin:0;font-family:ui-sans-serif,system-ui,sans-serif;background:linear-gradient(180deg,#f8fafc 0%,#eef2ff 100%);color:#0f172a;">
    <main style="max-width:980px;margin:0 auto;padding:32px 20px 48px;">
      <header style="margin-bottom:24px;">
        <div style="font-size:0.9rem;text-transform:uppercase;letter-spacing:0.08em;color:#475569;">Executable Scenario Report</div>
        <h1 style="margin:8px 0 12px 0;font-size:2.4rem;line-height:1.1;">Scheduling Logic Proof</h1>
        <p style="margin:0 0 16px 0;color:#334155;max-width:720px;">
          This report runs named staffing scenarios against the live FastAPI application and records whether the current implementation matches the target business rule.
        </p>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          {_status_badge('pass')} <span>{report.summary['pass']}</span>
          {_status_badge('gap')} <span>{report.summary['gap']}</span>
          {_status_badge('fail')} <span>{report.summary['fail']}</span>
        </div>
        <div style="margin-top:12px;color:#475569;">Generated: {escape(report.generated_at.isoformat())}</div>
      </header>
      {cards}
    </main>
  </body>
</html>
"""


def write_report_bundle(report: ScenarioRunReport, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "scenario-results.json"
    markdown_path = output_dir / "scenario-report.md"
    html_path = output_dir / "scenario-report.html"

    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(build_markdown_report(report), encoding="utf-8")
    html_path.write_text(build_html_report(report), encoding="utf-8")

    return {
        "json": json_path,
        "markdown": markdown_path,
        "html": html_path,
    }
