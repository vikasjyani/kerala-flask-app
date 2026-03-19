
import sys
import os
from functools import lru_cache
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash, make_response, g
from flask_babel import Babel, _
from flask_compress import Compress
from flask_wtf.csrf import CSRFProtect, CSRFError
import json
import uuid
import datetime
import io

# Import from new modules
import helper
from helper import db_helper, cleanup_old_reports
import residential_cooking
import commercial_cooking
from pdf_generator import generate_report
from config import get_config
from debug_logger import get_logger, log_request_start, log_session_data
from error_handlers import (
    api_error_handler, web_error_handler, 
    ValidationError, DatabaseError, 
    safe_float, safe_int, validate_required
)

# Initialize Flask app
app = Flask(__name__)
Compress(app)
app.config.from_object(get_config())

# Initialize CSRF Protection
csrf = CSRFProtect(app)

# Add security headers
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Strict-Transport-Security only if HTTPS (checking scheme or config)
    # Using a safe default max-age
    if request.is_secure or app.config.get('SESSION_COOKIE_SECURE'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# Initialize Babel
babel = Babel(app)

# Translation setup
app.config['LANGUAGES'] = {
    'en': 'English',
    'ml': 'മലയാളം'
}

FALLBACK_DISTRICTS = [
    "Thiruvananthapuram",
    "Kollam",
    "Pathanamthitta",
    "Alappuzha",
    "Kottayam",
    "Idukki",
    "Ernakulam",
    "Thrissur",
    "Palakkad",
    "Malappuram",
    "Kozhikode",
    "Wayanad",
    "Kannur",
    "Kasaragod"
]

def normalize_language(language_code):
    """Normalize legacy and supported language codes."""
    if not language_code:
        return None
    if language_code == 'hi':
        return 'ml'
    if language_code in ('en', 'ml'):
        return language_code
    return None

def get_locale():
    # Check if language is explicitly set in session
    if 'language' in session:
        session_lang = normalize_language(session.get('language'))
        if session_lang:
            session['language'] = session_lang
            return session_lang
    # Otherwise try to match best language from request headers
    return request.accept_languages.best_match(['en', 'ml']) or 'en'

def localize_db_label(label_en, label_ml=None):
    """Pick localized DB label with Malayalam fallback behavior."""
    if get_locale() == 'ml' and label_ml and str(label_ml).strip():
        return label_ml
    return label_en

@lru_cache(maxsize=1)
def get_district_options_with_fallback():
    """Load district options, using a static fallback when reference DB access fails."""
    try:
        district_options = db_helper.get_district_options()
        if district_options:
            return district_options
    except Exception:
        pass

    return [{'value': d, 'label_en': d, 'label_ml': None} for d in FALLBACK_DISTRICTS]

def clear_application_journey():
    """Clear application journey state without wiping unrelated session keys.

    Must be called at every flow entry point:
      - index()                 — home page (already done)
      - commercial_selection()  — start of commercial flow
      - household_profile() GET — if switching from commercial to residential

    Keys preserved across clear: 'language' (UI locale).
    """
    session_keys = (
        # Flow discriminator
        'flow_type',
        # Residential keys
        'household_id',
        'household_data',
        'kitchen_data',
        'res_energy_data',       # namespaced residential energy result
        'analysis_result',
        'residential_analysis_result',
        'residential_analysis_cache_key',
        # Commercial keys
        'institution_data',
        'commercial_analysis_id',
        'com_energy_data',       # namespaced commercial energy result
        'commercial_analysis_result',
        'commercial_analysis_cache_key',
        # Generic / legacy keys (clean up old browser cookies that predate namespacing)
        'energy_data',
        'analysis_cache_key',
        # Feedback (cleared after submission)
        'feedback_submitted',
        'schemes_selected',
        'solar_scheme',
        'png_scheme',
        'ujjwala_scheme',
        'allow_contact',
    )
    for key in session_keys:
        session.pop(key, None)

def build_analysis_result(current, alternatives, health_impact, recommendations):
    """Build the canonical analysis payload shared by pages, APIs and reports."""
    return {
        'current': current or {},
        'alternatives': alternatives or {},
        'health_impact': health_impact or {},
        'recommendations': recommendations or []
    }

def save_analysis_result_to_cache(analysis_result, analysis_type):
    """Persist large analysis payloads server-side and store only cache keys in session."""
    if analysis_type == 'commercial':
        entity_id = session.get('commercial_analysis_id', 'unknown')
        specific_cache_session_key = 'commercial_analysis_cache_key'
        legacy_session_key = 'commercial_analysis_result'
    else:
        entity_id = session.get('household_id', 'unknown')
        specific_cache_session_key = 'residential_analysis_cache_key'
        legacy_session_key = 'residential_analysis_result'

    cache_key = f"analysis_{entity_id}"
    db_helper.save_analysis_cache(cache_key, analysis_result)
    # Write ONLY the type-specific key — never the generic 'analysis_cache_key' so that
    # a commercial and a residential result cannot overwrite each other in the same cookie.
    session[specific_cache_session_key] = cache_key
    session.pop(legacy_session_key, None)
    session.pop('analysis_result', None)
    return cache_key

def load_analysis_result_from_cache(analysis_type=None):
    """Load cached analysis payload using type-specific or generic cache key."""
    cache_key = None

    if analysis_type == 'commercial':
        cache_key = session.get('commercial_analysis_cache_key')
    elif analysis_type == 'residential':
        cache_key = session.get('residential_analysis_cache_key')

    if not cache_key:
        # Fallback: derive cache key from flow_type so the generic key can no longer
        # cause cross-flow bleed.  Old cookies that still carry 'analysis_cache_key'
        # are NOT used here; they will be cleared by clear_application_journey().
        flow = session.get('flow_type')
        if flow == 'commercial':
            cache_key = session.get('commercial_analysis_cache_key')
        elif flow == 'residential':
            cache_key = session.get('residential_analysis_cache_key')

    return db_helper.load_analysis_cache(cache_key) if cache_key else None

def resolve_annual_emissions(data):
    """Read annual emissions from any supported payload shape."""
    if not isinstance(data, dict):
        return 0
    return (
        data.get('annual_emissions')
        or data.get('annual_co2')
        or data.get('annual_co2_kg')
        or data.get('annual_emissions_kg')
        or 0
    )

babel.init_app(app, locale_selector=get_locale)

@app.context_processor
def inject_template_context():
    district_options = get_district_options_with_fallback()
    return {
        'get_locale': get_locale,
        'LANGUAGES': app.config['LANGUAGES'],
        '_': _,
        'districts': [d['value'] for d in district_options],
        'district_options': district_options,
        'localize_db_label': localize_db_label
    }

@app.template_filter('moment')
def moment_filter():
    """Template filter to get current datetime formatted like moment.js"""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

@app.template_global()
def moment():
    """Template global function to get current datetime"""
    class MomentObject:
        def format(self, format_str):
            # Convert moment.js format to Python strftime format
            format_str = format_str.replace('YYYY', '%Y').replace('MM', '%m').replace('DD', '%d').replace('HH', '%H').replace('mm', '%M')
            return datetime.datetime.now().strftime(format_str)
    return MomentObject()

# Add custom filter for currency formatting
@app.template_filter('currency')
def currency_filter(value):
    try:
        return "₹{:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return value

# Ensure directories exist
os.makedirs('uploads', exist_ok=True)
os.makedirs('reports', exist_ok=True)
# Create fonts directory for multilingual support
os.makedirs('fonts', exist_ok=True)

# Connection cleanup
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# =================================================================
# ROUTES
# =================================================================

@app.route('/')
def index():
    """Landing page"""
    clear_application_journey()
    return render_template('index.html')

@app.route('/info')
def info():
    """Information and methodology page"""
    return render_template('info.html')

@app.route('/contact_us')
def contact_us():
    """Contact Us page"""
    return render_template('contact_us.html')


@app.route('/analysis_selection')
def analysis_selection():
    """Select between Residential and Commercial analysis"""
    return render_template('analysis_selection.html')

@app.route('/set_language/<language>')
def set_language(language):
    """Set the session language"""
    normalized = normalize_language(language)
    if normalized:
        session['language'] = normalized
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Unsupported language'}), 400

# =================================================================
# RESIDENTIAL ROUTES
# =================================================================

@app.route('/household_profile', methods=['GET', 'POST'])
def household_profile():
    """Household profile input form"""
    if request.method == 'POST':
        return redirect(url_for('submit_household'))

    # If user arrives at the residential entry from a previous commercial
    # journey (without going via /), clear all stale commercial keys.
    if session.get('flow_type') == 'commercial':
        clear_application_journey()

    household_data = session.get('household_data') or {}
    # Get default electricity tariff from database (avoid hardcoded value in template)
    default_electricity_rate = db_helper.get_system_parameter('ELECTRICITY_RESIDENTIAL_RATE', None)
    if not default_electricity_rate:
        default_electricity_rate = 6.50  # Log warning but allow fallback for UI
    return render_template('household_profile.html', 
                          household_data=household_data,
                          default_electricity_rate=default_electricity_rate)

@app.route('/submit_household', methods=['POST'])
def submit_household():
    """Process household profile submission"""
    try:
        # Handle both JSON and Form data
        if request.is_json:
            data = request.json
        else:
            data = request.form

        # Extract form data
        household_data = {
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'district': data.get('district'),
            'area_type': data.get('area_type'),
            'household_size': int(data.get('household_size', 4)),
            'monthly_income': data.get('monthly_income'),
            'ration_card': data.get('ration_card'),
            'lpg_subsidy': data.get('lpg_subsidy', 'No'),
            'electricity_tariff': float(data.get('electricity_tariff', 6.5)),
            'loan_interest_rate': float(data.get('loan_interest_rate', 7.0)),
            'loan_tenure': int(data.get('loan_tenure', 5)),
            'main_priority': data.get('main_priority', 'balanced'),
            'solar_willingness': data.get('solar_willingness', 'No'),
            'solar_rooftop_area': float(data.get('solar_rooftop_area', 0) or 0),
            'consent_given': True if data.get('consent') == 'on' or data.get('consent') is True else False
        }
        
        # Save to database
        household_id = helper.save_household_data(household_data)
        
        # Store in session — tag this as a residential flow
        session['flow_type'] = 'residential'
        session['household_id'] = household_id
        session['household_data'] = household_data
        session.pop('kitchen_data', None)
        session.pop('res_energy_data', None)
        
        if request.is_json:
            return jsonify({'status': 'success', 'redirect': url_for('energy_calculation')})
        else:
            return redirect(url_for('energy_calculation'))
        
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error in submit_household: {e}")
        if request.is_json:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        else:
            flash(_('An error occurred. Please try again.'), 'error')
            return redirect(url_for('household_profile'))

@app.route('/kitchen_profile', methods=['GET', 'POST'])
def kitchen_profile():
    """Kitchen profile input form with scenario selection"""
    if 'household_id' not in session:
        return redirect(url_for('household_profile'))
    if 'res_energy_data' not in session:
        return redirect(url_for('energy_calculation'))

    if request.method == 'POST':
        return redirect(url_for('submit_kitchen'))
    
    # Get residential kitchen scenarios for template
    scenarios = []
    for name, data in helper.RESIDENTIAL_KITCHEN_SCENARIOS.items():
        scenarios.append({
            'scenario_name': name,
            'scenario_name_ml': data['name_ml'],
            'description': data['description_en'],
            'health_risk_category': data['risk'],
            'combined_factor': data['factor'],
            'risk_color': helper.RISK_STYLES[data['risk']]['badge'],
            'risk_icon': helper.RISK_STYLES[data['risk']]['icon']
        })
    
    return render_template('kitchen_profile.html', scenarios=scenarios)

@app.route('/submit_kitchen', methods=['POST'])
def submit_kitchen():
    """Process kitchen profile submission with scenario"""
    try:
        # Handle both JSON and Form data
        if request.is_json:
            data = request.json
        else:
            data = request.form

        household_data = session.get('household_data', {})

        kitchen_data = {
            'kitchen_scenario': data.get('kitchen_scenario'),  # NEW: single scenario field
            'cooking_hours_daily': float(data.get('cooking_hours_daily', 3)),
            'sensitive_members': int(data.get('sensitive_members', 0)),
            'roof_area_available': float(data.get('roof_area_available', household_data.get('solar_rooftop_area', 0)) or 0),
            'breakfast_timing': data.get('breakfast_timing', 'late'),
            'budget_preference': data.get('budget_preference'),
            # Keep old fields for backward compatibility with existing database
            'kitchen_type': data.get('kitchen_scenario', ''),  
            'ventilation_quality': 'Average'
        }
        
        session['kitchen_data'] = kitchen_data
        
        if request.is_json:
            return jsonify({'status': 'success', 'redirect': url_for('analysis')})
        else:
            return redirect(url_for('analysis'))
        
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error in submit_kitchen: {e}")
        if request.is_json:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        else:
            flash(_('An error occurred. Please try again.'), 'error')
            return redirect(url_for('kitchen_profile'))


@app.route('/energy_calculation')
def energy_calculation():
    """Energy calculation page - select method"""
    if 'household_id' not in session:
        return redirect(url_for('household_profile'))
    
    logger = get_logger()
    logger.log_subsection("LOAD ENERGY CALCULATION PAGE")
    logger.log_data("Session Household Data", session.get('household_data', {}))
    
    # Fetch dishes for the dropdowns
    dishes_list = db_helper.get_all_dishes(dish_type='residential')
    logger.log_result("Residential Dishes Loaded", len(dishes_list))
    
    # Group dishes by category for template rendering (full objects)
    dishes_by_category = {}
    # Also create simple structure for JS (just names)
    dish_data = {}
    # Track unique dish names per category to avoid duplicates
    unique_dish_names = {}

    for dish in dishes_list:
        category = dish['category_name']
        if category not in dishes_by_category:
            dishes_by_category[category] = []
            dish_data[category] = []
            unique_dish_names[category] = set()

        dishes_by_category[category].append(dish)

        name = dish['dish_name']
        if name not in unique_dish_names[category]:
            unique_dish_names[category].add(name)
            # Include is_veg status in dish_data for frontend
            dish_data[category].append({
                'name': name,
                'name_ml': dish.get('dish_name_ml'),
                'display_name': localize_db_label(name, dish.get('dish_name_ml')),
                'is_veg': dish.get('is_veg', 'yes')  # Default to 'yes' if not specified
            })
        
    # Get available fuels
    fuels = db_helper.get_all_fuels(active_only=True)
    available_fuels = [f['fuel_name'] for f in fuels]
    fuel_label_map = {
        f['fuel_name']: localize_db_label(f['fuel_name'], f.get('fuel_name_ml'))
        for f in fuels
    }
    logger.log_data("Available Fuels", available_fuels)
    
    # Check if dishes are available
    dishes_available = len(dishes_list) > 0
    
    # Get pricing data from database for template (avoid hardcoded JS values)
    household_data = session.get('household_data', {})
    # Only pass energy_data for pre-fill if it has a known calculation_method.
    # Prevents dish-based values pre-filling consumption fields and vice-versa.
    _raw_energy = session.get('res_energy_data', {})
    energy_data = _raw_energy if _raw_energy.get('calculation_method') in ('consumption_based', 'dish_based') else {}
    electricity_tariff = household_data.get('electricity_tariff') or db_helper.get_system_parameter('ELECTRICITY_RESIDENTIAL_RATE', 6.50)
    png_price_data = db_helper.get_png_pricing(district='All', category='Domestic')
    if not png_price_data:
        # Log warning - database pricing missing
        png_rate = db_helper.get_system_parameter('PNG_DOMESTIC_RATE', 54.0)
    else:
        png_rate = float(png_price_data['price_per_scm'])
    lpg_price_data = db_helper.get_lpg_pricing(household_data.get('district', 'Thiruvananthapuram'), 'Domestic')
    if not lpg_price_data:
        # Fallback to system parameter
        lpg_cylinder_price = db_helper.get_system_parameter('LPG_DOMESTIC_PRICE', 850)
    else:
        lpg_cylinder_price = float(lpg_price_data.get('subsidized_price', lpg_price_data.get('non_subsidized_price', 850)))
    
    return render_template('energy_calculation.html', 
                          dishes_by_category=dishes_by_category,
                          dish_data=dish_data,
                          energy_data=energy_data,
                          fuels=fuels,
                          available_fuels=available_fuels,
                          fuel_label_map=fuel_label_map,
                          dishes_available=dishes_available,
                          electricity_tariff=electricity_tariff,
                          png_rate=png_rate,
                          lpg_cylinder_price=lpg_cylinder_price,
                          # Efficiency factors and calorific values from database
                          lpg_efficiency=helper.DEFAULT_EFFICIENCIES.get('LPG', 0.60),
                          png_efficiency=helper.DEFAULT_EFFICIENCIES.get('PNG', 0.70),
                          electricity_efficiency=helper.DEFAULT_EFFICIENCIES.get('Grid electricity', 0.90),
                          biomass_efficiency=helper.DEFAULT_EFFICIENCIES.get('Traditional Solid Biomass', 0.15),
                          lpg_calorific_value=helper.LPG_CALORIFIC_VALUE,
                          lpg_cylinder_weight=helper.LPG_CYLINDER_WEIGHT,
                          png_calorific_value=helper.PNG_CALORIFIC_VALUE,
                          biomass_energy_content=db_helper.get_system_parameter('BIOMASS_ENERGY_CONTENT', 4.5),
                          biomass_cost_per_kg=db_helper.get_system_parameter('BIOMASS_DEFAULT_COST', 5.0),
                          grid_emission_factor=helper.EMISSION_FACTORS.get('Grid electricity', 0.65),
                          grid_emission_adjustment=db_helper.get_system_parameter('GRID_EMISSION_ADJUSTMENT_FACTOR', 0.9),
                          household_data=household_data)

@app.route('/get_dishes/<category>')
def get_dishes(category):
    """API to get dishes by category"""
    dishes = db_helper.get_dishes_by_category(category)
    return jsonify(dishes)

@app.route('/calculate_consumption', methods=['POST'])
def calculate_consumption():
    """Handle energy calculation (both consumption-based and dish-based)"""
    # Determine if this is a JSON request (AJAX) or form request
    is_json_request = request.is_json or request.headers.get('Content-Type') == 'application/json'
    
    # Get form data from JSON or form
    if is_json_request:
        form_data = request.json
    else:
        form_data = request.form

    import os
    if os.environ.get("FLASK_ENV", "development") != "production":
        log_request_start(request.path, request.method, {
            k: v for k, v in dict(form_data).items()
            if k not in ('name', 'email', 'phone', 'password')
        })
        log_session_data(session)
    logger = get_logger()
    
    try:
        calc_method = form_data.get('calculation_method')
        logger.log_input("Calculation Method", calc_method)
        
        # Clear previous res_energy_data to ensure fresh calculation.
        # Fixes: old string was 'consumption' vs stored value 'consumption_based' — always triggered.
        # Also check top-level key first (set by engine), fall back to nested fuel_details key.
        old_energy_data = session.pop('res_energy_data', None)
        if old_energy_data:
            old_method = (
                old_energy_data.get('calculation_method')
                or old_energy_data.get('fuel_details', {}).get('calculation_method', 'consumption_based')
            )
            new_method = 'dish_based' if calc_method == 'dish' else 'consumption_based'
            if old_method != new_method:
                logger.log_step(f"Method switch detected: {old_method} → {new_method}. Cleared old data.")
        
        household_data = session.get('household_data', {})
        kitchen_data = session.get('kitchen_data', {})
        household_id = session.get('household_id')
        
        if calc_method == 'consumption':
            result = residential_cooking.calculate_consumption_based(
                form_data, household_data, kitchen_data, household_id
            )
        else:
            result = residential_cooking.calculate_dish_based(
                form_data, household_data, kitchen_data, household_id, 
                language=session.get('language', 'en')
            )
            
        if result.get('status') == 'error':
            error_msg = result.get('message', 'Calculation failed')
            if is_json_request:
                return jsonify({'status': 'error', 'message': error_msg}), 400
            else:
                flash(error_msg, 'error')
                return redirect(url_for('energy_calculation'))
            
        # Store result in session under the residential namespace key
        session['res_energy_data'] = result
        logger.log_success("Residential calculation completed")
        logger.log_data("Residential Energy Data Stored in Session", result)
        
        if is_json_request:
            return jsonify({'status': 'success', 'redirect': url_for('kitchen_profile')})
        else:
            return redirect(url_for('kitchen_profile'))
        
    except Exception as e:
        logger.log_error(f"Error in calculate_consumption: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        error_msg = str(e) if is_json_request else _('An error occurred during calculation. Please try again.')
        
        if is_json_request:
            return jsonify({'status': 'error', 'message': error_msg}), 500
        else:
            flash(_('An error occurred during calculation. Please try again.'), 'error')
            return redirect(url_for('energy_calculation'))

@app.route('/analysis')
def analysis():
    """Display analysis results"""
    if 'res_energy_data' not in session:
        return redirect(url_for('energy_calculation'))
    if 'kitchen_data' not in session:
        return redirect(url_for('kitchen_profile'))

    household_data = session.get('household_data', {})
    kitchen_data = session.get('kitchen_data', {})
    energy_data = session.get('res_energy_data', {})
    household_id = session.get('household_id')
    
    # Calculate alternatives
    alternatives = helper.calculate_alternatives(energy_data, household_data, kitchen_data)
    
    # Calculate health impact
    health_impact = helper.calculate_health_impact(energy_data, kitchen_data)
    
    # Generate recommendations
    recommendations = helper.generate_recommendations(alternatives, household_data, kitchen_data, energy_data)
    
    # Save recommendations to database
    if household_id:
        helper.save_recommendations(household_id, recommendations)
    
    # Prepare complete analysis result
    analysis_result = build_analysis_result(energy_data, alternatives, health_impact, recommendations)
    save_analysis_result_to_cache(analysis_result, 'residential')

    logger = get_logger()
    logger.log_subsection("RENDER RESIDENTIAL ANALYSIS")
    logger.log_data("Current Energy Data", energy_data)
    logger.log_data("Alternatives Summary", alternatives)
    logger.log_data("Health Impact", health_impact)
    logger.log_data("Recommendations", recommendations)
    
    return render_template('analysis.html', 
                          analysis=analysis_result,
                          household=household_data)

# =================================================================
# FEEDBACK ROUTES
# =================================================================

@app.route('/feedback')
def feedback():
    """Show feedback form with user data and government schemes"""
    # Get user data from session to pre-fill form
    household_data = session.get('household_data', {})
    institution_data = session.get('institution_data', {})
    
    # Determine which type of analysis (residential or commercial)
    is_commercial = 'institution_data' in session
    
    if is_commercial:
        user_name = institution_data.get('contact_person', '')
        user_email = institution_data.get('email', '')
        user_phone = institution_data.get('phone', '')
    else:
        user_name = household_data.get('name', '')
        user_email = household_data.get('email', '')
        user_phone = household_data.get('phone', '')
    
    return render_template('feedback.html',
                          user_name=user_name,
                          user_email=user_email,
                          user_phone=user_phone,
                          is_commercial=is_commercial)

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    """Process feedback submission with government scheme preferences"""
    try:
        # Determine entity type and ID
        is_commercial = 'institution_data' in session
        entity_type = 'institution' if is_commercial else 'household'
        entity_id = session.get('commercial_analysis_id') if is_commercial else session.get('household_id')
        
        if not entity_id:
            flash(_('Session expired. Please start a new analysis.'), 'error')
            return redirect(url_for('index'))
        
        # Collect feedback data
        feedback_data = {
            'entity_id': entity_id,
            'entity_type': entity_type,
            'name': request.form.get('name', ''),
            'email': request.form.get('email', ''),
            'phone': request.form.get('phone', ''),
            'png_scheme_interested': request.form.get('png_scheme_interested') == '1',
            'solar_scheme_interested': request.form.get('solar_scheme_interested') == '1',
            'ujjwala_scheme_interested': request.form.get('ujjwala_scheme_interested') == '1',
            'allow_authority_contact': request.form.get('allow_authority_contact') == '1',
            'feedback_text': request.form.get('feedback_text', '')
        }
        
        # Save to database
        helper.save_user_feedback(feedback_data)

        schemes_selected = any([
            feedback_data['png_scheme_interested'],
            feedback_data['solar_scheme_interested'],
            feedback_data['ujjwala_scheme_interested']
        ])

        # End the journey without dropping unrelated session keys.
        clear_application_journey()

        # Store success flags for the confirmation page
        session['feedback_submitted'] = True
        session['schemes_selected'] = schemes_selected
        session['solar_scheme'] = feedback_data['solar_scheme_interested']
        session['png_scheme'] = feedback_data['png_scheme_interested']
        session['ujjwala_scheme'] = feedback_data['ujjwala_scheme_interested']
        session['allow_contact'] = feedback_data['allow_authority_contact']

        return redirect(url_for('feedback_success'))
        
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error submitting feedback: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        flash(_('An error occurred while submitting feedback. Please try again.'), 'error')
        return redirect(url_for('feedback'))

@app.route('/feedback_success')
def feedback_success():
    """Show feedback submission success page"""
    if not session.get('feedback_submitted'):
        # Redirect to home if accessed directly without submitting feedback
        return redirect(url_for('index'))
    
    # Get scheme selection data for display
    schemes_selected = session.get('schemes_selected', False)
    solar_scheme = session.get('solar_scheme', False)
    png_scheme = session.get('png_scheme', False)
    ujjwala_scheme = session.get('ujjwala_scheme', False)
    allow_contact = session.get('allow_contact', False)
    
    return render_template('feedback_success.html',
                          schemes_selected=schemes_selected,
                          solar_scheme=solar_scheme,
                          png_scheme=png_scheme,
                          ujjwala_scheme=ujjwala_scheme,
                          allow_contact=allow_contact)

# =================================================================
# REPORT GENERATION ROUTES
# =================================================================

@app.route('/download_report')
def download_report():
    """Generate and download comprehensive PDF report"""
    try:
        # Determine analysis type from query param or session
        req_type = request.args.get('type')

        if req_type == 'commercial':
            analysis_data = load_analysis_result_from_cache('commercial')
            analysis_type = 'commercial'
        elif req_type == 'residential':
            analysis_data = load_analysis_result_from_cache('residential')
            analysis_type = 'residential'
        else:
            analysis_data = load_analysis_result_from_cache()
            is_commercial = 'institution_data' in session
            analysis_type = 'commercial' if is_commercial else 'residential'

        if not analysis_data:
            flash(_('No analysis data available. Please complete an analysis first.'), 'error')
            return redirect(url_for('index'))
            
        # Determine is_commercial for filename
        is_commercial = (analysis_type == 'commercial')
        
        # Gather all required data — pick the namespaced energy key that matches this report type.
        energy_key = 'com_energy_data' if is_commercial else 'res_energy_data'
        user_data = {
            'household_data': session.get('household_data', {}),
            'institution_data': session.get('institution_data', {}),
            'kitchen_data': session.get('kitchen_data', {}),
            'energy_data': session.get(energy_key, {})
        }
        report_locale = get_locale()
        
        # Generate PDF report
        pdf_buffer = generate_report(analysis_type, analysis_data, user_data, locale=report_locale)
        
        # Prepare filename
        entity_name = 'Commercial' if is_commercial else session.get('household_data', {}).get('name', 'Household')
        # Sanitize entity name for filename
        safe_entity_name = "".join([c for c in entity_name if c.isalnum() or c in (' ', '_', '-')]).strip().replace(' ', '_')
        filename = f"Cooking_Energy_Report_{safe_entity_name}_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
        
        # Send file
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error generating report: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        flash(_('An error occurred while generating the report. Please try again.'), 'error')
        return redirect(url_for('analysis') if 'household_data' in session else url_for('index'))

# =================================================================
# COMMERCIAL ROUTES
# =================================================================

@app.route('/commercial_selection')
def commercial_selection():
    """Commercial analysis landing page with institution profile"""
    # Clear any previous journey (residential or commercial) so old session
    # keys never bleed into this new commercial flow.
    clear_application_journey()
    try:
        # Fetch institution types and filter to allowed 5
        all_institutions = db_helper.get_all_institution_types()
        allowed_types = ['School', 'Anganwadi', 'Hotel', 'Factory', 'Community Kitchen']
        institutions = [i for i in all_institutions if i.get('institution_name') in allowed_types]
        
        # Get districts
        districts = db_helper.get_districts()
        
        # Get default electricity rate from database
        default_electricity_rate = db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.50)
        
        return render_template('commercial_selection.html',
                             institutions=institutions,
                             districts=districts,
                             default_electricity_rate=default_electricity_rate)
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error in commercial_selection: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        return render_template('error.html', error_message=str(e))

@app.route('/commercial_institution_profile', methods=['POST'])
def commercial_institution_profile():
    logger = get_logger()
    logger.log_step("DEBUG: /commercial_institution_profile POST")
    """Process commercial institution profile form with enhanced fields"""
    try:
        institution_data = {
            'institution_type': request.form.get('institution_type'),
            'institution_name': request.form.get('institution_name'),
            'contact_person': request.form.get('contact_person'),
            'email': request.form.get('email', ''),
            'phone': request.form.get('phone', ''),
            'country_code': request.form.get('country_code', '+91'),
            'address': request.form.get('address', ''),  # NEW
            'district': request.form.get('district'),
            'area_type': request.form.get('area_type'),
            'servings_per_day': int(request.form.get('servings_per_day') or 100),
            'working_days': int(request.form.get('working_days') or 26),
            'electricity_tariff': float(request.form.get('electricity_tariff') or db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.50)),  # From DB
            'solar_willing': request.form.get('solar_willing', 'No'),  # NEW
            'available_roof_area': float(request.form.get('available_roof_area') or 0),  # NEW
            'budget': request.form.get('budget', '')  # NEW
        }
        
        if not institution_data['institution_type'] or not institution_data['institution_name']:
            flash('Please provide institution type and name', 'error')
            return redirect(url_for('commercial_selection'))
        
        # Save to database
        institution_id = helper.save_institution_data(institution_data)
        
        # Tag this as a commercial flow
        session['flow_type'] = 'commercial'
        session['institution_data'] = institution_data
        session['commercial_analysis_id'] = institution_id
        
        return redirect(url_for('commercial_kitchen_profile'))
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"ERROR in commercial_institution_profile: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        flash('Error processing institution profile', 'error')
        return redirect(url_for('commercial_selection'))

@app.route('/commercial/kitchen-profile', methods=['GET'])
def commercial_kitchen_profile():
    """Commercial kitchen profile input form with scenario selection"""
    if 'institution_data' not in session:
        return redirect(url_for('commercial_selection'))
    
    try:
        # Get commercial kitchen scenarios for template
        scenarios = []
        for name, data in helper.COMMERCIAL_KITCHEN_SCENARIOS.items():
            scenarios.append({
                'scenario_name': name,
                'scenario_name_ml': data['name_ml'],
                'description': data['description_en'],
                'health_risk_category': data['risk'],
                'combined_factor': data['factor'],
                'risk_color': helper.RISK_STYLES[data['risk']]['badge'],
                'risk_icon': helper.RISK_STYLES[data['risk']]['icon']
            })
        
        institution_data = session.get('institution_data', {})
        default_electricity_rate = institution_data.get('electricity_tariff') or db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.50)
        
        return render_template('commercial_kitchen_profile.html',
                             scenarios=scenarios,
                             default_electricity_rate=default_electricity_rate)
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error in commercial_kitchen_profile: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        flash('Error loading kitchen profile page', 'error')
        return redirect(url_for('commercial_selection'))

@app.route('/commercial/submit_kitchen', methods=['POST'])
def commercial_submit_kitchen():
    logger = get_logger()
    logger.log_step("DEBUG: /commercial/submit_kitchen POST")
    """Process commercial kitchen profile submission with scenario"""
    try:
        logger = get_logger()
        logger.log_subsection("COMMERCIAL KITCHEN SUBMIT")
        # Handle both JSON and Form data
        if request.is_json:
            data = request.json
        else:
            data = request.form
        logger.log_data("Incoming Kitchen Form", dict(data))

        # Get solar_willing and roof area from institution_data (already collected in commercial_selection)
        institution_data = session.get('institution_data', {})
        logger.log_data("Institution Data (session)", institution_data)

        kitchen_data = {
            'kitchen_scenario': data.get('kitchen_scenario'),  # NEW: single scenario field
            'cooking_hours_daily': float(data.get('cooking_hours_daily', 6)),
            'staff_exposed': int(data.get('staff_exposed', 2)),
            'electricity_tariff': float(data.get('electricity_tariff') or db_helper.get_system_parameter('ELECTRICITY_COMMERCIAL_RATE', 9.50)),
            # Keep old fields for backward compatibility
            'kitchen_type': data.get('kitchen_scenario', ''),
            'ventilation_quality': 'Average',
            'roof_area_available': float(institution_data.get('available_roof_area') or 500),  # Use from institution_data
            'solar_willing': institution_data.get('solar_willing', 'No'),  # Use from institution_data
            'budget_preference': data.get('budget_preference')
        }
        logger.log_data("Kitchen Data Parsed", kitchen_data)
        
        # Store in session
        session['kitchen_data'] = kitchen_data
        logger.log_success("Stored kitchen_data in session for commercial flow")
        if request.is_json:
            return jsonify({'success':True, 'redirect': url_for('commercial_energy_calculation')})
        else:
            return redirect(url_for('commercial_energy_calculation'))
            
    except Exception as e:
        logger.log_error(f"Error in commercial_submit_kitchen: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        
        if request.is_json:
            return jsonify({'success': False, 'message': str(e)}), 500
        else:
            flash('Error processing kitchen profile', 'error')
            return redirect(url_for('commercial_kitchen_profile'))

@app.route('/commercial_energy_calculation', methods=['GET', 'POST'])
def commercial_energy_calculation():
    """Combined energy calculation page (both dish-based and consumption-based methods)"""
    if 'institution_data' not in session:
        return redirect(url_for('commercial_selection'))
    
    if request.method == 'POST':
        try:
            logger = get_logger()
            logger.log_subsection("COMMERCIAL ENERGY CALCULATION POST")
            calculation_method = request.form.get('calculation_method')
            institution_data = session.get('institution_data', {})
            kitchen_data = session.get('kitchen_data', {})
            institution_id = session.get('commercial_analysis_id')
            logger.log_input("Calculation Method", calculation_method)
            logger.log_data("Institution Data (session)", institution_data)
            logger.log_data("Kitchen Data (session)", kitchen_data)

            # Clear previous com_energy_data on method switch (mirrors residential logic).
            old_com_data = session.pop('com_energy_data', None)
            if old_com_data:
                old_method = (
                    old_com_data.get('calculation_method')
                    or old_com_data.get('fuel_details', {}).get('calculation_method', 'consumption_based')
                )
                new_method = 'dish_based' if calculation_method == 'dish' else 'consumption_based'
                if old_method != new_method:
                    logger.log_step(f"Commercial method switch: {old_method} → {new_method}. Cleared old data.")

            # Call appropriate calculation function based on method
            if calculation_method == 'dish':
                result = commercial_cooking.calculate_dish_based(
                    request.form,
                    institution_data,
                    kitchen_data,
                    institution_id
                )
            else:  # consumption
                result = commercial_cooking.calculate_consumption_based(
                    request.form,
                    institution_data,
                    kitchen_data,
                    institution_id
                )
            
            if result.get('status') == 'error':
                flash(result.get('message', 'Calculation failed'), 'error')
                return redirect(url_for('commercial_energy_calculation'))
            
            # Save results to database
            if institution_id:
                helper.save_commercial_analysis(institution_id, result)
            
            session['com_energy_data'] = result
            logger.log_data("Commercial Energy Result", result)
            return redirect(url_for('commercial_analysis'))
            
        except Exception as e:
            logger.log_error(f"Error in commercial calculation: {e}")
            import traceback
            logger.log_error(traceback.format_exc())
            flash('Error processing calculation', 'error')
            return redirect(url_for('commercial_energy_calculation'))
    
    # GET: Show combined form
    try:
        logger = get_logger()
        logger.log_subsection("COMMERCIAL ENERGY CALCULATION GET")
        logger.log_step("DEBUG: commercial_energy_calculation GET request")

        institution_data = session.get('institution_data', {})
        logger.log_data("Session Institution Data", institution_data)
        logger.log_step(f"DEBUG: Institution type: {institution_data.get('institution_type')}")

        # Fetch commercial dishes and fuels for dish-based method
        conn = db_helper.get_connection()
        cursor = conn.cursor()

        # Get institution type to filter dishes
        institution_type = institution_data.get('institution_type')
        logger.log_step(f"DEBUG: Fetching commercial dishes for institution type: {institution_type}")
        
        # Query to get dishes filtered by institution_type column
        query = """
            SELECT dc.*, cat.category_name, cat.category_name_ml
            FROM dishes_commercial dc
            JOIN dish_categories cat ON dc.category_id = cat.category_id
            AND dc.institution_type = ?
            ORDER BY cat.display_order, dc.display_order
        """
        logger.log_step(f"DEBUG: Executing query to fetch dishes for {institution_type}...")
        cursor.execute(query, (institution_type,))
        all_dishes = [dict(row) for row in cursor.fetchall()]
        logger.log_step(f"DEBUG: Fetched {len(all_dishes)} dishes for {institution_type}")

        # Group dishes by category
        dish_data = {}
        for meal in ['Breakfast', 'Lunch', 'Dinner', 'Snacks']:
            dish_data[meal] = [d for d in all_dishes if d.get('category_name') == meal]
            logger.log_step(f"DEBUG: Meal '{meal}': {len(dish_data[meal])} dishes")

        all_fuels = db_helper.get_all_fuels()
        fuel_label_map = {
            f['fuel_name']: localize_db_label(f['fuel_name'], f.get('fuel_name_ml'))
            for f in all_fuels
        }
        logger.log_step(f"DEBUG: Fetched {len(all_fuels)} fuels from database")
        for fuel in all_fuels:
            logger.log_step(f"  - {fuel.get('fuel_name')}")
        logger.log_data("Commercial Dishes Loaded", {"total": len(all_dishes)})
        logger.log_data("Dish Data By Meal", {k: len(v) for k, v in dish_data.items()})
        logger.log_data("Fuels Loaded", [f.get('fuel_name') for f in all_fuels])

        conn.close()

        logger.log_step(f"DEBUG: dishes_available = True")
        logger.log_step("DEBUG: Rendering template: commercial_energy_calculation.html")

        return render_template('commercial_energy_calculation.html',
                             institution=institution_data,
                             dish_data=dish_data,
                             all_fuels=all_fuels,
                             fuel_label_map=fuel_label_map,
                             dishes_available=True)
    
    except Exception as e:
        logger.log_error(f"Error loading commercial energy calculation: {e}")
        import traceback
        logger.log_error(traceback.format_exc())
        flash('Error loading page', 'error')
        return redirect(url_for('commercial_selection'))



@app.route('/commercial_analysis')
def commercial_analysis():
    """Display commercial cooking analysis results (matching residential pattern)"""
    if 'com_energy_data' not in session:
        # If no energy data, send user back to start the commercial flow
        return redirect(url_for('commercial_selection'))

    institution_data = session.get('institution_data', {})
    kitchen_data = session.get('kitchen_data', {})
    energy_data = session.get('com_energy_data', {})
    institution_id = session.get('commercial_analysis_id')
    
    # Calculate alternatives (same helper as residential!)
    alternatives = helper.calculate_commercial_alternatives(energy_data, institution_data, kitchen_data)
    
    # Calculate health impact
    health_impact = helper.calculate_health_impact(energy_data, kitchen_data)
    
    # Generate recommendations
    recommendations = helper.generate_recommendations(alternatives, institution_data, kitchen_data, energy_data)
    
    # Save recommendations to database
    if institution_id:
        helper.save_recommendations(institution_id, recommendations)
    
    # Prepare complete analysis result (SAME structure as residential)
    analysis_result = build_analysis_result(energy_data, alternatives, health_impact, recommendations)
    save_analysis_result_to_cache(analysis_result, 'commercial')
    logger = get_logger()
    logger.log_subsection("RENDER COMMERCIAL ANALYSIS")
    logger.log_data("Energy Data", energy_data)
    logger.log_data("Alternatives", alternatives)
    logger.log_data("Health Impact", health_impact)
    logger.log_data("Recommendations", recommendations)
    
    # Use separate template for commercial analysis as requested
    return render_template('commercial_analysis.html', 
                          analysis=analysis_result,
                          household=institution_data,
                          is_commercial=True)


# =================================================================
# API & UTILITY ROUTES
# =================================================================

@app.route('/api/chart_data')
@api_error_handler
def chart_data():
    """Provide data for Chart.js visualizations"""
    # Determine analysis type from query param
    req_type = request.args.get('type')
    
    if req_type == 'commercial':
        analysis = load_analysis_result_from_cache('commercial')
    elif req_type == 'residential':
        analysis = load_analysis_result_from_cache('residential')
    else:
        analysis = load_analysis_result_from_cache()
        
    if not analysis:
        return jsonify({'error': 'No analysis data available'})
    
    # Localize chart labels with DB-backed Malayalam names where available.
    all_fuels = db_helper.get_all_fuels(active_only=False)
    fuel_label_map = {
        fuel['fuel_name']: localize_db_label(fuel['fuel_name'], fuel.get('fuel_name_ml'))
        for fuel in all_fuels
    }

    # Prepare data for different charts
    chart_data = {
        'cost_comparison': {
            'labels': [],
            'data': []
        },
        'emissions_comparison': {
            'labels': [],
            'data': []
        },
        'health_comparison': {
            'labels': [],
            'data': []
        }
    }
    
    # Add current fuel data
    current = analysis['current']
    chart_data['cost_comparison']['labels'].append(_('Current'))
    chart_data['cost_comparison']['data'].append(current['monthly_cost'])
    chart_data['emissions_comparison']['labels'].append(_('Current'))
    chart_data['emissions_comparison']['data'].append(resolve_annual_emissions(current))
    chart_data['health_comparison']['labels'].append(_('Current'))
    chart_data['health_comparison']['data'].append(analysis['health_impact']['health_risk_score'])
    
    # Add alternatives data
    alternatives = analysis.get('alternatives', [])
    
    # Handle both dict and list formats for alternatives
    if isinstance(alternatives, dict):
        for fuel, data in alternatives.items():
            label = fuel_label_map.get(fuel, _(fuel))
            chart_data['cost_comparison']['labels'].append(label)
            chart_data['cost_comparison']['data'].append(data.get('monthly_cost', 0))
            chart_data['emissions_comparison']['labels'].append(label)
            chart_data['emissions_comparison']['data'].append(resolve_annual_emissions(data))
            # Check for health score in different places
            health_score = data.get('health_risk_score', 0)
            chart_data['health_comparison']['labels'].append(label)
            chart_data['health_comparison']['data'].append(health_score)
    elif isinstance(alternatives, list):
        for alt in alternatives:
            fuel = alt.get('fuel', alt.get('alternative_fuel', 'Unknown'))
            label = fuel_label_map.get(fuel, _(fuel))
            chart_data['cost_comparison']['labels'].append(label)
            chart_data['cost_comparison']['data'].append(alt.get('monthly_cost', 0))
            chart_data['emissions_comparison']['labels'].append(label)
            chart_data['emissions_comparison']['data'].append(resolve_annual_emissions(alt))
            chart_data['health_comparison']['labels'].append(label)
            chart_data['health_comparison']['data'].append(alt.get('health_risk_score', 0))
            
    return jsonify(chart_data)

@app.route('/api/calculate_png', methods=['POST'])
def calculate_png():
    """API endpoint to calculate PNG consumption using shared backend logic"""
    try:
        data = request.json
        monthly_bill = float(data.get('monthly_bill', 0))
        input_type = data.get('type', 'bill') # 'bill' or 'consumption'
        
        # Priority 1: User-provided rate, Priority 2: database rate.
        rate = data.get('rate')
        if rate is None:
            png_price_data = db_helper.get_png_pricing(district='All', category='Domestic')
            if not png_price_data:
                return jsonify({'error': 'PNG pricing not found in database'}), 500
            rate = float(png_price_data['price_per_scm'])
        else:
            rate = float(rate)
        
        if input_type == 'bill':
            if monthly_bill <= 0:
                result = {
                     'monthly_scm_consumption': 0,
                     'monthly_energy_delivered': 0,
                     'total_bill': 0,
                     'tariff_used': rate
                }
            else:
                # Use shared helper with matching logic (binary search if needed)
                # Note: helper.calculate_png_consumption_from_bill takes bill amount
                calc_result = helper.calculate_png_consumption_from_bill(
                    monthly_bill,
                    rate_per_scm=rate
                )
                
                # Extract needed values
                result = {
                    'monthly_scm_consumption': calc_result.get('monthly_scm_consumption', 0),
                    'monthly_energy_delivered': calc_result.get('daily_energy_kwh', 0) * 30 * helper.DEFAULT_EFFICIENCIES.get('PNG', 0.70), # Energy Delivered = Gross * Eff
                    'total_bill': calc_result.get('total_bill', 0),
                    'tariff_used': calc_result.get('rate_per_scm', rate)
                }
        else:
            # Consumption (SCM) based
            monthly_scm = float(data.get('monthly_scm', 0))
            if monthly_scm <= 0:
                 result = {
                     'monthly_scm_consumption': 0,
                     'monthly_energy_delivered': 0,
                     'total_bill': 0,
                     'tariff_used': rate
                }
            else:
                calc_result = helper.calculate_png_bill_and_consumption(monthly_scm, rate_per_scm=rate)
                
                result = {
                    'monthly_scm_consumption': monthly_scm,
                    'monthly_energy_delivered': calc_result.get('daily_energy_kwh', 0) * 30 * helper.DEFAULT_EFFICIENCIES.get('PNG', 0.70),
                    'total_bill': calc_result.get('total_bill', 0),
                    'tariff_used': rate
                }

        return jsonify(result)
        
    except Exception as e:
        logger = get_logger()
        logger.log_error(f"Error in calculate_png: {e}")
        return jsonify({'error': str(e)}), 500

# =================================================================
# ERROR HANDLERS
# =================================================================

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors - Page Not Found"""
    return render_template('error.html',
                          error_code=404,
                          error_title=_('Page Not Found'),
                          error_message=_('The page you are looking for does not exist. It may have been moved or deleted.')), 404

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors - Internal Server Error"""
    # Log the error
    app.logger.error(f'Server Error: {e}')
    
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'error',
            'message': _('Something went wrong on our end. Please try again.'),
            'error_code': 500
        }), 500
        
    return render_template('error.html',
                          error_code=500,
                          error_title=_('Internal Server Error'),
                          error_message=_('Something went wrong on our end. Our team has been notified and is working to fix the issue.')), 500

@app.errorhandler(403)
def forbidden(e):
    """Handle 403 errors - Forbidden"""
    return render_template('error.html',
                          error_code=403,
                          error_title=_('Access Denied'),
                          error_message=_('You do not have permission to access this page.')), 403

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with JSON support"""
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'error',
            'message': _('Session expired. Please refresh the page and try again.'),
            'error_code': 'CSRF_ERROR'
        }), 400
    return render_template('error.html',
                          error_code=400,
                          error_title=_('Session Expired'),
                          error_message=_('Your session has expired. Please refresh the page and try again.')), 400

@app.errorhandler(400)
def bad_request(e):
    """Handle 400 errors - Bad Request"""
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'error',
            'message': _('Bad Request'),
            'error_code': 400
        }), 400
    return render_template('error.html',
                          error_code=400,
                          error_title=_('Bad Request'),
                          error_message=_('The request could not be understood or was missing required parameters.')), 400


if __name__ == '__main__':
    host = os.environ.get('FLASK_RUN_HOST') or os.environ.get('HOST') or '0.0.0.0'
    port = int(os.environ.get('FLASK_RUN_PORT') or os.environ.get('PORT') or '5000')
    debug = os.environ.get('FLASK_DEBUG')
    if debug is None:
        debug = bool(app.config.get('DEBUG'))
    else:
        debug = debug.strip().lower() in {'1', 'true', 'yes', 'on'}
    app.run(host=host, port=port, debug=debug)
