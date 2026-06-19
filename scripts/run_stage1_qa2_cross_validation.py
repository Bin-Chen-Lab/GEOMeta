#!/usr/bin/env python3
"""
Runner for GEOMeta Stage 1 QA2 cross-agent validation.

Run after Stage 1 QA1 and before Stage 2.

Basic use:
PYTHONPATH=. python scripts/run_stage1_qa2_cross_validation.py \
  --workdir . \
  --stage1 artifacts/outputs/geometa_full_RUN_stage1_qa1_corrected_high_confidence.xlsx \
  --run-version geometa_full_RUN

Optional LLM review:
PYTHONPATH=. python scripts/run_stage1_qa2_cross_validation.py \
  --workdir . \
  --stage1 artifacts/outputs/geometa_full_RUN_stage1_qa1_corrected_high_confidence.xlsx \
  --run-version geometa_full_RUN \
  --use-llm-review \
  --max-llm-issues 50 \
  --include-medium
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GEOMeta Stage 1 QA2 cross-agent validation")
    parser.add_argument("--workdir", default=".", help="GEOMeta repository/work directory")
    parser.add_argument("--stage1", required=True, help="Stage 1 or Stage 1 QA1 corrected Excel file")
    parser.add_argument("--run-version", required=True, help="Run version prefix")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to <workdir>/artifacts/outputs")
    parser.add_argument("--gse-col", default="GSE_ID")
    parser.add_argument("--gsm-col", default="GSM_ID")
    parser.add_argument("--include-low-severity", action="store_true")
    parser.add_argument("--use-llm-review", action="store_true")
    parser.add_argument("--max-llm-issues", type=int, default=None)
    parser.add_argument("--include-medium", action="store_true", help="Send Medium severity issues to LLM reviewer")
    parser.add_argument("--include-low", action="store_true", help="Send Low severity issues to LLM reviewer")
    parser.add_argument("--rule-ids", default=None, help="Optional comma-separated Rule_ID filter for LLM review")
    args = parser.parse_args()

    workdir = Path(args.workdir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else workdir / "artifacts" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    script_dir = Path(__file__).resolve().parent
    validation_script = script_dir / "stage1_cross_agent_validation.py"
    llm_script = script_dir / "llm_cross_agent_review_agent.py"

    validation_cmd = [
        sys.executable,
        str(validation_script),
        "--input",
        str(Path(args.stage1).resolve()),
        "--output-dir",
        str(output_dir),
        "--run-version",
        args.run_version,
        "--gse-col",
        args.gse_col,
        "--gsm-col",
        args.gsm_col,
    ]
    if args.include_low_severity:
        validation_cmd.append("--include-low-severity")

    run(validation_cmd)

    cross_report = output_dir / f"{args.run_version}_stage1_qa2_cross_agent_validation_report.xlsx"

    if args.use_llm_review:
        llm_output = output_dir / f"{args.run_version}_stage1_qa2_llm_cross_agent_recommendations.xlsx"
        llm_cmd = [
            sys.executable,
            str(llm_script),
            "--stage1",
            str(Path(args.stage1).resolve()),
            "--cross-report",
            str(cross_report),
            "--output",
            str(llm_output),
            "--gse-col",
            args.gse_col,
            "--gsm-col",
            args.gsm_col,
        ]
        if args.max_llm_issues is not None:
            llm_cmd.extend(["--max-issues", str(args.max_llm_issues)])
        if args.include_medium:
            llm_cmd.append("--include-medium")
        if args.include_low:
            llm_cmd.append("--include-low")
        if args.rule_ids:
            llm_cmd.extend(["--rule-ids", args.rule_ids])
        run(llm_cmd)

    print("\nStage 1 QA2 complete.")
    print(f"Cross-agent validation report:\n  {cross_report}")
    print("Stage 2 should still use the Stage 1 QA1 corrected file as input unless a human-curated correction file is created.")


if __name__ == "__main__":
    main()
