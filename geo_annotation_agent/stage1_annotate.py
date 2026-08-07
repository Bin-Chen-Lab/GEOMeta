from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .llm_client import BaseLLM, make_llm_from_config
from .excel_safe import reconstruct_long_text_columns
from .token_budget import (
    TokenBudget,
    check_messages_token_budget,
    estimate_messages_tokens,
    pack_gsm_blocks_by_token_budget,
)


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

def _format_seconds(seconds: float) -> str:
    seconds = max(float(seconds), 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)

    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def _stage1_print_intro(df_input: pd.DataFrame, cfg) -> None:
    n_chunks = int(df_input.shape[0])
    n_gse = int(df_input["GSE_ID"].astype(str).nunique()) if "GSE_ID" in df_input.columns else 0

    gsm_counts = pd.to_numeric(
        df_input["GSM_Counts"] if "GSM_Counts" in df_input.columns else pd.Series([], dtype=float),
        errors="coerce",
    )
    n_gsm_expected = int(gsm_counts.fillna(0).sum()) if len(gsm_counts) else 0

    print("[Stage1] Starting LLM-guided GEO metadata annotation.", flush=True)
    print(
        f"[Stage1] Input summary: {n_gse:,} GSE records, "
        f"{n_chunks:,} annotation chunks, expected GSM rows={n_gsm_expected:,}.",
        flush=True,
    )
    print(
        "[Stage1] Each chunk sends GSE/GSM metadata context to four task-specific "
        "annotation agents: experimental context, biological context, perturbation, "
        "and sample metadata.",
        flush=True,
    )
    print(
        "[Stage1] The agent outputs are merged into the canonical 27-field "
        "GEOMeta sample-level schema.",
        flush=True,
    )
    print(
        "[Stage1] Progress shows completed chunks, percent complete, elapsed time, "
        "average time per chunk, ETA, and completed GSM rows.",
        flush=True,
    )
    print(
        "[Stage1] Main outputs will be saved under artifacts/outputs/ and artifacts/ledgers/.",
        flush=True,
    )


def _stage1_print_progress(
    *,
    done_chunks: int,
    total_chunks: int,
    completed_gsm_rows: int,
    start_time: float,
    current_gse_id: str,
    current_chunk_id: str,
) -> None:
    if not should_print_progress(done_chunks, total_chunks):
        return

    elapsed = time.perf_counter() - start_time
    pct = (done_chunks / total_chunks * 100.0) if total_chunks else 100.0
    avg = elapsed / done_chunks if done_chunks else 0.0
    eta = avg * max(total_chunks - done_chunks, 0)

    print(
        "[Stage1 progress] "
        f"chunks={done_chunks:,}/{total_chunks:,} ({pct:.1f}%); "
        f"completed_GSM_rows={completed_gsm_rows:,}; "
        f"current_GSE={current_gse_id}; "
        f"current_chunk={current_chunk_id}; "
        f"elapsed={_format_seconds(elapsed)}; "
        f"avg={avg:.1f}s/chunk; "
        f"ETA={_format_seconds(eta)}",
        flush=True,
    )

def should_print_progress(done: int, total: int) -> bool:
    """
    Throttle progress logging based on executable units.
    For Stage 1, the unit is a metadata chunk.
    """
    try:
        done = int(done)
        total = int(total)
    except Exception:
        return True

    if total <= 0 or done <= 0:
        return False

    if done == 1 or done == total:
        return True

    if total <= 20:
        return True

    if total <= 100:
        return done % 5 == 0

    if total <= 500:
        return done % 10 == 0

    return done % 50 == 0


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


def _make_token_budget(cfg) -> TokenBudget:
    return TokenBudget.from_config(cfg)


def _build_role_messages(
    role_name: str,
    role_prompt_text: str,
    gse_id: str,
    gse_info: str,
    gsm_info: str,
    expected_gsm_ids: List[str],
) -> List[Dict[str, str]]:
    return [
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


def _estimate_max_role_input_tokens(
    *,
    role_prompt_texts: Dict[str, str],
    budget: TokenBudget,
    gse_id: str,
    gse_info: str,
    gsm_info: str,
    expected_gsm_ids: List[str],
) -> int:
    vals = []
    for role_name, prompt_text in role_prompt_texts.items():
        messages = _build_role_messages(
            role_name=role_name,
            role_prompt_text=prompt_text,
            gse_id=gse_id,
            gse_info=gse_info,
            gsm_info=gsm_info,
            expected_gsm_ids=expected_gsm_ids,
        )
        vals.append(estimate_messages_tokens(messages, budget.encoding_name))
    return max(vals) if vals else 0


def _expand_stage1_input_for_token_budget(
    *,
    df_input: pd.DataFrame,
    role_prompt_texts: Dict[str, str],
    cfg,
    reviewer=None,
) -> tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Split Stage1 input rows into token-safe chunks before any LLM call.

    Splits only between complete GSM blocks. The GSE_ID stays unchanged, so QA1/QA2/QA3
    still audit all GSM annotations for the same GSE together after Stage1.
    """
    budget = _make_token_budget(cfg)
    auto_split = bool(getattr(cfg, "stage1_auto_split_over_token_limit", True))

    expanded_rows: List[Dict[str, Any]] = []
    token_logs: List[Dict[str, Any]] = []

    for ridx, row in df_input.iterrows():
        row_dict = row.to_dict()
        gse_id = _s(row_dict.get("GSE_ID"))
        gse_info = str(row_dict.get("GSE_Info", ""))
        gsm_info = str(row_dict.get("GSM_Info", ""))
        expected_ids = _extract_expected_gsm_ids(gsm_info)
        original_chunk_id = _s(row_dict.get("Chunk_ID", f"{gse_id}_inputrow_{ridx}"))

        def counter(candidate_gsm_info: str) -> int:
            candidate_ids = _extract_expected_gsm_ids(candidate_gsm_info)
            return _estimate_max_role_input_tokens(
                role_prompt_texts=role_prompt_texts,
                budget=budget,
                gse_id=gse_id,
                gse_info=gse_info,
                gsm_info=candidate_gsm_info,
                expected_gsm_ids=candidate_ids,
            )

        max_tokens = counter(gsm_info)
        needs_split = max_tokens > budget.safe_input_limit

        if (not needs_split) or (not auto_split):
            row_dict["Original_Chunk_ID"] = original_chunk_id
            row_dict["Token_Split_Index"] = 1
            row_dict["Token_Split_Count"] = 1
            row_dict["Stage1_Max_Estimated_Input_Tokens"] = int(max_tokens)
            row_dict["Stage1_Token_Split_Applied"] = False
            expanded_rows.append(row_dict)
            token_logs.append(
                {
                    "GSE_ID": gse_id,
                    "Original_Chunk_ID": original_chunk_id,
                    "Stage1_Chunk_ID": row_dict.get("Chunk_ID", original_chunk_id),
                    "Token_Split_Index": 1,
                    "Token_Split_Count": 1,
                    "GSM_Counts": len(expected_ids),
                    "Estimated_Max_Input_Tokens": int(max_tokens),
                    "Warning_Input_Token_Limit": budget.warning_input_limit,
                    "Safe_Input_Token_Limit": budget.safe_input_limit,
                    "Model_Input_Token_Limit": budget.model_input_limit,
                    "Within_Safe_Limit": bool(max_tokens <= budget.safe_input_limit),
                    "Within_Model_Limit": bool(max_tokens <= budget.model_input_limit),
                    "Action": "no_split" if not needs_split else "over_safe_limit_but_auto_split_disabled",
                }
            )
            if max_tokens > budget.model_input_limit:
                _reviewer_add_issue(
                    reviewer=reviewer,
                    gsm_id="GSE_LEVEL",
                    gse_id=gse_id,
                    issue_type="stage1_input_token_limit_exceeded",
                    field_name="GSM_Info",
                    severity="high",
                    message=(
                        f"Stage1 input chunk exceeds model input token limit: "
                        f"estimated {max_tokens:,} > {budget.model_input_limit:,}."
                    ),
                    reviewer_action="manual_review",
                )
            continue

        packed = pack_gsm_blocks_by_token_budget(
            gsm_info=gsm_info,
            budget=budget,
            token_counter_for_candidate=counter,
        )

        if not packed:
            expanded_rows.append(row_dict)
            continue

        split_count = len(packed)
        for si, part in enumerate(packed, start=1):
            part_text = str(part.get("GSM_Info", ""))
            part_ids = _extract_expected_gsm_ids(part_text)
            part_tokens = int(part.get("Estimated_Max_Input_Tokens", counter(part_text)))
            new_row = dict(row_dict)
            new_row["GSM_Info"] = part_text
            new_row["GSM_Counts"] = len(part_ids)
            new_row["GSM_ID_List"] = " | ".join(part_ids)
            new_row["Original_Chunk_ID"] = original_chunk_id
            new_row["Token_Split_Index"] = si
            new_row["Token_Split_Count"] = split_count
            new_row["Stage1_Max_Estimated_Input_Tokens"] = part_tokens
            new_row["Stage1_Token_Split_Applied"] = True
            new_row["Chunk_ID"] = f"{original_chunk_id}_toksplit_{si:03d}"
            expanded_rows.append(new_row)

            token_logs.append(
                {
                    "GSE_ID": gse_id,
                    "Original_Chunk_ID": original_chunk_id,
                    "Stage1_Chunk_ID": new_row["Chunk_ID"],
                    "Token_Split_Index": si,
                    "Token_Split_Count": split_count,
                    "GSM_Counts": len(part_ids),
                    "Estimated_Max_Input_Tokens": part_tokens,
                    "Warning_Input_Token_Limit": budget.warning_input_limit,
                    "Safe_Input_Token_Limit": budget.safe_input_limit,
                    "Model_Input_Token_Limit": budget.model_input_limit,
                    "Within_Safe_Limit": bool(part_tokens <= budget.safe_input_limit),
                    "Within_Model_Limit": bool(part_tokens <= budget.model_input_limit),
                    "Action": "auto_split_between_gsm_blocks",
                    "Single_GSM_Block_Over_Safe_Limit": bool(part.get("Single_GSM_Block_Over_Safe_Limit", False)),
                }
            )

    return pd.DataFrame(expanded_rows), token_logs


def _call_role(
    llm: BaseLLM,
    cfg,
    role_name: str,
    role_prompt_text: str,
    gse_id: str,
    gse_info: str,
    gsm_info: str,
    expected_gsm_ids: List[str],
    chunk_id: str,
    token_logs: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    messages = _build_role_messages(
        role_name=role_name,
        role_prompt_text=role_prompt_text,
        gse_id=gse_id,
        gse_info=gse_info,
        gsm_info=gsm_info,
        expected_gsm_ids=expected_gsm_ids,
    )

    budget = _make_token_budget(cfg)
    budget_row = check_messages_token_budget(
        messages,
        budget=budget,
        context_label=f"Stage1 role={role_name} GSE={gse_id} chunk={chunk_id}",
        action=str(getattr(cfg, "llm_token_budget_action", "raise")),
    )
    if token_logs is not None:
        token_logs.append(
            {
                "GSE_ID": gse_id,
                "Chunk_ID": chunk_id,
                "Role": role_name,
                "GSM_Counts": len(expected_gsm_ids),
                **budget_row,
            }
        )

    txt = llm.chat(messages)
    return _safe_json_loads_with_simple_repair(txt)

def _stage1_role_workers_from_env(default: int = 1) -> int:
    """
    Number of parallel Stage 1 role calls per chunk.

    STAGE1_ROLE_WORKERS=1 preserves the original sequential behavior.
    STAGE1_ROLE_WORKERS=2 or 4 runs independent role annotators concurrently.
    """
    raw = os.environ.get("STAGE1_ROLE_WORKERS", str(default)).strip()
    try:
        n = int(raw)
    except Exception:
        n = int(default)

    # Stage 1 currently has four role annotators.
    return max(1, min(n, 4))

def _stage1_role_start_stagger_from_env(default: float = 0.0) -> float:
    """
    Optional small delay to stagger parallel Stage 1 role calls.

    This helps avoid sending all role requests at exactly the same time when
    STAGE1_ROLE_WORKERS > 1. It does not change prompts, schema, or annotation logic.
    """
    raw = os.environ.get("STAGE1_ROLE_START_STAGGER_SECONDS", str(default)).strip()
    try:
        value = float(raw)
    except Exception:
        value = float(default)

    return max(0.0, value)

def _stage1_role_max_attempts_from_env(default: int = 3) -> int:
    """
    Maximum attempts for each Stage 1 role call.

    This is a role-level retry. It retries malformed JSON, transient API
    failures, and other role-call exceptions before falling back to NA rows.
    Keep the default conservative: 3 total attempts.
    """
    raw = os.environ.get("STAGE1_ROLE_MAX_ATTEMPTS", str(default)).strip()
    try:
        n = int(raw)
    except Exception:
        n = int(default)

    return max(1, min(n, 5))


def _stage1_role_retry_sleep_seconds_from_env(default: float = 5.0) -> float:
    """
    Base sleep time between Stage 1 role retries.

    The actual sleep uses a small linear backoff:
    retry_sleep_seconds * attempt_number.
    """
    raw = os.environ.get("STAGE1_ROLE_RETRY_SLEEP_SECONDS", str(default)).strip()
    try:
        value = float(raw)
    except Exception:
        value = float(default)

    return max(0.0, value)


def _call_role_with_retries(
    *,
    llm: BaseLLM,
    cfg,
    role_name: str,
    role_prompt_text: str,
    gse_id: str,
    gse_info: str,
    gsm_info: str,
    expected_gsm_ids: List[str],
    chunk_id: str,
    token_logs: List[Dict[str, Any]] | None = None,
    max_attempts: int | None = None,
    retry_sleep_seconds: float | None = None,
) -> Dict[str, Any]:
    """
    Call one Stage 1 role with bounded retries.

    This prevents one malformed JSON response from immediately becoming NA
    fallback rows. If all attempts fail, the caller still handles the failure
    through the existing stage1_role_failure reviewer path.
    """
    if max_attempts is None:
        max_attempts = _stage1_role_max_attempts_from_env(default=3)
    if retry_sleep_seconds is None:
        retry_sleep_seconds = _stage1_role_retry_sleep_seconds_from_env(default=5.0)

    max_attempts = max(1, int(max_attempts))
    retry_sleep_seconds = max(0.0, float(retry_sleep_seconds))

    errors: List[str] = []

    for attempt in range(1, max_attempts + 1):
        attempt_token_logs: List[Dict[str, Any]] = []

        try:
            out = _call_role(
                llm=llm,
                cfg=cfg,
                role_name=role_name,
                role_prompt_text=role_prompt_text,
                gse_id=gse_id,
                gse_info=gse_info,
                gsm_info=gsm_info,
                expected_gsm_ids=expected_gsm_ids,
                chunk_id=chunk_id,
                token_logs=attempt_token_logs,
            )

            if token_logs is not None:
                for row in attempt_token_logs:
                    row["Stage1_Role_Attempt"] = attempt
                    row["Stage1_Role_Attempt_Status"] = "success"
                token_logs.extend(attempt_token_logs)

            if attempt > 1:
                print(
                    f"[Stage1 RETRY OK] GSE={gse_id} chunk={chunk_id} "
                    f"role={role_name} succeeded on attempt {attempt}/{max_attempts}.",
                    flush=True,
                )

            return out

        except Exception as e:
            err = repr(e)
            errors.append(err)

            if token_logs is not None:
                for row in attempt_token_logs:
                    row["Stage1_Role_Attempt"] = attempt
                    row["Stage1_Role_Attempt_Status"] = "failed"
                    row["Stage1_Role_Attempt_Error"] = err
                token_logs.extend(attempt_token_logs)

            if attempt >= max_attempts:
                raise RuntimeError(
                    f"Stage1 role call failed after {max_attempts} attempt(s): "
                    f"GSE={gse_id}; chunk={chunk_id}; role={role_name}; "
                    f"last_error={err}; all_errors={errors}"
                ) from e

            sleep_seconds = retry_sleep_seconds * attempt
            print(
                f"[Stage1 RETRY] GSE={gse_id} chunk={chunk_id} role={role_name} "
                f"failed attempt {attempt}/{max_attempts}: {err}. "
                f"Retrying in {sleep_seconds:.1f}s.",
                flush=True,
            )

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    raise RuntimeError(
        f"Stage1 role call failed unexpectedly without returning or raising: "
        f"GSE={gse_id}; chunk={chunk_id}; role={role_name}; errors={errors}"
    )

def _make_role_failure_rows(
    role_name: str,
    expected_gsm_ids: List[str],
    gse_id: str,
) -> List[Dict[str, str]]:
    """
    Hard fallback for one failed role.
    Preserves GSM rows and fills only that role's assigned fields with NA.
    """
    return [
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


def _call_role_worker(
    *,
    cfg,
    role_name: str,
    role_prompt_text: str,
    gse_id: str,
    gse_info: str,
    gsm_info: str,
    expected_gsm_ids: List[str],
    chunk_id: str,
    role_index: int = 0,
    start_stagger_seconds: float = 0.0,
    max_attempts: int | None = None,
    retry_sleep_seconds: float | None = None,
) -> tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Worker wrapper for one role call.

    A separate LLM client is created inside each worker to avoid sharing one
    OpenAI-compatible client across threads. The worker uses the same bounded
    retry policy as sequential Stage 1.
    """
    if start_stagger_seconds > 0 and role_index > 0:
        time.sleep(float(start_stagger_seconds) * int(role_index))

    local_llm = make_llm_from_config(cfg)
    local_token_logs: List[Dict[str, Any]] = []

    raw_out = _call_role_with_retries(
        llm=local_llm,
        cfg=cfg,
        role_name=role_name,
        role_prompt_text=role_prompt_text,
        gse_id=gse_id,
        gse_info=gse_info,
        gsm_info=gsm_info,
        expected_gsm_ids=expected_gsm_ids,
        chunk_id=chunk_id,
        token_logs=local_token_logs,
        max_attempts=max_attempts,
        retry_sleep_seconds=retry_sleep_seconds,
    )

    return role_name, raw_out, local_token_logs

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
      - row-level sample table with 27 fields
    """
    cfg.validate_env()
    cfg.ensure_dirs()

    # If Stage1 is started from the Excel review copy, long metadata may be stored
    # across GSE_Info_Part_* / GSM_Info_Part_* columns. Reconstruct full text before
    # prompt construction. If no part columns exist, this is a no-op.
    df_input = reconstruct_long_text_columns(df_input, long_text_columns=("GSE_Info", "GSM_Info"))

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

    df_input, token_prep_logs = _expand_stage1_input_for_token_budget(
        df_input=df_input,
        role_prompt_texts=role_prompt_texts,
        cfg=cfg,
        reviewer=reviewer,
    )

    _stage1_print_intro(df_input, cfg)

    stage1_progress_start = time.perf_counter()
    stage1_completed_gsm_rows = 0
    total_chunks = int(df_input.shape[0])

    all_rows: List[Dict[str, str]] = []

    chunk_logs: List[Dict[str, Any]] = []
    token_call_logs: List[Dict[str, Any]] = []

    stage1_role_workers = _stage1_role_workers_from_env(default=1)
    stage1_role_start_stagger_seconds = _stage1_role_start_stagger_from_env(default=0.0)
    stage1_role_max_attempts = _stage1_role_max_attempts_from_env(default=3)
    stage1_role_retry_sleep_seconds = _stage1_role_retry_sleep_seconds_from_env(default=5.0)

    print(
        f"[Stage1] Annotation-agent retry policy: "
        f"STAGE1_ROLE_MAX_ATTEMPTS={stage1_role_max_attempts}; "
        f"STAGE1_ROLE_RETRY_SLEEP_SECONDS={stage1_role_retry_sleep_seconds}.",
        flush=True,
    )

    if stage1_role_workers > 1:
        print(
            f"[Stage1] Parallel annotation-agent execution enabled: "
            f"STAGE1_ROLE_WORKERS={stage1_role_workers}; "
            f"STAGE1_ROLE_START_STAGGER_SECONDS={stage1_role_start_stagger_seconds}. "
            "Each metadata chunk still preserves GSM order and final schema merging.",
            flush=True,
        )

    for chunk_n, (ridx, row) in enumerate(df_input.iterrows(), start=1):
        gse_id = _s(row["GSE_ID"])
        gse_info = str(row["GSE_Info"])
        gsm_info = str(row["GSM_Info"])
        expected_count = int(row["GSM_Counts"]) if _s(row["GSM_Counts"]) != "NA" else None
        chunk_id = _s(row.get("Chunk_ID", f"{gse_id}_inputrow_{ridx}"))

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

            _stage1_print_progress(
                done_chunks=chunk_n,
                total_chunks=total_chunks,
                completed_gsm_rows=stage1_completed_gsm_rows,
                start_time=stage1_progress_start,
                current_gse_id=gse_id,
                current_chunk_id=chunk_id,
            )

            continue

        role_rows_map: Dict[str, List[Dict[str, str]]] = {}
        role_status = {}

        def handle_role_failure(role_name: str, err: Exception) -> None:
            print(f"[Stage1 ERROR] GSE={gse_id} role={role_name}: {repr(err)}", flush=True)

            role_rows_map[role_name] = _make_role_failure_rows(
                role_name=role_name,
                expected_gsm_ids=expected_gsm_ids,
                gse_id=gse_id,
            )

            role_status[role_name] = f"failed: {repr(err)}"

            _reviewer_add_issue(
                reviewer=reviewer,
                gsm_id="GSE_LEVEL",
                gse_id=gse_id,
                issue_type="stage1_role_failure",
                field_name=role_name,
                severity="high",
                message=(
                    f"Role {role_name} failed; emitted NA fallback rows. "
                    f"Error: {repr(err)}"
                ),
                reviewer_action="manual_review",
            )

        if stage1_role_workers <= 1:
            # Original sequential behavior.
            for role_name, prompt_text in role_prompt_texts.items():
                try:
                    raw_out = _call_role_with_retries(
                        llm=llm,
                        cfg=cfg,
                        role_name=role_name,
                        role_prompt_text=prompt_text,
                        gse_id=gse_id,
                        gse_info=gse_info,
                        gsm_info=gsm_info,
                        expected_gsm_ids=expected_gsm_ids,
                        chunk_id=chunk_id,
                        token_logs=token_call_logs,
                        max_attempts=stage1_role_max_attempts,
                        retry_sleep_seconds=stage1_role_retry_sleep_seconds,
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
                    handle_role_failure(role_name, e)

        else:
            # Parallel role execution within the same chunk.
            max_workers = min(stage1_role_workers, len(role_prompt_texts))

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_role = {
                    executor.submit(
                        _call_role_worker,
                        cfg=cfg,
                        role_name=role_name,
                        role_prompt_text=prompt_text,
                        gse_id=gse_id,
                        gse_info=gse_info,
                        gsm_info=gsm_info,
                        expected_gsm_ids=expected_gsm_ids,
                        chunk_id=chunk_id,
                        role_index=role_index,
                        start_stagger_seconds=stage1_role_start_stagger_seconds,
                        max_attempts=stage1_role_max_attempts,
                        retry_sleep_seconds=stage1_role_retry_sleep_seconds,
                    ): role_name
                    for role_index, (role_name, prompt_text) in enumerate(role_prompt_texts.items())
                }

                for future in as_completed(future_to_role):
                    role_name = future_to_role[future]

                    try:
                        returned_role_name, raw_out, local_token_logs = future.result()
                        token_call_logs.extend(local_token_logs)

                        role_rows = _normalize_role_rows(
                            role_name=returned_role_name,
                            role_output=raw_out,
                            expected_gsm_ids=expected_gsm_ids,
                            gse_id=gse_id,
                            reviewer=reviewer,
                        )

                        role_rows_map[returned_role_name] = role_rows
                        role_status[returned_role_name] = "ok"

                    except Exception as e:
                        handle_role_failure(role_name, e)

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
                "Chunk_ID": chunk_id,
                "Original_Chunk_ID": _s(row.get("Original_Chunk_ID", chunk_id)),
                "Token_Split_Index": _s(row.get("Token_Split_Index", "")),
                "Token_Split_Count": _s(row.get("Token_Split_Count", "")),
                "Stage1_Max_Estimated_Input_Tokens": _s(row.get("Stage1_Max_Estimated_Input_Tokens", "")),
                "Stage1_Token_Split_Applied": _s(row.get("Stage1_Token_Split_Applied", "")),
                "expected_gsm_count": len(expected_gsm_ids),
                "emitted_gsm_count": len(normalized_merged),
                "role_status": json.dumps(role_status, ensure_ascii=False),
            }
        )

        stage1_completed_gsm_rows += len(normalized_merged)

        _stage1_print_progress(
            done_chunks=chunk_n,
            total_chunks=total_chunks,
            completed_gsm_rows=stage1_completed_gsm_rows,
            start_time=stage1_progress_start,
            current_gse_id=gse_id,
            current_chunk_id=chunk_id,
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

        token_report_df = pd.DataFrame(token_prep_logs + token_call_logs)
        token_report_fp = ledger_dir / f"{cfg.run_version}_stage1_token_budget_report.xlsx"
        if bool(getattr(cfg, "stage1_token_report_enabled", True)):
            token_report_df.to_excel(token_report_fp, index=False)

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
            "token_budget_report_xlsx": str(token_report_fp),
        }

        summary_fp = ledger_dir / f"{cfg.run_version}_stage1_summary.json"
        summary_fp.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print("[SAVED] Stage1 raw Excel:", out_xlsx)
        print("[SAVED] Stage1 rows JSONL:", out_jsonl)
        print("[SAVED] Stage1 chunk ledger:", chunk_log_fp)
        if bool(getattr(cfg, "stage1_token_report_enabled", True)):
            print("[SAVED] Stage1 token budget report:", token_report_fp)
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