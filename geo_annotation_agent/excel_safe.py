from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


EXCEL_CELL_CHAR_LIMIT = 32767
DEFAULT_EXCEL_TEXT_PART_CHAR_LIMIT = 32000


LONG_TEXT_COLUMNS = ("GSE_Info", "GSM_Info")


def _is_missing_text(x: Any) -> bool:
    if x is None:
        return True
    try:
        if isinstance(x, float) and x != x:
            return True
    except Exception:
        pass
    return str(x).strip().lower() in {"", "nan", "none", "na", "unknown"}


def _as_text(x: Any) -> str:
    return "" if _is_missing_text(x) else str(x)


def _part_prefix(col: str) -> str:
    return f"{col}_Part_"


def _part_columns(columns: Iterable[str], col: str) -> list[str]:
    prefix = _part_prefix(col)
    return sorted([c for c in columns if str(c).startswith(prefix)])


def split_gsm_info_by_complete_gsm_blocks(text: Any, limit: int = DEFAULT_EXCEL_TEXT_PART_CHAR_LIMIT) -> list[str]:
    """
    Split a Stage0 GSM_Info chunk into Excel-safe parts.

    Preference order:
      1. Split between complete GSM blocks, where each block starts with `GSM ID: GSM...`.
      2. If one individual GSM block exceeds the limit, split that block by character length as a last resort.

    The returned parts are intended for Excel review columns only. The full GSM_Info should remain
    unchanged in the authoritative dataframe/parquet/jsonl artifact.
    """
    text = _as_text(text)
    if not text:
        return []

    limit = max(1000, int(limit))
    if len(text) <= limit:
        return [text]

    blocks = re.split(r"(?=GSM ID:\s*GSM\d+)", text)
    blocks = [b.strip() for b in blocks if b and b.strip()]

    # If GSM boundaries are not found, fall back to fixed-size chunks.
    if not blocks:
        return [text[i : i + limit] for i in range(0, len(text), limit)]

    parts: list[str] = []
    current = ""

    for block in blocks:
        if len(block) > limit:
            if current:
                parts.append(current)
                current = ""
            # Last resort: one GSM block itself is too large for one Excel cell.
            for i in range(0, len(block), limit):
                parts.append(block[i : i + limit])
            continue

        candidate = block if not current else current + "\n\n" + block
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = block

    if current:
        parts.append(current)

    return parts


def split_long_text_for_excel(text: Any, col: str, limit: int = DEFAULT_EXCEL_TEXT_PART_CHAR_LIMIT) -> list[str]:
    """Split long text into Excel-safe parts using GSM-block-aware logic for GSM_Info."""
    text = _as_text(text)
    if not text:
        return []
    limit = max(1000, int(limit))

    if col == "GSM_Info":
        return split_gsm_info_by_complete_gsm_blocks(text, limit=limit)

    return [text[i : i + limit] for i in range(0, len(text), limit)] if len(text) > limit else [text]


def reconstruct_long_text_columns(
    df: pd.DataFrame,
    long_text_columns: Iterable[str] = LONG_TEXT_COLUMNS,
) -> pd.DataFrame:
    """
    Reconstruct GSE_Info/GSM_Info from split Excel part columns when present.

    This makes standalone Stage1 runs safe when reading Stage0 Excel review files that contain
    `GSM_Info_Part_001`, `GSM_Info_Part_002`, ... instead of relying on a truncated Excel cell.
    If part columns are present, they take precedence over the preview column.
    """
    out = df.copy()

    for col in long_text_columns:
        part_cols = _part_columns(out.columns, col)
        if not part_cols:
            continue

        def combine_parts(row) -> str:
            parts: list[str] = []
            for pcol in part_cols:
                val = row.get(pcol, "")
                if not _is_missing_text(val):
                    parts.append(str(val).strip())
            if parts:
                return "\n\n".join(parts).strip()
            return _as_text(row.get(col, ""))

        out[col] = out.apply(combine_parts, axis=1)

    return out


def add_long_text_part_columns_for_excel(
    df: pd.DataFrame,
    long_text_columns: Iterable[str] = LONG_TEXT_COLUMNS,
    part_limit: int = DEFAULT_EXCEL_TEXT_PART_CHAR_LIMIT,
    keep_preview_column: bool = True,
) -> pd.DataFrame:
    """
    Return an Excel-safe dataframe.

    For each long text column, this adds ordered part columns:
      GSE_Info_Part_001, GSE_Info_Part_002, ...
      GSM_Info_Part_001, GSM_Info_Part_002, ...

    The original column is retained as a short preview by default, never exceeding Excel's
    per-cell limit. The full original text should be written to parquet/jsonl separately.
    """
    out = df.copy()
    part_limit = min(max(1000, int(part_limit)), EXCEL_CELL_CHAR_LIMIT)

    for col in long_text_columns:
        if col not in out.columns:
            continue

        all_parts: list[list[str]] = [
            split_long_text_for_excel(v, col=col, limit=part_limit)
            for v in out[col].tolist()
        ]
        max_parts = max((len(parts) for parts in all_parts), default=0)

        for i in range(max_parts):
            pcol = f"{col}_Part_{i + 1:03d}"
            out[pcol] = [parts[i] if i < len(parts) else "" for parts in all_parts]

        out[f"{col}_Part_Count"] = [len(parts) for parts in all_parts]
        out[f"{col}_Was_Split_For_Excel"] = [len(parts) > 1 for parts in all_parts]
        out[f"{col}_Original_Chars"] = [len(_as_text(v)) for v in out[col].tolist()]

        if keep_preview_column:
            preview_limit = min(part_limit, EXCEL_CELL_CHAR_LIMIT)

            def preview(v: Any) -> str:
                text = _as_text(v)
                if len(text) <= preview_limit:
                    return text
                suffix = (
                    f"\n\n...[EXCEL PREVIEW ONLY; full text stored in {col}_Part_* "
                    f"and parquet/jsonl; original_chars={len(text)}]"
                )
                keep = max(0, preview_limit - len(suffix))
                return text[:keep] + suffix

            out[col] = out[col].map(preview)
        else:
            out = out.drop(columns=[col], errors="ignore")

    out["Excel_Output_Is_Preview"] = True
    return out


def write_excel_with_long_text_parts(
    df: pd.DataFrame,
    path: str | Path,
    long_text_columns: Iterable[str] = LONG_TEXT_COLUMNS,
    part_limit: int = DEFAULT_EXCEL_TEXT_PART_CHAR_LIMIT,
) -> Path:
    """Write an Excel-safe review copy with split long-text columns."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df_excel = add_long_text_part_columns_for_excel(
        df,
        long_text_columns=long_text_columns,
        part_limit=part_limit,
        keep_preview_column=True,
    )
    df_excel.to_excel(path, index=False)
    return path
