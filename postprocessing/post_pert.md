As a Biological Data Analyst with expertise in pharmacology and chemistry, your task is to recognize variations in perturbation terms, understand their biological, pharmacological, or chemical significance, and standardize them accordingly. You are responsible for creating consistent and accurate standardization of treatment descriptions, focusing on clarity, uniformity, and scientific accuracy. Please standardize the perturbation term: {row['Pert_Pre1']} 

Guidelines for Standardization:

Before starting the standardization, check the total number of Original Terms provided. Ensure that the order of terms in your Standardized terms matches the exact order in the input data. Standardize each Original Term sequentially without omission, and verify that the total number of Standardized Terms matches the count in the input.

1. Review Existing Data: Examine the drug treatment information to identify inconsistencies, variations, and errors in drug names, dosages, and other treatment details.

2. Establish Standardization Guidelines: Define standardization guidelines or rules to guide the harmonization process. Consider factors such as drug naming conventions, generic and brand names of drugs, and known abbreviations.

3. Re-Ordering and Grouping: Re-order similar variations of drug names and treatment details to establish a consistent format. Group together drugs that represent the same medication but are described differently, ensuring that all names are standardized to a common form.

4. Consider Case-Insensitivity: Convert all drug names and treatment details to lowercase to ensure uniformity.

5. Standardize Abbreviations: Standardize abbreviations used in drug names or treatment details to their full, unabbreviated forms wherever applicable. This helps avoid ambiguity and misinterpretation. For instance:
- 'TCDD' should be expanded to '2,3,7,8-tetrachlorodibenzo-p-dioxin.'
- 'G418' should be standardized to 'geneticin.'
- 'SAG' should be consistently referred to as 'smoothened agonist.'

6. Remove Dosage Information: Do not include dosage information in the standardized term. Only provide the drug name. For example:
- '0.2% amobarbital' should be standardized to 'Amobarbital.'                     
- '5 µM-hydroxy-tamoxifen' should be standardized to 'Hydroxytamoxifen.'

7. Capitalize Initial Letters:
- Ensure that the initial letter of each word in the standardized term is capitalized. For example:
- 'amobarbital solution' should be standardized to 'Amobarbital Solution.'
- '2,4-dichlorophenoxyacetic acid' should be standardized to '2,4-Dichlorophenoxyacetic Acid.'
- Ensure consistent capitalization across similar terms. For example, if 'all-trans retinoic acid' is standardized as 'All-trans Retinoic Acid,' then 'all-trans RA' should be standardized similarly.
            
8. Remove Parentheses and Short Names: Remove short names or abbreviations provided in parentheses unless they are essential for clarity. For example:
- '10-carboxymethyl-9-acridanone (CMA)' should be standardized to '10-Carboxymethyl-9-Acridanone.'

9. Standardize Specific Terms: Ensure specific terms like 'All-trans' are used consistently. For example: 'all trans retinoic acid' should be standardized to 'All-trans Retinoic Acid.'

10. Replace Greek Characters with Full English Names: Replace Greek characters with their full English names. For example:
- 'β-Estradiol' should be standardized to 'Beta-Estradiol.'
- 'γ' should be standardized to 'gamma.'

11. Standardize Chemical Names: Use full chemical names for substances. For example:
'2,4-D' should be standardized to '2,4-Dichlorophenoxyacetic Acid.'

12. Remove Apostrophes: Remove apostrophes from terms. For example:
- '4'-hydroxytamoxifen' should be standardized to '4-Hydroxytamoxifen.'

13. Use Full Names for Abbreviations: Expand abbreviations to their full names. For example:
- 'T3' should be standardized to 'Triiodothyronine.'

14. Ensure Consistency in Term Format: Ensure consistency in the format of terms across the dataset. For example: use 'Anti-OX40 (IgG1)' instead of 'Anti-OX40 antibody (IgG1).'

15. Use Full Names for Drugs and Antibodies: Use full names for drugs and antibodies, including specifying if they are antibodies. For example:
- 'Anti-IL-4' should be standardized to 'Anti-IL-4 antibody.'
- 'M-CSF' should be standardized to 'Macrophage Colony-Stimulating Factor.'
-'TGFβ1 + IL-6 + IL-1β + IL-21 + Anti-IL-4 + Anti-IFNγ + Anti-IL-12' should be standardized to 'TGF Beta 1 + Interleukin-6 + Interleukin-1 Beta + Interleukin-21 + Anti-Interleukin-4 Antibody + Anti-IFN Gamma Antibody + Anti-Interleukin-12 Antibody'.
                
16. Best Known Synonym: Use the best known synonym for each term to ensure clarity and consistency. For example:
- 'Adriamycin' is better known as 'doxorubicin.'
- 'AG-221' is better known as 'enasidenib.'
- 'LPS' should be expanded to 'lipopolysaccharide.'
- 'M-CSF' should be expanded to 'macrophage colony-stimulating factor.'
- 'β-Estradiol' should be standardized as 'beta-estradiol.'

17. Maintain Hyphenated Forms: Keep all similar terms with a hyphen in their standardized forms. For example: '17-betaestradiol' and '17beta-estradiol' should both be standardized to '17-Beta Estradiol.'

18. Consistent Expansion of Abbreviations and Hyphen Usage: Expand abbreviations consistently, ensuring that terms with or without hyphens are standardized in the same way. For example:
- 'FGF-2' and 'FGF2' should both be expanded to 'Fibroblast Growth Factor-2.'
- Maintain consistent usage of hyphens in similar terms. For example, if '4-hydroxy tamoxifen' is standardized as '4-Hydroxytamoxifen,' then '4-hydroxy-Tamoxifen' and '4-HydroxyTamoxifen' should also be standardized to '4-Hydroxytamoxifen'.
- 'IL-2' and 'IL2' should both be expanded to 'Interleukin-2.'
-For the non compound terms, remove the hyphen usages. for example, 'High-fat diet' should be converted as 'High Fat Diet'.
            
19. Control Formatting: Format control terms by placing 'Control' at the beginning and enclosing the specific condition or substance in parentheses, in this format `Control (xxx)`. Examples:
- `Empty Vector` becomes `Control (Empty Vector)`
- `ISO Control` becomes `Control (ISO)`
- `Water Control` becomes `Control (Water)`

20. Gene Modifications:
- Format genetic modifications as `Type: Gene`.
- Separate multiple genes with semicolons and follow nomenclature conventions.
- Examples:
- `Overexpression of Mouse PU.1` becomes `Overexpression: Mouse PU.1`
- `Silc1 KO` becomes `Knockout: Silc1`

21. Capitalization: Capitalize the initial word of each term, but leave connecting words (like 'and') lowercase.

22. Withdrawn Terms: Use the format `xxx Withdrawn` if the term includes the concept of withdrawal. Example: `Withdrawal of Doxycycline` becomes `Doxycycline Withdrawn`

23. Dosage Information: Remove all dosage and concentration information. Examples:
- `2% Cholesterol + Cholic Acid` becomes `Cholesterol + Cholic Acid`
- `MS-275 + Interferon Gamma` remains `MS-275 + Interferon Gamma`

24. Consistency for Similar Terms:
- Use standardized terms for similar expressions:
- `24 Hour Fast`, `24 Hour Fasted`, and `24 Hour Food Deprivation` all become `24 Hour Fasting`
- `Sleep Deprivation` and `Sleep Deprived` become `Sleep Deprived`
- `Stimulated` or `Stimulation` both become `Stimulated`
- `Activated or `Activation` both become `activated`.

25. Wildtype Notation: Convert any variations like `Wild-Type`, `WT`, and `Wild-Type Snai1` to `Wildtype`.

26. Vehicle Terms Simplification: Remove 'Vehicle' from vehicle terms, retaining only the substance name.
- Standardize vehicle-related terms consistently. Examples:
- `Corn Oil Vehicle` becomes `Corn Oil`
- `Oil Vehicle` becomes `Oil`

27. Treatment Formatting Examples: When treatments include multiple agents, separate them with `+` signs without additional details:
- `Dimethyl Sulfoxide in Corn Oil` becomes `Dimethyl Sulfoxide + Corn Oil`
- `DMSO + 6 Gray Ionizing Radiation` becomes `Dimethyl Sulfoxide + Ionizing Radiation`

28. Simplification and Removal of Non-Descriptive Terms: Remove non-descriptive terms or redundant descriptors:
- `Control of PU.1 Knockdown` simplifies to `Control (PU.1 Knockdown)`

29. Standardizing and Grouping Biological Terms: Group similar perturbations and describe them uniformly.
- Example:`Scramble`, `Scramble Control`, `Scramble shRNA`, `Scrambled siRNA` should all be standardized as `Scrambled`.

30. Handling Diet and Environmental Factors: Use simplified names for diet and environmental conditions:
- `Chow` and `Chow Diet` both become `Chow Diet`
- `Methionine Deficient Diet` becomes `Methionine Deficient`
- `28% Ethanol-Derived Calories + Doxycycline` becomes `Ethanol-Derived Calories + Doxycycline`

31. Treatment Conditions with Temperature: Format temperature exposures as `Exposure to [temperature]°C`:
- `37°C` becomes `Exposure to 37°C`
- `Activated at 39 C` becomes `Activated at 39°C`
            
32. Removal of Genotype Notation Symbols: Omit genotype notation symbols like -/-, +/-, KI from gene names in knockout or mutant terms to simplify.
Examples:
Wild-Type; Knockout: SHP2 -/- becomes Wildtype; Knockout: SHP2.
Wild-Type; Mutant: Htt KI becomes Wildtype; Mutant: Htt.
            
33.	Remove 'Model' from Transgenic Terms: Omit the word 'Model' in transgenic terms to simplify.
Example: Transgenic Model: Tg(CR1) becomes Transgenic: Tg(CR1)
            
34. Standardize Spelling Variations:Correct spelling variations to the most widely accepted form.
Example: Thioglycollate becomes Thioglycolate.
            
35. Standardize Polarization Terms:Convert terms like 'Polarizing Conditions' to 'Polarization' for uniformity.
Example: Th2 Polarizing Conditions becomes Th2 Polarization.

36. Standardize Stress-Related Terms: Consolidate various stress terms into the single term 'Stress'.
Examples: Stress Paradigm, Stress Induced, and Stressed all become 'Stress'.

37. Standardize Control Terms Starting with 'sh', 'si', or 'sg': Guideline: For terms like 'shControl', 'siControl', and 'sgControl', standardize them as 'Control (shRNA)', 'Control (siRNA)', and 'Control (sgRNA)', respectively.
Examples:
- 'shControl' becomes 'Control (shRNA)'
- 'siControl' becomes 'Control (siRNA)'
- 'sgControl RPP' becomes 'Control (sgControl RPP)'
- 'sgControl-CFP' becomes 'Control (sgControl-CFP)' 
            
38. Simplify Control Terms Involving Substances or Vehicles:
For control terms that mention substances or vehicles, format them as 'Control (Substance)' and remove redundant words like 'Solution' or 'Self Administration'.
Examples:
- 'Saline' becomes 'Control (Saline)'.
- 'Saline Solution' becomes 'Control (Saline)'.
- 'Saline Self Administration' becomes 'Control (Saline)'.
- 'Sesame Oil Control' becomes 'Control (Sesame Oil)'.
39. Consistency in Gene Symbol Capitalization: Maintain consistent capitalization of gene symbols according to species-specific conventions.
- For mouse genes, use all lowercase letters.
- For human genes, use all uppercase letters.                 
            
40. Standardize Temperature Notation: Always use the '°C' symbol for degrees Celsius.
Example: 'Activated at 37 Degrees Celsius' becomes 'Activated at 37°C'.

41. Miscellaneous Adjustments: Maintain consistency in names across records, using standard names or removing unneeded descriptors:
- `Exercise Training` becomes `Exercise`
- `Exosome` and `Exosomes` both become `Exosomes`
Apply these guidelines to ensure all perturbation terms follow the same pattern and are clear and consistent across entries.
                    
42. Standardization of Wound-Related Terms: Standardize terms referring to wounds or injury to 'Wounding' for consistency.
Examples:
Wound becomes Wounding.
Wounded becomes Wounding.
            
43. Use Descriptors for Diet Components:
Guideline: When diet terms specify component levels, use descriptors like 'High-' or 'Low-' to reflect significant variations.
Example: '20% Fat 1% Protein Diet' becomes 'High-Fat Low-Protein Diet'.           

44. Remove Dosage Information and Expand Abbreviations in Treatments: Eliminate dosage percentages and expand abbreviations when necessary.
Example: Streptozotocin + 5% DMSO becomes Streptozotocin + Dimethyl Sulfoxide.
           
45. Treat Complex Multi-component Terms as Single Terms:
Guideline: When a term includes multiple components connected by '+' or ';', treat the entire term as a single unit. Do not split these terms into separate components during standardization.

1). Usage of Symbols:     
- The '+' symbol is used to combine multiple agents or substances that are part of a single treatment.
- The ';' symbol is used to separate multiple genetic modifications or complex components within a single treatment term.
Examples:
- Combined Agents with '+':
'(-)-Bicuculline Methiodide + DL-Norepinephrin Hydrochloride + Carbamolylcholine Chloride + Dopamine Hydrochloride + Ascorbic Acid + Serotonin Hydrochloride' is treated as one single term.

'Aflibercept + AMG386 + Anti-PD1' is treated as one single term.

2). Multiple Genetic Modifications with ';'
- 'Conditional Knockout: Yap; Conditional Knockout: Taz; Cre: VE-cadherin-CreERT2' is treated as one single term.
- 'Conditional Knockout: Mst1; Conditional Knockout: Mst2; Cre: alb-CreF' is treated as one single term.
- 'Conditional Knockout: NIKdeltaT3flSTOP; Conditional Knockout: Notch2ICN; Cre: CD19Cre' is treated as one single term.

3). Implementation: Do not split these complex terms into separate components during the standardization process. Ensure that the entire term is kept intact to preserve the full context of the treatment.      
            
46. Standardize Capitalization for Perturbation Names: Keep the same format for the similar terms lile 'Doxorubicin' or 'doxorubicin' to 'Doxorubicin'.
- 'Chemotherapy' or 'chemotherapy to ‘Chemotherapy'.
- Always use Title Case for all Perturbation Names, regardless of their original format.
- Convert names to ensure that the first letter of each significant word is capitalized, while articles, conjunctions, and prepositions (e.g., 'of', 'and', 'in') remain in lowercase unless they begin the term.
47. For any "Placebo", it should be standardized as: "Vehicle Control".
So: Placebo → Vehicle Control
 
48. Perturbation Standardization Rule: Remove Dosage, Duration, and Administration Details.
When standardizing the Pert_name and generating the Standardized_Perturbation field, remove all dosage, duration, concentration units, or administration route descriptors. Retain only the core perturbation agent name (e.g., drug, compound, gene, etc.).
This includes removal of:
Concentration values (e.g., "3 µM", "10 ng/mL");
Time durations (e.g., "for 3 days", "24h");
Administration routes or context (e.g., "IV", "oral", "pulse", "co-treatment")
Units and qualifiers (e.g., "µM", "ng/mL", "hours", "daily").

for example:
Doxorubicin 3 µM for 3 days → Doxorubicin
Nintedanib 1 µM	→ Nintedanib
Paclitaxel 10 nM 24h → Paclitaxel
Tamoxifen (5 µM, 48 hours) → Tamoxifen
Radiation (5 Gy, 30 mins)	→ Radiation


49. Final Review and Correction: Final review the standardized drug treatment information to verify accuracy and address any remaining inconsistencies or errors. Make corrections as needed.            
            
50. Ensure all similar original terms are standardized consistently before providing the final outputs. Apply biological nomenclature standards and domain expertise for accuracy.
                
51. Formatting Guidelines: Ensure all drug names are presented in a standardized format. This includes using a consistent format for similar terms. Do not provide explanations in any format.
            
52. Create a table with two columns:

Column 1: List each original term separately.

Column 2: Provide the standardized Pert Name corresponding to each original term.

