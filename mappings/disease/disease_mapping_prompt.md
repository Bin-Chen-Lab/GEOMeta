# Disease Ontology Mapping Prompt

## Purpose

Map standardized GEOMeta disease terms to the most appropriate CTD/MEDIC disease concept. The goal is to assign a canonical disease name and associated disease identifier while avoiding overmatching, hallucination, and unsupported subtype assignment.

This prompt is used as additional guidance inside the Stage 3 disease mapping workflow. The Python script performs candidate retrieval and provides candidate disease records. The model should select the best mapping only from the provided candidate context unless the candidates are clearly misleading. Candidate retrieval may include TF-IDF similarity, synonym expansion, ontology lookup, or hybrid retrieval methods.

## Input

Each mapping task includes:

- A standardized disease term from GEOMeta.
- Candidate CTD/MEDIC disease records retrieved by the mapping script.
- Candidate fields may include:
  - DiseaseName
  - DiseaseID
  - AltDiseaseIDs
  - Synonyms
  - Context text

## Mapping Rules

### 1. Use Canonical CTD/MEDIC Disease Names

Always return the exact canonical `DiseaseName` from the provided candidate context.

Do not create a simplified, shortened, or paraphrased disease name.

### 2. Exact and Synonym Matches

If the input term matches a candidate `DiseaseName` or listed synonym after normalization, return the corresponding canonical `DiseaseName` and `DiseaseID`.

Matching should be case-insensitive and robust to minor punctuation or spacing differences.

### 3. Multi-Disease Terms

If the input contains multiple disease components joined by `+`, treat each component independently.

Return matched disease names in the same order, joined by ` + `.

If no suitable match is found for one component, return `NA` for that component.

### 4. Abbreviations

Expand common disease abbreviations only when supported by the candidate context or established biomedical usage.

Examples:
- `SLE` → `Lupus Erythematosus, Systemic`
- `AML` → `Leukemia, Myeloid, Acute`

Do not expand ambiguous abbreviations without contextual support.

### 5. Subtypes and Generalization

If the subtype or modifier is clinically central and explicitly stated in the input, preserve it whenever supported by the ontology.

If the subtype is not available or not clearly supported, return the most appropriate general disease concept that preserves the core disease identity.

Do not return numbered or named subtypes unless the same subtype identifier appears in the input.

Examples:
- Input includes `type 2 diabetes` → map to the supported diabetes concept if available.
- Input does not include a subtype number → do not map to `Alzheimer disease type 4` or another numbered subtype.

### 6. Avoid Overmatching by Generic Modifiers

Do not select a disease based only on generic modifiers such as:

- acute
- chronic
- progressive
- age-related
- familial
- juvenile
- senile

These modifiers should not override the core disease class.

Example:
- `Age-related cognitive disorder` should map to a cognitive disorder concept if supported, not to age-related macular degeneration.

### 7. Genetic Locus Compatibility

Do not map terms to diseases with incompatible chromosomal loci or genetic regions.

Example:
- A term involving `22q11` should not be mapped to a disease involving `13q`.

### 8. Composite Clinical Descriptions

If the input includes phrases such as `with`, `in`, `associated with`, or organ-specific modifiers, treat the phrase as a single disease concept unless the term is explicitly joined by `+`.

Examples:
- `Colorectal cancer liver metastasis` should be treated as one clinical concept.
- If a specific metastatic concept is not available, map to the base disease only when appropriate and explain the limitation.

### 9. Disease Versus Etiology

If the input describes a condition caused by another condition, map the primary clinical condition when it is available.

Examples:
- `Mild cognitive impairment due to Alzheimer's disease` → map to `Mild Cognitive Impairment` if available.
- `Delirium due to UTI` → map to `Delirium` if available.

Only map to the secondary cause if the primary condition is not independently available.

### 10. Disease Versus Phenotype or Finding

If the input term is a phenotype, symptom, laboratory finding, or nonspecific abnormality rather than a disease, map only if CTD/MEDIC contains an appropriate concept.

If no suitable disease concept exists, return `NA`.

### 11. Avoid Hallucination

Do not infer unsupported disease concepts or invent ontology mappings.

Do not choose a candidate based only on partial keyword overlap.

If all provided candidates are unrelated or misleading, return `NA` unless a clearly semantically appropriate candidate is present in the context.

### 12. Prioritize Semantic Correctness

When exact string similarity conflicts with disease meaning, prioritize semantic correctness.

Use synonyms, definitions, disease hierarchy, and biomedical context when selecting the best match.

## Required Output Format

When used by the Stage 3 mapping script, return strict JSON only:

```json
{
  "mappings": [
    {
      "raw": "<standardized disease term>",
      "DiseaseName": "<canonical CTD/MEDIC DiseaseName or NA>",
      "DiseaseID": "<DiseaseID or NA>",
      "explanation": "<brief justification>"
    }
  ]
}