Role: Sample Metadata

Annotate only the following fields for each GSM sample in this role:
SampleType, Specimen_Type, Race, Ethnicity, Age, Sex, Timepoint, Outcome. Do not annotate any other fields in this role.

First, annotate the 'SampleType' and 'Specimen_Type'. 'SampleType' is the broad, top-level classification of the sample (e.g., Patient Specimen, Cell Line, Organoid, etc.), while 'Specimen_Type' is a narrower annotation describing how the tissue or cells were obtained or cultured (e.g., Primary Tissue, PDX, Isolated Cells). If SampleType and Specimen_Type appear similar, annotate each field according to its own definition and scope. 
Use 'SampleType' to categorize the overall nature of the sample.

20. SampleType: Choose the most appropriate SampleType for the given data using the exact case-sensitive categories listed below. Ensure that your selection matches the categories exactly as written. Any variation (e.g., 'celllin', 'CELL LINE', or 'Cell Line') will be considered invalid.'
 'Step 1: Review the sample details: Consider the source, processing method, and context of the sample.'
 'Step 2: Select the appropriate category: Use the definitions, examples, and edge cases to choose the most accurate classification. Categories are mutually exclusive, so a sample should fit into only one type.'
(1). Patient Specimen
 'Definition: Biological material obtained directly from a human patient as part of a clinical, diagnostic, or therapeutic procedure. These specimens represent intact biological material (e.g., blood, biopsy tissue, cerebrospinal fluid).'
 'Examples:'
 ' - Blood collected from a cancer patient.'
 ' - Tumor biopsy from a breast cancer patient.'
 ' - Cerebrospinal fluid (CSF) from a lumbar puncture.'
(2). Patient-Derived Xenograft (PDX)
 'Definition: Tissue or tumors obtained from a human patient that are implanted into an animal model (e.g., mouse or rat). These models are often used to study human disease in a living organism.'
 'Examples:'
 ' - Human breast tumor implanted into a mouse.'
 ' - Patient-derived colon carcinoma in a rat model.'
(3). Cell Line
 'Definition: Immortalized or primary cells maintained in vitro as a reproducible, stable culture. Includes human, animal, or microbial cell lines.'
 'Examples:'
 ' - HeLa (human cervical cancer cell line).'
 ' - MCF7 (human breast cancer cell line).'
 ' - CHO cells (Chinese hamster ovary cell line).'
(4). Organoid
 'Definition: In vitro 3D culture systems that mimic tissue or organ architecture and function. These are advanced models often used to study development, disease, or host-pathogen interactions.'
 'Examples:'
 ' - Intestinal organoids derived from human stem cells.'
 ' - Brain organoids developed from pluripotent stem cells.'
 ' - Lung spheroids used for drug testing.'
(5). Primary Tissue
 'Definition: isolated tissue obtained directly from an organism (human, animal, or other), maintaining its structure and microenvironment.'
 'Examples:'
 ' - Mouse liver tissue for RNA extraction.'
 ' - Human lung tissue from cadaveric donors.'
 ' - Rat brain tissue for histology.'
(6). Isolated Cells
 'Definition: Specific cell populations isolated or enriched from tissues, blood, or fluids, often through techniques like density gradient centrifugation or cell sorting.'
 'Examples:'
 ' - PBMCs isolated from whole blood.'
 ' - Macrophages enriched from bronchoalveolar lavage fluid.'
 ' - Neurons dissociated from mouse brain tissue.'
(7). Fetus
 'Definition: Biological material, tissues, or cells collected directly from a developing fetus (human or animal). These samples are typically used for studying early developmental stages.'
 'Examples:'
 ' - Whole mouse fetus or human fetal tissue.'
 ' - Fetal brain, liver, or lung tissue.'
 ' - Placenta or amniotic fluid samples.'
- 'Understand how Fetus differs from other categories:'
 ' - Not Patient Specimen: Fetal samples are not obtained from a living patient for diagnostic purposes.'
 ' - Not Primary Tissue: Fetal samples represent a developmental stage distinct from 'adult' or 'post-natal' tissues.'
 ' - Not Isolated Cells: Whole fetal samples or tissues are intact and not isolated into specific cell types.'

Lastly, already refer to Edge Cases for further clarification.

Edge Cases for Sample Types:
(1). Patient Specimen vs. Isolated Cells:
 ' - Whole blood collected directly from a patient: Patient Specimen.'
 ' - PBMCs enriched from blood using Ficoll gradient centrifugation: Isolated Cells.'
(2). Patient Specimen vs. Primary Tissue:
 ' - Tumor biopsy from a patient: Patient Specimen.'
 ' - tissue from an animal or cadaver not tied to a clinical context: Primary Tissue.'
(3). Primary Tissue vs. Isolated Cells:
 ' - Whole mouse liver: Primary Tissue.'
 ' - Hepatocytes isolated from liver tissue: Isolated Cells.'
(4). Embryo vs. Embryonic Stem Cells (ESCs):
 ' - Whole embryo: Primary Tissue.'
 ' - ESCs cultured in vitro: Cell Line.'
(5). Organoid vs. Cell Line:
 ' - Brain organoids derived from human pluripotent stem cells: Organoid'
 ' - Standard 2D cell cultures: Cell Line.'
(6). Patient-Derived Xenograft (PDX):
 ' - Tumor tissue implanted in a mouse: PDX.'
 ' - Tissue harvested post-xenograft (still originating from the patient): PDX.'
(7). Fetal Cells Isolated from Fetal Tissue:
 ' - If cells are dissociated or enriched from fetal tissue, classify as Isolated Cells.'
(8). Fetal Organoid Cultures:
 ' - If cells from a fetus are used to create 3D organoid models, classify as Organoid.'
(9). Fetal ESCs:
 ' - Embryonic stem cells derived from a fetus are classified as Cell Line.'
 'Note: Placental tissue from a developing fetus is classified as Fetus, unless it is explicitly enriched into isolated cells.'

21. Specimen_Type: 
Use the 'Specimen_Type' field to categorize the biological source or model system used in a study. It provides clear and standardized descriptions of the specimen, ensuring consistency in annotation across diverse datasets (e.g., patient tissues, animal models, cell lines, and cultured systems). 
 Scope: 
 The field captures 'Directly obtained tissues', 'Cultured or engineered biological models', 'Cellular populations', 'Fetal samples'.

**The Specimen_Type Categories are: 
(1). Primary Tissue: Tissue obtained directly from an organism (human, animal, or other), either fresh or previously frozen, while maintaining its original structure and microenvironment.' 
 'Examples:' 
 'Human lung tissue from a cadaver' 
 'Mouse liver biopsy for RNA extraction'
  'Rat brain tissue for histology' 
 'Key Distinction: Not cultured; excludes PDX, organoids, or precision-cut tissue slices.'
(2). PDX (Patient-Derived Xenograft): Tissue or tumors obtained from a human patient that are implanted into an animal model (e.g., mouse, rat) for disease modeling and treatment studies.'  'Examples:' 
 'Human breast tumor implanted into a mouse' 
 'Patient-derived colon carcinoma in a rat model' 
 'Key Distinction: Implanted into animals; excludes directly isolated tissues (Primary Tissue) and cultured systems (Organoids, Tissue Culture).'
(3). Cell Line: Immortalized or primary cells maintained in vitro as stable, reproducible cultures. Includes human, animal, or microbial cell lines, embryonic stem cell lines, and induced pluripotent stem cells.' 
 'Examples:' 
 'HeLa (human cervical cancer cell line)' 
 'MCF7 (human breast cancer cell line)' 
 'CHO cells (Chinese hamster ovary cell line)' 
 'Key Distinction: 2D culture; excludes organoids (3D cultures) and tissue cultures.'
(4). Organoid: In vitro 3D culture systems that mimic tissue or organ architecture and function. Derived from stem cells or tissues.'
  'Examples:' 
 'Intestinal organoids derived from human stem cells' 
 'Brain organoids developed from pluripotent stem cells' 
 'Lung spheroids used for drug testing' 
 'Key Distinction: 3D structure; excludes monolayer cell lines and precision-cut tissue slices.'
(5). Isolated Cells: Specific cell populations isolated or enriched from tissues, blood, or fluids using techniques like density gradient centrifugation or cell sorting.' 
 'Examples:' 
 'PBMCs isolated from whole blood' 
 'Macrophages isolated from bronchoalveolar lavage fluid' 
 'Dissociated neurons from mouse brain tissue' 
 'Key Distinction: Individual cell populations; excludes whole tissues (Primary Tissue) and cultured systems (Cell Line, Organoid).'
(6). Fetus: Biological material, tissues, or cells collected directly from a developing fetus (human or animal).'
  'Examples:' 
 'Fetal brain tissue from a mouse' 
 'Human placenta or amniotic fluid' 
 'Whole mouse fetus used for analysis' 
 'Key Distinction: Fetal origin; excludes adult tissues, isolated cells, or cultured systems.'
(7). Tissue Culture: Tissue sections cultured ex vivo under controlled conditions, often used to study tissue responses while retaining original architecture.'
  'Examples:' 
 'Precision-cut liver tissue slices cultured for 48 hours'
  'Cultured skin tissue for drug toxicity assays' 
 'Key Distinction: Cultured ex vivo tissue; excludes organoids (3D stem cell-derived) and cell lines (immortalized cultures).'
(8). NA 
 'Definition: No specimen information is available.' 
 'Examples:' 
 'No description of specimen provided'
**Additional Rules for Resolving Overlaps or Ambiguities: 
(1). Primary Tissue vs. Tissue Culture 
 'Rule: If the tissue is directly obtained (fresh or previously frozen) without ex vivo culture, annotate as Primary Tissue. If the tissue is cultured ex vivo, annotate as Tissue Culture.'  'Example:' 
 'Mouse liver tissue directly used for RNA-seq' → 'Primary Tissue' 
 'Precision-cut liver tissue slices cultured for 24 hours' → 'Tissue Culture'
(2). Cell Line vs. Organoid 
 'Rule: If the sample is an immortalized 2D culture, annotate as Cell Line. If it is a 3D culture mimicking organ structure, annotate as Organoid.' 
 'Example:' 
 'MCF7 breast cancer cells grown in vitro' → 'Cell Line' 
 'Intestinal organoids for disease modeling' → 'Organoid'
(3). Primary Tissue vs. PDX 
 'Rule: If the tissue is directly isolated from a patient or organism, annotate as Primary Tissue. If it has been implanted into an animal host, annotate as PDX.' 
 'Example:'  'Human colon biopsy' → 'Primary Tissue' 
 'Human tumor implanted into a mouse model' → 'PDX'
(4). Isolated Cells vs. Primary Tissue 
 'Rule: If specific cells have been isolated or enriched, annotate as Isolated Cells. If the sample retains tissue integrity, annotate as Primary Tissue.' 
 'Example:'
  'PBMCs isolated from blood' → 'Isolated Cells' 
 'Freshly obtained human liver tissue' → 'Primary Tissue'
(5). Tissue Culture vs. Organoid 
 'Rule: If the culture involves thin tissue slices or ex vivo tissues, annotate as Tissue Culture. If it is a 3D structure grown to mimic organ architecture, annotate as Organoid.' 
 'Example:' 
 'Precision-cut lung slices in culture' → 'Tissue Culture' 
 'Lung organoids for drug screening' → 'Organoid'
                
Lastly, here are the final notes for annotations: 
(1) 'Always Prioritize Specificity: Always annotate using the most specific category.' 
(2) 'Apply Resolution Rules: Use the provided overlap rules to resolve ambiguous cases.' 
(3) 'Document Unusual Cases: If you use Other or NA, note why it was chosen if possible.' 
(4) 'Consistency: Ensure consistent usage across all samples to avoid misclassification.'

 Next, annotate Race and Ethnicity. First of all, here is the Race vs. Ethnicity Distinction.
- At a high level, Race refers to broad categories based on shared physical or social traits (e.g., ‘White,’ ‘Black or African American,’ ‘Asian’), while Ethnicity focuses on cultural, national, religious, or linguistic identity (e.g., ‘Hispanic,’ ‘Han’).
- In GEO metadata, you may occasionally see ‘ethnicity: African American’ or ‘ethnicity: Han,’ but these are more accurately annotated as Race: 'Black or African American' (with Ethnicity: 'Not Specified') or Race: 'Asian' (with Ethnicity: 'Han'), respectively. If you find a Race descriptor incorrectly placed under ‘Ethnicity,’ re-map it to the Race field and mark Ethnicity as appropriate (e.g., ‘Not Specified’).
- Key Note on 'Not Specified' vs. 'NA'.
'Not Specified' is used only for Patient Specimen samples when relevant information (Race or Ethnicity) is missing or not provided.
'NA' is used for samples that do not originate from a patient (e.g., cell lines, organoids, animal tissues), where Race/Ethnicity simply does not apply.

22. Race: 
Use the 'Race' field to classify Patient Specimen samples into one of the U.S. Census Bureau race categories or related terms provided. Race refers to broad population groups often defined by physical characteristics and geographic ancestry. If no information is available or the sample is not a Patient Specimen, follow the rules below.
(1). Applicability:
 - Annotate 'Race' only if SampleType is 'Patient Specimen'.
 - If SampleType is not 'Patient Specimen' (e.g., 'Cell Line', 'Organoid'), annotate 'NA'.
(2). Determining Race:
 - Refer to GSE-level metadata first. If a single race is stated for all Patient Specimens, apply that category uniformly.
 - If multiple races are mentioned at the GSE level, check GSM-level metadata for sample-specific race information.
 - Use the category that most closely matches the provided race information. If a population does not neatly fit into one of the categories below, annotate as 'Not Specified' or provide the closest equivalent with additional specificity if possible. When you see synonyms or older terms like Caucasian, map them to ‘White’; African American or African descent → ‘Black or African American’; Han → ‘Asian’.
(3). Categories:
Use these exact case-sensitive categories whenever possible:
 - 'American Indian or Alaska Native'
 - 'Asian'
 - 'Black or African American'
 - 'Hispanic or Latino'
 - 'Native Hawaiian or Pacific Islander'
 - 'White'
 - 'Two or More Races'
 - 'Not Specified'
 - 'NA' (for non-Patient Specimen samples)
(4). Missing or Ambiguous Race:
 - If no race information is available for a Patient Specimen, annotate as 'Not Specified'.
 - For non-Patient Specimen samples, annotate as 'NA'.
 - If the metadata suggests a specific race not listed, provide the closest category and if unclear, 'Not Specified'.
(5). Examples:
Scenario 1: GSE Info: 'All patients are of European ancestry' → Closest category: 'White'.
 GSM001 (Patient Specimen): Race: White
 GSM002 (Cell line): Race: NA (since not a Patient Specimen)
Scenario 2: GSE mentions multiple donors: African, European, and Mixed.
 Map 'African' to 'Black or African American', 'European' to 'White', and if a donor is described as mixed ancestry from multiple categories, use 'Two or More Races'.
 GSM001 (Patient Specimen, African donor): Race: Black or African American
 GSM002 (Patient Specimen, European donor): Race: White
 GSM003 (Patient Specimen, described as mixed from multiple groups): Race: Two or More Races
Scenario 3: No race data at GSE or GSM level.
 GSM001 (Patient Specimen): Race: Not Specified
 GSM002 (Organoid): Race: NA

23. Ethnicity: 
Use the 'Ethnicity' field to capture cultural, national, religious, or linguistic affiliations that distinguish groups such as 'Hispanic' or 'Non-Hispanic'.
 (1). Applicability:
 - Only annotate 'Ethnicity' if SampleType is 'Patient Specimen'.
 - If SampleType is not 'Patient Specimen', annotate 'NA'.
 (2). Determining Ethnicity:
 - Check GSE-level metadata: If all Patient Specimens are of a single ethnicity, apply that to all.
 - If multiple ethnicities are mentioned, refer to GSM-level metadata for sample-specific details.
 - If the original GEO labeling incorrectly uses Ethnicity for Race (e.g., ethnicity: African American), reassign appropriately to the Race field, and set Ethnicity to ‘Not Specified’ if no true ethnic descriptor is given.
 (3). Categories:
 - Basic categories: 'Hispanic', 'Non-Hispanic', 'Not Specified', 'NA'.
 - If more specific ethnic details are provided (e.g., 'Asian-Han Chinese', 'Asian: Indian'), annotate them as given to maintain specificity.
 (4). Missing or Ambiguous Ethnicity:
 - If no ethnicity information is available for a Patient Specimen, use 'Not Specified'.
 - For non-Patient Specimen samples, use 'NA'.
 (5). Examples:
 Scenario 1: GSE Info: 'All European samples are Non-Hispanic'.
 GSM001 (Patient Specimen): Ethnicity: Non-Hispanic
 GSM002 (Cell line): Ethnicity: NA
 Scenario 2: GSM Info shows a donor listed as Hispanic.
 GSM001 (Patient Specimen): Ethnicity: Hispanic
 Scenario 3: No ethnicity mentioned.
 GSM001 (Patient Specimen): Ethnicity: Not Specified
 GSM002 (Organoid): Ethnicity: NA

 (6). Summary of 'Not Specified' vs. 'NA'
- Not Specified: Used for Patient Specimen samples when the metadata lacks race or ethnicity details.
- NA: Used for samples not derived from a patient (e.g., cell lines, organoids, animal models).

24. Age: 
Age records the exact age of the sample source with numeric values and standardized units, avoiding any inference or assumption.
(1). Capturing Age
- Record numeric age only if the metadata explicitly states it as age. For example: 'age: 25', '25 years old', or 'age: 6 Months.'
- Do not use numeric fields that simply appear in the GSM record but are unrelated to age (e.g., sample numbers, replicate IDs, 'Birthweight: 580 Grams').
- Include units in the final annotation: '25 Years', '6 Months', '7 Days', '5 Hours'.
- Leave a space between the number and the unit (e.g., 8 Days, 20 Years).
- Do not use 'old' or other variations; maintain the strict Number + Unit format.
- If no numeric age is provided or it cannot be confirmed from the metadata, annotate as NA.
- If age does not apply (e.g., a cell line or organoid sample), annotate as NA.
(2) Important Notes
- Confirm that the numeric value truly refers to age in the GSM/GSE description. Any numeric entry lacking explicit mention of 'age,' 'years,' 'months,' etc. must not be assumed to be age.
- Allowed units: 'Years', 'Months', 'Days', 'Hours.'
- Avoid abbreviations like 'yrs,' 'mos,' 'hr.'
- Do not infer age from file names or sample IDs.
- If the numeric value references 'bmi' or any other measurement (e.g., 'sample #' or numerical values from the titles), you must not conflate it with age.
Do not use treatment duration, culture duration, differentiation duration, or timepoint information as biological age.

25. Sex
                 'Sex' must be accurately extracted, annotated, and standardized based on the GSE summary, overall design, and GSM-specific metadata.
                 The annotations should reflect the study's experimental design and the terminology used in the metadata.
                
                 (1). Where to Extract Sex Information:
                 'GSE Overall Design and Summary': Look for explicit mentions of Sex in the study-level description. Examples include '72 males and 72 females' or 'Male mice treated with PBS', or references to Sex-specific biological processes like 'Effects of testosterone in males'.
                 'GSM-Specific Metadata': Search for explicit sex mentions in sample-level fields. For instance, 'Sex: Male' or ' Sex: Female'. Sex may also appear indirectly, such as 'pregnant' or 'ovarian cancer patient' (implying 'Female') or 'patient with prostate enlargement' (implying 'Male').
                 'Implicit Sex Clues': If not explicitly stated, infer sex from biological or experimental context. For example, 'ovarian tissue' implies 'Female', 'prostate tissue' implies 'Male', and 'pregnant' implies 'Female'. If no inference is possible, use 'Unknown'.
                
                 (2). Strategy for Extracting and Annotating Sex:
                 Step 1: Parse the GSE Summary and Overall Design. If the GSE states something like '72 male', annotate sex as 'Male'. If it states 'samples collected from females', annotate as 'Female'. Standardize all explicitly mentioned sex.
                 Step 2: Parse GSM Metadata. Look for explicit fields like 'Sex: M' or 'Sex: F' and map them to 'Male' or 'Female'. If only abbreviations or indirect clues are given, interpret them accordingly.
                 Step 3: Infer Sex When Necessary. Use tissue type or experimental context if direct mentions are absent. If no inference is possible, use 'Unknown'.
                 Step 4: Standardize Sex Information. The final annotation should be 'Sex: Male', 'Sex: Female', 'Sex: Unknown', or if not applicable (e.g., for cell lines without donor info), 'Sex: NA'. If 'Sex: Not Specified', use 'Sex: NA'.
                
                 (3). How to Handle Sex for Cell Lines:
                 In general, cell lines are not sex-specific, so annotate 'Sex: NA'.
                 If donor information is provided, use it to assign 'Male' or 'Female'. If the cell line originates from ovarian carcinoma, 'Female'; from prostate carcinoma, 'Male'. If multiple donors of different sex were used to create a hybrid cell line, annotate 'Sex: Mixed'.

                 (4). Examples:
                 Example 1: A cell line 'A549' (lung carcinoma, no sex info): 'Sex: NA'.
                 Example 2: A cell line 'HeLa' derived from a female cervical carcinoma: 'Sex: Female'.
                 Example 3: A cell line 'LNCaP' (prostate carcinoma): 'Sex: Male'.
                 Example 4: A hybrid cell line from male and female donors: 'Sex: Mixed'.
 
26. Timepoint
 Annotate and standardize timepoint information from GEO metadata.
 Identify when a sample was collected relative to events, stages, or factors.
Timepoints can be 'NA' if no time dimension applies (e.g., purely cross-sectional data with no mention of collection timing). Always verify that any 'Day X' or 'Week X' matches the GSE-level conventions (e.g., '7 days post-inoculation' → 'Post-inoculation Day: 7').

 Potential Timepoint Types:
(1). Pre/Post-Event: Defined relative to a key event, such as inoculation, treatment, surgery, or drug administration. (for example, Pre-treatment Day: -1, Post-treatment Hour: 24; Post-surgery Week: 2)
(2). Developmental: Based on the biological or developmental stage of the organism. (for example, Gestational Day: 14; Postnatal Day: 7; Embryonic Day: 10)
(3). Chronological: Absolute time markers, often tied to the experimental design (Day: 7; Week: 2; Month: 1)
(4). Follow-Up: Used in longitudinal or clinical studies to indicate repeated measurements.
Examples: (Baseline; Follow-Up Month: 3; Follow-Up Year: 5)
(5). Event-Driven: Associated with external stimuli or interventions. (Post-inoculation Day: 14; Post-challenge Hour: 4)
(6). Behavioral/Physiological: Defined by symptoms or biological responses. (First Symptom Day; Onset of Fever)
(7). Cyclic/Rhythmic: Relevant for circadian rhythm studies or periodic sampling. (Circadian Phase: ZT12; Diurnal Hour: 16)
(8). Age-Based: Biological age of the subject used explicitly or inferred as a timepoint. (Age: 12 Weeks)

Lastly, please follow the following Strategies for Annotating Timepoints:
Step 1: Review GSE Overall Design and Summary
- Look for explicit descriptions of timepoints in the study design (e.g., 48 samples collected at 7, 14, and 28 days post-inoculation). 
- Define standardized terms for timepoints based on this overview: 
Example: 
7 days post-inoculation → Post-inoculation Day: 7
14 days post-inoculation → Post-inoculation Day: 14
Step 2: Parse Individual GSM Metadata
- Examine individual sample metadata fields (e.g., timepoint, day, dpi) to extract timepoint information. 
- Examples: 
GSE overall summary says  48 samples collected at 7, 14, and 28 days 'post-inoculation'). And specific GSM Metadata includes  timepoint: D7 → Annotation: Post-inoculation Day: 7
GSM Metadata: timepoint: baseline → Annotation: Baseline
For missing or ambiguous timepoints, infer from replicates or GSE-level descriptions, or label as unknown. 
 
Step 3: Standardize Timepoint Information
Map all extracted timepoints to a consistent format: 
[Context] [Unit]: [Value] 
Examples: 
7 days post-inoculation → Post-inoculation Day: 7
14 days post-treatment → Post-treatment Day: 14
Step 4: Address Age-Related Timepoints
When timepoints can be derived from age: 
Example: 
Baseline age: 12 weeks
Timepoint: 14 days post-inoculation
Effective age: 14 weeks
 If no timepoint or it is truly not relevant, annotate ‘NA.’
  If ambiguous or missing: 'NA'.

27. Outcome
 'The Outcome field is a unified annotation field designed to capture all relevant treatment-related and prognostic outcomes for both patient-level and cell line data. It provides a structured and standardized way to represent treatment response, survival status, and prognosis information in a single, parsable format.'
 The Outcome field integrates three components (if available): 'Response', 'Survival', and 'Prognosis'.
(1). Response:
 'Describes the subject's or sample's response to treatment.'
 - For patients:
 'Responder': Complete remission or significant response.
 'Partial Responder': Partial remission or partial improvement.
 'Stable Disease': No progression or improvement.
 'Non-Responder': Disease progression or no response.
 'Unknown': Ambiguous or unclear response.
 - For cell lines:
 'Sensitive': Effective response (e.g., growth inhibition).
 'Partially Sensitive': Moderate or partial response.
 'Resistant': No response or lack of inhibition.
 'Unknown': Ambiguous or unclear response.
(2). Survival:
 'Represents survival data for patients, including survival time and status.'
 Format: '[Survival_Time]: [Status]'
 'Survival_Time': Duration reported in months (preferred) or years.
 'Status': 'Alive', 'Deceased', or 'Unknown'.
 Example: '36 Months: Alive', '12 Months: Deceased'.
 If sample is from a living patient but no survival data is provided, annotate 'Unknown'. If it’s a cell line or purely animal model with no survival aspect, use 'NA'.

(3). Prognosis:
 'Provides the predicted clinical outcome for the patient based on available metadata.'
 Possible values:
 'Good Prognosis': Favorable or low-risk outcome expected.
 'Poor Prognosis': Unfavorable or high-risk outcome expected.
 'Unknown': Prognosis unclear or not reported.

 (4) Combining Multiple Aspects:
You may combine Response, Survival, and Prognosis in the same cell by separating them with semicolons.
Example: Responder; 36 Months: Alive; Good Prognosis

 (5) Outcome Annotation Examples:
Below are example scenarios demonstrating how to annotate Response, Survival, and Prognosis within the Outcome field for both patient-level and cell-line samples. Each scenario provides a short description of the sample’s situation, followed by the recommended Outcome Annotation.
*Patient-Level Examples:*
Scenario: Complete remission, survived 36 months
Outcome Annotation: Responder; 36 Months: Alive
Scenario: Partial remission, survived 24 months
Outcome Annotation: Partial Responder; 24 Months: Alive
Scenario: Disease progression, deceased at 12 months
Outcome Annotation: Non-Responder; 12 Months: Deceased
Scenario: Stable disease, no survival or prognosis
Outcome Annotation: Stable Disease
Scenario: Poor prognosis only
Outcome Annotation: Poor Prognosis
Scenario: Ambiguous response, unclear status
Outcome Annotation: Unknown
Patient Scenario with No Outcome Data Provided
Outcome: Unknown

*Cell Line Examples:*
Scenario: Sensitive to treatment, no survival/prognosis data
Outcome Annotation: Sensitive
Scenario: Partial sensitivity to treatment
Outcome Annotation: Partially Sensitive
Scenario: Resistant to treatment
Outcome Annotation: Resistant
Scenario: Ambiguous response
Outcome Annotation: Unknown
Scenario: No treatment outcome
Outcome Annotation: NA
