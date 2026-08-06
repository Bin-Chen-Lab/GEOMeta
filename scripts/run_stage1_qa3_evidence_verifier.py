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
  --stage1-qa3-mode smart

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

def parse_qa3_target_fields(text):
    if text is None:
        return None

    text = str(text).strip()
    if not text or text.upper() in {"ALL", "*"}:
        return None

    fields = [
        x.strip()
        for x in text.replace(";", ",").replace("|", ",").split(",")
        if x.strip()
    ]
    return tuple(dict.fromkeys(fields))

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
    parser.add_argument("--max-tasks", type=int, default=None)

    parser.add_argument(
        "--qa3-target-fields",
        "--stage1-qa3-fields",
        dest="qa3_target_fields",
        default="GSE_Pert,GSM_Pert,RNA_Source,Tissue",
        help=(
            "Comma-separated target fields for field-targeted QA3. "
            "Default: GSE_Pert,GSM_Pert,RNA_Source,Tissue. "
            "Use ALL to disable field filtering."
        ),
    )

    parser.add_argument(
        "--stage1-qa3-mode",
        "--qa3-mode",
        dest="stage1_qa3_mode",
        choices=["off", "smart", "full"],
        default="smart",
        help="QA3 mode: off skips QA3 tasks, smart runs prioritized tasks, full runs broad QA3.",
    )
    parser.add_argument("--min-confidence-to-apply", type=float, default=0.90)
    parser.add_argument("--build-tasks-only", action="store_true")
    parser.add_argument("--no-apply", action="store_true", help="Save LLM recommendations but do not apply corrections")
    parser.add_argument("--allow-nonempty-overwrite", action="store_true")
    parser.add_argument("--skip-sampling-qc", action="store_true")
    parser.add_argument(
    "--include-stage1-qa2-low",
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

    qa3_mode = args.stage1_qa3_mode

    if args.max_tasks is not None:
        qa3_max_tasks = args.max_tasks
    elif qa3_mode == "off":
        qa3_max_tasks = 0
    else:
        qa3_max_tasks = None

    qa3_target_fields = parse_qa3_target_fields(args.qa3_target_fields)

    print(
        "[Stage1 QA3] Field-targeted QA3 target fields: "
        + ("ALL" if qa3_target_fields is None else ", ".join(qa3_target_fields))
    )
    print(
        "[Stage1 QA3] Max tasks: "
        + ("None / uncapped after field filtering" if qa3_max_tasks is None else str(qa3_max_tasks))
    )

    cfg = EvidenceVerifierConfig(
        gse_col=args.gse_col,
        gsm_col=args.gsm_col,
        qa3_mode=qa3_mode,
        max_tasks=qa3_max_tasks,
        min_confidence_to_apply=args.min_confidence_to_apply,
        build_tasks_only=args.build_tasks_only,
        apply_accepted=not args.no_apply,
        allow_nonempty_overwrite=args.allow_nonempty_overwrite,
        include_sampling_qc=(qa3_mode == "full") and not args.skip_sampling_qc,
        include_stage1_qa2_low=args.include_stage1_qa2_low,
        qa3_target_fields=qa3_target_fields,
        fields_for_sampling_qc=qa3_target_fields or ("GSE_Pert", "GSM_Pert", "RNA_Source", "Tissue"),
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
