Agent task: Perturbation-duration standardization

Standardize the `Pert_Duration` field according to the rules below. Preserve the input order and return one standardized value for each original term.
            
## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Preserve Composite Terms: Keep complex duration terms as they are to maintain detail, e.g., '14 hours + 5 days + 3 hours + 1 minute' remains unchanged. Convert'1 day + 4 day' to '1 Day + 4 Days'. Do not add as '5 Days'. Consider '48h,24h,6h' as one single term.

2. Format ranges with hyphens and no spaces for clarity. Ensure proper capitalization.
 e.g., 'from 4 weeks to 6 months' becomes '4 Weeks-6 Months'.
  '10 to 12 weeks'becomes '10-12 Weeks'.          

3. Singular and Plural Terms for 0 terms: Standardize to singular where applicable, e.g., '0 Hours' becomes '0 Hour'. Also, ensure uniformity in terminology, changing 'LT' to 'Long-Term'.

4. Consistent Formatting: Capitalize the first letter of each term and maintain consistent terms across entries. For instance, 'overnight + 0 Hours' should be 'Overnight + 0 Hour'.

5. Special Terms Standardization: Standardize terms like 'From birth' to 'From Birth' and 'From day 1 to day 28' to 'From Day 1 to Day 28'.

6. Approximation Symbols
Remove approximation symbols such as `~` while preserving the reported numeric value and unit.
Example: ~18 Hours → 18 Hours
            
## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.
