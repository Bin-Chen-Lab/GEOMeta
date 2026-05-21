from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from geo_annotation_agent.config import default_config
from geo_annotation_agent.stage0_retrieve import run_stage0_retrieval


def make_run_version(prefix: str = "gaa_stage0") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def main():
    ap = argparse.ArgumentParser(
        description="Run Stage 0 GEO retrieval: GSE list -> GSE/GSM metadata -> Stage1-ready input table"
    )
    ap.add_argument(
        "--workdir",
        default=".",
        help="Project working directory. Defaults to current directory.",
    )
    ap.add_argument(
        "--gse-list",
        default=None,
        help=(
            "Optional GSE list input override (.xlsx/.csv/.tsv/.txt). "
            "If omitted, config.gse_list_input is used."
        ),
    )
    ap.add_argument(
        "--run-version",
        default=None,
        help="Optional run version override.",
    )
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    cfg = default_config(workdir)

    if args.run_version:
        cfg.run_version = args.run_version
    else:
        cfg.run_version = make_run_version("gaa_stage0")

    if args.gse_list:
        cfg.gse_list_input = Path(args.gse_list).resolve()

    cfg.ensure_dirs()

    # Stage 0 only needs the GSE list input.
    # It does NOT need Stage 3 mapping resources.
    cfg.validate_paths(
        require_gse_list=True,
        require_stage3_resources=False,
        require_prompts=False,
    )

    print(f"[RUN] workdir={cfg.workdir}")
    print(f"[RUN] run_version={cfg.run_version}")
    print(f"[RUN] gse_list_input={cfg.gse_list_input}")

    df_stage0 = run_stage0_retrieval(cfg)

    result = {
        "run_version": cfg.run_version,
        "gse_list_input": str(cfg.gse_list_input),
        "stage0_rows": int(df_stage0.shape[0]),
        "stage0_output_xlsx": str(Path(cfg.outputs_dir) / f"{cfg.run_version}_stage0_input.xlsx"),
        "stage0_output_parquet": str(Path(cfg.outputs_dir) / f"{cfg.run_version}_stage0_input.parquet"),
        "stage0_ledger_csv": str(Path(cfg.ledger_dir) / f"{cfg.run_version}_stage0_retrieval_ledger.csv"),
        "stage0_failed_gse_xlsx": str(Path(cfg.review_dir) / f"{cfg.run_version}_stage0_failed_gse.xlsx"),
        "stage0_failed_gsm_xlsx": str(Path(cfg.review_dir) / f"{cfg.run_version}_stage0_failed_gsm.xlsx"),
        "stage0_summary_json": str(Path(cfg.ledger_dir) / f"{cfg.run_version}_stage0_summary.json"),
    }

    summary_fp = Path(cfg.ledger_dir) / f"{cfg.run_version}_run_stage0_result.json"
    summary_fp.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("[SAVED] Stage0 runner summary:", summary_fp)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()