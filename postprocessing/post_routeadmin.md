Agent task: Route-of-administration standardization

Standardize the `Route_Admin` field according to the rules below. Preserve the input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Preserve biologically meaningful route information.
- Do not infer an administration route that is not supported by the input.
- Use `NA` when administration route information is not applicable or cannot
  be determined.

## Standardization Rules

1. Expand Route Abbreviations

Expand commonly used administration-route abbreviations to their full standardized forms.

Examples:
- I.V. → Intravenous
- IV → Intravenous
- I.P. → Intraperitoneal
- IP → Intraperitoneal
- S.C. → Subcutaneous
- SC → Subcutaneous
- I.M. → Intramuscular
- IM → Intramuscular

2. Normalize Equivalent Route Terms

Standardize spelling, capitalization, punctuation, and equivalent variants to a single consistent route label.

Examples:
- intraperitoneal injection → Intraperitoneal
- intraperitoneal → Intraperitoneal
- intravenous injection → Intravenous
- oral administration → Oral
- subcutaneous injection → Subcutaneous

3. Preserve Unspecified Injection Status

If the metadata states only that an injection occurred but does not identify the route, standardize as: `Injection (unspecified)`

Do not shorten this value to `Injection`, because the qualifier preserves the fact that the route was not specified.

4. Normalize Specific Route Names
Correct clear spelling or hyphenation variants.
Examples:
- Intra-tracheal → Intratracheal
- intra tracheal → Intratracheal
- Osmotic mini-pump → Osmotic Minipump

5. Tail-Vein Administration
Normalize tail-vein variants consistently.
Examples:
- Tail vein → Tail Vein Injection
- Tail injection → Tail Vein Injection
- Tail veins injection → Tail Vein Injection
Do not use `Tail Vein Injection` when the input does not specifically indicate
tail-vein administration.

6. Administration Through Culture Medium
When the treatment or compound is explicitly added to cell-culture medium,
standardize as: `In Media`

7. Multiple Routes
When multiple routes apply to the same term, standardize each route
individually and join them using: ` + `. Preserve their original order.
Example: - Intraperitoneal (I.P.) + intranasal + oral → Intraperitoneal + Intranasal + Oral

8. Preserve Specific Route Information
Do not collapse a specific administration route to a broader or less informative label when the specific route is clearly provided.

9. Missing or Non-applicable Information
Use `NA` only when no administration route is applicable or when the route cannot be determined from the input.

## Output Requirements

Return exactly one standardized Route_Admin value for each original term.
Do not include explanations or additional commentary.