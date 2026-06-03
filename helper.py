import sqlite3
import flask
import pandas as pd
import numpy as np
import json
import datetime
import math
import uuid
import os
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from config import get_config
from database.db_helper import DatabaseHelper
from debug_logger import get_logger, log_request_start, log_session_data

# Initialize database helper
db_helper = DatabaseHelper()

# Defaults (overwritten by load_constants_from_db())
EMISSION_SOURCES = {}
BIOGAS_ENERGY_PER_M3 = 5.5

# =================================================================
# LOAD CONSTANTS FROM DATABASE
# =================================================================

def load_constants_from_db():
    """Load all constants from database - called at startup and can be refreshed"""
    global LPG_CALORIFIC_VALUE, LPG_CYLINDER_WEIGHT, LPG_ENERGY_PER_CYLINDER, LPG_SUBSIDY_AMOUNT
    global PNG_CALORIFIC_VALUE
    global Keralam_SOLAR_GHI, SOLAR_SYSTEM_EFF, Keralam_WEATHER_FACTOR, SOLAR_DEGRADATION
    global SOLAR_CAPITAL_COST_PER_KW, SOLAR_INSTALLATION_COST, SOLAR_LIFETIME_YEARS
    global SOLAR_MAINTENANCE_PER_KW_ANNUAL
    global BATTERY_COST_PER_KWH, BATTERY_CAPACITY_PER_UNIT, BATTERY_EFFICIENCY
    global BATTERY_DOD, BATTERY_COMBINED_FACTOR, BATTERY_LIFETIME_YEARS
    global INDIA_SCC, DEFAULT_DISCOUNT_RATE, ELECTRICITY_TARIFF_INFLATION
    global EMISSION_FACTORS, EMISSION_SOURCES, PM25_BASE_EMISSIONS, DEFAULT_EFFICIENCIES
    global KITCHEN_FACTORS, BIOGAS_ENERGY_PER_M3

    all_params = db_helper.get_all_system_parameters()

    # System parameters
    LPG_CALORIFIC_VALUE = float(all_params.get('LPG_CALORIFIC_VALUE_KWH_PER_KG', 12.8))
    LPG_CYLINDER_WEIGHT = float(all_params.get('LPG_DOMESTIC_CYLINDER_WEIGHT_KG', 14.2))
    LPG_ENERGY_PER_CYLINDER = LPG_CYLINDER_WEIGHT * LPG_CALORIFIC_VALUE

    # Subsidy Parameters
    # Note: Subsidy is now calculated dynamically based on income
    SUBSIDY_INCOME_THRESHOLD = float(all_params.get('SUBSIDY_INCOME_THRESHOLD', 50000))
    
    # DEPRECATED: Global constant for backward compatibility
    # Actual calculation happens in residential_cooking.py / fuel_cost_standardizer.py
    LPG_SUBSIDY_AMOUNT = 0 

    PNG_CALORIFIC_VALUE = float(all_params.get('PNG_CALORIFIC_VALUE_KWH_PER_SCM', 10.2))

    # Solar parameters
    Keralam_SOLAR_GHI = float(all_params.get('Keralam_SOLAR_GHI', 5.59))
    SOLAR_SYSTEM_EFF = float(all_params.get('SOLAR_SYSTEM_EFF', 0.85))
    Keralam_WEATHER_FACTOR = float(all_params.get('Keralam_WEATHER_FACTOR', 0.88))
    SOLAR_DEGRADATION = float(all_params.get('SOLAR_DEGRADATION', 0.005))

    # Get solar pricing from database
    solar_pricing = db_helper.get_solar_pricing()
    SOLAR_CAPITAL_COST_PER_KW = solar_pricing['capital_cost_per_kw']
    SOLAR_INSTALLATION_COST = solar_pricing['installation_cost_rs']
    SOLAR_LIFETIME_YEARS = solar_pricing['system_lifetime_years']
    SOLAR_MAINTENANCE_PER_KW_ANNUAL = solar_pricing['maintenance_per_kw_annual']

    # Battery parameters
    battery_pricing = db_helper.get_battery_pricing(capacity_kwh=2.0)
    BATTERY_COST_PER_KWH = battery_pricing['cost_per_unit']
    BATTERY_CAPACITY_PER_UNIT = battery_pricing['capacity_kwh']
    BATTERY_EFFICIENCY = battery_pricing['round_trip_efficiency']
    BATTERY_DOD = battery_pricing['depth_of_discharge']
    BATTERY_COMBINED_FACTOR = BATTERY_EFFICIENCY * BATTERY_DOD
    BATTERY_LIFETIME_YEARS = battery_pricing['lifetime_years']

    # Biogas parameters
    BIOGAS_ENERGY_PER_M3 = float(all_params.get('BIOGAS_ENERGY_PER_M3_KWH', 5.5))

    # Economic parameters
    INDIA_SCC = float(all_params.get('INDIA_SCC', 7470))
    DEFAULT_DISCOUNT_RATE = float(all_params.get('DEFAULT_DISCOUNT_RATE', 0.08))
    ELECTRICITY_TARIFF_INFLATION = float(all_params.get('ELECTRICITY_TARIFF_INFLATION', 0.05))

    # Emission factors from database (all fuels including improved stoves)
    emission_data = db_helper.get_emission_factors()
    EMISSION_FACTORS = {fuel: data['co2'] for fuel, data in emission_data.items()}
    EMISSION_SOURCES = {fuel: data.get('source') for fuel, data in emission_data.items()}
    PM25_BASE_EMISSIONS = {fuel: data['pm25'] for fuel, data in emission_data.items()}

    # Thermal efficiencies from database
    DEFAULT_EFFICIENCIES = db_helper.get_all_efficiencies()

    # NOTE: KITCHEN_FACTORS and VENTILATION_FACTORS have been removed.
    # Use kitchen scenarios from database instead via load_kitchen_scenarios()
    KITCHEN_FACTORS = {}  # Kept for backward compatibility, will be removed in future

# Load constants at startup
load_constants_from_db()

# =================================================================
# KITCHEN SCENARIOS - LOAD FROM DATABASE
# =================================================================

def load_kitchen_scenarios(scenario_type='residential'):
    """
    Load kitchen scenarios from reference database
    
    Args:
        scenario_type: 'residential' or 'commercial'
    
    Returns:
        dict: {scenario_name: {'factor': 0.04, 'risk': 'VERY LOW', ...}}
    """
    scenarios = db_helper.get_kitchen_scenarios(scenario_type=scenario_type, active_only=True)
    
    result = {}
    for scenario in scenarios:
        result[scenario['scenario_name']] = {
            'factor': float(scenario['combined_factor']),
            'risk': scenario['health_risk_category'],
            'id': scenario['scenario_id'],
            'name_ml': scenario['scenario_name_ml'],
            'description_en': scenario['description_en'],
            'description_ml': scenario['description_ml']
        }
    return result

# Load kitchen scenarios at module startup
RESIDENTIAL_KITCHEN_SCENARIOS = load_kitchen_scenarios('residential')
COMMERCIAL_KITCHEN_SCENARIOS = load_kitchen_scenarios('commercial')

# Risk color/icon mapping for UI display
RISK_STYLES = {
    'VERY LOW': {'badge': 'success', 'icon': '✅', 'severity': 0},
    'LOW': {'badge': 'info', 'icon': '👍', 'severity': 1},
    'MODERATE': {'badge': 'warning', 'icon': '⚠️', 'severity': 2},
    'HIGH': {'badge': 'danger', 'icon': '🚨', 'severity': 3}
}

def get_kitchen_scenario_factor(kitchen_scenario, scenario_type='residential'):
    """
    Get combined exposure factor for a kitchen scenario
    
    Args:
        kitchen_scenario: Scenario name from database
        scenario_type: 'residential' or 'commercial'
    
    Returns:
        dict with factor and risk data,or float if only factor needed
    """
    scenarios = RESIDENTIAL_KITCHEN_SCENARIOS if scenario_type == 'residential' else COMMERCIAL_KITCHEN_SCENARIOS
    return scenarios.get(kitchen_scenario, {'factor': 0.60, 'risk': 'MODERATE'})

def calculate_health_impact_from_scenario(kitchen_scenario, cooking_hours, people_exposed=1, 
                                         base_emission=0.015, scenario_type='residential'):
    """
    Calculate health risk based on kitchen scenario (NEW METHOD)
    
    Args:
        kitchen_scenario: Scenario name from kitchen_scenarios table
        cooking_hours: Daily cooking hours
        people_exposed: Number of people exposed (sensitive_members or staff_exposed)
        base_emission: Base PM2.5 or CO2 emissions per kWh
        scenario_type: 'residential' or 'commercial'
    
    Returns:
        dict with health metrics
    """
    scenario_data = get_kitchen_scenario_factor(kitchen_scenario, scenario_type)
    
    if isinstance(scenario_data, dict):
        combined_factor = scenario_data.get('factor', 0.60)
        risk_category = scenario_data.get('risk', 'MODERATE')
    else:
        combined_factor = scenario_data
        risk_category = 'MODERATE'
    
    # Calculate peak PM2.5 exposure (kg/day)
    peak_exposure = base_emission * combined_factor * cooking_hours
    
    # Risk score: 0-100 scale
    base_score = peak_exposure * 500
    people_penalty = people_exposed * 5
    health_risk_score = min(100, base_score + people_penalty)
    
    risk_style = RISK_STYLES.get(risk_category, RISK_STYLES['MODERATE'])
    
    return {
        'pm25_peak': round(peak_exposure, 4),
        'health_risk_score': round(health_risk_score, 1),
        'health_risk_category': risk_category,
        'combined_factor': combined_factor,
        'risk_color': risk_style['badge'],
        'risk_icon': risk_style['icon']
    }


# DUAL DATABASE ARCHITECTURE
# =================================================================

# Database file paths
REFERENCE_DB = 'cooking_webapp.db'  # Read-only reference/master data
USER_DB = 'user_data.db'  # Read-write user transactions

def get_reference_connection():
    """
    Get READ-ONLY connection to reference database.
    Contains master data: dishes, fuels, pricing, factors, etc.
    """
    # Open in read-only mode using URI
    conn = sqlite3.connect(f'file:{REFERENCE_DB}?mode=ro', uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_connection():
    """
    Get READ+WRITE connection to user database.
    Uses flask.g for connection pooling within request context.
    """
    # Check if we are in a Flask app context
    if flask.has_app_context():
        existing_conn = getattr(flask.g, '_database', None)
        if existing_conn is not None:
            try:
                existing_conn.execute("SELECT 1")
                return existing_conn
            except sqlite3.Error:
                # Connection may have been closed elsewhere; recreate it
                try:
                    existing_conn.close()
                except Exception:
                    pass
                flask.g._database = None

        conn = sqlite3.connect(USER_DB, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        conn.execute(f"ATTACH DATABASE '{REFERENCE_DB}' AS ref")
        flask.g._database = conn
        return conn
    else:
        # Fallback for scripts outside request context
        conn = sqlite3.connect(USER_DB, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        conn.execute(f"ATTACH DATABASE '{REFERENCE_DB}' AS ref")
        return conn

def get_db_connection():
    """
    DEPRECATED: Use get_user_connection() or get_reference_connection() instead.
    Kept for backward compatibility - defaults to user database.
    """
    return get_user_connection()

def close_user_connection(conn):
    """Safely close database connection unless managed by Flask request context."""
    if conn is None:
        return

    if flask.has_app_context() and getattr(flask.g, '_database', None) is conn:
        # Flask teardown will handle closing the shared connection
        return

    try:
        conn.close()
    except Exception:
        # Suppress close errors to avoid masking upstream logic
        pass

def ensure_table_columns(cursor, table_name, column_definitions):
    """Add missing columns for legacy user databases during startup initialization."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_sql in column_definitions.items():
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")

def init_user_database():
    """
    Initialize the normalized user transactional database.

    The app stores profile rows early, then stores one complete analysis
    transaction when the user reaches the results page.
    """
    conn = sqlite3.connect(USER_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS households (
            household_id TEXT PRIMARY KEY,
            survey_date DATE,
            name TEXT,
            email TEXT,
            phone TEXT,
            country_code TEXT DEFAULT '+91',
            district TEXT,
            area_type TEXT,
            household_size INTEGER,
            monthly_income INTEGER,
            ration_card TEXT,
            lpg_subsidy TEXT,
            electricity_tariff REAL,
            loan_interest_rate REAL,
            loan_tenure INTEGER,
            main_priority TEXT,
            calculation_method TEXT,
            kitchen_scenario TEXT,
            solar_willingness TEXT,
            solar_rooftop_area REAL,
            consent_given INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS commercial_institutions (
            institution_id TEXT PRIMARY KEY,
            survey_date DATE,
            institution_name TEXT,
            institution_type TEXT,
            contact_person TEXT,
            email TEXT,
            phone TEXT,
            country_code TEXT DEFAULT '+91',
            district TEXT,
            area_type TEXT,
            address TEXT,
            servings_per_day INTEGER,
            working_days INTEGER,
            electricity_tariff REAL,
            solar_willing TEXT,
            roof_area_available REAL,
            budget_preference TEXT,
            kitchen_scenario TEXT,
            cooking_hours_daily REAL,
            staff_exposed INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS analysis_sessions (
            analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('household', 'institution')),
            analysis_type TEXT NOT NULL,
            calculation_method TEXT,
            monthly_energy_kwh REAL,
            monthly_cost REAL,
            annual_emissions_kg REAL,
            health_risk_score REAL,
            environmental_grade TEXT,
            kitchen_scenario TEXT,
            cooking_hours_daily REAL,
            people_exposed INTEGER,
            roof_area_available REAL,
            primary_fuel TEXT,
            overall_thermal_efficiency REAL,
            cost_per_serving REAL,
            energy_per_serving_kwh REAL,
            payload_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fuel_selections (
            fuel_selection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('household', 'institution')),
            fuel_type TEXT NOT NULL,
            percentage_usage REAL,
            monthly_quantity REAL,
            quantity_unit TEXT,
            monthly_cost REAL,
            energy_delivered_kwh REAL,
            monthly_emissions_kg REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (analysis_id) REFERENCES analysis_sessions(analysis_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS dish_selections (
            selection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('household', 'institution')),
            meal_category TEXT,
            dish_name TEXT NOT NULL,
            dish_id INTEGER,
            fuel_type TEXT,
            frequency_per_week REAL,
            portions_per_meal INTEGER,
            energy_per_serving_kwh REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (analysis_id) REFERENCES analysis_sessions(analysis_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS alternative_options (
            option_id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            rank INTEGER,
            fuel_name TEXT NOT NULL,
            monthly_cost REAL,
            monthly_savings REAL,
            payback_period_months REAL,
            upfront_cost REAL,
            annual_emissions_kg REAL,
            health_risk_score REAL,
            environmental_grade TEXT,
            recommendation_score REAL,
            recommendation_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (analysis_id) REFERENCES analysis_sessions(analysis_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_feedback (
            feedback_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('household', 'institution')),
            analysis_id INTEGER,
            name TEXT,
            email TEXT,
            phone TEXT,
            interest_clean_cooking TEXT,
            support_solar INTEGER DEFAULT 0,
            support_electric_cooking INTEGER DEFAULT 0,
            support_png INTEGER DEFAULT 0,
            support_govt_schemes INTEGER DEFAULT 0,
            support_none INTEGER DEFAULT 0,
            allow_authority_contact INTEGER DEFAULT 0,
            feedback_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (analysis_id) REFERENCES analysis_sessions(analysis_id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS user_activity_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT,
            entity_type TEXT CHECK(entity_type IN ('household', 'institution', 'unknown')),
            activity_type TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS analysis_cache (
            cache_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
            expires_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_households_district ON households(district);
        CREATE INDEX IF NOT EXISTS idx_institutions_type ON commercial_institutions(institution_type);
        CREATE INDEX IF NOT EXISTS idx_analysis_entity ON analysis_sessions(entity_id, entity_type);
        CREATE INDEX IF NOT EXISTS idx_analysis_created ON analysis_sessions(created_at);
        CREATE INDEX IF NOT EXISTS idx_fuel_analysis ON fuel_selections(analysis_id);
        CREATE INDEX IF NOT EXISTS idx_fuel_entity ON fuel_selections(entity_id, entity_type);
        CREATE INDEX IF NOT EXISTS idx_dish_analysis ON dish_selections(analysis_id);
        CREATE INDEX IF NOT EXISTS idx_dish_entity ON dish_selections(entity_id, entity_type);
        CREATE INDEX IF NOT EXISTS idx_alt_analysis ON alternative_options(analysis_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_entity ON user_feedback(entity_id, entity_type);
        CREATE INDEX IF NOT EXISTS idx_feedback_analysis ON user_feedback(analysis_id);
        CREATE INDEX IF NOT EXISTS idx_activity_entity ON user_activity_log(entity_id, entity_type);

        CREATE TRIGGER IF NOT EXISTS trg_cleanup_cache
        AFTER INSERT ON analysis_cache
        BEGIN
            DELETE FROM analysis_cache WHERE expires_at < strftime('%s', 'now');
        END;
    ''')

    conn.commit()
    close_user_connection(conn)

def init_databases():
    """
    Initialize both databases.
    Note: Reference database should already exist with master data.
    This only initializes the user database.
    """
    # Check if reference database exists
    if not os.path.exists(REFERENCE_DB):
        logger = get_logger()
        logger.log_warning(f"Reference database '{REFERENCE_DB}' not found!")
        logger.log_warning("   Please ensure the reference database exists before starting.")
    
    # Initialize user database
    if not os.path.exists(USER_DB):
        logger = get_logger()
        logger.log_step(f"Creating user database: {USER_DB}")
    else:
        logger = get_logger()
        logger.log_step(f"User database exists: {USER_DB}")
    
    # Always run init to ensure schema is up to date (tables exist)
    init_user_database()

# Initialize databases
init_databases()

# Database helper functions
def _as_bool_int(value):
    if isinstance(value, str):
        return 1 if value.strip().lower() in ('1', 'true', 'yes', 'on') else 0
    return 1 if bool(value) else 0

def _as_float(value, default=None):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def _as_int(value, default=None):
    try:
        if value is None or value == '':
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default

def round_numeric_values(value, digits=3):
    """Round float-like values recursively for output and storage."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return round(number, digits) if math.isfinite(number) else number
    if isinstance(value, dict):
        return {
            key: round_numeric_values(item, digits)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [round_numeric_values(item, digits) for item in value]
    if isinstance(value, tuple):
        return tuple(round_numeric_values(item, digits) for item in value)
    return value

def _json_dumps(value):
    return json.dumps(value or {}, default=str, ensure_ascii=False)

def _annual_emissions_from_result(energy_data):
    return (
        _as_float(energy_data.get('annual_emissions'))
        or _as_float(energy_data.get('annual_co2_kg'))
        or _as_float(energy_data.get('annual_co2'))
        or _as_float(energy_data.get('annual_emissions_kg'))
        or 0
    )

def _get_calculation_method(energy_data):
    fuel_details = energy_data.get('fuel_details') if isinstance(energy_data, dict) else {}
    if not isinstance(fuel_details, dict):
        fuel_details = {}
    return (
        energy_data.get('calculation_method')
        or fuel_details.get('calculation_method')
        or ''
    )

def _get_primary_fuel(energy_data):
    fuel_details = energy_data.get('fuel_details') if isinstance(energy_data, dict) else {}
    if not isinstance(fuel_details, dict):
        return 'Unknown'

    fuel_type = fuel_details.get('type')
    if fuel_type:
        return fuel_type

    fuels_used = fuel_details.get('fuels_used')
    if isinstance(fuels_used, list) and fuels_used:
        return 'Multiple' if len(fuels_used) > 1 else fuels_used[0]

    fuel_breakdown = fuel_details.get('fuel_breakdown')
    if isinstance(fuel_breakdown, dict) and fuel_breakdown:
        names = list(fuel_breakdown.keys())
        return 'Multiple' if len(names) > 1 else names[0]

    fuel_rows = [key for key, value in fuel_details.items() if isinstance(value, dict)]
    if fuel_rows:
        return 'Multiple' if len(fuel_rows) > 1 else fuel_rows[0]

    return 'Unknown'

def _fuel_breakdown_rows(energy_data):
    fuel_details = energy_data.get('fuel_details') if isinstance(energy_data, dict) else {}
    if not isinstance(fuel_details, dict):
        return []

    fuel_breakdown = fuel_details.get('fuel_breakdown')
    if isinstance(fuel_breakdown, dict) and fuel_breakdown:
        source = fuel_breakdown
    else:
        source = {
            fuel_name: details
            for fuel_name, details in fuel_details.items()
            if isinstance(details, dict)
        }

    rows = []
    total_energy = _as_float(energy_data.get('monthly_energy_kwh'), 0) or 0
    for fuel_name, details in source.items():
        if not isinstance(details, dict):
            continue
        energy_delivered = (
            _as_float(details.get('energy_delivered'))
            or _as_float(details.get('delivered_energy_kwh'))
            or _as_float(details.get('energy_delivered_kwh'))
            or 0
        )
        annual_emissions = (
            _as_float(details.get('annual_emissions'))
            or _as_float(details.get('annual_co2_kg'))
            or _as_float(details.get('annual_co2'))
            or 0
        )
        percentage = _as_float(details.get('percentage'))
        if percentage is None and total_energy > 0:
            percentage = (energy_delivered / total_energy) * 100

        monthly_quantity = (
            _as_float(details.get('monthly_quantity'))
            or _as_float(details.get('quantity'))
            or _as_float(details.get('monthly_scm'))
            or _as_float(details.get('monthly_kg'))
            or _as_float(details.get('cylinders_per_month'))
        )

        rows.append(round_numeric_values({
            'fuel_type': details.get('fuel_type') or details.get('type') or fuel_name,
            'percentage_usage': percentage,
            'monthly_quantity': monthly_quantity,
            'quantity_unit': details.get('quantity_unit') or details.get('unit') or '',
            'monthly_cost': _as_float(details.get('monthly_cost'), 0) or 0,
            'energy_delivered_kwh': energy_delivered,
            'monthly_emissions_kg': _as_float(details.get('monthly_emissions_kg')) or (annual_emissions / 12 if annual_emissions else 0)
        }, 3))
    return rows

def _selected_dish_rows(entity_type, profile_data, energy_data):
    fuel_details = energy_data.get('fuel_details') if isinstance(energy_data, dict) else {}
    if not isinstance(fuel_details, dict):
        return []

    selected = fuel_details.get('selected_dishes') or []
    if not isinstance(selected, list):
        return []

    if entity_type == 'institution':
        working_days = _as_float(profile_data.get('working_days'), 30) or 30
        default_frequency = round((working_days * 7) / 30, 2)
        default_portions = _as_int(profile_data.get('servings_per_day'), 1)
    else:
        default_frequency = 7
        default_portions = _as_int(profile_data.get('household_size'), 1)

    rows = []
    for dish in selected:
        if not isinstance(dish, dict):
            continue
        dish_name = dish.get('dish_name') or dish.get('Dishes') or dish.get('dish')
        if not dish_name:
            continue
        rows.append(round_numeric_values({
            'meal_category': dish.get('meal_category') or dish.get('Category') or dish.get('category') or '',
            'dish_name': dish_name,
            'dish_id': _as_int(dish.get('dish_id')),
            'fuel_type': dish.get('fuel_type') or dish.get('stoves') or dish.get('fuel') or '',
            'frequency_per_week': _as_float(dish.get('frequency_per_week'), default_frequency),
            'portions_per_meal': _as_int(dish.get('portions_per_meal'), default_portions),
            'energy_per_serving_kwh': _as_float(dish.get('energy_per_serving_kwh'))
        }, 3))
    return rows

def _recommendation_maps(recommendations):
    scores = {}
    ranks = {}
    reasons = {}
    for idx, rec in enumerate(recommendations or [], 1):
        if isinstance(rec, (list, tuple)) and len(rec) >= 3:
            fuel, score, data = rec[0], rec[1], rec[2] or {}
            scores[fuel] = score
            ranks[fuel] = idx
            if isinstance(data, dict):
                reasons[fuel] = data.get('recommendation_reason') or data.get('reason') or ''
        elif isinstance(rec, dict):
            fuel = rec.get('fuel') or rec.get('fuel_name') or rec.get('recommended_solution')
            if fuel:
                scores[fuel] = rec.get('score') or rec.get('recommendation_score')
                ranks[fuel] = rec.get('rank') or idx
                reasons[fuel] = rec.get('recommendation_reason') or rec.get('reason') or ''
    return scores, ranks, reasons

def _persist_fuel_rows(cursor, analysis_id, entity_id, entity_type, energy_data):
    for fuel in _fuel_breakdown_rows(energy_data):
        cursor.execute('''
            INSERT INTO fuel_selections (
                analysis_id, entity_id, entity_type, fuel_type, percentage_usage,
                monthly_quantity, quantity_unit, monthly_cost, energy_delivered_kwh,
                monthly_emissions_kg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analysis_id,
            entity_id,
            entity_type,
            fuel['fuel_type'],
            fuel['percentage_usage'],
            fuel['monthly_quantity'],
            fuel['quantity_unit'],
            fuel['monthly_cost'],
            fuel['energy_delivered_kwh'],
            fuel['monthly_emissions_kg']
        ))

def _persist_dish_rows(cursor, analysis_id, entity_id, entity_type, profile_data, energy_data):
    for dish in _selected_dish_rows(entity_type, profile_data, energy_data):
        cursor.execute('''
            INSERT INTO dish_selections (
                analysis_id, entity_id, entity_type, meal_category, dish_name,
                dish_id, fuel_type, frequency_per_week, portions_per_meal,
                energy_per_serving_kwh
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analysis_id,
            entity_id,
            entity_type,
            dish['meal_category'],
            dish['dish_name'],
            dish['dish_id'],
            dish['fuel_type'],
            dish['frequency_per_week'],
            dish['portions_per_meal'],
            dish['energy_per_serving_kwh']
        ))

def _persist_alternative_rows(cursor, analysis_id, alternatives, recommendations, current_cost):
    scores, ranks, reasons = _recommendation_maps(recommendations)
    if not isinstance(alternatives, dict):
        return

    for fuel_name, data in alternatives.items():
        if not isinstance(data, dict):
            continue
        monthly_cost = _as_float(data.get('monthly_cost'), 0) or 0
        monthly_savings = _as_float(data.get('monthly_savings'))
        if monthly_savings is None:
            monthly_savings = (_as_float(current_cost, 0) or 0) - monthly_cost
        upfront_cost = _as_float(data.get('upfront_cost')) or _as_float(data.get('capital_cost'), 0) or 0
        payback_months = _as_float(data.get('payback_period_months'))
        if payback_months is None:
            payback_years = _as_float(data.get('payback_years'))
            if payback_years is not None:
                payback_months = payback_years * 12
            elif monthly_savings > 0 and upfront_cost > 0:
                payback_months = upfront_cost / monthly_savings
        monthly_cost = round_numeric_values(monthly_cost, 3)
        monthly_savings = round_numeric_values(monthly_savings, 3)
        upfront_cost = round_numeric_values(upfront_cost, 3)
        payback_months = round_numeric_values(payback_months, 3)
        annual_emissions = round_numeric_values(
            _as_float(data.get('annual_emissions_kg')) or _as_float(data.get('annual_co2'), 0) or 0,
            3
        )
        health_risk_score = round_numeric_values(_as_float(data.get('health_risk_score'), 0) or 0, 3)
        recommendation_score = round_numeric_values(scores.get(fuel_name), 3)

        cursor.execute('''
            INSERT INTO alternative_options (
                analysis_id, rank, fuel_name, monthly_cost, monthly_savings,
                payback_period_months, upfront_cost, annual_emissions_kg,
                health_risk_score, environmental_grade, recommendation_score,
                recommendation_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analysis_id,
            ranks.get(fuel_name),
            fuel_name,
            monthly_cost,
            monthly_savings,
            payback_months,
            upfront_cost,
            annual_emissions,
            health_risk_score,
            data.get('environmental_grade') or '',
            recommendation_score,
            reasons.get(fuel_name) or data.get('recommendation_reason') or data.get('reason') or ''
        ))

def save_household_data(household_data):
    """Save household profile data and return household_id."""
    household_id = str(uuid.uuid4())
    consent_given = _as_bool_int(household_data.get('consent_given', False))
    name = household_data.get('name', '') if consent_given else None
    email = household_data.get('email', '') if consent_given else None
    phone = household_data.get('phone', '') if consent_given else None
    country_code = household_data.get('country_code', '+91') if consent_given else None

    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO households (
                household_id, survey_date, name, email, phone, country_code,
                district, area_type, household_size, monthly_income, ration_card,
                lpg_subsidy, electricity_tariff, loan_interest_rate, loan_tenure,
                main_priority, calculation_method, kitchen_scenario,
                solar_willingness, solar_rooftop_area, consent_given
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            household_id,
            datetime.datetime.now().date(),
            name,
            email,
            phone,
            country_code,
            household_data.get('district', ''),
            household_data.get('area_type', ''),
            _as_int(household_data.get('household_size'), 4),
            _as_int(household_data.get('monthly_income')),
            household_data.get('ration_card'),
            household_data.get('lpg_subsidy'),
            _as_float(household_data.get('electricity_tariff'), 6.5),
            _as_float(household_data.get('loan_interest_rate'), 7.0),
            _as_int(household_data.get('loan_tenure'), 5),
            household_data.get('main_priority', 'balanced'),
            household_data.get('calculation_method', ''),
            household_data.get('kitchen_scenario', ''),
            household_data.get('solar_willingness', 'No'),
            _as_float(household_data.get('solar_rooftop_area'), 0),
            consent_given
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        close_user_connection(conn)
    return household_id

def save_institution_data(institution_data):
    """Save commercial institution profile data and return institution_id."""
    institution_id = str(uuid.uuid4())
    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO commercial_institutions (
                institution_id, survey_date, institution_name, institution_type,
                contact_person, email, phone, country_code, district, area_type,
                address, servings_per_day, working_days, electricity_tariff,
                solar_willing, roof_area_available, budget_preference,
                kitchen_scenario, cooking_hours_daily, staff_exposed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            institution_id,
            datetime.datetime.now().date(),
            institution_data.get('institution_name', ''),
            institution_data.get('institution_type', ''),
            institution_data.get('contact_person', ''),
            institution_data.get('email', ''),
            institution_data.get('phone', ''),
            institution_data.get('country_code', '+91'),
            institution_data.get('district', ''),
            institution_data.get('area_type', ''),
            institution_data.get('address', ''),
            _as_int(institution_data.get('servings_per_day')),
            _as_int(institution_data.get('working_days')),
            _as_float(institution_data.get('electricity_tariff')),
            institution_data.get('solar_willing', 'No'),
            _as_float(institution_data.get('roof_area_available')) or _as_float(institution_data.get('available_roof_area'), 0),
            institution_data.get('budget_preference') or institution_data.get('budget', ''),
            institution_data.get('kitchen_scenario', ''),
            _as_float(institution_data.get('cooking_hours_daily')),
            _as_int(institution_data.get('staff_exposed'))
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        close_user_connection(conn)
    return institution_id

def persist_analysis_session(entity_id, entity_type, analysis_type, profile_data,
                             kitchen_data, energy_data, alternatives=None,
                             recommendations=None, health_impact=None):
    """Persist one complete analysis after the results page payload is ready."""
    if entity_type not in ('household', 'institution'):
        raise ValueError("entity_type must be 'household' or 'institution'")

    profile_data = profile_data or {}
    kitchen_data = kitchen_data or {}
    energy_data = energy_data or {}
    alternatives = alternatives or {}
    recommendations = recommendations or []
    health_impact = health_impact or {}

    profile_data = round_numeric_values(profile_data, 3)
    kitchen_data = round_numeric_values(kitchen_data, 3)
    energy_data = round_numeric_values(energy_data, 3)
    alternatives = round_numeric_values(alternatives, 3)
    recommendations = round_numeric_values(recommendations, 3)
    health_impact = round_numeric_values(health_impact, 3)

    calculation_method = _get_calculation_method(energy_data)
    annual_emissions = _annual_emissions_from_result(energy_data)
    health_score = (
        _as_float(health_impact.get('health_risk_score'))
        or _as_float(energy_data.get('health_risk_score'))
        or 0
    )
    environmental_grade = energy_data.get('environmental_grade')
    if not environmental_grade and annual_emissions:
        try:
            if entity_type == 'household':
                environmental_grade = get_environmental_grade(
                    annual_emissions,
                    household_size=_as_int(profile_data.get('household_size'), 4)
                )
            else:
                environmental_grade = get_environmental_grade(annual_emissions)
        except Exception:
            environmental_grade = ''

    people_exposed = (
        _as_int(kitchen_data.get('sensitive_members'))
        if entity_type == 'household'
        else _as_int(kitchen_data.get('staff_exposed'))
    )
    payload = {
        'profile': profile_data,
        'kitchen': kitchen_data,
        'current': energy_data,
        'alternatives': alternatives,
        'recommendations': recommendations,
        'health_impact': health_impact
    }

    conn = get_user_connection()
    try:
        cursor = conn.cursor()

        if entity_type == 'household':
            cursor.execute('''
                UPDATE households
                SET kitchen_scenario = ?, calculation_method = ?
                WHERE household_id = ?
            ''', (
                kitchen_data.get('kitchen_scenario') or kitchen_data.get('kitchen_type', ''),
                calculation_method,
                entity_id
            ))
        else:
            cursor.execute('''
                UPDATE commercial_institutions
                SET kitchen_scenario = ?, cooking_hours_daily = ?, staff_exposed = ?,
                    roof_area_available = ?, budget_preference = ?
                WHERE institution_id = ?
            ''', (
                kitchen_data.get('kitchen_scenario') or kitchen_data.get('kitchen_type', ''),
                _as_float(kitchen_data.get('cooking_hours_daily')),
                _as_int(kitchen_data.get('staff_exposed')),
                _as_float(kitchen_data.get('roof_area_available')),
                kitchen_data.get('budget_preference', ''),
                entity_id
            ))

        cursor.execute('''
            INSERT INTO analysis_sessions (
                entity_id, entity_type, analysis_type, calculation_method,
                monthly_energy_kwh, monthly_cost, annual_emissions_kg,
                health_risk_score, environmental_grade, kitchen_scenario,
                cooking_hours_daily, people_exposed, roof_area_available,
                primary_fuel, overall_thermal_efficiency, cost_per_serving,
                energy_per_serving_kwh, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            entity_id,
            entity_type,
            analysis_type,
            calculation_method,
            _as_float(energy_data.get('monthly_energy_kwh'), 0) or 0,
            _as_float(energy_data.get('monthly_cost'), 0) or 0,
            annual_emissions,
            health_score,
            environmental_grade or '',
            kitchen_data.get('kitchen_scenario') or kitchen_data.get('kitchen_type', ''),
            _as_float(kitchen_data.get('cooking_hours_daily')),
            people_exposed,
            _as_float(kitchen_data.get('roof_area_available')),
            _get_primary_fuel(energy_data),
            _as_float(energy_data.get('overall_thermal_efficiency')),
            _as_float(energy_data.get('cost_per_serving')),
            _as_float(energy_data.get('energy_per_serving_kwh')),
            _json_dumps(payload)
        ))
        analysis_id = cursor.lastrowid

        _persist_fuel_rows(cursor, analysis_id, entity_id, entity_type, energy_data)
        _persist_dish_rows(cursor, analysis_id, entity_id, entity_type, profile_data, energy_data)
        _persist_alternative_rows(
            cursor,
            analysis_id,
            alternatives,
            recommendations,
            energy_data.get('monthly_cost', 0)
        )

        cursor.execute('''
            INSERT INTO user_activity_log (entity_id, entity_type, activity_type, details)
            VALUES (?, ?, ?, ?)
        ''', (
            entity_id,
            entity_type,
            'analysis_viewed',
            f"{analysis_type} {calculation_method} analysis saved"
        ))

        conn.commit()
        return analysis_id
    except Exception:
        conn.rollback()
        raise
    finally:
        close_user_connection(conn)

def save_user_feedback(feedback_data):
    """Save user feedback after an analysis has been completed."""
    conn = get_user_connection()
    try:
        feedback_id = str(uuid.uuid4())
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_feedback (
                feedback_id, entity_id, entity_type, analysis_id, name, email, phone,
                interest_clean_cooking, support_solar, support_electric_cooking,
                support_png, support_govt_schemes, support_none,
                allow_authority_contact, feedback_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            feedback_id,
            feedback_data.get('entity_id', ''),
            feedback_data.get('entity_type', ''),
            _as_int(feedback_data.get('analysis_id')),
            feedback_data.get('name', ''),
            feedback_data.get('email', ''),
            feedback_data.get('phone', ''),
            feedback_data.get('interest_clean_cooking', ''),
            _as_bool_int(feedback_data.get('support_solar', False)),
            _as_bool_int(feedback_data.get('support_electric_cooking', False)),
            _as_bool_int(feedback_data.get('support_png', False)),
            _as_bool_int(feedback_data.get('support_govt_schemes', False)),
            _as_bool_int(feedback_data.get('support_none', False)),
            _as_bool_int(feedback_data.get('allow_authority_contact', False)),
            feedback_data.get('feedback_text', '')
        ))
        cursor.execute('''
            INSERT INTO user_activity_log (entity_id, entity_type, activity_type, details)
            VALUES (?, ?, ?, ?)
        ''', (
            feedback_data.get('entity_id', ''),
            feedback_data.get('entity_type', 'unknown'),
            'feedback_submitted',
            'Feedback submitted'
        ))
        conn.commit()
        return feedback_id
    except Exception:
        conn.rollback()
        raise
    finally:
        close_user_connection(conn)

def log_user_activity(entity_id, entity_type, activity_type, details=''):
    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_activity_log (entity_id, entity_type, activity_type, details)
            VALUES (?, ?, ?, ?)
        ''', (str(entity_id), entity_type or 'unknown', activity_type, str(details)))
        conn.commit()
    except Exception as exc:
        print(f"Error logging activity: {exc}")
    finally:
        close_user_connection(conn)

def log_user_history(user_id, activity_type, details=''):
    """Compatibility wrapper for the old activity function name."""
    log_user_activity(user_id, 'unknown', activity_type, details)

def save_cooking_analysis(household_id, kitchen_data, energy_data):
    """Deprecated compatibility no-op. Results are saved on /analysis."""
    return None

def save_commercial_analysis(institution_id, result):
    """Deprecated compatibility no-op. Results are saved on /commercial_analysis."""
    return None

def save_recommendations(household_id, recommendations):
    """Deprecated compatibility no-op. Recommendations are saved with analysis."""
    return None

def save_dish_selections(entity_id, dishes, is_residential=True):
    """Deprecated compatibility no-op. Dish selections are saved with analysis."""
    return None

def save_fuel_selections(entity_id, fuels, is_residential=True):
    """Deprecated compatibility no-op. Fuel selections are saved with analysis."""
    return None

def save_alternative_recommendations(entity_id, entity_type, alternatives):
    """Deprecated compatibility no-op. Alternatives are saved with analysis."""
    return None

def get_household_data(household_id):
    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM households WHERE household_id = ?', (household_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        close_user_connection(conn)

def get_institution_data(institution_id):
    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM commercial_institutions WHERE institution_id = ?', (institution_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        close_user_connection(conn)

def get_cooking_analysis(household_id):
    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM analysis_sessions
            WHERE entity_id = ? AND entity_type = 'household'
            ORDER BY analysis_id DESC
            LIMIT 1
        ''', (household_id,))
        row = cursor.fetchone()
        data = dict(row) if row else None
        if data and data.get('payload_json'):
            data['payload'] = json.loads(data['payload_json'])
        return data
    finally:
        close_user_connection(conn)

def get_commercial_analysis(institution_id):
    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM analysis_sessions
            WHERE entity_id = ? AND entity_type = 'institution'
            ORDER BY analysis_id DESC
            LIMIT 1
        ''', (institution_id,))
        row = cursor.fetchone()
        data = dict(row) if row else None
        if data and data.get('payload_json'):
            data['payload'] = json.loads(data['payload_json'])
        return data
    finally:
        close_user_connection(conn)

def get_recommendations(entity_id):
    conn = get_user_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT analysis_id FROM analysis_sessions
            WHERE entity_id = ?
            ORDER BY analysis_id DESC
            LIMIT 1
        ''', (entity_id,))
        analysis = cursor.fetchone()
        if not analysis:
            return []
        cursor.execute('''
            SELECT * FROM alternative_options
            WHERE analysis_id = ? AND rank IS NOT NULL
            ORDER BY rank
        ''', (analysis['analysis_id'],))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        close_user_connection(conn)

# =================================================================
# SHARED CALCULATION FUNCTIONS
# =================================================================

def basic_calories(df):
    """
    Calculate total calories for each dish based on quantity
    
    Formula: Total Calories = (Calories per 100g × Quantity in grams) / 100
    """
    calorie_col = 'calories_per_100g'
    
    # Handle different column names for quantity
    if 'minimum_portion_g' in df.columns:
        quantity_col = 'minimum_portion_g'
    else:
        quantity_col = 'Minimum_Dish _Quantity'
    
    logger = get_logger()
    logger.log_subsection("BASIC CALORIES CALCULATION")
    logger.log_input("Quantity Column", quantity_col)
    
    df_calc = df.copy()
    
    # Convert to numeric, handling any non-numeric values
    df_calc[calorie_col] = pd.to_numeric(df_calc[calorie_col], errors='coerce')
    df_calc[quantity_col] = pd.to_numeric(df_calc[quantity_col], errors='coerce')
    
    # Calculate total calories
    df_calc['total_calories'] = (df_calc[calorie_col] * df_calc[quantity_col] / 100).fillna(0)
    
    # Log sample
    if not df_calc.empty:
        sample = df_calc.iloc[0]
        logger.log_calculation(
            f"Sample Dish Calories: {sample.get('Dishes', 'Unknown')}",
            "(calories_per_100g * quantity_g) / 100",
            {
                "calories_per_100g": sample.get(calorie_col, 0),
                "quantity_g": sample.get(quantity_col, 0)
            },
            f"{sample.get('total_calories', 0):.2f} kcal"
        )
    
    return df_calc

def calculate_lpg_consumption_from_refill(refill_days, cylinder_weight=14.2):
    logger = get_logger()
    logger.log_subsection("LPG CONSUMPTION CALCULATION")
    
    energy_per_cylinder = cylinder_weight * LPG_CALORIFIC_VALUE
    daily_energy_kwh = energy_per_cylinder / refill_days
    monthly_energy_kwh = daily_energy_kwh * 30
    cylinders_per_month = 30 / refill_days
    
    logger.log_calculation(
        "LPG Consumption",
        "Based on refill days",
        {
            "cylinder_weight": f"{cylinder_weight} kg",
            "calorific_value": f"{LPG_CALORIFIC_VALUE} kWh/kg",
            "refill_days": refill_days
        },
        f"{monthly_energy_kwh:.2f} kWh/month ({cylinders_per_month:.2f} cylinders)"
    )
    
    return {
        'daily_energy_kwh': daily_energy_kwh,
        'monthly_energy_kwh': monthly_energy_kwh,
        'cylinders_per_month': cylinders_per_month,
        'energy_per_cylinder': energy_per_cylinder
    }

def calculate_png_bill_and_consumption(monthly_scm_consumption, rate_per_scm):
    """
    Calculate PNG bill based on flat rate (Domestic/Commercial).
    
    Args:
        monthly_scm_consumption (float): Monthly consumption in SCM
        rate_per_scm (float): Rate per SCM (REQUIRED - must be fetched from database)
        
    Returns:
        dict: Detailed bill breakdown
    """
    daily_avg_scm = monthly_scm_consumption / 30
    
    # Simple flat rate calculation
    variable_cost = monthly_scm_consumption * rate_per_scm
    
    bill_breakdown = {
        'consumption_charge': {
            'consumption_scm': monthly_scm_consumption,
            'rate': rate_per_scm,
            'cost': variable_cost
        }
    }
    
    # Add fixed charges
    fixed_charge = db_helper.get_system_parameter('PNG_FIXED_CHARGE_MONTHLY', 0)
    meter_rent = db_helper.get_system_parameter('PNG_METER_RENT_MONTHLY', 0)
    fixed_charges_total = fixed_charge + meter_rent

    # Total bill
    total_bill_with_fixed = variable_cost + fixed_charges_total

    monthly_energy_kwh = monthly_scm_consumption * PNG_CALORIFIC_VALUE
    daily_energy_kwh = monthly_energy_kwh / 30

    cost_per_kwh = total_bill_with_fixed / monthly_energy_kwh if monthly_energy_kwh > 0 else 0
    
    logger = get_logger()
    logger.log_subsection("PNG BILL CALCULATION")
    logger.log_calculation(
        "PNG Bill",
        "Flat rate calculation",
        {
            "monthly_scm": monthly_scm_consumption,
            "rate_per_scm": rate_per_scm,
            "variable_cost": variable_cost,
            "fixed_charges": fixed_charges_total
        },
        f"Rs {total_bill_with_fixed:.2f} (Avg: Rs {cost_per_kwh:.2f}/kWh)"
    )

    return {
        'daily_energy_kwh': daily_energy_kwh,
        'monthly_energy_kwh': monthly_energy_kwh,
        'monthly_scm_consumption': monthly_scm_consumption,
        'daily_avg_scm': daily_avg_scm,
        'rate_per_scm': rate_per_scm,
        'base_rate_per_scm': rate_per_scm,
        'total_bill': total_bill_with_fixed,
        'variable_bill': variable_cost,
        'fixed_charges': fixed_charges_total,
        'bill_breakdown': bill_breakdown,
        'average_rate_per_scm': total_bill_with_fixed / monthly_scm_consumption if monthly_scm_consumption > 0 else 0,
        'cost_per_kwh': cost_per_kwh
    }

    


def calculate_png_consumption_from_bill(total_bill_amount, rate_per_scm=None, district='All', category='Domestic'):
    """Reverse calculate PNG consumption from bill amount."""
    logger = get_logger()
    logger.log_subsection("PNG CONSUMPTION FROM BILL")
    logger.log_input("Total Bill Amount", f"₹{total_bill_amount}")

    # Resolve rate from DB if not explicitly provided.
    if rate_per_scm is None:
        png_price_data = db_helper.get_png_pricing(district=district, category=category)
        if png_price_data:
            rate_per_scm = float(png_price_data['price_per_scm'])
        else:
            # Fallback still comes from reference DB system parameters.
            fallback_param = 'PNG_DOMESTIC_RATE' if category == 'Domestic' else 'PNG_COMMERCIAL_RATE'
            fallback_default = 54.0 if category == 'Domestic' else 47.0
            rate_per_scm = float(db_helper.get_system_parameter(fallback_param, fallback_default))
    else:
        rate_per_scm = float(rate_per_scm)

    logger.log_input("PNG Rate Used", f"₹{rate_per_scm:.2f}/SCM")

    def bill_for_consumption(scm):
        if scm <= 0:
            return 0
        result = calculate_png_bill_and_consumption(scm, rate_per_scm=rate_per_scm)
        return result['total_bill']
    
    # Binary search for consumption that matches the bill.
    # Upper bound: estimate from bill ÷ rate (no fixed charges) × 2 safety factor.
    # Min 200 SCM so residential bills always fit; no hard cap for large commercial bills.
    estimated_max = int(total_bill_amount / max(rate_per_scm, 0.01)) + 200
    low, high = 0.0, max(200.0, float(estimated_max))
    tolerance = 1  # ±1 rupee tolerance
    logger.log_step(f"Binary search bounds set: low={low} SCM, high={high} SCM, tolerance=₹{tolerance}")
    
    while high - low > 0.1:  # 0.1 SCM precision
        mid = (low + high) / 2
        calculated_bill = bill_for_consumption(mid)
        logger.log_calculation(
            "PNG Bill Solver Iteration",
            "binary search mid → bill",
            {"mid_scm": round(mid, 3), "low": round(low, 3), "high": round(high, 3)},
            f"Calculated bill: ₹{calculated_bill:.2f}"
        )
        
        if abs(calculated_bill - total_bill_amount) <= tolerance:
            result = calculate_png_bill_and_consumption(mid, rate_per_scm=rate_per_scm)
            logger.log_success(f"Match found within tolerance at {mid:.3f} SCM")
            logger.log_data("Resolved PNG Bill Result", result)
            return result
        elif calculated_bill < total_bill_amount:
            low = mid
        else:
            high = mid
    
    # Return the closest match
    final_consumption = (low + high) / 2
    result = calculate_png_bill_and_consumption(final_consumption, rate_per_scm=rate_per_scm)
    logger.log_warning(f"No exact match within tolerance; using closest SCM {final_consumption:.3f}")
    logger.log_data("Closest PNG Bill Result", result)
    return result


def calculate_co2_emissions(daily_energy_kwh, emission_factor, institution_data=None):
    """
    Calculate annual CO2 emissions from daily energy consumption.
    
    Args:
        daily_energy_kwh: Daily energy consumption in kWh
        emission_factor: CO2 emission factor (kg CO2/kWh)
        institution_data: Optional dict with 'working_days' for commercial calculations
    
    Returns:
        float: Annual CO2 emissions in kg/year
    """
    logger = get_logger()
    
    # Determine annual factor based on working days
    if institution_data and 'working_days' in institution_data:
        working_days = institution_data.get('working_days', 30)
        monthly_factor = float(working_days) if working_days else 30.0
        
        # For commercial: scale to full year based on working pattern
        # If working 26 days/month, that's 312 days/year (26 * 12)
        annual_days = monthly_factor * 12
        
        logger.log_data("Commercial CO2 Calculation", {
            "working_days_per_month": working_days,
            "annual_working_days": annual_days,
            "daily_energy": daily_energy_kwh,
            "emission_factor": emission_factor
        })
    else:
        # For residential: use standard 365 days/year
        annual_days = 365
        logger.log_data("Residential CO2 Calculation", {
            "annual_days": annual_days,
            "daily_energy": daily_energy_kwh,
            "emission_factor": emission_factor
        })
    
    annual_emissions = daily_energy_kwh * annual_days * emission_factor
    
    logger.log_calculation(
        "CO2 Emissions",
        f"daily_energy_kwh × {annual_days} × emission_factor",
        {
            "daily_energy_kwh": daily_energy_kwh, 
            "emission_factor": emission_factor,
            "annual_days": annual_days
        },
        f"{annual_emissions:.2f}",
        "kg CO₂/year"
    )
    
    return annual_emissions



def calculate_pollutant_exposure(base_emission, kitchen_type, ventilation_quality, cooking_hours, scenario_type='residential'):
    """
    Calculate PM2.5 peak concentration in µg/m³ using a Scenario-Based IAQ box model.

    Formula:
        C (µg/m³) = base_emission × scenario_factor × hours_factor × PM25_SCALE

    where:
        base_emission   — fuel PM2.5 emission index from emission_factors table
                          (proportional to g PM2.5 emitted per kWh of input energy)
        scenario_factor — combined kitchen exposure factor (ventilation + layout),
                          loaded from kitchen_scenarios table (0.04 – 0.80)
        hours_factor    — cooking duration modifier: min(hours/3.0, 1.5)
                          (longer sessions raise time-averaged concentration; capped at 1.5×
                           so a 6-h cook is 1.5× not 2× a 3-h cook)
        PM25_SCALE      — calibration constant (µg/m³ per unit of emission_index × factor)
                          stored as 'PM25_CONCENTRATION_SCALE' system parameter (default 5000).
                          Calibrated so LPG + No-Exhaust kitchen ≈ 50 µg/m³ (above WHO guideline).

    DB thresholds (health_risk_thresholds) use µg/m³ so the output of this function must
    be in the same units for get_health_risk_score() to return meaningful scores.
    """
    combined_factor = db_helper.get_scenario_factor(kitchen_type, scenario_type)

    # Cooking duration modifier — baseline is 3 h, max multiplier capped at 1.5
    hours_factor = min(max(cooking_hours, 0.5) / 3.0, 1.5)

    # Scale emission index → µg/m³ (DB parameter so it can be adjusted without code changes)
    pm25_scale = db_helper.get_system_parameter('PM25_CONCENTRATION_SCALE', 5000.0)

    peak_exposure_ug_m3 = base_emission * combined_factor * hours_factor * pm25_scale

    logger = get_logger()
    logger.log_calculation(
        "Pollutant Exposure IAQ (µg/m³)",
        "base_emission × scenario_factor × hours_factor × PM25_SCALE",
        {
            "base_emission": base_emission,
            "scenario_name": kitchen_type,
            "scenario_type": scenario_type,
            "combined_factor": combined_factor,
            "cooking_hours": cooking_hours,
            "hours_factor": round(hours_factor, 3),
            "pm25_scale": pm25_scale,
        },
        f"{peak_exposure_ug_m3:.2f} µg/m³"
    )
    return peak_exposure_ug_m3

def calculate_health_risk_score(pm25_peak_exposure, cooking_hours, sensitive_members):
    """Calculate health risk score using database thresholds.

    pm25_peak_exposure is now in µg/m³ (output of calculate_pollutant_exposure).
    DB health_risk_thresholds are also in µg/m³ — units now match.

    The old guard (< 1.0) fired for EVERY fuel because peak_exposure was a raw emission
    index (0.0002 – 0.4) not a concentration.  It is replaced with a physically meaningful
    threshold: fuels that produce < PM25_LOW_RISK_THRESHOLD µg/m³ (default 5 µg/m³,
    covering Grid electricity and Solar which have pm25_factor = 0.0) are treated as clean
    and receive no sensitive/duration penalty.
    """
    logger = get_logger()
    logger.log_subsection("HEALTH RISK SCORE")
    logger.log_input("PM2.5 Peak Exposure (µg/m³)", pm25_peak_exposure)
    logger.log_input("Cooking Hours", cooking_hours)
    logger.log_input("Sensitive Members", sensitive_members)

    # Get PM2.5 base score from database (thresholds are in µg/m³)
    pm25_score, _ = db_helper.get_health_risk_score(pm25_peak_exposure)

    # Get penalty factors from database
    sensitive_penalty_factor = db_helper.get_system_parameter('HEALTH_SENSITIVE_PENALTY', 10)
    duration_penalty_factor = db_helper.get_system_parameter('HEALTH_DURATION_PENALTY', 5)
    baseline_hours = db_helper.get_system_parameter('HEALTH_BASELINE_HOURS', 2)

    # Clean-fuel threshold in µg/m³: fuels below this emit virtually no PM2.5
    # (Grid electricity, Solar — pm25_factor = 0.0 in DB → concentration ≈ 0)
    low_risk_ug_m3 = db_helper.get_system_parameter('PM25_LOW_RISK_THRESHOLD_UG_M3', 5.0)

    if pm25_peak_exposure <= low_risk_ug_m3:
        # Essentially zero PM2.5 — no penalties for sensitive members or duration
        sensitive_penalty = 0
        duration_penalty = 0
        health_risk_score = pm25_score
    else:
        sensitive_penalty = sensitive_members * sensitive_penalty_factor
        duration_penalty = max(0, (cooking_hours - baseline_hours) * duration_penalty_factor)
        health_risk_score = pm25_score + sensitive_penalty + duration_penalty

    logger.log_calculation(
        "Health Risk Score",
        "pm25_score + sensitive_penalty + duration_penalty",
        {
            "pm25_score": pm25_score,
            "sensitive_penalty": sensitive_penalty,
            "duration_penalty": duration_penalty
        },
        f"{health_risk_score:.2f}"
    )

    return min(100, health_risk_score)

def categorize_health_risk(score):
    """Categorize health risk based on score.

    Cut-points are midpoints between consecutive DB base scores (10/25/45/65/85):
      midpoints → 17.5, 35, 55, 75
    Using integer boundaries: 17, 35, 55, 75.
    """
    if score <= 17:
        return "low"
    elif score <= 35:
        return "moderate"
    elif score <= 55:
        return "high"
    elif score <= 75:
        return "very_high"
    else:
        return "critical"

def get_environmental_grade(annual_co2_kg, household_size=4):
    """
    Get environmental grade based on annual per-member emissions.
    Default household size 4 if not provided.
    """
    if household_size <= 0: 
        household_size = 4
        
    per_member_emissions = annual_co2_kg / household_size
    
    grade, label = db_helper.get_environmental_grade(per_member_emissions, metric='annual_per_member_kg')
    
    logger = get_logger()
    logger.log_result(
        "Environmental Grade", 
        f"{grade} ({label})", 
        f"Based on {per_member_emissions:.1f} kg/person/year (Total: {annual_co2_kg:.1f} kg)"
    )
    return grade

def calculate_solar_system_sizing(daily_energy_kwh, roof_area):
    # Get solar sizing parameters from database
    sizing_buffer = db_helper.get_system_parameter('SOLAR_SIZING_BUFFER', 1.2)
    area_per_kw = db_helper.get_system_parameter('SOLAR_AREA_PER_KW', 8)

    required_capacity = (daily_energy_kwh * sizing_buffer) / (Keralam_SOLAR_GHI * SOLAR_SYSTEM_EFF * Keralam_WEATHER_FACTOR)
    max_capacity_by_area = roof_area / area_per_kw
    system_capacity = min(required_capacity, max_capacity_by_area)
    logger = get_logger()
    logger.log_subsection("SOLAR SYSTEM SIZING")
    logger.log_input("Daily Energy (kWh)", daily_energy_kwh)
    logger.log_input("Roof Area (m²)", roof_area)
    logger.log_data("Sizing Parameters", {
        "sizing_buffer": sizing_buffer,
        "area_per_kw": area_per_kw,
        "ghi": Keralam_SOLAR_GHI,
        "system_eff": SOLAR_SYSTEM_EFF,
        "weather_factor": Keralam_WEATHER_FACTOR
    })
    logger.log_result("Required Capacity (kW)", f"{required_capacity:.3f}")
    logger.log_result("Max Capacity By Area (kW)", f"{max_capacity_by_area:.3f}")
    logger.log_result("Selected System Capacity (kW)", f"{system_capacity:.3f}")
    return system_capacity, required_capacity

def calculate_emi(principal, annual_rate, tenure_years):
    if principal <= 0 or annual_rate <= 0 or tenure_years <= 0:
        return 0

    monthly_rate = annual_rate / 12
    total_payments = tenure_years * 12

    if monthly_rate == 0:
        return principal / total_payments

    emi = (principal * monthly_rate * ((1 + monthly_rate) ** total_payments)) / \
          (((1 + monthly_rate) ** total_payments) - 1)

    logger = get_logger()
    logger.log_calculation(
        "EMI Calculation",
        "standard amortization",
        {
            "principal": principal,
            "annual_rate": annual_rate,
            "tenure_years": tenure_years,
            "monthly_rate": monthly_rate,
            "payments": total_payments
        },
        f"{emi:.2f} per month"
    )

    return emi

def calculate_bess_sizing(breakfast_energy, dinner_energy, breakfast_timing='late'):
    """
    Calculate battery (BESS) requirements based on meal energy and timing

    Args:
        breakfast_energy: Monthly breakfast energy requirement (kWh)
        dinner_energy: Monthly dinner energy requirement (kWh)
        breakfast_timing: 'early' (6-7 AM) or 'late' (9-10 AM)

    Returns:
        dict with battery specs:
            - daily_bess_energy: Daily energy from battery (kWh/day)
            - bess_capacity_required: Required battery capacity accounting for losses (kWh)
            - battery_units: Number of kWh battery units needed
            - battery_cost: Total battery capital cost (Rs)
            - breakfast_from_bess: Monthly breakfast energy from BESS (kWh)
            - dinner_from_bess: Monthly dinner energy from BESS (kWh)
    """
    # Determine if breakfast uses BESS
    if breakfast_timing == 'early':  # 6-7 AM
        breakfast_from_bess = breakfast_energy
    else:  # 9-10 AM or later - solar available
        breakfast_from_bess = 0

    # Dinner always uses BESS (evening, after sunset)
    dinner_from_bess = dinner_energy

    # Total monthly BESS load
    total_bess_monthly = breakfast_from_bess + dinner_from_bess

    # Convert to daily
    daily_bess_energy = total_bess_monthly / 30

    # Account for battery efficiency and depth of discharge
    # Combined factor = efficiency × DoD = 0.90 × 0.80 = 0.72
    bess_capacity_required = daily_bess_energy / BATTERY_COMBINED_FACTOR

    # Calculate number of battery units (round up)
    battery_units = math.ceil(bess_capacity_required / BATTERY_CAPACITY_PER_UNIT)

    # Calculate battery cost
    battery_cost = battery_units * BATTERY_COST_PER_KWH

    logger = get_logger()
    logger.log_subsection("BESS SIZING")
    logger.log_data("Inputs", {
        "breakfast_energy": breakfast_energy,
        "dinner_energy": dinner_energy,
        "breakfast_timing": breakfast_timing,
        "battery_efficiency": BATTERY_EFFICIENCY,
        "battery_dod": BATTERY_DOD
    })
    logger.log_data("Derived", {
        "breakfast_from_bess": breakfast_from_bess,
        "dinner_from_bess": dinner_from_bess,
        "daily_bess_energy": daily_bess_energy,
        "bess_capacity_required": bess_capacity_required,
        "battery_units": battery_units,
        "battery_cost": battery_cost
    })

    return {
        'daily_bess_energy': daily_bess_energy,
        'bess_capacity_required': bess_capacity_required,
        'battery_units': battery_units,
        'battery_cost': battery_cost,
        'breakfast_from_bess': breakfast_from_bess,
        'dinner_from_bess': dinner_from_bess,
        'total_bess_monthly': total_bess_monthly
    }

def calculate_solar_with_bess_sizing(breakfast_energy, lunch_energy, dinner_energy, snacks_energy,
                                     breakfast_timing, roof_area, category='Domestic'):
    """
    Calculate solar + BESS system sizing based on SUPPLY CONSTRAINTS.
    Logic:
    1. Determine limits based on Roof Area.
    2. Prioritize direct daytime consumption (Lunch, Snacks, Late Breakfast).
    3. Only size BESS to store EXCESS solar (if any).
    4. Meet remaining deficits via Grid Backup.

    Args:
        breakfast_energy, lunch_energy, dinner_energy, snacks_energy: Monthly energy per meal (kWh)
        breakfast_timing: 'early' (6-7 AM) or 'late' (9-10 AM)
        roof_area: Available roof area (m²)

    Returns:
        dict with complete system specs
    """
    # --- 1. Determine Loads (Daily) ---
    daily_breakfast = breakfast_energy / 30
    daily_lunch = lunch_energy / 30
    daily_dinner = dinner_energy / 30
    daily_snacks = snacks_energy / 30

    # Classify loads
    daytime_load = daily_lunch + daily_snacks
    evening_load = daily_dinner # Dinner is always evening/night

    if breakfast_timing == 'early':
        evening_load += daily_breakfast # Regard early morning as "non-solar" logic (needs battery/grid)
    else:
        daytime_load += daily_breakfast

    total_daily_load = daytime_load + evening_load

    # --- 2. Determine Solar Potential ---
    # Max capacity allowed by roof (approx 8m² per kW)
    max_solar_kw = roof_area / 8
    
    # Generation factors
    daily_gen_per_kw = Keralam_SOLAR_GHI * SOLAR_SYSTEM_EFF * Keralam_WEATHER_FACTOR
    
    # Potential generation if we filled the roof
    potential_daily_gen = max_solar_kw * daily_gen_per_kw

    # --- 3. Energy Balance & Sizing ---
    
    # A. Meet Daytime Load First
    # We can only meet what we can generate
    daytime_solar_supplied = min(daytime_load, potential_daily_gen)
    daytime_grid_needed = daytime_load - daytime_solar_supplied
    
    # B. Check Excess for Battery
    excess_solar = max(0, potential_daily_gen - daytime_solar_supplied)
    
    # C. Size Battery (Supply Constrained)
    # We need 'evening_load'. We have 'excess_solar'.
    # Battery Output available = Excess Solar * Charging Eff (approx 0.9)
    # round-trip eff is handled in capacity calc, here we just look at energy available to put IN
    CHARGING_EFFICIENCY = 0.95 
    storable_output = excess_solar * CHARGING_EFFICIENCY
    
    # The battery output target is limited by both Demand and Supply
    bess_output_daily = min(evening_load, storable_output)
    
    # D. Calculate Grid Backup for Evening
    evening_grid_needed = evening_load - bess_output_daily
    
    # --- 4. Final Dimensions ---
    
    # Solar Size:
    # We need to generate: (Daytime Supplied) + (Energy to put into Battery)
    # Energy into Battery = bess_output_daily / CHARGING_EFFICIENCY
    required_gen = daytime_solar_supplied + (bess_output_daily / CHARGING_EFFICIENCY if bess_output_daily > 0 else 0)
    
    # Apply standard oversizing buffer (1.2) for reliability?
    # Or stick to strict generation potential?
    # Let's keep the user's roof limit as the hard stop.
    required_gen_with_buffer = required_gen * 1.1 # 10% buffer
    
    calculated_solar_kw = required_gen_with_buffer / daily_gen_per_kw
    calculated_solar_kw = math.ceil(calculated_solar_kw)
    # Cap at max roof capacity and round DOWN to whole number
    calculated_solar_capped = min(calculated_solar_kw, max_solar_kw)
    final_solar_kw = math.ceil(calculated_solar_capped)
    
    # Ensure minimum 1kW if roof space is available (no constraint case)
    if final_solar_kw == 0 and max_solar_kw >= 1 and calculated_solar_capped > 0:
        final_solar_kw = 1
    
    # Recalculate actual generation matches
    # If we hit the roof cap, we implied `excess_solar` limits above, so `bess_output_daily` is already correct.
    # If we didn't hit cap, we generate exactly what's needed.
    
    # Battery Size:
    # Calculate hardware needed to deliver `bess_output_daily`
    if bess_output_daily > 0.1: # Minimum viable
        # Reuse helper logic but manually
        bess_capacity_raw = bess_output_daily / BATTERY_COMBINED_FACTOR
        # Round UP battery capacity to whole kWh
        bess_capacity_required = math.ceil(bess_capacity_raw)
        battery_units = math.ceil(bess_capacity_required / BATTERY_CAPACITY_PER_UNIT)
        battery_cost = battery_units * BATTERY_COST_PER_KWH
        daily_bess_energy = bess_output_daily
    else:
        # Battery not needed - keep at 0
        bess_capacity_required = 0
        battery_units = 0
        battery_cost = 0
        daily_bess_energy = 0
        
    # --- 5. Costs & Output ---


    def calculate_solar_net_cost(final_solar_kw, capital_cost_per_kw, installation_cost, is_domestic=True):
        """
        Calculate solar panel cost with subsidies for domestic, without for commercial.
        
        Domestic subsidies:
        - <2 kW: ₹30k/kW subsidy
        - 2-3 kW: ₹60k fixed subsidy
        - >=3 kW: ₹78k max cap subsidy
        
        Commercial: No subsidies applied
        """
        gross_cost = final_solar_kw * capital_cost_per_kw + installation_cost
        
        if not is_domestic:
            # Commercial: No subsidies
            return gross_cost
        
        # Domestic: Apply subsidies
        if final_solar_kw > 0 and final_solar_kw < 2:
            # ₹30k/kW subsidy (first 2kW slab)
            solar_cost = final_solar_kw * (capital_cost_per_kw - 30000) + installation_cost
        elif final_solar_kw >= 2 and final_solar_kw < 3:
            # ₹60k fixed (2kW @ ₹30k) + subtract from gross
            solar_cost = gross_cost - 60000
        else:  # >= 3kW
            # ₹78k max cap
            solar_cost = gross_cost - 78000
        
        return solar_cost
    
    # Determine if domestic or commercial for subsidy calculation
    is_domestic = (category == 'Domestic')
    solar_cost = calculate_solar_net_cost(final_solar_kw, SOLAR_CAPITAL_COST_PER_KW, SOLAR_INSTALLATION_COST, is_domestic)
    
    total_capital_cost = solar_cost + battery_cost
    
    
    total_grid_backup_daily = daytime_grid_needed + evening_grid_needed
    grid_backup_percent = (total_grid_backup_daily / total_daily_load * 100) if total_daily_load > 0 else 0
    
    # Build BESS Specs dict for display consistency
    bess_specs = {
        'daily_bess_energy': daily_bess_energy,
        'bess_capacity_required': bess_capacity_required,
        'battery_units': battery_units,
        'battery_cost': battery_cost,
        'breakfast_from_bess': daily_breakfast * 30 if (breakfast_timing == 'early' and daily_bess_energy >= (daily_breakfast + daily_dinner)) else 0, # Simplified
        'dinner_from_bess': daily_dinner * 30 if daily_bess_energy > 0 else 0
    }
    
    logger = get_logger()
    logger.log_subsection("SUPPLY-CONSTRAINED SOLAR SIZING")
    logger.log_data("Balance", {
        "roof_area": roof_area,
        "solar panel cost": solar_cost,
        "bess required in kwh":bess_capacity_required,
        "bess size": battery_units,
        "bess cost in rupees": battery_cost,
        "total system solar+bess cost": total_capital_cost,
        "max_solar_kw": max_solar_kw,
        "daytime_load": daytime_load,
        "evening_load": evening_load,
        "potential_gen": potential_daily_gen,
        "bess_output": bess_output_daily,
        "grid_backup": total_grid_backup_daily
    })

    return {
        'solar_capacity_kw': final_solar_kw,
        'required_capacity_kw': calculated_solar_kw,
        'solar_cost': solar_cost,
        'battery_units': battery_units,
        'battery_capacity_kwh': bess_capacity_required,
        'battery_cost': battery_cost,
        'total_capital_cost': total_capital_cost,
        'daily_solar_generation': final_solar_kw * daily_gen_per_kw,
        'daily_direct_solar_load': daytime_solar_supplied,
        'daily_battery_charging': (bess_output_daily / CHARGING_EFFICIENCY if bess_output_daily > 0 else 0),
        'bess_specs': bess_specs,
        'energy_breakdown': {
            'breakfast_from_solar': (daily_breakfast * 30) if breakfast_timing != 'early' else 0,
            'breakfast_from_bess': bess_specs['breakfast_from_bess'],
            'lunch_from_solar': daily_lunch * 30,
            'snacks_from_solar': daily_snacks * 30,
            'dinner_from_bess': bess_specs['dinner_from_bess']
        },
        'grid_backup': {
            'needed_kwh_daily': total_grid_backup_daily,
            'percentage': grid_backup_percent
        }
    }

def calculate_levelized_cost_25yr(capital_cost, loan_percentage, annual_interest_rate,
                                   tenure_years, solar_capacity_kw, battery_cost,
                                   use_npv=False, maintenance_annual_pct=0.01):
    """
    Calculate 25-year levelized monthly cost for solar + BESS system

    This accounts for:
    - Initial loan payments
    - Battery replacements (every 7 years)
    - Maintenance costs
    - Optionally applies NPV discounting

    Args:
        capital_cost: Total initial capital cost (Rs)
        loan_percentage: Percentage financed (default 80%)
        annual_interest_rate: Annual loan interest rate (e.g., 0.09 for 9%)
        tenure_years: Loan tenure in years
        solar_capacity_kw: Solar system capacity for maintenance calculation
        battery_cost: Cost of battery bank (for replacement calculation)
        use_npv: Whether to apply NPV discounting (default False for simplicity)
        maintenance_annual_pct: Annual maintenance as % of Capital Cost (or per kW if logic dictates, but standard is % of Capex in this model)
                                WAIT: The previous logic was `solar_capacity_kw * SOLAR_MAINTENANCE_PER_KW_ANNUAL`.
                                If we switch to %, it should be `capital_cost * maintenance_annual_pct`.
                                Let's support both or switch to the requested dynamic model which uses %.
    """
    # 1. LOAN COSTS
    loan_amount = capital_cost * (loan_percentage / 100)
    down_payment = capital_cost - loan_amount

    monthly_emi = calculate_emi(loan_amount, annual_interest_rate, tenure_years)
    total_loan_payments = monthly_emi * tenure_years * 12
    total_paid_during_loan = down_payment + total_loan_payments

    # 2. BATTERY REPLACEMENT COSTS
    # Batteries replaced at years 7, 14, 21 (3 times over 25 years)
    battery_replacements = 3

    if use_npv:
        # Apply NPV discounting for future battery replacements
        discount_rate = DEFAULT_DISCOUNT_RATE
        npv_replacement_cost = (
            battery_cost / ((1 + discount_rate) ** 7) +
            battery_cost / ((1 + discount_rate) ** 14) +
            battery_cost / ((1 + discount_rate) ** 21)
        )
        total_battery_replacement_cost = npv_replacement_cost
    else:
        # Simple sum without discounting
        total_battery_replacement_cost = battery_cost * battery_replacements

    # 3. MAINTENANCE COSTS
    # New Logic: Calculate based on % of Capital Cost OR capacity if that was the intent.
    # The 'loan_and_capital_costs' table has 'maintenance_annual_pct'.
    # So we should use: annual_maintenance = capital_cost * maintenance_annual_pct
    annual_maintenance = capital_cost * maintenance_annual_pct

    if use_npv:
        # Apply NPV discounting for future maintenance
        discount_rate = DEFAULT_DISCOUNT_RATE
        npv_maintenance = sum(
            annual_maintenance / ((1 + discount_rate) ** year)
            for year in range(1, SOLAR_LIFETIME_YEARS + 1)
        )
        total_maintenance_25yr = npv_maintenance
    else:
        # Simple sum without discounting
        total_maintenance_25yr = annual_maintenance * SOLAR_LIFETIME_YEARS

    # 4. TOTAL 25-YEAR COST
    total_25yr_cost = (
        total_paid_during_loan +
        total_battery_replacement_cost +
        total_maintenance_25yr
    )

    # 5. LEVELIZED MONTHLY COST
    # Spread over 25 years = 300 months
    levelized_monthly_cost = total_25yr_cost / (SOLAR_LIFETIME_YEARS * 12)

    logger = get_logger()
    logger.log_subsection("LEVELIZED COST 25YR")
    logger.log_data("Loan Inputs", {
        "capital_cost": capital_cost,
        "loan_percentage": loan_percentage,
        "annual_interest_rate": annual_interest_rate,
        "tenure_years": tenure_years
    })
    logger.log_data("Loan Calculations", {
        "loan_amount": loan_amount,
        "down_payment": down_payment,
        "monthly_emi": monthly_emi,
        "total_paid_during_loan": total_paid_during_loan
    })
    logger.log_data("Battery & Maintenance", {
        "battery_replacements": battery_replacements,
        "total_battery_replacement_cost": total_battery_replacement_cost,
        "annual_maintenance": annual_maintenance,
        "total_maintenance_25yr": total_maintenance_25yr
    })
    logger.log_result("Total 25yr Cost", f"₹{total_25yr_cost:,.2f}")
    logger.log_result("Levelized Monthly Cost", f"₹{levelized_monthly_cost:,.2f}")

    return {
        'down_payment': down_payment,
        'loan_amount': loan_amount,
        'monthly_emi': monthly_emi,
        'total_loan_payments': total_loan_payments,
        'total_paid_during_loan': total_paid_during_loan,
        'battery_replacements_count': battery_replacements,
        'total_battery_replacement_cost': total_battery_replacement_cost,
        'annual_maintenance': annual_maintenance,
        'total_maintenance_25yr': total_maintenance_25yr,
        'total_25yr_cost': total_25yr_cost,
        'levelized_monthly_cost': levelized_monthly_cost,
        'loan_tenure_years': tenure_years,
        'npv_applied': use_npv
    }

def compute_biogas_costs(monthly_m3, category='Commercial', user_added_opex=0,
                         interest_rate=None, tenure_years=None):
    """
    Compute biogas monthly cost components and cost per primary kWh.
    - monthly_m3: biogas volume available per month
    - category: 'Commercial' or 'Domestic' to pull pricing from DB
    - user_added_opex: additional monthly operating cost provided by user
    """
    if monthly_m3 <= 0:
        logger = get_logger()
        logger.log_warning("Biogas cost calculation skipped - monthly_m3 <= 0")
        return {
            'feedstock_cost': 0,
            'maintenance_cost': 0,
            'capex_component': 0,
            'user_opex': user_added_opex,
            'total_monthly_cost': user_added_opex,
            'energy_per_m3': BIOGAS_ENERGY_PER_M3,
            'primary_energy_kwh': 0,
            'cost_per_kwh_primary': 0
        }

    feedstock_cost_per_m3 = db_helper.get_system_parameter('BIOGAS_FEEDSTOCK_COST_PER_M3', 0.0)
    
    # New Dynamic Logic using Loan & Capital Costs Table
    # 1. Determine System Size: Biogas plants are rated by daily gas production (m3/day)
    #    Assumption: monthly_m3 is total consumption, so daily needed = monthly / 30
    daily_capacity_m3 = monthly_m3 / 30.0 if monthly_m3 > 0 else 0
    
    # 2. Get Pricing Factors
    tech_data = db_helper.get_technology_pricing('Biogas')
    
    # 3. Calculate Capital Cost
    #    Cost = (Capacity * Cost/Unit) + Base Installation
    unit_cost = float(tech_data.get('capital_cost_per_unit') or 25000)
    base_cost = float(tech_data.get('installation_cost_base') or 5000)
    capital_cost = (daily_capacity_m3 * unit_cost) + base_cost
    
    # 4. Calculate Maintenance Cost
    #    Maintenance = (Capital Cost * Annual %) / 12
    #    Default to 2% (0.02) if not set
    maint_pct = float(tech_data.get('maintenance_annual_pct') or 0.02)
    maintenance_cost = (capital_cost * maint_pct) / 12.0

    if interest_rate is None:
        interest_rate = db_helper.get_system_parameter('BIOGAS_LOAN_INTEREST_RATE', 0.07)
    if tenure_years is None:
        tenure_years = db_helper.get_system_parameter('BIOGAS_LOAN_TENURE_YEARS', 5)

    capex_component = calculate_emi(capital_cost, interest_rate, tenure_years)
    feedstock_cost = feedstock_cost_per_m3 * monthly_m3

    total_monthly_cost = feedstock_cost + maintenance_cost + capex_component + user_added_opex
    primary_energy_kwh = monthly_m3 * BIOGAS_ENERGY_PER_M3
    cost_per_kwh_primary = total_monthly_cost / primary_energy_kwh if primary_energy_kwh > 0 else 0

    logger = get_logger()
    logger.log_subsection("BIOGAS COST COMPONENTS")
    logger.log_data("Inputs", {
        "monthly_m3": monthly_m3,
        "category": category,
        "user_added_opex": user_added_opex,
        "interest_rate": interest_rate,
        "tenure_years": tenure_years
    })
    logger.log_data("Pricing & Factors", {
        "feedstock_cost_per_m3": feedstock_cost_per_m3,
        "maintenance_cost": maintenance_cost,
        "capital_cost": capital_cost,
        "energy_per_m3": BIOGAS_ENERGY_PER_M3
    })
    logger.log_data("Outputs", {
        "feedstock_cost": feedstock_cost,
        "capex_component": capex_component,
        "total_monthly_cost": total_monthly_cost,
        "primary_energy_kwh": primary_energy_kwh,
        "cost_per_kwh_primary": cost_per_kwh_primary
    })

    return {
        'feedstock_cost': feedstock_cost,
        'maintenance_cost': maintenance_cost,
        'capex_component': capex_component,
        'user_opex': user_added_opex,
        'total_monthly_cost': total_monthly_cost,
        'energy_per_m3': BIOGAS_ENERGY_PER_M3,
        'primary_energy_kwh': primary_energy_kwh,
        'cost_per_kwh_primary': cost_per_kwh_primary,
        'capital_cost': capital_cost,
        'interest_rate': interest_rate,
        'tenure_years': tenure_years
    }

def calculate_fuel_emissions_and_costs(fuel_energy_dict, fuel_efficiency_dict, 
                                     fuel_cost_per_kwh_dict, emission_factors=None, emission_sources=None, institution_data=None):
    """
    Calculate emissions and costs for multiple fuels with proper accumulation
    """
    if emission_factors is None:
        emission_factors = EMISSION_FACTORS
    if emission_sources is None:
        emission_sources = EMISSION_SOURCES
    
    logger = get_logger()
    logger.log_subsection("MULTI-FUEL EMISSIONS & COSTS")
        
    total_emissions = 0
    total_cost = 0
    total_energy_delivered = 0
    fuel_breakdown = {}
    
    if institution_data is None:
        institution_data = {}
        
    working_days = institution_data.get('working_days', 30)
    monthly_factor = float(working_days) if working_days else 30.0
    for fuel, energy in fuel_energy_dict.items():
        if energy <= 0:
            continue
            
        efficiency = fuel_efficiency_dict.get(fuel, 1.0)
        cost_per_kwh = fuel_cost_per_kwh_dict.get(fuel, 0)
        emission_factor = emission_factors.get(fuel, 0)
        
        # Energy required accounting for efficiency
        energy_required = energy / efficiency if efficiency > 0 else energy
        
        # Calculate emissions (annual)
        daily_energy = energy_required / monthly_factor  

        annual_emissions = calculate_co2_emissions(daily_energy, emission_factor, institution_data)
        
        # Calculate cost (monthly)
        monthly_cost = energy_required * cost_per_kwh
        
        # Store breakdown
        fuel_breakdown[fuel] = {
            'energy_delivered': energy,
            'energy_required': energy_required,
            'efficiency': efficiency,
            'monthly_cost': monthly_cost,
            'annual_emissions': annual_emissions,
            'cost_per_kwh': cost_per_kwh,
            'percentage': 0,  # Will be calculated after
            'emission_source': emission_sources.get(fuel) if emission_sources else None
        }
        
        # Accumulate totals
        total_emissions += annual_emissions
        total_cost += monthly_cost
        total_energy_delivered += energy

        logger.log_calculation(
            f"Fuel: {fuel}",
            "efficiency & emission calc",
            {
                "gross_energy": f"{energy:.2f} kWh",
                "efficiency": f"{efficiency:.2f}",
                "energy_required": f"{energy_required:.2f} kWh",
                "cost_per_kwh": f"₹{cost_per_kwh:.2f}",
                "emission_factor": f"{emission_factor:.2f}"
            },
            f"₹{monthly_cost:.2f}/mo, {annual_emissions:.2f} kg CO2/yr"
        )
    
    # Calculate percentages
    for fuel in fuel_breakdown:
        fuel_breakdown[fuel]['percentage'] = (
            fuel_breakdown[fuel]['energy_delivered'] / total_energy_delivered * 100 
            if total_energy_delivered > 0 else 0
        )
        
        # Calculate quantity and unit based on fuel type
        energy_required = fuel_breakdown[fuel]['energy_required']
        quantity = 0
        unit = 'kWh'
        
        if fuel == 'LPG':
            # LPG: kWh -> kg
            quantity = energy_required / LPG_CALORIFIC_VALUE if LPG_CALORIFIC_VALUE > 0 else 0
            unit = 'kg'
        elif fuel == 'PNG':
            # PNG: kWh -> SCM
            quantity = energy_required / PNG_CALORIFIC_VALUE if PNG_CALORIFIC_VALUE > 0 else 0
            unit = 'SCM'
        elif fuel == 'Biogas':
            # Biogas: kWh -> m3
            quantity = energy_required / BIOGAS_ENERGY_PER_M3 if BIOGAS_ENERGY_PER_M3 > 0 else 0
            unit = 'm³'
        elif fuel == 'Grid electricity':
            # Electricity: kWh -> Units (1:1)
            quantity = energy_required
            unit = 'Units'
        elif fuel == 'Traditional Solid Biomass' or fuel == 'Improved Cookstove (Biomass)':
             # Biomass: kWh -> kg
             # Try to get biomass energy content, default to 4.5 kWh/kg if not found
             biomass_energy = db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5)
             quantity = energy_required / biomass_energy if biomass_energy > 0 else 0
             unit = 'kg'
        else:
            # Default fallback
            quantity = energy_required
            unit = 'kWh'
            
        fuel_breakdown[fuel]['quantity'] = quantity
        fuel_breakdown[fuel]['unit'] = unit

    logger.log_data("Fuel Breakdown Summary", fuel_breakdown)
    logger.log_result("Total Energy Delivered", f"{total_energy_delivered:.2f} kWh")
    logger.log_result("Total Monthly Cost", f"₹{total_cost:.2f}")
    logger.log_result("Total Annual Emissions", f"{total_emissions:.2f} kg CO₂/year")
    
    return {
        'total_annual_emissions': total_emissions,
        'total_monthly_cost': total_cost,
        'total_energy_delivered': total_energy_delivered,
        'fuel_breakdown': fuel_breakdown
    }

def calculate_alternatives(energy_data, household_data, kitchen_data):
    """Calculate costs and impacts for all fuel alternatives"""
    alternatives = {}

    # Load fuels from database instead of hard-coding
    fuel_list = db_helper.get_all_fuels(active_only=True)
    fuels = [f['fuel_name'] for f in fuel_list]
    logger = get_logger()
    logger.log_subsection("ALTERNATIVES (Residential)")
    logger.log_input("Monthly Energy (kWh)", energy_data.get('monthly_energy_kwh', 0))
    logger.log_data("Fuels Considered", fuels)

    for fuel in fuels:
        # Check for Solar + BESS willingness (Residential)
        if fuel == 'Solar + BESS':
            willingness = household_data.get('solar_willingness', 'No')
            if willingness != 'Yes':
                continue

        alternatives[fuel] = calculate_fuel_scenario(
            fuel, energy_data['monthly_energy_kwh'], household_data, kitchen_data, energy_data
        )

    return alternatives

def _get_cost_per_kwh_from_energy_data(fuel, energy_data):
    """Extract a cost_per_kwh for the given fuel from current energy data if available"""
    if not energy_data:
        return None

    fuel_details = energy_data.get('fuel_details', {})
    breakdown = fuel_details.get('fuel_breakdown') if isinstance(fuel_details, dict) else None

    if not breakdown or fuel not in breakdown or not isinstance(breakdown[fuel], dict):
        return None

    details = breakdown[fuel]

    # Prefer explicit cost_per_kwh
    cost_per_kwh = details.get('cost_per_kwh')
    if cost_per_kwh and cost_per_kwh > 0:
        return cost_per_kwh

    # Derive from monthly_cost and energy requirement/delivery if present
    monthly_cost = details.get('monthly_cost')
    energy_required = details.get('energy_required')
    energy_delivered = details.get('energy_delivered')

    if monthly_cost is not None:
        if energy_required and energy_required > 0:
            return monthly_cost / energy_required
        if energy_delivered and energy_delivered > 0:
            return monthly_cost / energy_delivered

    return None

def calculate_commercial_fuel_scenario(fuel, monthly_energy_kwh, institution_data, kitchen_data, energy_data=None):
    """Commercial-specific fuel scenario that respects commercial tariffs and current fuel pricing"""
    logger = get_logger()
    logger.log_subsection(f"COMMERCIAL FUEL SCENARIO: {fuel}")
    logger.log_input("Monthly Energy (kWh)", monthly_energy_kwh)
    
    # Get working_days
    working_days = institution_data.get('working_days', 30)
    monthly_factor = float(working_days) if working_days else 30.0
    
    efficiency = DEFAULT_EFFICIENCIES.get(fuel, 0.60) or 0.60
    energy_required = monthly_energy_kwh / efficiency if efficiency > 0 else monthly_energy_kwh

    # Try to reuse the pricing from the current setup
    cost_per_kwh = _get_cost_per_kwh_from_energy_data(fuel, energy_data)

    # Grid/LPG/PNG: compute cost directly with commercial pricing
    if fuel in ('Grid electricity', 'LPG', 'PNG'):
        if cost_per_kwh is None:
            if fuel == 'Grid electricity':
                tariff = (
                    institution_data.get('electricity_tariff')
                    or kitchen_data.get('electricity_tariff')
                    or db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.5)
                )
                cost_per_kwh = tariff
            elif fuel == 'LPG':
                # Get LPG price: session custom > system parameter
                _custom = institution_data.get('custom_fuel_prices', {})
                if _custom.get('LPG_unit_price'):
                    cylinder_price = float(_custom['LPG_unit_price'])
                else:
                    cylinder_price = db_helper.get_system_parameter('LPG_COMMERCIAL_CYLINDER_PRICE', None)
                    if cylinder_price is None:
                        cylinder_price = db_helper.get_system_parameter('LPG_COMMERCIAL_PRICE', 31060)
                cylinder_weight = db_helper.get_system_parameter('LPG_COMMERCIAL_CYLINDER_WEIGHT', 19.0)
                energy_per_cylinder = cylinder_weight * LPG_CALORIFIC_VALUE
                cost_per_kwh = cylinder_price / energy_per_cylinder if energy_per_cylinder > 0 else 0

            elif fuel == 'PNG':
                # ✅ NEW CODE: Use FuelCostCalculator
                from fuel_cost_standardizer import FuelCostCalculator
                cost_calculator = FuelCostCalculator(
                    db_helper,
                    institution_data=institution_data,
                    kitchen_data=kitchen_data
                )
                cost_per_kwh, source = cost_calculator.get_cost_per_kwh('PNG', energy_required=energy_required)
                




        monthly_cost = energy_required * cost_per_kwh

        # ✅ Calculate CO2 using centralized function with institution_data
        daily_energy = energy_required / monthly_factor
        # Honour session Grid CO₂ override for Grid electricity
        if fuel == 'Grid electricity':
            _cef_cfs = institution_data.get('custom_fuel_prices', {})
            emission_factor = float(_cef_cfs['Grid_emission_factor']) if _cef_cfs.get('Grid_emission_factor') is not None else EMISSION_FACTORS.get('Grid electricity', 0.65)
        else:
            emission_factor = EMISSION_FACTORS.get(fuel, 0.5)
        annual_co2 = calculate_co2_emissions(
            daily_energy,
            emission_factor,
            institution_data  # ✅ Pass institution_data for working_days
        )
        
        logger.log_data("Commercial Fuel Cost & Emission", {
            "efficiency": efficiency,
            "energy_required": energy_required,
            "cost_per_kwh": cost_per_kwh,
            "monthly_cost": monthly_cost,
            "annual_co2": annual_co2,
            "working_days": working_days
        })

        base_pm25 = PM25_BASE_EMISSIONS.get(fuel, 100)
        pm25_peak = calculate_pollutant_exposure(
            base_pm25,
            kitchen_data.get('kitchen_type', 'Open Kitchen'),
            kitchen_data.get('ventilation_quality', 'Average'),
            kitchen_data.get('cooking_hours_daily', 3.0)
        )
        health_risk_score = calculate_health_risk_score(
            pm25_peak,
            kitchen_data.get('cooking_hours_daily', 3.0),
            kitchen_data.get('sensitive_members', 1)
        )

        return {
            'fuel': fuel,
            'monthly_cost': monthly_cost,
            'capital_cost': 0,
            'efficiency': efficiency * 100,
            'annual_co2': annual_co2,
            'environmental_grade': get_environmental_grade(annual_co2),
            'pm25_peak': pm25_peak,
            'health_risk_score': health_risk_score,
            'health_risk_category': categorize_health_risk(health_risk_score),
            'cost_per_kwh': cost_per_kwh,
            'emission_source': EMISSION_SOURCES.get(fuel)
        }
    
    elif fuel == 'Biogas':
        monthly_m3 = energy_required / BIOGAS_ENERGY_PER_M3 if BIOGAS_ENERGY_PER_M3 > 0 else 0
        biogas_costs = compute_biogas_costs(monthly_m3, category='Commercial')
        monthly_cost = biogas_costs['total_monthly_cost']
        
        logger.log_data("Commercial Biogas Cost", {
            "monthly_m3": monthly_m3,
            "monthly_cost": monthly_cost,
            "cost_components": biogas_costs,
            "working_days": working_days
        })

        # ✅ Calculate CO2 using centralized function with institution_data
        daily_energy = energy_required / monthly_factor
        emission_factor = EMISSION_FACTORS.get('Biogas', 0.30)
        annual_co2 = calculate_co2_emissions(
            daily_energy, 
            emission_factor,
            institution_data  # ✅ Pass institution_data for working_days
        )

        base_pm25 = PM25_BASE_EMISSIONS.get(fuel, 50)
        pm25_peak = calculate_pollutant_exposure(
            base_pm25,
            kitchen_data.get('kitchen_type', 'Open Kitchen'),
            kitchen_data.get('ventilation_quality', 'Average'),
            kitchen_data.get('cooking_hours_daily', 3.0)
        )
        health_risk_score = calculate_health_risk_score(
            pm25_peak,
            kitchen_data.get('cooking_hours_daily', 3.0),
            kitchen_data.get('sensitive_members', 1)
        )

        return {
            'fuel': fuel,
            'monthly_cost': monthly_cost,
            'capital_cost': biogas_costs.get('capital_cost', 0),
            'efficiency': efficiency * 100,
            'annual_co2': annual_co2,
            'environmental_grade': get_environmental_grade(annual_co2),
            'pm25_peak': pm25_peak,
            'health_risk_score': health_risk_score,
            'health_risk_category': categorize_health_risk(health_risk_score),
            'cost_per_kwh': biogas_costs.get('cost_per_kwh_primary'),
            'emission_source': EMISSION_SOURCES.get(fuel),
            'cost_components': biogas_costs,
            'monthly_m3': monthly_m3
        }

    elif fuel == 'Traditional Solid Biomass':
        # ✅ Dedicated commercial Biomass handler — avoids residential /30 and missing institution_data
        district = institution_data.get('district', 'Thiruvananthapuram')
        # Get biomass cost: session custom > DB > fallback
        _custom = institution_data.get('custom_fuel_prices', {})
        if _custom.get('Biomass_unit_price'):
            biomass_cost_per_kg = float(_custom['Biomass_unit_price'])
        else:
            biomass_price_data = db_helper.get_fuel_unit_price(district, 'Traditional Solid Biomass', 'Commercial')
            biomass_cost_per_kg = float(
                biomass_price_data['unit_price']
                if biomass_price_data and biomass_price_data.get('unit_price') is not None
                else db_helper.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0)
            )
        biomass_energy_content = float(db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5))

        energy_required_gross = monthly_energy_kwh / efficiency if efficiency > 0 else monthly_energy_kwh
        monthly_kg = energy_required_gross / biomass_energy_content if biomass_energy_content > 0 else 0
        monthly_cost = monthly_kg * biomass_cost_per_kg

        # ✅ Use working_days (not hardcoded 30) and pass institution_data for correct annual days
        daily_energy = energy_required_gross / monthly_factor
        emission_factor = EMISSION_FACTORS.get('Traditional Solid Biomass', 0.4)
        annual_co2 = calculate_co2_emissions(daily_energy, emission_factor, institution_data)

        logger.log_data("Commercial Biomass Cost & Emission", {
            "district": district,
            "efficiency": efficiency,
            "energy_required_gross_kwh": energy_required_gross,
            "monthly_kg": monthly_kg,
            "biomass_cost_per_kg": biomass_cost_per_kg,
            "monthly_cost": monthly_cost,
            "annual_co2": annual_co2,
            "working_days": working_days
        })

        base_pm25 = PM25_BASE_EMISSIONS.get(fuel, 0.5)
        pm25_peak = calculate_pollutant_exposure(
            base_pm25,
            kitchen_data.get('kitchen_type', 'Open Kitchen'),
            kitchen_data.get('ventilation_quality', 'Average'),
            kitchen_data.get('cooking_hours_daily', 3.0)
        )
        health_risk_score = calculate_health_risk_score(
            pm25_peak,
            kitchen_data.get('cooking_hours_daily', 3.0),
            kitchen_data.get('sensitive_members', 1)
        )

        return {
            'fuel': fuel,
            'monthly_cost': monthly_cost,
            'capital_cost': 0,
            'efficiency': efficiency * 100,
            'annual_co2': annual_co2,
            'environmental_grade': get_environmental_grade(annual_co2),
            'pm25_peak': pm25_peak,
            'health_risk_score': health_risk_score,
            'health_risk_category': categorize_health_risk(health_risk_score),
            'cost_per_kwh': (monthly_cost / monthly_energy_kwh) if monthly_energy_kwh > 0 else 0,
            'emission_source': EMISSION_SOURCES.get(fuel)
        }

    elif fuel == 'Solar + BESS':
         # Delegate to residential logic but ensure commercial tariff is used for backup
        commercial_household = dict(institution_data or {})
        commercial_household.setdefault(
            'electricity_tariff',
            institution_data.get('electricity_tariff') or 
            db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.5)
        )
        # Ensure available_roof_area is mapped to solar_rooftop_area (if needed by residential logic fallback)
        # But actually residential logic looks at kitchen_data['roof_area_available']
        # Ensure kitchen_data has it
        if 'roof_area_available' not in kitchen_data and 'available_roof_area' in institution_data:
             kitchen_data['roof_area_available'] = institution_data['available_roof_area']

        result = calculate_fuel_scenario(fuel, monthly_energy_kwh, commercial_household, kitchen_data, energy_data)
        
        # Override tariff for backup cost if needed? 
        # Actually calculate_fuel_scenario uses household_data['electricity_tariff'], which we just set.
        # So it should be fine.
        return result

    # For other fuels, reuse the existing residential scenario logic with commercial defaults
    commercial_household = dict(institution_data or {})
    commercial_household.setdefault(
        'electricity_tariff',
        db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.5)
    )

    return calculate_fuel_scenario(fuel, monthly_energy_kwh, commercial_household, kitchen_data, energy_data)

def calculate_commercial_alternatives(energy_data, institution_data, kitchen_data):
    """Commercial variant of alternatives using commercial tariffs and current fuel pricing"""
    alternatives = {}

    monthly_energy_kwh = energy_data.get('monthly_energy_kwh', 0)

    fuel_list = db_helper.get_all_fuels(active_only=True)
    fuels = [f['fuel_name'] for f in fuel_list]

    for fuel in fuels:
        # Check for Solar + BESS willingness (Commercial)
        if fuel == 'Solar + BESS':
            willingness = institution_data.get('solar_willing', 'No')
            if willingness not in ['Yes', 'Maybe']:
                continue

        alternatives[fuel] = calculate_commercial_fuel_scenario(
            fuel, monthly_energy_kwh, institution_data, kitchen_data, energy_data
        )

    logger = get_logger()
    logger.log_subsection("ALTERNATIVES (Commercial)")
    logger.log_input("Monthly Energy (kWh)", monthly_energy_kwh)
    logger.log_data("Fuels Considered", fuels)

    return alternatives



def calculate_fuel_scenario(fuel, monthly_energy_kwh, household_data, kitchen_data, energy_data=None):
    """Calculate comprehensive metrics for a specific fuel"""
    logger = get_logger()
    logger.log_subsection(f"FUEL SCENARIO: {fuel}")
    logger.log_input("Monthly Energy (useful kWh)", monthly_energy_kwh)
    logger.log_data("Household Data (key fields)", {
        "electricity_tariff": household_data.get('electricity_tariff'),
        "loan_interest_rate": household_data.get('loan_interest_rate'),
        "loan_tenure": household_data.get('loan_tenure'),
        "lpg_subsidy": household_data.get('lpg_subsidy'),
        "roof_area": kitchen_data.get('roof_area_available')
    })
    efficiency = DEFAULT_EFFICIENCIES.get(fuel, 0.60)
    fuel_energy_required = monthly_energy_kwh / efficiency
    daily_fuel_energy = fuel_energy_required / 30
    biogas_costs = None
    logger.log_data("Baseline", {
        "efficiency": efficiency,
        "fuel_energy_required": fuel_energy_required,
        "daily_fuel_energy": daily_fuel_energy
    })

    # Cost calculation
    # Initialize levelized_monthly_cost (will be set for solar/bess)
    levelized_monthly_cost = None

    if fuel == 'Grid electricity':
        # Try to get cost_per_kwh from current energy_data (for consistency)
        cost_per_kwh = _get_cost_per_kwh_from_energy_data('Grid electricity', energy_data)
        
        if cost_per_kwh and cost_per_kwh > 0:
            # Use cost_per_kwh for consistency with current usage
            monthly_cost = fuel_energy_required * cost_per_kwh
        else:
            # Fallback: use household electricity tariff
            cost_per_kwh = household_data.get('electricity_tariff', 6.5)
            monthly_cost = fuel_energy_required * cost_per_kwh
        capital_cost = 0  # Induction stove cost
    elif fuel == 'Solar + BESS':
        # Convert useful energy to electricity requirement (induction cooking)
        # Solar+BESS powers induction stoves at ~90% efficiency
        induction_efficiency = DEFAULT_EFFICIENCIES.get('Grid electricity', 0.90)
        monthly_electricity_kwh = monthly_energy_kwh / induction_efficiency

        # Estimate meal energy distribution (typical patterns)
        # Breakfast: 21%, Lunch: 32%, Dinner: 40%, Snacks: 7%
        breakfast_energy = monthly_electricity_kwh * 0.21
        lunch_energy = monthly_electricity_kwh * 0.32
        dinner_energy = monthly_electricity_kwh * 0.40
        snacks_energy = monthly_electricity_kwh * 0.07

        # Get breakfast timing from kitchen data or default to 'late'
        breakfast_timing = kitchen_data.get('breakfast_timing', 'late')

        # Calculate Solar + BESS system
        bess_system = calculate_solar_with_bess_sizing(
            breakfast_energy=breakfast_energy,
            lunch_energy=lunch_energy,
            dinner_energy=dinner_energy,
            snacks_energy=snacks_energy,
            breakfast_timing=breakfast_timing,
            roof_area=kitchen_data.get('roof_area_available', 50)
        )

        capital_cost = bess_system['total_capital_cost']

        # Calculate 25-year levelized cost
        loan_pct = 80
        interest_rate = household_data.get('loan_interest_rate', 7) / 100
        tenure = household_data.get('loan_tenure', 5)

        levelized_costs = calculate_levelized_cost_25yr(
            capital_cost=capital_cost,
            loan_percentage=loan_pct,
            annual_interest_rate=interest_rate,
            tenure_years=tenure,
            solar_capacity_kw=bess_system['solar_capacity_kw'],
            battery_cost=bess_system['battery_cost'],
            use_npv=False
        )

        # Hardware Cost (Levelized)
        hardware_monthly_cost = levelized_costs['levelized_monthly_cost']

        # Grid Backup Cost
        grid_backup = bess_system.get('grid_backup', {})
        grid_backup_kwh_daily = grid_backup.get('needed_kwh_daily', 0)
        grid_backup_cost_monthly = grid_backup_kwh_daily * 30 * household_data.get('electricity_tariff', 6.5)

        # Total Monthly Cost
        monthly_cost = hardware_monthly_cost + grid_backup_cost_monthly
        levelized_monthly_cost = monthly_cost

        # Emissions: Solar (near zero) + Grid Backup
        # Honour session custom grid emission factor override
        _cef_s = household_data.get('custom_fuel_prices', {})
        grid_emission_factor = float(_cef_s['Grid_emission_factor']) if _cef_s.get('Grid_emission_factor') is not None else EMISSION_FACTORS.get('Grid electricity', 0.65)
        # BESS losses are already accounted for in the input monthly_electricity_kwh (via efficiency)
        # but emissions strictly come from the grid portion
        annual_backup_emissions = grid_backup_kwh_daily * 365 * grid_emission_factor
        
        # Base solar emissions (manufacturing etc - optional, usually considered 0 for direct op)
        # But we can add a small factor if needed. For now, assuming 0 operational emissions for solar part.
        annual_emissions = annual_backup_emissions
        
        # Override daily energy for environmental grade to reflect grid usage
        daily_carbon_energy = grid_backup_kwh_daily 

        logger.log_data("Solar+BESS Costs", {
            "capital_cost": capital_cost,
            "hardware_monthly_cost": hardware_monthly_cost,
            "grid_backup_cost_monthly": grid_backup_cost_monthly,
            "total_monthly_cost": monthly_cost,
            "bess_system": bess_system
        })

    elif fuel == 'Biogas':
        monthly_m3 = fuel_energy_required / BIOGAS_ENERGY_PER_M3 if BIOGAS_ENERGY_PER_M3 > 0 else 0
        biogas_costs = compute_biogas_costs(
            monthly_m3,
            category='Domestic',
            interest_rate=household_data.get('loan_interest_rate', 9) / 100,
            tenure_years=household_data.get('loan_tenure', 5)
        )
        monthly_cost = biogas_costs['total_monthly_cost']
        capital_cost = biogas_costs.get('capital_cost', 0)
        logger.log_data("Biogas Calculation", {
            "monthly_m3": monthly_m3,
            "monthly_cost": monthly_cost,
            "capital_cost": capital_cost
        })
    elif fuel == 'LPG':
        # LPG alternative: ALWAYS use cost_per_kwh for consistency with current usage calculation
        cylinders_needed = fuel_energy_required / LPG_ENERGY_PER_CYLINDER
        
        # Try to get cost_per_kwh from current energy_data (for consistency)
        cost_per_kwh = _get_cost_per_kwh_from_energy_data('LPG', energy_data)
        
        if cost_per_kwh and cost_per_kwh > 0:
            # Use cost_per_kwh for consistency with current usage
            monthly_cost = fuel_energy_required * cost_per_kwh
            cylinder_price = cost_per_kwh * LPG_ENERGY_PER_CYLINDER  # For logging
        else:
            # Fallback: session custom > database cylinder price
            _custom = household_data.get('custom_fuel_prices', {})
            if _custom.get('LPG_unit_price'):
                cylinder_price = float(_custom['LPG_unit_price'])
            else:
                lpg_price = db_helper.get_lpg_pricing(household_data.get('district', 'Thiruvananthapuram'), 'Domestic')
                cylinder_price = float(lpg_price.get('subsidized_price', 922)) if lpg_price else db_helper.get_system_parameter('LPG_DOMESTIC_PRICE', 922)
            if household_data.get('lpg_subsidy') == 'Yes':
                cylinder_price = max(0, cylinder_price - LPG_SUBSIDY_AMOUNT)
            cost_per_kwh = cylinder_price / LPG_ENERGY_PER_CYLINDER
            monthly_cost = fuel_energy_required * cost_per_kwh
                
        capital_cost = 0  # LPG stove cost
        logger.log_data("LPG Calculation", {
            "cylinders_needed": cylinders_needed,
            "cylinder_price": cylinder_price,
            "cost_per_kwh": cost_per_kwh,
            "monthly_cost": monthly_cost
        })
    elif fuel == 'PNG':
        # PNG cost calculation - use cost_per_kwh for consistency with current usage
        monthly_scm = fuel_energy_required / PNG_CALORIFIC_VALUE
        
        # Try to get cost_per_kwh from current energy_data (for consistency)
        cost_per_kwh = _get_cost_per_kwh_from_energy_data('PNG', energy_data)
        
        if cost_per_kwh and cost_per_kwh > 0:
            # Use cost_per_kwh for consistency with current usage
            monthly_cost = fuel_energy_required * cost_per_kwh
        else:
            # Fallback: session custom > database rate (variable cost only, no fixed charges)
            _custom = household_data.get('custom_fuel_prices', {})
            if _custom.get('PNG_unit_price'):
                png_rate = float(_custom['PNG_unit_price'])
            else:
                png_price_data = db_helper.get_png_pricing(household_data.get('district', 'All'), 'Domestic')
                png_rate = float(png_price_data['price_per_scm']) if png_price_data else db_helper.get_system_parameter('PNG_DOMESTIC_RATE', 54.0)
            monthly_cost = monthly_scm * png_rate
            cost_per_kwh = png_rate / PNG_CALORIFIC_VALUE
            
        capital_cost = 0  # PNG stove cost
        logger.log_data("PNG Calculation", {
            "monthly_scm": monthly_scm,
            "cost_per_kwh": cost_per_kwh,
            "monthly_cost": monthly_cost
        })
    else:  # Traditional Solid Biomass
        biomass_energy_content = db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5)
        # Get biomass cost: session custom > system parameter
        _custom = household_data.get('custom_fuel_prices', {})
        if _custom.get('Biomass_unit_price'):
            biomass_cost_per_kg = float(_custom['Biomass_unit_price'])
        else:
            biomass_cost_per_kg = db_helper.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0)
        monthly_kg = fuel_energy_required / biomass_energy_content
        monthly_cost = monthly_kg * biomass_cost_per_kg
        capital_cost = 0  # Traditional stove cost
        logger.log_data("Biomass Calculation", {
            "biomass_energy_content": biomass_energy_content,
            "monthly_kg": monthly_kg,
            "cost_per_kg": biomass_cost_per_kg,
            "monthly_cost": monthly_cost
        })
    
    # Emissions — for Grid electricity, honour session custom override
    if fuel == 'Grid electricity':
        _cef_h = household_data.get('custom_fuel_prices', {})
        emission_factor = float(_cef_h['Grid_emission_factor']) if _cef_h.get('Grid_emission_factor') is not None else EMISSION_FACTORS.get('Grid electricity', 0.65)
    else:
        emission_factor = EMISSION_FACTORS.get(fuel, 0.5)
    annual_co2 = calculate_co2_emissions(daily_fuel_energy, emission_factor)
    logger.log_result("Annual CO₂", f"{annual_co2:.2f} kg/year")
    
    # Health impact
    base_pm25 = PM25_BASE_EMISSIONS.get(fuel, 100)
    pm25_peak = calculate_pollutant_exposure(
        base_pm25, kitchen_data.get('kitchen_type', 'Open Kitchen'), 
        kitchen_data.get('ventilation_quality', 'Average'), 
        kitchen_data.get('cooking_hours_daily', 3.0)
    )
    health_risk_score = calculate_health_risk_score(
        pm25_peak, kitchen_data.get('cooking_hours_daily', 3.0), 
        kitchen_data.get('sensitive_members', 1)
    )
    logger.log_data("Health Impact", {
        "pm25_peak": pm25_peak,
        "health_risk_score": health_risk_score
    })
    
    result = {
        'fuel': fuel,
        'monthly_cost': monthly_cost,
        'capital_cost': capital_cost,
        'efficiency': efficiency * 100,
        'annual_co2': annual_co2,
        'environmental_grade': get_environmental_grade(annual_co2),
        'pm25_peak': pm25_peak,
        'health_risk_score': health_risk_score,
        'health_risk_category': categorize_health_risk(health_risk_score),
        'emission_source': EMISSION_SOURCES.get(fuel),
        'cost_components': biogas_costs if fuel == 'Biogas' else None
    }

    # Add levelized cost for solar/bess options
    if levelized_monthly_cost is not None:
        result['levelized_monthly_cost'] = levelized_monthly_cost
        result['emi_during_loan'] = emi if 'emi' in locals() else monthly_cost
        logger.log_result("Levelized Monthly Cost Applied", f"₹{levelized_monthly_cost:.2f}")

    # Add system specs for Solar + BESS
    if fuel == 'Solar + BESS' and 'bess_system' in locals():
        result['bess_system'] = bess_system
        result['levelized_costs'] = levelized_costs
        logger.log_data("Stored BESS System", bess_system)

    return result

def calculate_health_impact(energy_data, kitchen_data):
    """Calculate current health impact"""
    # Extract fuel type from nested structure
    fuel_details = energy_data.get('fuel_details', {})
    logger = get_logger()
    logger.log_subsection("HEALTH IMPACT")
    logger.log_data("Energy Data Fuel Details", fuel_details)
    
    fuel_type = 'LPG'
    base_pm25 = PM25_BASE_EMISSIONS.get(fuel_type, 100)
    pm25_components = []

    if fuel_details and isinstance(fuel_details, dict):
        fuel_breakdown = fuel_details.get('fuel_breakdown')

        if isinstance(fuel_breakdown, dict) and fuel_breakdown:
            total_energy = 0
            weighted_pm25 = 0
            for fuel_name, fuel_data in fuel_breakdown.items():
                if not isinstance(fuel_data, dict):
                    continue
                delivered_energy = (
                    fuel_data.get('energy_delivered')
                    or fuel_data.get('delivered_energy_kwh')
                    or 0
                )
                if delivered_energy <= 0:
                    continue
                fuel_pm25 = PM25_BASE_EMISSIONS.get(fuel_name, 100)
                total_energy += delivered_energy
                weighted_pm25 += delivered_energy * fuel_pm25
                pm25_components.append({
                    'fuel': fuel_name,
                    'energy_delivered': delivered_energy,
                    'pm25_base': fuel_pm25
                })
            if total_energy > 0:
                fuel_type = 'Weighted fuel mix'
                base_pm25 = weighted_pm25 / total_energy
        elif fuel_details.get('type') and fuel_details.get('type') not in ('Multiple', 'Mixed usage'):
            fuel_type = fuel_details['type']
            base_pm25 = PM25_BASE_EMISSIONS.get(fuel_type, 100)
        else:
            nested_entries = {
                fuel_name: fuel_data
                for fuel_name, fuel_data in fuel_details.items()
                if isinstance(fuel_data, dict)
            }
            if nested_entries:
                total_energy = 0
                weighted_pm25 = 0
                for fuel_name, fuel_data in nested_entries.items():
                    delivered_energy = (
                        fuel_data.get('energy_delivered')
                        or fuel_data.get('delivered_energy_kwh')
                        or 0
                    )
                    if delivered_energy <= 0:
                        continue
                    fuel_pm25 = PM25_BASE_EMISSIONS.get(fuel_name, 100)
                    total_energy += delivered_energy
                    weighted_pm25 += delivered_energy * fuel_pm25
                    pm25_components.append({
                        'fuel': fuel_name,
                        'energy_delivered': delivered_energy,
                        'pm25_base': fuel_pm25
                    })
                if total_energy > 0:
                    fuel_type = 'Weighted fuel mix'
                    base_pm25 = weighted_pm25 / total_energy
                else:
                    first_fuel = next(iter(nested_entries))
                    fuel_type = nested_entries[first_fuel].get('type', first_fuel)
                    base_pm25 = PM25_BASE_EMISSIONS.get(fuel_type, 100)

    logger.log_input("Derived Fuel Type", fuel_type)
    if pm25_components:
        logger.log_data("Weighted PM2.5 Components", pm25_components)
    
    pm25_peak = calculate_pollutant_exposure(
        base_pm25, kitchen_data.get('kitchen_type', 'Open Kitchen'), 
        kitchen_data.get('ventilation_quality', 'Average'), 
        kitchen_data.get('cooking_hours_daily', 3.0)
    )
    
    health_risk_score = calculate_health_risk_score(
        pm25_peak, kitchen_data.get('cooking_hours_daily', 3.0), 
        kitchen_data.get('sensitive_members', 1)
    )
    logger.log_data("Health Risk Result", {
        "pm25_peak": pm25_peak,
        "health_risk_score": health_risk_score,
        "category": categorize_health_risk(health_risk_score)
    })
    
    return {
        'pm25_peak': pm25_peak,
        'health_risk_score': health_risk_score,
        'health_risk_category': categorize_health_risk(health_risk_score)
    }

def generate_recommendations(alternatives, household_data, kitchen_data, energy_data):
    """Generate personalized recommendations"""
    logger = get_logger()
    logger.log_subsection("RECOMMENDATION ENGINE")
    scored_alternatives = []
    current_cost = energy_data['monthly_cost']
    priority = household_data.get('main_priority', 'balanced')
    logger.log_input("User Priority", priority)

    # Load weights from database based on user priority
    weight_config = db_helper.get_recommendation_weights(priority)
    selected_weights = {
        'health': weight_config['health'],
        'env': weight_config['environmental'],
        'econ': weight_config['economic'],
        'prac': weight_config['practicality']
    }
    logger.log_data("Selected Weights", selected_weights)
    
    for fuel, data in alternatives.items():
        logger.log_subsection(f"Scoring Fuel: {fuel}")
        # Health score — cut-points aligned with DB base scores (10/25/45/65/85)
        if data['health_risk_score'] <= 17:
            health_score = 100
        elif data['health_risk_score'] <= 35:
            health_score = 75
        elif data['health_risk_score'] <= 55:
            health_score = 40
        elif data['health_risk_score'] <= 75:
            health_score = 15
        else:
            health_score = 5
        
        if data['pm25_peak'] > 200:
            health_score -= 20
        
        # Environmental score
        if data['annual_co2'] < 200:
            env_score = 100
        elif data['annual_co2'] < 500:
            env_score = 80
        elif data['annual_co2'] < 1000:
            env_score = 60
        elif data['annual_co2'] < 2000:
            env_score = 40
        else:
            env_score = 10
        
        # Economic score
        monthly_savings = current_cost - data['monthly_cost']
        if current_cost > 0:
            savings_pct = (monthly_savings / current_cost) * 100
        else:
            savings_pct = 0

        if savings_pct > 50:
            econ_score = 100
        elif savings_pct > 20:
            econ_score = 80
        elif savings_pct > 0:
            econ_score = 60
        elif savings_pct > -20:
            econ_score = 40
        else:
            econ_score = 10

        # Practicality score
        prac_score = 100

        if fuel == 'Solar + BESS':
            # Needs adequate roof area
            if kitchen_data.get('roof_area_available', 0) < 40:
                prac_score -= 40
            # Bonus for energy independence
            prac_score += 10
        if fuel == 'Biogas':
            prac_score -= 30
        if fuel == 'Traditional Solid Biomass' and household_data.get('area_type') == 'Urban':
            prac_score -= 80
        # Calculate final weighted score
        score = (health_score * selected_weights['health'] +
                 env_score * selected_weights['env'] +
                 econ_score * selected_weights['econ'] +
                 prac_score * selected_weights['prac'])
        
        # Cap biomass score
        if fuel == 'Traditional Solid Biomass':
            score = min(score, 30)
        
        scored_alternatives.append((fuel, score, data))
        logger.log_data("Fuel Score Components", {
            "fuel": fuel,
            "health_score": health_score,
            "env_score": env_score,
            "econ_score": econ_score,
            "prac_score": prac_score,
            "final_score": score
        })
    
    # Sort by score
    scored_alternatives.sort(key=lambda x: x[1], reverse=True)
    logger.log_data("Top Recommendations", scored_alternatives[:3])
    
    return scored_alternatives[:3]  # Return top 3 recommendations

def cleanup_old_reports(max_files=10):
    """Clean up old PDF reports to manage storage"""
    try:
        reports_dir = 'reports'
        if not os.path.exists(reports_dir):
            pass
        
        # Get all PDF files with their creation times
        pdf_files = []
        if os.path.exists(reports_dir):
            for filename in os.listdir(reports_dir):
                if filename.endswith('.pdf'):
                    filepath = os.path.join(reports_dir, filename)
                    if os.path.isfile(filepath):
                        pdf_files.append((filepath, os.path.getctime(filepath)))
        
        # Sort by creation time (newest first)
        pdf_files.sort(key=lambda x: x[1], reverse=True)
        
        # Remove old files if we exceed max_files
        if len(pdf_files) > max_files:
            for filepath, _ in pdf_files[max_files:]:
                try:
                    os.remove(filepath)
                    get_logger().log_step(f"Cleaned up old report: {os.path.basename(filepath)}")
                except Exception as e:
                    get_logger().log_error(f"Failed to remove {filepath}: {e}")

        # Clean up expired analysis cache entries
        try:
            import time

            conn = db_helper.get_user_connection()
            conn.execute("DELETE FROM analysis_cache WHERE expires_at < ?", (time.time(),))
            conn.commit()
            conn.close()
        except Exception as e:
            get_logger().log_error(f"Cache cleanup error: {e}")
    except Exception as e:
        get_logger().log_error(f"Error during cleanup: {e}")
