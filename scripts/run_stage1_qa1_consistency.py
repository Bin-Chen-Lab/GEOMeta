#!/usr/bin/env python3
"""
Runner for GEOMeta Stage 1 QA1 consistency audit between Stage 1 and Stage 2.

Typical use from GEOMeta repo root:

PYTHONPATH=. python scripts/run_stage1_qa1_consistency.py \
  --workdir . \
  --stage1 artifacts/outputs/geometa_full_RUN_stage1.xlsx \
  --run-version geometa_full_RUN

Optional LLM reviewer:

PYTHONPATH=. python scripts/run_stage1_qa1_consistency.py \
  --workdir . \
  --stage1 artifacts/outputs/geometa_full_RUN_stage1.xlsx \
  --run-version geometa_full_RUN \
  --use-llm-review \
  --max-llm-issues 50
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
    parser = argparse.ArgumentParser(description="Run GEOMeta Stage 1 QA1 within-GSE consistency audit")
    parser.add_argument("--workdir", default=".", help="GEOMeta repository/work directory")
    parser.add_argument("--stage1", required=True, help="Stage 1 output file")
    parser.add_argument("--run-version", required=True, help="Run version prefix")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to <workdir>/artifacts/outputs")
    parser.add_argument("--gse-col", default="GSE_ID")
    parser.add_argument("--gsm-col", default="GSM_ID")
    parser.add_argument("--treat-na-as-missing", action="store_true")
    parser.add_argument("--use-llm-review", action="store_true")
    parser.add_argument("--max-llm-issues", type=int, default=None)
    args = parser.parse_args()

    workdir = Path(args.workdir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else workdir / "artifacts" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    script_dir = Path(__file__).resolve().parent
    audit_script = script_dir / "within_gse_consistency_audit.py"
    llm_script = script_dir / "llm_gse_review_agent.py"

    audit_cmd = [
        sys.executable,
        str(audit_script),
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
    if args.treat_na_as_missing:
        audit_cmd.append("--treat-na-as-missing")

    run(audit_cmd)

    corrected = output_dir / f"{args.run_version}_stage1_qa1_corrected_high_confidence.xlsx"
    report = output_dir / f"{args.run_version}_stage1_qa1_consistency_report.xlsx"

    if args.use_llm_review:
        llm_output = output_dir / f"{args.run_version}_stage1_qa1_llm_reviewer_recommendations.xlsx"
        llm_cmd = [
            sys.executable,
            str(llm_script),
            "--stage1",
            str(corrected),
            "--consistency-report",
            str(report),
            "--output",
            str(llm_output),
            "--gse-col",
            args.gse_col,
            "--gsm-col",
            args.gsm_col,
        ]
        if args.max_llm_issues is not None:
            llm_cmd.extend(["--max-issues", str(args.max_llm_issues)])
        run(llm_cmd)

    print("\nStage 1 QA1 complete.")
    print(f"Use this file as Stage 2 input:\n  {corrected}")
    print(f"Audit report:\n  {report}")


if __name__ == "__main__":
    main()
