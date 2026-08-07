Agent task: RNA-source mapping

Map each standardized `RNA_Source` term to the final controlled `RNA_Source_Mapped` label according to the reviewed mappings, reference resources, and rules below.

## General Requirements

- Use reviewed mappings before applying inference-based mapping rules.
- Treat the reviewed mapping file as the source of truth.
- Apply new mappings conservatively.
- Use only the allowed final label formats defined below.
- Use `null` when the final RNA-source label should intentionally remain blank.

## Input
The main input field is RNA_Source_Pre. Optional context may include GSE_Info, GSM_Info, sample title, source name, characteristics, organism, disease, tissue, or cell-line fields.

## Output
Return valid JSON only with these fields: Standardized_Term, RNA_Source_Mapped, Reasoning, and Confidence. Confidence must be one of high, medium, or low. Use null if the final RNA-source label should intentionally be blank.

## Allowed final label format
Use only Tissue: xx, Cells: xx, Cell Line: xx, Biofluid: xx, Other, or null.

## Reuse-first rule
If the term matches a reviewed mapping in RNA_Source_mappings.xlsx, use the reviewed RNA_Source_Mapped value directly. The reviewed mapping file is the source of truth.

## Blood rules
Tissue: Blood maps to Cells: Blood. Tissue: Whole Blood maps to Cells: Whole Blood. Tissue: PBMC maps to Cells: PBMC.
Blood exosome, plasma, serum, or vessel-preparation terms map to Tissue: Other.

## Generic non-informative terms
Exact generic terms map to null. These include Tissue: Tumor, Tissue: Biopsy, Tissue: Adjacent Normal Tissue, Tissue: Extracellular Vesicles, and Tissue: Organoid.

If an adjacent-normal or disease-status term contains a clear anatomical source, recover that tissue. For example, Tissue: Adjacent Normal Cervix maps to Tissue: Cervix, Tissue: Adjacent Normal Colon maps to Tissue: Intestine, and Tissue: Adjacent Non-Tumor Liver Tissue maps to Tissue: Liver.

## Organoid rules
Exact Tissue: Organoid maps to null. Any other organoid-containing term maps to Tissue: Other.
Do not map organoid terms to brain, retina, liver, intestine, or other anatomical tissue.

## HPA-style tissue mapping
Map confident anatomical terms to controlled HPA-style labels. Colon or colorectal maps to Tissue: Intestine. Bladder maps to Tissue: Urinary bladder. Thyroid maps to Tissue: Thyroid gland. Lymph node maps to Tissue: Lymphoid tissue. Spinal cord maps to Tissue: Brain: Spinal cord. Cervical or cervix maps to Tissue: Cervix. Gastric maps to Tissue: Stomach.

## Cancer and metastasis rules
Recover anatomy only when clear. Tissue: Cancerous maps to null. Tissue: Cancer Tissue maps to Tissue: Other. Tissue: Cancer-Free Ovary maps to Tissue: Ovary. Tissue: Metastatic Colorectal Cancer maps to Tissue: Intestine. Tissue: Metastatic Ovarian Cancer maps to Tissue: Ovary.

## CD4/CD8 T-cell rules
Simple CD4-only or CD8-only T-cell terms are standardized. Cells: CD4+ T Cells maps to Cells: CD4 T Cells. Cells: CD8+ T Cells maps to Cells: CD8 T Cells.

Mixed or complex marker-defined subsets map to Cells: Other. For example, Cells: CD4 and CD8 T-cells, Cells: CD3+CD45RO+CD8+ T Cells, and Cells: CD4+CD45RO+CXCR5+PD-1+ T Cells all map to Cells: Other.

## Cell-line rules
Standardize cell-line names only when confident. If matched to StrippedCellLineName, output the corresponding CellLineName. If matched to a reviewed alias, output the reviewed alias. If unmatched and count is at least 30, keep the current Cell Line: xx. If unmatched and count is below 30, map to Cell Line: Other.

## Confidence
Use high when the rule is deterministic or anatomy is clear. Use medium for likely but less direct mappings. Use low for ambiguous terms requiring review.

## Output Requirements
- Return exactly one mapping for each input RNA-source term.
- Preserve the original input term in `RNA_Source_Pre`.
- Return the standardized term in `Standardized_Term`.
- `RNA_Source_Mapped` must use only one of the allowed final label formats:
  `Tissue: xx`, `Cells: xx`, `Cell Line: xx`, `Biofluid: xx`, `Other`, or `null`.
- Use `null` only when the final RNA-source label should intentionally remain blank.
- Provide a brief rationale in `Reasoning`.
- `Confidence` must be exactly `high`, `medium`, or `low`.
- Do not include explanations or commentary outside the structured output.