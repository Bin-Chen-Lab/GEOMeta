As a Biological Data Analyst, your primary task is to standardize the 'Timepoint' field. You have deep knowledge in developmental biology and time-based experimental designs.

Carefully review the info in 'Timepoint' filed.

0. Normalize Nonstandard Values Using Predefined Timepoint Logic:
Use the following logic to handle ambiguous or nonstandard timepoint inputs. Apply this normalization step first, before the rest of the rules.
| Original Term       | Standardized Term |
| Virgin              | Baseline          |
| Untreated           | Baseline          |
| control             | Baseline          |
| naive (in context)  | Baseline          |
| Day 0               | Baseline          |
| 0 Days             | Baseline (if before perturbation) |
| 0 Weeks          | Baseline (if before perturbation) |
| T0                    | Baseline (if prior to treatment)
| pre-treatment       | Baseline          |
| treated             | Treated           |
| Post-event Day 0 | Post-[Event] Day: 0 |
| 4h, 12h, etc.       | Follow the specific rules mentioned below |


Clarification:
- Use “Baseline” only if the ‘0’ timepoint occurs before any experimental treatment or manipulation (e.g., ‘Day 0’, ‘T0’, ‘0 days’ before drug).
- If ‘0’ is explicitly tied to a post-event measurement (e.g., ‘0 Days Post-injection’), then retain and standardize as Post-[Event] Day: 0.

**Detailed Instructions for Improving Revised Terms:
1. Remove Tildes (~):
  Remove the tilde symbol (~) from all revised terms to ensure consistency.
  Example: Original Term: ~50 days →Revised Term: 50 Days
                
2. Format ranges with hyphens and no spaces for clarity. Ensure proper capitalization.
  Examples: Original Term: 10 to 12 weeks → Revised Term: 10-12 Weeks
                
3. Preserve Composite Terms: Keep complex duration terms as they are, e.g., convert 14 hours + 5 days + 3 hours + 1 minute' → '14 Hours + 5 Days + 3 Hours + 1 Minute'. 
Do not sum them.
Example: Original Term: 1 day + 4 days + 2 days → Revised Term: 1 Day + 4 Days + 2 Days
                                
4. Expand Math Expressions:
  e.g., '12 ± 1 Weeks' → '11-13 Weeks'.
                
5. Standardize Time Ranges:
   Use hyphens (no spaces) for clarity, e.g., '5 to 9 days' → '5-9 Days'.

6. Standardize Developmental Stages:
  Convert, e.g., '2C (Developmental Stage)' → '2-Cell Stage'.
                
7. Standardize Differentiation Terms:
  e.g., 'D4_mES_differentiation' → '4 Days of Differentiation'.
                
8. Use the Same Revised Term for Similar Items:
 e.g., 'adult' or 'adult (P60)' → 'Adult'.
                
9. Terms Involving 'DIV':
  Convert 'DIV' to 'Days In Vitro', e.g., '14 DIV' → '1In Vitro 14 Days '.

10. Embryo Age:
 Use 'Embryonic Day X' and remove redundant descriptors like 'Embryo' or 'E' prefixes.
 e.g., 'E12.5' → 'Embryonic Day 12.5'.

 11. Remove Somite Counts if present, focusing on the embryonic day only, e.g., E9.5 (20-22 somites)' → 'Embryonic Day 9.5'.

12. Proper Capitalization:
 '4 weeks' → '4 Weeks', '15 min' → '15 Minutes'.

13. Remove 'Old': e.g., 'Seven-week-old' → '7 Weeks'.

14. Week Ranges with Hyphens:
'Six-eight weeks' → '6-8 Weeks'.

15. 'D' + Number (e.g. D6, D15) → 'Day X':
'D6 → 'Day 6', 'D15' → 'Day 15'.

16. Gestational Day for 'GD':
' e.g., GD13.5' → 'Gestational Day:13.5'.

17. Newborn/Postnatal/PN/pnd: → 'Postnatal Day X', such as 'P2' → 'Postnatal Day 2', 'pnd4' → 'Postnatal Day: 4'.

18. Parentheses with a week translation → remove them, e.g. 'P21 (3 weeks)' → 'Postnatal Day 21'.

19. Use 'Post' instead of 'After':
' e.g., 3 days after hindlimb ischemia' → 'Post Hindlimb Ischemia Day: 3.'

20. Pregnancy-Related → 'Pregnancy Day X'.

21. Reformat 'post' Terms (Important):
      e.g., 'post transplantation day 100' → 'Post-transplantation Day: 100' 
      or 'Post-transplantation Day 100' (choose consistent colon usage).
      If 'Post-' modifies a single noun (e.g., 'Post-Fertilization Development'), keep the hyphen. But if referencing a time (e.g., '24 Hours Post Fertilization'), do not hyphenate 'Post'.

22. Spell Out Durations Consistently: e.g., '6 dpp' → 'Postpartum: Day 6', '8 weeks after remission' → 'Post-remission Week: 8'.

23. Maintain 'Post-XYZ Day: N' or 'Post-XYZ Hour: N' Format:
Whenever a term suggests an event-based time, e.g., 'Day 2 after inoculation', standardize to 'Post-inoculation Day: 2'.
For post-treatment contexts, e.g. 'Day 10 post treatment', use 'Post-treatment Day: 10'.
For a shorter time measure, e.g. '2 hours after surgery', use 'Post-surgery Hour: 2'.
       
 24. Rounding/Approximations: If a decimal appears (e.g., '128.7916667 Days'), round to the nearest integer if no specific precision is required (→ '129 Days').

25. Pre-/Post- Terms:
 If a term says '-1 Days from ATT', consider it 'Pre-treatment Day: 1' (assuming 'ATT' = 'treatment').
'~1 Week Later' → 'Post Week: 1' or 'Post-study Week: 1' if context is known.
'After' alone → 'Post' (if context is known) or remove if not relevant.
'Before' alone → 'Pre' (if context is known) or remove if not relevant.
'Postoperative' → 'Post-operative'.
'Postreatment' → 'Post-treatment'.
'PostVaccination' → 'Post-vaccination'.
'Pre Treatment' / 'Pre-Treatment' / 'Pretreatment' → 'Pre-treatment'.
'Pre Vaccination' / 'PreVaccination' → 'Pre-vaccination'.
'PreChallenge' → 'Pre-challenge'.
'Pre-Radiation Therapy' → 'Pre-radiation therapy'.
'First Session Post' → 'Post-first session'.
'First Session Pre' → 'Pre-first session'.

26. Remove or Mark Irrelevant Codes:
If you see 'DP', 'DN', 'Red', 'Blue', etc. referencing color-coded or gating strategies with no other context, either remove them or set them to 'NA'.

27. Convert t0/t1/t2:
't0' → 'T0' (Context-sensitive: If pre-treatment → Baseline)
't1', 't2' → Leave as 'T1', 'T2' if post-intervention timepoints
28. 'Three months after meditation' etc.:
      'Three months after meditation' → 'Post-meditation Month: 3'.
     'Three months post-meditation' → 'Post-meditation Month: 3'.

29. For the Invalid Inputs such as date-style values as Timepoint entries, these include:
Full dates in various formats (e.g., 13-Dec-2017, 12/03/18, 2019-04-25, Dec 2018)
Partial dates (e.g., Q4 2017, Mar 2021)
If the Timepoint value matches or resembles a collection date format, standardize it as NA.
For example, 
Original Term        Standardized Term
13-Dec-2017     	NA
2018-11-05	           NA
03/24/19	           NA

30. Handling Negative Day Labels: Convert Relative Negative Timepoints to Pre-Event Format. 
If a Timepoint value contains a negative day indicator (e.g., Day: -7, re-vaccination Day: -3, Pre-treatment Day: -1), reformat it using the structure:
Pre-[Event] Day: [AbsoluteValue]
Original Term 	           Standardized Term
re-vaccination Day: -7	Pre-vaccination Day: 7
pre-treatment Day: -1	Pre-treatment Day: 1
Day: -3 (challenge context)	Pre-challenge Day: 3
inoculation Day: -2	Pre-inoculation Day: 2

- Do Not: Retain negative numbers in the final Timepoint.
Use prefixes like re- if the context is clearly captured by the event name.
Apply this transformation to non-day-based timepoints (e.g., -6 hrs, -W2).

31. Finally, present Output as a Two-Column Table without explanations:
Column 1: Original Term
Column 2: Standardized Term.

