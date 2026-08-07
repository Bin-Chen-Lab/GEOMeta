Agent task: Sex standardization

Standardize the `Sex` field according to the rules below. Preserve the input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules
- Male: Use when the term refers exclusively to male sources.
- Female: Use when the term refers exclusively to female sources.
- Mixed: Use when the term explicitly includes both male and female sources.
- Unknown: Use when Sex is applicable but explicitly unknown, ambiguous, or conflicting.
- NA: Use when Sex is not applicable or not reported.

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.