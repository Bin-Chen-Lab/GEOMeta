Agent task: Organism standardization

Standardize the `Organism` field according to the rules below. Preserve the input order and return one standardized value for each original term.


## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Standardize all variants of human organism names to "Homo sapiens":
This includes correcting misspellings, incomplete names, alternative or outdated scientific names, and improper capitalizations.
Examples of variants to standardize:
"homo sapiens" → "Homo sapiens"
"Homo Sapiens" → "Homo sapiens"
"Homo sapiensis" → "Homo sapiens"
"Homo sapiens (human)" → "Homo sapiens"
"human" → "Homo sapiens"
Any other spelling, capitalization, or descriptive variants referring to humans.

2. Retain correct scientific names for non-human organisms:
For samples not from humans, preserve the accurate and standardized binomial (Latin) name, e.g., "Mus musculus" for mouse, "Rattus norvegicus" for rat, "Danio rerio" for zebrafish.
Apply proper capitalization (Genus capitalized, species lowercase) and formatting to all organism names.

3. Remove any extra descriptors, comments, or abbreviations:
Exclude text such as "(sample)", "(cell line)", "(tissue)", "(blood)", or similar parenthetical or bracketed annotations. Only keep the organism name.
For example: "Homo sapiens (blood)" → "Homo sapiens"

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.