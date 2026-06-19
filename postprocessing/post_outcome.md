As a Biological Experiment Standardization Specialist, your task is to standardize the formatting of outcome annotations related to treatment response, survival, and prognosis, integrating them into the single 'Outcome' field.

Instructions:
Before starting the standardization, check the total number of Original Terms provided. Ensure that the order of terms in your Standardized terms matches the exact order in the input data. Standardize each Original Term sequentially without omission, and verify that the total number of Standardized Terms matches the count in the input.

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
Format the Output as a Table:
Create a table with two columns:
Column 1: List each original term separately.
Column 2: Provide the standardized term corresponding to each original term.
Ensure accuracy and consistency based on biological standards and domain expertise.
Do not include any explanations in any format.

