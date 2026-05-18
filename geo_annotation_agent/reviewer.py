from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any

import json
import pandas as pd


@dataclass
class ReviewIssue:
    gsm_id: str
    gse_id: str
    issue_type: str
    field_name: str
    severity: str
    message: str
    reviewer_action: str   # accept / rerun_field / rerun_chunk / manual_review


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


class ReviewerV2:
    def __init__(self):
        self.issues: List[ReviewIssue] = []

    def add_issue(
        self,
        gsm_id: str,
        gse_id: str,
        issue_type: str,
        field_name: str,
        severity: str,
        message: str,
        reviewer_action: str,
    ) -> None:
        self.issues.append(
            ReviewIssue(
                gsm_id=gsm_id,
                gse_id=gse_id,
                issue_type=issue_type,
                field_name=field_name,
                severity=severity,
                message=message,
                reviewer_action=reviewer_action,
            )
        )

    def review_stage1(self, df: pd.DataFrame, expected_total_rows: int) -> pd.DataFrame:
        if df.shape[0] != expected_total_rows:
            self.add_issue(
                gsm_id="RUN_LEVEL",
                gse_id="RUN_LEVEL",
                issue_type="row_count_mismatch",
                field_name="ALL",
                severity="high",
                message=f"Expected {expected_total_rows} rows, got {df.shape[0]} rows.",
                reviewer_action="rerun_chunk",
            )

        for _, row in df.iterrows():
            gsm_id = _s(row.get("GSM_ID"))
            gse_id = _s(row.get("GSE_ID"))

            if gsm_id.startswith("RECOVERY_PLACEHOLDER_"):
                self.add_issue(
                    gsm_id=gsm_id,
                    gse_id=gse_id,
                    issue_type="placeholder_gsm",
                    field_name="GSM_ID",
                    severity="medium",
                    message="GSM ID could not be recovered; placeholder emitted.",
                    reviewer_action="manual_review",
                )

            if gse_id == "NA":
                self.add_issue(
                    gsm_id=gsm_id,
                    gse_id=gse_id,
                    issue_type="missing_gse",
                    field_name="GSE_ID",
                    severity="high",
                    message="Missing GSE_ID.",
                    reviewer_action="rerun_chunk",
                )

        return self.to_dataframe()

    def review_stage2_rules(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Fast deterministic checks on all rows.
        """
        for _, row in df.iterrows():
            gsm_id = _s(row.get("GSM_ID"))
            gse_id = _s(row.get("GSE_ID"))

            sex = _s(row.get("Sex_Post"))
            organ = _s(row.get("Organ_Region_Post"))
            pert = _s(row.get("Pert_Post"))
            pert_type = _s(row.get("Pert_Type"))
            sample_type = _s(row.get("SampleType"))
            disease = _s(row.get("Disease_Post"))

            female_organs = {"ovary", "uterus", "cervix", "endometrium", "placenta"}
            male_organs = {"testis", "prostate", "epididymis"}
            organ_norm = organ.lower()

            if sex == "Male" and any(x in organ_norm for x in female_organs):
                self.add_issue(
                    gsm_id, gse_id, "sex_organ_conflict", "Sex_Post", "high",
                    f"Sex_Post=Male but Organ_Region_Post={organ}.",
                    "rerun_field",
                )

            if sex == "Female" and any(x in organ_norm for x in male_organs):
                self.add_issue(
                    gsm_id, gse_id, "sex_organ_conflict", "Sex_Post", "high",
                    f"Sex_Post=Female but Organ_Region_Post={organ}.",
                    "rerun_field",
                )

            control_terms = {"Untreated", "Vehicle Control", "DMSO", "PBS", "Saline", "Mock", "Control"}
            if pert in control_terms and pert_type not in {"CTL", "NA"}:
                self.add_issue(
                    gsm_id, gse_id, "pert_control_conflict", "Pert_Type", "medium",
                    f"Pert_Post={pert} but Pert_Type={pert_type}.",
                    "rerun_field",
                )

            if sample_type.lower() == "cell line":
                for fld in ["Race_Post", "Ethnicity_Post", "Age_Post"]:
                    val = _s(row.get(fld))
                    if val not in {"NA", "Unknown"}:
                        self.add_issue(
                            gsm_id, gse_id, "demographic_cellline_suspect", fld, "low",
                            f"{fld}={val} for SampleType=cell line.",
                            "manual_review",
                        )

            if disease == "NA" and organ not in {"NA", "Unknown"}:
                self.add_issue(
                    gsm_id, gse_id, "missing_key_field", "Disease_Post", "low",
                    "Disease_Post is NA while Organ_Region_Post is present.",
                    "rerun_field",
                )

        return self.to_dataframe()

    def review_within_gse(self, df: pd.DataFrame) -> pd.DataFrame:
        stable_fields = [
            "Seq_Type_Post",
            "Organism_Post",
            "Experimental_Setting_Post",
            "Model_Type_Post",
        ]

        for gse_id, sub in df.groupby("GSE_ID", dropna=False):
            for fld in stable_fields:
                if fld not in sub.columns:
                    continue
                vals = sorted(set(sub[fld].astype(str).fillna("NA")))
                vals = [v for v in vals if v not in {"NA", "nan"}]
                if len(vals) > 1:
                    self.add_issue(
                        gsm_id="GSE_LEVEL",
                        gse_id=str(gse_id),
                        issue_type="within_gse_heterogeneity",
                        field_name=fld,
                        severity="medium",
                        message=f"{fld} has multiple values within GSE: {vals}",
                        reviewer_action="manual_review",
                    )

        return self.to_dataframe()

    def get_flagged_rows_for_llm(self) -> pd.DataFrame:
        """
        Review-by-exception routing:
        only rows with actual issues get LLM review.
        """
        df = self.to_dataframe()
        if df.empty:
            return df

        # Exclude run-level only rows from row review
        row_df = df.loc[~df["gsm_id"].isin(["RUN_LEVEL", "GSE_LEVEL"])].copy()
        if row_df.empty:
            return row_df

        severity_rank = {"high": 0, "medium": 1, "low": 2}
        row_df["_sev_rank"] = row_df["severity"].map(lambda x: severity_rank.get(str(x).lower(), 9))
        row_df = row_df.sort_values(["_sev_rank", "gse_id", "gsm_id"])
        return row_df

    def build_reannotation_queue(
        self,
        rule_review_df: pd.DataFrame,
        llm_row_review_df: pd.DataFrame | None = None,
        llm_gse_review_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Combine rule-based and LLM reviewer outputs into a rerun queue.
        """
        queue_rows: List[Dict[str, Any]] = []

        if rule_review_df is not None and not rule_review_df.empty:
            for _, r in rule_review_df.iterrows():
                gsm_id = _s(r.get("gsm_id"))
                if gsm_id in {"RUN_LEVEL", "GSE_LEVEL"}:
                    continue
                queue_rows.append({
                    "gsm_id": gsm_id,
                    "gse_id": _s(r.get("gse_id")),
                    "source": "rules",
                    "field_name": _s(r.get("field_name")),
                    "issue_type": _s(r.get("issue_type")),
                    "message": _s(r.get("message")),
                    "recommended_action": _s(r.get("reviewer_action")),
                })

        if llm_row_review_df is not None and not llm_row_review_df.empty:
            for _, r in llm_row_review_df.iterrows():
                flagged_fields = []
                try:
                    flagged_fields = json.loads(_s(r.get("flagged_fields")))
                except Exception:
                    pass
                if not flagged_fields:
                    flagged_fields = ["UNKNOWN_FIELD"]

                for fld in flagged_fields:
                    queue_rows.append({
                        "gsm_id": _s(r.get("gsm_id")),
                        "gse_id": _s(r.get("gse_id")),
                        "source": "llm_row",
                        "field_name": fld,
                        "issue_type": "llm_review_flag",
                        "message": _s(r.get("review_reason")),
                        "recommended_action": _s(r.get("recommended_action")),
                    })

        if llm_gse_review_df is not None and not llm_gse_review_df.empty:
            for _, r in llm_gse_review_df.iterrows():
                try:
                    flagged = json.loads(_s(r.get("flagged_gsms_json")))
                except Exception:
                    flagged = []
                for item in flagged:
                    gsm_id = _s(item.get("GSM_ID"))
                    fields = item.get("flagged_fields", []) or ["UNKNOWN_FIELD"]
                    for fld in fields:
                        queue_rows.append({
                            "gsm_id": gsm_id,
                            "gse_id": _s(r.get("gse_id")),
                            "source": "llm_gse",
                            "field_name": fld,
                            "issue_type": "llm_gse_review_flag",
                            "message": _s(r.get("summary")),
                            "recommended_action": _s(item.get("recommended_action")),
                        })

        if not queue_rows:
            return pd.DataFrame(columns=[
                "gsm_id", "gse_id", "source", "field_name",
                "issue_type", "message", "recommended_action"
            ])

        queue_df = pd.DataFrame(queue_rows).drop_duplicates()
        return queue_df

    def to_dataframe(self) -> pd.DataFrame:
        if not self.issues:
            return pd.DataFrame(
                columns=["gsm_id", "gse_id", "issue_type", "field_name", "severity", "message", "reviewer_action"]
            )
        return pd.DataFrame([i.__dict__ for i in self.issues])

    def save(self, out_path) -> None:
        self.to_dataframe().to_excel(out_path, index=False)