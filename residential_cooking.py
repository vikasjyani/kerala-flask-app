import pandas as pd
import json
from helper import (
    db_helper, basic_calories, calculate_lpg_consumption_from_refill,
    calculate_png_consumption_from_bill, calculate_png_bill_and_consumption,
    calculate_co2_emissions, calculate_fuel_emissions_and_costs,
    save_cooking_analysis, DEFAULT_EFFICIENCIES, EMISSION_FACTORS,
    LPG_SUBSIDY_AMOUNT, LPG_CALORIFIC_VALUE, LPG_ENERGY_PER_CYLINDER
)
import helper
from debug_logger import get_logger

# =================================================================
# DISH-BASED CALCULATION FUNCTIONS
# =================================================================

def get_household_size_factor(household_size):
    """
    Calculate energy efficiency factor based on household size (economies of scale).
    
    Args:
        household_size (int): Number of members in the household.
    
    Returns:
        float: Efficiency factor (e.g., 1.0 for single person, lower for larger households).
    """
    return db_helper.get_household_size_efficiency(household_size)

def monthly_calories(df, no_of_persons, total_calories_per_person=2400, 
                    breakfast='Normal', lunch='Heavy', dinner='Light'):
    """
    Calculate monthly energy requirements based on caloric needs and meal patterns.

    Args:
        df: DataFrame containing dish data (basic_calories must be calculated).
        no_of_persons (int): Number of people in the household.
        total_calories_per_person (int, optional): Daily calorie requirement per person. Defaults to 2400.
        breakfast (str, optional): Breakfast intensity ('Normal', 'Heavy', 'Light'). Defaults to 'Normal'.
        lunch (str, optional): Lunch intensity. Defaults to 'Heavy'.
        dinner (str, optional): Dinner intensity. Defaults to 'Light'.

    Returns:
        pd.DataFrame: DataFrame with calculated 'Final_Energy_Value' for each dish.
    """
    # First calculate basic calories
    df_calc = basic_calories(df)
    
    # Get household size efficiency factor
    household_efficiency = get_household_size_factor(no_of_persons)

    # Load meal type calorie distribution from database
    breakfast_dist = db_helper.get_meal_distribution(breakfast)
    lunch_dist = db_helper.get_meal_distribution(lunch)
    dinner_dist = db_helper.get_meal_distribution(dinner)
    snacks_dist = db_helper.get_meal_distribution('Normal')  # Snacks is fixed

    # Get calorie percentages for each meal
    breakfast_cal = breakfast_dist.get('Breakfast', 0.21)
    lunch_cal = lunch_dist.get('Lunch', 0.32)
    dinner_cal = dinner_dist.get('Dinner', 0.40)
    snacks_cal = snacks_dist.get('Snacks', 0.07)
    
    # Monthly total calories for each category
    monthly_factor = 30  # days per month
    total_breakfast_calories = breakfast_cal * total_calories_per_person * no_of_persons * monthly_factor
    total_lunch_calories = lunch_cal * total_calories_per_person * no_of_persons * monthly_factor
    total_dinner_calories = dinner_cal * total_calories_per_person * no_of_persons * monthly_factor
    total_snacks_calories = snacks_cal * total_calories_per_person * no_of_persons * monthly_factor
    
    # Base wastage factor (reduced for larger households) - load from database
    base_wastage = db_helper.get_system_parameter('COOKING_WASTAGE_BASE', 1.15)
    min_wastage = db_helper.get_system_parameter('COOKING_WASTAGE_MIN', 1.05)
    adjusted_wastage = base_wastage - (0.05 * (no_of_persons - 2) / 6)
    wastage_factor = max(min_wastage, adjusted_wastage)  # Minimum wastage
    
    # Category target mapping
    category_targets = {
        'Breakfast': total_breakfast_calories,
        'Lunch': total_lunch_calories,
        'Dinner': total_dinner_calories,
        'Snacks': total_snacks_calories
    }
    
    # Calculate final energy values for each category
    for category in df_calc['Category'].unique():
        if category not in category_targets:
            continue
        
        # Get target calories for this category
        target_calories = category_targets[category]
        
        # Get actual calories from selected dishes
        category_mask = df_calc['Category'] == category
        actual_calories = df_calc.loc[category_mask, 'total_calories'].sum()
        
        if actual_calories > 0:
            # Scaling factor to meet calorie targets
            scaling_factor = target_calories / actual_calories
            
            # Energy column name
            if 'energy_to_cook_kwh' in df_calc.columns:
                energy_col = 'energy_to_cook_kwh'
            else:
                energy_col = 'Energy_to_cook_Minimum_Dish _Quantity'
            
            # Check if energy column exists
            if energy_col not in df_calc.columns:
                possible_energy_cols = [col for col in df_calc.columns if 'Energy' in col and 'cook' in col]
                if possible_energy_cols:
                    energy_col = possible_energy_cols[0]
                else:
                    continue
            
            # Apply scaling, household efficiency, and wastage
            df_calc.loc[category_mask, 'Final_Energy_Value'] = (
                df_calc.loc[category_mask, energy_col] * 
                scaling_factor * 
                household_efficiency *  # Economies of scale
                wastage_factor         # Cooking wastage
            )
            
            # Log the calculation for this category
            logger = get_logger()
            logger.log_calculation(
                f"{category} Calculation",
                "energy × scaling × efficiency × wastage",
                {
                    "target_calories": f"{target_calories:,.0f} kcal",
                    "actual_calories": f"{actual_calories:,.0f} kcal",
                    "scaling_factor": f"{scaling_factor:.4f}",
                    "household_efficiency": f"{household_efficiency:.4f}",
                    "wastage_factor": f"{wastage_factor:.4f}",
                    "energy_col": energy_col
                },
                f"Total Energy: {df_calc.loc[category_mask, 'Final_Energy_Value'].sum():.4f} kWh"
            )
    
    return df_calc

def calculate_consumption_based(data, household_data, kitchen_data, household_id):
    """
    Calculate energy consumption based on fuel bills/usage (Top-down approach).

    Args:
        data (dict): Form data containing fuel usage details (refill days, monthly bill, etc.).
        household_data (dict): Household profile data (subsidy status, tariff, etc.).
        kitchen_data (dict): Kitchen profile data.
        household_id (str): Unique identifier for the household.

    Returns:
        dict: Calculation results including monthly energy (kWh), cost, emissions, and fuel details.
    """
    logger = get_logger()
    logger.log_subsection("CONSUMPTION-BASED CALCULATION")

    primary_fuel = data.get('primary_fuel')

    logger.log_input("Primary Fuel", primary_fuel)
    logger.log_data("Household Data", household_data)

    result = {
        'monthly_energy_kwh': 0,
        'monthly_cost': 0,
        'annual_emissions': 0,
        'fuel_details': {}
    }

    if primary_fuel == 'LPG':
        logger.log_step("Calculating LPG consumption from refill data")

        refill_days = float(data.get('refill_days', 30))
        # Priority: User input > database > fallback
        user_price = data.get('cylinder_price')
        if user_price and float(user_price) > 0:
            cylinder_price = float(user_price)
        else:
            lpg_price = db_helper.get_lpg_pricing(data.get('district', 'Thiruvananthapuram'), 'Domestic')
            cylinder_price = float(lpg_price.get('subsidized_price', 850)) if lpg_price else db_helper.get_system_parameter('LPG_DOMESTIC_PRICE', 850)
        cylinder_size = float(data.get('cylinder_size', 14.2))

        logger.log_input("Refill Days", f"{refill_days} days")
        logger.log_input("Cylinder Price", f"Rs {cylinder_price:.2f}")
        logger.log_input("Cylinder Size", f"{cylinder_size} kg")

        lpg_data = calculate_lpg_consumption_from_refill(refill_days, cylinder_size)
        efficiency = DEFAULT_EFFICIENCIES.get('LPG', 0.60)

        logger.log_data("LPG Data from calculation", lpg_data)
        logger.log_input("LPG Thermal Efficiency", f"{efficiency * 100}%")

        logger.log_calculation(
            "Monthly Energy (with efficiency)",
            "monthly_energy_kwh = monthly_energy_gross × efficiency",
            {
                "monthly_energy_gross": f"{lpg_data['monthly_energy_kwh']:.2f} kWh",
                "efficiency": f"{efficiency} ({efficiency*100}%)"
            },
            f"{lpg_data['monthly_energy_kwh'] * efficiency:.2f}",
            "kWh"
        )
        result['monthly_energy_kwh'] = lpg_data['monthly_energy_kwh'] * efficiency

        effective_price = cylinder_price
        has_subsidy = household_data.get('lpg_subsidy') == 'Yes'
        logger.log_input("LPG Subsidy Status", "Yes" if has_subsidy else "No")

        if has_subsidy:
            logger.log_calculation(
                "Effective Cylinder Price (with subsidy)",
                "effective_price = cylinder_price - subsidy_amount",
                {
                    "cylinder_price": f"Rs {cylinder_price:.2f}",
                    "subsidy_amount": f"Rs {LPG_SUBSIDY_AMOUNT:.2f}"
                },
                f"Rs {max(0, cylinder_price - LPG_SUBSIDY_AMOUNT):.2f}"
            )
            effective_price = max(0, cylinder_price - LPG_SUBSIDY_AMOUNT)

        logger.log_calculation(
            "Monthly Cost",
            "monthly_cost = cylinders_per_month × effective_price",
            {
                "cylinders_per_month": f"{lpg_data['cylinders_per_month']:.2f}",
                "effective_price": f"Rs {effective_price:.2f}"
            },
            f"Rs {lpg_data['cylinders_per_month'] * effective_price:.2f}"
        )
        result['monthly_cost'] = lpg_data['cylinders_per_month'] * effective_price

        logger.log_calculation(
            "Annual CO₂ Emissions",
            "annual_emissions = daily_energy_kwh × emission_factor × 365",
            {
                "daily_energy_kwh": f"{lpg_data['daily_energy_kwh']:.2f} kWh",
                "emission_factor": f"{EMISSION_FACTORS['LPG']} kg CO₂/kWh"
            },
            f"{calculate_co2_emissions(lpg_data['daily_energy_kwh'], EMISSION_FACTORS['LPG']):.2f}",
            "kg CO₂/year"
        )
        result['annual_emissions'] = calculate_co2_emissions(
            lpg_data['daily_energy_kwh'], EMISSION_FACTORS['LPG']
        )

        # Standardize fuel_details to match multi-fuel structure for analysis.html
        result['fuel_details'] = {
            'LPG': {
                'quantity': lpg_data['cylinders_per_month'],
                'unit': 'Cylinders',
                'energy_delivered': result['monthly_energy_kwh'], # Useful energy
                'monthly_cost': result['monthly_cost'],
                'annual_emissions': result['annual_emissions'],
                'type': 'LPG',
                'cylinders_per_month': lpg_data['cylinders_per_month'],
                'energy_per_cylinder': lpg_data['energy_per_cylinder'],
                'refill_days': refill_days,
                'cylinder_price': cylinder_price,
                'cylinder_size': cylinder_size
            }
        }
        logger.log_data("LPG Result Details", result['fuel_details'])
    
    elif primary_fuel == 'PNG':
        logger.log_step("Calculating PNG consumption")
        png_input_method = data.get('png_input_method')
        logger.log_input("PNG Input Method", png_input_method)

        # Get Domestic PNG rate from database (required).
        png_price_data = db_helper.get_png_pricing(district='All', category='Domestic')
        if not png_price_data:
            raise ValueError("PNG pricing not found in database. Please ensure fuel_unit_pricing table has PNG data.")
        png_rate = float(png_price_data['price_per_scm'])
        logger.log_input("PNG Rate (Domestic)", f"Rs {png_rate:.2f}/SCM")

        if png_input_method == 'bill':
            monthly_bill = float(data.get('monthly_bill', 1500))
            logger.log_input("Monthly Bill", f"Rs {monthly_bill:.2f}")
            png_data = calculate_png_consumption_from_bill(monthly_bill, rate_per_scm=png_rate)
        elif png_input_method == 'scm':
            monthly_scm = float(data.get('monthly_scm', 50))
            logger.log_input("Monthly SCM", f"{monthly_scm} SCM")
            png_data = calculate_png_bill_and_consumption(monthly_scm, rate_per_scm=png_rate)
        else:  # daily
            daily_scm = float(data.get('daily_scm', 1.5))
            logger.log_input("Daily SCM", f"{daily_scm} SCM/day")
            monthly_scm = daily_scm * 30
            png_data = calculate_png_bill_and_consumption(monthly_scm, rate_per_scm=png_rate)

        efficiency = DEFAULT_EFFICIENCIES.get('PNG', 0.70)
        logger.log_data("PNG Data from calculation", png_data)
        logger.log_input("PNG Thermal Efficiency", f"{efficiency * 100}%")

        result['monthly_energy_kwh'] = png_data['monthly_energy_kwh'] * efficiency
        result['monthly_cost'] = png_data['total_bill']

        logger.log_result("Monthly Cost", f"Rs {png_data['total_bill']:.2f}")
        logger.log_data("Bill Breakdown", png_data['bill_breakdown'])

        result['annual_emissions'] = calculate_co2_emissions(
            png_data['daily_energy_kwh'], EMISSION_FACTORS['PNG']
        )
        logger.log_result("Annual CO₂ Emissions", result['annual_emissions'], "kg CO₂/year")

        result['fuel_details'] = {
            'PNG': {
                'quantity': png_data['monthly_scm_consumption'],
                'unit': 'SCM',
                'energy_delivered': result['monthly_energy_kwh'],
                'monthly_cost': result['monthly_cost'],
                'annual_emissions': result['annual_emissions'],
                'type': 'PNG',
                'monthly_scm': png_data['monthly_scm_consumption'],
                'bill_breakdown': png_data['bill_breakdown'],
                'input_method': data.get('png_input_method')
            }
        }
        logger.log_data("PNG Result Details", result['fuel_details'])
    
    elif primary_fuel == 'Grid electricity':
        logger.log_step("Calculating Grid Electricity consumption")

        monthly_kwh = float(data.get('monthly_kwh_cooking', 80))
        efficiency = DEFAULT_EFFICIENCIES.get('Grid electricity', 0.90)
        tariff = household_data.get('electricity_tariff', 6.5)

        logger.log_input("Monthly kWh for Cooking", f"{monthly_kwh} kWh")
        logger.log_input("Electrical Efficiency", f"{efficiency * 100}%")
        logger.log_input("Electricity Tariff", f"Rs {tariff:.2f}/kWh")

        result['monthly_energy_kwh'] = monthly_kwh * efficiency

        logger.log_calculation(
            "Monthly Cost",
            "monthly_cost = monthly_kwh × tariff",
            {
                "monthly_kwh": f"{monthly_kwh} kWh",
                "tariff": f"Rs {tariff}/kWh"
            },
            f"Rs {monthly_kwh * tariff:.2f}"
        )
        result['monthly_cost'] = monthly_kwh * tariff

        result['annual_emissions'] = calculate_co2_emissions(
            monthly_kwh / 30, EMISSION_FACTORS['Grid electricity']
        )
        logger.log_result("Annual CO₂ Emissions", result['annual_emissions'], "kg CO₂/year")

        result['fuel_details'] = {
            'Grid electricity': {
                'quantity': monthly_kwh,
                'unit': 'Units',
                'energy_delivered': result['monthly_energy_kwh'],
                'monthly_cost': result['monthly_cost'],
                'annual_emissions': result['annual_emissions'],
                'type': 'Grid electricity',
                'monthly_kwh': monthly_kwh,
                'tariff': tariff
            }
        }
        logger.log_data("Grid Electricity Result Details", result['fuel_details'])

    elif primary_fuel == 'Traditional Solid Biomass':
        logger.log_step("Calculating Traditional Biomass consumption")

        monthly_kg = float(data.get('monthly_kg', 100))
        biomass_type = data.get('biomass_type', 'Firewood')

        logger.log_input("Monthly Biomass Consumption", f"{monthly_kg} kg")
        logger.log_input("Biomass Type", biomass_type)

        # Biomass energy content and efficiency - load from database
        biomass_energy_content = float(db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5))
        biomass_cost_per_kg = float(db_helper.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0))
        efficiency = DEFAULT_EFFICIENCIES.get('Traditional Solid Biomass', 0.18)

        logger.log_input("Biomass Energy Content", f"{biomass_energy_content} kWh/kg")
        logger.log_input("Biomass Cost", f"Rs {biomass_cost_per_kg}/kg")
        logger.log_input("Biomass Thermal Efficiency", f"{efficiency * 100}%")

        monthly_energy_required = monthly_kg * biomass_energy_content
        result['monthly_energy_kwh'] = monthly_energy_required * efficiency

        logger.log_calculation(
            "Monthly Cost",
            "monthly_cost = monthly_kg × cost_per_kg",
            {
                "monthly_kg": f"{monthly_kg} kg",
                "cost_per_kg": f"Rs {biomass_cost_per_kg}/kg"
            },
            f"Rs {monthly_kg * biomass_cost_per_kg:.2f}"
        )
        result['monthly_cost'] = monthly_kg * biomass_cost_per_kg

        result['annual_emissions'] = calculate_co2_emissions(
            monthly_energy_required / 30, EMISSION_FACTORS['Traditional Solid Biomass']
        )
        logger.log_result("Annual CO₂ Emissions", result['annual_emissions'], "kg CO₂/year")
        
        result['fuel_details'] = {
            'Traditional Solid Biomass': {
                'quantity': monthly_kg,
                'unit': 'kg',
                'energy_delivered': result['monthly_energy_kwh'],
                'monthly_cost': result['monthly_cost'],
                'annual_emissions': result['annual_emissions'],
                'type': 'Traditional Solid Biomass',
                'monthly_kg': monthly_kg,
                'biomass_type': biomass_type
            }
        }
        logger.log_data("Biomass Result Details", result['fuel_details'])

    elif primary_fuel == 'Mixed usage':
        logger.log_step("Calculating Mixed Fuel consumption")
        fuel_details = {}
        total_energy = 0
        total_cost = 0
        total_emissions = 0
        fuels_used = []

        # LPG
        if data.get('mixed_use_lpg') in [True, 'true', 'on', '1', 1]:
            logger.log_step("Processing LPG in mixed mode")
            refill_days = float(data.get('mixed_refill_days', 45))
            cylinder_size = 14.2  # Default domestic cylinder
            # Get price from database
            lpg_price = db_helper.get_lpg_pricing(data.get('district', 'Thiruvananthapuram'), 'Domestic')
            cylinder_price = float(lpg_price.get('subsidized_price', 850)) if lpg_price else db_helper.get_system_parameter('LPG_DOMESTIC_PRICE', 850)

            lpg_data = calculate_lpg_consumption_from_refill(refill_days, cylinder_size)
            efficiency = DEFAULT_EFFICIENCIES.get('LPG', 0.60)

            energy = lpg_data['monthly_energy_kwh'] * efficiency
            cost = lpg_data['cylinders_per_month'] * cylinder_price
            emissions = calculate_co2_emissions(lpg_data['daily_energy_kwh'], EMISSION_FACTORS['LPG'])

            total_energy += energy
            total_cost += cost
            total_emissions += emissions
            fuels_used.append('LPG')

            fuel_details['LPG'] = {
                'quantity': lpg_data['cylinders_per_month'],
                'unit': 'Cylinders',
                'energy_delivered': energy,
                'monthly_cost': cost,
                'annual_emissions': emissions,
                'efficiency': efficiency,
                'percentage': 0  # Will calculate after
            }
            logger.log_data("LPG Mixed", fuel_details['LPG'])

        # PNG
        if data.get('mixed_use_png') in [True, 'true', 'on', '1', 1]:
            logger.log_step("Processing PNG in mixed mode")
            monthly_bill = float(data.get('mixed_monthly_bill_png', 500))
            png_price_data = db_helper.get_png_pricing(district='All', category='Domestic')
            if not png_price_data:
                raise ValueError("PNG pricing not found in database. Please ensure fuel_unit_pricing table has PNG data.")
            png_rate = float(png_price_data['price_per_scm'])
            png_data = calculate_png_consumption_from_bill(monthly_bill, rate_per_scm=png_rate)
            efficiency = DEFAULT_EFFICIENCIES.get('PNG', 0.70)

            energy = png_data['monthly_energy_kwh'] * efficiency
            cost = png_data['total_bill']
            emissions = calculate_co2_emissions(png_data['daily_energy_kwh'], EMISSION_FACTORS['PNG'])

            total_energy += energy
            total_cost += cost
            total_emissions += emissions
            fuels_used.append('PNG')

            fuel_details['PNG'] = {
                'quantity': png_data['monthly_scm_consumption'],
                'unit': 'SCM',
                'energy_delivered': energy,
                'monthly_cost': cost,
                'annual_emissions': emissions,
                'efficiency': efficiency,
                'percentage': 0
            }
            logger.log_data("PNG Mixed", fuel_details['PNG'])

        # Grid electricity
        if data.get('mixed_use_elec') in [True, 'true', 'on', '1', 1]:
            logger.log_step("Processing Grid electricity in mixed mode")
            monthly_kwh = float(data.get('mixed_monthly_kwh', 40))
            efficiency = DEFAULT_EFFICIENCIES.get('Grid electricity', 0.90)
            tariff = household_data.get('electricity_tariff', 6.5)

            energy = monthly_kwh * efficiency
            cost = monthly_kwh * tariff
            emissions = calculate_co2_emissions(monthly_kwh / 30, EMISSION_FACTORS['Grid electricity'])

            total_energy += energy
            total_cost += cost
            total_emissions += emissions
            fuels_used.append('Grid electricity')

            fuel_details['Grid electricity'] = {
                'quantity': monthly_kwh,
                'unit': 'Units',
                'energy_delivered': energy,
                'monthly_cost': cost,
                'annual_emissions': emissions,
                'efficiency': efficiency,
                'percentage': 0
            }
            logger.log_data("Grid electricity Mixed", fuel_details['Grid electricity'])

        # Traditional Biomass
        if data.get('mixed_use_biomass') in [True, 'true', 'on', '1', 1]:
            logger.log_step("Processing Traditional Biomass in mixed mode")
            monthly_kg = float(data.get('mixed_monthly_kg_biomass', 50))

            biomass_energy_content = float(db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5))
            biomass_cost_per_kg = float(db_helper.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0))
            efficiency = DEFAULT_EFFICIENCIES.get('Traditional Solid Biomass', 0.18)

            monthly_energy_required = monthly_kg * biomass_energy_content
            energy = monthly_energy_required * efficiency
            cost = monthly_kg * biomass_cost_per_kg
            emissions = calculate_co2_emissions(monthly_energy_required / 30, EMISSION_FACTORS['Traditional Solid Biomass'])

            total_energy += energy
            total_cost += cost
            total_emissions += emissions
            fuels_used.append('Traditional Solid Biomass')

            fuel_details['Traditional Solid Biomass'] = {
                'quantity': monthly_kg,
                'unit': 'kg',
                'energy_delivered': energy,
                'monthly_cost': cost,
                'annual_emissions': emissions,
                'efficiency': efficiency,
                'percentage': 0
            }
            logger.log_data("Biomass Mixed", fuel_details['Traditional Solid Biomass'])

        # Calculate percentages
        if total_energy > 0:
            for fuel in fuel_details:
                fuel_details[fuel]['percentage'] = round((fuel_details[fuel]['energy_delivered'] / total_energy) * 100, 1)

        result['monthly_energy_kwh'] = total_energy
        result['monthly_cost'] = total_cost
        result['annual_emissions'] = total_emissions
        result['fuel_details'] = fuel_details
        result['fuel_details']['fuels_used'] = fuels_used
        result['fuel_details']['type'] = 'Mixed usage'
        result['fuel_details']['calculation_method'] = 'consumption_based'

        logger.log_data("Mixed Fuel Total Results", {
            'total_energy': total_energy,
            'total_cost': total_cost,
            'total_emissions': total_emissions,
            'fuels_used': fuels_used
        })

    # Log final results
    logger.log_subsection("FINAL CONSUMPTION-BASED RESULTS")
    logger.log_result("Monthly Energy Consumption", f"{result['monthly_energy_kwh']:.2f} kWh")
    logger.log_result("Monthly Cost", f"Rs {result['monthly_cost']:.2f}")
    logger.log_result("Annual CO₂ Emissions", f"{result['annual_emissions']:.2f} kg CO₂/year")

    # Save to database
    if household_id:
        logger.log_step(f"Saving cooking analysis to database for household {household_id}")
        save_cooking_analysis(household_id, kitchen_data, result)
        logger.log_success("Cooking analysis saved to database")
    else:
        logger.log_warning("No household_id - skipping database save")

    # Add overall thermal efficiency to result
    # For consumption-based, efficiency is based on the primary fuel's efficiency
    efficiency = DEFAULT_EFFICIENCIES.get(primary_fuel, 0.60)
    result['overall_thermal_efficiency'] = efficiency * 100
    
    logger.log_result("Overall Thermal Efficiency", f"{result['overall_thermal_efficiency']:.1f}%")
    logger.log_success("Consumption-based calculation completed successfully")
    logger.log_step(f"Debug log saved to: {logger.get_log_path()}")

    return result

def calculate_dish_based(data, household_data, kitchen_data, household_id, language='en'):
    """
    Calculate energy consumption based on selected dishes and cooking patterns (Bottom-up approach).

    Args:
        data (dict): Form data containing selected dishes and their fuel types.
        household_data (dict): Household profile data.
        kitchen_data (dict): Kitchen profile data.
        household_id (str): Unique identifier for the household.
        language (str, optional): Language code ('en' or 'ml') for dish name matching. Defaults to 'en'.

    Returns:
        dict: Calculation results including total monthly energy, cost, emissions, and detailed breakdown.
    """
    logger = get_logger()
    logger.log_subsection("DISH-BASED CALCULATION")

    try:
        logger.log_step("Loading dish data from database")
        # Fetch dishes from database
        dishes_list = db_helper.get_all_dishes(dish_type='residential')
        
        if not dishes_list:
            logger.log_error("Dishes data not available")
            return {'status': 'error', 'message': 'Dishes data not available'}

        # Convert to DataFrame for compatibility with existing logic
        dishes = pd.DataFrame(dishes_list)
        
        # Check if mapping is needed
        if 'dish_name' in dishes.columns and 'Dishes' not in dishes.columns:
            dishes = dishes.rename(columns={
                'dish_name': 'Dishes',
                'dish_name_ml': 'Dishes_ml',
                'category_name': 'Category'
            })

        logger.log_success(f"Loaded {len(dishes)} dishes from database")
        logger.log_data("Dish columns available", {"columns": dishes.columns.tolist()})

        logger.log_data("Household Data", household_data)
        logger.log_data("Kitchen Data", kitchen_data)

        # Extract dish selections
        selected_dishes = []
        fuel_selections = {}
        meal_types = {
            'breakfast_type': data.get('breakfast_type', 'Normal'),
            'lunch_type': data.get('lunch_type', 'Normal'),
            'dinner_type': data.get('dinner_type', 'Normal')
        }

        logger.log_data("Meal Types", meal_types)

        # Process each meal category
        logger.log_step("Processing dish selections by meal category")
        for category in ['Breakfast', 'Lunch', 'Dinner', 'Snacks']:

            if hasattr(data, "getlist"):
                dishes_list_input = data.getlist(f"{category.lower()}_dishes")
            else:
                dishes_list_input = data.get(f"{category.lower()}_dishes", [])

            if isinstance(dishes_list_input, str):
                dishes_list_input = [dishes_list_input] if dishes_list_input else []

            logger.log_input(f"{category} dishes selected", f"{len(dishes_list_input)} dishes")

            for dish in dishes_list_input:
                fuel_type = data.get(f'{dish}_fuel', 'LPG')
                selected_dishes.append({
                    'Dishes': dish,
                    'Category': category,
                    'stoves': fuel_type
                })
                fuel_selections[dish] = fuel_type
                logger.log_input(f"  - {dish}", f"Fuel: {fuel_type}")

        if not selected_dishes:
            logger.log_error("No dishes selected by user")
            return {'status': 'error', 'message': 'No dishes selected'}

        logger.log_success(f"Total {len(selected_dishes)} dishes selected")
        logger.log_data("Fuel selections by dish", fuel_selections)

        # Create DataFrame from selections
        logger.log_step("Creating user_responses DataFrame from selected dishes")
        user_responses = pd.DataFrame(selected_dishes)
        logger.log_dataframe("user_responses (Selected Dishes)", user_responses)

        # Determine which dish column to use for merging
        logger.log_step("Merging user selections with dish database")
        if language == 'ml':
            logger.log_step("Using Malayalam dish mapping for merge")
            # For Malayalam, try to merge using Malayalam dish names
            # First, map Malayalam names to English names
            dish_mapping = dict(zip(dishes['Dishes_ml'].fillna(''), dishes['Dishes']))
            
            # Map Malayalam dish names to English for merging
            user_responses['Dishes_mapped'] = user_responses['Dishes'].map(
                lambda x: dish_mapping.get(x, x)
            )

            # Merge using mapped names
            user_dishes_with_data = pd.merge(
                user_responses,
                dishes,
                left_on='Dishes_mapped',
                right_on='Dishes',
                how='left',
                suffixes=('_user', '_dish')
            )
            logger.log_success("Malayalam dish merge completed")
        else:
            logger.log_step("Using English dish names for direct merge")
            # For English, merge directly
            user_dishes_with_data = pd.merge(
                user_responses,
                dishes,
                on='Dishes',
                how='left',
                suffixes=('_user', '_dish')
            )
            logger.log_success("English dish merge completed")

        # Log merge result
        logger.log_dataframe("user_dishes_with_data (After Merge)", user_dishes_with_data, max_rows=10)

        # Restore the Category column from user data
        user_dishes_with_data['Category'] = user_dishes_with_data['Category_user']
        logger.log_step("Restored Category column from user data")

        if user_dishes_with_data.empty:
            logger.log_error("No matching dishes found after merge")
            return {'status': 'error', 'message': 'No matching dishes found'}

        # Calculate monthly energy with economies of scale
        logger.log_subsection("CALCULATING MONTHLY ENERGY & CALORIES")
        household_size = household_data.get('household_size', 4)
        total_calories = 2400

        logger.log_input("Household Size", f"{household_size} members")
        logger.log_input("Total Calories per Person", f"{total_calories} kcal/person/day")
        logger.log_data("Meal Type Adjustments", meal_types)

        logger.log_step("Calling monthly_calories() function")
        monthly_calories_df = monthly_calories(
            user_dishes_with_data,
            household_size,
            total_calories_per_person=total_calories,
            breakfast=meal_types['breakfast_type'],
            lunch=meal_types['lunch_type'],
            dinner=meal_types['dinner_type']
        )

        # Log monthly_calories_df result
        logger.log_dataframe("monthly_calories_df (Energy Calculations)", monthly_calories_df, max_rows=15)

        if 'Final_Energy_Value' not in monthly_calories_df.columns:
            logger.log_error("Final_Energy_Value column missing from monthly_calories_df")
            return {'status': 'error', 'message': 'Energy calculation failed'}

    except Exception as e:
        logger.log_error(f"Exception in calculate_dish_based: {str(e)}")
        import traceback
        error_trace = traceback.format_exc()
        logger.log_error(f"\nEXCEPTION TRACEBACK:\n{error_trace}\n")
        return {'status': 'error', 'message': 'Energy calculation failed'}

    # Calculate total monthly energy
    logger.log_subsection("CALCULATING TOTAL ENERGY & COSTS BY FUEL")

    logger.log_step("Summing total energy from all dishes")
    monthly_energy_kwh = monthly_calories_df['Final_Energy_Value'].sum()
    logger.log_result("Total Monthly Energy (gross)", f"{monthly_energy_kwh:.2f} kWh")

    # Get efficiency and cost data for each fuel
    logger.log_step("Loading stove efficiency data for user's area type")
    area_type = household_data.get('area_type', 'Urban')
    logger.log_input("Area Type", area_type)

    # Fetch stove data from database
    stove_data_list = db_helper.get_all_stove_efficiencies()
    stove_data = pd.DataFrame(stove_data_list)
    
    # Handle 'Both' area type by duplicating for Urban and Rural
    if not stove_data.empty and 'Area' in stove_data.columns:
        both_area = stove_data[stove_data['Area'] == 'Both']
        if not both_area.empty:
            urban = both_area.copy()
            urban['Area'] = 'Urban'
            rural = both_area.copy()
            rural['Area'] = 'Rural'
            stove_data = pd.concat([stove_data[stove_data['Area'] != 'Both'], urban, rural], ignore_index=True)
    else:
        logger.log_warning("Stove data is empty or missing Area column")
        # Create empty DataFrame with expected columns to avoid errors
        stove_data = pd.DataFrame(columns=['Area', 'Fuel', 'Thermal Efficiency'])

    user_stove_data = stove_data[
        (stove_data['Area'] == area_type)
    ].copy()

    if user_stove_data.empty:
        logger.log_warning(f"No stove data found for {area_type}, using all stove data")
        user_stove_data = stove_data.copy()
    else:
        logger.log_success(f"Loaded {len(user_stove_data)} stove records for {area_type}")

    logger.log_dataframe("user_stove_data (Stove Efficiency & Cost)", user_stove_data, max_rows=10)

    # Build dictionaries for multi-fuel calculation
    logger.log_step("Building fuel-specific energy, efficiency, and cost dictionaries")
    
    # Initialize FuelCostCalculator
    from fuel_cost_standardizer import FuelCostCalculator
    cost_calculator = FuelCostCalculator(
        db_helper,
        household_data=household_data,
        kitchen_data=kitchen_data
    )

    fuel_energy_dict = {}
    fuel_efficiency_dict = {}
    fuel_cost_per_kwh_dict = {}

    # Get unique fuels used
    current_fuel_mix = user_responses['stoves'].unique().tolist()
    logger.log_input("Fuel Mix Used", ', '.join(current_fuel_mix))
    logger.log_step(f"Processing {len(current_fuel_mix)} different fuels")

    for fuel in current_fuel_mix:
        logger.log_subsection(f"FUEL: {fuel}")

        # Energy for this fuel
        fuel_energy = monthly_calories_df[monthly_calories_df['stoves'] == fuel]['Final_Energy_Value'].sum()
        fuel_energy_dict[fuel] = fuel_energy
        logger.log_result(f"{fuel} - Monthly Energy", f"{fuel_energy:.2f} kWh")

        # Efficiency for this fuel
        fuel_stove_info = user_stove_data[user_stove_data['Fuel'] == fuel]
        if not fuel_stove_info.empty:
            efficiency = fuel_stove_info['Thermal Efficiency'].values[0]
            fuel_efficiency_dict[fuel] = efficiency
            logger.log_result(f"{fuel} - Thermal Efficiency (from stove database)", f"{efficiency:.2%}")
        else:
            efficiency = DEFAULT_EFFICIENCIES.get(fuel, 0.50)
            fuel_efficiency_dict[fuel] = efficiency
            logger.log_warning(f"{fuel} not found in stove database, using default efficiency")
            logger.log_result(f"{fuel} - Thermal Efficiency (default)", f"{efficiency:.2%}")

        # Cost per kWh for this fuel using Centralized Calculator
        # Calculate energy required for fuels that need it (like PNG fixed charges)
        energy_required = fuel_energy / efficiency if efficiency > 0 else 0
        
        # Get standardized cost
        # Note: Residential dish-based currently doesn't support direct user cost input in the form
        # If it did, we would pass 'user_input_cost' here.
        cost_per_kwh, source = cost_calculator.get_cost_per_kwh(
            fuel,
            energy_required=energy_required
        )
        
        fuel_cost_per_kwh_dict[fuel] = cost_per_kwh
        logger.log_result(f"{fuel} - Cost per kWh", f"Rs {cost_per_kwh:.2f}/kWh", source)

    # Calculate using helper function
    logger.log_step("Calling calculate_fuel_emissions_and_costs() function")
    multi_fuel_results = calculate_fuel_emissions_and_costs(
        fuel_energy_dict,
        fuel_efficiency_dict,
        fuel_cost_per_kwh_dict
    )

    logger.log_data("Multi-fuel calculation results", multi_fuel_results)

    # Calculate overall thermal efficiency
    # Overall efficiency = (Total Energy Delivered / Total Energy Required) * 100
    total_energy_required = sum(
        details['energy_required'] 
        for details in multi_fuel_results['fuel_breakdown'].values()
    )
    if total_energy_required > 0:
        overall_efficiency = (multi_fuel_results['total_energy_delivered'] / total_energy_required) * 100
    else:
        overall_efficiency = 0
    
    logger.log_calculation(
        "Overall Thermal Efficiency",
        "(Total Energy Delivered / Total Energy Required) × 100",
        {
            "total_delivered": f"{multi_fuel_results['total_energy_delivered']:.2f} kWh",
            "total_required": f"{total_energy_required:.2f} kWh"
        },
        f"{overall_efficiency:.1f}",
        "%"
    )

    # Extract results
    result = {
        'monthly_energy_kwh': multi_fuel_results['total_energy_delivered'],
        'monthly_cost': multi_fuel_results['total_monthly_cost'],
        'annual_emissions': multi_fuel_results['total_annual_emissions'],
        'overall_thermal_efficiency': overall_efficiency,
        'fuel_details': {
            'type': 'Multiple' if len(current_fuel_mix) > 1 else current_fuel_mix[0],
            'fuels_used': current_fuel_mix,
            'fuel_breakdown': multi_fuel_results['fuel_breakdown'],
            'calculation_method': 'dish_based',
            'selected_dishes': selected_dishes,
            'meal_types': meal_types
        }
    }

    # Log final results
    logger.log_subsection("FINAL DISH-BASED RESULTS")
    logger.log_result("Total Monthly Energy (useful)", f"{result['monthly_energy_kwh']:.2f} kWh")
    logger.log_result("Total Monthly Cost", f"Rs {result['monthly_cost']:.2f}")
    logger.log_result("Total Annual Emissions", f"{result['annual_emissions']:.2f} kg CO₂/year")

    # Calculate environmental grade
    environmental_grade = helper.get_environmental_grade(result['annual_emissions'], household_size=household_size)
    result['environmental_grade'] = environmental_grade

    # Save to database
    if household_id:
        logger.log_step(f"Saving cooking analysis to database for household {household_id}")
        save_cooking_analysis(household_id, kitchen_data, result)
        logger.log_success("Cooking analysis saved to database")
    else:
        logger.log_warning("No household_id - skipping database save")

    logger.log_success("Dish-based calculation completed successfully")
    logger.log_step(f"Debug log saved to: {logger.get_log_path()}")

    return result
