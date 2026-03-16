"""
Keralam Cooking Energy Analysis Tool - Database Helper Module
Provides easy access to all database tables with caching and utility functions
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any
from functools import lru_cache

# Database path
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'cooking_webapp.db'
USER_DB_PATH = BASE_DIR / 'user_data.db'
SYSTEM_PARAMETER_ALIASES = {
    'BIOMASS_ENERGY_CONTENT': 'BIOMASS_ENERGY_CONTENT_KWH_PER_KG',
    'Keralam_SOLAR_GHI': 'KERALAM_SOLAR_GHI',
    'SOLAR_SYSTEM_EFF': 'SOLAR_SYSTEM_EFFICIENCY'
}


@lru_cache(maxsize=8)
def _cached_recommendation_weights(priority_profile: str = 'balanced') -> Dict[str, float]:
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM recommendation_weights WHERE priority_profile = ?",
            (priority_profile,)
        )
        row = cursor.fetchone()

    if row:
        return {
            'health': row['health_weight'],
            'environmental': row['environmental_weight'],
            'economic': row['economic_weight'],
            'practicality': row['practicality_weight']
        }

    return {'health': 0.3, 'environmental': 0.2, 'economic': 0.3, 'practicality': 0.2}


@lru_cache(maxsize=16)
def _cached_household_size_efficiency(household_size: int) -> float:
    with DatabaseConnection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT efficiency_factor
            FROM group_cooking_efficiency
            WHERE group_type = ?
            AND ? BETWEEN size_min AND size_max
            """,
            ('Residential', household_size)
        )
        row = cursor.fetchone()

    return float(row['efficiency_factor']) if row else 1.00


class DatabaseHelper:
    """Main database helper class with connection management and caching."""

    def __init__(self, db_path=None):
        """Initialize database helper."""
        self.db_path = db_path or DB_PATH
        self.user_db_path = USER_DB_PATH
        self._conn = None
        self._cache = {}

    def get_connection(self):
        """Get database connection (thread-safe - creates new connection each time)."""
        # Always create a new connection to avoid threading issues
        # SQLite connections cannot be shared across threads
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def get_user_connection(self):
        """Get user database connection for transient server-side cache/state."""
        conn = sqlite3.connect(str(self.user_db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_analysis_cache_table(self, conn):
        """Ensure the server-side analysis cache table exists."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_cache (
                cache_key   TEXT PRIMARY KEY,
                payload     TEXT NOT NULL,
                created_at  REAL NOT NULL DEFAULT (strftime('%s', 'now')),
                expires_at  REAL NOT NULL
            )
        """)

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def clear_cache(self):
        """Clear cached data."""
        self._cache = {}

    def _fetch_all(self, query, params=None):
        """Execute query and return all results (thread-safe)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            results = cursor.fetchall()
            return results
        finally:
            conn.close()

    def _fetch_one(self, query, params=None):
        """Execute query and return one result (thread-safe)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            result = cursor.fetchone()
            return result
        finally:
            conn.close()

    # Public alias for fetch_one (for backward compatibility)
    def fetch_one(self, query, params=None):
        """Public method to fetch one result."""
        return self._fetch_one(query, params)

    # Public alias for execute_query (for backward compatibility)
    def execute_query(self, query, params=None):
        """Public method to execute a query."""
        return self._execute(query, params)

    def _execute(self, query, params=None):
        """Execute query and commit (thread-safe)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            last_id = cursor.lastrowid
            return last_id
        finally:
            conn.close()

    # ========================================================================
    # FUEL TYPES
    # ========================================================================

    def get_all_fuels(self, active_only=True) -> List[Dict]:
        """Get all fuel types."""
        cache_key = f'fuels_active_{active_only}'
        if cache_key in self._cache:
            return self._cache[cache_key]

        query = "SELECT * FROM fuel_types"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY display_order"

        rows = self._fetch_all(query)
        result = [dict(row) for row in rows]
        self._cache[cache_key] = result
        return result

    def get_fuel_by_name(self, fuel_name: str) -> Optional[Dict]:
        """Get fuel by name."""
        row = self._fetch_one(
            "SELECT * FROM fuel_types WHERE fuel_name = ?",
            (fuel_name,)
        )
        return dict(row) if row else None

    def get_fuel_id(self, fuel_name: str) -> Optional[int]:
        """Get fuel ID by name."""
        fuel = self.get_fuel_by_name(fuel_name)
        return fuel['fuel_id'] if fuel else None

    # ========================================================================
    # EMISSION FACTORS
    # ========================================================================

    def get_emission_factors(self, fuel_name: str = None) -> Dict:
        """Get current emission factors for all fuels or specific fuel."""
        if fuel_name:
            row = self._fetch_one("""
                SELECT ft.fuel_name, ef.co2_factor, ef.pm25_factor, ef.source
                FROM emission_factors ef
                JOIN fuel_types ft ON ef.fuel_id = ft.fuel_id
                WHERE ft.fuel_name = ?
                AND (ef.valid_to IS NULL OR ef.valid_to >= date('now'))
            """, (fuel_name,))
            if row:
                return {
                    'co2': row['co2_factor'],
                    'pm25': row['pm25_factor'],
                    'source': row['source']
                }
            return None

        # Get all emission factors
        rows = self._fetch_all("""
            SELECT ft.fuel_name, ef.co2_factor, ef.pm25_factor, ef.source
            FROM emission_factors ef
            JOIN fuel_types ft ON ef.fuel_id = ft.fuel_id
            WHERE ef.valid_to IS NULL OR ef.valid_to >= date('now')
        """)

        return {
            row['fuel_name']: {
                'co2': row['co2_factor'],
                'pm25': row['pm25_factor'],
                'source': row['source']
            }
            for row in rows
        }

    # ========================================================================
    # THERMAL EFFICIENCIES
    # ========================================================================

    def get_thermal_efficiency(self, fuel_name: str, stove_type: str = 'Standard',
                                area_type: str = 'Both') -> float:
        """Get thermal efficiency for fuel and stove type."""
        # Default stove_type to 'Standard' if None passed
        stove_type = stove_type or 'Standard'
        
        query = """
            SELECT te.efficiency
            FROM thermal_efficiencies te
            JOIN fuel_types ft ON te.fuel_id = ft.fuel_id
            WHERE ft.fuel_name = ?
            AND te.stove_type = ?
            AND (te.area_type = ? OR te.area_type = 'Both')
            AND (te.valid_to IS NULL OR te.valid_to >= date('now'))
            ORDER BY te.area_type = 'Both'
            LIMIT 1
        """

        row = self._fetch_one(query, (fuel_name, stove_type, area_type))
        return float(row['efficiency']) if row else 0.60  # Default 60%

    @staticmethod
    def _efficiency_area_priority(area_type: Optional[str]) -> int:
        normalized = str(area_type or '').strip().lower()
        if normalized == 'both':
            return 0
        if normalized in {'urban', 'rural'}:
            return 1
        return 2

    @staticmethod
    def _efficiency_stove_priority(stove_type: Optional[str]) -> int:
        normalized = str(stove_type or '').strip().lower()
        priorities = {
            'standard': 0,
            'traditional': 1,
            'induction': 2,
            'hotplate': 3,
        }
        return priorities.get(normalized, 10)

    def _select_preferred_efficiency_rows(self, rows, key_fields: Tuple[str, ...]) -> List[Dict[str, Any]]:
        """Pick a canonical DB-backed efficiency row for each key."""
        selected: Dict[Tuple[Any, ...], Tuple[Tuple[int, int], Dict[str, Any]]] = {}

        for row in rows:
            payload = dict(row)
            key = tuple(payload[field] for field in key_fields)
            priority = (
                self._efficiency_area_priority(payload.get('area_type')),
                self._efficiency_stove_priority(payload.get('stove_type')),
            )

            current = selected.get(key)
            if current is None or priority < current[0]:
                selected[key] = (priority, payload)

        return [payload for _, payload in selected.values()]

    def get_all_efficiencies(self) -> Dict[str, float]:
        """Get default efficiencies for all fuels."""
        rows = self._fetch_all("""
            SELECT ft.fuel_name, te.area_type, te.stove_type, te.efficiency
            FROM thermal_efficiencies te
            JOIN fuel_types ft ON te.fuel_id = ft.fuel_id
            WHERE te.valid_to IS NULL OR te.valid_to >= date('now')
        """)

        preferred_rows = self._select_preferred_efficiency_rows(rows, ('fuel_name',))
        return {row['fuel_name']: float(row['efficiency']) for row in preferred_rows}

    def get_all_stove_efficiencies(self) -> List[Dict]:
        """Get all stove efficiencies with area and fuel info."""
        rows = self._fetch_all("""
            SELECT
                te.area_type,
                te.stove_type,
                ft.fuel_name,
                te.efficiency
            FROM thermal_efficiencies te
            JOIN fuel_types ft ON te.fuel_id = ft.fuel_id
            WHERE te.valid_to IS NULL OR te.valid_to >= date('now')
        """)
        preferred_rows = self._select_preferred_efficiency_rows(rows, ('area_type', 'fuel_name'))
        return [
            {
                'Area': row['area_type'],
                'Stove type': row['stove_type'],
                'Fuel': row['fuel_name'],
                'Thermal Efficiency': float(row['efficiency']),
            }
            for row in preferred_rows
        ]

    # ========================================================================
    # DISTRICTS
    # ========================================================================

    def get_districts(self) -> List[str]:
        """Get list of all districts sorted alphabetically."""
        rows = self._fetch_all("SELECT district_name FROM districts ORDER BY district_name")
        return [row['district_name'] for row in rows]

    def get_district_options(self) -> List[Dict]:
        """Get district options with English and Malayalam labels."""
        rows = self._fetch_all("""
            SELECT district_name, district_name_ml
            FROM districts
            ORDER BY district_name
        """)
        return [
            {
                'value': row['district_name'],
                'label_en': row['district_name'],
                'label_ml': row['district_name_ml']
            }
            for row in rows
        ]
    
    # ========================================================================
    # KITCHEN SCENARIOS (Unified Kitchen & Ventilation)
    # ========================================================================

    def get_kitchen_scenarios(self, scenario_type='residential', active_only=True) -> List[Dict]:
        """
        Get all kitchen scenarios for a specific type.
        
        Args:
            scenario_type: 'residential' or 'commercial'
            active_only: Only return active scenarios
        
        Returns:
            List of scenario dictionaries with all fields
        """
        query = "SELECT * FROM kitchen_scenarios WHERE scenario_type = ?"
        params = [scenario_type]
        
        if active_only:
            query += " AND is_active = 1"
        
        query += " ORDER BY display_order"
        
        rows = self._fetch_all(query, tuple(params))
        return [dict(row) for row in rows]

    def get_scenario_factor(self, scenario_id: int) -> float:
        """
        Get combined exposure factor for a kitchen scenario ID.
        """
        row = self._fetch_one("SELECT combined_factor FROM kitchen_scenarios WHERE scenario_id = ?", (scenario_id,))
        return float(row['combined_factor']) if row else 0.60  # Default to moderate

    def get_scenario_by_name(self, scenario_name: str, scenario_type='residential') -> Optional[Dict]:
        """
        Get single kitchen scenario by name and type.
        
        Args:
            scenario_name: Name of the scenario
            scenario_type: 'residential' or 'commercial'
        
        Returns:
            Scenario dictionary or None
        """
        row = self._fetch_one("""
            SELECT * FROM kitchen_scenarios 
            WHERE scenario_name = ? AND scenario_type = ?
        """, (scenario_name, scenario_type))
        
        return dict(row) if row else None

    def get_scenario_factor(self, scenario_name: str, scenario_type='residential') -> float:
        """
        Get combined exposure factor for a kitchen scenario.
        
        Args:
            scenario_name: Name of the scenario
            scenario_type: 'residential' or 'commercial'
        
        Returns:
            Combined exposure factor (default 0.60 if not found)
        """
        row = self._fetch_one("""
            SELECT combined_factor FROM kitchen_scenarios 
            WHERE scenario_name = ? AND scenario_type = ?
        """, (scenario_name, scenario_type))
        
        return float(row['combined_factor']) if row else 0.60  # Default to moderate

    # NOTE: Deprecated methods get_kitchen_factor, get_ventilation_factor, 
    # get_all_kitchen_factors, get_all_ventilation_factors have been removed.
    # Use get_kitchen_scenarios() and get_scenario_factor() instead.

    # ========================================================================
    # GROUP EFFICIENCIES (Consolidated Household & Commercial)
    # ========================================================================

    def get_group_efficiency(self, size: int, group_type: str = 'Residential') -> float:
        """
        Get efficiency factor based on group size and type (Residential/Commercial).
        """
        row = self._fetch_one("""
            SELECT efficiency_factor
            FROM group_cooking_efficiency
            WHERE group_type = ?
            AND ? BETWEEN size_min AND size_max
        """, (group_type, size))
        
        return float(row['efficiency_factor']) if row else 1.00

    def get_household_size_efficiency(self, household_size: int) -> float:
        """Get efficiency factor based on household size (Legacy Wrapper)."""
        return _cached_household_size_efficiency(household_size)

    def get_commercial_efficiency(self, servings: int) -> float:
        """Get efficiency factor based on number of servings."""
        return self.get_group_efficiency(servings, 'Commercial')

    # ========================================================================
    # MEAL DISTRIBUTION
    # ========================================================================

    def get_meal_distribution(self, meal_intensity: str = 'Normal') -> Dict[str, float]:
        """Get meal distribution percentages by intensity."""
        # Clean up intensity input (e.g. 'Normal' -> 'Normal')
        intensity = meal_intensity.title() if meal_intensity else 'Normal'
        
        rows = self._fetch_all(
            "SELECT meal_type, energy_percent as percentage FROM meal_energy_distribution WHERE intensity = ?",
            (intensity,)
        )
        return {row['meal_type']: row['percentage'] / 100.0 for row in rows}

    # ========================================================================
    # HEALTH RISK THRESHOLDS
    # ========================================================================

    def get_health_risk_score(self, pm25_level: float) -> Tuple[int, str]:
        """Get health risk score and category based on PM2.5 level."""
        row = self._fetch_one("""
            SELECT risk_score, risk_category
            FROM health_risk_thresholds
            WHERE ? >= pm25_min AND ? < pm25_max
        """, (pm25_level, pm25_level))

        if row:
            return row['risk_score'], row['risk_category']
        return 85, 'Critical'  # Default to highest risk

    # ========================================================================
    # ENVIRONMENTAL GRADES
    # ========================================================================

    def get_environmental_grade(self, value: float, metric: str = 'annual_per_member_kg') -> Tuple[str, str]:
        """
        Get environmental grade based on numeric value and metric type.
        
        Args:
            value: The numeric value to grade (e.g. 55.0)
            metric: database column to compare against (default 'annual_per_member_kg')
            
        Returns:
            Tuple (Grade Letter, Label)
        """
        # Fetch all grades sorted by efficiency (A+ first)
        rows = self._fetch_all("SELECT * FROM environmental_grades ORDER BY grade_id ASC")
        lowest_bounded_row = None
        lowest_bound = None
        
        for row in rows:
            range_str = row[metric]
            
            # Parse range string (e.g., "55-91", ">1915", "0.05-0.10")
            try:
                if '>' in range_str:
                    limit = float(range_str.replace('>', '').strip().replace(',', ''))
                    if value > limit:
                        return row['grade_letter'], row['label']
                elif '-' in range_str:
                    low, high = map(lambda x: float(x.strip().replace(',', '')), range_str.split('-'))
                    if lowest_bound is None or low < lowest_bound:
                        lowest_bound = low
                        lowest_bounded_row = row
                    if low <= value <= high:
                        return row['grade_letter'], row['label']
            except ValueError:
                continue
        
        # Values below the first bounded range should map to the cleanest grade, not the fallback worst grade.
        if lowest_bounded_row and lowest_bound is not None and value < lowest_bound:
            return lowest_bounded_row['grade_letter'], lowest_bounded_row['label']
                
        # Default fallback
        return 'F', 'Critical'

    # ========================================================================
    # RECOMMENDATION WEIGHTS
    # ========================================================================

    def get_recommendation_weights(self, priority_profile: str = 'balanced') -> Dict[str, float]:
        """Get recommendation weights for priority profile."""
        return _cached_recommendation_weights(priority_profile)

    # ========================================================================
    # CONSOLIDATED PRICING (New Generic Architecture)
    # ========================================================================

    def get_fuel_unit_price(self, district_name: str, fuel_name: str, category: str = 'Domestic') -> Optional[Dict]:
        """
        Get unit price for a fuel from consolidated table.
        
        Args:
            district_name: Name of district
            fuel_name: Name of fuel
            category: 'Domestic' or 'Commercial'
            
        Returns:
            Dict: {unit_price, unit_name}
        """
        query = """
            SELECT fp.unit_price, fp.subsidized_unit_price, fp.unit_name
            FROM fuel_unit_pricing fp
            JOIN districts d ON fp.district_id = d.district_id
            JOIN fuel_types ft ON fp.fuel_id = ft.fuel_id
            WHERE d.district_name = ?
            AND ft.fuel_name = ?
            AND fp.pricing_category = ?
            AND (fp.valid_to IS NULL OR fp.valid_to >= date('now'))
            LIMIT 1
        """
        row = self._fetch_one(query, (district_name, fuel_name, category))
        return dict(row) if row else None

    # ========================================================================
    # LOAN & CAPITAL COSTS
    # ========================================================================
    
    def get_technology_pricing(self, technology_type: str) -> dict:
        """
        Get pricing parameters for a specific technology (e.g., 'Biogas', 'Solar', 'BESS').
        Returns dict with capital_cost_per_unit, installation_cost_base, maintenance_annual_pct, etc.
        """
        row = self._fetch_one("""
            SELECT *
            FROM loan_and_capital_costs
            WHERE technology_type LIKE ?
        """, (f'%{technology_type}%',))
        
        if row:
            return dict(row)
        return {}

    def get_biogas_pricing(self, category: str = 'Domestic') -> dict:
        """
        Get Biogas pricing. category='Domestic' or 'Commercial' for different rates.
        """
        tech_data = self.get_capital_cost_structure('Biogas', category)
        # Ensure we return at least empty dict if not found, consistent with old behavior
        return tech_data if tech_data else {}

    def get_capital_cost_structure(self, technology_type: str, category: str = 'Domestic') -> Optional[Dict]:
        """
        Get capital cost structure for Solar, Biogas, BESS.
        
        Args:
            technology_type: 'Solar', 'BESS', or 'Biogas'
            category: 'Domestic' or 'Commercial' - affects pricing
        """
        query = """
            SELECT * FROM loan_and_capital_costs
            WHERE technology_type = ?
            AND type = ?
            AND (valid_to IS NULL OR valid_to >= date('now'))
            LIMIT 1
        """
        row = self._fetch_one(query, (technology_type, category))
        if row:
            return dict(row)
        
        # Fallback: try without category filter (backward compatibility)
        query_fallback = """
            SELECT * FROM loan_and_capital_costs
            WHERE technology_type = ?
            AND (valid_to IS NULL OR valid_to >= date('now'))
            LIMIT 1
        """
        row = self._fetch_one(query_fallback, (technology_type,))
        return dict(row) if row else None

    # ========================================================================
    # LEGACY / SPECIFIC GETTERS (Redirected or Deprecated)
    # ========================================================================
    
    def get_lpg_pricing(self, district: str, category: str = 'Domestic') -> Optional[Dict]:
        """Deprecated: Use get_fuel_unit_price. Mapping for compatibility."""
        data = self.get_fuel_unit_price(district, 'LPG', category)
        if data:
            return {
                'market_price': data['unit_price'] if category == 'Commercial' else 0,
                'subsidized_price': data['unit_price'] if category == 'Domestic' else 0,
                'cylinder_type': category,
                'cylinder_weight': 14.2 if category == 'Domestic' else 19.0
            }
        return None

    def get_png_pricing(self, district: str = 'All', category: str = 'Domestic') -> Optional[Dict]:
         """Deprecated: Use get_fuel_unit_price."""
         # PNG is state-wide usually, but we store per district now. Just pick one if 'All' passed
         target_district = district if district != 'All' else 'Thiruvananthapuram'
         data = self.get_fuel_unit_price(target_district, 'PNG', category)
         if data:
             return {'price_per_scm': data['unit_price']}
         return None
         
    def get_biomass_pricing(self, category: str='Domestic') -> Optional[Dict]:
        """Deprecated."""
        data = self.get_fuel_unit_price('Thiruvananthapuram', 'Traditional Solid Biomass', category)
        if data:
            return {'cost_per_kg': data['unit_price']}
        return None

    # Solar/Battery pricing getters now use get_capital_cost_structure
    def get_solar_pricing(self, district_name=None, area_type=None, category='Domestic'):
        """Get solar pricing. category='Domestic' or 'Commercial' for different rates."""
        data = self.get_capital_cost_structure('Solar', category)
        if data:
            return {
                'capital_cost_per_kw': data['capital_cost_per_unit'],
                'installation_cost_rs': data.get('installation_cost_base', 0),
                'system_lifetime_years': data.get('lifetime_years', 25),
                'maintenance_per_kw_annual': float(data['capital_cost_per_unit']) * float(data.get('maintenance_annual_pct', 0.01))
            }
        # Fallback defaults based on category
        return {'capital_cost_per_kw': 55000 if category == 'Commercial' else 65000}

    def get_battery_pricing(self, capacity_kwh=2.0, battery_type=None, category='Domestic'):
        """Get BESS pricing. category='Domestic' or 'Commercial' for different rates."""
        data = self.get_capital_cost_structure('BESS', category)
        if data:
            return {
                'cost_per_unit': data['capital_cost_per_unit'], # Usually per kWh
                'capacity_kwh': 1.0, # Unit is per kWh in new table
                'round_trip_efficiency': 0.90,
                'depth_of_discharge': 0.80,
                'lifetime_years': data.get('lifetime_years', 10)
            }
        # Fallback defaults based on category
        return {'cost_per_unit': 14000 if category == 'Commercial' else 16000}


    # ========================================================================
    # SYSTEM PARAMETERS
    # ========================================================================

    def get_system_parameter(self, param_name: str, default=None) -> Any:
        """Get system parameter value."""
        candidate_names = [param_name]
        aliased_name = SYSTEM_PARAMETER_ALIASES.get(param_name)
        if aliased_name and aliased_name not in candidate_names:
            candidate_names.append(aliased_name)

        row = None
        for candidate_name in candidate_names:
            row = self._fetch_one("""
                SELECT param_value, param_type
                FROM system_parameters
                WHERE param_name = ?
                AND (valid_to IS NULL OR valid_to >= date('now'))
            """, (candidate_name,))
            if row:
                break

        if not row:
            return default

        value = row['param_value']
        param_type = row['param_type']

        # Convert based on type
        if param_type in ('NUMERIC', 'DECIMAL', 'INTEGER'):
            try:
                # Try integer first if param_type is INTEGER
                if param_type == 'INTEGER':
                    return int(value)
                return float(value)
            except (ValueError, TypeError):
                return default if default is not None else value
        elif param_type == 'BOOLEAN':
            return value.lower() in ('true', '1', 'yes')
        elif param_type == 'JSON':
            return json.loads(value)
        else:
            return value

    def get_all_system_parameters(self) -> Dict[str, Any]:
        """Fetch all system parameters in one query. Returns {param_name: value} dict."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT param_name, param_value
                FROM system_parameters
                WHERE valid_to IS NULL OR valid_to >= date('now')
                """
            )
            result = {row[0]: row[1] for row in cursor.fetchall()}

            # Preserve existing compatibility behavior for callers that use legacy aliases.
            for alias_name, actual_name in SYSTEM_PARAMETER_ALIASES.items():
                if alias_name not in result and actual_name in result:
                    result[alias_name] = result[actual_name]

            return result
        finally:
            conn.close()

    def save_analysis_cache(self, cache_key: str, payload: dict, ttl_seconds: int = 7200):
        import time

        conn = self.get_user_connection()
        try:
            self._ensure_analysis_cache_table(conn)
            now = time.time()
            conn.execute(
                "INSERT OR REPLACE INTO analysis_cache (cache_key, payload, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (cache_key, json.dumps(payload, default=str), now, now + ttl_seconds)
            )
            conn.commit()
        finally:
            conn.close()

    def load_analysis_cache(self, cache_key: str) -> dict | None:
        import time

        conn = self.get_user_connection()
        try:
            self._ensure_analysis_cache_table(conn)
            row = conn.execute(
                "SELECT payload, expires_at FROM analysis_cache WHERE cache_key = ?",
                (cache_key,)
            ).fetchone()
            if row and row[1] > time.time():
                return json.loads(row[0])
            return None
        finally:
            conn.close()

    # ========================================================================
    # DISHES
    # ========================================================================

    def get_all_dishes(self, dish_type: str = 'residential', active_only: bool = True) -> List[Dict]:
        """
        Get all dishes with categories.
        
        Args:
            dish_type: 'residential' or 'commercial'
            active_only: Only return active dishes
            
        Returns:
            List of dish dictionaries with category info
        """
        table = 'dishes_residential' if dish_type == 'residential' else 'dishes_commercial'
        
        query = f"""
            SELECT d.*, c.category_name, c.category_name_ml, c.display_order as cat_order
            FROM {table} d
            JOIN dish_categories c ON d.category_id = c.category_id
        """
        
        if active_only:
            query += " WHERE d.is_active = 1"
            
        query += " ORDER BY c.display_order, d.display_order"
        
        rows = self._fetch_all(query)
        return [dict(row) for row in rows]

    def get_dishes_by_category(self, category_name: str, dish_type: str = 'residential') -> List[Dict]:
        """Get dishes for a specific category."""
        table = 'dishes_residential' if dish_type == 'residential' else 'dishes_commercial'
        
        query = f"""
            SELECT d.*
            FROM {table} d
            JOIN dish_categories c ON d.category_id = c.category_id
            WHERE c.category_name = ? AND d.is_active = 1
            ORDER BY d.display_order
        """
        rows = self._fetch_all(query, (category_name,))
        return [dict(row) for row in rows]
        
    # ========================================================================
    # INSTITUTIONS
    # ========================================================================

    def get_all_institution_types(self) -> List[Dict]:
        """Get all institution types."""
        rows = self._fetch_all("SELECT * FROM institution_types ORDER BY institution_name")
        return [dict(row) for row in rows]

    def get_district_id(self, district_name: str) -> Optional[int]:
        """Get district ID by name."""
        row = self._fetch_one("SELECT district_id FROM districts WHERE district_name = ?", (district_name,))
        return row['district_id'] if row else None

    # ========================================================================
    # UTILITY FUNCTIONS
    # ========================================================================

    def row_to_dict(self, row) -> Dict:
        """Convert SQLite Row to dictionary."""
        return dict(row) if row else None

    def rows_to_list(self, rows) -> List[Dict]:
        """Convert list of SQLite Rows to list of dictionaries."""
        return [dict(row) for row in rows]


# Global instance for easy import
db = DatabaseHelper()


# Convenience functions
def get_emission_factors() -> Dict:
    """Get all current emission factors."""
    return db.get_emission_factors()


def get_all_efficiencies() -> Dict:
    """Get default efficiencies for all fuels."""
    return db.get_all_efficiencies()


def get_household_size_factor(household_size: int) -> float:
    """Get efficiency factor for household size."""
    return db.get_household_size_efficiency(household_size)


# NOTE: Deprecated convenience functions get_kitchen_factors and get_ventilation_factors
# have been removed. Use db.get_kitchen_scenarios() instead.


def get_health_risk_score(pm25_level: float) -> Tuple[int, str]:
    """Get health risk score and category."""
    return db.get_health_risk_score(pm25_level)


def get_environmental_grade(annual_co2_kg: float) -> Tuple[str, str]:
    """Get environmental grade."""
    return db.get_environmental_grade(annual_co2_kg)


# Context manager for database operations
class DatabaseConnection:
    """Context manager for database connections."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=3000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
            self.conn.close()
        return False
