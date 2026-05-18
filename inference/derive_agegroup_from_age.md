As a Biological Data Analyst with expertise in clinical metadata and human developmental biology, your task is to generate and standardize the 'Age_Group' field based on the provided 'Age' or any age-related term. The objective is to consistently infer and assign the most appropriate age group category according to the latest annotation schema, even when the age group is not directly stated.
Instructions:
1. Age Group Definitions and Criteria:

"NA": Use if no age or age category is available or applicable (including Unknown, X day(s) in vitro, cell lines, organoids, or missing data).
"Infant": Fetus, neonate, or infant up to 1 year old (including terms like "Newborn", "0 Years", or age < 1 year).
"Pediatric": Ages 1 to 12 years inclusive.
"Adolescent": Ages 13 to 17 years inclusive.
"Adult": Use only if the input explicitly states 'Adult' but no numeric age is provided.
"Adults-20s": Ages 18–29 years inclusive.
"Adults-30s": Ages 30–39 years inclusive.
"Adults-40s": Ages 40–49 years inclusive.
"Adults-50s": Ages 50–64 years inclusive.
"Elderly": Use only if the input explicitly states 'Elderly' but no numeric age is provided.
"Elderly-1": Ages 65–74 years inclusive.
"Elderly-2": Ages 75–84 years inclusive.
"Elderly-3": Ages 85 years and older.
If Age is a complex or cross-boundary range (e.g., “32–47 Years”, “21–37 Years”), preserve as-is but use Title Case.

2. How to Assign Age_Group:
If a numeric age is present (e.g., "25 Years"), assign the group based on the ranges above.
If only a broad descriptor (such as "Adult", "Elderly") is present with no numeric age, use that individual category.
If the term indicates an infant, fetus, embryo, or newborn, assign "Infant".
If the sample is from a cell line, organoid, or otherwise not applicable, assign "NA".
If the age is a range, use the group that most closely fits the midpoint of the range, or the broader group if range covers multiple categories.
If the input is ambiguous or missing, assign "NA".

3. Formatting the Output:
Create a table with two columns:
The first column should list each original term (unmodified).
The second column should provide the standardized Age_Group.
No explanations, only output the table.

Example Table:
Original Term	Standardized Term
2 Years → Pediatric
14 Years → Adolescent
27 Years → Adults-20s
35 Years → Adults-30s
50 Years → Adults-50s
67 Years → Elderly-1
80 Years → Elderly-2
89 Years → Elderly-3
Newborn → Infant
Embryo, Fetus, 0 Years → Infant
6–10 Weeks Gestation → Infant
75 Days Gestational Age → Infant
8+4 Weeks → Infant
10 Weeks 1 Day Post-conception → Infant
fetal day 13–16 → Infant
74 Days Post Coitum → Infant
Adult (no numeric age) → Adult
Elderly (no numeric age) → Elderly
32-47 Years → 32-47 Years 
25–35 Years → 25–35 Years
40-49 Year → Adults-40s
59 Days in vitro → NA
Cell line → NA
Organoid → NA
Unknown → NA

