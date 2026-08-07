Agent task: Age-group derivation

Derive the `Age_Group` field from the standardized `Age` value according to the rules below. Preserve the input order and return one derived Age_Group value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and derived terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Derive Age_Group only from information contained in the Age term.
- Do not infer age from unrelated metadata.
- Use `NA` when Age_Group cannot be determined.

## Derivation Rules:

1. Age Group Definitions and Criteria:
- "NA": Use if no age or age category is available or applicable (including Unknown, X day(s) in vitro, cell lines, organoids, or missing data).
- "Infant": Fetus, neonate, or infant younger than 1 year (including terms like "Newborn", "0 Years", or age < 1 year).
- "Pediatric": Ages 1 to 12 years inclusive.
- "Adolescent": Ages 13 to 17 years inclusive.
- "Adult": Use only if the input explicitly states 'Adult' but no numeric age is provided.
- "Adults-20s": Ages 18–29 years inclusive.
- "Adults-30s": Ages 30–39 years inclusive.
- "Adults-40s": Ages 40–49 years inclusive.
- "Adults-50s": Ages 50–64 years inclusive.
- "Elderly": Use only if the input explicitly states 'Elderly' but no numeric age is provided.
- "Elderly-1": Ages 65–74 years inclusive.
- "Elderly-2": Ages 75–84 years inclusive.
- "Elderly-3": Ages 85 years and older.
- If Age is a complex or cross-boundary range (e.g., “32–47 Years”, “21–37 Years”), preserve as-is but use Title Case.

2. Numeric Age Ranges:
- If the entire age range falls within a single Age_Group category, assign that category.
- If the age range spans more than one Age_Group category, preserve the standardized age range as-is using Title Case.
- Do not use the midpoint to assign a cross-boundary range to a single Age_Group category.

3. Age Unit Handling:

- Ages reported in months should be converted conceptually to years when assigning Age_Group.
- Ages below 12 months → Infant.
- Ages from 12 months to <13 years → Pediatric, according to the equivalent age in years.
- Gestational, embryonic, fetal, or post-conception ages → Infant.

## Output Requirements

Return exactly one derived Age_Group value for each original Age term. Use an Age_Group category when the age can be assigned unambiguously to a single category. Preserve standardized cross-boundary age ranges when they span multiple categories. Use `NA` when Age_Group cannot be determined. Do not include explanations or additional commentary.
