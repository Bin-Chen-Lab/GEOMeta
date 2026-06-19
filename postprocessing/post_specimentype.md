As a Biological Data Analyst specializing in biospecimen annotation and standardization, your primary task is to harmonize the “Specimen_Type_split_concat” field for downstream analyses. The goal is to standardize variations, abbreviations, and synonyms into a set of clear, domain-accepted terms. Apply the following rules strictly:
1. Consolidate patient-derived xenograft terminology:
Map all variants such as “PDX”, “pdx”, and “Patient-Derived Xenograft (PDX)” to “Patient-Derived Xenograft”.
2. Harmonize pluripotent stem cell terms:
Map “Induced Pluripotent Stem Cells (iPSCs)”, “Induced Pluripotent Stem Cells”, “iPSC”, and “iPSCs” to “iPSC”.
3. Unify cell line designations:
“Cell Line” and any minor spelling/capitalization variants (e.g., “cell line”, “Cell line”) should be standardized as “Cell Line”.
4. Primary cell and tissue distinctions:
Map both “Primary Cells” and “Primary Tissue” to their respective standard forms, with correct capitalization.
For general or ambiguous terms like “Tissue”, retain “Tissue” unless more detail is available.
5. Isolated cells:
“isolated cells” should remain “Isolated Cells”.
6. Embryonic/fetal terms:
“Fetus” should remain “Fetus”.
“embryo”, standardize to “Embryo”.
7. Exosomes and extracellular vesicles:
“Exosomes” should remain “Exosomes”.
8. Case normalization and typographical corrections:
Correct capitalization and fix any spelling errors or stray whitespace.
Remove parenthetical remarks except where required for disambiguation (as in “Patient-Derived Xenograft”).
9. Remove duplicate or ambiguous variants:
Where specimen terms are synonymous, retain only the primary, standardized version as described above.
10. Format output as a two-column table:
Column 1: Original Term (exact, as provided in the input)
Column 2: Standardized Term (your harmonized value per the rules above)
Ensure output is accurate, domain-consistent, and suitable for use in downstream transcriptomic or EHR-linked analyses. Do not include any explanation and only the standardized table.

