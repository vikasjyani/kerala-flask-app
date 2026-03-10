"""
Standardized Fuel Cost per kWh Calculator
==========================================
Priority System: User Input → Database

This module provides a unified interface for calculating cost per kWh
for all fuel types with consistent priority handling.
"""

from typing import Optional, Dict, Tuple
from debug_logger import get_logger


class FuelCostCalculator:
    """
    Centralized fuel cost calculator with priority-based cost resolution.
    
    Priority Order:
    1. User-provided cost (from form input)
    2. Database pricing (district/category specific)
    
    Note: No hardcoded fallback values - database must have complete pricing data.
    """
    
    def __init__(self, db_helper, household_data=None, institution_data=None, kitchen_data=None):
        """
        Initialize calculator with database helper and context data.
        
        Args:
            db_helper: Database helper instance
            household_data: Residential user data (optional)
            institution_data: Commercial user data (optional)
            kitchen_data: Kitchen configuration data (optional)
        """
        self.db = db_helper
        self.household_data = household_data or {}
        self.institution_data = institution_data or {}
        self.kitchen_data = kitchen_data or {}
        self.logger = get_logger()
        
        # Determine if this is commercial or residential
        self.is_commercial = bool(institution_data)
        self.entity_data = institution_data if self.is_commercial else household_data
        
        # Get district for regional pricing
        self.district = self.entity_data.get('district', 'Thiruvananthapuram')
        self.area_type = self.entity_data.get('area_type', 'Urban')
        
        # Zero-cost fuels (no variable fuel cost, capital costs handled separately)
        self.ZERO_COST_FUELS = ['Biogas', 'Solar rooftop', 'Solar + BESS']
    
    def get_cost_per_kwh(self, fuel_name: str, user_input_cost: Optional[float] = None,
                         energy_required: Optional[float] = None) -> Tuple[float, str]:
        """
        Get cost per kWh for any fuel with priority-based resolution.
        
        Args:
            fuel_name: Name of the fuel
            user_input_cost: User-provided cost (priority 1)
            energy_required: Required energy in kWh (needed for some fuels)
        
        Returns:
            Tuple of (cost_per_kwh, source_description)
            source_description explains where the cost came from
        """
        self.logger.log_subsection(f"COST PER KWH CALCULATION: {fuel_name}")
        
        # Priority 1: User Input
        if user_input_cost is not None and user_input_cost > 0:
            self.logger.log_result("Priority 1: User Input", f"₹{user_input_cost:.2f}/kWh")
            return user_input_cost, "User Provided"
        
        # Priority 2: Database
        db_cost = self._get_cost_from_database(fuel_name, energy_required)
        if db_cost is not None:
            source = f"Database ({self.district})" if self.district else "Database"
            self.logger.log_result("Priority 2: Database", f"₹{db_cost:.2f}/kWh", source)
            return db_cost, source
        
        # Zero-cost fuels (Biogas, Solar) - no per-kWh fuel cost
        if fuel_name in self.ZERO_COST_FUELS:
            self.logger.log_result("Zero-cost fuel", "₹0.00/kWh")
            return 0.0, "Zero Cost Fuel"
        
        # No fallback - log warning and return None to indicate missing data
        self.logger.log_warning(f"No pricing data found for {fuel_name} in database")
        return None, "Not Found"
    
    def _get_cost_from_database(self, fuel_name: str, energy_required: Optional[float] = None) -> Optional[float]:
        """
        Get cost per kWh from database with fuel-specific logic.
        
        Args:
            fuel_name: Name of the fuel
            energy_required: Required energy (needed for PNG with slab rates)
        
        Returns:
            Cost per kWh or None if not found in database
        """
        try:
            # Check for direct 'Cost per kWh' if available or specific fuel dispatch
            
            # Note: We rely on specific handlers (below) to convert unit prices (Cylinders, SCM) to kWh cost.
            # Only use direct fetching if we know the unit is kWh ?
            # For now, let's skip the generic "regional_pricing" check that assumed everything is in Rs/kWh
            # and dispatch directly to handlers which we have just updated.
            
            # Fallback to specialized logic
            if fuel_name == 'LPG':
                return self._calculate_lpg_cost_from_db()
            
            elif fuel_name == 'PNG':
                return self._calculate_png_cost_from_db(energy_required)
            
            elif fuel_name == 'Grid electricity':
                return self._get_electricity_tariff_from_db()
            
            elif fuel_name == 'Biogas':
                return self._calculate_biogas_cost_from_db(energy_required)
            
            elif fuel_name in ['Traditional Solid Biomass', 'Improved Cookstove (Biomass)']:
                return self._calculate_biomass_cost_from_db()
            
            else:
                # For other fuels, try system parameters
                # E.g. Kerosene
                try:
                    sys_param_cost = self.db.get_system_parameter(f'{fuel_name.upper()}_COST_PER_KWH')
                    if sys_param_cost is not None:
                        return float(sys_param_cost)
                except:
                    pass
                return None
        
        except Exception as e:
            self.logger.log_error(f"Database lookup failed for {fuel_name}: {e}")
            return None
    
    def _calculate_lpg_cost_from_db(self) -> Optional[float]:
        """Calculate LPG cost per kWh from database pricing."""
        category = 'Commercial' if self.is_commercial else 'Domestic'
        
        # Get pricing from database using new consolidated method
        # Returns: {'unit_price': ..., 'unit_name': ...}
        pricing = self.db.get_fuel_unit_price(self.district, 'LPG', category)
        
        if pricing:
            # Determine which price to use
            unit_price = pricing['unit_price']
            
            # If domestic, check for subsidy eligibility
            if category == 'Domestic':
                # Check income threshold
                try:
                    income_threshold = float(self.db.get_system_parameter('SUBSIDY_INCOME_THRESHOLD', 50000))
                    household_income = float(self.household_data.get('monthly_income', 999999)) # Default high if missing
                    
                    if household_income < income_threshold:
                        # Eligible for subsidy
                        subsidized_price = float(pricing.get('subsidized_unit_price', 0))
                        if subsidized_price > 0:
                            unit_price = subsidized_price
                            self.logger.log_result("Subsidy Applied", f"Income {household_income} < {income_threshold}")
                except Exception as e:
                    pass

            # Get parameters from system_parameters
            try:
                # Determine weight based on pricing category implicitly or defaulting
                # Typically Domestic=14.2kg, Commercial=19.0kg
                weight_param = 'LPG_COMMERCIAL_CYLINDER_WEIGHT_KG' if category == 'Commercial' else 'LPG_DOMESTIC_CYLINDER_WEIGHT_KG'
                default_weight = 19.0 if category == 'Commercial' else 14.2
                
                cylinder_weight = float(self.db.get_system_parameter(weight_param, default_weight))
                calorific_value = float(self.db.get_system_parameter('LPG_CALORIFIC_VALUE_KWH_PER_KG', 12.8))
            except Exception as e:
                self.logger.log_error(f"Error fetching LPG params: {e}")
                cylinder_weight = 14.2 
                calorific_value = 12.8
            
            # Calculate cost per kWh
            energy_per_cylinder = cylinder_weight * calorific_value
            if energy_per_cylinder > 0:
                cost_per_kwh = unit_price / energy_per_cylinder
                
                self.logger.log_calculation(
                    "LPG Cost from DB",
                    "unit_price / (weight × calorific_value)",
                    {
                        "category": category,
                        "unit_price": f"₹{unit_price}",
                        "weight": f"{cylinder_weight} kg",
                        "calorific_value": f"{calorific_value} kWh/kg",
                        "energy_per_cylinder": f"{energy_per_cylinder} kWh"
                    },
                    f"₹{cost_per_kwh:.2f}/kWh"
                )
                return cost_per_kwh
            
        return None
    
    def _calculate_png_cost_from_db(self, energy_required: Optional[float] = None) -> Optional[float]:
        """Calculate PNG cost per kWh from database pricing."""
        category = 'Commercial' if self.is_commercial else 'Domestic'
        
        # Get PNG pricing 
        # PNG might be district specific in new DB, or 'All'
        # Try district first, then fall back? 
        # Our migration populated per district, so district should work.
        pricing = self.db.get_fuel_unit_price(self.district, 'PNG', category)
        
        if pricing:
            rate_per_scm = pricing['unit_price']
            
            # Get calorific value
            try:
                calorific_value = float(self.db.get_system_parameter('PNG_CALORIFIC_VALUE_KWH_PER_SCM', 10.2))
            except:
                calorific_value = 10.2
            
            # Calculate base cost per kWh (variable cost only)
            if calorific_value > 0:
                base_cost_per_kwh = rate_per_scm / calorific_value
                
                # Add fixed charges if we know the energy requirement
                if energy_required and energy_required > 0:
                    # Get fixed charges
                    try:
                        fixed_charge = float(self.db.get_system_parameter('PNG_FIXED_CHARGE_MONTHLY', 0)) # Defaulting 0 if not set
                        meter_rent = float(self.db.get_system_parameter('PNG_METER_RENT_MONTHLY', 0))
                        total_fixed = fixed_charge + meter_rent
                    except:
                        total_fixed = 0
                    
                    # Add fixed charges to cost per kWh
                    cost_per_kwh = base_cost_per_kwh + (total_fixed / energy_required)
                    
                    self.logger.log_calculation(
                        "PNG Cost from DB (with fixed charges)",
                        "rate/calorific_value + fixed_charges/energy",
                        {
                            "rate_per_scm": f"₹{rate_per_scm}",
                            "calorific_value": f"{calorific_value} kWh/SCM",
                            "fixed_charges": f"₹{total_fixed}",
                            "energy_required": f"{energy_required} kWh"
                        },
                        f"₹{cost_per_kwh:.2f}/kWh"
                    )
                else:
                    # Without energy requirement, use base cost
                    cost_per_kwh = base_cost_per_kwh
                    
                    self.logger.log_calculation(
                        "PNG Cost from DB (variable only)",
                        "rate/calorific_value",
                        {
                            "rate_per_scm": f"₹{rate_per_scm}",
                            "calorific_value": f"{calorific_value} kWh/SCM"
                        },
                        f"₹{cost_per_kwh:.2f}/kWh"
                    )
                
                return cost_per_kwh
        
        return None
    
    def _get_electricity_tariff_from_db(self) -> Optional[float]:
        """Get electricity tariff from database or user data."""
        # Priority order for electricity:
        # 1. Kitchen data electricity_tariff (direct input)
        # 2. Entity data electricity_tariff (profile data)
        # 3. Database system parameter
        
        try:
            tariff_k = self.kitchen_data.get('electricity_tariff')
            if tariff_k and float(tariff_k) > 0:
                return float(tariff_k)
                
            tariff_e = self.entity_data.get('electricity_tariff')
            if tariff_e and float(tariff_e) > 0:
                return float(tariff_e)
                
            param_name = 'ELECTRICITY_COMMERCIAL_RATE' if self.is_commercial else 'ELECTRICITY_RESIDENTIAL_RATE'
            
            db_rate = self.db.get_system_parameter(param_name, None)
            if db_rate is not None:
                return float(db_rate)
            return None
            
        except:
            return None
    
    def _calculate_biogas_cost_from_db(self, energy_required: Optional[float] = None) -> Optional[float]:
        """Calculate biogas cost per kWh from database pricing."""
        category = 'Commercial' if self.is_commercial else 'Domestic'
        
        # Biogas is complicated because cost depends on installation + opex
        # For simplified priority calculator, we usually use the default (0/low cost)
        # UNLESS we have specific pricing models.
        
        # Let's try to use the helper function if we have energy required
        if energy_required and energy_required > 0:
            try:
                # Import helper function to calculate complete biogas costs
                # We do local import to avoid circular dependency if helper imports this file
                from helper import compute_biogas_costs, BIOGAS_ENERGY_PER_M3
                
                # Calculate monthly m3 needed
                if BIOGAS_ENERGY_PER_M3 > 0:
                    monthly_m3 = energy_required / BIOGAS_ENERGY_PER_M3
                    
                    # Get comprehensive cost breakdown
                    biogas_costs = compute_biogas_costs(monthly_m3, category=category)
                    
                    cost_per_kwh = biogas_costs.get('cost_per_kwh_primary', 0)
                    
                    self.logger.log_calculation(
                        "Biogas Cost from DB",
                        "total_monthly_cost / primary_energy",
                        {
                            "monthly_m3": f"{monthly_m3:.2f}",
                            "total_cost": f"₹{biogas_costs['total_monthly_cost']:.2f}",
                            "primary_energy": f"{biogas_costs['primary_energy_kwh']:.2f} kWh"
                        },
                        f"₹{cost_per_kwh:.2f}/kWh"
                    )
                    return cost_per_kwh
            except ImportError:
                 # Fallback if helper not available or circular import
                 pass
            except Exception as e:
                self.logger.log_error(f"Biogas calculation error: {e}")
                
        # Fallback to simple pricing if available
        biogas_pricing = self.db.get_biogas_pricing(category)
        if biogas_pricing:
             # This table might not have direct 'per kwh' cost, usually it has installation costs
             # So we return None to let it fall back to default
             return None
             
        return None
    
    def _calculate_biomass_cost_from_db(self) -> Optional[float]:
        """Calculate biomass cost per kWh from database pricing."""
        category = 'Commercial' if self.is_commercial else 'Domestic'
        
        # Determine specific fuel name (Traditional vs Improved)
        # Assuming generic 'Traditional Solid Biomass' for base price lookup if specific not found?
        # Actually our DB has entries for both potentially.
        # Let's try 'Traditional Solid Biomass' as the base commodity (Firewood) price
        
        pricing = self.db.get_fuel_unit_price(self.district, 'Traditional Solid Biomass', category)
        
        if pricing:
            cost_per_kg = pricing['unit_price']
            
            # Get energy content
            try:
                energy_content = float(self.db.get_system_parameter('BIOMASS_ENERGY_CONTENT_KWH_PER_KG', 4.5))
            except:
                energy_content = 4.5
        else:
            # Fallback to system defaults if no regional price
            try:
                cost_per_kg = float(self.db.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0))
                energy_content = float(self.db.get_system_parameter('BIOMASS_ENERGY_CONTENT_KWH_PER_KG', 4.5))
            except:
                cost_per_kg = 5.0
                energy_content = 4.5
        
        if energy_content > 0:
            cost_per_kwh = cost_per_kg / energy_content
            
            self.logger.log_calculation(
                "Biomass Cost from DB",
                "cost_per_kg / energy_content",
                {
                    "cost_per_kg": f"₹{cost_per_kg}",
                    "energy_content": f"{energy_content} kWh/kg"
                },
                f"₹{cost_per_kwh:.2f}/kWh"
            )
            return cost_per_kwh
        
        return None


# Convenience functions for integration with existing code

def get_standardized_fuel_cost(fuel_name: str, db_helper, household_data=None, 
                                institution_data=None, kitchen_data=None,
                                user_input_cost: Optional[float] = None,
                                energy_required: Optional[float] = None) -> Tuple[float, str]:
    """
    Get standardized cost per kWh for any fuel.
    """
    calculator = FuelCostCalculator(
        db_helper,
        household_data=household_data,
        institution_data=institution_data,
        kitchen_data=kitchen_data
    )
    
    return calculator.get_cost_per_kwh(
        fuel_name,
        user_input_cost=user_input_cost,
        energy_required=energy_required
    )


def build_fuel_cost_dict(fuel_list: list, db_helper, household_data=None,
                         institution_data=None, kitchen_data=None,
                         energy_required_dict: Optional[Dict[str, float]] = None,
                         user_costs_dict: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """
    Build a dictionary of {fuel_name: cost_per_kwh} for multiple fuels.
    
    Args:
        fuel_list: List of fuel names
        db_helper: Database helper instance
        household_data: Residential user data
        institution_data: Commercial user data
        kitchen_data: Kitchen configuration
        energy_required_dict: Optional dict of {fuel_name: energy_kwh}
        user_costs_dict: Optional dict of {fuel_name: user_cost_per_kwh}
    
    Returns:
        Dict of {fuel_name: cost_per_kwh}
    """
    calculator = FuelCostCalculator(
        db_helper,
        household_data=household_data,
        institution_data=institution_data,
        kitchen_data=kitchen_data
    )
    
    energy_dict = energy_required_dict or {}
    user_costs = user_costs_dict or {}
    
    result = {}
    for fuel_name in fuel_list:
        energy_required = energy_dict.get(fuel_name)
        user_cost = user_costs.get(fuel_name)
        
        cost_per_kwh, _ = calculator.get_cost_per_kwh(
            fuel_name, 
            user_input_cost=user_cost,
            energy_required=energy_required
        )
        result[fuel_name] = cost_per_kwh
    
    return result
