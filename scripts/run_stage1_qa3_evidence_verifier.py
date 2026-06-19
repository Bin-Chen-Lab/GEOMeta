#!/usr/bin/env python3
"""
Runner for GEOMeta Stage 1 QA3 evidence-grounded verifier / targeted rescue.

Typical use from repo root:

PYTHONPATH=. python scripts/run_stage1_qa3_evidence_verifier.py \
  --workdir . \
  --stage1 artifacts/outputs/RUN_stage1_qa1_corrected_high_confidence.xlsx \
  --stage1-qa1-report artifacts/outputs/RUN_stage1_qa1_consistency_report.xlsx \
  --stage1-qa2-report artifacts/outputs/RUN_stage1_qa2_cross_agent_validation_report.xlsx \
  --run-version RUN \
  --max-tasks 150

Build tasks only, without LLM calls:

PYTHONPATH=. python scripts/run_stage1_qa3_evidence_verifier.py \
  --workdir . \
  --stage1 artifacts/outputs/RUN_stage1_qa1_corrected_high_confidence.xlsx \
  --stage1-qa1-report artifacts/outputs/RUN_stage1_qa1_consistency_report.xlsx \
  --stage1-qa2-report artifacts/outputs/RUN_stage1_qa2_cross_agent_validation_report.xlsx \
  --run-version RUN \
  --build-tasks-only
"""

from __future__ import annotations

import argparse
from pathlib import Path

from stage1_evidence_verifier import (
    EvidenceVerifierConfig,
    read_table,
    run_stage1_qa3_verification_pipeline,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GEOMeta Stage 1 QA3 evidence-grounded verifier")
    parser.add_argument("--workdir", default=".", help="GEOMeta repository/work directory")
    parser.add_argument("--stage1", required=True, help="Stage 1 QA1 corrected file with GSE/GSM info")
    parser.add_argument(
        "--stage1-qa1-report",
        "--stage1-5-report",
        dest="stage1_qa1_report",
        default=None,
        help="Stage 1 QA1 consistency report; --stage1-5-report is kept as a backward-compatible alias.",
    )
    parser.add_argument(
        "--stage1-qa2-report",
        "--stage1-6-report",
        dest="stage1_qa2_report",
        default=None,
        help="Stage 1 QA2 cross-agent validation report; --stage1-6-report is kept as a backward-compatible alias.",
    )
    parser.add_argument("--run-version", required=True, help="Run version prefix")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to <workdir>/artifacts/outputs")
    parser.add_argument("--gse-col", default="GSE_ID")
    parser.add_argument("--gsm-col", default="GSM_ID")
    parser.add_argument("--max-tasks", type=int, default=150)
    parser.add_argument("--min-confidence-to-apply", type=float, default=0.90)
    parser.add_argument("--build-tasks-only", action="store_true")
    parser.add_argument("--no-apply", action="store_true", help="Save LLM recommendations but do not apply corrections")
    parser.add_argument("--allow-nonempty-overwrite", action="store_true")
    parser.add_argument("--skip-sampling-qc", action="store_true")
    parser.add_argument(
        "--include-stage1-qa2-low",
        "--include-stage1-6-low",
        dest="include_stage1_qa2_low",
        action="store_true",
    )
    args = parser.parse_args()

    workdir = Path(args.workdir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else workdir / "artifacts" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    stage1_path = Path(args.stage1).resolve()
    if not stage1_path.exists():
        raise FileNotFoundError(f"Stage1 input file not found: {stage1_path}")

    df_stage1 = read_table(stage1_path)

    cfg = EvidenceVerifierConfig(
        gse_col=args.gse_col,
        gsm_col=args.gsm_col,
        max_tasks=args.max_tasks,
        min_confidence_to_apply=args.min_confidence_to_apply,
        build_tasks_only=args.build_tasks_only,
        apply_accepted=not args.no_apply,
        allow_nonempty_overwrite=args.allow_nonempty_overwrite,
        include_sampling_qc=not args.skip_sampling_qc,
        include_stage1_qa2_low=args.include_stage1_qa2_low,
    )

    _, outputs = run_stage1_qa3_verification_pipeline(
        df_stage1=df_stage1,
        stage1_qa1_report=Path(args.stage1_qa1_report).resolve() if args.stage1_qa1_report else None,
        stage1_qa2_report=Path(args.stage1_qa2_report).resolve() if args.stage1_qa2_report else None,
        output_dir=output_dir,
        run_version=args.run_version,
        verifier_config=cfg,
        cfg_pipeline=None,
    )

    print("\nStage 1 QA3 complete.")
    print("Use this file as Stage 2 input if you accept high-confidence targeted rescue:")
    print(f"  {outputs['corrected']}")
    print("Audit report:")
    print(f"  {outputs['report']}")


if __name__ == "__main__":
    main()
