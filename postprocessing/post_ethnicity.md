Agent task: Ethnicity standardization

Standardize the `Ethnicity` field according to the rules below. Preserve the input order and return one standardized term and one broad category for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules
1. Avoid Ambiguity: Use terms that are clear and recognized by major institutions or governments. For instance, terms like 'Caucasian' should be standardized to 'White,' as this is the more widely accepted term in scientific and demographic contexts.

2. Avoid Multiple Descriptions: When multiple ethnic groups are described in a single term (e.g., 'Hispanic, Latino or Spanish Origin'), standardize the term to the most commonly used version, such as 'Hispanic or Latino.'

3. Ethnic Subgroup Clarity: Specify ethnic subgroups when needed but keep them standardized. For example, 'Chinese Han' should be standardized to 'Han' to maintain clarity and avoid overcomplication.

4. Missing and Unknown Information:
- Retain `NA` when the original term is `NA` or when no ethnicity information is available.
- Use `Unknown` when the original term explicitly indicates that ethnicity is unknown, unspecified, or not reported.
- Do not interchange `NA` and `Unknown`.

5. Groupings Based on Region: For ethnicities defined by geographic regions, standardize the names of the regions and ethnic groups, e.g., 'East African (Kenya)' should be standardized as 'East African'. The specific country names should be omitted unless they are necessary for clarity.

6. Consistency in 'Hispanic' Terms: Ensure that 'Hispanic,' 'Latino,' or 'Spanish Origin' are standardized consistently as 'Hispanic or Latino.' Do not use multiple variants in the same dataset.

7. Standardize National Terms: Where ethnic groups are identified by nationality, use the common standardized names. For example, 'British Indian' should become 'Indian,' and 'South Asian (Pakistan)' should be standardized as 'South Asian.'

8. Avoid Unnecessary 'Non' Prefixes: Terms such as 'Non-Hispanic' or 'Non-Hispanic, Latino or Spanish Origin' should be replaced with 'Not Hispanic or Latino.'

9. Retain Common Groupings: Terms like 'African American,' 'European American,' and 'White British' should be standardized according to common terminology. For example, 'African American' remains 'African American,' 'White' can be used for 'Caucasian' or 'White British.'

10. Ensure Consistency in Mixed Group Terms: For terms like 'Mixed' or 'Multi-racial,' standardize them to 'Mixed.' Do not use overly broad terms like 'Any other ethnic group.'

## Rules for the ‘Broad_Category’:
1). Choose exactly one of:  
  ‘American Indian or Alaska Native’, ‘Asian’, ‘Black or African American’,  
  ‘Hispanic or Latino’, ‘Native Hawaiian or Pacific Islander’, ‘White’,  
  ‘Two or More Races’, ‘Unknown’, ‘NA’.
2). Map logically (e.g., ‘Uyghur’ → Broad_Category = ‘Asian’).  
3). If Standardised Term = ‘Mixed’ or describes >1 OMB group, set Broad_Category = ‘Two or More Races’.  
4). If Standardised Term = ‘Unknown’ or ‘NA’, set Broad_Category = same value.

## Output Requirements
Return exactly one standardized term and one Broad_Category for each original term.
Do not include explanations or additional commentary.
            
## Output Examples:
Original Term	  |Standardized Term	|Broad_Category
African American  |African American	|Black or African American
Any other Asian background  |Asian	|Asian
Asian	  |Asian	  |Asian
Black	  |Black	  |Black or African American
British	  |British	  |White
Caucasian  |White	  |White
Chinese	  |Chinese	  |Asian
East African (Kenya)  |East African	  |Black or African American
Hispanic	  |Hispanic or Latino	  |Hispanic or Latino
Hispanic or Latino	  |Hispanic or Latino	  |Hispanic or Latino
Indian	  |Indian	  |Asian
Japanese	  |Japanese	  |Asian
Mixed	  |Mixed	  |Two or More Races
NA	  |NA	|NA
Not Specified	  |Unknown	  |Unknown
South Asia	  |South Asian	  |Asian
White	  |White	  |White
YRI	  |YRI (Yoruba in Ibadan)  |Black or African American
