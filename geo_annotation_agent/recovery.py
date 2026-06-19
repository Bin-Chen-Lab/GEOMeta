from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


GSM_REGEX = re.compile(r"\bGSM\d+\b", flags=re.IGNORECASE)


@dataclass
class RecoveryResult:
    gsm_ids: List[str]
    status: str
    reason: str
    recovered: bool
    used_placeholders: bool


def extract_gsms_regex(gsm_info: str) -> List[str]:
    if not gsm_info:
        return []
    found = GSM_REGEX.findall(gsm_info)
    # preserve order, deduplicate
    seen = set()
    ordered = []
    for g in found:
        g = g.upper()
        if g not in seen:
            seen.add(g)
            ordered.append(g)
    return ordered


def extract_gsms_linewise(gsm_info: str) -> List[str]:
    """
    A slightly more permissive fallback parser.
    """
    if not gsm_info:
        return []

    candidates = []
    for line in gsm_info.splitlines():
        line = line.strip()
        if not line:
            continue
        found = GSM_REGEX.findall(line)
        for g in found:
            g = g.upper()
            if g not in candidates:
                candidates.append(g)
    return candidates


def call_recovery_llm(
    llm,
    gse_id: str,
    gsm_info: str,
    expected_count: int,
    debug_tag: str,
) -> List[str]:
    """
    Skeleton for LLM-based GSM recovery.
    Replace/extend with your preferred JSON-safe wrapper if needed.
    """
    system = (
        "You are recovering GSM accession IDs from GEO sample text.\n"
        "Return STRICT JSON ONLY.\n"
        "Output format: {\"gsm_ids\": [\"GSM123\", ...]}\n"
        f"Return exactly {expected_count} GSM IDs if they are recoverable.\n"
        "If not recoverable, return an empty list.\n"
        "Do not invent IDs."
    )
    user = {
        "gse_id": gse_id,
        "expected_count": expected_count,
        "gsm_info": gsm_info,
    }
    try:
        txt = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": str(user)},
            ],
            temperature=0.0,
        )
        import json
        js = json.loads(txt)
        vals = js.get("gsm_ids", [])
        vals = [str(v).upper().strip() for v in vals if str(v).strip()]
        return vals
    except Exception:
        return []


def make_placeholder_gsms(gse_id: str, input_row_index: int, expected_count: int) -> List[str]:
    return [f"RECOVERY_PLACEHOLDER_{gse_id}_{input_row_index}_{i+1}" for i in range(expected_count)]


def recover_gsm_ids(
    gse_id: str,
    gsm_info: str,
    expected_count: int,
    input_row_index: int,
    llm=None,
    enable_llm_recovery: bool = True,
    debug_tag: str = "",
) -> RecoveryResult:
    """
    Recovery cascade:
    1) regex
    2) linewise fallback
    3) optional LLM recovery
    4) placeholders
    """
    # Pass 1: regex
    vals = extract_gsms_regex(gsm_info)
    if len(vals) == expected_count:
        return RecoveryResult(
            gsm_ids=vals,
            status="ok_regex",
            reason="Recovered with regex.",
            recovered=False,
            used_placeholders=False,
        )

    # Pass 2: linewise
    vals2 = extract_gsms_linewise(gsm_info)
    if len(vals2) == expected_count:
        return RecoveryResult(
            gsm_ids=vals2,
            status="ok_linewise",
            reason="Recovered with linewise parsing.",
            recovered=True,
            used_placeholders=False,
        )

    # Pass 3: LLM recovery
    if enable_llm_recovery and llm is not None:
        vals3 = call_recovery_llm(
            llm=llm,
            gse_id=gse_id,
            gsm_info=gsm_info,
            expected_count=expected_count,
            debug_tag=debug_tag,
        )
        if len(vals3) == expected_count:
            return RecoveryResult(
                gsm_ids=vals3,
                status="ok_llm_recovery",
                reason="Recovered with LLM recovery.",
                recovered=True,
                used_placeholders=False,
            )

    # Pass 4: placeholders (row-preserving fallback)
    placeholders = make_placeholder_gsms(gse_id, input_row_index, expected_count)
    return RecoveryResult(
        gsm_ids=placeholders,
        status="placeholder_recovery",
        reason="Could not recover GSM IDs; emitted placeholder rows to preserve row count.",
        recovered=True,
        used_placeholders=True,
    )