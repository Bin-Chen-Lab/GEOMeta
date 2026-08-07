Agent task: Chemical-perturbation mapping

Map each standardized `Pert` term to the best PubChem query term according to the rules below. The query term is used by the Python mapping workflow to retrieve PubChem identifiers and compound metadata.

## General Requirements

- Return one mapping for each input term.
- Select only a PubChem query term; do not return PubChem identifiers directly.
- Do not invent compound names or unsupported chemical identities.
- Return `NA` when a reliable PubChem query cannot be determined.

## Input

Each input is a standardized perturbation term extracted from GEO metadata.

Typical inputs may include:

- drug names
- small molecules
- chemical inhibitors
- experimental compounds
- compound abbreviations
- chemical perturbation combinations

Examples:
- Bleomycin
- Dexamethasone
- Niclosamide ethanolamine
- Cisplatin + Paclitaxel
- BLM
- Dox

## Mapping Goal

For each input term, return the best compound name to send to PubChem name lookup. The query should be a clean compound name, not a full treatment description.

## Query Selection Rules

1. Preserve the Raw Term
Always copy the original input term into the `raw` field.

2. Return a PubChem Query Term
The `query` field should contain the best chemical name to use for PubChem lookup.
Examples:
- `Bleomycin treatment` → `Bleomycin`
- `100 nM Dexamethasone` → `Dexamethasone`
- `BLM` → `Bleomycin` if context supports the abbreviation

3. Remove Non-Identifying Treatment Details
Remove dose, duration, route, frequency, timepoint, and experimental-condition wording.
Examples:
- `Dexamethasone 100 nM for 24 hours` → `Dexamethasone`
- `treated with cisplatin` → `Cisplatin`

4. Expand Unambiguous Abbreviations
Expand abbreviations only when they are common or contextually supported.
Examples:
- `BLM` → `Bleomycin`
- `Dox` → `Doxorubicin` only when supported by context
Do not expand ambiguous abbreviations without support.

5. Preserve Specific Chemical Forms When Important
If the input specifies a salt, formulation, stereochemical form, or named derivative and it is likely represented in PubChem, preserve that specificity.
Examples:
- `Niclosamide ethanolamine` → `Niclosamide ethanolamine`
- Do not reduce to `Niclosamide` unless the specific form cannot be resolved or the context supports the parent compound.

6. Combination Treatments
If the input contains multiple chemical perturbations joined by `+`, `;`, or `/`, preserve the chemical components when possible.

If the current script expects one PubChem query per input term and the combination cannot be represented as a single PubChem query, return the clearest single compound query only when one compound is dominant; otherwise return `NA`.

Examples:
- `Cisplatin + Paclitaxel` → `NA` if one query cannot represent the combination.
- `Cisplatin treatment with vehicle control` → `Cisplatin`

7. Do Not Map Non-Chemical Perturbations
Return `NA` for perturbations that are not chemical compounds.
Examples:
- gene knockdown
- knockout
- CRISPR
- siRNA
- shRNA
- overexpression
- hypoxia
- radiation
- starvation
- infection
- heat shock
- mechanical stress

8. Do Not Map Generic Treatment Descriptions
Return `NA` for vague or generic descriptions.
Examples:
- drug treatment
- chemotherapy
- inhibitor
- compound
- vehicle
- untreated
- control

9. Biological Reagents
For biological reagents such as cytokines, antibodies, proteins, viruses, or cells, return `NA` unless the term clearly corresponds to a chemical compound represented in PubChem.
Examples:
- `TNF alpha` → `NA`
- `IL-6` → `NA`

10. Avoid Hallucination
Do not invent compound names. Do not infer a specific drug from a drug class.
Do not choose a compound based only on partial string similarity.
Return `NA` when no reliable PubChem query can be identified.

11. Preserve Standard Chemical Naming
Use standard biomedical or PubChem-compatible compound naming conventions.
Examples:
- `cis-platin` → `Cisplatin`
- `5 aza` → `5-Azacytidine` if clearly supported

## Output Requirements
- Return exactly one mapping for each input term.
- Preserve the original input term in `raw`.
- Return the best PubChem search term or `NA` in `query`.
- Provide a brief mapping rationale in `explanation`.
- Do not return CID, SMILES, PubChem URL, PubChem title, or other PubChem metadata.
- Do not include explanations or commentary outside the structured output.