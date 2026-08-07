Agent task: Strain standardization

Standardize the `Strain` field according to the rules below. Preserve the
input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Standardize only strain information.
- Do not annotate or return genotype information.
- If an input term contains both strain and genotype information, use only the
  strain component to determine the standardized Strain value.
- If no strain can be confidently determined, use `NA`.

## Standardization Rules

1. Strain Identification

Identify the strain, substrain, background, hybrid background, recombinant
inbred background, or mixed genetic background represented by each term.

Ignore genotype, transgene, reporter, knockout, knockin, mutation, Cre-driver,
or other genetic-modification information when determining the Strain value.

Examples:
- `Amigo2-GFP C57BL/6` → `C57BL/6`
- `Bmal -/-` → `NA`
- `AP4-mCherry c-MYC-GFP knockin` → `NA`

2. Standardize Common Mouse Strains

Normalize spelling, capitalization, spacing, slash usage, and commonly used
variants to the following standardized strain labels when appropriate.

- Variants such as `C57BL6`, `C57Black6`, `CD57BL/6`, `Bl/6`, `BL6`,
  and `B6` → `C57BL/6`
- BALB/c-related variants → `BALB/c`
- 129-related variants should be standardized to the most specific supported
  129 background that can be confidently determined.
- FVB-related variants → `FVB`
- DBA-related variants → `DBA`
- `CD1`, `CD-1`, and `ICR` → `CD-1`
- PWK-related variants → `PWK`
- 129/Ola-related variants → `129/Ola`
- 129/SvEv-related variants → `129/SvEv`

Preserve a more specific standardized strain label when it is biologically
meaningful and can be confidently identified from the input.

3. Institution and Vendor Suffixes

Remove institution- or vendor-specific suffixes only when the project
standardization intentionally collapses them to the broader strain label.

Examples:
- `BALB/cJ` → `BALB/c`
- `FVB/NJ` → `FVB`

Do not remove characters that are part of the biological strain identity
rather than a removable source designation.

4. Mixed and Hybrid Backgrounds

For a known cross or mixed background with identifiable parental strains,
use:

`Mixed: Strain1 X Strain2`

Use an uppercase `X` consistently.

If maternal and paternal strains are explicitly identified, list the maternal
strain first and the paternal strain second.

Examples:
- `BXD-11/TyJ` → `Mixed: C57BL/6 X DBA/2`
- `AXB-2/PgnJ` → `Mixed: A/J X C57BL/6`

If more than two contributing strains are explicitly identified, preserve all
supported components in their stated order.

Example:
- `BDF1(mother) X PWK(father)` → `Mixed: C57BL/6 X DBA/2 X PWK`

5. Unspecified Mixed or Outbred Populations

For terms indicating a mixed or outbred population without identifiable
parental strains, use:

`Mixed`

Examples:
- `Mixed background` → `Mixed`
- `Diversity Outbred` → `Mixed`
- `Outbred` → `Mixed`

6. Recombinant Inbred Strains

When the parental backgrounds of a recombinant inbred strain are known,
represent them using:

`Mixed: Strain1 X Strain2`

Example:
- BXD strains → `Mixed: C57BL/6 X DBA/2`

7. Typographical Variants

Correct clear strain-name spelling or formatting errors when the intended
strain is unambiguous.

Example:
- `CH3` when clearly referring to C3H → `C3H`

Do not guess when the intended strain cannot be determined confidently.

8. Cell Lines and Genotype-Only Terms

Cell-line names are not strain labels.

Examples:
- `CGR8` → `NA`
- `CJ7` → `NA`

Likewise, genotype-only terms without identifiable strain information should
be standardized as `NA`.

9. Final Consistency

Use consistent capitalization, slash placement, spacing, and strain
nomenclature across equivalent terms.

For crosses, always use an uppercase `X`:

`Mixed: Strain1 X Strain2`

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.
