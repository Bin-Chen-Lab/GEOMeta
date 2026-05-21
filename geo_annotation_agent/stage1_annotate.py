from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .llm_client import BaseLLM, make_llm_from_config


# -------------------------
# Canonical Stage1 schema
# -------------------------
STAGE1_FIELDS = [
    "GSM_ID",
    "GSE_ID",
    "Seq_Type",
    "Organism",
    "Strain",
    "Genotype",
    "RNA_Library",
    "RNA_Source",
    "Tissue",
    "Experimental_Setting",
    "Model_Type",
    "Disease",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "SampleType",
    "Specimen_Type",
    "Race",
    "Ethnicity",
    "Age",
    "Sex",
    "Timepoint",
    "Outcome",
]

ROLE_FIELDS = {
    "experimental_context": [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type",
        "Organism",
        "Strain",
        "Genotype",
        "RNA_Library",
        "RNA_Source",
        "Tissue",
        "Experimental_Setting",
        "Model_Type",
    ],
    "biological_context": [
        "GSM_ID",
        "GSE_ID",
        "Disease",
    ],
    "perturbation": [
        "GSM_ID",
        "GSE_ID",
        "GSE_Pert",
        "GSM_Pert",
        "Pert",
        "Pert_Dose",
        "Pert_Freq",
        "Pert_Duration",
        "Route_Admin",
    ],
    "sample_metadata": [
        "GSM_ID",
        "GSE_ID",
        "SampleType",
        "Specimen_Type",
        "Race",
        "Ethnicity",
        "Age",
        "Sex",
        "Timepoint",
        "Outcome",
    ],
}

ROLE_PROMPT_FILENAMES = {
    "common": "stage1_common_system_prompt.md",
    "experimental_context": "experimental_context_prompt.md",
    "biological_context": "biological_context_prompt.md",
    "perturbation": "perturbation_prompt.md",
    "sample_metadata": "sample_metadata_prompt.md",
}


# -------------------------
# Small helpers
# -------------------------
def _s(x) -> str:
    if x is None:
        return "NA"
    try:
        if isinstance(x, float) and x != x:
            return "NA"
    except Exception:
        pass

    v = str(x).strip()
    return "NA" if v.lower() in {"", "nan"} else v


def _extract_json_block(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        return m.group(0)

    raise ValueError("No JSON object found in model output.")


def _safe_json_loads_with_simple_repair(text: str) -> Dict[str, Any]:
    raw = _extract_json_block(text)

    try:
        return json.loads(raw)
    except Exception:
        pass

    # Very light repairs only
    repaired = raw.replace("\t", " ")
    repaired = re.sub(r",\s*}", "}", repaired)
    repaired = re.sub(r",\s*]", "]", repaired)

    return json.loads(repaired)


def _read_prompt_text(path: Path) -> str:
    """Read Stage 1 prompt files from Markdown, plain text, or DOCX.

    The public GEOMeta repository now stores prompts as `.md` files. DOCX
    support is kept only for backward compatibility with older local runs.
    """
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8").strip()

    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        paras = [p.text.rstrip() for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(paras).strip()

    raise ValueError(f"Unsupported prompt file type: {path}")


def _resolve_annotation_prompt_dir(cfg) -> Path:
    candidates = [
        Path(cfg.workdir) / "prompts" / "stage1",
        Path(cfg.workdir) / "stage1",
        Path(cfg.workdir) / "Annotation_Prompts",
        Path(cfg.workdir) / "Annotation_Prompt",
        Path(cfg.workdir) / "Prompts_Annotation",
        Path(getattr(cfg, "post_prompt_dir", Path(cfg.workdir))),
    ]

    for d in candidates:
        if d.exists():
            return d

    raise FileNotFoundError(
        "Could not locate Stage 1 prompt directory. Expected prompts/stage1/ "
        "or one of the legacy prompt directories."
    )


def _load_role_prompt(cfg, role_name: str) -> str:
    prompt_dir = _resolve_annotation_prompt_dir(cfg)

    common_fp = prompt_dir / ROLE_PROMPT_FILENAMES["common"]
    role_fp = prompt_dir / ROLE_PROMPT_FILENAMES[role_name]

    if not common_fp.exists():
        raise FileNotFoundError(f"Missing common Stage1 prompt file: {common_fp}")

    if not role_fp.exists():
        raise FileNotFoundError(f"Missing Stage1 role prompt file for {role_name}: {role_fp}")

    common_text = _read_prompt_text(common_fp)
    role_text = _read_prompt_text(role_fp)

    return f"{common_text}\n\n{role_text}".strip()


def _extract_expected_gsm_ids(gsm_info_text: str) -> List[str]:
    """
    Supports:
      - Stage0 chunk format with ### GSM_START: GSM...
      - generic GSM mentions in text
    """
    starts = re.findall(r"###\s*GSM_START:\s*(GSM\d+)", gsm_info_text, flags=re.IGNORECASE)
    if starts:
        return starts

    gsms = re.findall(r"\bGSM\d+\b", gsm_info_text)
    out = []
    seen = set()

    for g in gsms:
        if g not in seen:
            seen.add(g)
            out.append(g)

    return out


def _make_empty_row(gsm_id: str, gse_id: str) -> Dict[str, str]:
    row = {c: "NA" for c in STAGE1_FIELDS}
    row["GSM_ID"] = gsm_id
    row["GSE_ID"] = gse_id
    return row


def _reviewer_add_issue(
    reviewer,
    gsm_id: str,
    gse_id: str,
    issue_type: str,
    field_name: str,
    severity: str,
    message: str,
    reviewer_action: str,
) -> None:
    if reviewer is None:
        return

    if hasattr(reviewer, "add_issue"):
        reviewer.add_issue(
            gsm_id=gsm_id,
            gse_id=gse_id,
            issue_type=issue_type,
            field_name=field_name,
            severity=severity,
            message=message,
            reviewer_action=reviewer_action,
        )


# -------------------------
# Role-call wrappers
# -------------------------
def _build_role_system_prompt(role_name: str, role_prompt_text: str) -> str:
    role_fields = ROLE_FIELDS[role_name]
    fields_json = json.dumps(role_fields, ensure_ascii=False)

    return (
        "You are a GEO metadata annotation assistant.\n"
        "Return STRICT JSON only. No markdown. No commentary.\n"
        "Annotate ALL expected GSM samples in the exact order provided.\n"
        "Output schema:\n"
        "{\n"
        '  "rows": [\n'
        "    {<only these fields>: ...},\n"
        "    ...\n"
        "  ]\n"
        "}\n"
        f"Allowed fields for this role only: {fields_json}\n"
        "Rules:\n"
        "- Output exactly one row per expected GSM sample.\n"
        "- Keep the exact GSM order from the input.\n"
        "- Use NA if a field is unavailable.\n"
        "- Do not add fields outside the allowed list.\n\n"
        f"{role_prompt_text}"
    )


def _call_role(
    llm: BaseLLM,
    role_name: str,
    role_prompt_text: str,
    gse_id: str,
    gse_info: str,
    gsm_info: str,
    expected_gsm_ids: List[str],
) -> Dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": _build_role_system_prompt(role_name, role_prompt_text),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "GSE_ID": gse_id,
                    "expected_gsm_ids": expected_gsm_ids,
                    "expected_gsm_count": len(expected_gsm_ids),
                    "GSE_Info": gse_info,
                    "GSM_Info": gsm_info,
                },
                ensure_ascii=False,
            ),
        },
    ]

    txt = llm.chat(messages)
    return _safe_json_loads_with_simple_repair(txt)


def _normalize_role_rows(
    role_name: str,
    role_output: Dict[str, Any],
    expected_gsm_ids: List[str],
    gse_id: str,
    reviewer=None,
) -> List[Dict[str, str]]:
    """
    Enforce:
      - exact row count
      - exact GSM order
      - exact role field set
    """
    role_fields = ROLE_FIELDS[role_name]
    rows = role_output.get("rows", [])

    out_rows: List[Dict[str, str]] = []
    by_gsm: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        gsm_id = _s(r.get("GSM_ID"))
        if gsm_id not in {"NA", ""}:
            by_gsm[gsm_id] = r

    for idx, gsm_id in enumerate(expected_gsm_ids):
        base = {f: "NA" for f in role_fields}
        base["GSM_ID"] = gsm_id
        base["GSE_ID"] = gse_id

        source = None

        # Prefer keyed recovery by GSM_ID
        if gsm_id in by_gsm:
            source = by_gsm[gsm_id]

        # Fall back to positional recovery
        elif idx < len(rows) and isinstance(rows[idx], dict):
            source = rows[idx]

        if source is not None:
            for f in role_fields:
                if f in {"GSM_ID", "GSE_ID"}:
                    continue
                base[f] = _s(source.get(f))

        # Force identity fields
        base["GSM_ID"] = gsm_id
        base["GSE_ID"] = gse_id
        out_rows.append(base)

    if len(rows) != len(expected_gsm_ids):
        _reviewer_add_issue(
            reviewer=reviewer,
            gsm_id="GSE_LEVEL",
            gse_id=gse_id,
            issue_type="stage1_role_row_mismatch",
            field_name=role_name,
            severity="medium",
            message=(
                f"Role {role_name} returned {len(rows)} rows; "
                f"expected {len(expected_gsm_ids)}. Applied row-preserving recovery."
            ),
            reviewer_action="manual_review",
        )

    return out_rows


def _merge_role_outputs(
    gse_id: str,
    expected_gsm_ids: List[str],
    role_rows_map: Dict[str, List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    merged = []

    for i, gsm_id in enumerate(expected_gsm_ids):
        row = _make_empty_row(gsm_id=gsm_id, gse_id=gse_id)

        for role_name, role_rows in role_rows_map.items():
            if i >= len(role_rows):
                continue

            rr = role_rows[i]

            for f in ROLE_FIELDS[role_name]:
                if f in {"GSM_ID", "GSE_ID"}:
                    continue
                row[f] = _s(rr.get(f))

        merged.append(row)

    return merged


# -------------------------
# Main Stage1
# -------------------------
def run_stage1_raw_annotation(
    cfg,
    df_input: pd.DataFrame,
    reviewer=None,
    save_outputs: bool = True,
) -> pd.DataFrame:
    """
    Stage1 input must contain:
      - GSE_ID
      - GSE_Info
      - GSM_Info
      - GSM_Counts

    Output:
      - row-level sample table with 28 fields
    """
    cfg.validate_env()
    cfg.ensure_dirs()

    required_cols = {"GSE_ID", "GSE_Info", "GSM_Info", "GSM_Counts"}
    missing = required_cols - set(df_input.columns)

    if missing:
        raise ValueError(f"Stage1 input missing required columns: {sorted(missing)}")

    llm = make_llm_from_config(cfg)

    role_prompt_texts = {
        "experimental_context": _load_role_prompt(cfg, "experimental_context"),
        "biological_context": _load_role_prompt(cfg, "biological_context"),
        "perturbation": _load_role_prompt(cfg, "perturbation"),
        "sample_metadata": _load_role_prompt(cfg, "sample_metadata"),
    }

    all_rows: List[Dict[str, str]] = []
    chunk_logs: List[Dict[str, Any]] = []

    for ridx, row in df_input.iterrows():
        gse_id = _s(row["GSE_ID"])
        gse_info = str(row["GSE_Info"])
        gsm_info = str(row["GSM_Info"])
        expected_count = int(row["GSM_Counts"]) if _s(row["GSM_Counts"]) != "NA" else None

        expected_gsm_ids = _extract_expected_gsm_ids(gsm_info)

        if (
            expected_count is not None
            and expected_count > 0
            and expected_gsm_ids
            and len(expected_gsm_ids) != expected_count
        ):
            _reviewer_add_issue(
                reviewer=reviewer,
                gsm_id="GSE_LEVEL",
                gse_id=gse_id,
                issue_type="stage1_input_count_mismatch",
                field_name="GSM_Counts",
                severity="medium",
                message=(
                    f"Input GSM_Counts={expected_count} but extracted "
                    f"{len(expected_gsm_ids)} GSM IDs from chunk text."
                ),
                reviewer_action="manual_review",
            )

        if not expected_gsm_ids:
            _reviewer_add_issue(
                reviewer=reviewer,
                gsm_id="GSE_LEVEL",
                gse_id=gse_id,
                issue_type="stage1_no_gsm_ids_found",
                field_name="GSM_Info",
                severity="high",
                message="No GSM IDs could be extracted from GSM_Info.",
                reviewer_action="manual_review",
            )
            continue

        role_rows_map: Dict[str, List[Dict[str, str]]] = {}
        role_status = {}

        for role_name, prompt_text in role_prompt_texts.items():
            try:
                raw_out = _call_role(
                    llm=llm,
                    role_name=role_name,
                    role_prompt_text=prompt_text,
                    gse_id=gse_id,
                    gse_info=gse_info,
                    gsm_info=gsm_info,
                    expected_gsm_ids=expected_gsm_ids,
                )

                role_rows = _normalize_role_rows(
                    role_name=role_name,
                    role_output=raw_out,
                    expected_gsm_ids=expected_gsm_ids,
                    gse_id=gse_id,
                    reviewer=reviewer,
                )

                role_rows_map[role_name] = role_rows
                role_status[role_name] = "ok"

            except Exception as e:
                print(f"[Stage1 ERROR] GSE={gse_id} role={role_name}: {repr(e)}")

                # Hard fallback: create NA rows for that role only
                role_rows_map[role_name] = [
                    {
                        f: (
                            "NA"
                            if f not in {"GSM_ID", "GSE_ID"}
                            else (gsm_id if f == "GSM_ID" else gse_id)
                        )
                        for f in ROLE_FIELDS[role_name]
                    }
                    for gsm_id in expected_gsm_ids
                ]

                role_status[role_name] = f"failed: {repr(e)}"

                _reviewer_add_issue(
                    reviewer=reviewer,
                    gsm_id="GSE_LEVEL",
                    gse_id=gse_id,
                    issue_type="stage1_role_failure",
                    field_name=role_name,
                    severity="high",
                    message=(
                        f"Role {role_name} failed; emitted NA fallback rows. "
                        f"Error: {repr(e)}"
                    ),
                    reviewer_action="manual_review",
                )

        if role_status and all(str(v).startswith("failed:") for v in role_status.values()):
            raise RuntimeError(
                f"All Stage1 role calls failed for GSE={gse_id}. "
                f"See role_status for details: {role_status}"
            )

        merged_rows = _merge_role_outputs(
            gse_id=gse_id,
            expected_gsm_ids=expected_gsm_ids,
            role_rows_map=role_rows_map,
        )

        # Final schema fill
        normalized_merged = []

        for m in merged_rows:
            row_out = {f: _s(m.get(f)) for f in STAGE1_FIELDS}
            normalized_merged.append(row_out)

        all_rows.extend(normalized_merged)

        chunk_logs.append(
            {
                "input_row_index": ridx,
                "GSE_ID": gse_id,
                "expected_gsm_count": len(expected_gsm_ids),
                "emitted_gsm_count": len(normalized_merged),
                "role_status": json.dumps(role_status, ensure_ascii=False),
            }
        )

    df_out = pd.DataFrame(all_rows)

    # Stable column order
    for c in STAGE1_FIELDS:
        if c not in df_out.columns:
            df_out[c] = "NA"

    df_out = df_out[STAGE1_FIELDS].copy()

    # Final reviewer check: duplicate or missing GSM IDs
    if "GSM_ID" in df_out.columns:
        dup_mask = df_out["GSM_ID"].astype(str).duplicated(keep=False)

        if dup_mask.any():
            dup_ids = sorted(df_out.loc[dup_mask, "GSM_ID"].astype(str).unique().tolist())[:20]

            _reviewer_add_issue(
                reviewer=reviewer,
                gsm_id="RUN_LEVEL",
                gse_id="RUN_LEVEL",
                issue_type="stage1_duplicate_gsm_ids",
                field_name="GSM_ID",
                severity="high",
                message=f"Duplicate GSM_IDs detected in Stage1 output. Examples: {dup_ids}",
                reviewer_action="manual_review",
            )

    if save_outputs:
        outputs_dir = Path(cfg.outputs_dir)
        ledger_dir = Path(cfg.ledger_dir)

        outputs_dir.mkdir(parents=True, exist_ok=True)
        ledger_dir.mkdir(parents=True, exist_ok=True)

        # Clean names
        out_xlsx = outputs_dir / f"{cfg.run_version}_stage1_raw.xlsx"
        out_jsonl = outputs_dir / f"{cfg.run_version}_stage1_rows.jsonl"

        df_out.to_excel(out_xlsx, index=False)

        with out_jsonl.open("w", encoding="utf-8") as f:
            for _, r in df_out.iterrows():
                f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

        # Compatibility names for the current trial phase
        chunk_log_df = pd.DataFrame(chunk_logs)
        chunk_log_fp = ledger_dir / f"{cfg.run_version}_stage1_chunk_ledger.csv"
        chunk_log_df.to_csv(chunk_log_fp, index=False)

        summary = {
            "run_version": cfg.run_version,
            "stage1_rows": int(df_out.shape[0]),
            "stage1_unique_gsm": (
                int(df_out["GSM_ID"].astype(str).nunique()) if not df_out.empty else 0
            ),
            "stage1_dup_gsm": (
                int(df_out["GSM_ID"].astype(str).duplicated().sum()) if not df_out.empty else 0
            ),
            "output_xlsx": str(out_xlsx),
            "output_jsonl": str(out_jsonl),
            "chunk_ledger_csv": str(chunk_log_fp),
        }

        summary_fp = ledger_dir / f"{cfg.run_version}_stage1_summary.json"
        summary_fp.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print("[SAVED] Stage1 raw Excel:", out_xlsx)
        print("[SAVED] Stage1 rows JSONL:", out_jsonl)
        print("[SAVED] Stage1 chunk ledger:", chunk_log_fp)
        print("[SAVED] Stage1 summary:", summary_fp)
        print("Stage1 DONE rows:", df_out.shape)

    return df_out


# Backward-compatible alias for current downstream imports
def run_stage1_raw_annotation_v2(
    cfg,
    df_input: pd.DataFrame,
    reviewer=None,
    save_outputs: bool = True,
) -> pd.DataFrame:
    return run_stage1_raw_annotation(
        cfg=cfg,
        df_input=df_input,
        reviewer=reviewer,
        save_outputs=save_outputs,
    )