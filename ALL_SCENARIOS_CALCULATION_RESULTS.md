# All Scenario Calculation Results

This document covers every calculation branch currently supported by the cooking-energy webapp:

- Residential dish-based cooking
- Residential consumption-based cooking: LPG, PNG bill, PNG SCM, PNG daily use, Grid electricity, Traditional Solid Biomass, Mixed usage
- Commercial dish-based cooking
- Commercial consumption-based cooking: LPG dual cylinder, PNG bill, PNG SCM, Grid electricity, Biogas, Traditional Solid Biomass, Mixed usage
- Analysis-stage health risk, alternatives, and recommendations

The values below were generated from the current Python functions and `cooking_webapp.db`. They are representative scenarios that cover all calculation types. Users can create many more combinations by changing dishes, fuels, servings, prices, or kitchen scenarios.

## Common Inputs

### Residential Reference Profile

| Field | Value |
|---|---:|
| Household size | 4 members |
| District | Thiruvananthapuram |
| Area | Urban |
| Solar willingness | No |
| Electricity tariff | 6.5 Rs/kWh |
| LPG price | 922 Rs per 14.2 kg cylinder |
| PNG price | 48 Rs/SCM |
| Biomass price | 5 Rs/kg |
| Grid CO2 factor | 0.65 kg CO2/kWh |
| Main priority | balanced |
| Kitchen scenario | Open Kitchen |
| Cooking duration | 3 hours/day |
| Sensitive members | 1 |

### Commercial Reference Profile

| Field | Value |
|---|---:|
| Institution type | School |
| District | Thiruvananthapuram |
| Area | Urban |
| Servings per day | 250 |
| Working days/month | 26 |
| Monthly servings | 250 * 26 = 6,500 |
| Solar willingness | No |
| Commercial electricity tariff | 9.5 Rs/kWh |
| Commercial LPG price | 3,106 Rs per 19 kg cylinder |
| Domestic LPG price | 922 Rs per 14.2 kg cylinder |
| Commercial PNG price | 51 Rs/SCM |
| Biomass price | 5 Rs/kg |
| Grid CO2 factor | 0.65 kg CO2/kWh |
| Kitchen scenario | Chimney |
| Cooking duration | 6 hours/day |

### DB Constants Used

| Constant | Value |
|---|---:|
| LPG calorific value | 12.8 kWh/kg |
| PNG calorific value | 10.2 kWh/SCM |
| Biomass energy content | 4.5 kWh/kg |
| Biogas energy value | 5.5 kWh/m3 |
| LPG efficiency | 0.60 |
| PNG efficiency | 0.70 |
| Grid electricity efficiency | 0.90 |
| Biogas efficiency | 0.55 |
| Traditional Solid Biomass efficiency | 0.55 |
| LPG CO2 factor | 0.24 kg CO2/kWh input |
| PNG CO2 factor | 0.21 kg CO2/kWh input |
| Grid electricity CO2 factor | 0.65 kg CO2/kWh input |
| Biogas CO2 factor | 0.30 kg CO2/kWh input |
| Traditional Solid Biomass CO2 factor | 0.40 kg CO2/kWh input |
| PM2.5 concentration scale fallback | 5000 |

## Shared Formulas

### Residential Dish-Based

```text
dish_calories = calories_per_100g * minimum_portion_g / 100
target_meal_kcal = meal_percent * 2400 * household_size * 30
meal_scaling = target_meal_kcal / sum(selected_dish_calories_for_meal)
wastage = 1.15 - (0.05 * (household_size - 2) / 6)
row_useful_energy = energy_to_cook_kwh * meal_scaling * household_efficiency * wastage
```

For the 4-member residential profile:

```text
household_efficiency = 0.85
wastage = 1.15 - (0.05 * 2 / 6) = 1.133333
```

Meal calorie targets:

| Meal | Intensity | Percent or target | Monthly kcal target |
|---|---|---:|---:|
| Breakfast | Normal | 21 percent | 60,480 |
| Lunch | Heavy | 38 percent | 109,440 |
| Dinner | Light | 32 percent | 92,160 |
| Snacks | Normal | 7 percent | 20,160 |

### Commercial Dish-Based

```text
dish_calories = calories_per_100g * minimum_portion_g / 100
monthly_servings = servings_per_day * working_days
target_meal_kcal = calories_per_serving_for_institution * monthly_servings
actual_meal_kcal = sum(selected_dish_calories_per_serving) * monthly_servings
meal_scaling = target_meal_kcal / actual_meal_kcal
row_useful_energy = energy_to_cook_kwh * meal_scaling * serving_efficiency * wastage * monthly_servings
```

For the School scenario:

```text
serving_efficiency = 0.87
wastage = 1.03
monthly_servings = 250 * 26 = 6500
```

School meal targets used:

| Meal | Intensity | DB kcal/serving | Monthly kcal target |
|---|---|---:|---:|
| Breakfast | Normal | 500 | 3,250,000 |
| Lunch | Heavy | 1,000 | 6,500,000 |
| Dinner | Light | 525 | 3,412,500 |
| Snacks | Normal | 250 | 1,625,000 |

### Fuel Cost And Emission

For a useful energy amount assigned to a fuel:

```text
input_energy = useful_energy / fuel_efficiency
monthly_cost = input_energy * cost_per_kWh_input
residential_annual_CO2 = (input_energy / 30) * 365 * emission_factor
commercial_annual_CO2 = (input_energy / working_days) * (working_days * 12) * emission_factor
```

For commercial scenarios this simplifies to:

```text
commercial_annual_CO2 = input_energy * 12 * emission_factor
```

### Health Impact

The health helper calculates a weighted PM2.5 base emission if multiple fuels are present.

```text
weighted_PM25_base = sum(fuel_delivered_energy * fuel_PM25_factor) / total_delivered_energy
PM25_peak = weighted_PM25_base * kitchen_scenario_factor * hours_factor * PM25_scale
hours_factor = min(cooking_hours / 3, 1.5)
```

Risk score:

```text
if PM25_peak <= 5:
    health_score = DB_PM25_base_score
else:
    health_score = DB_PM25_base_score + sensitive_penalty + duration_penalty
```

Current important implementation detail: `app.py` maps submitted kitchen forms into `kitchen_type` and `cooking_hours_daily`, which are the fields the health helper reads.

### Recommendations

With `main_priority = balanced`, DB weights are:

| Component | Weight |
|---|---:|
| Health | 0.40 |
| Environmental | 0.25 |
| Economic | 0.25 |
| Practicality | 0.10 |

```text
recommendation_score =
  health_component * 0.40 +
  environmental_component * 0.25 +
  economic_component * 0.25 +
  practicality_component * 0.10
```

## Scenario Summary

### Residential Summary

| Scenario | Useful energy kWh/month | Cost Rs/month | Annual CO2 kg | Efficiency percent | Health | Top recommendations |
|---|---:|---:|---:|---:|---|---|
| Dish-based multi-fuel | 393.53 | 2,597.85 | 2,559.13 | 70.45 | 25 moderate | PNG 70.0, LPG 62.5, Grid 62.5 |
| Consumption LPG | 109.06 | 922.00 | 530.74 | 60.00 | 10 low | PNG 90.0, Grid 80.0, LPG 75.0 |
| Consumption PNG bill | 223.08 | 1,499.70 | 814.24 | 70.00 | 10 low | PNG 80.0, Grid 70.0, LPG 62.5 |
| Consumption PNG SCM | 357.00 | 2,400.00 | 1,303.05 | 70.00 | 10 low | PNG 70.0, LPG 62.5, Grid 62.5 |
| Consumption PNG daily | 321.30 | 2,160.00 | 1,172.75 | 70.00 | 10 low | PNG 70.0, LPG 62.5, Grid 62.5 |
| Consumption Grid electricity | 72.00 | 520.00 | 632.67 | 90.00 | 10 low | PNG 85.0, LPG 80.0, Grid 75.0 |
| Consumption Biomass | 247.50 | 500.00 | 2,190.00 | 55.00 | 80 critical | PNG 67.5, LPG 62.5, Grid 55.0 |
| Consumption Mixed all | 306.77 | 1,624.24 | 2,036.39 | 60.00 | 40 high | LPG 62.5, PNG 62.5, Grid 55.0 |

### Commercial Summary

| Scenario | Useful energy kWh/month | Cost Rs/month | Annual CO2 kg | Efficiency percent | Cost/serving Rs | Energy/serving kWh | Health | Top recommendations |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Dish-based multi-fuel School | 2,407.05 | 17,983.80 | 15,361.93 | 61.81 | 2.77 | 0.370 | 100 critical | Grid 55.0, PNG 43.5, Biogas 35.5 |
| Consumption LPG dual | 947.71 | 17,374.00 | 4,549.02 | 60.00 | 2.67 | 0.146 | 40 high | Grid 72.5, PNG 53.5, Biogas 40.5 |
| Consumption PNG bill | 1,399.91 | 10,000.00 | 5,039.69 | 70.00 | 1.54 | 0.215 | 40 high | Grid 55.0, PNG 38.5, Biogas 35.5 |
| Consumption PNG SCM | 1,428.00 | 10,200.00 | 5,140.80 | 70.00 | 1.57 | 0.220 | 40 high | Grid 55.0, PNG 38.5, Biogas 35.5 |
| Consumption Grid electricity | 1,350.00 | 14,250.00 | 11,700.00 | 90.00 | 2.19 | 0.208 | 10 low | Grid 62.5, PNG 48.5, Biogas 35.5 |
| Consumption Biogas | 1,573.00 | 11,293.75 | 10,296.00 | 55.00 | 1.74 | 0.242 | 75 very_high | Grid 55.0, PNG 43.5, Biogas 35.5 |
| Consumption Biomass | 1,237.50 | 2,500.00 | 10,800.00 | 55.00 | 0.38 | 0.190 | 100 critical | Grid 55.0, LPG 31.0, PNG 31.0 |
| Consumption Mixed all | 2,374.58 | 26,280.00 | 14,241.99 | 65.67 | 4.04 | 0.365 | 100 critical | Grid 67.5, PNG 48.5, Biogas 40.5 |

## Residential Scenario Details

### R1. Dish-Based Multi-Fuel

Selected dishes and fuels:

| Meal | Dish | Fuel |
|---|---|---|
| Breakfast | Idli | LPG |
| Breakfast | Sambar | Traditional Solid Biomass |
| Lunch | Fish Curry | PNG |
| Dinner | chappathi | Grid electricity |
| Snacks | Vada | Biogas |

DB dish rows:

| Dish | DB category | calories/100g | portion g | energy_to_cook kWh | Dish kcal |
|---|---|---:|---:|---:|---:|
| Idli | Breakfast | 170 | 120 | 0.240 | 204.0 |
| Sambar | Breakfast | 65 | 200 | 0.320 | 130.0 |
| Fish Curry | Lunch | 110 | 200 | 0.280 | 220.0 |
| chappathi | Dinner | 230 | 100 | 0.360 | 230.0 |
| Vada | Snacks | 308 | 80 | 0.288 | 246.4 |

Implementation note: selecting Lunch `Fish Curry` now uses only the Lunch DB row because the backend merge is by dish name plus selected meal category.

Meal calculation:

| Meal | Target kcal | Actual kcal | Scaling | Useful energy calculation | Useful kWh |
|---|---:|---:|---:|---|---:|
| Breakfast | 60,480 | 334.0 | 181.0778 | `(0.24 + 0.32) * 181.0778 * 0.85 * 1.133333` | 97.69 |
| Lunch | 109,440 | 220.0 | 497.4545 | `0.28 * 497.4545 * 0.85 * 1.133333` | 134.18 |
| Dinner | 92,160 | 230.0 | 400.6957 | `0.36 * 400.6957 * 0.85 * 1.133333` | 138.96 |
| Snacks | 20,160 | 246.4 | 81.8182 | `0.288 * 81.8182 * 0.85 * 1.133333` | 22.70 |

Fuel breakdown:

| Fuel | Useful kWh | Input kWh | Quantity | Cost Rs | Annual CO2 kg |
|---|---:|---:|---:|---:|---:|
| LPG | 41.87 | 69.78 | 5.45 kg | 353.94 | 203.74 |
| Traditional Solid Biomass | 55.82 | 101.49 | 22.55 kg | 112.77 | 493.92 |
| PNG | 134.18 | 191.69 | 18.79 SCM | 902.05 | 489.76 |
| Grid electricity | 138.96 | 154.40 | 154.40 units | 1,003.61 | 1,221.06 |
| Biogas | 22.70 | 41.27 | 7.50 m3 | 225.48 | 150.64 |

Final output:

```text
Monthly useful energy = 393.526 kWh
Monthly cost = 2597.848 Rs
Annual CO2 = 2559.127 kg
Overall efficiency = 393.526 / total_input_energy * 100 = 70.445 percent
Health = PM2.5 15.209 ug/m3, score 25 moderate
```

### R2. Consumption-Based LPG

Input:

```text
primary_fuel = LPG
cylinder_size = 14.2 kg
refill_days = 30
cylinder_price = 922 Rs
```

Calculation:

```text
energy_per_cylinder = 14.2 * 12.8 = 181.76 kWh
cylinders_per_month = 30 / 30 = 1.00
daily_gross_energy = 181.76 / 30 = 6.0587 kWh/day
monthly_gross_energy = 6.0587 * 30 = 181.76 kWh
useful_energy = 181.76 * 0.60 = 109.056 kWh
monthly_cost = 1.00 * 922 = 922 Rs
annual_CO2 = 6.0587 * 365 * 0.24 = 530.739 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 109.06 kWh/month |
| Monthly cost | 922.00 Rs |
| Annual CO2 | 530.74 kg |
| Efficiency | 60.00 percent |
| Health | 10 low |

### R3. Consumption-Based PNG By Bill

Input:

```text
primary_fuel = PNG
png_input_method = bill
monthly_bill = 1500 Rs
PNG rate = 48 Rs/SCM
```

Calculation:

```text
SCM is reverse-solved by binary search so calculated bill matches 1500 Rs within tolerance.
resolved_SCM = 31.243652 SCM
gross_energy = 31.243652 * 10.2 = 318.685 kWh
useful_energy = 318.685 * 0.70 = 223.080 kWh
monthly_cost = 1499.695 Rs
daily_gross_energy = 318.685 / 30 = 10.623 kWh/day
annual_CO2 = 10.623 * 365 * 0.21 = 814.241 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 223.08 kWh/month |
| Monthly cost | 1,499.70 Rs |
| Annual CO2 | 814.24 kg |
| Efficiency | 70.00 percent |
| Health | 10 low |

### R4. Consumption-Based PNG By Monthly SCM

Input:

```text
primary_fuel = PNG
png_input_method = scm
monthly_scm = 50
PNG rate = 48 Rs/SCM
```

Calculation:

```text
gross_energy = 50 * 10.2 = 510.000 kWh
useful_energy = 510.000 * 0.70 = 357.000 kWh
monthly_cost = 50 * 48 = 2400 Rs
daily_gross_energy = 510 / 30 = 17.000 kWh/day
annual_CO2 = 17.000 * 365 * 0.21 = 1303.050 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 357.00 kWh/month |
| Monthly cost | 2,400.00 Rs |
| Annual CO2 | 1,303.05 kg |
| Efficiency | 70.00 percent |
| Health | 10 low |

### R5. Consumption-Based PNG By Daily SCM

Input:

```text
primary_fuel = PNG
png_input_method = daily
daily_scm = 1.5
PNG rate = 48 Rs/SCM
```

Calculation:

```text
monthly_scm = 1.5 * 30 = 45 SCM
gross_energy = 45 * 10.2 = 459.000 kWh
useful_energy = 459.000 * 0.70 = 321.300 kWh
monthly_cost = 45 * 48 = 2160 Rs
daily_gross_energy = 459 / 30 = 15.300 kWh/day
annual_CO2 = 15.300 * 365 * 0.21 = 1172.745 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 321.30 kWh/month |
| Monthly cost | 2,160.00 Rs |
| Annual CO2 | 1,172.75 kg |
| Efficiency | 70.00 percent |
| Health | 10 low |

### R6. Consumption-Based Grid Electricity

Input:

```text
primary_fuel = Grid electricity
monthly_kwh_cooking = 80
tariff = 6.5 Rs/kWh
```

Calculation:

```text
useful_energy = 80 * 0.90 = 72.000 kWh
monthly_cost = 80 * 6.5 = 520 Rs
daily_input_energy = 80 / 30 = 2.6667 kWh/day
annual_CO2 = 2.6667 * 365 * 0.65 = 632.667 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 72.00 kWh/month |
| Monthly cost | 520.00 Rs |
| Annual CO2 | 632.67 kg |
| Efficiency | 90.00 percent |
| Health | 10 low |

### R7. Consumption-Based Traditional Solid Biomass

Input:

```text
primary_fuel = Traditional Solid Biomass
monthly_kg = 100
biomass_type = Firewood
cost = 5 Rs/kg
```

Calculation:

```text
gross_energy = 100 * 4.5 = 450.000 kWh
useful_energy = 450.000 * 0.55 = 247.500 kWh
monthly_cost = 100 * 5 = 500 Rs
daily_input_energy = 450 / 30 = 15.000 kWh/day
annual_CO2 = 15.000 * 365 * 0.40 = 2190.000 kg
PM2.5 = 100.000 ug/m3
health_score = 80 critical
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 247.50 kWh/month |
| Monthly cost | 500.00 Rs |
| Annual CO2 | 2,190.00 kg |
| Efficiency | 55.00 percent |
| Health | 80 critical |

### R8. Consumption-Based Mixed Usage

Input:

| Fuel | Input |
|---|---|
| LPG | refill every 45 days |
| PNG | 500 Rs monthly bill |
| Grid electricity | 40 kWh/month |
| Traditional Solid Biomass | 50 kg/month |

Component calculation:

| Fuel | Calculation | Useful kWh | Cost Rs | Annual CO2 kg |
|---|---|---:|---:|---:|
| LPG | `(30/45 cylinders) * 181.76 * 0.60` | 72.70 | 614.67 | 353.83 |
| PNG | `500 Rs bill -> 10.4077 SCM -> * 10.2 * 0.70` | 74.31 | 499.57 | 271.24 |
| Grid electricity | `40 * 0.90` | 36.00 | 260.00 | 316.33 |
| Biomass | `50 * 4.5 * 0.55` | 123.75 | 250.00 | 1,095.00 |

Output:

```text
Monthly useful energy = 72.704 + 74.311 + 36.000 + 123.750 = 306.765 kWh
Monthly cost = 614.667 + 499.570 + 260.000 + 250.000 = 1624.237 Rs
Annual CO2 = 353.826 + 271.235 + 316.333 + 1095.000 = 2036.395 kg
Overall efficiency shown by code = 60.00 percent
Health = PM2.5 40.820 ug/m3, score 40 high
```

## Commercial Scenario Details

### C1. Commercial Dish-Based Multi-Fuel School

Selected dishes and fuels:

| Meal | Dish | Fuel |
|---|---|---|
| Breakfast | Dosa | LPG |
| Lunch | Sambar | PNG |
| Lunch | Rice Meals | Traditional Solid Biomass |
| Dinner | Parotta | Grid electricity |
| Snacks | Wheat Payasam | Biogas |

DB dish rows:

| Dish | DB category | calories/100g | portion g | energy_to_cook kWh | Dish kcal |
|---|---|---:|---:|---:|---:|
| Dosa | Breakfast | 168 | 100 | 0.020 | 168.0 |
| Sambar | Lunch | 82 | 200 | 0.050 | 164.0 |
| Rice Meals | Lunch | 145 | 166 | 0.060 | 240.7 |
| Parotta | Dinner | 290 | 100 | 0.020 | 290.0 |
| Wheat Payasam | Snacks | 165 | 116 | 0.035 | 191.4 |

Meal calculation:

| Meal | Target kcal | Actual kcal/month | Scaling | Useful energy calculation | Useful kWh |
|---|---:|---:|---:|---|---:|
| Breakfast | 3,250,000 | 1,092,000 | 2.9762 | `0.020 * 2.9762 * 0.87 * 1.03 * 6500` | 346.71 |
| Lunch | 6,500,000 | 2,630,550 | 2.4710 | `(0.050 + 0.060) * 2.4710 * 0.87 * 1.03 * 6500` | 1,583.18 |
| Dinner | 3,412,500 | 1,885,000 | 1.8103 | `0.020 * 1.8103 * 0.87 * 1.03 * 6500` | 210.89 |
| Snacks | 1,625,000 | 1,244,100 | 1.3063 | `0.035 * 1.3063 * 0.87 * 1.03 * 6500` | 266.28 |

Fuel breakdown:

| Fuel | Useful kWh | Input kWh | Quantity | Cost Rs | Annual CO2 kg |
|---|---:|---:|---:|---:|---:|
| LPG | 346.71 | 577.84 | 45.14 kg | 7,379.84 | 1,664.19 |
| PNG | 719.63 | 1,028.04 | 100.79 SCM | 5,140.18 | 2,590.65 |
| Traditional Solid Biomass | 863.55 | 1,570.09 | 348.91 kg | 1,744.55 | 7,536.44 |
| Grid electricity | 210.89 | 234.33 | 234.33 units | 2,226.09 | 1,827.74 |
| Biogas | 266.28 | 484.14 | 88.03 m3 | 1,493.14 | 1,742.91 |

Final output:

```text
Monthly useful energy = 2407.053 kWh
Monthly cost = 17983.802 Rs
Annual CO2 = 15361.929 kg
Overall efficiency = 61.807 percent
Energy per serving = 2407.053 / 6500 = 0.370 kWh
Cost per serving = 17983.802 / 6500 = 2.767 Rs
Health = PM2.5 350.860 ug/m3, score 100 critical
```

### C2. Commercial Consumption-Based LPG Dual Cylinder

Input:

```text
primary_fuel = LPG
domestic_cylinders = 2
commercial_cylinders = 5
domestic price = 922 Rs/cylinder
commercial price = 3106 Rs/cylinder
```

Calculation:

```text
domestic_gross = 2 * 14.2 * 12.8 = 363.52 kWh
commercial_gross = 5 * 19.0 * 12.8 = 1216.00 kWh
total_gross = 1579.52 kWh
useful_energy = 1579.52 * 0.60 = 947.712 kWh
monthly_cost = (2 * 922) + (5 * 3106) = 17374 Rs
annual_CO2 = (1579.52 / 26) * (26 * 12) * 0.24 = 4549.018 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 947.71 kWh/month |
| Monthly cost | 17,374.00 Rs |
| Annual CO2 | 4,549.02 kg |
| Cost per serving | 2.67 Rs |
| Energy per serving | 0.146 kWh |
| Health | 40 high |

### C3. Commercial Consumption-Based PNG By Bill

Input:

```text
primary_fuel = PNG
png_input_method = bill
monthly_bill = 10000 Rs
PNG rate = 51 Rs/SCM
```

Calculation:

```text
SCM is reverse-solved by binary search.
resolved_SCM = 196.066406
gross_energy = 196.066406 * 10.2 = 1999.877 kWh
useful_energy = 1999.877 * 0.70 = 1399.914 kWh
monthly_cost = 10000 Rs
annual_CO2 = (1999.877 / 26) * 312 * 0.21 = 5039.691 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 1,399.91 kWh/month |
| Monthly cost | 10,000.00 Rs |
| Annual CO2 | 5,039.69 kg |
| Cost per serving | 1.54 Rs |
| Energy per serving | 0.215 kWh |
| Health | 40 high |

### C4. Commercial Consumption-Based PNG By Monthly SCM

Input:

```text
primary_fuel = PNG
png_input_method = scm
monthly_scm = 200
PNG rate = 51 Rs/SCM
```

Calculation:

```text
gross_energy = 200 * 10.2 = 2040.000 kWh
useful_energy = 2040.000 * 0.70 = 1428.000 kWh
monthly_cost = 200 * 51 = 10200 Rs
annual_CO2 = (2040 / 26) * 312 * 0.21 = 5140.800 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 1,428.00 kWh/month |
| Monthly cost | 10,200.00 Rs |
| Annual CO2 | 5,140.80 kg |
| Cost per serving | 1.57 Rs |
| Energy per serving | 0.220 kWh |
| Health | 40 high |

### C5. Commercial Consumption-Based Grid Electricity

Input:

```text
primary_fuel = Grid electricity
monthly_kwh = 1500
electricity_rate = 9.5 Rs/kWh
```

Calculation:

```text
useful_energy = 1500 * 0.90 = 1350.000 kWh
monthly_cost = 1500 * 9.5 = 14250 Rs
annual_CO2 = (1500 / 26) * 312 * 0.65 = 11700.000 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 1,350.00 kWh/month |
| Monthly cost | 14,250.00 Rs |
| Annual CO2 | 11,700.00 kg |
| Cost per serving | 2.19 Rs |
| Energy per serving | 0.208 kWh |
| Health | 10 low |

### C6. Commercial Consumption-Based Biogas

Input:

```text
primary_fuel = Biogas
daily_biogas_m3 = 20
biogas_monthly_cost user OPEX = 3000 Rs
working_days = 26
```

Calculation:

```text
monthly_m3 = 20 * 26 = 520 m3
gross_energy = 520 * 5.5 = 2860.000 kWh
useful_energy = 2860.000 * 0.55 = 1573.000 kWh
```

Biogas cost is computed by `helper.compute_biogas_costs`:

| Cost component | Value Rs/month |
|---|---:|
| Feedstock cost | 0.00 |
| Maintenance cost | 643.89 |
| Capex component | 7,649.86 |
| User OPEX | 3,000.00 |
| Total monthly cost | 11,293.75 |

Emission:

```text
annual_CO2 = (2860 / 26) * 312 * 0.30 = 10296.000 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 1,573.00 kWh/month |
| Monthly cost | 11,293.75 Rs |
| Annual CO2 | 10,296.00 kg |
| Cost per serving | 1.74 Rs |
| Energy per serving | 0.242 kWh |
| Health | 75 very_high |

### C7. Commercial Consumption-Based Traditional Solid Biomass

Input:

```text
primary_fuel = Traditional Solid Biomass
monthly_biomass_kg = 500
biomass_cost_per_kg = 5 Rs
```

Calculation:

```text
gross_energy = 500 * 4.5 = 2250.000 kWh
useful_energy = 2250.000 * 0.55 = 1237.500 kWh
monthly_cost = 500 * 5 = 2500 Rs
annual_CO2 = (2250 / 26) * 312 * 0.40 = 10800.000 kg
```

Output:

| Metric | Value |
|---|---:|
| Useful energy | 1,237.50 kWh/month |
| Monthly cost | 2,500.00 Rs |
| Annual CO2 | 10,800.00 kg |
| Cost per serving | 0.38 Rs |
| Energy per serving | 0.190 kWh |
| Health | 100 critical |

### C8. Commercial Consumption-Based Mixed Usage

Input:

| Fuel | Input |
|---|---|
| LPG | 5 commercial cylinders/month |
| PNG | 5,000 Rs monthly bill |
| Grid electricity | 500 kWh/month |
| Traditional Solid Biomass | 200 kg/month |

Component calculation:

| Fuel | Calculation | Useful kWh | Cost Rs | Annual CO2 kg |
|---|---|---:|---:|---:|
| LPG | `5 * 19 * 12.8 * 0.60` | 729.60 | 15,530.00 | 3,502.08 |
| PNG | `5000 Rs bill -> 98.0359 SCM -> * 10.2 * 0.70` | 699.98 | 5,000.00 | 2,519.91 |
| Grid electricity | `500 * 0.90` | 450.00 | 4,750.00 | 3,900.00 |
| Biomass | `200 * 4.5 * 0.55` | 495.00 | 1,000.00 | 4,320.00 |

Output:

```text
Monthly useful energy = 729.600 + 699.976 + 450.000 + 495.000 = 2374.576 kWh
Monthly cost = 15530 + 5000 + 4750 + 1000 = 26280 Rs
Annual CO2 = 3502.080 + 2519.914 + 3900.000 + 4320.000 = 14241.994 kg
Overall efficiency = 65.669 percent
Cost per serving = 26280 / 6500 = 4.043 Rs
Energy per serving = 2374.576 / 6500 = 0.365 kWh
Health = PM2.5 201.074 ug/m3, score 100 critical
```

## Kitchen Scenario Factors

The DB currently contains these kitchen scenario factors for both residential and commercial:

| Scenario | Combined factor |
|---|---:|
| Open Kitchen | 0.04 |
| Chimney | 0.25 |
| Exhaust Fan | 0.60 |
| No Exhaust | 0.80 |

For LPG with 3 cooking hours/day:

```text
Open Kitchen PM2.5 = 0.005 * 0.04 * 1.0 * 5000 = 1.000 ug/m3
Chimney PM2.5 = 0.005 * 0.25 * 1.0 * 5000 = 6.250 ug/m3
Exhaust Fan PM2.5 = 0.005 * 0.60 * 1.0 * 5000 = 15.000 ug/m3
No Exhaust PM2.5 = 0.005 * 0.80 * 1.0 * 5000 = 20.000 ug/m3
```

For the commercial Chimney case with 6 cooking hours/day:

```text
hours_factor = min(6 / 3, 1.5) = 1.5
LPG PM2.5 = 0.005 * 0.25 * 1.5 * 5000 = 9.375 ug/m3
```

## Implementation Notes

1. Residential and commercial dish-based calculation now merge selected dishes to DB rows by dish name plus selected meal category. This fixes cross-meal duplicate names such as Lunch `Fish Curry` versus Dinner `Fish Curry`; same-category duplicate DB rows can still expand until the app moves to `dish_id`.
2. Residential consumption-based results do not set `environmental_grade` directly in the energy result; environmental grades appear in alternative fuel scenarios.
3. Residential mixed consumption sets top-level `overall_thermal_efficiency` from the primary fuel name `Mixed usage`, which falls back to 60 percent. Component efficiencies are still used for component energy.
4. Solar+BESS is active in the DB but skipped in alternatives when solar willingness is No.
5. Commercial alternatives use `calculate_commercial_fuel_scenario`. If commercial LPG system-price parameters are missing, the helper can fall back to its hardcoded LPG commercial price path. The current consumption branch itself used the explicit form price of 3,106 Rs/cylinder for the LPG scenario documented here.
6. Commercial environmental grade is based on CO2 per serving, while residential environmental grade is based on annual CO2 per household member where available.
