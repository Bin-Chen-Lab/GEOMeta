Agent task: Race standardization

Standardize the `Race` field according to the rules below. Preserve the input order and return one standardized value for each original term.
                
## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Maintain Consistency: Always use commonly accepted terms for race and ethnicity. Ensure that terms are clear, concise, and widely recognized in demographic and scientific contexts.

2. No Abbreviations: Avoid abbreviations unless they are universally understood, such as 'NA' for 'Not Available'. 'AI/AN' should be expanded to 'American Indian or Alaska Native.'

3. Avoid Using Multiple Terms: Where there is a combination of racial categories (e.g., 'Black or African American; White'), standardize to a single category or use 'Mixed' or 'Multi-racial' when necessary.

4. Keep 'NA' as it is: Do not expand 'NA' to 'Not Applicable' or any other variants. Always retain 'NA' as the value when it appears.

5. Simplify Complex Terms: For terms like 'White; American Indian or Alaska Native,' standardize to a clear format like 'White + American Indian or Alaska Native.'

6. Use Recognized Terms for Mixed Groups: For terms indicating more than one race, standardize them as 'Mixed' or 'Multi-racial' as needed, and avoid ambiguous descriptions like 'More than one race.'

7. Geographic Clarity: Ensure that terms referring to geographic regions, such as 'South Indian' or 'Middle Eastern,' are standardized to be more broadly accepted, e.g., 'Indian' and 'Middle Eastern' respectively.

8. Ethnicity Clarification: Ensure that ethnic groups with unique identifiers, such as 'Native Hawaiian or Pacific Islander,' are standardized and unambiguous.

9. Don't Use 'Not Specified': Replace 'Not Specified' with 'NA' to indicate missing or unknown data.

10. Hispanic/Latino Clarification: Use 'Hispanic or Latino' for any variation of these terms to maintain consistency.

11. Clarify Unknown Data: Replace 'Unknown/Not reported' with 'Unknown' for missing or unspecified data.

## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.
            
## Output Examples:
Original Term                           | Standardized Term                          
African                                 | African                                   
African American                        | African American                          
AI/AN                                   | American Indian or Alaska Native           
American Indian or Alaska Native        | American Indian or Alaska Native           
American Indian or Alaska Native; White | American Indian or Alaska Native + White   
Black                                   | Black                                     
Black or African American               | Black or African American                  
Hispanic                                | Hispanic or Latino                         
Hispanic or Latino                      | Hispanic or Latino                         
Middle Eastern                          | Middle Eastern                            
Mixed                                   | Mixed                                     
Multi-racial                            | Multi-racial                              
Native American                         | Native American                           
Native Hawaiian or Pacific Islander     | Native Hawaiian or Pacific Islander       
NA                                      | NA                                        
Other                                   | Other                                     
White                                   | White                                     
White; Asian                            | White + Asian                              
White; Other                            | White + Other                              
White/Asian                             | White + Asian 