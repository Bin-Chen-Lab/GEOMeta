Agent task: Perturbation-dose standardization

Standardize the `Pert_Dose` field according to the rules below. Preserve the input order and return one standardized value for each original term.

## General Requirements

- Preserve the original input order.
- Maintain a strict one-to-one correspondence between original and standardized terms.
- Do not skip, reorder, duplicate, split, or merge input rows.
- Apply only the field-specific rules defined below.

## Standardization Rules

1. Units of Measurement: Ensure that all terms use consistent units.
   - Use 'µg' (micrograms) instead of 'ug' to reflect standard scientific notation.
   - Use 'µM' (micromolar) instead of 'uM.'
   - Maintain capitalization for proper units like 'nM' for nanomolar and 'mM' for millimolar.
   - Convert all other unit terms to standard scientific abbreviations (e.g., 'ml' for milliliters).
    - Replace 'kcal' for calorie-related terms. For example, '60% calories' → '60% kcal'.
    - Standardize 'genomic copies' to 'genome copies' (e.g., '2 × 10^11 genomic copies/mouse' → '2 × 10^11 genome copies/mouse').
      - For any mentions of 'body weight' or 'Body Weight', use 'bw' consistently (e.g., 'µg/g body weight/day' → 'µg/g bw/day').
       
2. Special Units: Ensure specific units like CFU and PFU are used consistently without changes. Do not add an 's' at the end, even in plural contexts.
 - Colony Forming Units (CFU): Maintain the abbreviation 'CFU.' If additional clarification is required (e.g., bacterial species or context).
- Plaque Forming Units (PFU): Maintain the abbreviation 'PFU.' Clarify viral species or treatment context if necessary.
- Replace '1 x 10^8 cfu' or similar variations with '1 x 10^8 CFU' for capitalization consistency.
- Use 'MOI' for multiplicity of infection, ensuring consistency. For example, 'moi 2' → 'MOI 2'; '3 MOI' → 'MOI 3'.
- Use 'focus forming units' for similar contexts. For example, '2 x 10^6 focal-forming units' → '2 x 10^6 focus forming units'. 
MOI: Replace '=' with a space.
Example: 'MOI=1' → 'MOI 1'
Percent Volume/Volume (v/v):
Remove parentheses but retain 'v/v' format.
Example: '1% (v/v)' → '1% v/v'
            
3. Scientific Notation and Spacing: Standardize scientific notation across the dataset.
- Convert 'e' notation to standard power notation (e.g., '10e5 cells' becomes '10^5 cells').
- Use lowercase 'x' with spacing for scientific notation, e.g., '1x10^6' → '1 x 10^6'.
- Maintain consistent formatting for exponents (e.g., '1 x 10^5 cells').
- Numeric Value Formatting: Always apply comma formatting for numbers ≥1,000. Insert commas as thousands separators. For ratios or titers expressed as 1:40000, format the denominator with a comma. Apply this consistently across all units and concentration notations.
Example: 1000 IU/ml → 1,000 IU/mL
Example: 1:40000 → 1:40,000
'10000 nM' → '10,000 nM'
'2000000 particles' → '2,000,000 particles'
'100000 U/mL' → '100,000 U/mL'
4. Exponent Standardization: Maintain a consistent format for all values expressed in scientific notation or exponents.
Convert all forms to the format: 1 x 10^n [unit]
Examples:
1x10^5 cells → 1 x 10^5 cells
10^5 cells → 1 x 10^5 cells
10e5 cells or 1e5 cells → 1 x 10^5 cells
Always use a lowercase x with single spaces on both sides.
Retain the original unit or descriptor (e.g., cells, IU/mL, etc.) after the exponent.
If an integer is already in 1 x 10^n format, leave unchanged.
If a numeric value appears as n x 10^m, leave unchanged (e.g., 2 x 10^6 cells).
Do not convert explicit numbers with commas (e.g., 100,000 cells) to exponent form.

5. Preserve Order and Structure: The order in which the dosages appear should be preserved as they represent a sequence of treatment. 
- The format should be: Dosage Value + Unit, separated by + when there are multiple entries.
- Multiple Dosages and Combinations: For terms with multiple doses or combinations, separate them using ' + '.
- Do not split terms connected by a semicolon. If a semicolon is present, it indicates that the term is complex and should remain unified as one single term in subsequent steps for clarity and consistency.
- Ensure spacing around units for readability (e.g., '100 µg/mL + 10 ng/mL').
Example: 5000 U/mL + 100 U/mL + 10 µg/mL + 10 µg/mL.

6. Consistency in Capitalization: Ensure that units and measurements are capitalized correctly.
     - For example, '100ng/ml' should be converted to '100 ng/mL'.
     - '10e5 cells' should be converted to '1 x 10^5 cells.'
     - '100ug/ml' should be standardized as '100 µg/mL.'
     - '100uM' should be converted to '100 µM.'
     - '10^7 CFU' should be retained unless additional context is required.
            
7. Remove Drug Names: Exclude any drug or chemical names preceding the dosage. Only the numerical values with their corresponding units (such as U/mL, ng/mL, µg/mL, etc.) should remain in the annotation. Ensure the components are separated by a single space.
 Example: IL-4 5000 U/ml + IL-2 100 U/ml + Anti-IFNγ 10 µg/ml + Anti-IL-12 10 µg/ml → 5000 U/mL + 100 U/mL + 10 µg/mL + 10 µg/mL.
                                
 8. Per to Slash Conversion:
  - Replace 'per' with '/'. For example, '0.2 ml per 25 g' should be '0.2 mL/25 g'.
                  
9. Dosage Example Transformations:
   - '0.5mg/ml Ascorbic Acid + 10mM β-Glycerol Phosphate' → '0.5 mg/mL + 10 mM'.
   - '60% Calories' → '60% kcal'.
   - '1X10^6' → '1 x 10^6'. (use lowercase x)
   - '2 × 10^6 focal-forming units' → '2 × 10^6 focus forming units'.
  - '50mg/kg/day + 5mg/kg/day + 20mg/kg/day + 60mg/kg/day' should be kept 50 mg/kg/day + 5 mg/kg/day + 20mg/kg/day + 60mg/kg/day.
  - '10^7 PFUs' should be kept as '10^7 PFU'.
          
10. Standardizing Viral Particles:
 - Use 'viral particles' consistently for clarity and precision.
 - For combinations, preserve order and structure (e.g., '1 × 10^7 viral particles of MVA + 1 × 10^9 viral particles of adenovirus'→ '1 × 10^7 viral particles + 1 × 10^9 viral particles').
            
11. Consistency in Capitalization:
  - Capitalize initial words but avoid capitalization for connecting words like 'and'.

12. Nutritional Context:
  - Use consistent terminology for nutritional terms (e.g., '60% kcal' instead of '60% calories').
  - If the context requires additional clarification, ensure terms align with standard nutritional guidelines.
            
13. Scientific Notation: Format: Use the format 'numeric value x 10^n' or X × 10^-n
(remove leading zeros after the negative sign) for scientific notation.
Examples:
'1.50E-04' → '1.5 x 10^-4'
'1.50E-05' → '1.5 x 10^-5'
'2.00E-04' → '2 x 10^-4'
For numbers like '1.10', '2.10', or '1.20', remove the trailing zero:
'1.5 E-04' → '1.5 x 10^-4'
'2.10E-05' → '2.1 x 10^-5'
            
14. Whole Numbers: Simplify Decimal Whole Numbers:
For numbers like '2.0' or '5.0', drop the '.0' and use the integer:
'2.0 mg/mL' → '2 mg/mL'
'5.0 µg' → '5 µg'
            
15. Units and Spacing: Leave a Space Between Numeric Value and Unit. Ensure a single space between the number and the unit.
Examples:
'250μM + 200pM' → '250 µM + 200 pM'
'40mM' → '40 mM'
'2500nM + 100nM' → '2,500 nM + 100 nM'
'40ng/ml' → '40 ng/mL'

16. Superscripted Area/Volume Units:
Rule: Use proper superscripts for squared and cubed units (², ³) etc in expressions involving area or volume.

Examples:
dynes/cm2 -> dynes/cm²;
J/m2 -> J/m²;
µg/cm3 -> µg/cm³;

17. Drug/Vector Dose Formatting
Use standard scientific unit formatting with appropriate spacing and superscripts. Use lowercase for biological units like vectors.
Examples:
Dose with energy	25 µM + 10 kJ/m²
Dose with surface area	30 mg/m² + 200 mg
Vector dose	2 × 10^10 vg/mL
                    
## Output Requirements

Return exactly one standardized value for each original term.
Do not include explanations or additional commentary.
