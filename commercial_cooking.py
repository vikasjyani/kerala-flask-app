"""
Commercial Cooking Calculations Module
Matches residential cooking pattern - portion-based with serving volume efficiency
"""

import pandas as pd
import helper
from helper import (
    db_helper, basic_calories, calculate_co2_emissions, calculate_png_bill_and_consumption,
    calculate_fuel_emissions_and_costs, DEFAULT_EFFICIENCIES,
    EMISSION_FACTORS, LPG_CALORIFIC_VALUE, LPG_ENERGY_PER_CYLINDER,
    PNG_CALORIFIC_VALUE, get_user_connection, close_user_connection
)
from debug_logger import get_logger

# ==================================================================
# COMMERCIAL COOKING CALCULATION FUNCTIONS
# ==================================================================

from config import get_config

def get_serving_volume_efficiency(servings_per_day):
    """
    Get efficiency factor based on serving volume (like household size for residential).
    Larger volumes have better economies of scale.

    Args:
        servings_per_day (int): Number of daily servings.

    Returns:
        float: Efficiency factor (lower is more efficient per serving).
    """
    try:
        # Use new consolidated method
        return db_helper.get_commercial_efficiency(servings_per_day)
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error fetching serving efficiency: {e}")
    
    # Fallback calculation using config constants
    conf = get_config()
    thresholds = conf.SERVINGS_THRESHOLDS
    efficiencies = conf.VOLUME_EFFICIENCY_DEFAULTS
    
    if servings_per_day < thresholds['small']:
        return efficiencies['small']
    elif servings_per_day < thresholds['medium']:
        return efficiencies['medium']
    elif servings_per_day < thresholds['large']:
        return efficiencies['large']
    else:
        return efficiencies.get('very_large', 0.85)  # Fallback for large volumes


def get_institution_meal_calories(institution_type, meal_type, intensity='Normal'):
    """Get target calories per serving for institution, meal type, and intensity.

    Args:
        institution_type (str): Type of institution (School, Hotel, etc.).
        meal_type (str): Type of meal (Breakfast, Lunch, Dinner, Snacks).
        intensity (str, optional): Meal intensity (Normal, Heavy, Light). Defaults to 'Normal'.

    Returns:
        int: Calories per serving based on intensity level.
    """
    try:
        meal_type = meal_type.title()
        intensity = intensity.title()

        # Map intensity to column name
        intensity_column = {
            'Normal': 'calories_normal',
            'Heavy': 'calories_heavy',
            'Light': 'calories_light'
        }.get(intensity, 'calories_normal')

        query = f"""
            SELECT calories_per_serving, {intensity_column}
            FROM institution_meal_calories
            WHERE institution_type = ? AND meal_type = ?
        """
        result = db_helper.fetch_one(query, (institution_type, meal_type))
        if result:
            # Convert Row to dict for easier access
            result_dict = dict(result)
            # Try intensity-specific column first, fallback to calories_per_serving
            if result_dict.get(intensity_column):
                return result_dict[intensity_column]
            return result_dict['calories_per_serving']
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error fetching institution calories: {e}")

    # Fallback values from config
    conf = get_config()
    defaults = conf.INSTITUTION_MEAL_CALORIES_DEFAULTS
    base_calories = defaults.get(meal_type, 500)

    # Apply intensity multiplier
    if intensity == 'Heavy':
        return int(base_calories * 1.25)
    elif intensity == 'Light':
        return int(base_calories * 0.75)
    return base_calories


def get_commercial_wastage_factor(servings_per_day, institution_type='School'):
    """
    Calculate wastage factor for commercial kitchens.
    Professional kitchens have less wastage than residential due to better inventory management.
    
    Args:
        servings_per_day (int): Number of servings prepared daily.
        institution_type (str): Type of institution (School/Factory/Anganwadi/Hotel/Community Kitchen).
    
    Returns:
        float: Wastage multiplier (e.g., 1.03 to 1.12).
    """
    conf = get_config()
    thresholds = conf.SERVINGS_THRESHOLDS
    wastage_config = conf.COMMERCIAL_WASTAGE_FACTORS
    
    # Get base and min wastage for the institution type
    type_config = wastage_config.get(institution_type, wastage_config.get('Factory')) # Default to Factory if unknown
    
    base = type_config['base']
    min_wastage = type_config['min']
    
    # Scale reduction based on volume
    # Larger volumes → better planning → less wastage
    if servings_per_day < thresholds['small']:
        return base  # Small scale: base wastage
    elif servings_per_day < thresholds['medium']:
        return max(base - 0.02, min_wastage)  # Medium: -2%
    elif servings_per_day < thresholds['large']:
        return max(base - 0.04, min_wastage)  # Large: -4%
    else:
        return min_wastage  # Very large: minimum wastage


def commercial_monthly_energy(df_dishes, servings_per_day, working_days, institution_type,
                              breakfast='Normal', lunch='Heavy', dinner='Light'):
    """
    Calculate monthly energy for commercial cooking (portion-based, matching residential pattern)
    
    Similar to residential monthly_calories() but for commercial scale
    """
    logger = get_logger()
    logger.log_step("Calculating commercial monthly energy")
    
    # Get serving volume efficiency (like household size efficiency)
    serving_efficiency = get_serving_volume_efficiency(servings_per_day)
    logger.log_calculation(
        "Serving Volume Efficiency",
        "Based on servings_per_day volume",
        {"servings_per_day": servings_per_day},
        f"{serving_efficiency:.2%}"
    )
    
    # Calculate basic calories for each dish
    df_calc = basic_calories(df_dishes)
    logger.log_dataframe("Dishes with basic calories", df_calc, max_rows=5)

    # Note: energy_to_cook_kwh now comes directly from database as per-portion values
    # No batch division needed - database has been migrated to store per-portion energy
    logger.log_data("Using per-portion energy from database", {
        "sample_dish": df_calc.iloc[0]['Dishes'] if not df_calc.empty else "None",
        "energy_per_portion": df_calc.iloc[0]['energy_to_cook_kwh'] if not df_calc.empty and 'energy_to_cook_kwh' in df_calc.columns else 0.05
    })

    # Wastage factor for commercial kitchens (dynamic based on type and volume)
    wastage_factor = get_commercial_wastage_factor(servings_per_day, institution_type)
    logger.log_calculation(
        "Commercial Wastage Factor",
        f"Based on {institution_type} serving {servings_per_day} per day",
        {"institution_type": institution_type, "servings_per_day": servings_per_day},
        f"{wastage_factor:.3f} ({(wastage_factor-1)*100:.1f}% wastage)"
    )
    
    # Process each meal category
    for category in ['Breakfast', 'Lunch', 'Dinner', 'Snacks']:
        category_mask = df_calc['Category'].str.lower() == category.lower()
        if not category_mask.any():
            continue

        # Get meal intensity
        if category == 'Breakfast':
            meal_intensity = breakfast
        elif category == 'Lunch':
            meal_intensity = lunch
        elif category == 'Dinner':
            meal_intensity = dinner
        else:
            meal_intensity = 'Normal'

        # FIXED: Calculate MONTHLY calorie target (not per-serving)
        # Use meal intensity from user selection (Normal, Heavy, Light)
        calories_per_serving = get_institution_meal_calories(institution_type, category, meal_intensity)
        
        # Use working_days for monthly factor, defaulting to 30 if not provided or zero
        monthly_factor = float(working_days) if working_days else 30.0
        monthly_servings = servings_per_day * monthly_factor
        target_calories_monthly = calories_per_serving * monthly_servings

        logger.log_input(
            f"{category} target (monthly)",
            f"{target_calories_monthly:,.0f} kcal ({calories_per_serving} kcal/serving × {monthly_servings} servings)"
        )

        # Calculate total calories from selected dishes (per serving)
        total_dish_calories_per_serving = df_calc.loc[category_mask, 'total_calories'].sum()

        # FIXED: Scale to monthly total
        total_dish_calories_monthly = total_dish_calories_per_serving * monthly_servings

        # FIXED: Scaling factor now uses monthly totals
        if total_dish_calories_monthly > 0:
            scaling_factor = target_calories_monthly / total_dish_calories_monthly
        else:
            scaling_factor = 1.0

        logger.log_calculation(
            f"{category} scaling factor",
            "target_monthly / actual_monthly",
            {
                "target": f"{target_calories_monthly:,.0f} kcal",
                "actual": f"{total_dish_calories_monthly:,.0f} kcal",
                "per_serving_target": f"{calories_per_serving} kcal",
                "per_serving_actual": f"{total_dish_calories_per_serving:.1f} kcal"
            },
            f"{scaling_factor:.3f}"
        )

        # FIXED: Apply scaling with efficiencies to get MONTHLY energy
        # Ensure energy_to_cook_kwh exists
        if 'energy_to_cook_kwh' not in df_calc.columns:
             df_calc['energy_to_cook_kwh'] = 0.05 # Fallback default
             
        base_energy_per_serving = df_calc.loc[category_mask, 'energy_to_cook_kwh']

        df_calc.loc[category_mask, 'Final_Energy_Value'] = (
            base_energy_per_serving *
            scaling_factor *
            serving_efficiency *
            wastage_factor *
            monthly_servings  # Scale to monthly total
        )

        logger.log_calculation(
            f"{category} monthly energy",
            "base_energy × scaling × efficiency × wastage × monthly_servings",
            {
                "servings_per_day": servings_per_day,
                "working_days": working_days,
                "monthly_servings": monthly_servings,
                "scaling": f"{scaling_factor:.3f}",
                "efficiency": f"{serving_efficiency:.3f}",
                "wastage": f"{wastage_factor:.3f}"
            },
            f"{df_calc.loc[category_mask, 'Final_Energy_Value'].sum():.2f} kWh"
        )
    
    return df_calc


def calculate_consumption_based(data, institution_data, kitchen_data, institution_id):

    #Commercial consumption-based calculation (matches residential pattern)
   
    #Commercial consumption-based calculation
    #Supports: Dual LPG cylinders (Domestic + Commercial), PNG, Electricity, Biogas, Biomass
   
    logger = get_logger()
    logger.log_subsection("COMMERCIAL CONSUMPTION-BASED CALCULATION")
    
    try:
        # Get primary fuel and institution data
        primary_fuel = data.get('primary_fuel')
        logger.log_input("Primary Fuel", primary_fuel)
        
        servings_per_day = institution_data.get('servings_per_day', 100)
        working_days = institution_data.get('working_days', 30)
        district = institution_data.get('district', 'Thiruvananthapuram')
        
        # Initialize result
        result = {
            'monthly_energy_kwh': 0,
            'monthly_cost': 0,
            'annual_co2_kg': 0,
            'calculation_method': 'consumption_based',
            'fuel_details': {},
            'servings_per_day': servings_per_day,
            'working_days': working_days,
            'institution_type': institution_data.get('institution_type', 'School')
        }
        
        monthly_energy_kwh = 0
        monthly_cost = 0
        annual_co2_kg = 0
        
        # ==============================================================
        # LPG - DUAL CYLINDER SUPPORT (Domestic + Commercial)
        # ==============================================================

        if primary_fuel == 'LPG':
            logger.log_step("Processing LPG consumption (Dual Cylinder Support)")
            
            lpg_types_selected = data.getlist('lpg_types') or []
            logger.log_data("LPG Cylinder Types Selected", lpg_types_selected)
            
            # ✅ Get working_days for proper daily calculation
            working_days = institution_data.get('working_days', 30)
            monthly_factor = float(working_days) if working_days else 30.0
            
            total_lpg_energy = 0
            total_lpg_cost = 0
            total_lpg_co2 = 0
            total_lpg_kg=0
            # Domestic LPG (14.2 kg)
            if 'Domestic' in lpg_types_selected:
                domestic_cylinders = float(data.get('domestic_cylinders') or 0)
                logger.log_input("Domestic Cylinders/Month", domestic_cylinders)
                
                if domestic_cylinders > 0:
                    # Get pricing from database
                    # Get pricing from database
                    try:
                        price_data = db_helper.get_fuel_unit_price(district, 'LPG', 'Domestic')
                        domestic_price = float(price_data['unit_price']) if price_data else 850.0
                    except:
                        domestic_price = 850.0
                    
                    # Energy calculation (14.2 kg * 12.8 kWh/kg)
                    domestic_energy = domestic_cylinders * 14.2 * 12.8
                    domestic_cost = domestic_cylinders * domestic_price
                    
                    # ✅ FIX: Use working_days and calculate_co2_emissions() for consistency
                    daily_energy = domestic_energy / monthly_factor
                    domestic_co2 = calculate_co2_emissions(daily_energy, EMISSION_FACTORS.get('LPG', 0.213), institution_data)
                    
                    total_lpg_energy += domestic_energy
                    total_lpg_cost += domestic_cost
                    total_lpg_co2 += domestic_co2
                    total_lpg_kg += domestic_cylinders * 14.2
                    
                    logger.log_calculation("Domestic LPG", 
                        f"{domestic_cylinders} cylinders × 14.2kg × 12.8kWh/kg",
                        {
                            "cylinders": domestic_cylinders, 
                            "price": domestic_price,
                            "working_days": working_days
                        },
                        f"{domestic_energy:.2f} kWh, ₹{domestic_cost:.2f}, {domestic_co2:.2f} kg CO₂/year"
                    )
            
            # Commercial LPG (19 kg)
            if 'Commercial' in lpg_types_selected:
                commercial_cylinders = float(data.get('commercial_cylinders') or 0)
                logger.log_input("Commercial Cylinders/Month", commercial_cylinders)
                
                if commercial_cylinders > 0:
                    # Get pricing: User Input > DB > Default (1810.5)
                    commercial_price_input = data.get('commercial_cylinder_price')
                    if commercial_price_input and float(commercial_price_input) > 0:
                        commercial_price = float(commercial_price_input)
                    else:
                        try:
                            price_data = db_helper.get_fuel_unit_price(district, 'LPG', 'Commercial')
                            commercial_price = float(price_data['unit_price']) if price_data else 1810.5
                        except:
                            commercial_price = 1810.5
                    
                    # Energy calculation (19 kg * 12.8 kWh/kg)
                    commercial_energy = commercial_cylinders * 19.0 * 12.8
                    commercial_cost = commercial_cylinders * commercial_price
                    
                    # ✅ FIX: Use working_days and calculate_co2_emissions() for consistency
                    daily_energy = commercial_energy / monthly_factor
                    commercial_co2 = calculate_co2_emissions(daily_energy, EMISSION_FACTORS.get('LPG', 0.213), institution_data)
                    
                    total_lpg_energy += commercial_energy
                    total_lpg_cost += commercial_cost
                    total_lpg_co2 += commercial_co2
                    total_lpg_kg += commercial_cylinders * 19.0
                    
                    logger.log_calculation("Commercial LPG",
                        f"{commercial_cylinders} cylinders × 19kg × 12.8kWh/kg",
                        {
                            "cylinders": commercial_cylinders, 
                            "price": commercial_price,
                            "working_days": working_days
                        },
                        f"{commercial_energy:.2f} kWh, ₹{commercial_cost:.2f}, {commercial_co2:.2f} kg CO₂/year"
                    )
            
            # Apply thermal efficiency
            efficiency = DEFAULT_EFFICIENCIES.get('LPG', 0.60)
            delivered_energy = total_lpg_energy * efficiency
            #useful enegy =delivered_energy
            monthly_energy_kwh = delivered_energy
            monthly_cost = total_lpg_cost
            annual_co2_kg = total_lpg_co2  # ✅ Already annual (365 days), no × 12 needed!
            
            result['fuel_details']['LPG'] = {
                'gross_energy_kwh': total_lpg_energy,
                'delivered_energy_kwh': delivered_energy,
                'monthly_cost': total_lpg_cost,
                'energy_required': total_lpg_energy,
                'thermal_efficiency': efficiency * 100,
                'annual_co2_kg': annual_co2_kg,
                'domestic_cylinders': float(data.get('domestic_cylinders') or 0),
                'commercial_cylinders': float(data.get('commercial_cylinders') or 0),
                'quantity': total_lpg_kg,
                'unit': 'kg',
                'monthly_kg': total_lpg_kg,
                'energy_delivered': delivered_energy,
                'annual_emissions': annual_co2_kg
            }


        # ==============================================================
        # PNG - Bill Amount or SCM Method
        # ==============================================================
        elif primary_fuel == 'PNG':
            logger.log_step("Processing PNG consumption")
            
            png_method = data.get('png_input_method', 'bill')
            logger.log_input("PNG Input Method", png_method)

            # Single canonical rate source for this request (DB-backed commercial rate).
            png_price_data = db_helper.get_png_pricing(district=district, category='Commercial')
            png_rate = float(png_price_data['price_per_scm']) if png_price_data else 47.0
            logger.log_input("PNG Rate (Commercial, DB)", f"Rs {png_rate:.2f}/SCM")
            
            if png_method == 'bill':
                monthly_bill = float(data.get('monthly_bill') or 0)
                logger.log_input("Monthly Bill Amount", f"₹{monthly_bill}")

                calc_result = helper.calculate_png_consumption_from_bill(
                    monthly_bill,
                    rate_per_scm=png_rate,
                    district=district,
                    category='Commercial'
                )
                monthly_scm = calc_result.get('monthly_scm_consumption', 0)
                monthly_energy_kwh = calc_result.get('monthly_energy_kwh', monthly_scm * PNG_CALORIFIC_VALUE)
                monthly_cost = monthly_bill  # Keep user-entered bill as displayed monthly cost.
                modeled_bill = calc_result.get('total_bill', monthly_bill)
            else:  # SCM method
                monthly_scm = float(data.get('monthly_scm') or 0)
                logger.log_input("Monthly SCM", monthly_scm)
                calc_result = calculate_png_bill_and_consumption(monthly_scm, rate_per_scm=png_rate)
                monthly_energy_kwh = calc_result.get('monthly_energy_kwh', monthly_scm * PNG_CALORIFIC_VALUE)
                monthly_cost = calc_result.get('total_bill', monthly_scm * png_rate)
                modeled_bill = monthly_cost
            
            # Apply thermal efficiency
            efficiency = DEFAULT_EFFICIENCIES.get('PNG', 0.70)
            delivered_energy = monthly_energy_kwh * efficiency
            
            #useful energy = delivered energy
            # Calculate emissions using standard function for consistency
            daily_energy = monthly_energy_kwh / working_days if working_days else monthly_energy_kwh / 30
            annual_co2_kg = calculate_co2_emissions(daily_energy, EMISSION_FACTORS.get('PNG', 0.2), institution_data)
            
            result['fuel_details']['PNG'] = {
                'gross_energy_kwh': monthly_energy_kwh,
                'delivered_energy_kwh': delivered_energy,
                'monthly_cost': monthly_cost,
                'energy_required': monthly_energy_kwh,
                'thermal_efficiency': efficiency * 100,
                'annual_co2_kg': annual_co2_kg,
                'monthly_scm': monthly_scm,
                'quantity': monthly_scm,
                'unit': 'SCM',
                'rate_per_scm': png_rate,
                'modeled_bill': modeled_bill,
                'input_method': png_method,
                'energy_delivered': delivered_energy,
                'annual_emissions': annual_co2_kg
            }
            
            monthly_energy_kwh = delivered_energy
        
        # ==============================================================
        # Grid Electricity
        # ==============================================================
        elif primary_fuel == 'Grid electricity':
            logger.log_step("Processing Electricity consumption")
            
            monthly_kwh = float(data.get('monthly_kwh') or 0)
            # Priority: User input > institution data > database > fallback
            electricity_rate = float(data.get('electricity_rate') or institution_data.get('electricity_tariff') or 
                                    db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.50))
            
            logger.log_input("Monthly kWh", monthly_kwh)
            logger.log_input("Electricity Rate", f"₹{electricity_rate}/kWh")
            
            monthly_cost = monthly_kwh * electricity_rate
            monthly_energy_kwh = monthly_kwh
            
           
            # Electricity is already delivered energy (efficiency ~90%)
            efficiency = DEFAULT_EFFICIENCIES.get('Grid electricity', 0.90)
            delivered_energy = monthly_kwh * efficiency
             #useful energy = delivered energy
            # Calculate emissions using standard function for consistency
            daily_energy = monthly_kwh / working_days if working_days else monthly_kwh / 30
            annual_co2_kg = calculate_co2_emissions(daily_energy, EMISSION_FACTORS.get('Grid electricity', 0.82), institution_data)
            
            result['fuel_details']['Grid electricity'] = {
                'gross_energy_kwh': monthly_kwh,
                'delivered_energy_kwh': delivered_energy,
                'monthly_cost': monthly_cost,
                'energy_required': monthly_kwh,
                'thermal_efficiency': efficiency * 100,
                'annual_co2_kg': annual_co2_kg,
                'monthly_kwh': monthly_kwh,
                'rate_per_kwh': electricity_rate,
                'energy_delivered': delivered_energy,
                'annual_emissions': annual_co2_kg
            }
            
            monthly_energy_kwh = delivered_energy
        
        # ==============================================================
        # Biogas
        # ==============================================================
        elif primary_fuel == 'Biogas':
            logger.log_step("Processing Biogas consumption")
            
            daily_biogas_m3 = float(data.get('daily_biogas_m3') or 0)
            biogas_monthly_cost = float(data.get('biogas_monthly_cost') or 0)
            
            logger.log_input("Daily Biogas Production (m³)", daily_biogas_m3)
            
            monthly_factor = float(working_days) if working_days else 30.0
            monthly_m3 = daily_biogas_m3 * monthly_factor
            energy_per_m3 = helper.BIOGAS_ENERGY_PER_M3
            monthly_energy_kwh_gross = monthly_m3 * energy_per_m3

            # Compute feedstock + O&M + capex using DB-backed defaults; user input acts as extra OPEX
            biogas_costs = helper.compute_biogas_costs(
                monthly_m3,
                category='Commercial',
                user_added_opex=biogas_monthly_cost
            )
            monthly_cost = biogas_costs['total_monthly_cost']
            
            # Apply thermal efficiency
            efficiency = DEFAULT_EFFICIENCIES.get('Biogas', 0.55)
            delivered_energy = monthly_energy_kwh_gross * efficiency
             #useful energy = delivered energy
            # Emissions from DB emission factor (kg/kWh primary)
            emission_factor = EMISSION_FACTORS.get('Biogas', 0.27)
            annual_co2_kg = calculate_co2_emissions(
                monthly_energy_kwh_gross / monthly_factor,
                emission_factor,
                institution_data
            )
            
            result['fuel_details']['Biogas'] = {
                'gross_energy_kwh': monthly_energy_kwh_gross,
                'delivered_energy_kwh': delivered_energy,
                'monthly_cost': monthly_cost,
                'energy_required': monthly_energy_kwh_gross,
                'thermal_efficiency': efficiency * 100,
                'annual_co2_kg': annual_co2_kg,
                'daily_m3': daily_biogas_m3,
                'monthly_m3': monthly_m3,
                'energy_per_m3_kwh': energy_per_m3,
                'emission_source': helper.EMISSION_SOURCES.get('Biogas'),
                'cost_components': biogas_costs,
                'cost_per_kwh': biogas_costs.get('cost_per_kwh_primary'),
                'energy_delivered': delivered_energy,
                'annual_emissions': annual_co2_kg
            }
            
            monthly_energy_kwh = delivered_energy
        
        # ==============================================================
        # Traditional Solid Biomass
        # ==============================================================
        elif primary_fuel == 'Traditional Solid Biomass':
            logger.log_step("Processing Solid Biomass consumption")
            
            monthly_biomass_kg = float(data.get('monthly_biomass_kg') or 0)
            biomass_type = data.get('biomass_type', 'Firewood')
            monthly_factor = float(working_days) if working_days else 30.0
            biomass_energy_content = float(db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5))
            biomass_price_data = db_helper.get_fuel_unit_price(district, 'Traditional Solid Biomass', 'Commercial')
            default_biomass_cost = float(
                biomass_price_data['unit_price']
                if biomass_price_data and biomass_price_data.get('unit_price') is not None
                else db_helper.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0)
            )
            biomass_cost_per_kg = float(data.get('biomass_cost_per_kg') or default_biomass_cost)
            
            logger.log_input("Monthly Biomass (kg)", monthly_biomass_kg)
            logger.log_input("Biomass Type", biomass_type)
            
            monthly_energy_kwh_gross = monthly_biomass_kg * biomass_energy_content
            monthly_cost = monthly_biomass_kg * biomass_cost_per_kg
            
            # Apply thermal efficiency (very low for traditional stoves)
            efficiency = DEFAULT_EFFICIENCIES.get('Traditional Solid Biomass', 0.18)
            delivered_energy = monthly_energy_kwh_gross * efficiency
             #useful energy = delivered energy
            annual_co2_kg = calculate_co2_emissions(
                monthly_energy_kwh_gross / monthly_factor,
                EMISSION_FACTORS.get('Traditional Solid Biomass', 0.4),
                institution_data
            )
            
            result['fuel_details']['Traditional Solid Biomass'] = {
                'gross_energy_kwh': monthly_energy_kwh_gross,
                'delivered_energy_kwh': delivered_energy,
                'monthly_cost': monthly_cost,
                'energy_required': monthly_energy_kwh_gross,
                'thermal_efficiency': efficiency * 100,
                'annual_co2_kg': annual_co2_kg,
                'monthly_kg': monthly_biomass_kg,
                'biomass_type': biomass_type,
                'cost_per_kg': biomass_cost_per_kg,
                'energy_per_kg_kwh': biomass_energy_content,
                'energy_delivered': delivered_energy,
                'annual_emissions': annual_co2_kg
            }
            
            monthly_energy_kwh = delivered_energy
        
        # ==============================================================
        # MIXED USAGE - MULTIPLE FUELS
        # ==============================================================
        elif primary_fuel == 'Mixed usage':
            logger.log_step("Processing Mixed Fuel Usage")
            
            total_energy = 0
            total_cost = 0
            total_emissions = 0
            fuels_used = []
            
            working_days = institution_data.get('working_days', 30)
            monthly_factor = float(working_days) if working_days else 30.0
            
            # Commercial LPG (19 kg)
            if data.get('mixed_use_lpg') in [True, 'true', 'on', '1', 1, 'on']:
                logger.log_step("Mixed: Processing Commercial LPG")
                mixed_cylinders = float(data.get('mixed_commercial_cylinders') or 5)
                
                lpg_price_data = db_helper.get_fuel_unit_price(district, 'LPG', 'Commercial')
                cylinder_price = float(
                    lpg_price_data['unit_price']
                    if lpg_price_data and lpg_price_data.get('unit_price') is not None
                    else db_helper.get_system_parameter('LPG_COMMERCIAL_PRICE', 1810.5)
                )
                lpg_energy = mixed_cylinders * 19.0 * 12.8
                lpg_cost = mixed_cylinders * cylinder_price
                efficiency = DEFAULT_EFFICIENCIES.get('LPG', 0.60)
                delivered = lpg_energy * efficiency
                
                daily_energy = lpg_energy / monthly_factor
                lpg_emissions = calculate_co2_emissions(daily_energy, EMISSION_FACTORS.get('LPG', 0.213), institution_data)
                
                total_energy += delivered
                total_cost += lpg_cost
                total_emissions += lpg_emissions
                fuels_used.append('LPG')
                
                result['fuel_details']['LPG'] = {
                    'quantity': mixed_cylinders,
                    'unit': 'Cylinders',
                    'energy_delivered': delivered,
                    'monthly_cost': lpg_cost,
                    'annual_emissions': lpg_emissions,
                    'efficiency': efficiency
                }
            
            # PNG
            if data.get('mixed_use_png') in [True, 'true', 'on', '1', 1, 'on']:
                logger.log_step("Mixed: Processing PNG")
                mixed_bill = float(data.get('mixed_monthly_bill_png') or 5000)

                # Use same canonical commercial PNG flow as single-fuel mode.
                png_price_data = db_helper.get_png_pricing(
                    district=institution_data.get('district', 'All'),
                    category='Commercial'
                )
                rate_per_scm = float(png_price_data['price_per_scm']) if png_price_data else 47.0
                png_calc = helper.calculate_png_consumption_from_bill(
                    mixed_bill,
                    rate_per_scm=rate_per_scm,
                    district=institution_data.get('district', 'All'),
                    category='Commercial'
                )
                monthly_scm = png_calc.get('monthly_scm_consumption', 0)
                png_energy = png_calc.get('monthly_energy_kwh', monthly_scm * PNG_CALORIFIC_VALUE)
                modeled_bill = png_calc.get('total_bill', mixed_bill)
                efficiency = DEFAULT_EFFICIENCIES.get('PNG', 0.70)
                delivered = png_energy * efficiency
                
                daily_energy = png_energy / monthly_factor
                png_emissions = calculate_co2_emissions(daily_energy, EMISSION_FACTORS.get('PNG', 0.2), institution_data)
                
                total_energy += delivered
                total_cost += mixed_bill
                total_emissions += png_emissions
                fuels_used.append('PNG')
                
                result['fuel_details']['PNG'] = {
                    'quantity': monthly_scm,
                    'unit': 'SCM',
                    'energy_delivered': delivered,
                    'monthly_cost': mixed_bill,
                    'modeled_bill': modeled_bill,
                    'rate_per_scm': rate_per_scm,
                    'annual_emissions': png_emissions,
                    'efficiency': efficiency
                }
            
            # Electricity
            if data.get('mixed_use_elec') in [True, 'true', 'on', '1', 1, 'on']:
                logger.log_step("Mixed: Processing Electricity")
                mixed_kwh = float(data.get('mixed_monthly_kwh') or 500)
                tariff = float(
                    institution_data.get('electricity_tariff')
                    or db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.5)
                )
                
                efficiency = DEFAULT_EFFICIENCIES.get('Grid electricity', 0.90)
                delivered = mixed_kwh * efficiency
                elec_cost = mixed_kwh * tariff
                
                daily_energy = mixed_kwh / monthly_factor
                elec_emissions = calculate_co2_emissions(
                    daily_energy,
                    EMISSION_FACTORS.get('Grid electricity', 0.82),
                    institution_data
                )
                
                total_energy += delivered
                total_cost += elec_cost
                total_emissions += elec_emissions
                fuels_used.append('Grid electricity')
                
                result['fuel_details']['Grid electricity'] = {
                    'quantity': mixed_kwh,
                    'unit': 'kWh',
                    'energy_delivered': delivered,
                    'monthly_cost': elec_cost,
                    'annual_emissions': elec_emissions,
                    'efficiency': efficiency
                }
            
            # Traditional Biomass
            if data.get('mixed_use_biomass') in [True, 'true', 'on', '1', 1, 'on']:
                logger.log_step("Mixed: Processing Traditional Biomass")
                mixed_kg = float(data.get('mixed_monthly_kg_biomass') or 200)
                biomass_price_data = db_helper.get_fuel_unit_price(district, 'Traditional Solid Biomass', 'Commercial')
                biomass_cost_per_kg = float(
                    biomass_price_data['unit_price']
                    if biomass_price_data and biomass_price_data.get('unit_price') is not None
                    else db_helper.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0)
                )
                biomass_energy_content = float(db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5))
                
                biomass_energy = mixed_kg * biomass_energy_content
                efficiency = DEFAULT_EFFICIENCIES.get('Traditional Solid Biomass', 0.18)
                delivered = biomass_energy * efficiency
                biomass_cost = mixed_kg * biomass_cost_per_kg
                
                biomass_emissions = calculate_co2_emissions(
                    biomass_energy / monthly_factor,
                    EMISSION_FACTORS.get('Traditional Solid Biomass', 0.4),
                    institution_data
                )
                
                total_energy += delivered
                total_cost += biomass_cost
                total_emissions += biomass_emissions
                fuels_used.append('Traditional Solid Biomass')
                
                result['fuel_details']['Traditional Solid Biomass'] = {
                    'quantity': mixed_kg,
                    'unit': 'kg',
                    'energy_delivered': delivered,
                    'monthly_cost': biomass_cost,
                    'annual_emissions': biomass_emissions,
                    'efficiency': efficiency,
                    'energy_required': biomass_energy,
                    'cost_per_kg': biomass_cost_per_kg,
                    'energy_per_kg_kwh': biomass_energy_content
                }
            
            monthly_energy_kwh = total_energy
            monthly_cost = total_cost
            annual_co2_kg = total_emissions
            
            logger.log_result("Mixed Fuel Total", f"{total_energy:.2f} kWh, ₹{total_cost:.2f}, {total_emissions:.2f} kg CO₂/year")
        
        # ==============================================================
        # Populate Final Result
        # ==============================================================
        
        # Re-structure to match dish-based output
        logger.log_data("DEBUG FUEL DETAILS BEFORE BREAKDOWN", result['fuel_details'])
        fuel_breakdown = {
            fuel: details
            for fuel, details in result['fuel_details'].items()
            if isinstance(details, dict)
        }
        fuels_used = list(fuel_breakdown.keys())
        
        # Determine primary fuel type for display
        if len(fuels_used) > 1:
            fuel_type_display = 'Multiple'
        elif len(fuels_used) == 1:
            fuel_type_display = fuels_used[0]
        else:
            fuel_type_display = 'None'

        # Calculate per-serving metrics
        total_monthly_servings = servings_per_day * working_days
        cost_per_serving = monthly_cost / total_monthly_servings if total_monthly_servings > 0 else 0
        energy_per_serving = monthly_energy_kwh / total_monthly_servings if total_monthly_servings > 0 else 0

        result = {
            'monthly_energy_kwh': monthly_energy_kwh,
            'monthly_cost': monthly_cost,
            'annual_emissions': annual_co2_kg, # Alias for compatibility
            'annual_co2_kg': annual_co2_kg,
            'cost_per_serving': cost_per_serving,
            'energy_per_serving_kwh': energy_per_serving,
            'fuel_details': {
                'calculation_method': 'consumption_based',
                'type': fuel_type_display,
                'fuels_used': fuels_used,
                'fuel_breakdown': fuel_breakdown,
                'servings_per_day': servings_per_day,
                'working_days': working_days,
                'institution_type': institution_data.get('institution_type', 'School'),
                'meal_breakdown': {} # Not available for consumption-based
            }
        }
        
        # Overall thermal efficiency
        total_energy_required = 0
        for fuel_name, details in fuel_breakdown.items():
            energy_required = details.get('energy_required')
            if energy_required is None:
                efficiency_value = details.get('thermal_efficiency')
                if efficiency_value is None:
                    efficiency_value = details.get('efficiency', DEFAULT_EFFICIENCIES.get(fuel_name, 0.60))
                    if efficiency_value > 1:
                        efficiency_value = efficiency_value / 100.0
                else:
                    efficiency_value = efficiency_value / 100.0
                delivered = details.get('energy_delivered', details.get('delivered_energy_kwh', 0))
                energy_required = delivered / efficiency_value if efficiency_value else delivered
                details['energy_required'] = energy_required
            total_energy_required += energy_required
        result['overall_thermal_efficiency'] = (
            (monthly_energy_kwh / total_energy_required) * 100
            if total_energy_required > 0 else 0
        )
        
        # Per serving metrics
        if servings_per_day > 0 and working_days > 0:
            total_servings_month = servings_per_day * working_days
            result['energy_per_serving_kwh'] = monthly_energy_kwh / total_servings_month
            result['cost_per_serving'] = monthly_cost / total_servings_month

        # Calculate environmental grade (Per Serving)
        total_annual_servings = servings_per_day * working_days * 12
        co2_per_serving = (annual_co2_kg / total_annual_servings) if total_annual_servings > 0 else 0
        grade, label = db_helper.get_environmental_grade(co2_per_serving, metric='co2_per_serving_kg')
        result['environmental_grade'] = grade
        
        logger.log_result("Environmental Grade", f"{grade} ({label})", f"Based on {co2_per_serving:.3f} kg/serving")
        
        logger.log_success(f"Consumption calculation complete: {monthly_energy_kwh:.2f} kWh/month, ₹{monthly_cost:.2f}/month")
        
        return result
        
    except Exception as e:
        logger.log_error(f"Error in consumption-based calculation: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'message': f'Error calculating consumption: {str(e)}'
        }


def calculate_dish_based(data, institution_data, kitchen_data, institution_id):
    """
    Commercial dish-based calculation (matches residential pattern)
    Portion-based cooking with serving volume efficiency
    """
    logger = get_logger()
    logger.log_subsection("COMMERCIAL DISH-BASED CALCULATION")
    
    try:
        # Get commercial dishes from database
        logger.log_step("Loading commercial dishes from database")
        dishes_list = db_helper.get_all_dishes(dish_type='commercial')
        
        if not dishes_list:
            logger.log_error("Commercial dishes data not available")
            return {'status': 'error', 'message': 'Commercial dishes data not available'}
        
        dishes = pd.DataFrame(dishes_list)
        
        # Map column names to match residential pattern
        if 'dish_name' in dishes.columns and 'Dishes' not in dishes.columns:
            dishes = dishes.rename(columns={
                'dish_name': 'Dishes',
                'dish_name_ml': 'Dishes_ml',
                'category_name': 'Category'
            })
        
        logger.log_success(f"Loaded {len(dishes)} commercial dishes")
        
        # Extract institution parameters
        servings_per_day = int(data.get('servings_per_day', 100))
        try:
            working_days = int(data.get('working_days_per_month', 30))
        except (ValueError, TypeError):
            working_days = 30
        institution_type = institution_data.get('institution_type', 'School')
        district = institution_data.get('district', 'Thiruvananthapuram')
        
        logger.log_data("Institution Parameters", {
            "servings_per_day": servings_per_day,
            "working_days": working_days,
            "institution_type": institution_type
        })
        
        # Extract dish selections and fuel assignments
        selected_dishes = []
        fuel_selections = {}
        meal_intensities = {
            'breakfast_type': data.get('breakfast_type', 'Normal'),
            'lunch_type': data.get('lunch_type', 'Heavy'),
            'dinner_type': data.get('dinner_type', 'Light')
        }
        
        dishes_with_details = []  # For template display
        for category in ['Breakfast', 'Lunch', 'Dinner', 'Snacks']:
            # Use getlist() to get all values with same name
            dishes_for_meal = data.getlist(f'{category.lower()}_dishes') if hasattr(data, 'getlist') else data.get(f'{category.lower()}_dishes', [])
            # Ensure it's a list
            if isinstance(dishes_for_meal, str):
                dishes_for_meal = [dishes_for_meal] if dishes_for_meal else []
            logger.log_input(f"{category} dishes", f"{len(dishes_for_meal)} selected")

            for dish in dishes_for_meal:
                fuel_type = data.get(f'{dish}_fuel', 'LPG')
                selected_dishes.append({
                    'Dishes': dish,
                    'Category': category,
                    'stoves': fuel_type
                })
                fuel_selections[dish] = fuel_type
                # Store dish with full details for template
                dishes_with_details.append({
                    'dish': dish,
                    'category': category,
                    'fuel': fuel_type
                })
        
        if not selected_dishes:
            logger.log_error("No dishes selected")
            return {'status': 'error', 'message': 'No dishes selected'}
        
        logger.log_success(f"Total {len(selected_dishes)} dishes selected")
        
        # Create DataFrame from selections
        user_responses = pd.DataFrame(selected_dishes)
        
        # Merge with dish database
        user_dishes_with_data = pd.merge(
            user_responses,
            dishes,
            on='Dishes',
            how='left',
            suffixes=('_user', '_dish')
        )
        
        # Restore Category from user data
        user_dishes_with_data['Category'] = user_dishes_with_data['Category_user']
        
        if user_dishes_with_data.empty:
            logger.log_error("No matching dishes found")
            return {'status': 'error', 'message': 'No matching dishes found'}
        
        # Calculate monthly energy using commercial_monthly_energy
        energy_df = commercial_monthly_energy(
            user_dishes_with_data,
            servings_per_day,
            working_days,
            institution_type,
            breakfast=meal_intensities['breakfast_type'],
            lunch=meal_intensities['lunch_type'],
            dinner=meal_intensities['dinner_type']
        )
        
        # Group energy by fuel type
        fuel_energy_dict = {}
        fuel_efficiency_dict = {}
        fuel_cost_per_kwh_dict = {}
        current_fuel_mix = list(set(user_dishes_with_data['stoves']))
        
        logger.log_data("Fuels used", current_fuel_mix)
        
        # Initialize FuelCostCalculator
        from fuel_cost_standardizer import FuelCostCalculator
        cost_calculator = FuelCostCalculator(
            db_helper,
            institution_data=institution_data,
            kitchen_data=kitchen_data
        )
        
        for fuel in current_fuel_mix:
            fuel_mask = energy_df['stoves'] == fuel
            fuel_energy = energy_df.loc[fuel_mask, 'Final_Energy_Value'].sum()
            fuel_energy_dict[fuel] = fuel_energy
            
            # Get efficiency from database or defaults
            fuel_efficiency_dict[fuel] = DEFAULT_EFFICIENCIES.get(fuel, 0.60)
            
            # Calculate energy required
            efficiency = fuel_efficiency_dict[fuel]
            energy_required = fuel_energy / efficiency if efficiency > 0 else 0
            
            # Determine User Input Cost if any
            user_input_cost = None
            if fuel == 'LPG':
                commercial_price_input = data.get('commercial_cylinder_price')
                if commercial_price_input:
                    try:
                        price = float(commercial_price_input)
                        if price > 0:
                            user_input_cost = price / (19.0 * LPG_CALORIFIC_VALUE)
                    except: pass
            elif fuel == 'PNG':
                png_rate_input = data.get('png_rate_per_scm') or data.get('rate_per_scm')
                if png_rate_input:
                    try:
                        rate = float(png_rate_input)
                        if rate > 0:
                            user_input_cost = rate / PNG_CALORIFIC_VALUE
                    except: pass
            
            # Get Standardized Cost
            cost_per_kwh, source = cost_calculator.get_cost_per_kwh(
                fuel,
                user_input_cost=user_input_cost,
                energy_required=energy_required
            )
            fuel_cost_per_kwh_dict[fuel] = cost_per_kwh
            
            logger.log_result(f"{fuel} Cost", f"Rs {cost_per_kwh:.2f}/kWh", source)
        
        # Calculate using helper function
        logger.log_step("Calculating emissions and costs using helper function")
        multi_fuel_results = calculate_fuel_emissions_and_costs(
            fuel_energy_dict,
            fuel_efficiency_dict,
            fuel_cost_per_kwh_dict,
            institution_data=institution_data  # Pass context for correct annualization (working days)
        )
        
        # Calculate overall thermal efficiency
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
                "delivered": f"{multi_fuel_results['total_energy_delivered']:.2f} kWh",
                "required": f"{total_energy_required:.2f} kWh"
            },
            f"{overall_efficiency:.1f}%"
        )
        
        # Calculate meal-level breakdown for dish-based mode
        meal_breakdown = {}
        for meal in ['Breakfast', 'Lunch', 'Dinner', 'Snacks']:
            meal_mask = energy_df['Category'].str.lower() == meal.lower()
            if meal_mask.any():
                meal_energy = energy_df.loc[meal_mask, 'Final_Energy_Value'].sum()
                meal_cost = 0

                # Calculate cost for this meal based on fuel used
                for fuel in current_fuel_mix:
                    fuel_meal_mask = meal_mask & (energy_df['stoves'] == fuel)
                    if fuel_meal_mask.any():
                        fuel_meal_energy = energy_df.loc[fuel_meal_mask, 'Final_Energy_Value'].sum()
                        # Apply fuel efficiency to get required energy
                        efficiency = DEFAULT_EFFICIENCIES.get(fuel, 0.60)
                        required_energy = fuel_meal_energy / efficiency
                        meal_cost += required_energy * fuel_cost_per_kwh_dict.get(fuel, 8.0)

                meal_breakdown[meal] = {
                    'energy_kwh': meal_energy,
                    'cost': meal_cost,
                    'percentage': (meal_energy / multi_fuel_results['total_energy_delivered'] * 100) if multi_fuel_results['total_energy_delivered'] > 0 else 0
                }

        logger.log_data("Meal breakdown", meal_breakdown)

        # Calculate per-serving metrics
        total_monthly_servings = servings_per_day * working_days
        cost_per_serving = multi_fuel_results['total_monthly_cost'] / total_monthly_servings if total_monthly_servings > 0 else 0
        energy_per_serving = multi_fuel_results['total_energy_delivered'] / total_monthly_servings if total_monthly_servings > 0 else 0

        # Post-process fuel breakdown to add quantities for display
        for fuel, details in multi_fuel_results['fuel_breakdown'].items():
            if fuel == 'LPG':
                 quantity_kg = details['energy_required'] / LPG_CALORIFIC_VALUE if LPG_CALORIFIC_VALUE > 0 else 0
                 details['quantity'] = quantity_kg
                 details['unit'] = 'kg'
                 details['monthly_kg'] = quantity_kg
            elif fuel == 'PNG':
                 quantity_scm = details['energy_required'] / PNG_CALORIFIC_VALUE if PNG_CALORIFIC_VALUE > 0 else 0
                 details['quantity'] = quantity_scm
                 details['unit'] = 'SCM'
                 details['monthly_scm'] = quantity_scm

        # Build result (MATCHING RESIDENTIAL STRUCTURE)
        result = {
            'monthly_energy_kwh': multi_fuel_results['total_energy_delivered'],
            'monthly_cost': multi_fuel_results['total_monthly_cost'],
            'annual_emissions': multi_fuel_results['total_annual_emissions'],
            'overall_thermal_efficiency': overall_efficiency,
            'cost_per_serving': cost_per_serving,
            'energy_per_serving_kwh': energy_per_serving,
            'fuel_details': {
                'type': 'Multiple' if len(current_fuel_mix) > 1 else current_fuel_mix[0],
                'fuels_used': current_fuel_mix,
                'fuel_breakdown': multi_fuel_results['fuel_breakdown'],
                'calculation_method': 'dish_based',
                'servings_per_day': servings_per_day,
                'working_days': working_days,
                'institution_type': institution_type,
                'meal_breakdown': meal_breakdown,  # Add meal-level data
                'selected_dishes': dishes_with_details  # Add selected dishes with category and fuel
            }
        }
        
        
        # Calculate environmental grade (Per Serving)
        total_annual_servings = servings_per_day * working_days * 12
        co2_per_serving = (result['annual_emissions'] / total_annual_servings) if total_annual_servings > 0 else 0
        grade, label = db_helper.get_environmental_grade(co2_per_serving, metric='co2_per_serving_kg')
        result['environmental_grade'] = grade

        logger.log_subsection("FINAL COMMERCIAL DISH-BASED RESULTS")
        logger.log_result("Monthly Energy (useful)", f"{result['monthly_energy_kwh']:.2f} kWh")
        logger.log_result("Monthly Cost", f"Rs {result['monthly_cost']:.2f}")
        logger.log_result("Annual Emissions", f"{result['annual_emissions']:.2f} kg CO₂/year")
        logger.log_result("Overall Efficiency", f"{result['overall_thermal_efficiency']:.1f}%")
        logger.log_result("Environmental Grade", f"{grade} ({label})", f"Based on {co2_per_serving:.3f} kg/serving")
        
        # Save to database
        if institution_id:
            logger.log_step(f"Saving commercial analysis for institution {institution_id}")
            save_commercial_analysis(institution_id, kitchen_data, result)
            logger.log_success("Commercial analysis saved")
        
        logger.log_success("Commercial dish-based calculation completed")
        
        return result
        
    except Exception as e:
        logger.log_error(f"Error in commercial dish-based calculation: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        return {'status': 'error', 'message': str(e)}


def save_commercial_analysis(institution_id, kitchen_data, result):
    """Save commercial cooking analysis to database"""
    import json
    
    logger = get_logger()
    logger.log_step(f"Saving commercial analysis for institution {institution_id}")
    
    try:
        # Extract fuel details
        fuel_details = result.get('fuel_details', {})
        fuel_breakdown_json = json.dumps(fuel_details)
        
        # Determine primary fuel
        if isinstance(fuel_details, dict):
            if 'type' in fuel_details:
                primary_fuel = fuel_details['type']
            elif 'fuels_used' in fuel_details:
                fuels_list = fuel_details.get('fuels_used', [])
                primary_fuel = 'Multiple' if len(fuels_list) > 1 else (fuels_list[0] if fuels_list else 'Unknown')
            else:
                primary_fuel = 'Unknown'
        else:
            primary_fuel = 'Unknown'
        
        logger.log_data("Primary Fuel", primary_fuel)
        
        # Calculate health risk score if not already in result
        health_risk_score = result.get('health_risk_score', 0)
        if health_risk_score == 0 and kitchen_data:
            # Use simple health calculation based on fuel and kitchen conditions
            # Default risk based on fuel type only
            fuel_risk_defaults = {
                'Traditional Solid Biomass': 8.5,
                'LPG': 2.5,
                'PNG': 2.0,
                'Grid electricity': 0.5,
                'Biogas': 2.0,
                'Multiple': 4.0
            }
            health_risk_score = fuel_risk_defaults.get(primary_fuel, 3.0)
        
        # Calculate environmental grade if not already in result
        environmental_grade = result.get('environmental_grade', 'C')
        # Legacy hardcoded logic removed. Relies on db_helper.get_environmental_grade.
        
        logger.log_data("Environmental Grade", environmental_grade)
        logger.log_data("Health Risk Score", f"{health_risk_score:.2f}")
        
        # Save to commercial_analysis table
        query = """
            INSERT OR REPLACE INTO commercial_analysis 
            (institution_id, monthly_energy_kwh, monthly_cost, annual_emissions,
             calculation_method, fuel_breakdown, primary_fuel, 
             health_risk_score, environmental_grade, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        
        params = (
            institution_id,
            result.get('monthly_energy_kwh', 0),
            result.get('monthly_cost', 0),
            result.get('annual_emissions', 0),
            fuel_details.get('calculation_method', 'unknown'),
            fuel_breakdown_json,
            primary_fuel,
            health_risk_score,
            environmental_grade
        )

        conn = get_user_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
        finally:
            close_user_connection(conn)
        
        logger.log_success(f"✅ Commercial analysis saved for institution {institution_id}")
        logger.log_data("Saved Data", {
            "monthly_energy_kwh": f"{result.get('monthly_energy_kwh', 0):.2f}",
            "monthly_cost": f"₹{result.get('monthly_cost', 0):.2f}",
            "annual_emissions": f"{result.get('annual_emissions', 0):.2f} kg CO2",
            "primary_fuel": primary_fuel,
            "health_risk_score": f"{health_risk_score:.2f}",
            "environmental_grade": environmental_grade
        })
        
    except Exception as e:
        logger.log_error(f"❌ Error saving commercial analysis: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        # Don't raise exception - allow analysis to continue even if save fails
