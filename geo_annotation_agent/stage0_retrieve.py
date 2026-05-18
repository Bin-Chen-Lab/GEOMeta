from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import requests


# -------------------------
# GEO URLs
# -------------------------
def geo_soft_url(acc: str) -> str:
    """
    GEO text/quick view from GEO website directly.
    Works for both GSE and GSM accessions.
    """
    return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={acc}&targ=self&form=text&view=quick"


# -------------------------
# Small helpers
# -------------------------
def _s(x) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, float) and x != x:
            return ""
    except Exception:
        pass
    return str(x).strip()


def _chunk(xs: List[Any], n: int) -> List[List[Any]]:
    return [xs[i:i + n] for i in range(0, len(xs), n)]


def _unique_preserve_order(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _clean_text(v: str) -> str:
    """
    Light cleanup for GEO text fields.
    """
    v = _s(v)
    if not v:
        return ""
    v = v.replace("\xa0", " ")
    v = v.replace("Â®", "®")
    v = re.sub(r"\s+", " ", v).strip()
    return v


def _join_unique_clean(vals: List[str], sep: str = " | ") -> str:
    out = []
    seen = set()
    for v in vals:
        sv = _clean_text(v)
        if sv and sv not in seen:
            seen.add(sv)
            out.append(sv)
    return sep.join(out)


# -------------------------
# Retrieval ledger rows
# -------------------------
@dataclass
class Stage0LedgerRow:
    GSE_ID: str
    expected_gsm_count: int
    retrieved_gsm_count: int
    failed_gsm_count: int
    chunk_count: int
    status: str
    reason: str = ""


# -------------------------
# Cache-backed fetch
# -------------------------
def fetch_with_cache(
    url: str,
    cache_path: Path,
    timeout_sec: int = 30,
    n_retry: int = 6,
    sleep_sec: float = 1.5,
) -> str:
    """
    Fetch text from URL with local cache.
    """
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="ignore")

    last_err = None
    for attempt in range(1, n_retry + 1):
        try:
            r = requests.get(url, timeout=timeout_sec)
            r.raise_for_status()
            txt = r.text
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(txt, encoding="utf-8")
            return txt
        except Exception as e:
            last_err = e
            if attempt < n_retry:
                time.sleep(sleep_sec)

    raise RuntimeError(f"Failed to fetch {url} after {n_retry} attempts: {last_err}")


# -------------------------
# GEO SOFT-style parsing
# -------------------------
def parse_series_sample_ids(gse_soft_text: str) -> List[str]:
    """
    Parse linked GSM IDs from GSE soft/quick text.
    """
    gsms = []
    for line in gse_soft_text.splitlines():
        line = line.strip()
        if line.startswith("!Series_sample_id"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                gsm = parts[1].strip()
                if gsm.startswith("GSM"):
                    gsms.append(gsm)
    return _unique_preserve_order(gsms)


def parse_soft_fields(text: str, entity_prefix: str) -> Dict[str, List[str]]:
    """
    Parse lines like:
      !Series_title = ...
      !Sample_characteristics_ch1 = ...
    into:
      {"title": [...], "characteristics_ch1": [...]}
    """
    out: Dict[str, List[str]] = {}
    marker = f"!{entity_prefix}_"

    for line in text.splitlines():
        line = line.rstrip()
        if not line.startswith(marker):
            continue

        body = line[len(marker):]
        if " = " not in body:
            continue

        key, val = body.split(" = ", 1)
        key = key.strip()
        val = val.strip()

        out.setdefault(key, []).append(val)

    return out


# -------------------------
# GSE / GSM text builders
# -------------------------
def build_gse_info(gse_id: str, gse_soft_text: str) -> str:
    """
    Build a cleaner, annotation-oriented GSE_Info block.
    Intentionally excludes:
      - duplicated GSE_ID
      - Platform_ID
      - PubMed_ID
      - Submission_Date
      - Last_Update_Date
      - Relation
      - raw supplementary file URLs
      - GSM_Counts
      - Linked_GSM_IDs
    """
    d = parse_soft_fields(gse_soft_text, "Series")

    def first_nonempty(key: str) -> str:
        vals = [_clean_text(v) for v in d.get(key, []) if _clean_text(v)]
        return vals[0] if vals else ""

    def join_unique(key: str) -> str:
        return _join_unique_clean(d.get(key, []))

    lines = [f"GSE ID: {gse_id}"]

    title = first_nonempty("title")
    if title:
        lines.append(f"GSE Title: {title}")

    exp_type = join_unique("type")
    if exp_type:
        lines.append(f"Experiment Type: {exp_type}")

    summary = first_nonempty("summary")
    if summary:
        lines.append(f"GSE Summary: {summary}")

    overall_design = first_nonempty("overall_design")
    if overall_design:
        lines.append(f"GSE Overall Design: {overall_design}")

    treatment_protocol = join_unique("treatment_protocol_ch1")
    if treatment_protocol:
        lines.append(f"Treatment Protocol: {treatment_protocol}")

    growth_protocol = join_unique("growth_protocol_ch1")
    if growth_protocol:
        lines.append(f"Growth Protocol: {growth_protocol}")

    molecule = join_unique("molecule_ch1")
    if molecule:
        lines.append(f"Molecule: {molecule}")

    extract_protocol = join_unique("extract_protocol_ch1")
    if extract_protocol:
        lines.append(f"Extraction: {extract_protocol}")

    library_strategy = join_unique("library_strategy")
    if library_strategy:
        lines.append(f"Library Strategy: {library_strategy}")

    library_source = join_unique("library_source")
    if library_source:
        lines.append(f"Library Source: {library_source}")

    library_selection = join_unique("library_selection")
    if library_selection:
        lines.append(f"Library Selection: {library_selection}")

    data_processing = join_unique("data_processing")
    if data_processing:
        lines.append(f"Data Processing: {data_processing}")

    genome_build = join_unique("genome_build")
    if genome_build:
        lines.append(f"Genome Build: {genome_build}")

    supp_fmt = join_unique("supplementary_files_format_and_content")
    if supp_fmt:
        lines.append(f"Supplementary Files Format And Content: {supp_fmt}")

    # Optional lightweight supplementary summary
    supp_files = [_clean_text(v) for v in d.get("supplementary_file", []) if _clean_text(v)]
    if not supp_files:
        lines.append("Supplementary: NONE")

    return "\n".join(lines).strip()


def build_gsm_info(gsm_id: str, gsm_soft_text: str) -> str:
    """
    Build a cleaner, annotation-oriented GSM_Info block.
    Intentionally excludes:
      - duplicated GSM_ID
      - wrapper markers
      - Extract_Protocol (already often captured in GSE_Info)
      - Data_Processing
      - Platform_ID
      - Relation
      - repeated library fields already in GSE_Info
    """
    d = parse_soft_fields(gsm_soft_text, "Sample")

    def first_nonempty(key: str) -> str:
        vals = [_clean_text(v) for v in d.get(key, []) if _clean_text(v)]
        return vals[0] if vals else ""

    def all_nonempty(key: str) -> List[str]:
        vals = []
        seen = set()
        for v in d.get(key, []):
            sv = _clean_text(v)
            if sv and sv not in seen:
                seen.add(sv)
                vals.append(sv)
        return vals

    lines = [f"GSM ID: {gsm_id}"]

    title = first_nonempty("title")
    if title:
        lines.append(f"Title: {title}")

    sample_type = first_nonempty("type")
    if sample_type:
        lines.append(f"Sample Type: {sample_type}")

    source_name = first_nonempty("source_name_ch1")
    if source_name:
        lines.append(f"Source Name: {source_name}")

    organism = first_nonempty("organism_ch1")
    if organism:
        lines.append(f"Organism: {organism}")

    for v in all_nonempty("characteristics_ch1"):
        lines.append(v)

    treatment_protocol = first_nonempty("treatment_protocol_ch1")
    if treatment_protocol:
        lines.append(f"Treatment Protocol: {treatment_protocol}")

    growth_protocol = first_nonempty("growth_protocol_ch1")
    if growth_protocol:
        lines.append(f"Growth Protocol: {growth_protocol}")

    description = first_nonempty("description")
    if description:
        lines.append(f"Description: {description}")

    return "\n".join(lines).strip()

def _parse_gsm_info_lines(gsm_info: str) -> Dict[str, str]:
    """
    Parse selected labeled lines from a built GSM_Info block.
    """
    out = {}
    for line in str(gsm_info).splitlines():
        line = line.strip()
        if not line or ": " not in line:
            continue

        key, val = line.split(": ", 1)
        key = key.strip()
        val = _clean_text(val)

        if key in {"Treatment Protocol", "Growth Protocol", "Description"} and val:
            out[key] = val

    return out


def _remove_shared_lines_from_gsm_info(gsm_info: str, shared_fields: Dict[str, str]) -> str:
    """
    Remove GSM_Info lines that were promoted to GSE_Info.
    """
    lines = []
    for line in str(gsm_info).splitlines():
        stripped = line.strip()
        remove = False

        for key, val in shared_fields.items():
            if stripped == f"{key}: {val}":
                remove = True
                break

        if not remove:
            lines.append(line)

    return "\n".join(lines).strip()


def promote_shared_gsm_fields_to_gse_info(
    gse_info: str,
    gsm_records: List[Dict[str, str]],
) -> tuple[str, List[Dict[str, str]]]:
    """
    Move GSM-level fields that are identical across all retrieved GSMs in a GSE
    into GSE_Info to reduce repeated token usage.

    Conservative rule:
      - Only promote if exactly one unique non-empty value exists across GSMs.
      - Only promote Treatment Protocol, Growth Protocol, and Description.
    """
    if not gsm_records:
        return gse_info, gsm_records

    candidate_fields = ["Treatment Protocol", "Growth Protocol", "Description"]
    parsed = [_parse_gsm_info_lines(r.get("GSM_Info", "")) for r in gsm_records]

    shared_fields = {}

    for field in candidate_fields:
        vals = [_clean_text(p.get(field, "")) for p in parsed]
        nonempty_vals = [v for v in vals if v]

        # Require the field to be present for all GSMs and exactly identical.
        if len(nonempty_vals) == len(gsm_records) and len(set(nonempty_vals)) == 1:
            shared_fields[field] = nonempty_vals[0]

    if not shared_fields:
        return gse_info, gsm_records

    gse_lines = [gse_info.strip()] if gse_info and gse_info.strip() else []

    for field, val in shared_fields.items():
        label = f"Shared GSM {field}"
        new_line = f"{label}: {val}"
        if new_line not in gse_info:
            gse_lines.append(new_line)

    updated_records = []
    for rec in gsm_records:
        rec2 = dict(rec)
        rec2["GSM_Info"] = _remove_shared_lines_from_gsm_info(
            rec2.get("GSM_Info", ""),
            shared_fields,
        )
        updated_records.append(rec2)

    return "\n".join(gse_lines).strip(), updated_records



def build_chunked_gsm_text(gsm_records: List[Dict[str, str]]) -> str:
    """
    Combine multiple GSM metadata blocks into one chunk text for Stage1.
    No wrapper markers; just clean GSM blocks separated by blank lines.
    """
    blocks = []
    for rec in gsm_records:
        gsm_info = rec["GSM_Info"]
        blocks.append(gsm_info.strip())
    return "\n\n".join(blocks).strip()


# -------------------------
# Input loader
# -------------------------
def load_gse_list(gse_list_input: Path) -> List[str]:
    """
    Accepts:
      - .xlsx / .xls
      - .csv / .tsv
      - .txt
    Expected:
      - column named GSE_ID
      - or first column if no header match
    """
    p = Path(gse_list_input)
    if not p.exists():
        raise FileNotFoundError(f"GSE list input not found: {p}")

    if p.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(p, engine="openpyxl")
    elif p.suffix.lower() == ".csv":
        df = pd.read_csv(p)
    elif p.suffix.lower() == ".tsv":
        df = pd.read_csv(p, sep="\t")
    elif p.suffix.lower() == ".txt":
        vals = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        vals = [v for v in vals if v.startswith("GSE")]
        return _unique_preserve_order(vals)
    else:
        raise ValueError(f"Unsupported gse_list_input format: {p.suffix}")

    if "GSE_ID" in df.columns:
        vals = df["GSE_ID"].astype(str).map(str.strip).tolist()
    else:
        vals = df.iloc[:, 0].astype(str).map(str.strip).tolist()

    vals = [v for v in vals if v.startswith("GSE")]
    return _unique_preserve_order(vals)


# -------------------------
# Main retrieval logic
# -------------------------
def run_stage0_retrieval(
    cfg,
    gse_ids: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Stage0:
      Input: GSE accession list
      Output: Stage1-ready chunk table with columns:
        - GSE_ID
        - GSE_Info
        - GSM_Info
        - GSM_Counts
        - Chunk_Index
        - Chunk_ID
        - GSM_ID_List
        - Retrieved_GSM_Count
        - Failed_GSM_Count
    """
    cfg.ensure_dirs()
    cfg.validate_paths(
        require_gse_list=(gse_ids is None),
        require_stage3_resources=False,
        require_prompts=False,
    )

    if gse_ids is None:
        gse_ids = load_gse_list(Path(cfg.gse_list_input))

    if not gse_ids:
        raise ValueError("No GSE IDs found in input.")

    rows: List[Dict[str, Any]] = []
    ledger_rows: List[Stage0LedgerRow] = []
    failed_gse_rows: List[Dict[str, Any]] = []
    failed_gsm_rows: List[Dict[str, Any]] = []

    for gse_id in gse_ids:
        try:
            gse_cache_fp = Path(cfg.geo_gse_cache_dir) / f"{gse_id}.txt"
            gse_txt = fetch_with_cache(
                url=geo_soft_url(gse_id),
                cache_path=gse_cache_fp,
                timeout_sec=int(cfg.geo_timeout_sec),
                n_retry=int(cfg.geo_fetch_retry),
            )

            gsm_ids = parse_series_sample_ids(gse_txt)
            gsm_ids = _unique_preserve_order(gsm_ids)

            if not gsm_ids:
                ledger_rows.append(
                    Stage0LedgerRow(
                        GSE_ID=gse_id,
                        expected_gsm_count=0,
                        retrieved_gsm_count=0,
                        failed_gsm_count=0,
                        chunk_count=0,
                        status="failed",
                        reason="No GSM IDs parsed from GSE text.",
                    )
                )
                failed_gse_rows.append(
                    {
                        "GSE_ID": gse_id,
                        "reason": "No GSM IDs parsed from GSE text.",
                    }
                )
                continue

            gse_info = build_gse_info(gse_id, gse_txt)

            gsm_records: List[Dict[str, str]] = []
            failed_gsms_for_this_gse = 0

            for gsm_id in gsm_ids:
                try:
                    gsm_cache_fp = Path(cfg.geo_gsm_cache_dir) / f"{gsm_id}.txt"
                    gsm_txt = fetch_with_cache(
                        url=geo_soft_url(gsm_id),
                        cache_path=gsm_cache_fp,
                        timeout_sec=int(cfg.geo_timeout_sec),
                        n_retry=int(cfg.geo_fetch_retry),
                    )
                    gsm_info = build_gsm_info(gsm_id, gsm_txt)
                    gsm_records.append(
                        {
                            "GSM_ID": gsm_id,
                            "GSM_Info": gsm_info,
                        }
                    )
                except Exception as e:
                    failed_gsms_for_this_gse += 1
                    failed_gsm_rows.append(
                        {
                            "GSE_ID": gse_id,
                            "GSM_ID": gsm_id,
                            "reason": repr(e),
                        }
                    )

            retrieved_count = len(gsm_records)
            expected_count = len(gsm_ids)

            if retrieved_count == 0:
                ledger_rows.append(
                    Stage0LedgerRow(
                        GSE_ID=gse_id,
                        expected_gsm_count=expected_count,
                        retrieved_gsm_count=0,
                        failed_gsm_count=failed_gsms_for_this_gse,
                        chunk_count=0,
                        status="failed",
                        reason="All GSM retrievals failed.",
                    )
                )
                failed_gse_rows.append(
                    {
                        "GSE_ID": gse_id,
                        "reason": "All GSM retrievals failed.",
                    }
                )
                continue

            # Promote GSM-level fields shared by all samples in this GSE into GSE_Info.
            # This reduces repeated text in GSM_Info chunks and lowers Stage1 token usage.
            gse_info, gsm_records = promote_shared_gsm_fields_to_gse_info(
                gse_info=gse_info,
                gsm_records=gsm_records,
            )

            chunks = _chunk(gsm_records, int(cfg.stage0_chunk_size))

            for ci, chunk in enumerate(chunks, start=1):
                gsm_id_list = [r["GSM_ID"] for r in chunk]
                gsm_info_chunk = build_chunked_gsm_text(chunk)

                rows.append(
                    {
                        "GSE_ID": gse_id,
                        "GSE_Info": gse_info,
                        "GSM_Info": gsm_info_chunk,
                        "GSM_Counts": len(chunk),
                        "Chunk_Index": ci,
                        "Chunk_ID": f"{gse_id}_chunk_{ci}",
                        "GSM_ID_List": " | ".join(gsm_id_list),
                        "Retrieved_GSM_Count": retrieved_count,
                        "Failed_GSM_Count": failed_gsms_for_this_gse,
                    }
                )

            status = "ok" if failed_gsms_for_this_gse == 0 else "partial"
            reason = "" if status == "ok" else f"{failed_gsms_for_this_gse} GSM retrieval(s) failed."

            ledger_rows.append(
                Stage0LedgerRow(
                    GSE_ID=gse_id,
                    expected_gsm_count=expected_count,
                    retrieved_gsm_count=retrieved_count,
                    failed_gsm_count=failed_gsms_for_this_gse,
                    chunk_count=len(chunks),
                    status=status,
                    reason=reason,
                )
            )

        except Exception as e:
            ledger_rows.append(
                Stage0LedgerRow(
                    GSE_ID=gse_id,
                    expected_gsm_count=0,
                    retrieved_gsm_count=0,
                    failed_gsm_count=0,
                    chunk_count=0,
                    status="failed",
                    reason=repr(e),
                )
            )
            failed_gse_rows.append(
                {
                    "GSE_ID": gse_id,
                    "reason": repr(e),
                }
            )

    df_stage0 = pd.DataFrame(rows)

    wanted_cols = [
        "GSE_ID",
        "GSE_Info",
        "GSM_Info",
        "GSM_Counts",
        "Chunk_Index",
        "Chunk_ID",
        "GSM_ID_List",
        "Retrieved_GSM_Count",
        "Failed_GSM_Count",
    ]
    for c in wanted_cols:
        if c not in df_stage0.columns:
            df_stage0[c] = ""
    df_stage0 = df_stage0[wanted_cols]

    # Save outputs
    out_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage0_input.xlsx"
    out_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage0_input.parquet"

    # Excel is useful for inspection, but parquet is the authoritative file
    # because Excel cells may truncate very long text.
    df_stage0.to_excel(out_xlsx, index=False)
    df_stage0.to_parquet(out_parq, index=False)

    df_ledger = pd.DataFrame([asdict(r) for r in ledger_rows])
    ledger_fp = Path(cfg.ledger_dir) / f"{cfg.run_version}_stage0_retrieval_ledger.csv"
    df_ledger.to_csv(ledger_fp, index=False)

    df_failed_gse = pd.DataFrame(failed_gse_rows)
    failed_gse_fp = Path(cfg.review_dir) / f"{cfg.run_version}_stage0_failed_gse.xlsx"
    df_failed_gse.to_excel(failed_gse_fp, index=False)

    df_failed_gsm = pd.DataFrame(failed_gsm_rows)
    failed_gsm_fp = Path(cfg.review_dir) / f"{cfg.run_version}_stage0_failed_gsm.xlsx"
    df_failed_gsm.to_excel(failed_gsm_fp, index=False)

    summary = {
        "run_version": cfg.run_version,
        "input_gse_count": len(gse_ids),
        "stage0_chunk_rows": int(df_stage0.shape[0]),
        "unique_gse_in_output": int(df_stage0["GSE_ID"].nunique()) if not df_stage0.empty else 0,
        "total_gsm_expected": int(df_ledger["expected_gsm_count"].sum()) if not df_ledger.empty else 0,
        "total_gsm_retrieved": int(df_ledger["retrieved_gsm_count"].sum()) if not df_ledger.empty else 0,
        "total_gsm_failed": int(df_ledger["failed_gsm_count"].sum()) if not df_ledger.empty else 0,
        "failed_gse_count": int((df_ledger["status"] == "failed").sum()) if not df_ledger.empty else 0,
        "partial_gse_count": int((df_ledger["status"] == "partial").sum()) if not df_ledger.empty else 0,
        "output_xlsx": str(out_xlsx),
        "output_parquet": str(out_parq),
        "ledger_csv": str(ledger_fp),
        "failed_gse_xlsx": str(failed_gse_fp),
        "failed_gsm_xlsx": str(failed_gsm_fp),
    }

    summary_fp = Path(cfg.ledger_dir) / f"{cfg.run_version}_stage0_summary.json"
    summary_fp.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("[SAVED] Stage0 input Excel:", out_xlsx)
    print("[SAVED] Stage0 input Parquet:", out_parq)
    print("[SAVED] Stage0 retrieval ledger:", ledger_fp)
    print("[SAVED] Stage0 failed GSE report:", failed_gse_fp)
    print("[SAVED] Stage0 failed GSM report:", failed_gsm_fp)
    print("[SAVED] Stage0 summary:", summary_fp)
    print("Stage0 DONE rows:", df_stage0.shape)

    return df_stage0