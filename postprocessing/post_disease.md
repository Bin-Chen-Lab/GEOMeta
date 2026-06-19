## Disease Standardization Prompt

## Role
As a physician and medical domain expert, your task is to revise the given terms to ensure consistency, eliminate formatting variations, and group similar disease terms under standardized diagnostic categories. You are expected to align disease terminology with the ICD-10-CM 2025 coding standards and reference biomedical ontologies such as ICD 10 codes. Follow each rule below carefully.

## General Instructions
- Count the total number of original terms before standardization.
- Preserve the original order of terms.
- Do not skip, reorder, duplicate, or merge rows.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- If a disease cannot be mapped to a recognized clinical entity and lacks specificity, annotate as `NA`.

## Standardization Rules

### 1. Match Disease Labels to ICD-10-CM 2025 When Possible
- Primary Mapping: Use the exact ICD-10-CM 2025 disease term if available. These terms take precedence over synonyms or local labels.
- Fallback Mapping: When an exact match does not exist, use the closest medically appropriate ICD-compatible term. Prioritize terms found in ICD code.
- Deduplication: If multiple terms map to the same ICD concept, normalize them to a single canonical form to eliminate redundancy.
- Refer to: https://www.icd10data.com/ for authoritative term lookup.

### 2. General Guidelines:
Capitalize the first letter of each disease name.
If a disease cannot be mapped to a recognized ICD entity and lacks clinical specificity, annotate as NA.
Structure severity or status descriptors within parentheses. (e.g., Resolved, Severe, Mild).
Prefer atomic, discrete disease entities. Avoid bundled or compound descriptions unless medically standard.

### 3. Retain Clinically Meaningful Adjectives Based on ICD:
Retain modifiers such as Acute, Chronic, Aggressive, Advanced, Adult only when they reflect clinically recognized and meaningful subtypes as defined by ICD-10.
1) Retain when clinically meaningful:
Acute Myeloid Leukemia, Acute Pancreatitis, Acute Myocardial Infarction, Acute Kidney Injury,
Acute Rejection, Acute Respiratory Distress Syndrome
Chronic Hepatitis B → Chronic Hepatitis B Virus Infection
Chronic viral hepatitis C → Chronic viral hepatitis C (ICD code: B18.2)
Hepatitis B Virus Infection (Chronic) → Chronic Hepatitis B Virus Infection
Aggressive NK Cell Leukemia
Adult T-Cell Leukemia/Lymphoma

2). Remove generic or temporal descriptors that are not ICD-recognized disease entities:
Acute Decompensation → Decompensation
Acute Cholestasis → Cholestasis
Acute Coronary Syndrome → Coronary Syndrome (unless broader context justifies)
Chronic viral hepatitis → Chronic viral hepatitis (ICD code: B18)

### 4. Remove Non-Standard Suffixes or Codes: Eliminate any appended codes, symbols, or suffixes that do not contribute to the medical description.
Examples:
Abdominal Aortic Aneurysm+A2 → Abdominal Aortic Aneurysm
Adenocarcinoma (No Special Type) → Adenocarcinoma
Adenoma/MIN → Adenoma and Mucosal Invasive Neoplasia

### 5. Expand Abbreviations to Full Terms: Replace commonly used abbreviations with their full descriptive terms to avoid ambiguity.
Examples:
AV Stenosis → Atrioventricular Stenosis
STZ Diabetes → Streptozotocin-Induced Diabetes

### 6. Correct Capitalization of Species Names: Ensure that genus names are capitalized and species names are lowercase as per scientific nomenclature.
Examples:
Chlamydia Trachomatis Infection → Chlamydia trachomatis Infection
Cryptococcus Neoformans Infection → Cryptococcus neoformans Infection
Salmonella Infection → Salmonella enterica Infection

### 7. Use Singular or Plural Forms Appropriately: Standardize terms to use singular or plural forms consistently, based on common medical usage.
Examples:
Actinic Keratoses → Actinic Keratosis
Autism Spectrum Disorders → Autism Spectrum Disorder 
Anxiety Disorder → Anxiety Disorders
Depressive Disorders → Depressive Disorder
Anxiety Disorder  → Anxiety Disorders
Cardiovascular Disease  → Cardiovascular Diseases
 
### 8. Map to Standardized Medical Terms: Substitute non-standard or outdated terms with current, widely accepted medical terminology.
Examples:
Autism → Autism Spectrum Disorder
Acetaminophen-Induced Liver Injury → Acetaminophen-Induced Hepatotoxicity
Concentric Hypertrophy → Cardiac Hypertrophy
Hepatocarcinoma → Hepatocellular Carcinoma
Acne  →  Acne Vulgaris

### 9. Standardize Hyphenation and Capitalization: Ensure proper hyphenation and capitalization for compound terms to maintain grammatical correctness.
Examples:
House Dust Mite Induced Asthma → House Dust Mite-Induced Asthma
Spinal And Bulbar Muscular Atrophy → Spinal and Bulbar Muscular Atrophy
Cardiomyocyte-Specific Adult Notch Gain-Of-Function → Cardiomyocyte-Specific Adult Notch Gain-of-Function

### 10. Replace Slashes with 'and' for Clarity: When terms are separated by slashes indicating combination or dual conditions, replace with 'and' for better readability.
Examples:
Adenoma/MIN → Adenoma and Mucosal Invasive Neoplasia
Pre-B Acute Lymphoblastic Leukemia / Pre-B Cell Leukemia → Pre-B Cell Acute Lymphoblastic Leukemia

### 11. Rephrase Terms to Align with Standard Nomenclature: Re-arrange or re-phrase words in the term to match standard medical nomenclature conventions. 
Examples:
H1N1 Influenza → Influenza A (H1N1)
H9N2 Influenza A Virus Infection → Influenza A (H9N2) Virus Infection
Prostate Cancer Metastasis → Metastatic Prostate Cancer

### 12. Specify Subtypes When Necessary: When diseases have subtypes, specify them accurately to enhance clarity and precision.
Examples:
Charcot-Marie-Tooth Disease Type 1A → Charcot-Marie-Tooth Disease Type 1A
Charcot-Marie-Tooth Disease Type 2A → Charcot-Marie-Tooth Disease Type 2A
LCMV Armstrong Infection → Lymphocytic Choriomeningitis Virus Armstrong Strain Infection

### 13. Replace General Terms with Specific Ones: Substitute broad or vague terms with more specific medical diagnoses to improve accuracy.
Examples:
Colon Cancer, Colon Carcinoma, Colon Tumor, Colon Tumorigenic Carcinoma → Colon Adenocarcinoma
Gastric Squamous-Columnar Junction Cancer → Gastric Junction Carcinoma

### 14. Use Appropriate Noun Forms: Convert adjectives or other forms to appropriate noun forms when standardizing disease names.
Examples:
Epileptic → Epilepsy
Pre-Malignant → Premalignant

### 15. Combine Related Terms for Standardization: When multiple related terms exist, standardize to a single comprehensive term to avoid duplication.
Examples: 
Autism Spectrum Disorders and Autism → Autism Spectrum Disorder
Pre-B Acute Lymphoblastic Leukemia and Pre-B Cell Leukemia → Pre-B Cell Acute Lymphoblastic Leukemia

### 16. Eliminate Redundant Terms: Remove repetitive or unnecessary words to streamline terminology.
Examples: 
Colitis-Associated Cancer and Colitis-Associated Colon Cancer → Colitis-Associated Colorectal Cancer

### 17. Replace Specific Terms with Standard Terms When Necessary: Substitute terms that are too specific or technical with standardized medical terminology if appropriate, or retain them if they are standard.
Examples:
Tagged-Cyclin D1 RAS/DNP53-Driven Tumor → Tagged Cyclin D1 RAS/DNP53-Driven Tumor (no change needed)
Prion Infection → (No change needed if no standard term exists)
            
### 18. Categorize Similar Terms Under Broader Categories with Specifics in Parentheses: For similar terms, map to a broader category and specify the subtype inside parentheses.
Examples:
Low Grade Glioma → Glioma (Low-grade)
High Grade Glioma → Glioma (High-grade)
Triple-Negative Breast Cancer → Breast Cancer (Triple-negative Breast Cancer)
HER2+ Breast Cancer → Breast Cancer (HER2+)

### 19. Capitalize Each Initial Word Unless Specifically Lowercased: Capitalize the first letter of each major word in the term, unless the term requires lowercase letters for specific parts, such as species names.

### 20. Other rules to follow:

Dermal fibrosis → Skin fibrosis
Influenza A (H9N2) Virus Infection → Influenza A (H9N2)
Influenza A → Influenza A Infection
Late Carcinoma → Late-stage carcinoma
Lupus → Systemic Lupus Erythematosus
Mouse Cytomegalovirus Infection → Cytomegalovirus Infection
Murine Melanoma → Melanoma
Mammary Carcinoma → Breast Carcinoma
Mammary Gland Tumor → Breast Tumor
Mammary Sarcoma → Breast Sarcoma
NA → NA

### 21. Normalize Abbreviations and Synonyms: Replace well-known medical acronyms with full clinical terms:
For example, ANCA → Antineutrophilic Cytoplasmic Antibody Vasculitis

### 22. Merge Synonymous or Hierarchically Related Leukemia Terms: Use ICD-based alignment to standardize related hematologic malignancies:

Acute Lymphoblastic Leukemia (Childhood) → Acute Lymphoblastic Leukemia
Acute Mononuclear Cell Leukemia → Acute Monocytic Leukemia
Acute Myeloblastic Leukemia → Acute Myeloid Leukemia
Acute Myelogenous Leukemia → Acute Myeloid Leukemia

### 23. For multiple diseases or co-morbid conditions, replace separators like ";" or the word “with” with the symbol "+". Left a space in front and after the "+". E.g., "Alzheimer's Disease; Cerebral Amyloid Angiopathy" → "Alzheimer's Disease + Cerebral Amyloid Angiopathy"

### 24. Remove informal or vague modifiers such as "like". Recast terms: "Basal-Like Breast Cancer" → "Breast Cancer (Basal)"

### 25. For in situ, in vivo etc. conditions, remove the "In Situ" or "In Vivo" for generalization: "Breast Ductal Carcinoma In Situ" → "Breast Ductal Carcinoma"

### 26. Normalize castration-related terms: "Castration-Resistant Prostate Cancer" → "Prostate Cancer (Castrate-Resistant)"

### 27. Normalize healthy control terms: any variation of "Healthy Control", "Control (donor)", etc. → "Healthy" or "NA" if context demands

### 28. Unify tumor/cancer terminology: "Head and Neck Tumor" → "Head and Neck Cancer"; "Hepatobiliary Tumor" → "Hepatobiliary Cancer"

### 29. Normalize viral infection terminology: "Hepatitis A" → "Hepatitis A Virus Infection", "Hepatitis E" → "Hepatitis E Virus Infection"

### 30. For overexpression or amplification, represent it as subtype: "Her2 Overexpression Breast Cancer" → "Breast Cancer (HER2+)"

### 31. Eliminate Formatting Inconsistencies: Standardize disease labels to eliminate variation in hyphenation, capitalization, and spacing.
Acceptable form: use Nonalcoholic only, NOT "Non-Alcoholic" or "Non-alcoholic".
Non-Alcoholic Steatohepatitis →  Nonalcoholic Steatohepatitis
Non-alcoholic Fatty Liver Disease →  Nonalcoholic Fatty Liver Disease

Multiple co-occurring conditions: separate by +, not ;
"Nonalcoholic Fatty Liver Disease; Nonalcoholic Steatohepatitis" → "Nonalcoholic Fatty Liver Disease + Nonalcoholic Steatohepatitis"

### 32. Handle Resolved or Severity Modifiers: Use structured ICD-like phrasing for resolved or severity-modified diseases:
Resolved cases:
Resolved Hepatitis B →  Hepatitis B Virus Infection (Resolved)
Severity levels:
Severe Alcoholic Hepatitis → Alcoholic Hepatitis (Severe)
Mild Acute Pancreatitis → Acute Pancreatitis (Mild)

### 33. Once completed, provide the structured table with two columns: 'Original_Term' and 'Standardized_Term'. Keep a concise annotation only. Don't provide any explanations in any forms.
                                  
## Output Format
Return only a structured table with two columns:
Column 1: List each original term separately.
Column 2: Provide the standardized term corresponding to each original term.
Ensure accuracy and consistency based on biological nomenclature standards and domain expertise.
