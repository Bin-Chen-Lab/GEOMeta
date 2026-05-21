from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd

from .llm_client import make_llm_from_config
from .json_safety import safe_json_loads_with_repair


def _s(x) -> str:
    if x is None:
        return "NA"
    try:
        if isinstance(x, float) and x != x:
            return "NA"
    except Exception:
        pass
    v = str(x).strip()
    return "NA" if v.lower() in {"nan", ""} else v


ROW_REVIEW_SYSTEM = """
You are a biomedical metadata reviewer.

Your job is NOT to re-annotate directly.
Your job is to review whether the Stage 2 annotations are well-supported by the original metadata.

Return STRICT JSON only.

Input JSON format:
{
  "GSE_ID": "...",
  "GSM_ID": "...",
  "GSE_Info": "...",
  "GSM_Info": "...",
  "stage2_annotations": {...},
  "rule_flags": [...]
}

Output JSON format:
{
  "review_status": "pass|suspicious|fail",
  "flagged_fields": ["..."],
  "review_reason": "...",
  "recommended_action": "keep|rerun_field|rerun_row|manual_review",
  "confidence": "high|medium|low"
}

Rules:
- Be conservative.
- Only flag a field if the annotation appears unsupported, contradictory, over-normalized, or inconsistent with metadata.
- If the annotations are generally acceptable, return review_status=pass.
- Do not invent new annotations.
"""

GSE_REVIEW_SYSTEM = """
You are a biomedical metadata reviewer for study-level consistency.

Your job is NOT to rewrite annotations.
Your job is to review whether the GSM-level annotations within one GSE are coherent with each other and with the study-level metadata.

Return STRICT JSON only.

Input JSON format:
{
  "GSE_ID": "...",
  "GSE_Info": "...",
  "stage2_gse_summary": {...},
  "flagged_gsms": [...]
}

Output JSON format:
{
  "gse_review_status": "pass|suspicious|fail",
  "summary": "...",
  "flagged_gsms": [
    {
      "GSM_ID": "...",
      "flagged_fields": ["..."],
      "recommended_action": "keep|rerun_field|rerun_row|manual_review"
    }
  ]
}

Rules:
- Be conservative.
- Focus on whether one or more GSMs appear inconsistent with the study design or with the rest of the GSE.
- Do not invent annotations.
"""


@dataclass
class LLMReviewConfig:
    max_row_reviews_per_run: int = 150
    max_gse_reviews_per_run: int = 50
    row_fields_focus: Optional[List[str]] = None


class ReviewerLLMV2:
    def __init__(self, cfg, debug_dir: Path, llm_review_cfg: Optional[LLMReviewConfig] = None):
        cfg.validate_env()
        self.cfg = cfg
        self.debug_dir = Path(debug_dir)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.llm_review_cfg = llm_review_cfg or LLMReviewConfig()

        self.llm = make_llm_from_config(cfg)

    def _row_payload(
        self,
        row: pd.Series,
        input_lookup: Dict[str, Dict[str, Any]],
        rule_flags: List[str],
    ) -> Dict[str, Any]:
        gsm_id = _s(row.get("GSM_ID"))
        source = input_lookup.get(gsm_id, {})

        annotations = {}
        for c in row.index:
            if c.endswith("_Post") or c in {"GSM_ID", "GSE_ID", "SampleType", "Pert_Type", "Sex_Inferred_from_Organ"}:
                annotations[c] = _s(row.get(c))

        if self.llm_review_cfg.row_fields_focus:
            filtered = {"GSM_ID": gsm_id, "GSE_ID": _s(row.get("GSE_ID"))}
            for k, v in annotations.items():
                keep = False
                for fld in self.llm_review_cfg.row_fields_focus:
                    if fld in k:
                        keep = True
                        break
                if keep or k in {"SampleType", "Pert_Type", "Sex_Inferred_from_Organ"}:
                    filtered[k] = v
            annotations = filtered

        return {
            "GSE_ID": _s(row.get("GSE_ID")),
            "GSM_ID": gsm_id,
            "GSE_Info": source.get("GSE_Info", ""),
            "GSM_Info": source.get("GSM_Info", ""),
            "stage2_annotations": annotations,
            "rule_flags": rule_flags,
        }

    def _gse_payload(
        self,
        gse_id: str,
        gse_df: pd.DataFrame,
        input_lookup_by_gse: Dict[str, str],
        flagged_rows_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        summary = {
            "sample_count": int(gse_df.shape[0]),
            "field_distributions": {},
        }

        important_fields = [
            "Seq_Type_Post", "Organism_Post", "Experimental_Setting_Post",
            "Model_Type_Post", "Disease_Post", "Organ_Region_Post",
            "Pert_Type", "Sex_Post", "SampleType"
        ]

        for fld in important_fields:
            if fld in gse_df.columns:
                vc = gse_df[fld].astype(str).fillna("NA").value_counts().to_dict()
                summary["field_distributions"][fld] = vc

        compact_rows = []
        show_cols = [
            "GSM_ID", "Disease_Post", "Organ_Region_Post", "Pert_Post",
            "Pert_Type", "Sex_Post", "SampleType", "Model_Type_Post"
        ]
        show_cols = [c for c in show_cols if c in gse_df.columns]
        for _, r in gse_df[show_cols].iterrows():
            compact_rows.append({c: _s(r.get(c)) for c in show_cols})

        summary["gsm_rows"] = compact_rows[:50]

        flagged_gsms = []
        if not flagged_rows_df.empty:
            for _, r in flagged_rows_df.iterrows():
                flagged_gsms.append({
                    "GSM_ID": _s(r.get("gsm_id")),
                    "issue_type": _s(r.get("issue_type")),
                    "field_name": _s(r.get("field_name")),
                    "message": _s(r.get("message")),
                })

        return {
            "GSE_ID": gse_id,
            "GSE_Info": input_lookup_by_gse.get(gse_id, ""),
            "stage2_gse_summary": summary,
            "flagged_gsms": flagged_gsms,
        }

    def review_rows(
        self,
        df_stage2: pd.DataFrame,
        df_input_stage1_source: pd.DataFrame,
        flagged_rows_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        GPT row review only on flagged rows.
        """
        if flagged_rows_df.empty:
            return pd.DataFrame(columns=[
                "gsm_id", "gse_id", "review_status", "flagged_fields",
                "review_reason", "recommended_action", "confidence"
            ])

        # build lookup from stage1/source input
        input_lookup: Dict[str, Dict[str, Any]] = {}
        for _, r in df_input_stage1_source.iterrows():
            gsm_id = _s(r.get("GSM_ID"))
            if gsm_id != "NA":
                input_lookup[gsm_id] = {
                    "GSE_Info": r.get("GSE_Info", "") if "GSE_Info" in r else "",
                    "GSM_Info": r.get("GSM_Info", "") if "GSM_Info" in r else "",
                }

        # prioritize high severity
        flagged_rows_df = flagged_rows_df.copy()
        severity_rank = {"high": 0, "medium": 1, "low": 2}
        if "severity" in flagged_rows_df.columns:
            flagged_rows_df["_sev_rank"] = flagged_rows_df["severity"].map(lambda x: severity_rank.get(str(x).lower(), 9))
            flagged_rows_df = flagged_rows_df.sort_values(["_sev_rank", "gse_id", "gsm_id"])

        unique_gsms = flagged_rows_df["gsm_id"].astype(str).dropna().unique().tolist()
        unique_gsms = [g for g in unique_gsms if g not in {"RUN_LEVEL", "GSE_LEVEL"}]
        unique_gsms = unique_gsms[: self.llm_review_cfg.max_row_reviews_per_run]

        out_rows = []

        for gsm_id in unique_gsms:
            row = df_stage2.loc[df_stage2["GSM_ID"].astype(str) == gsm_id]
            if row.empty:
                continue
            row = row.iloc[0]

            rule_flags = flagged_rows_df.loc[flagged_rows_df["gsm_id"].astype(str) == gsm_id, "message"].astype(str).tolist()
            payload = self._row_payload(row, input_lookup, rule_flags)

            messages = [
                {"role": "system", "content": ROW_REVIEW_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            txt = self.llm.chat(messages, temperature=0.0)
            out = safe_json_loads_with_repair(
                txt,
                debug_dir=str(self.debug_dir),
                debug_tag=f"ROW_REVIEW_{gsm_id}",
                llm_chat_fn=lambda msgs, temperature=0.0: self.llm.chat(msgs, temperature=temperature),
            )

            out_rows.append({
                "gsm_id": gsm_id,
                "gse_id": _s(row.get("GSE_ID")),
                "review_status": _s(out.get("review_status")),
                "flagged_fields": json.dumps(out.get("flagged_fields", []), ensure_ascii=False),
                "review_reason": _s(out.get("review_reason")),
                "recommended_action": _s(out.get("recommended_action")),
                "confidence": _s(out.get("confidence")),
            })

        return pd.DataFrame(out_rows)

    def review_gses(
        self,
        df_stage2: pd.DataFrame,
        df_input_stage1_source: pd.DataFrame,
        flagged_rows_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        GPT GSE review only on suspicious GSEs.
        """
        if flagged_rows_df.empty:
            return pd.DataFrame(columns=[
                "gse_id", "gse_review_status", "summary", "flagged_gsms_json"
            ])

        input_lookup_by_gse: Dict[str, str] = {}
        if "GSE_ID" in df_input_stage1_source.columns and "GSE_Info" in df_input_stage1_source.columns:
            for _, r in df_input_stage1_source.iterrows():
                gse_id = _s(r.get("GSE_ID"))
                if gse_id != "NA" and gse_id not in input_lookup_by_gse:
                    input_lookup_by_gse[gse_id] = r.get("GSE_Info", "")

        suspicious_gses = flagged_rows_df["gse_id"].astype(str).dropna().unique().tolist()
        suspicious_gses = [g for g in suspicious_gses if g not in {"RUN_LEVEL"}]
        suspicious_gses = suspicious_gses[: self.llm_review_cfg.max_gse_reviews_per_run]

        out_rows = []

        for gse_id in suspicious_gses:
            gse_df = df_stage2.loc[df_stage2["GSE_ID"].astype(str) == gse_id].copy()
            if gse_df.empty:
                continue

            gse_flagged = flagged_rows_df.loc[flagged_rows_df["gse_id"].astype(str) == gse_id].copy()
            payload = self._gse_payload(gse_id, gse_df, input_lookup_by_gse, gse_flagged)

            messages = [
                {"role": "system", "content": GSE_REVIEW_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            txt = self.llm.chat(messages, temperature=0.0)
            out = safe_json_loads_with_repair(
                txt,
                debug_dir=str(self.debug_dir),
                debug_tag=f"GSE_REVIEW_{gse_id}",
                llm_chat_fn=lambda msgs, temperature=0.0: self.llm.chat(msgs, temperature=temperature),
            )

            out_rows.append({
                "gse_id": gse_id,
                "gse_review_status": _s(out.get("gse_review_status")),
                "summary": _s(out.get("summary")),
                "flagged_gsms_json": json.dumps(out.get("flagged_gsms", []), ensure_ascii=False),
            })

        return pd.DataFrame(out_rows)