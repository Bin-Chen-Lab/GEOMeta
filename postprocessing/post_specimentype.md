Agent task: Specimen-type standardization

Standardize the `Specimen_Type` field according to the rules below. Preserve
the input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Use only the canonical Specimen_Type categories defined below.
- Do not create new Specimen_Type categories.

## Canonical Categories

Each standardized value must be exactly one of:

- Primary Tissue
- PDX
- Cell Line
- Organoid
- Isolated Cells
- Fetus
- Tissue Culture
- NA

## Standardization Rules

1. Primary Tissue

Use `Primary Tissue` for intact tissue obtained directly from an organism
without ex vivo culture.

Examples:
- Primary tissue → Primary Tissue
- Fresh tissue → Primary Tissue
- Frozen tissue → Primary Tissue
- Tissue → Primary Tissue when the term clearly refers to directly obtained
  biological tissue and no cultured model is indicated.

2. PDX

Standardize all patient-derived xenograft variants to `PDX`.

Examples:
- PDX → PDX
- pdx → PDX
- Patient-Derived Xenograft → PDX
- Patient-Derived Xenograft (PDX) → PDX

3. Cell Line

Use `Cell Line` for established cell-line cultures, including pluripotent stem
cell lines when represented as cultured cell-line systems.

Examples:
- Cell line → Cell Line
- Cell Line → Cell Line
- iPSC → Cell Line
- iPSCs → Cell Line
- Induced Pluripotent Stem Cells → Cell Line
- Embryonic Stem Cell Line → Cell Line

4. Organoid

Standardize organoid and organoid-like 3D culture terms to `Organoid` when
they clearly represent an organoid system.

5. Isolated Cells

Use `Isolated Cells` for specific cell populations isolated or enriched from
tissue, blood, or biological fluids.

Examples:
- Isolated cells → Isolated Cells
- PBMCs isolated from blood → Isolated Cells
- Sorted cells → Isolated Cells

6. Fetus

Use `Fetus` only when the specimen directly represents fetal biological
material and no more specific cultured or isolated-cell category applies.

7. Tissue Culture

Use `Tissue Culture` for tissue sections or intact tissues maintained ex vivo
in culture while retaining tissue architecture.

8. Unsupported or Unclear Terms

Use `NA` when the input cannot be assigned confidently to one of the canonical
Specimen_Type categories.

Examples:
- Exosomes → NA
- Extracellular vesicles → NA

Do not create new categories such as `Exosomes`, `Embryo`, `Tissue`, or
`Patient-Derived Xenograft`.

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.