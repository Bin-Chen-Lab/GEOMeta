Agent task: Outcome standardization

Standardize the `Outcome` field according to the rules below. Preserve the input order and return one standardized value for each original term.


## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Use the definitions and rules for 'Outcome'—which can include up to three components (Response, Survival, Prognosis)—to standardize each term.

2. Response (for patient or cell line):
- Patient: Responder, Partial Responder, Stable Disease, Non-Responder, Unknown.
- Cell line: Sensitive, Partially Sensitive, Resistant, Unknown.

3. Survival (patient only): 
- '[Survival_Time]: [Status]', e.g. '36 Months: Alive', '12 Months: Deceased'.
- If no survival data or if it's a cell line: 'NA'.

4. Prognosis:
 - Good Prognosis, Poor Prognosis, Unknown.

5. Combine multiple components with semicolons, e.g. 'Responder; 24 Months: Alive; Good Prognosis'.
                       
6. If no relevant data is provided, use 'Unknown' or 'NA' as needed.

7. When at least one Outcome component is available, omit unavailable components rather than appending `NA`. Use `NA` only when no applicable Outcome information is available for the entire term.

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.

