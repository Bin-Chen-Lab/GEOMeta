from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from geo_annotation_agent.config import default_config
from geo_annotation_agent.reviewer import ReviewerV2
from geo_annotation_agent.reviewer_llm import ReviewerLLMV2, LLMReviewConfig
from geo_annotation_agent.stage2_postprocess import (
    run_stage2_postprocessing,
    run_stage2_postprocessing_v2,
)


def make_run_version(prefix: str = "gaa_stage2") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def main():
    ap = argparse.ArgumentParser(
        description="Run Stage 2 independently: pass1 -> review -> selective rerun"
    )
    ap.add_argument(
        "--workdir",
        default=".",
        help="Project working directory. Defaults to current directory.",
    )
    ap.add_argument(
        "--stage1",
        required=True,
        help="Path to Stage1 Excel file.",
    )
    ap.add_argument(
        "--run-version",
        default=None,
        help="Optional run version override.",
    )
    ap.add_argument(
        "--skip-pass1",
        action="store_true",
        help="If provided, use --stage2-pass1 instead of rerunning Stage2 pass 1.",
    )
    ap.add_argument(
        "--stage2-pass1",
        default=None,
        help="Optional Stage2 pass1 Excel file, required when --skip-pass1 is used.",
    )
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    cfg = default_config(workdir)

    if args.run_version:
        cfg.run_version = args.run_version
    else:
        cfg.run_version = make_run_version("gaa_stage2")

    cfg.ensure_dirs()

    stage1_path = Path(args.stage1).resolve()
    if not stage1_path.exists():
        raise FileNotFoundError(f"Stage1 input file not found: {stage1_path}")

    print(f"[RUN] workdir={cfg.workdir}")
    print(f"[RUN] run_version={cfg.run_version}")
    print(f"[RUN] stage1={stage1_path}")
    print(f"[RUN] llm_api_type={cfg.llm_api_type}")
    print(f"[RUN] llm_model={cfg.llm_model}")
    print(f"[RUN] llm_base_url={cfg.llm_base_url}")

    df_stage1 = pd.read_excel(stage1_path, engine="openpyxl")

    if "GSM_ID" not in df_stage1.columns or "GSE_ID" not in df_stage1.columns:
        raise ValueError(
            f"Stage1 input file does not look like a Stage1 output. "
            f"Required columns missing from: {stage1_path}"
        )

    # -------------------------
    # Stage2 pass1
    # -------------------------
    if args.skip_pass1:
        if not args.stage2_pass1:
            raise ValueError("--stage2-pass1 is required when --skip-pass1 is used.")
        stage2_pass1_path = Path(args.stage2_pass1).resolve()
        if not stage2_pass1_path.exists():
            raise FileNotFoundError(f"Stage2 pass1 file not found: {stage2_pass1_path}")
        df_stage2_pass1 = pd.read_excel(stage2_pass1_path, engine="openpyxl")
    else:
        df_stage2_pass1 = run_stage2_postprocessing(cfg, df_stage1)

        out_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_pass1.xlsx"
        out_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_pass1.parquet"
        df_stage2_pass1.to_excel(out_xlsx, index=False)
        df_stage2_pass1.to_parquet(out_parq, index=False)

        print("[SAVED] Stage2 pass1 Excel:", out_xlsx)
        print("[SAVED] Stage2 pass1 Parquet:", out_parq)

    if "GSM_ID" not in df_stage2_pass1.columns or "GSE_ID" not in df_stage2_pass1.columns:
        raise ValueError("Stage2 pass1 output is missing required columns GSM_ID/GSE_ID.")

    # -------------------------
    # Review
    # -------------------------
    reviewer = ReviewerV2()
    reviewer.review_stage2_rules(df_stage2_pass1)
    reviewer.review_within_gse(df_stage2_pass1)
    rule_review_df = reviewer.to_dataframe()

    review_dir = Path(cfg.review_dir)
    rule_review_path = review_dir / f"{cfg.run_version}_stage2_rule_review.xlsx"
    rule_review_df.to_excel(rule_review_path, index=False)
    print("[SAVED] Stage2 rule review:", rule_review_path)

    llm_reviewer = ReviewerLLMV2(
        cfg=cfg,
        debug_dir=Path(cfg.debug_dir) / "reviewer",
        llm_review_cfg=LLMReviewConfig(
            max_row_reviews_per_run=int(cfg.max_row_reviews_per_run),
            max_gse_reviews_per_run=int(cfg.max_gse_reviews_per_run),
            row_fields_focus=[
                "Disease", "Tissue", "Pert", "Pert_Type",
                "Sex", "Age", "Model_Type", "SampleType", "Specimen_Type",
            ],
        ),
    )

    flagged_rows_df = reviewer.get_flagged_rows_for_llm()

    llm_row_review_df = llm_reviewer.review_rows(
        df_stage2=df_stage2_pass1,
        df_input_stage1_source=df_stage1,
        flagged_rows_df=flagged_rows_df,
    )
    llm_row_review_path = review_dir / f"{cfg.run_version}_stage2_llm_row_review.xlsx"
    llm_row_review_df.to_excel(llm_row_review_path, index=False)
    print("[SAVED] Stage2 LLM row review:", llm_row_review_path)

    llm_gse_review_df = llm_reviewer.review_gses(
        df_stage2=df_stage2_pass1,
        df_input_stage1_source=df_stage1,
        flagged_rows_df=flagged_rows_df,
    )
    llm_gse_review_path = review_dir / f"{cfg.run_version}_stage2_llm_gse_review.xlsx"
    llm_gse_review_df.to_excel(llm_gse_review_path, index=False)
    print("[SAVED] Stage2 LLM GSE review:", llm_gse_review_path)

    rerun_queue_df = reviewer.build_reannotation_queue(
        rule_review_df=rule_review_df,
        llm_row_review_df=llm_row_review_df,
        llm_gse_review_df=llm_gse_review_df,
    )
    rerun_queue_path = review_dir / f"{cfg.run_version}_stage2_reannotation_queue.xlsx"
    rerun_queue_df.to_excel(rerun_queue_path, index=False)
    print("[SAVED] Stage2 reannotation queue:", rerun_queue_path)

    # -------------------------
    # Stage2 rerun executor
    # -------------------------
    df_stage2_final = run_stage2_postprocessing_v2(
        cfg=cfg,
        df_stage1=df_stage1,
        df_queue=rerun_queue_df,
        run_pass1=False,
        df_stage2_pass1=df_stage2_pass1,
    )

    final_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post_final.xlsx"
    final_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post_final.parquet"
    df_stage2_final.to_excel(final_xlsx, index=False)
    df_stage2_final.to_parquet(final_parq, index=False)

    print("[SAVED] Stage2 final Excel:", final_xlsx)
    print("[SAVED] Stage2 final Parquet:", final_parq)

    # -------------------------
    # Basic integrity summary
    # -------------------------
    result = {
        "run_version": cfg.run_version,
        "stage1_input_file": str(stage1_path),
        "stage1_rows": int(df_stage1.shape[0]),
        "stage2_pass1_rows": int(df_stage2_pass1.shape[0]),
        "stage2_final_rows": int(df_stage2_final.shape[0]),
        "stage2_pass1_unique_gsm": int(df_stage2_pass1["GSM_ID"].astype(str).nunique()),
        "stage2_final_unique_gsm": int(df_stage2_final["GSM_ID"].astype(str).nunique()),
        "stage2_pass1_dup_gsm": int(df_stage2_pass1["GSM_ID"].astype(str).duplicated().sum()),
        "stage2_final_dup_gsm": int(df_stage2_final["GSM_ID"].astype(str).duplicated().sum()),
        "rule_review_rows": int(rule_review_df.shape[0]),
        "llm_row_review_rows": int(llm_row_review_df.shape[0]),
        "llm_gse_review_rows": int(llm_gse_review_df.shape[0]),
        "reannotation_queue_rows": int(rerun_queue_df.shape[0]),
        "stage2_final_xlsx": str(final_xlsx),
        "stage2_final_parquet": str(final_parq),
        "rule_review_xlsx": str(rule_review_path),
        "llm_row_review_xlsx": str(llm_row_review_path),
        "llm_gse_review_xlsx": str(llm_gse_review_path),
        "reannotation_queue_xlsx": str(rerun_queue_path),
    }

    if result["stage2_pass1_rows"] != result["stage1_rows"]:
        result["warning_stage2_pass1_row_mismatch"] = True
    if result["stage2_final_rows"] != result["stage1_rows"]:
        result["warning_stage2_final_row_mismatch"] = True

    summary_path = Path(cfg.ledger_dir) / f"{cfg.run_version}_run_stage2_result.json"
    summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("[SAVED] Stage2 summary:", summary_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()