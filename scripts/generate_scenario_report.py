from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from tests.scenarios.reporting import write_report_bundle
from tests.scenarios.runtime import run_scenario_suite


async def _main(output_dir: Path) -> None:
    report = await run_scenario_suite()
    paths = write_report_bundle(report, output_dir)

    print("Scenario report generated:")
    for label, path in paths.items():
        print(f"- {label}: {path}")
    print(
        "Summary: "
        f"pass={report.summary['pass']} "
        f"gap={report.summary['gap']} "
        f"fail={report.summary['fail']} "
        f"total={report.summary['total']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the executable scheduling scenario report.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/scenario-report",
        help="Directory where JSON, Markdown, and HTML reports will be written.",
    )
    args = parser.parse_args()
    asyncio.run(_main(Path(args.output_dir)))


if __name__ == "__main__":
    main()
