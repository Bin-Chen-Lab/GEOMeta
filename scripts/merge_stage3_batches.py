from pathlib import Path
import pandas as pd

workdir = Path(".").resolve()

run1 = "geometa_may2026_hs_batch1_2_20260615_020000"
run2 = "geometa_may2026_hs_batch3_4_20260615_074356"
merged_run = "geometa_may2026_hs_batch1_4_20260618"

search_dirs = [
    workdir / "artifacts" / "outputs",
    workdir / "artifacts" / "review_queue",
    workdir / "artifacts" / "manual_review" / "novel_terms",
]

ADD_BATCH_SOURCE = True


def read_excel_all_sheets(path: Path) -> dict[str, pd.DataFrame]:
    return pd.read_excel(
        path,
        sheet_name=None,
        dtype=str,
        keep_default_na=False,
        engine="openpyxl",
    )


def align_and_concat(df1: pd.DataFrame, df2: pd.DataFrame, label1: str, label2: str) -> pd.DataFrame:
    df1 = df1.copy()
    df2 = df2.copy()

    if ADD_BATCH_SOURCE:
        if "Batch_Source" not in df1.columns:
            df1.insert(0, "Batch_Source", label1)
        if "Batch_Source" not in df2.columns:
            df2.insert(0, "Batch_Source", label2)

    all_cols = list(dict.fromkeys(list(df1.columns) + list(df2.columns)))

    for c in all_cols:
        if c not in df1.columns:
            df1[c] = ""
        if c not in df2.columns:
            df2[c] = ""

    return pd.concat(
        [df1.loc[:, all_cols], df2.loc[:, all_cols]],
        ignore_index=True,
    )


def merge_excel_pair(file1: Path, file2: Path, output_path: Path) -> list[dict]:
    sheets1 = read_excel_all_sheets(file1)
    sheets2 = read_excel_all_sheets(file2)

    all_sheet_names = list(dict.fromkeys(list(sheets1.keys()) + list(sheets2.keys())))

    summary_rows = []
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        used_sheet_names = set()

        for sheet_name in all_sheet_names:
            df1 = sheets1.get(sheet_name, pd.DataFrame())
            df2 = sheets2.get(sheet_name, pd.DataFrame())

            merged = align_and_concat(df1, df2, "batch1_2", "batch3_4")

            safe_sheet_name = str(sheet_name)[:31]
            base = safe_sheet_name
            i = 1
            while safe_sheet_name in used_sheet_names:
                suffix = f"_{i}"
                safe_sheet_name = base[: 31 - len(suffix)] + suffix
                i += 1
            used_sheet_names.add(safe_sheet_name)

            merged.to_excel(writer, sheet_name=safe_sheet_name, index=False)

            gsm_unique_count = ""
            gsm_dup_count = ""
            if "GSM_ID" in merged.columns:
                gsm = merged["GSM_ID"].astype(str).str.strip()
                gsm_unique_count = gsm.nunique()
                gsm_dup_count = int(gsm.duplicated().sum())

            summary_rows.append(
                {
                    "Output_File": str(output_path),
                    "Sheet": sheet_name,
                    "Rows_Batch1_2": len(df1),
                    "Rows_Batch3_4": len(df2),
                    "Rows_Merged": len(merged),
                    "Columns_Merged": len(merged.columns),
                    "Unique_GSM_ID": gsm_unique_count,
                    "Duplicated_GSM_ID_Rows": gsm_dup_count,
                    "Columns_Only_In_Batch1_2": "; ".join([c for c in df1.columns if c not in df2.columns]),
                    "Columns_Only_In_Batch3_4": "; ".join([c for c in df2.columns if c not in df1.columns]),
                }
            )

    return summary_rows


all_summary_rows = []
missing_pairs = []

for folder in search_dirs:
    if not folder.exists():
        print(f"[SKIP] Folder not found: {folder}")
        continue

    run1_files = sorted(folder.glob(f"{run1}*.xlsx"))

    for file1 in run1_files:
        suffix = file1.name.replace(run1, "", 1)
        file2 = folder / f"{run2}{suffix}"

        if not file2.exists():
            missing_pairs.append(
                {
                    "Folder": str(folder),
                    "Batch1_2_File": file1.name,
                    "Expected_Batch3_4_File": file2.name,
                    "Status": "Missing batch3_4 counterpart",
                }
            )
            print(f"[MISSING] {file1.name} -> expected {file2.name}")
            continue

        output_path = folder / f"{merged_run}{suffix}"

        print(f"[MERGE] {file1.name}")
        print(f"        {file2.name}")
        print(f"   -->  {output_path.name}")

        all_summary_rows.extend(merge_excel_pair(file1, file2, output_path))


summary_df = pd.DataFrame(all_summary_rows)
missing_df = pd.DataFrame(missing_pairs)

summary_path = workdir / "artifacts" / "review_queue" / f"{merged_run}_merge_summary.xlsx"

with pd.ExcelWriter(summary_path, engine="openpyxl") as writer:
    summary_df.to_excel(writer, sheet_name="merge_summary", index=False)
    missing_df.to_excel(writer, sheet_name="missing_pairs", index=False)

print("\n[SAVED] Merge summary:", summary_path)

if not summary_df.empty:
    print("\n===== MERGE SUMMARY =====")
    print(summary_df[["Output_File", "Sheet", "Rows_Batch1_2", "Rows_Batch3_4", "Rows_Merged", "Unique_GSM_ID", "Duplicated_GSM_ID_Rows"]].to_string(index=False))

if not missing_df.empty:
    print("\n===== MISSING PAIRS =====")
    print(missing_df.to_string(index=False))
