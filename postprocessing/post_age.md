# Age Standardization Prompt

## Role

As a Biological Data Analyst, your primary task is to standardize the `Age` field using developmental biology knowledge.

## General Instructions

Before beginning, count the number of original terms. Ensure that:
- The number of standardized terms matches the input count.
- The order of standardized terms matches the original input order.
- Terms are standardized sequentially without skipping entries.

## Standardization Rules
1. Range Formatting
Use hyphens with no spaces to denote ranges.
 10 to 12 weeks → 10-12 Weeks
 Five to seven weeks → 5-7 Weeks
 Six-eight weeks → 6-8 Weeks

2. Preserve Composite Durations
Do not sum multiple durations; retain all as listed.
 1 day + 4 days + 2 days → 1 Day + 4 Days + 2 Days

3. Zero Durations
Use singular for zero units.
 0 days → 0 Day
0 weeks → 0 Week

4. Math Expressions
Expand expressions like ± values.
 12 ± 1 weeks → 11-13 Weeks

5. Time Ranges
Standardize expressions like to, through, and into hyphenated ranges.
 5 to 9 days → 5-9 Days

6. In Vitro Age
If the age describes time in vitro, set value to NA.
7 Days In Vitro → NA

7. Embryonic Days
Remove redundant terms like “embryo” or “E” prefix.
E12.5 → Embryonic Day 12.5
embryonic day E15.0 → Embryonic Day 15

8. Capitalization & Consistency
Capitalize time units uniformly (e.g., Weeks, Days, Years).
4 weeks or 4 Weeks → 4 Weeks

9. Postnatal Time → Chronological Age
Treat postnatal days/weeks as chronological age.
1 Week Postnatal → 1 Week
Postnatal 36 Weeks → 36 Weeks

10. Decimal and Padded Values
Normalize decimals and remove trailing zeros.
10.00 Years → 10 Years
9.0 Days → 9 Days

11. Gestational Age Terms
Use consistent terminology: "X Weeks Gestation" or "X Days Gestation".
75 Days Gestational Age → 75 Days Gestation
14.00 Weeks Gestation → 14 Weeks Gestation

12. Format for Post-conception Expressions: Format as "X Weeks Y Days Post-conception". If Y = 0, simplify to "X Weeks Post-conception"

Original Term	Standardized As
8+4 Weeks	→ 8 Weeks 4 Days Post-conception
10+1 Weeks	→  10 Weeks 1 Day Post-conception
11+0 Weeks	11 Weeks Post-conception

13. Decimal Precision Rule:
(1) For age values with 1 or 2 decimal places, preserve them as-is.
(2) For age values with more than 2 decimal places, round to 2 decimal places using standard rounding rules. Applies to all units: Years, Months, Weeks, Days, Hours.
Examples:
46.5833333333333 Years	→46.58 Years
9.99 Weeks	→ 9.99 Weeks (kept as-is)
1.444 Days	→ 1.44 Days
7.128456 Weeks	→ 7.13 Weeks
            
14. Finally, follow the instructions as described above and present the final table. Do not provide any explanations in any form.

- Create a table with two columns:
- List each original term separately in the first column.
- Provide the standardized term in the second column, ensuring clarity and consistency in how ages are reported.
- Apply biological nomenclature standards and domain expertise to ensure accuracy in the age standardization process.

