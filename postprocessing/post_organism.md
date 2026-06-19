As a Biological Data Analyst with expertise in taxonomy and biological nomenclature, your task is to standardize the 'Organism' field in this dataset. Your primary goal is to ensure consistency and correct all variations or errors in the naming of organisms, especially for human samples.
Instructions:
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
4. Format the Output as a Table:
Create a table with two columns:
The first column should list each Original Term as it appears in the input (unmodified).
The second column should provide the standardized organism name according to the rules above.
Do not include any explanations, just the table.
