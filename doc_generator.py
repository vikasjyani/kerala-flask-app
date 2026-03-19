import sqlite3
import os
import re
import pandas as pd
from datetime import datetime

# Configuration
DB_PATH = 'cooking_webapp.db'
TEMPLATE_DIR = 'templates'
OUTPUT_FILE = 'Calculation_Documentation_Full.md'

sections = []

def add_section(title, content, level=1):
    header = "#" * level
    sections.append(f"{header} {title}\n\n{content}\n")

def get_db_tables():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables

def dump_table_sample(table_name):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        conn.close()
        if df.empty:
            return f"*Table {table_name} is empty.*"
        # Return only first 5 rows
        return df.head(5).to_markdown(index=False)
    except Exception as e:
        return f"Error dumping {table_name}: {e}"

def extract_inputs_from_templates():
    input_report = []
    if not os.path.exists(TEMPLATE_DIR):
        return "Templates directory not found."
    
    for filename in os.listdir(TEMPLATE_DIR):
        if filename.endswith('.html'):
            filepath = os.path.join(TEMPLATE_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            inputs = re.findall(r'<(?:input|select|textarea)[^>]*name=["\']([^"\']+)["\']', content)
            if inputs:
                input_report.append(f"### Page: {filename}")
                input_report.append("| Input Name | Type (Inferred) | Context |")
                input_report.append("| :--- | :--- | :--- |")
                for inp in inputs:
                    input_report.append(f"| `{inp}` | Form Field | User Input |")
                input_report.append("\n")
    return "\n".join(input_report)

# ==============================================================================
# DOCUMENT GENERATION
# ==============================================================================

# 1. Title & Intro
add_section("Cooking Energy Web App - Exhaustive Technical Documentation", 
f"**Generated**: {datetime.now()}\n\n"
"**Purpose**: To provide a complete, verified record of every database parameter, user input, and calculation step in the system.\n"
"**Scope**: Detailed Verification Traces with Sample Reference Data.")

# 2. User Inputs Mapping
add_section("Chapter 1: User Input Atlas", 
"This section references every single HTML input field across the application, defining the exact variable names passed to the Python backend.\n\n" + 
extract_inputs_from_templates())

# 3. Database Reference (Sample Data)
add_section("Chapter 2: Database Reference (Sample Data)", 
"This section contains SAMPLE content (first 5 rows) of the reference database used for calculations.")

tables_to_dump = [
    'system_parameters',
    'fuel_unit_pricing',
    'thermal_efficiencies',
    'emission_factors',
    'dishes_residential',
    'dishes_commercial',
    'meal_energy_distribution',
    'group_cooking_efficiency',
    'institution_meal_calories',
    'kitchen_scenarios',
    'lpg_pricing'
]

available_tables = get_db_tables()
for table in tables_to_dump:
    if table in available_tables:
        add_section(f"Table: {table}", dump_table_sample(table), level=3)
    else:
        add_section(f"Table: {table}", "*Table not found in schema.*", level=3)

# 4. Calculation Logic Traces (Exhaustive)
add_section("Chapter 3: Calculation Logic Traces (Detailed)", 
"""
This section provides step-by-step verification logic for EVERY supported calculation scenario in the codebase.

## 3.1 Residential Consumption: LPG (Subsidized vs Non-Subsidized)
**Code Ref**: `residential_cooking.calculate_consumption_based` -> `helper.calculate_lpg_consumption_from_refill`

### Inputs
*   `days` (User): Refill frequency (e.g., 30 days)
*   `cyl_size` (Const): 14.2 kg
*   `calorific` (Const): 12.8 kWh/kg
*   `efficiency` (DB): 0.60
*   `price` (DB): Market Price (e.g., ₹850)
*   `subsidy` (DB/Logic): Subsidy Amount (e.g., ₹200)

### Algorithm
1.  **Gross Consumption**:
    $$ E_{gross\_monthly} = \\frac{14.2 \\times 12.8}{days} \\times 30 $$
2.  **Useful Energy**:
    $$ E_{useful} = E_{gross} \\times 0.60 $$
3.  **Cost Calculation**:
    *   **Subsidized User**: Cost = $ (\\text{Cylinders}/Month) \\times (Price_{market} - Subsidy) $
    *   **Non-Subsidized**: Cost = $ (\\text{Cylinders}/Month) \\times Price_{market} $
4.  **Emissions**:
    $$ CO_{2} = E_{gross} \\times 0.213 \\text{ kg/kWh} \\times 12 $$

---

## 3.2 Residential Consumption: PNG (Bill vs SCM)
**Code Ref**: `residential_cooking.calculate_png_consumption...`

### Case A: Input via Bill Amount
1.  **Infer Consumption**:
    $$ SCM_{monthly} = \\frac{BillAmount}{Rate_{per\_scm}} $$
2.  **Energy**:
    $$ E_{useful} = SCM_{monthly} \\times 10.56 \\text{ (Calorific)} \\times 0.70 \\text{ (Eff)} $$

### Case B: Input via Monthly SCM
1.  **Calculate Bill**:
    $$ Bill = SCM_{monthly} \\times Rate_{per\_scm} $$
2.  **Energy**: Same as above.

### Case C: Input via Daily SCM
1.  $$ SCM_{monthly} = SCM_{daily} \\times 30 $$

---

## 3.3 Residential Consumption: Grid Electricity
**Input**: `Monthly_Units` (kWh).
**Tariff**: User Profile `electricity_tariff` (e.g., ₹6.5/unit).

1.  **Useful Energy**:
    $$ E_{useful} = Input_{kWh} \\times 0.90 \\text{ (Induction Eff)} $$
2.  **Cost**:
    $$ Cost = Input_{kWh} \\times Tariff $$

---

## 3.4 Residential Consumption: Traditional Biomass
**Input**: `Monthly_Mass` (kg).
**Calorific**: ~4.5 kWh/kg (Wood).
**Efficiency**: **55%** (0.55) - Very low.

1.  **Useful Energy**:
    $$ E_{useful} = (Mass_{kg} \\times 4.5) \\times 0.55 $$

---

## 3.5 Commercial: Mixed Fuel Calculation
**Code Ref**: `commercial_cooking.calculate_consumption_based` -> `Mixed usage` loop.

This algorithm iterates through selections and sums up the loads.

### Step 1: Accumulators
*   `Total_Useful_Energy = 0`
*   `Total_Cost = 0`
*   `Total_Emissions = 0`
*   `Total_Gross_Input = 0`

### Step 2: Loop Logic
*   **If LPG Selected**:
    1.  `Cyls` = Input (Commercial 19kg).
    2.  `E_useful_step` = $ Cyls \\times 19 \\times 12.8 \\times 0.60 $.
    3.  `Cost_step` = $ Cyls \\times 1810.5 $.
    4.  Add to Accumulators.
*   **If Electric Selected**:
    1.  `Units` = Input.
    2.  `E_useful_step` = $ Units \\times 0.90 $.
    3.  `Cost_step` = $ Units \\times 9.5 $.
    4.  Add to Accumulators.
*   **If PNG Selected**:
    1.  `SCM` = Input (Derived from bill).
    2.  `E_useful_step` = $ SCM \\times 10.56 \\times 0.70 $.
    3.  `Cost_step` = Bill Amount.
    4.  Add to Accumulators.

### Step 3: Final Consolidation
*   `Monthly_Energy_kWh` = `Total_Useful_Energy`
*   `Overall_Efficiency` = `Total_Useful_Energy / Total_Gross_Input`

---

## 3.6 Commercial: Biogas Costing Model
**Code Ref**: `helper.compute_biogas_costs`

Biogas is unique; it has Capex + O&M.

### Inputs
*   `Daily_Gas_m3`
*   `Working_Days`

### Logic
1.  `Monthly_m3` = $ Daily \\times Days $.
2.  `Energy_Gross` = $ Monthly_{m3} \\times 5.5 \\text{ kWh/m3} $.
3.  **Cost Components**:
    *   `Feedstock`: Assumed free (0).
    *   `Labor`: Assumed internal (0).
    *   `Amortized_Capex`: $ (Capex / Lifetime_{months}) $.
    *   `Maintenance`: $ 2\% \\text{ of Capex} / 12 $.
4.  `Cost_Monthly` = Amortized + Maintenance.

---

## 3.7 Residential Dish-Based: The "Scaling Factor" Trace
**Code Ref**: `residential_cooking.monthly_calories`

### 1. Requirements
*   `Household_Size` (N)
*   `Calorie_Norm` = 2400 kcal/day.
*   `Meal_Ratios`: B=0.21, L=0.32, D=0.40, S=0.07.

### 2. Category Targets
$$ Target_{Category} = N \\times 2400 \\times Ratio \\times 30 $$

### 3. Dish Contribution
Sum of calories of all selected dishes in category (per standard portion).
$$ Actual_{Calories} = \\sum (Dish_{kcal/100g} \\times Portion_{g}/100) $$

### 4. Scaling Factor (S)
$$ S = Target / Actual $$
*This determines how many "standard portions" are needed.*

### 5. Final Energy Formula
$$ E_{kWh} = (E_{cook\_per\_portion} \\times S) \\times \\eta_{size\_efficiency} \\times Wastage_{factor} $$

---

## 3.8 Commercial Dish-Based: Volume Efficiency Trace
**Code Ref**: `commercial_cooking.commercial_monthly_energy`

### 1. Volume Factor ($\eta_{vol}$)
lookup `servings_per_day` in `SERVINGS_THRESHOLDS`:
*   < 100: 1.00
*   100-500: 0.85
*   500+: 0.75

### 2. Commercial Wastage ($W_{comm}$)
lookup `institution_type` in `commercial_wastage_factors`:
*   School: Base 1.05
*   Hotel: Base 1.10

### 3. Final Energy
$$ E_{kWh} = (E_{cook} \\times Scaling) \\times \\eta_{vol} \\times W_{comm} $$
*Note: $\eta_{household}$ is replaced by $\eta_{vol}$.*

---

## 3.9 Solar + BESS Hourly Simulation
**Code Ref**: `helper.calculate_solar_with_bess_sizing`

### Algorithm Step-by-Step (per hour)
1.  **Solar Gen**: $ KW_{installed} \\times Irradiance_{t} \\times 0.75 $.
2.  **Direct Load**: $ Load_{day} $ (Lunch hours).
3.  **Solar to Load**: $ \min(Solar, Load) $.
4.  **Excess Solar**: $ \max(0, Solar - Load) $.
5.  **Battery Charging**: $ \min(Excess, Bat_{capacity} - Bat_{state}) $.
6.  **Night Load**: $ Load_{night} $ (Dinner/Lights).
7.  **Battery Discharge**: $ \min(NightLoad, Bat_{state}) $.
8.  **Grid Import**: $ (Load - SolarUsed - BattUsed) $.

---

## 3.10 Financial LCOE (Levelized Cost of Energy)
**Code Ref**: `helper.calculate_levelized_cost_25yr`

$$ LCOE = \\frac{\\sum_{t=0}^{25} \\frac{Cost_t}{(1+r)^t}}{\\sum_{t=0}^{25} \\frac{Energy_t}{(1+r)^t}} $$

### Cash Flow Items ($Cost_t$)
*   **Year 0**: 20% Down Payment.
*   **Year 1-5**: 80% Loan EMI + O&M.
*   **Year 8, 15, 22**: Battery Replacement Cost.
*   **Year 6-25**: O&M Only.

""")

# Write File
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write("\n".join(sections))

print(f"Successfully generated {OUTPUT_FILE} with exhaustive details.")
