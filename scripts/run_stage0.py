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

    ap.add_argument(
        "--stage0-max-gsms-per-chunk",
        type=int,
        default=None,
        help=(
            "Manual global GSM-count cap for Stage0 chunks. "
            "If set, this applies to all GSEs and overrides adaptive large-GSE chunking."
        ),
    )
    ap.add_argument(
        "--disable-stage0-auto-large-gse-chunking",
        action="store_true",
        help="Disable adaptive large-GSE chunking.",
    )
    ap.add_argument(
        "--stage0-auto-large-gse-min-gsms",
        type=int,
        default=None,
        help="Retrieved GSM-count threshold for adaptive large-GSE splitting. Default: 300.",
    )
    ap.add_argument(
        "--stage0-auto-large-gse-max-gsms-per-chunk",
        type=int,
        default=None,
        help="Chunk size used for adaptive large-GSE splitting. Default: 75.",
    )
    ap.add_argument(
        "--stage0-force-split-gse-ids",
        default=None,
        help=(
            "Optional comma-separated GSE IDs to force split, for known problematic GSEs. "
            "Example: GSE314188,GSE312139"
        ),
    )
    ap.add_argument(
        "--stage0-force-split-max-gsms-per-chunk",
        type=int,
        default=None,
        help="Chunk size for GSE IDs listed in --stage0-force-split-gse-ids. Default: 75.",
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

    if args.stage0_max_gsms_per_chunk is not None:
        cfg.stage0_max_gsms_per_chunk = int(args.stage0_max_gsms_per_chunk)

    cfg.stage0_auto_large_gse_chunking = not bool(args.disable_stage0_auto_large_gse_chunking)

    if args.stage0_auto_large_gse_min_gsms is not None:
        cfg.stage0_auto_large_gse_min_gsms = int(args.stage0_auto_large_gse_min_gsms)

    if args.stage0_auto_large_gse_max_gsms_per_chunk is not None:
        cfg.stage0_auto_large_gse_max_gsms_per_chunk = int(args.stage0_auto_large_gse_max_gsms_per_chunk)

    if args.stage0_force_split_gse_ids is not None:
        cfg.stage0_force_split_gse_ids = str(args.stage0_force_split_gse_ids)

    if args.stage0_force_split_max_gsms_per_chunk is not None:
        cfg.stage0_force_split_max_gsms_per_chunk = int(args.stage0_force_split_max_gsms_per_chunk)

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
    print(
        "[RUN] stage0_chunking_policy=metadata-token-aware plus adaptive large-GSE chunking; "
        "manual stage0_max_gsms_per_chunk overrides adaptive policy when > 0"
    )
    print(f"[RUN] stage0_metadata_safe_input_token_limit={getattr(cfg, 'stage0_metadata_safe_input_token_limit', 180000)}")
    print(f"[RUN] stage0_max_gsms_per_chunk={getattr(cfg, 'stage0_max_gsms_per_chunk', 0)}")
    print(f"[RUN] stage0_auto_large_gse_chunking={getattr(cfg, 'stage0_auto_large_gse_chunking', True)}")
    print(f"[RUN] stage0_auto_large_gse_min_gsms={getattr(cfg, 'stage0_auto_large_gse_min_gsms', 300)}")
    print(f"[RUN] stage0_auto_large_gse_max_gsms_per_chunk={getattr(cfg, 'stage0_auto_large_gse_max_gsms_per_chunk', 75)}")
    print(f"[RUN] stage0_force_split_gse_ids={getattr(cfg, 'stage0_force_split_gse_ids', '')}")
    print("[RUN] full-fidelity restart artifact will be stage0_input.parquet; Excel is review copy only")

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