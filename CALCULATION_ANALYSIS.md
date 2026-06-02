# Cooking Tool Calculation Analysis

This document records the calculation flow in the current webapp, the user options exposed by the Python routes and HTML templates, and four worked residential dish-based LPG examples.

The webapp was verified running with:

```powershell
python app.py
```

Verified URL:

```text
http://127.0.0.1:5000/
```

## Files Analyzed

### Python Files

| File | Purpose in current calculation flow |
|---|---|
| `app.py` | Main Flask application. Defines route flow, session data, residential and commercial form handling, energy calculation dispatch, analysis rendering, feedback, PDF download, and API helpers. |
| `residential_cooking.py` | Residential dish-based and consumption-based calculations. Reads dishes, meal selections, fuel selections, household scaling, and returns monthly energy, cost, emissions, efficiency, and fuel details. |
| `commercial_cooking.py` | Commercial dish-based and consumption-based calculations. Uses institution type, servings per day, working days, meal categories, fuel selections, and commercial usage inputs. |
| `helper.py` | Shared formulas for dish calories, fuel input energy, emissions, costs, alternatives, health exposure, environmental grading, and recommendations. |
| `fuel_cost_standardizer.py` | Converts LPG, PNG, electricity, biomass, biogas, and solar pricing into comparable cost per kWh values. User-entered prices override DB prices. |
| `database/db_helper.py` | SQLite access layer for dishes, districts, fuels, fuel prices, thermal efficiencies, emissions, kitchen scenarios, meal distribution, system parameters, and recommendation weights. |
| `pdf_generator.py` | Builds localized PDF reports from analysis results. Does not change the calculation values. |
| `error_handlers.py` | Central error page handling. |
| `debug_logger.py` | Debug logging helper. |
| `config.py` | Flask configuration, database paths, default settings, and security settings. |
| `run.py` | Simple app runner wrapper. The requested run command uses `python app.py` instead. |
| `gunicorn.conf.py` | Production server configuration. |
| `database/__init__.py` | Package marker for database helpers. |

### HTML Templates

| Template | User-facing role and options |
|---|---|
| `templates/base.html` | Shared layout, navigation, language selector, static assets, common page shell. |
| `templates/index.html` | Landing/start page that links the user into the analysis flow. |
| `templates/info.html` | Informational content page. |
| `templates/analysis_selection.html` | First major choice: Residential or Commercial analysis. |
| `templates/household_profile.html` | Residential profile form: name, email, country code, phone, household size, district, urban/rural area, income bracket, solar willingness, roof area when solar is selected, and fuel price overrides. |
| `templates/energy_calculation.html` | Residential energy form. User chooses dish-based or consumption-based method. Dish-based exposes meal sections, dish checkboxes, meal intensity, fuel mix, and per-dish fuel assignment. Consumption-based exposes fuel usage inputs. |
| `templates/kitchen_profile.html` | Residential kitchen form: ventilation scenario, cooking hours, sensitive members, budget preference, and breakfast timing. |
| `templates/analysis.html` | Residential analysis output: current setup, fuel breakdown, monthly energy, cost, annual emissions, efficiency, health impact, alternatives, solar details, recommendations, and feedback link. |
| `templates/feedback.html` | Post-analysis feedback and support-interest options. |
| `templates/feedback_success.html` | Feedback success page. |
| `templates/contact_us.html` | Contact page. |
| `templates/error.html` | Error page. |
| `templates/commercial_selection.html` | Commercial institution profile: institution type, name, contact details, district, area, servings per day, working days, budget priority, solar willingness, roof area, and fuel price overrides. |
| `templates/commercial_kitchen_profile.html` | Commercial kitchen form: kitchen scenario, cooking hours, exposed staff count, and budget preference. |
| `templates/commercial_energy_calculation.html` | Commercial energy form. User chooses dish-based or consumption-based method, then selects meals/dishes/fuels or enters fuel consumption. |
| `templates/commercial_analysis.html` | Commercial analysis output with current setup, alternatives, health, environmental, cost, and recommendation results. |

## Main User Option Map

### Start

1. User opens `/`.
2. User selects analysis type on `/analysis_selection`:
   - Residential
   - Commercial

### Residential Profile Options

Residential route sequence:

```text
/household_profile -> /submit_household -> /energy_calculation -> /calculate_consumption -> /kitchen_profile -> /submit_kitchen -> /analysis
```

Residential profile inputs:

| Option | Values |
|---|---|
| Household size | 1 to 20, default 4 |
| District | Kerala district list from DB |
| Area type | Urban, Rural |
| Monthly income | Less than 50,000; 50,000-70,000; 70,000-1,00,000; 1,00,000-1,50,000; Above 1,50,000 |
| Solar willingness | Yes, No |
| Roof area | Shown when solar willingness is Yes |
| Country code | +91 India, +971 UAE, +94 Sri Lanka, +44 UK, +1 USA |
| Fuel price overrides | LPG cylinder price, PNG rate per SCM, electricity tariff per kWh, biomass cost per kg, grid CO2 factor |

Some economic fields are handled by `app.py` but are not active in the current residential template. Their server-side defaults are:

| Field | Default used |
|---|---:|
| LPG subsidy | No |
| Electricity tariff | 6.5 Rs/kWh |
| Loan interest rate | 7.0 percent |
| Loan tenure | 5 years |
| Main priority | balanced |

### Residential Dish-Based Options

Dish-based residential cooking exposes:

| Option | Values |
|---|---|
| Calculation method | Dish-based cooking |
| Fuel mix | LPG, PNG, Grid electricity, Biogas, Traditional Solid Biomass |
| Breakfast type | Normal, Heavy, Light |
| Lunch type | Normal, Heavy, Light |
| Dinner type | Normal, Heavy, Light |
| Snacks type | No visible selector. Code treats Snacks as Normal. |
| Dish assignment | Each selected dish is assigned one fuel from the selected fuel mix. |

Visible residential dish options loaded from the DB and grouped by template:

| Meal | Visible dish options |
|---|---|
| Breakfast | Tea (Spiced), Puttu, Appam, Idli, Dosa, Sambar, Kadala Curry, Idiyappam, Uppumavu, Pathiri, Oratty, Coconut Chutney, Potato Curry, Veg Kuruma, Vegetable Stew, Dal Curry, Green Pea Curry, Cherupayar Curry |
| Lunch | Meen Manga Mappas, Meen Pollichathu, Meen Manga Curry, Meen Puli Kuzhambu, Meen Moilee, Meen Vattichathu, Achinga Kaya Mezhukkupuratti, Cheera Avial, Vegetable Thoran, Rasam, Thoran, Aviyal, Mezhukku Puratty, Theeyal, Pachadi, Fish Curry, Egg Fry, Fish Fry, Pulissery, Achar, Pappad, Kootu Curry, Chicken Curry, Beef Curry, Pork Curry, Chammanthi, Mango Chammanthi, Parippu Curry, Olan, rice |
| Dinner | Kozhi Roast, Chicken Stew, Egg Curry, chappathi, dosa, appam, rice, Coconut Chutney, Kadala Curry, Potato Curry, Veg Kuruma, Vegetable Stew, Dal Curry, Green Pea Curry, Cherupayar Curry, Thoran, Aviyal, Mezhukku Puratty, Theeyal, Pachadi, Fish Curry, Egg Fry, Fish Fry, Pulissery, Achar, Pappad, Kootu Curry, Rasam |
| Snacks | Filter Coffee, Kattan Kaapi, Vada, Murukku, Banana Chips, Kappa (Tapioca), Ilayappam, Kozhukatta, pazham pori(banana fritter) |

Important implementation detail: the backend now merges selected dish names to DB rows by dish name plus selected meal category. This means Lunch `Fish Curry` and Dinner `Fish Curry` remain separate. If the DB contains duplicate rows with the same dish name inside the same category, those same-category duplicates can still expand until the UI/backend moves to `dish_id`.

### Residential Consumption-Based Options

Consumption-based residential cooking exposes:

| Primary fuel | Inputs |
|---|---|
| LPG | Cylinder size, refill interval in days, cylinder price |
| PNG | Input method bill/SCM/daily, monthly bill, monthly SCM, daily SCM |
| Grid electricity | Monthly cooking kWh |
| Traditional Solid Biomass | Biomass type and monthly kg |
| Mixed usage | LPG, PNG, electricity, and biomass usage sections |

### Residential Kitchen Options

| Option | Values |
|---|---|
| Kitchen scenario | Open Kitchen, Chimney, Exhaust Fan, No Exhaust |
| Cooking hours per day | 1 to 8, default 3 |
| Sensitive members | 0 to 10, default 1 |
| Budget preference | Low upfront cost, Balanced approach, Long-term savings, Environmental priority |

### Commercial Options

Commercial route sequence:

```text
/commercial_selection -> /commercial_institution_profile -> /commercial/kitchen-profile -> /commercial/submit_kitchen -> /commercial/energy_calculation -> /commercial_analysis
```

Commercial profile options:

| Option | Values |
|---|---|
| Institution type | School, Anganwadi, Hotel, Factory, Community Kitchen |
| District | Kerala district list from DB |
| Area type | Urban, Rural |
| Servings per day | 10 to 10000, default 250 |
| Working days per month | 1 to 31, default 26 |
| Budget priority | blank, Low, Medium, High, No constraints |
| Solar willingness | No, Maybe, Yes |
| Roof area | Shown when solar willingness is Maybe or Yes |
| Fuel price overrides | LPG commercial cylinder price, PNG rate, electricity tariff, biomass cost, grid CO2 factor |

Commercial energy options:

| Method | Options |
|---|---|
| Dish-based | Meal sections, commercial dishes filtered by institution type, selected fuel mix, and per-dish fuel assignment |
| LPG consumption | Domestic 14.2 kg and/or commercial 19 kg cylinder counts per month |
| PNG consumption | Monthly bill or monthly SCM plus rate |
| Grid electricity | Monthly cooking kWh plus rate |
| Biogas | Daily production in m3 and operating cost/month |
| Biomass | Monthly kg, biomass type, and cost/kg |
| Mixed usage | LPG commercial cylinders, PNG bill, electricity kWh, biomass kg |

Commercial kitchen options:

| Option | Values |
|---|---|
| Kitchen scenario | Commercial kitchen scenarios from DB |
| Cooking hours | 2 to 16, default 6 |
| Staff exposed | 1 to 50, default 2 |
| Budget preference | Low upfront cost, Balanced approach, Long-term savings, Environmental priority |

## Shared DB Values Used In Worked Residential Cases

The worked cases below use this common residential setup:

| Setting | Value |
|---|---:|
| Analysis type | Residential |
| Calculation method | Dish-based cooking |
| Household size | 4 members |
| District | Thiruvananthapuram |
| Area type | Urban |
| Solar willingness | No |
| Current selected fuel | LPG |
| Fuel assigned to every selected dish | LPG |
| Kitchen scenario | Open Kitchen |
| Cooking hours | 3 hours/day |
| Sensitive members | 1 |
| Budget preference | Balanced approach |
| Breakfast type | Normal |
| Lunch type | Heavy |
| Dinner type | Light |
| Snacks type | Normal by code |
| Total calories per person per day | 2400 kcal |
| Month length used in dish calculation | 30 days |

The app takes these values from DB or fallback logic:

| Value | Source | Current value |
|---|---|---:|
| Household cooking efficiency for 4 members | `group_cooking_efficiency` | 0.85 |
| Cooking wastage base | `system_parameters`, missing so fallback | 1.15 |
| Cooking wastage minimum | `system_parameters`, missing so fallback | 1.05 |
| LPG thermal efficiency | `thermal_efficiencies` | 0.60 |
| LPG CO2 factor | `emission_factors` | 0.24 kg/kWh input |
| LPG PM2.5 emission factor | `emission_factors` | 0.005 |
| LPG cylinder price | user/default form value from DB price | 922 Rs/cylinder |
| LPG domestic cylinder weight | `system_parameters` | 14.2 kg |
| LPG calorific value | `system_parameters` | 12.8 kWh/kg |
| PNG rate | DB/form default | 48 Rs/SCM |
| PNG calorific value | `system_parameters` | 10.2 kWh/SCM |
| Electricity tariff | DB/form default | 6.5 Rs/kWh |
| Biomass cost | DB/form default | 5 Rs/kg |
| Biomass energy content | `system_parameters` | 4.5 kWh/kg |
| PM2.5 concentration scale | `system_parameters`, missing so fallback | 5000 |
| PM2.5 low risk threshold | `system_parameters`, missing so fallback | 5 ug/m3 |
| Health baseline cooking hours | `system_parameters`, missing so fallback | 2 hours/day |
| Open Kitchen scenario factor | `kitchen_scenarios` | 0.04 |

Meal distribution values:

| Meal and intensity | DB percent used |
|---|---:|
| Breakfast Normal | 21 percent |
| Lunch Heavy | 38 percent |
| Dinner Light | 32 percent |
| Snacks Normal | 7 percent |

Fuel values used for current LPG setup:

```text
LPG cylinder energy = 14.2 kg * 12.8 kWh/kg = 181.76 kWh/cylinder
LPG cost per kWh input = 922 / 181.76 = 5.072623 Rs/kWh
```

Household wastage factor for 4 members:

```text
wastage = 1.15 - (0.05 * (household_size - 2) / 6)
wastage = 1.15 - (0.05 * 2 / 6)
wastage = 1.133333
```

## Formula Chain

### Dish Calories

For every selected DB row:

```text
dish_calories = calories_per_100g * minimum_portion_g / 100
```

### Meal Target Calories

For each selected meal category:

```text
target_category_calories = meal_percent * 2400 * household_size * 30
```

For the 4-member examples:

| Meal | Formula | Target kcal/month |
|---|---|---:|
| Breakfast Normal | 0.21 * 2400 * 4 * 30 | 60,480 |
| Lunch Heavy | 0.38 * 2400 * 4 * 30 | 109,440 |
| Dinner Light | 0.32 * 2400 * 4 * 30 | 92,160 |
| Snacks Normal | 0.07 * 2400 * 4 * 30 | 20,160 |

### Meal Scaling

For each meal category:

```text
category_scaling = target_category_calories / sum(selected_dish_calories_in_category)
```

### Monthly Useful Cooking Energy

For each selected DB row:

```text
row_monthly_useful_energy_kWh =
  energy_to_cook_kwh * category_scaling * household_efficiency * wastage
```

For these cases:

```text
row_monthly_useful_energy_kWh =
  energy_to_cook_kwh * category_scaling * 0.85 * 1.133333
```

Total monthly useful cooking energy:

```text
monthly_energy_kWh = sum(row_monthly_useful_energy_kWh)
```

### Fuel Input Energy

For current LPG:

```text
fuel_input_energy_kWh = monthly_energy_kWh / LPG_thermal_efficiency
fuel_input_energy_kWh = monthly_energy_kWh / 0.60
```

### Monthly Fuel Cost

```text
monthly_cost = fuel_input_energy_kWh * LPG_cost_per_kWh
monthly_cost = fuel_input_energy_kWh * 5.072623
```

### LPG Quantity

```text
monthly_LPG_kg = fuel_input_energy_kWh / 12.8
```

### Annual CO2 Emissions

Residential annual days are fixed at 365:

```text
daily_input_energy_kWh = fuel_input_energy_kWh / 30
annual_CO2_kg = daily_input_energy_kWh * 365 * LPG_CO2_factor
annual_CO2_kg = (fuel_input_energy_kWh / 30) * 365 * 0.24
```

### Overall Thermal Efficiency

```text
overall_efficiency_percent =
  monthly_useful_energy_kWh / total_input_energy_kWh * 100
```

For an all-LPG current setup this returns 60 percent.

### Health Exposure

For all-LPG examples:

```text
PM25_peak =
  LPG_PM25_factor * kitchen_scenario_factor * cooking_hours_factor * PM25_scale
```

Cooking hours factor:

```text
cooking_hours_factor = min(cooking_hours / 3, 1.5)
cooking_hours_factor = min(3 / 3, 1.5) = 1
```

Open Kitchen LPG PM2.5:

```text
PM25_peak = 0.005 * 0.04 * 1 * 5000 = 1.0 ug/m3
```

Risk score:

```text
PM25_peak 1.0 is inside DB 0-25 ug/m3 threshold.
Base risk score = 10.
Because PM25_peak <= fallback low risk threshold 5, no sensitive-member or duration penalties are added.
Final health risk score = 10.
Risk category = low.
```

### Environmental Grade

The grade lookup uses annual emissions per household member:

```text
annual_CO2_per_member = annual_CO2_kg / household_size
```

This value is compared to `environmental_grades`.

## Verified Exam-Style Methodology: Cases 1 To 4

This section is written in an exam-style format so the calculation can be checked line by line. Every number in these four cases was verified from the current code and database using:

- DB rows from `cooking_webapp.db` through `helper.db_helper`
- Formula flow from `residential_cooking.monthly_calories`
- Final result flow from `residential_cooking.calculate_dish_based`
- Analysis-stage health, alternatives, and recommendations from `helper.calculate_health_impact`, `helper.calculate_alternatives`, and `helper.generate_recommendations`

### Common Verified Values For All Four Cases

| Item | Actual source | Verified value |
|---|---|---:|
| Household size | user/profile input | 4 |
| Calories/person/day | `monthly_calories` default input | 2400 kcal |
| Month length for dish-based residential target | `monthly_calories` formula | 30 days |
| Household efficiency factor | `group_cooking_efficiency` via `get_household_size_efficiency(4)` | 0.85 |
| Wastage base | `COOKING_WASTAGE_BASE`, missing so code fallback | 1.15 |
| Wastage minimum | `COOKING_WASTAGE_MIN`, missing so code fallback | 1.05 |
| Wastage for 4 members | `1.15 - (0.05 * (4 - 2) / 6)` | 1.133333 |
| LPG thermal efficiency | `thermal_efficiencies` | 0.60 |
| LPG CO2 factor | `emission_factors` | 0.24 kg CO2/kWh input |
| LPG PM2.5 factor | `emission_factors` | 0.005 |
| LPG cylinder price | `fuel_unit_pricing`, Domestic Thiruvananthapuram | 922 Rs |
| LPG cylinder size | `system_parameters` / code default | 14.2 kg |
| LPG calorific value | `LPG_CALORIFIC_VALUE_KWH_PER_KG` | 12.8 kWh/kg |
| LPG cost/kWh input | `922 / (14.2 * 12.8)` | 5.072623 Rs/kWh |
| Open Kitchen factor | `kitchen_scenarios` | 0.04 |
| PM2.5 scale | `PM25_CONCENTRATION_SCALE`, missing so fallback | 5000 |

Meal target calories used in the worked cases:

| Meal | Intensity used | DB percentage | Formula | Target kcal/month |
|---|---|---:|---|---:|
| Breakfast | Normal | 0.21 | `0.21 * 2400 * 4 * 30` | 60,480 |
| Lunch | Heavy | 0.38 | `0.38 * 2400 * 4 * 30` | 109,440 |
| Dinner | Light | 0.32 | `0.32 * 2400 * 4 * 30` | 92,160 |
| Snacks | Normal | 0.07 | `0.07 * 2400 * 4 * 30` | 20,160 |

The exact formula chain used by the app is:

```text
1. dish_calories = calories_per_100g * minimum_portion_g / 100
2. meal_target_kcal = meal_percent * 2400 * household_size * 30
3. meal_scaling = meal_target_kcal / sum(dish_calories in that selected meal)
4. row_useful_energy_kWh = energy_to_cook_kwh * meal_scaling * household_efficiency * wastage
5. monthly_useful_energy_kWh = sum(row_useful_energy_kWh)
6. LPG_input_energy_kWh = monthly_useful_energy_kWh / 0.60
7. LPG_quantity_kg = LPG_input_energy_kWh / 12.8
8. monthly_cost_Rs = LPG_input_energy_kWh * 5.072623
9. annual_CO2_kg = (LPG_input_energy_kWh / 30) * 365 * 0.24
10. PM25_peak = 0.005 * 0.04 * min(3 / 3, 1.5) * 5000
```

Health substitution for these all-LPG, Open Kitchen, 3-hour cases:

```text
PM25_peak = 0.005 * 0.04 * 1 * 5000 = 1.000 ug/m3
PM25_peak <= 5, so no sensitive-member or duration penalty is added.
Health score = 10, category = low.
```

### Case 1: Breakfast Only, Idli Only, LPG

**Step 1: User flow selected**

```text
Residential -> Household size 4 -> Dish-based cooking -> LPG -> Breakfast -> Idli -> Analysis
```

**Step 2: Backend merge key**

```text
Selected key = (Dishes = "Idli", Category = "Breakfast")
Matched DB row = dish_id 6
```

**Step 3: DB row used**

| dish_id | Dish | Category | calories_per_100g | minimum_portion_g | energy_to_cook_kwh |
|---:|---|---|---:|---:|---:|
| 6 | Idli | Breakfast | 170 | 120 | 0.240 |

**Step 4: Dish calories**

```text
dish_calories = 170 * 120 / 100 = 204.000 kcal
```

**Step 5: Breakfast target and scaling**

```text
target_breakfast = 0.21 * 2400 * 4 * 30 = 60,480 kcal/month
actual_breakfast = 204.000 kcal
breakfast_scaling = 60,480 / 204.000 = 296.470588
```

**Step 6: Useful cooking energy**

```text
Idli_useful_energy =
0.240 * 296.470588 * 0.85 * 1.133333
= 68.544 kWh/month
```

**Step 7: LPG input energy, quantity, cost, emissions**

```text
LPG_input_energy = 68.544 / 0.60 = 114.240 kWh/month
LPG_quantity = 114.240 / 12.8 = 8.925 kg/month
monthly_cost = 114.240 * 5.072623 = 579.496 Rs/month
annual_CO2 = (114.240 / 30) * 365 * 0.24 = 333.581 kg/year
overall_efficiency = 68.544 / 114.240 * 100 = 60.000 percent
CO2_per_member = 333.581 / 4 = 83.395 kg/member/year
```

**Step 8: Final output**

| Metric | Verified result |
|---|---:|
| Monthly useful energy | 68.544 kWh |
| LPG input energy | 114.240 kWh |
| LPG quantity | 8.925 kg |
| Monthly cost | 579.496 Rs |
| Annual CO2 | 333.581 kg |
| Overall efficiency | 60.000 percent |
| Environmental grade | A+ |
| PM2.5 peak | 1.000 ug/m3 |
| Health score | 10 low |

**Step 9: Alternatives and recommendation output**

| Fuel | Monthly cost Rs | Annual CO2 kg | Efficiency percent | Health score | Grade |
|---|---:|---:|---:|---:|---|
| LPG | 579.496 | 333.581 | 60.000 | 10 | A+ |
| PNG | 460.800 | 250.186 | 70.000 | 10 | A+ |
| Grid electricity | 495.040 | 602.299 | 90.000 | 10 | A |
| Biogas | 484.756 | 454.883 | 55.000 | 25 | A |
| Traditional Solid Biomass | 138.473 | 606.511 | 55.000 | 80 | A |

Top recommendations:

```text
1. PNG = 90.0
2. LPG = 80.0
3. Grid electricity = 80.0
```

### Case 2: One Dish Each From Breakfast, Lunch, Dinner, Snacks, All LPG

**Step 1: User flow selected**

```text
Residential -> Household size 4 -> Dish-based cooking -> LPG
Breakfast: Idli
Lunch: Fish Curry
Dinner: chappathi
Snacks: Vada
```

**Step 2: Backend merge keys**

The backend matches by dish name plus category. This is important for `Fish Curry`.

| User selected meal | User selected dish | Merge key | Matched dish_id |
|---|---|---|---:|
| Breakfast | Idli | `(Idli, Breakfast)` | 6 |
| Lunch | Fish Curry | `(Fish Curry, Lunch)` | 51 |
| Dinner | chappathi | `(chappathi, Dinner)` | 67 |
| Snacks | Vada | `(Vada, Snacks)` | 20 |

`Fish Curry` also exists as dish_id 84 in Dinner, but it is not used here because the selected category is Lunch.

**Step 3: DB values and dish calories**

| Meal | dish_id | Dish | calories_per_100g | portion g | energy_to_cook_kwh | Dish calories formula | Dish kcal |
|---|---:|---|---:|---:|---:|---|---:|
| Breakfast | 6 | Idli | 170 | 120 | 0.240 | `170 * 120 / 100` | 204.0 |
| Lunch | 51 | Fish Curry | 110 | 200 | 0.280 | `110 * 200 / 100` | 220.0 |
| Dinner | 67 | chappathi | 230 | 100 | 0.360 | `230 * 100 / 100` | 230.0 |
| Snacks | 20 | Vada | 308 | 80 | 0.288 | `308 * 80 / 100` | 246.4 |

**Step 4: Meal scaling and useful energy**

| Meal | Target kcal | Actual kcal | Scaling formula | Scaling | Useful energy formula | Useful kWh |
|---|---:|---:|---|---:|---|---:|
| Breakfast | 60,480 | 204.0 | `60480 / 204.0` | 296.470588 | `0.240 * 296.470588 * 0.85 * 1.133333` | 68.544 |
| Lunch | 109,440 | 220.0 | `109440 / 220.0` | 497.454545 | `0.280 * 497.454545 * 0.85 * 1.133333` | 134.180 |
| Dinner | 92,160 | 230.0 | `92160 / 230.0` | 400.695652 | `0.360 * 400.695652 * 0.85 * 1.133333` | 138.961 |
| Snacks | 20,160 | 246.4 | `20160 / 246.4` | 81.818182 | `0.288 * 81.818182 * 0.85 * 1.133333` | 22.700 |

**Step 5: Total useful energy**

```text
monthly_useful_energy =
68.544 + 134.180 + 138.961 + 22.700
= 364.385 kWh/month
```

**Step 6: LPG input energy, quantity, cost, emissions**

```text
LPG_input_energy = 364.385 / 0.60 = 607.308 kWh/month
LPG_quantity = 607.308 / 12.8 = 47.446 kg/month
monthly_cost = 607.308 * 5.072623 = 3,080.646 Rs/month
annual_CO2 = (607.308 / 30) * 365 * 0.24 = 1,773.340 kg/year
overall_efficiency = 364.385 / 607.308 * 100 = 60.000 percent
CO2_per_member = 1,773.340 / 4 = 443.335 kg/member/year
```

**Step 7: Final output**

| Metric | Verified result |
|---|---:|
| Monthly useful energy | 364.385 kWh |
| LPG input energy | 607.308 kWh |
| LPG quantity | 47.446 kg |
| Monthly cost | 3,080.646 Rs |
| Annual CO2 | 1,773.340 kg |
| Overall efficiency | 60.000 percent |
| Environmental grade | C |
| PM2.5 peak | 1.000 ug/m3 |
| Health score | 10 low |

**Step 8: Alternatives and recommendation output**

| Fuel | Monthly cost Rs | Annual CO2 kg | Efficiency percent | Health score | Grade |
|---|---:|---:|---:|---:|---|
| LPG | 3,080.646 | 1,773.340 | 60.000 | 10 | C |
| PNG | 2,449.647 | 1,330.005 | 70.000 | 10 | B |
| Grid electricity | 2,631.669 | 3,201.864 | 90.000 | 10 | D |
| Biogas | 2,093.056 | 2,418.191 | 55.000 | 25 | C |
| Traditional Solid Biomass | 736.131 | 3,224.255 | 55.000 | 80 | D |

Top recommendations:

```text
1. PNG = 80.0
2. LPG = 70.0
3. Grid electricity = 67.5
```

### Case 3: All Visible Breakfast, Lunch, Dinner, Snacks Dishes, All LPG

**Step 1: User flow selected**

```text
Residential -> Household size 4 -> Dish-based cooking -> LPG
User selects all visible dishes from Breakfast, Lunch, Dinner, and Snacks.
```

**Step 2: Backend merge verification**

The backend merge is by `Dishes + Category`. Cross-meal duplicate names do not multiply rows. Same-category duplicate DB rows can still appear until the UI/backend uses `dish_id`.

| Meal | Visible UI dish names selected | Backend DB rows after merge |
|---|---:|---:|
| Breakfast | 18 | 21 |
| Lunch | 30 | 31 |
| Dinner | 28 | 28 |
| Snacks | 9 | 9 |
| Total | 85 | 89 |

**Step 3: Meal-level calculations from actual DB rows**

Each backend DB row uses this same formula:

```text
row_useful_energy = energy_to_cook_kwh * meal_scaling * 0.85 * 1.133333
```

Rows with `energy_to_cook_kwh = 0` are counted in calories but add `0` useful kWh.

| Meal | Target kcal | Actual kcal from DB rows | Scaling formula | Scaling | Zero-energy rows | Useful kWh |
|---|---:|---:|---|---:|---:|---:|
| Breakfast | 60,480 | 3,892.3 | `60480 / 3892.3` | 15.538371 | 0 | 88.345 |
| Lunch | 109,440 | 6,327.5 | `109440 / 6327.5` | 17.295930 | 1 | 128.695 |
| Dinner | 92,160 | 5,099.8 | `92160 / 5099.8` | 18.071297 | 1 | 134.569 |
| Snacks | 20,160 | 2,338.8 | `20160 / 2338.8` | 8.619805 | 0 | 21.274 |

**Step 4: Total useful energy**

```text
monthly_useful_energy =
88.345 + 128.695 + 134.569 + 21.274
= 372.883 kWh/month
```

**Step 5: LPG input energy, quantity, cost, emissions**

```text
LPG_input_energy = 372.883 / 0.60 = 621.472 kWh/month
LPG_quantity = 621.472 / 12.8 = 48.553 kg/month
monthly_cost = 621.472 * 5.072623 = 3,152.496 Rs/month
annual_CO2 = (621.472 / 30) * 365 * 0.24 = 1,814.700 kg/year
overall_efficiency = 372.883 / 621.472 * 100 = 60.000 percent
CO2_per_member = 1,814.700 / 4 = 453.675 kg/member/year
```

**Step 6: Final output**

| Metric | Verified result |
|---|---:|
| Monthly useful energy | 372.883 kWh |
| LPG input energy | 621.472 kWh |
| LPG quantity | 48.553 kg |
| Monthly cost | 3,152.496 Rs |
| Annual CO2 | 1,814.700 kg |
| Overall efficiency | 60.000 percent |
| Environmental grade | C |
| PM2.5 peak | 1.000 ug/m3 |
| Health score | 10 low |

**Step 7: Alternatives and recommendation output**

| Fuel | Monthly cost Rs | Annual CO2 kg | Efficiency percent | Health score | Grade |
|---|---:|---:|---:|---:|---|
| LPG | 3,152.496 | 1,814.700 | 60.000 | 10 | C |
| PNG | 2,506.780 | 1,361.025 | 70.000 | 10 | B |
| Grid electricity | 2,693.047 | 3,276.541 | 90.000 | 10 | D |
| Biogas | 2,139.257 | 2,474.590 | 55.000 | 25 | C |
| Traditional Solid Biomass | 753.300 | 3,299.454 | 55.000 | 80 | D |

Top recommendations:

```text
1. PNG = 80.0
2. LPG = 70.0
3. Grid electricity = 67.5
```

### Case 4: Fish Curry Category-Matching Verification

This case verifies the corrected backend behavior:

```text
Lunch Fish Curry only -> count Lunch Fish Curry once
Dinner Fish Curry only -> count Dinner Fish Curry once
Lunch + Dinner Fish Curry -> count two rows, one Lunch and one Dinner
```

**Step 1: Actual DB rows for Fish Curry**

| dish_id | Dish | Category | calories_per_100g | minimum_portion_g | energy_to_cook_kwh | Dish calories |
|---:|---|---|---:|---:|---:|---:|
| 51 | Fish Curry | Lunch | 110 | 200 | 0.280 | 220.0 |
| 84 | Fish Curry | Dinner | 110 | 200 | 0.280 | 220.0 |

**Step 2: Subcase A - user selects Lunch Fish Curry only**

```text
Merge key = (Fish Curry, Lunch)
Matched DB rows = 1
Matched dish_id = 51
target_lunch = 0.38 * 2400 * 4 * 30 = 109,440 kcal
actual_lunch = 220.0 kcal
lunch_scaling = 109,440 / 220.0 = 497.454545
lunch_useful_energy = 0.280 * 497.454545 * 0.85 * 1.133333 = 134.180 kWh
LPG_input_energy = 134.180 / 0.60 = 223.633 kWh
monthly_cost = 223.633 * 5.072623 = 1,134.408 Rs
annual_CO2 = (223.633 / 30) * 365 * 0.24 = 653.010 kg
```

Subcase A output:

| Metric | Verified result |
|---|---:|
| Backend rows | 1 |
| Monthly useful energy | 134.180 kWh |
| LPG input energy | 223.633 kWh |
| LPG quantity | 17.471 kg |
| Monthly cost | 1,134.408 Rs |
| Annual CO2 | 653.010 kg |
| Environmental grade | A |

**Step 3: Subcase B - user selects Dinner Fish Curry only**

```text
Merge key = (Fish Curry, Dinner)
Matched DB rows = 1
Matched dish_id = 84
target_dinner = 0.32 * 2400 * 4 * 30 = 92,160 kcal
actual_dinner = 220.0 kcal
dinner_scaling = 92,160 / 220.0 = 418.909091
dinner_useful_energy = 0.280 * 418.909091 * 0.85 * 1.133333 = 112.994 kWh
LPG_input_energy = 112.994 / 0.60 = 188.323 kWh
monthly_cost = 188.323 * 5.072623 = 955.291 Rs
annual_CO2 = (188.323 / 30) * 365 * 0.24 = 549.903 kg
```

Subcase B output:

| Metric | Verified result |
|---|---:|
| Backend rows | 1 |
| Monthly useful energy | 112.994 kWh |
| LPG input energy | 188.323 kWh |
| LPG quantity | 14.713 kg |
| Monthly cost | 955.291 Rs |
| Annual CO2 | 549.903 kg |
| Environmental grade | A |

**Step 4: Subcase C - user selects Fish Curry in Lunch and Dinner**

```text
Merge keys = (Fish Curry, Lunch) and (Fish Curry, Dinner)
Matched DB rows = 2
Matched dish_ids = 51 and 84
monthly_useful_energy = 134.180 + 112.994 = 247.174 kWh
LPG_input_energy = 247.174 / 0.60 = 411.956 kWh
LPG_quantity = 411.956 / 12.8 = 32.184 kg
monthly_cost = 411.956 * 5.072623 = 2,089.699 Rs
annual_CO2 = (411.956 / 30) * 365 * 0.24 = 1,202.913 kg
```

Subcase C output:

| Metric | Verified result |
|---|---:|
| Backend rows | 2 |
| Monthly useful energy | 247.174 kWh |
| LPG input energy | 411.956 kWh |
| LPG quantity | 32.184 kg |
| Monthly cost | 2,089.699 Rs |
| Annual CO2 | 1,202.913 kg |
| Environmental grade | B |
| PM2.5 peak | 1.000 ug/m3 |
| Health score | 10 low |

**Step 5: Case 4 verification conclusion**

```text
Lunch only: 1 backend row, dish_id 51.
Dinner only: 1 backend row, dish_id 84.
Lunch + Dinner: 2 backend rows, dish_id 51 + dish_id 84.
```

This confirms the current backend counts the same dish name separately only when the selected meal category is also different.

Recommendation output for Subcase C:

```text
1. PNG = 85.0
2. LPG = 70.0
3. Grid electricity = 67.5
```

## Alternative Fuel Formula Details

For each active fuel, `helper.calculate_alternatives` evaluates the same useful cooking energy with that fuel's efficiency and cost.

```text
alternative_input_energy = monthly_useful_energy / alternative_efficiency
alternative_monthly_cost = alternative_input_energy * alternative_cost_per_kWh
alternative_annual_CO2 = (alternative_input_energy / 30) * 365 * alternative_CO2_factor
```

Fuel cost conversion examples:

| Fuel | Formula | Cost per kWh input |
|---|---|---:|
| LPG | 922 / (14.2 * 12.8) | 5.072623 |
| PNG | 48 / 10.2 | 4.705882 |
| Grid electricity | tariff directly | 6.500000 |
| Biomass | 5 / 4.5 | 1.111111 |
| Biogas | DB/user cost path, fallback handling | depends on DB/user inputs |

Solar+BESS is an active fuel in DB, but residential alternatives skip it unless:

```text
household_data.solar_willingness == "Yes"
```

The worked cases use `No`, so Solar+BESS does not appear in the alternatives table.

## Recommendation Formula Details

Recommendations are generated from the alternatives using balanced DB weights:

| Component | Weight |
|---|---:|
| Health | 0.40 |
| Environmental | 0.25 |
| Economic | 0.25 |
| Practicality | 0.10 |

The score combines:

```text
final_score =
  health_score_component * 0.40 +
  environmental_score_component * 0.25 +
  economic_score_component * 0.25 +
  practicality_score_component * 0.10
```

The current setup and alternatives are then ranked by final score. The displayed recommendations in the worked cases above are the top three.

## Current Implementation Notes

1. Dish-based residential calculation is calorie-normalized. Selecting one dish in a meal category does not mean only one physical serving is cooked. The app scales that dish to satisfy that meal category's monthly calorie target for the household.
2. The selected "main fuel" in dish-based mode is represented by assigning that fuel to each selected dish. In the examples above, every selected dish is assigned LPG.
3. Dish-based merging now uses `Dishes` plus selected meal category, so Lunch `Fish Curry` and Dinner `Fish Curry` are counted independently. Same-category duplicate DB rows can still increase backend rows until the app moves to `dish_id`.
4. Some system parameters are not present in `system_parameters`, so the code uses hardcoded fallbacks. The important fallbacks in these examples are cooking wastage base, cooking wastage minimum, PM2.5 scale, PM2.5 low-risk threshold, health sensitive penalty, health duration penalty, health baseline hours, and PNG fixed charges.
5. Health PM2.5 in the all-LPG Open Kitchen examples remains low because LPG PM2.5 factor is very small and Open Kitchen scenario factor is 0.04.
6. Environmental grade is based on annual CO2 per household member, not total household annual CO2.
7. PDF generation and feedback collection do not alter the calculation results.
