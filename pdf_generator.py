
"""
Enhanced PDF Report Generator for Keralam Clean Cooking Insights Platform
Optimized UI/UX with improved visual hierarchy, spacing, and chart sizing
Version: 4.0 - Production Ready
"""

import io
import os
import datetime
import uuid
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, PageBreak, Image, KeepTogether, Frame, PageTemplate
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

# ==================== DESIGN SYSTEM CONFIGURATION ====================

class DesignSystem:
    """Centralized design system for consistent styling"""
    
    # Color Palette (matching web app)
    PRIMARY_GREEN = colors.HexColor('#4CAF50')
    DARK_GREEN = colors.HexColor('#388E3C')
    LIGHT_GREEN = colors.HexColor('#70C170')
    BG_GREEN = colors.HexColor('#E8F5E9')
    ACCENT_YELLOW = colors.HexColor('#F2C851')
    
    # Neutral colors
    GREY_900 = colors.HexColor('#212121')
    GREY_700 = colors.HexColor('#616161')
    GREY_500 = colors.HexColor('#9E9E9E')
    GREY_300 = colors.HexColor('#E0E0E0')
    GREY_100 = colors.HexColor('#F5F5F5')
    
    # Status colors
    SUCCESS = colors.HexColor('#4CAF50')
    WARNING = colors.HexColor('#FF9800')
    DANGER = colors.HexColor('#F44336')
    INFO = colors.HexColor('#2196F3')
    
    # Typography Scale (optimized for readability)
    FONT_SIZE_H1 = 24  # Page titles
    FONT_SIZE_H2 = 18  # Section headers
    FONT_SIZE_H3 = 14  # Subsection headers
    FONT_SIZE_BODY = 10  # Body text
    FONT_SIZE_SMALL = 8  # Captions, footnotes
    FONT_SIZE_TINY = 7  # Footer text
    
    # Spacing Scale (8pt grid system)
    SPACE_XS = 4
    SPACE_SM = 8
    SPACE_MD = 16
    SPACE_LG = 24
    SPACE_XL = 32
    SPACE_XXL = 48
    
    # Layout dimensions
    PAGE_WIDTH = A4[0]  # 595.27 points
    PAGE_HEIGHT = A4[1]  # 841.89 points
    MARGIN_HORIZONTAL = 50
    MARGIN_VERTICAL = 40
    CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_HORIZONTAL)
    
    # Logo sizes (optimized)
    LOGO_HEIGHT_HEADER = 45  # Main header logos
    LOGO_HEIGHT_FOOTER = 25  # Footer logos
    
    # Chart dimensions
    CHART_WIDTH_FULL = CONTENT_WIDTH - 20
    CHART_HEIGHT_STANDARD = 180  # Optimized for A4
    CHART_HEIGHT_LARGE = 220


# Initialize design system
DS = DesignSystem()

# Report configuration
REPORTS_DIR = 'reports'
MAX_REPORT_FILES = 10


# ==================== LOCALIZATION HELPERS ====================

SUPPORTED_REPORT_LOCALES = {'en', 'ml'}

REPORT_I18N = {
    'en': {
        'platform_name': 'Keralam Clean Cooking Insights Platform',
        'report_residential_title': 'Cooking Energy Analysis',
        'report_residential_subtitle': 'Residential Household Report',
        'report_commercial_title': 'Commercial Energy Analysis',
        'report_commercial_subtitle': '{institution_type} Report',
        'generated_on': 'Generated',
        'generated_date': '{date}',
        'not_available': 'N/A',
        'household_profile': 'Household Profile',
        'institution_profile': 'Institution Profile',
        'name': 'Name',
        'district': 'District',
        'household_size': 'Household Size',
        'household_size_value': '{size} persons',
        'main_priority': 'Main Priority',
        'institution_name': 'Institution Name',
        'institution_type': 'Type',
        'daily_servings': 'Daily Servings',
        'working_days_month': 'Working Days/Month',
        'current_energy_consumption': 'Current Energy Consumption',
        'metric': 'Metric',
        'value': 'Value',
        'monthly_cost': 'Monthly Cost',
        'annual_cost': 'Annual Cost',
        'monthly_energy': 'Monthly Energy',
        'annual_co2': 'Annual CO2',
        'thermal_efficiency': 'Thermal Efficiency',
        'cost_per_serving': 'Cost per Serving',
        'fuel_breakdown': 'Fuel-wise Breakdown',
        'fuel': 'Fuel',
        'quantity': 'Quantity',
        'energy_delivered': 'Delivered Energy',
        'annual_emission': 'Annual Emission',
        'health_safety': 'Health & Safety Evaluation',
        'health_advisory': 'Health Advisory',
        'health_advisory_message': 'PM2.5 levels are above WHO guidelines. Consider cleaner alternatives.',
        'health_risk_level': 'Health Risk Level',
        'peak_pm25': 'Peak PM2.5',
        'health_risk_index': 'Health Risk Index',
        'comparative_analysis': 'Comparative Analysis',
        'cost_comparison_heading': 'Monthly Cost Comparison',
        'emissions_comparison_heading': 'Annual Carbon Footprint Comparison',
        'comparison_table_title_residential': 'Cooking with an energy source: Comparative Estimates',
        'comparison_table_title_commercial': 'Comparative Estimates',
        'comparison_energy_source': 'Energy Source',
        'comparison_monthly_cost': 'Monthly Cost',
        'comparison_annual_co2': 'Annual CO2',
        'comparison_efficiency': 'Efficiency',
        'comparison_health_risk': 'Health Risk',
        'comparison_status': 'Status',
        'comparison_current_setup': 'Your Current Setup',
        'comparison_current': 'Current',
        'status_cost_same': 'Cost: Same',
        'status_cost_less': 'Cost: Rs {value} less',
        'status_cost_more': 'Cost: Rs {value} more',
        'status_co2_same': 'CO2: Same',
        'status_co2_less': 'CO2: {value} kg less',
        'status_co2_more': 'CO2: {value} kg more',
        'strategic_recommendations': 'Strategic Recommendations',
        'technical_specifications': 'Technical Specifications',
        'technical_specs_solar_bess': 'Technical Specifications: Solar + BESS',
        'solar_bess': 'Solar + BESS',
        'top_recommendations': 'Top Recommendations',
        'recommendation_title': '#{rank}: {fuel} (Score: {score}/100)',
        'payback_period': 'Payback Period',
        'health_risk': 'Health Risk',
        'months': 'months',
        'meal_wise_breakdown': 'Meal-wise Energy Breakdown',
        'meal': 'Meal',
        'cost': 'Cost',
        'percent': '%',
        'current_label': 'Current',
        'chart_monthly_cost_axis': 'Monthly Cost (Rs)',
        'chart_monthly_cost_title': 'Monthly Cost Comparison',
        'chart_annual_co2_axis': 'Annual CO2 Emissions (kg)',
        'chart_annual_co2_title': 'Environmental Impact Comparison',
        'chart_years': 'Years',
        'chart_cumulative_savings': 'Cumulative Savings (Rs)',
        'chart_savings_title': '5-Year Savings Projection',
        'page_number': 'Page {page}',
        'footer_disclaimer': 'Estimates based on user inputs and standard factors. Actual costs may vary.',
        'risk_very_low': 'Very Low',
        'risk_low': 'Low',
        'risk_moderate': 'Moderate',
        'risk_high': 'High',
        'risk_very_high': 'Very High',
        'unknown': 'Unknown'
    },
    'ml': {
        'platform_name': 'കേരള ക്ലീൻ കുക്കിംഗ് ഇൻസൈറ്റ്സ് പ്ലാറ്റ്ഫോം',
        'report_residential_title': 'പാചക ഊർജ വിശകലനം',
        'report_residential_subtitle': 'ഗാർഹിക കുടുംബ റിപ്പോർട്ട്',
        'report_commercial_title': 'വാണിജ്യ ഊർജ വിശകലനം',
        'report_commercial_subtitle': '{institution_type} റിപ്പോർട്ട്',
        'generated_on': 'തയ്യാറാക്കിയ തീയതി',
        'generated_date': '{date}',
        'not_available': 'ലഭ്യമല്ല',
        'household_profile': 'കുടുംബ പ്രൊഫൈൽ',
        'institution_profile': 'സ്ഥാപന പ്രൊഫൈൽ',
        'name': 'പേര്',
        'district': 'ജില്ല',
        'household_size': 'കുടുംബത്തിന്റെ വലുപ്പം',
        'household_size_value': '{size} പേർ',
        'main_priority': 'പ്രധാന മുൻഗണന',
        'institution_name': 'സ്ഥാപനത്തിന്റെ പേര്',
        'institution_type': 'സ്ഥാപന തരം',
        'daily_servings': 'ദൈനംദിന സർവിംഗുകൾ',
        'working_days_month': 'മാസത്തിലെ പ്രവർത്തി ദിവസങ്ങൾ',
        'current_energy_consumption': 'നിലവിലെ ഊർജ ഉപഭോഗം',
        'metric': 'സൂചിക',
        'value': 'മൂല്യം',
        'monthly_cost': 'മാസാന്ത്യ ചെലവ്',
        'annual_cost': 'വാർഷിക ചെലവ്',
        'monthly_energy': 'മാസാന്ത്യ ഊർജം',
        'annual_co2': 'വാർഷിക CO2',
        'thermal_efficiency': 'താപ കാര്യക്ഷമത',
        'cost_per_serving': 'ഒരു സർവിംഗിന് ചെലവ്',
        'fuel_breakdown': 'ഇന്ധനവാർിയായ വിഭജനം',
        'fuel': 'ഇന്ധനം',
        'quantity': 'അളവ്',
        'energy_delivered': 'ലഭ്യമായ ഊർജം',
        'annual_emission': 'വാർഷിക ഉത്സർജനം',
        'health_safety': 'ആരോഗ്യവും സുരക്ഷയും',
        'health_advisory': 'ആരോഗ്യ മുന്നറിയിപ്പ്',
        'health_advisory_message': 'PM2.5 നില WHO മാർഗ്ഗരേഖയെക്കാൾ കൂടുതലാണ്. ശുദ്ധമായ ഇന്ധനങ്ങൾ പരിഗണിക്കുക.',
        'health_risk_level': 'ആരോഗ്യ അപകടനില',
        'peak_pm25': 'പരമാവധി PM2.5',
        'health_risk_index': 'ആരോഗ്യ അപകട സൂചിക',
        'comparative_analysis': 'താരതമ്യ വിശകലനം',
        'cost_comparison_heading': 'മാസാന്ത്യ ചെലവ് താരതമ്യം',
        'emissions_comparison_heading': 'വാർഷിക കാർബൺ ഉത്സർജന താരതമ്യം',
        'comparison_table_title_residential': 'വിവിധ ഊർജ മാർഗങ്ങളുടെ താരതമ്യ കണക്ക്',
        'comparison_table_title_commercial': 'താരതമ്യ കണക്ക്',
        'comparison_energy_source': 'ഊർജ സ്രോതസ്',
        'comparison_monthly_cost': 'മാസാന്ത്യ ചെലവ്',
        'comparison_annual_co2': 'വാർഷിക CO2',
        'comparison_efficiency': 'കാര്യക്ഷമത',
        'comparison_health_risk': 'ആരോഗ്യ അപകടം',
        'comparison_status': 'സ്ഥിതി',
        'comparison_current_setup': 'നിങ്ങളുടെ നിലവിലെ സംവിധാനം',
        'comparison_current': 'നിലവിൽ',
        'status_cost_same': 'ചെലവ്: സമാനം',
        'status_cost_less': 'ചെലവ്: Rs {value} കുറവ്',
        'status_cost_more': 'ചെലവ്: Rs {value} കൂടുതൽ',
        'status_co2_same': 'CO2: സമാനം',
        'status_co2_less': 'CO2: {value} kg കുറവ്',
        'status_co2_more': 'CO2: {value} kg കൂടുതൽ',
        'strategic_recommendations': 'തന്ത്രപ്രധാന ശുപാർശകൾ',
        'technical_specifications': 'സാങ്കേതിക വിശദാംശങ്ങൾ',
        'technical_specs_solar_bess': 'സാങ്കേതിക വിശദാംശങ്ങൾ: സോളാർ + BESS',
        'solar_bess': 'സോളാർ + BESS',
        'top_recommendations': 'മുൻനിര ശുപാർശകൾ',
        'recommendation_title': '#{rank}: {fuel} (സ്കോർ: {score}/100)',
        'payback_period': 'തിരിച്ചടി കാലയളവ്',
        'health_risk': 'ആരോഗ്യ അപകടം',
        'months': 'മാസം',
        'meal_wise_breakdown': 'ഭക്ഷണവാർിയായ ഊർജ വിഭജനം',
        'meal': 'ഭക്ഷണം',
        'cost': 'ചെലവ്',
        'percent': '%',
        'current_label': 'നിലവിൽ',
        'chart_monthly_cost_axis': 'മാസാന്ത്യ ചെലവ് (Rs)',
        'chart_monthly_cost_title': 'മാസാന്ത്യ ചെലവ് താരതമ്യം',
        'chart_annual_co2_axis': 'വാർഷിക CO2 ഉത്സർജനം (kg)',
        'chart_annual_co2_title': 'പരിസ്ഥിതി സ്വാധീന താരതമ്യം',
        'chart_years': 'വർഷങ്ങൾ',
        'chart_cumulative_savings': 'സമാഹരിച്ച ലാഭം (Rs)',
        'chart_savings_title': '5-വർഷ ലാഭ പ്രവചനം',
        'page_number': 'താൾ {page}',
        'footer_disclaimer': 'ഉപയോക്തൃ ഇൻപുട്ടുകളും സ്റ്റാൻഡേർഡ് ഘടകങ്ങളും അടിസ്ഥാനമാക്കിയുള്ള കണക്ക്. യഥാർത്ഥ ചെലവ് വ്യത്യാസപ്പെട്ടേക്കാം.',
        'risk_very_low': 'വളരെ കുറവ്',
        'risk_low': 'കുറവ്',
        'risk_moderate': 'മിതമായ',
        'risk_high': 'ഉയർന്ന',
        'risk_very_high': 'വളരെ ഉയർന്ന',
        'unknown': 'അറിയില്ല'
    }
}

FUEL_NAME_I18N = {
    'LPG': {'ml': 'എൽ.പി.ജി'},
    'PNG': {'ml': 'പി.എൻ.ജി'},
    'Grid electricity': {'ml': 'ഗ്രിഡ് വൈദ്യുതി'},
    'Traditional Solid Biomass': {'ml': 'പരമ്പരാഗത ഘന ബയോമാസ്'},
    'Biogas': {'ml': 'ബയോഗ്യാസ്'},
    'Solar + BESS': {'ml': 'സോളാർ + BESS'},
    'Current': {'ml': 'നിലവിൽ'},
    'Your Current Setup': {'ml': 'നിങ്ങളുടെ നിലവിലെ സംവിധാനം'}
}


def normalize_locale(locale):
    if not locale:
        return 'en'
    locale = str(locale).strip().lower()
    if locale == 'hi':
        return 'ml'
    return locale if locale in SUPPORTED_REPORT_LOCALES else 'en'


def tr(locale, key, **kwargs):
    locale = normalize_locale(locale)
    text = REPORT_I18N.get(locale, REPORT_I18N['en']).get(key, REPORT_I18N['en'].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


def localize_fuel_name(fuel_name, locale):
    if not fuel_name:
        return tr(locale, 'unknown')
    locale = normalize_locale(locale)
    if locale == 'ml':
        translated = FUEL_NAME_I18N.get(fuel_name, {}).get('ml')
        return translated or fuel_name
    return fuel_name


def localize_risk_category(risk_label, locale):
    if not risk_label:
        return tr(locale, 'risk_moderate')
    label = str(risk_label).strip().lower()
    mapping = {
        'very low': 'risk_very_low',
        'low': 'risk_low',
        'moderate': 'risk_moderate',
        'high': 'risk_high',
        'very high': 'risk_very_high'
    }
    return tr(locale, mapping.get(label, 'risk_moderate'))


def normalize_alternatives(alternatives):
    """Normalize alternatives from dict/list to list[dict] with fuel field."""
    normalized = []
    if isinstance(alternatives, dict):
        for fuel_name, alt_data in alternatives.items():
            if isinstance(alt_data, dict):
                entry = dict(alt_data)
                entry.setdefault('fuel', fuel_name)
                normalized.append(entry)
        return normalized
    if isinstance(alternatives, list):
        for alt_data in alternatives:
            if isinstance(alt_data, dict):
                entry = dict(alt_data)
                if not entry.get('fuel'):
                    entry['fuel'] = entry.get('alternative_fuel', tr('en', 'unknown'))
                normalized.append(entry)
    return normalized


def get_alternative_by_fuel(alternatives, fuel_name):
    if isinstance(alternatives, dict) and isinstance(alternatives.get(fuel_name), dict):
        entry = dict(alternatives[fuel_name])
        entry.setdefault('fuel', fuel_name)
        return entry
    for alt in normalize_alternatives(alternatives):
        current_fuel = alt.get('fuel', alt.get('alternative_fuel'))
        if current_fuel == fuel_name:
            return alt
    return None


# ==================== FONT REGISTRATION ====================

def register_fonts():
    """Register PDF and matplotlib fonts for English and Malayalam report rendering."""
    import logging
    logger = logging.getLogger(__name__)

    def register_pdf_font_pair(font_name, regular_path, bold_path):
        if not (os.path.exists(regular_path) and os.path.exists(bold_path)):
            return None
        regular_registered = False
        bold_registered = False
        try:
            pdfmetrics.registerFont(TTFont(font_name, regular_path))
            regular_registered = True
        except Exception:
            regular_registered = font_name in pdfmetrics.getRegisteredFontNames()
        try:
            pdfmetrics.registerFont(TTFont(f'{font_name}-Bold', bold_path))
            bold_registered = True
        except Exception:
            bold_registered = f'{font_name}-Bold' in pdfmetrics.getRegisteredFontNames()
        if not (regular_registered and bold_registered):
            return None
        return font_name, f'{font_name}-Bold'

    def register_matplotlib_font(font_path):
        if not os.path.exists(font_path):
            return None
        try:
            font_manager.fontManager.addfont(font_path)
            return {
                'name': font_manager.FontProperties(fname=font_path).get_name(),
                'path': font_path
            }
        except Exception:
            return None

    default_candidates = [
        ('Arial', 'C:\\Windows\\Fonts\\arial.ttf', 'C:\\Windows\\Fonts\\arialbd.ttf'),
        ('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('DejaVuSans', '/usr/share/fonts/dejavu/DejaVuSans.ttf', '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf'),
        ('Arial', '/Library/Fonts/Arial.ttf', '/Library/Fonts/Arial Bold.ttf'),
        ('DejaVuSans', 'static/fonts/DejaVuSans.ttf', 'static/fonts/DejaVuSans-Bold.ttf'),
    ]

    malayalam_candidates = [
        ('NotoSansMalayalam', 'static/fonts/NotoSansMalayalam-Regular.ttf', 'static/fonts/NotoSansMalayalam-Bold.ttf'),
        ('NirmalaUI', 'C:\\Windows\\Fonts\\Nirmala.ttf', 'C:\\Windows\\Fonts\\NirmalaB.ttf'),
        ('NotoSansMalayalam', '/usr/share/fonts/truetype/noto/NotoSansMalayalam-Regular.ttf', '/usr/share/fonts/truetype/noto/NotoSansMalayalam-Bold.ttf'),
    ]

    default_pair = None
    for font_name, regular_path, bold_path in default_candidates:
        default_pair = register_pdf_font_pair(font_name, regular_path, bold_path)
        if default_pair:
            logger.info("PDF Generator: Using %s as default report font", font_name)
            break
    if not default_pair:
        default_pair = ('Helvetica', 'Helvetica-Bold')
        logger.warning("No Unicode default font found; using Helvetica fallback")

    ml_pair = None
    for font_name, regular_path, bold_path in malayalam_candidates:
        ml_pair = register_pdf_font_pair(font_name, regular_path, bold_path)
        if ml_pair:
            logger.info("PDF Generator: Using %s for Malayalam report text", font_name)
            break
    if not ml_pair:
        # Graceful fallback to default pair if Malayalam font unavailable.
        ml_pair = default_pair
        logger.warning("Malayalam font not found; falling back to default font pair")

    default_chart_font = (
        register_matplotlib_font('static/fonts/DejaVuSans.ttf')
        or register_matplotlib_font('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        or {'name': 'DejaVu Sans', 'path': None}
    )
    ml_chart_font = (
        register_matplotlib_font('static/fonts/NotoSansMalayalam-Regular.ttf')
        or register_matplotlib_font('/usr/share/fonts/truetype/noto/NotoSansMalayalam-Regular.ttf')
        or default_chart_font
    )

    return {
        'default_regular': default_pair[0],
        'default_bold': default_pair[1],
        'ml_regular': ml_pair[0],
        'ml_bold': ml_pair[1],
        'chart_default_name': default_chart_font.get('name'),
        'chart_default_path': default_chart_font.get('path'),
        'chart_ml_name': ml_chart_font.get('name'),
        'chart_ml_path': ml_chart_font.get('path')
    }


FONT_PROFILES = register_fonts()
FONT_REGULAR = FONT_PROFILES['default_regular']
FONT_BOLD = FONT_PROFILES['default_bold']


def get_font_pair(locale):
    locale = normalize_locale(locale)
    if locale == 'ml':
        return FONT_PROFILES['ml_regular'], FONT_PROFILES['ml_bold']
    return FONT_PROFILES['default_regular'], FONT_PROFILES['default_bold']


def get_chart_font(locale):
    locale = normalize_locale(locale)
    if locale == 'ml':
        return FONT_PROFILES['chart_ml_name']
    return FONT_PROFILES['chart_default_name']


def get_chart_font_properties(locale):
    locale = normalize_locale(locale)
    font_path = FONT_PROFILES['chart_ml_path'] if locale == 'ml' else FONT_PROFILES['chart_default_path']
    if font_path and os.path.exists(font_path):
        return font_manager.FontProperties(fname=font_path)
    return font_manager.FontProperties(family=get_chart_font(locale))


# ==================== STYLE SYSTEM ====================

def create_styles(locale='en'):
    """Create optimized paragraph styles."""
    font_regular, font_bold = get_font_pair(locale)
    styles = getSampleStyleSheet()
    
    # Page Title
    styles.add(ParagraphStyle(
        name='PageTitle',
        parent=styles['Heading1'],
        fontSize=DS.FONT_SIZE_H1,
        textColor=DS.PRIMARY_GREEN,
        spaceAfter=DS.SPACE_SM,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName=font_bold,
        leading=DS.FONT_SIZE_H1 * 1.2
    ))
    
    # Subtitle
    styles.add(ParagraphStyle(
        name='Subtitle',
        parent=styles['Normal'],
        fontSize=DS.FONT_SIZE_BODY,
        textColor=DS.GREY_700,
        spaceAfter=DS.SPACE_LG,
        alignment=TA_CENTER,
        fontName=font_regular
    ))
    
    # Section Header (with bottom border effect)
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading2'],
        fontSize=DS.FONT_SIZE_H2,
        textColor=DS.PRIMARY_GREEN,
        spaceAfter=DS.SPACE_MD,
        spaceBefore=DS.SPACE_LG,
        fontName=font_bold,
        borderWidth=0,
        borderPadding=0,
        leading=DS.FONT_SIZE_H2 * 1.2
    ))
    
    # Subsection Header
    styles.add(ParagraphStyle(
        name='SubsectionHeader',
        parent=styles['Heading3'],
        fontSize=DS.FONT_SIZE_H3,
        textColor=DS.DARK_GREEN,
        spaceAfter=DS.SPACE_SM,
        spaceBefore=DS.SPACE_MD,
        fontName=font_bold,
        leading=DS.FONT_SIZE_H3 * 1.2
    ))
    
    # Body text (update existing sample style to avoid duplicate registration)
    if 'BodyText' in styles.byName:
        body_style = styles['BodyText']
        body_style.fontSize = DS.FONT_SIZE_BODY
        body_style.spaceAfter = DS.SPACE_SM
        body_style.fontName = font_regular
        body_style.leading = DS.FONT_SIZE_BODY * 1.4
        body_style.textColor = DS.GREY_900
    else:
        styles.add(ParagraphStyle(
            name='BodyText',
            parent=styles['Normal'],
            fontSize=DS.FONT_SIZE_BODY,
            spaceAfter=DS.SPACE_SM,
            fontName=font_regular,
            leading=DS.FONT_SIZE_BODY * 1.4,
            textColor=DS.GREY_900
        ))
    
    # Small text
    styles.add(ParagraphStyle(
        name='SmallText',
        parent=styles['Normal'],
        fontSize=DS.FONT_SIZE_SMALL,
        spaceAfter=DS.SPACE_XS,
        fontName=font_regular,
        textColor=DS.GREY_700,
        leading=DS.FONT_SIZE_SMALL * 1.3
    ))
    
    # Footer text
    styles.add(ParagraphStyle(
        name='FooterText',
        parent=styles['Normal'],
        fontSize=DS.FONT_SIZE_TINY,
        textColor=DS.GREY_500,
        alignment=TA_CENTER,
        fontName=font_regular
    ))
    
    # Highlight text (for emphasis)
    styles.add(ParagraphStyle(
        name='Highlight',
        parent=styles['Normal'],
        fontSize=DS.FONT_SIZE_BODY,
        textColor=DS.PRIMARY_GREEN,
        fontName=font_bold,
        spaceAfter=DS.SPACE_XS
    ))
    
    # Warning text
    styles.add(ParagraphStyle(
        name='WarningText',
        parent=styles['Normal'],
        fontSize=DS.FONT_SIZE_SMALL,
        textColor=DS.DANGER,
        fontName=font_regular,
        leftIndent=DS.SPACE_MD,
        rightIndent=DS.SPACE_MD
    ))
    
    return styles


# ==================== TABLE STYLES ====================

def create_table_style(header_color=None, locale='en'):
    """Create optimized table style"""
    if header_color is None:
        header_color = DS.PRIMARY_GREEN
    font_regular, font_bold = get_font_pair(locale)
    
    return TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), header_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), font_bold),
        ('FONTSIZE', (0, 0), (-1, 0), DS.FONT_SIZE_BODY),
        ('TOPPADDING', (0, 0), (-1, 0), DS.SPACE_SM),
        ('BOTTOMPADDING', (0, 0), (-1, 0), DS.SPACE_SM),
        ('LEFTPADDING', (0, 0), (-1, -1), DS.SPACE_SM),
        ('RIGHTPADDING', (0, 0), (-1, -1), DS.SPACE_SM),
        
        # Body
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTNAME', (0, 1), (-1, -1), font_regular),
        ('FONTSIZE', (0, 1), (-1, -1), DS.FONT_SIZE_SMALL),
        ('TOPPADDING', (0, 1), (-1, -1), DS.SPACE_XS),
        ('BOTTOMPADDING', (0, 1), (-1, -1), DS.SPACE_XS),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, DS.GREY_100]),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, DS.GREY_300),
        ('LINEBELOW', (0, 0), (-1, 0), 2, header_color),
    ])


def create_summary_table_style(locale='en'):
    """Style for profile/summary tables"""
    font_regular, font_bold = get_font_pair(locale)
    return TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), DS.BG_GREEN),
        ('TEXTCOLOR', (0, 0), (0, -1), DS.DARK_GREEN),
        ('FONTNAME', (0, 0), (0, -1), font_bold),
        ('FONTNAME', (1, 0), (1, -1), font_regular),
        ('FONTSIZE', (0, 0), (-1, -1), DS.FONT_SIZE_SMALL),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, DS.GREY_300),
        ('TOPPADDING', (0, 0), (-1, -1), DS.SPACE_SM),
        ('BOTTOMPADDING', (0, 0), (-1, -1), DS.SPACE_SM),
        ('LEFTPADDING', (0, 0), (-1, -1), DS.SPACE_SM),
        ('RIGHTPADDING', (0, 0), (-1, -1), DS.SPACE_SM),
    ])


# ==================== PAGE TEMPLATES ====================

def add_page_number(canvas, doc):
    """Enhanced page numbering with footer"""
    canvas.saveState()
    locale = normalize_locale(getattr(doc, '_report_locale', 'en'))
    font_regular, _ = get_font_pair(locale)
    
    # Footer line
    canvas.setStrokeColor(DS.GREY_300)
    canvas.setLineWidth(0.5)
    canvas.line(
        DS.MARGIN_HORIZONTAL, 
        DS.MARGIN_VERTICAL - 10, 
        DS.PAGE_WIDTH - DS.MARGIN_HORIZONTAL, 
        DS.MARGIN_VERTICAL - 10
    )
    
    # Page number
    page_num = canvas.getPageNumber()
    canvas.setFont(font_regular, DS.FONT_SIZE_TINY)
    canvas.setFillColor(DS.GREY_500)
    canvas.drawRightString(
        DS.PAGE_WIDTH - DS.MARGIN_HORIZONTAL, 
        DS.MARGIN_VERTICAL - 25, 
        tr(locale, 'page_number', page=page_num)
    )
    
    # Footer text
    canvas.setFont(font_regular, DS.FONT_SIZE_TINY)
    canvas.drawString(
        DS.MARGIN_HORIZONTAL, 
        DS.MARGIN_VERTICAL - 25, 
        tr(locale, 'platform_name')
    )
    
    # Disclaimer (centered)
    canvas.setFont(font_regular, DS.FONT_SIZE_TINY - 1)
    canvas.drawCentredString(
        DS.PAGE_WIDTH / 2, 
        DS.MARGIN_VERTICAL - 40, 
        tr(locale, 'footer_disclaimer')
    )
    
    canvas.restoreState()


# ==================== CHART GENERATION ====================

def create_cost_comparison_chart(current_cost, alternatives, is_commercial=False, locale='en'):
    """Optimized cost comparison chart"""
    try:
        locale = normalize_locale(locale)
        chart_font = get_chart_font(locale)
        chart_font_props = get_chart_font_properties(locale)

        # Set up matplotlib style
        with plt.rc_context({'font.family': chart_font, 'axes.unicode_minus': False}):
            plt.style.use('seaborn-v0_8-darkgrid')
            fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)
        
            # Prepare data
            labels = [tr(locale, 'current_label')]
            costs = [safe_float(current_cost, 0)]
            colors_list = [DS.DANGER.hexval().replace('0x', '#')]
        
            for alt in alternatives[:5]:
                fuel_name = alt.get('fuel', alt.get('alternative_fuel', tr(locale, 'unknown')))
                labels.append(localize_fuel_name(fuel_name, locale)[:20])
                cost = safe_float(alt.get('monthly_cost', 0), 0)
                costs.append(cost)
                colors_list.append(DS.SUCCESS.hexval().replace('0x', '#') if cost < current_cost else DS.DANGER.hexval().replace('0x', '#'))
        
            # Create horizontal bar chart
            y_pos = np.arange(len(labels))
            bars = ax.barh(y_pos, costs, color=colors_list, edgecolor='white', linewidth=1.5)
        
            # Styling
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, fontsize=9, fontproperties=chart_font_props)
            ax.set_xlabel(
                tr(locale, 'chart_monthly_cost_axis'),
                fontsize=10,
                fontweight='bold',
                color=DS.GREY_900.hexval().replace('0x', '#'),
                fontproperties=chart_font_props
            )
            ax.set_title(tr(locale, 'chart_monthly_cost_title'), fontsize=12, fontweight='bold',
                         color=DS.PRIMARY_GREEN.hexval().replace('0x', '#'), pad=15, fontproperties=chart_font_props)
            for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
                tick_label.set_fontproperties(chart_font_props)
        
            # Add value labels
            max_cost = max(costs) if costs else 0
            x_offset = (max_cost * 0.02) if max_cost > 0 else 1
            for i, (bar, cost) in enumerate(zip(bars, costs)):
                ax.text(cost + x_offset, i, f'₹{cost:,.0f}',
                        va='center', fontsize=8, fontweight='bold', fontproperties=chart_font_props)
        
            # Grid and background
            ax.grid(axis='x', alpha=0.3, linestyle='--')
            ax.set_facecolor('#FAFAFA')
            fig.patch.set_facecolor('white')
        
            # Tight layout
            plt.tight_layout()
        
            # Save to file
            chart_path = os.path.join(REPORTS_DIR, f'cost_chart_{uuid.uuid4().hex[:8]}.png')
            plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
        
            return chart_path
    except Exception as e:
        print(f"Error creating cost chart: {e}")
        return None


def create_emissions_comparison_chart(current_emissions, alternatives, locale='en'):
    """Optimized emissions comparison chart"""
    try:
        locale = normalize_locale(locale)
        chart_font = get_chart_font(locale)
        chart_font_props = get_chart_font_properties(locale)

        with plt.rc_context({'font.family': chart_font, 'axes.unicode_minus': False}):
            plt.style.use('seaborn-v0_8-darkgrid')
            fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)
        
            # Prepare data
            labels = [tr(locale, 'current_label')]
            emissions = [safe_float(current_emissions, 0)]
        
            # Color gradient based on emissions level
            def get_emission_color(value):
                if value <= 200:
                    return DS.SUCCESS.hexval().replace('0x', '#')
                elif value <= 500:
                    return DS.LIGHT_GREEN.hexval().replace('0x', '#')
                elif value <= 1000:
                    return DS.WARNING.hexval().replace('0x', '#')
                else:
                    return DS.DANGER.hexval().replace('0x', '#')
        
            colors_list = [get_emission_color(current_emissions)]
        
            for alt in alternatives[:5]:
                fuel_name = alt.get('fuel', alt.get('alternative_fuel', tr(locale, 'unknown')))
                labels.append(localize_fuel_name(fuel_name, locale)[:20])
                emission = safe_float(alt.get('annual_emissions_kg', alt.get('annual_co2', 0)), 0)
                emissions.append(emission)
                colors_list.append(get_emission_color(emission))
        
            # Create chart
            y_pos = np.arange(len(labels))
            bars = ax.barh(y_pos, emissions, color=colors_list, edgecolor='white', linewidth=1.5)
        
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, fontsize=9, fontproperties=chart_font_props)
            ax.set_xlabel(tr(locale, 'chart_annual_co2_axis'), fontsize=10, fontweight='bold',
                          color=DS.GREY_900.hexval().replace('0x', '#'), fontproperties=chart_font_props)
            ax.set_title(tr(locale, 'chart_annual_co2_title'), fontsize=12, fontweight='bold',
                         color=DS.PRIMARY_GREEN.hexval().replace('0x', '#'), pad=15, fontproperties=chart_font_props)
            for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
                tick_label.set_fontproperties(chart_font_props)
        
            # Add labels
            max_emission = max(emissions) if emissions else 0
            x_offset = (max_emission * 0.02) if max_emission > 0 else 1
            for i, (bar, emission) in enumerate(zip(bars, emissions)):
                ax.text(emission + x_offset, i, f'{emission:,.0f} kg',
                        va='center', fontsize=8, fontweight='bold', fontproperties=chart_font_props)
        
            ax.grid(axis='x', alpha=0.3, linestyle='--')
            ax.set_facecolor('#FAFAFA')
            fig.patch.set_facecolor('white')
        
            plt.tight_layout()
        
            chart_path = os.path.join(REPORTS_DIR, f'emissions_chart_{uuid.uuid4().hex[:8]}.png')
            plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
        
            return chart_path
    except Exception as e:
        print(f"Error creating emissions chart: {e}")
        return None


def create_savings_timeline_chart(alternatives, current_cost, locale='en'):
    """Create savings over time projection chart"""
    try:
        if not alternatives:
            return None
        locale = normalize_locale(locale)
        chart_font = get_chart_font(locale)
        chart_font_props = get_chart_font_properties(locale)
        
        with plt.rc_context({'font.family': chart_font, 'axes.unicode_minus': False}):
            plt.style.use('seaborn-v0_8-whitegrid')
            fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)
        
            # Calculate savings over 5 years for top 3 alternatives
            years = np.arange(0, 6)
        
            for i, alt in enumerate(alternatives[:3]):
                monthly_savings = current_cost - alt.get('monthly_cost', 0)
                annual_savings = monthly_savings * 12
                cumulative_savings = years * annual_savings
            
                # Subtract initial investment
                initial_cost = alt.get('upfront_cost', alt.get('capital_cost', 0))
                cumulative_savings = cumulative_savings - initial_cost
            
                fuel_name = alt.get('fuel', alt.get('alternative_fuel', tr(locale, 'unknown')))
                ax.plot(
                    years,
                    cumulative_savings,
                    marker='o',
                    linewidth=2.5,
                    label=localize_fuel_name(fuel_name, locale)[:20],
                    markersize=6
                )
        
            ax.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
            ax.set_xlabel(tr(locale, 'chart_years'), fontsize=10, fontweight='bold', fontproperties=chart_font_props)
            ax.set_ylabel(tr(locale, 'chart_cumulative_savings'), fontsize=10, fontweight='bold', fontproperties=chart_font_props)
            ax.set_title(tr(locale, 'chart_savings_title'), fontsize=12, fontweight='bold',
                         color=DS.PRIMARY_GREEN.hexval().replace('0x', '#'), pad=15, fontproperties=chart_font_props)
            ax.legend(loc='best', fontsize=8, framealpha=0.9, prop=chart_font_props)
            for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
                tick_label.set_fontproperties(chart_font_props)
            ax.grid(True, alpha=0.3)
        
            # Format y-axis
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₹{x/1000:.0f}K'))
        
            plt.tight_layout()
        
            chart_path = os.path.join(REPORTS_DIR, f'savings_chart_{uuid.uuid4().hex[:8]}.png')
            plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
        
            return chart_path
    except Exception as e:
        print(f"Error creating savings chart: {e}")
        return None


# ==================== HEADER COMPONENTS ====================

def create_header_table(title, subtitle, styles):
    """Optimized header with logos"""
    logo_height = DS.LOGO_HEIGHT_HEADER
    vasudha_logo = os.path.join('static', 'images', 'Vasudha_Logo.png')
    emc_logo = os.path.join('static', 'images', 'emc_Keralam_logo.png')
    
    # Load logos with error handling
    try:
        img_vasudha = Image(vasudha_logo, height=logo_height, width=logo_height*2.5, 
                           kind='proportional')
    except:
        img_vasudha = Spacer(1, logo_height)
    
    try:
        img_emc = Image(emc_logo, height=logo_height, width=logo_height*1.2, 
                       kind='proportional')
    except:
        img_emc = Spacer(1, logo_height)
    
    title_para = Paragraph(title, styles['PageTitle'])
    subtitle_para = Paragraph(subtitle, styles['Subtitle'])
    
    # Optimized column widths (Total ~6.8 inch)
    data = [[img_vasudha, [title_para, subtitle_para], img_emc]]
    
    table = Table(data, colWidths=[1.9*inch, 3.0*inch, 1.9*inch])
    table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    
    return table


# ==================== UTILITY FUNCTIONS ====================

def cleanup_old_reports(max_files=10):
    """Clean up old PDF reports"""
    try:
        if not os.path.exists(REPORTS_DIR):
            os.makedirs(REPORTS_DIR)
            return
        
        pdf_files = []
        for filename in os.listdir(REPORTS_DIR):
            if filename.endswith('.pdf'):
                filepath = os.path.join(REPORTS_DIR, filename)
                if os.path.isfile(filepath):
                    pdf_files.append((filepath, os.path.getctime(filepath)))
        
        pdf_files.sort(key=lambda x: x[1], reverse=True)
        
        if len(pdf_files) > max_files:
            for filepath, _ in pdf_files[max_files:]:
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Failed to remove {filepath}: {e}")
    except Exception as e:
        print(f"Error during cleanup: {e}")


def get_risk_category(score):
    """Convert health risk score to category"""
    if score < 1.0:
        return 'Very Low'
    elif score < 2.0:
        return 'Low'
    elif score < 3.0:
        return 'Moderate'
    elif score < 4.0:
        return 'High'
    else:
        return 'Very High'


def format_currency(value):
    try:
        return f"₹{float(value):,.0f}"
    except Exception:
        return "₹0"


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def format_percent(value, digits=0):
    try:
        return f"{float(value):.{digits}f}%"
    except Exception:
        return "0%"


def extract_fuel_breakdown(current):
    """Extract clean fuel-wise rows from heterogeneous fuel_details shapes."""
    fuel_details = current.get('fuel_details', {})
    if not isinstance(fuel_details, dict):
        return {}

    if isinstance(fuel_details.get('fuel_breakdown'), dict):
        source = fuel_details.get('fuel_breakdown', {})
    else:
        source = fuel_details

    skip_keys = {
        'calculation_method', 'type', 'fuels_used', 'fuel_breakdown',
        'servings_per_day', 'working_days', 'institution_type', 'meal_breakdown'
    }

    filtered = {}
    for fuel, details in source.items():
        if fuel in skip_keys or not isinstance(details, dict):
            continue
        has_metrics = any(
            key in details for key in (
                'monthly_cost', 'annual_emissions', 'annual_co2', 'annual_co2_kg',
                'quantity', 'monthly_scm', 'monthly_kwh', 'monthly_kg', 'monthly_m3'
            )
        )
        if has_metrics:
            filtered[fuel] = details
    return filtered


def get_quantity_text(details):
    """Normalize quantity+unit display across different payload shapes."""
    if not isinstance(details, dict):
        return "-"
    if details.get('quantity') is not None:
        unit = details.get('unit', '')
        try:
            quantity = float(details.get('quantity', 0))
            return f"{quantity:,.2f} {unit}".strip()
        except Exception:
            return f"{details.get('quantity')} {unit}".strip()
    for key, unit in (
        ('monthly_scm', 'SCM'),
        ('monthly_kwh', 'kWh'),
        ('monthly_kg', 'kg'),
        ('monthly_m3', 'm3'),
        ('daily_m3', 'm3/day')
    ):
        if details.get(key) is not None:
            try:
                return f"{float(details.get(key)):,.2f} {unit}"
            except Exception:
                return f"{details.get(key)} {unit}"
    return "-"


def create_fuel_breakdown_table(current, styles, locale='en'):
    """Create localized fuel-wise breakdown table for report readability."""
    rows = extract_fuel_breakdown(current)
    if not rows:
        return None

    header = [
        tr(locale, 'fuel'),
        tr(locale, 'quantity'),
        tr(locale, 'energy_delivered'),
        tr(locale, 'monthly_cost'),
        tr(locale, 'annual_emission')
    ]
    data = [header]

    body_style = ParagraphStyle(
        f'FuelBreakdownBody_{locale}',
        parent=styles['SmallText'],
        leading=11,
        wordWrap='CJK'
    )

    for fuel, details in rows.items():
        annual_emissions = details.get('annual_emissions', details.get('annual_co2_kg', details.get('annual_co2', 0)))
        delivered = details.get('energy_delivered', details.get('delivered_energy_kwh', details.get('monthly_energy_kwh', 0)))
        row = [
            Paragraph(localize_fuel_name(fuel, locale), body_style),
            Paragraph(get_quantity_text(details), body_style),
            Paragraph(f"{float(delivered):,.1f} kWh" if delivered is not None else "-", body_style),
            Paragraph(format_currency(details.get('monthly_cost', 0)), body_style),
            Paragraph(f"{float(annual_emissions):,.0f} kg" if annual_emissions is not None else "-", body_style),
        ]
        data.append(row)

    table = Table(
        data,
        colWidths=[1.25 * inch, 1.30 * inch, 1.35 * inch, 1.35 * inch, 1.55 * inch],
        repeatRows=1
    )
    table.setStyle(create_table_style(header_color=DS.DARK_GREEN, locale=locale))
    return table


def create_detailed_comparison_table(current, alternatives, styles, locale='en'):
    """Create localized detailed comparison table matching web UI semantics."""
    body_style = ParagraphStyle(
        f'ComparisonBody_{locale}',
        parent=styles['SmallText'],
        leading=10.5,
        wordWrap='CJK'
    )

    data = [[
        tr(locale, 'comparison_energy_source'),
        tr(locale, 'comparison_monthly_cost'),
        tr(locale, 'comparison_annual_co2'),
        tr(locale, 'comparison_efficiency'),
        tr(locale, 'comparison_health_risk'),
        tr(locale, 'comparison_status')
    ]]

    current_cost = float(current.get('monthly_cost', 0) or 0)
    current_emissions = float(current.get('annual_emissions', 0) or 0)
    current_risk = localize_risk_category(current.get('health_risk_category') or get_risk_category(current.get('health_risk_score', 0)), locale)

    data.append([
        Paragraph(tr(locale, 'comparison_current_setup'), body_style),
        Paragraph(format_currency(current_cost), body_style),
        Paragraph(f"{current_emissions:,.0f} kg", body_style),
        Paragraph(format_percent(current.get('overall_thermal_efficiency', 0), digits=0), body_style),
        Paragraph(current_risk, body_style),
        Paragraph(tr(locale, 'comparison_current'), body_style)
    ])

    sorted_alts = sorted(normalize_alternatives(alternatives), key=lambda x: x.get('monthly_cost', float('inf')))

    for alt in sorted_alts:
        fuel = localize_fuel_name(alt.get('fuel', alt.get('alternative_fuel', tr(locale, 'unknown'))), locale)
        cost = float(alt.get('monthly_cost', 0) or 0)
        emissions = float(alt.get('annual_emissions_kg', alt.get('annual_co2', 0)) or 0)
        efficiency = alt.get('efficiency', alt.get('thermal_efficiency', 0))
        risk_text = localize_risk_category(alt.get('health_risk_category', 'Moderate'), locale)

        cost_diff = cost - current_cost
        emission_diff = emissions - current_emissions

        status_parts = []
        if abs(cost_diff) < 10:
            status_parts.append(tr(locale, 'status_cost_same'))
        elif cost_diff < 0:
            status_parts.append(tr(locale, 'status_cost_less', value=f"{-cost_diff:,.0f}"))
        else:
            status_parts.append(tr(locale, 'status_cost_more', value=f"{cost_diff:,.0f}"))

        if abs(emission_diff) < 10:
            status_parts.append(tr(locale, 'status_co2_same'))
        elif emission_diff < 0:
            status_parts.append(tr(locale, 'status_co2_less', value=f"{-emission_diff:,.0f}"))
        else:
            status_parts.append(tr(locale, 'status_co2_more', value=f"{emission_diff:,.0f}"))

        data.append([
            Paragraph(fuel, body_style),
            Paragraph(format_currency(cost), body_style),
            Paragraph(f"{emissions:,.0f} kg", body_style),
            Paragraph(format_percent(efficiency, digits=0), body_style),
            Paragraph(risk_text, body_style),
            Paragraph("<br/>".join(status_parts), body_style)
        ])

    table = Table(
        data,
        colWidths=[1.50 * inch, 1.00 * inch, 1.00 * inch, 0.85 * inch, 1.05 * inch, 1.40 * inch],
        repeatRows=1
    )

    font_regular, font_bold = get_font_pair(locale)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), DS.PRIMARY_GREEN),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), font_bold),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e3f2fd')),
        ('FONTNAME', (0, 1), (-1, 1), font_bold),
        ('FONTNAME', (0, 2), (-1, -1), font_regular),
        ('GRID', (0, 0), (-1, -1), 0.5, DS.GREY_300),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    table.setStyle(TableStyle(style))
    return table

def create_solar_specs_table(bess_data, locale='en'):
    """Create Solar + BESS Specifications Table"""
    if not bess_data:
        return None
        
    if normalize_locale(locale) == 'ml':
        data = [
            ['വിശദാംശം', 'മൂല്യം', 'വിവരണം'],
            ['സോളാർ പി.വി സിസ്റ്റം വലുപ്പം', f"{bess_data.get('solar_capacity_kw', 0):.1f} kW", 'ദൈനംദിന ലോഡിനെ അടിസ്ഥാനമാക്കിയ ശേഷി'],
            ['ബാറ്ററി സ്റ്റോറേജ്', f"{bess_data.get('battery_capacity_kwh', 0):.1f} kWh", f"{bess_data.get('battery_units', 0)} യൂണിറ്റുകൾ x 1kWh മോഡ്യൂൾ"],
            ['ആവശ്യമായ മേൽക്കൂര വിസ്തൃതി', f"{bess_data.get('solar_capacity_kw', 0) * 10:.0f} m²", 'ഏകദേശം 10m²/kW'],
            ['ദൈനംദിന ഉൽപാദനം', f"{bess_data.get('daily_solar_generation', 0):.1f} kWh", 'കേരള GHI അടിസ്ഥാനമാക്കി'],
        ]
    else:
        data = [
            ['Specification', 'Value', 'Description'],
            ['Solar PV System Size', f"{bess_data.get('solar_capacity_kw', 0):.1f} kW", 'Capacity required based on daily load'],
            ['Battery Storage', f"{bess_data.get('battery_capacity_kwh', 0):.1f} kWh", f"{bess_data.get('battery_units', 0)} Units x 1kWh Modules"],
            ['Roof Area Required', f"{bess_data.get('solar_capacity_kw', 0) * 10:.0f} m²", 'Approx 10m²/kW'],
            ['Daily Generation', f"{bess_data.get('daily_solar_generation', 0):.1f} kWh", 'Based on Keralam GHI'],
        ]
    
    # Grid Backup
    grid_backup = bess_data.get('grid_backup', {})
    if grid_backup.get('needed_kwh_daily', 0) > 0.1:
        if normalize_locale(locale) == 'ml':
            data.append([
                'ഗ്രിഡ് ബാക്കപ്പ് ആവശ്യം',
                f"{grid_backup.get('needed_kwh_daily'):.1f} kWh",
                f"ദൈനംദിന ഊർജത്തിന്റെ {grid_backup.get('percentage'):.0f}% ഗ്രിഡിൽ നിന്ന്"
            ])
        else:
            data.append([
                'Grid Backup Needed',
                f"{grid_backup.get('needed_kwh_daily'):.1f} kWh",
                f"{grid_backup.get('percentage'):.0f}% of daily energy from grid"
            ])
        
    if normalize_locale(locale) == 'ml':
        data.append(['ആകെ പ്രാരംഭ ചെലവ്', f"₹{bess_data.get('total_capital_cost', 0):,.0f}", 'സോളാർ + ബാറ്ററി + ഇൻസ്റ്റലേഷൻ'])
    else:
        data.append(['Total Upfront Cost', f"₹{bess_data.get('total_capital_cost', 0):,.0f}", 'Solar + Battery + Installation'])
    
    table = Table(data, colWidths=[1.8*inch, 1.4*inch, 3.6*inch])
    table.setStyle(create_table_style(locale=locale))
    return table
    
def create_health_section(health_impact, locale='en'):
    """Create Health Evaluation Section table"""
    risk_cat_en = (health_impact.get('health_risk_category') or 'Moderate').title()
    risk_cat = localize_risk_category(risk_cat_en, locale)
    # Color
    color_map = {'Low': DS.SUCCESS, 'Moderate': DS.WARNING, 'High': DS.DANGER, 'Very High': DS.DANGER}
    risk_color = color_map.get(risk_cat_en, DS.WARNING)
    font_regular, font_bold = get_font_pair(locale)
    
    data = [
        [tr(locale, 'health_risk_level'), tr(locale, 'peak_pm25'), tr(locale, 'health_risk_index')],
        [risk_cat, f"{health_impact.get('pm25_peak', 0):.1f} μg/m³", f"{health_impact.get('health_risk_score', 0):.0f}/100"]
    ]
    
    table = Table(data, colWidths=[2.2*inch, 2.3*inch, 2.3*inch])
    style = TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), font_bold),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('TEXTCOLOR', (0,0), (-1,0), DS.GREY_700),
        ('FONTSIZE', (0,1), (-1,1), 12),
        ('FONTNAME', (0,1), (-1,1), font_regular),
        ('TEXTCOLOR', (0,1), (0,1), risk_color), # Risk Level Color
        ('GRID', (0,0), (-1,-1), 0.5, DS.GREY_300),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ])
    table.setStyle(style)
    return table

def generate_residential_report(analysis_data, household_data, kitchen_data, energy_data, locale='en'):
    """Generate localized residential PDF report."""
    locale = normalize_locale(locale)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=DS.MARGIN_HORIZONTAL,
        leftMargin=DS.MARGIN_HORIZONTAL,
        topMargin=DS.MARGIN_VERTICAL + 20,
        bottomMargin=DS.MARGIN_VERTICAL + 50
    )
    doc._report_locale = locale

    story = []
    styles = create_styles(locale)
    current = analysis_data.get('current') or energy_data or {}
    health_impact = analysis_data.get('health_impact', {})
    alternatives = analysis_data.get('alternatives', {})
    alts_list = sorted(normalize_alternatives(alternatives), key=lambda x: x.get('monthly_cost', float('inf')))

    cost_chart = None
    emissions_chart = None

    # ===== PAGE 1 =====
    story.append(create_header_table(
        tr(locale, 'report_residential_title'),
        tr(locale, 'report_residential_subtitle'),
        styles
    ))
    story.append(Spacer(1, DS.SPACE_MD))
    story.append(Paragraph(
        f"{tr(locale, 'generated_on')}: {datetime.datetime.now().strftime('%d-%m-%Y')}",
        styles['FooterText']
    ))
    story.append(Spacer(1, DS.SPACE_LG))

    story.append(Paragraph(tr(locale, 'household_profile'), styles['SectionHeader']))
    profile_data = [
        [tr(locale, 'name'), household_data.get('name') or tr(locale, 'not_available')],
        [tr(locale, 'district'), household_data.get('district') or tr(locale, 'not_available')],
        [tr(locale, 'household_size'), tr(locale, 'household_size_value', size=household_data.get('household_size', 0))],
        [tr(locale, 'main_priority'), str(household_data.get('main_priority', tr(locale, 'not_available'))).title()],
    ]
    story.append(Table(profile_data, colWidths=[2 * inch, 3.5 * inch], style=create_summary_table_style(locale=locale)))
    story.append(Spacer(1, DS.SPACE_LG))

    story.append(Paragraph(tr(locale, 'current_energy_consumption'), styles['SectionHeader']))
    summary_data = [
        [tr(locale, 'metric'), tr(locale, 'value')],
        [tr(locale, 'monthly_cost'), format_currency(current.get('monthly_cost', 0))],
        [tr(locale, 'monthly_energy'), f"{float(current.get('monthly_energy_kwh', 0) or 0):.1f} kWh"],
        [tr(locale, 'annual_co2'), f"{float(current.get('annual_emissions', 0) or 0):,.0f} kg"],
        [tr(locale, 'thermal_efficiency'), format_percent(current.get('overall_thermal_efficiency', 0), digits=0)],
    ]
    story.append(Table(summary_data, colWidths=[2.5 * inch, 3.0 * inch], style=create_table_style(locale=locale)))
    story.append(Spacer(1, DS.SPACE_MD))

    fuel_breakdown_table = create_fuel_breakdown_table(current, styles, locale=locale)
    if fuel_breakdown_table:
        story.append(Paragraph(tr(locale, 'fuel_breakdown'), styles['SubsectionHeader']))
        story.append(fuel_breakdown_table)
        story.append(Spacer(1, DS.SPACE_LG))
    else:
        story.append(Spacer(1, DS.SPACE_SM))

    story.append(Paragraph(tr(locale, 'health_safety'), styles['SectionHeader']))
    story.append(create_health_section(health_impact, locale=locale))

    if float(health_impact.get('pm25_peak', 0) or 0) > 25:
        story.append(Spacer(1, DS.SPACE_SM))
        advisory = f"<b>{tr(locale, 'health_advisory')}:</b> {tr(locale, 'health_advisory_message')}"
        story.append(Paragraph(advisory, styles['WarningText']))

    story.append(PageBreak())

    # ===== PAGE 2 =====
    story.append(Paragraph(tr(locale, 'comparative_analysis'), styles['PageTitle']))
    story.append(Spacer(1, DS.SPACE_MD))

    if alts_list:
        cost_chart = create_cost_comparison_chart(current.get('monthly_cost', 0), alts_list, locale=locale)
        emissions_chart = create_emissions_comparison_chart(current.get('annual_emissions', 0), alts_list, locale=locale)
        if cost_chart and emissions_chart:
            chart_row = [
                Image(cost_chart, width=3.3 * inch, height=2.3 * inch),
                Image(emissions_chart, width=3.3 * inch, height=2.3 * inch)
            ]
            chart_table = Table([chart_row], colWidths=[3.4 * inch, 3.4 * inch])
            chart_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            story.append(chart_table)
            story.append(Spacer(1, DS.SPACE_LG))

    story.append(Paragraph(tr(locale, 'comparison_table_title_residential'), styles['SectionHeader']))
    story.append(create_detailed_comparison_table(current, alternatives, styles, locale=locale))

    story.append(PageBreak())

    # ===== PAGE 3 =====
    story.append(Paragraph(tr(locale, 'strategic_recommendations'), styles['PageTitle']))
    story.append(Spacer(1, DS.SPACE_MD))

    solar_alt = get_alternative_by_fuel(alternatives, 'Solar + BESS')
    if solar_alt and isinstance(solar_alt.get('bess_system'), dict):
        story.append(Paragraph(tr(locale, 'technical_specs_solar_bess'), styles['SectionHeader']))
        bess_table = create_solar_specs_table(solar_alt['bess_system'], locale=locale)
        if bess_table:
            story.append(bess_table)
            story.append(Spacer(1, DS.SPACE_LG))

    story.append(Paragraph(tr(locale, 'top_recommendations'), styles['SectionHeader']))
    recommendations = analysis_data.get('recommendations', [])
    for i, rec in enumerate(recommendations[:3], 1):
        if isinstance(rec, (list, tuple)) and len(rec) >= 3:
            fuel, score, rec_data = rec[0], rec[1], rec[2]
        elif isinstance(rec, dict):
            fuel = rec.get('fuel', rec.get('alternative_fuel', tr(locale, 'unknown')))
            score = rec.get('score', 0)
            rec_data = rec
        else:
            continue

        fuel_label = localize_fuel_name(fuel, locale)
        story.append(Paragraph(
            tr(locale, 'recommendation_title', rank=i, fuel=fuel_label, score=f"{float(score):.1f}"),
            styles['SubsectionHeader']
        ))
        rec_data_table = [
            [tr(locale, 'monthly_cost'), format_currency(rec_data.get('monthly_cost', 0))],
            [tr(locale, 'annual_co2'), f"{float(rec_data.get('annual_co2', rec_data.get('annual_emissions_kg', 0)) or 0):,.0f} kg"],
            [tr(locale, 'payback_period'), f"{float(rec_data.get('payback_period_months', 0) or 0):.0f} {tr(locale, 'months')}"],
            [tr(locale, 'health_risk'), localize_risk_category(rec_data.get('health_risk_category', 'Moderate'), locale)],
        ]
        story.append(Table(rec_data_table, colWidths=[2 * inch, 3.5 * inch], style=create_summary_table_style(locale=locale)))
        story.append(Spacer(1, DS.SPACE_MD))

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    buffer.seek(0)

    try:
        if cost_chart and os.path.exists(cost_chart):
            os.remove(cost_chart)
        if emissions_chart and os.path.exists(emissions_chart):
            os.remove(emissions_chart)
    except Exception:
        pass

    return buffer


def generate_commercial_report(analysis_data, institution_data, kitchen_data, energy_data, locale='en'):
    """Generate localized commercial PDF report."""
    locale = normalize_locale(locale)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=DS.MARGIN_HORIZONTAL,
        leftMargin=DS.MARGIN_HORIZONTAL,
        topMargin=DS.MARGIN_VERTICAL + 20,
        bottomMargin=DS.MARGIN_VERTICAL + 50
    )
    doc._report_locale = locale

    story = []
    styles = create_styles(locale)
    current = analysis_data.get('current') or energy_data or {}
    alternatives = analysis_data.get('alternatives', {})
    alts_list = sorted(normalize_alternatives(alternatives), key=lambda x: x.get('monthly_cost', float('inf')))

    cost_chart = None
    emissions_chart = None

    institution_type = institution_data.get('institution_type', tr(locale, 'institution_type'))
    story.append(create_header_table(
        tr(locale, 'report_commercial_title'),
        tr(locale, 'report_commercial_subtitle', institution_type=institution_type),
        styles
    ))
    story.append(Spacer(1, DS.SPACE_MD))
    story.append(Paragraph(
        f"{tr(locale, 'generated_on')}: {datetime.datetime.now().strftime('%d-%m-%Y')}",
        styles['FooterText']
    ))
    story.append(Spacer(1, DS.SPACE_LG))

    story.append(Paragraph(tr(locale, 'institution_profile'), styles['SectionHeader']))
    inst_profile = [
        [tr(locale, 'institution_name'), institution_data.get('institution_name') or tr(locale, 'not_available')],
        [tr(locale, 'institution_type'), institution_data.get('institution_type') or tr(locale, 'not_available')],
        [tr(locale, 'daily_servings'), f"{int(institution_data.get('servings_per_day', 0) or 0):,}"],
        [tr(locale, 'working_days_month'), str(institution_data.get('working_days', 0) or 0)],
    ]
    story.append(Table(inst_profile, colWidths=[2.2 * inch, 3.3 * inch], style=create_summary_table_style(locale=locale)))
    story.append(Spacer(1, DS.SPACE_LG))

    story.append(Paragraph(tr(locale, 'current_energy_consumption'), styles['SectionHeader']))
    ops_summary = [
        [tr(locale, 'metric'), tr(locale, 'value')],
        [tr(locale, 'monthly_cost'), format_currency(current.get('monthly_cost', 0))],
        [tr(locale, 'annual_cost'), format_currency((float(current.get('monthly_cost', 0) or 0) * 12))],
        [tr(locale, 'monthly_energy'), f"{float(current.get('monthly_energy_kwh', 0) or 0):,.0f} kWh"],
        [tr(locale, 'annual_co2'), f"{float(current.get('annual_emissions', 0) or 0):,.0f} kg"],
    ]
    if current.get('cost_per_serving') is not None:
        ops_summary.append([tr(locale, 'cost_per_serving'), f"₹{float(current.get('cost_per_serving', 0) or 0):.2f}"])

    story.append(Table(ops_summary, colWidths=[2.5 * inch, 3 * inch], style=create_table_style(locale=locale)))
    story.append(Spacer(1, DS.SPACE_MD))

    fuel_breakdown_table = create_fuel_breakdown_table(current, styles, locale=locale)
    if fuel_breakdown_table:
        story.append(Paragraph(tr(locale, 'fuel_breakdown'), styles['SubsectionHeader']))
        story.append(fuel_breakdown_table)
        story.append(Spacer(1, DS.SPACE_MD))

    meal_breakdown = current.get('fuel_details', {}).get('meal_breakdown', {})
    if isinstance(meal_breakdown, dict) and meal_breakdown:
        story.append(Paragraph(tr(locale, 'meal_wise_breakdown'), styles['SubsectionHeader']))
        meal_data = [[tr(locale, 'meal'), f"{tr(locale, 'monthly_energy')} (kWh)", f"{tr(locale, 'cost')} (₹)", tr(locale, 'percent')]]
        for meal, meal_values in meal_breakdown.items():
            meal_data.append([
                str(meal),
                f"{float(meal_values.get('energy_kwh', 0) or 0):.1f}",
                f"₹{float(meal_values.get('cost', 0) or 0):.0f}",
                f"{float(meal_values.get('percentage', 0) or 0):.0f}%"
            ])
        story.append(Table(
            meal_data,
            colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 1.0 * inch],
            style=create_table_style(header_color=DS.DARK_GREEN, locale=locale)
        ))
        story.append(Spacer(1, DS.SPACE_LG))

    health_impact = analysis_data.get('health_impact', {})
    if isinstance(health_impact, dict) and health_impact:
        story.append(Paragraph(tr(locale, 'health_safety'), styles['SectionHeader']))
        story.append(create_health_section(health_impact, locale=locale))
        if safe_float(health_impact.get('pm25_peak', 0), 0) > 25:
            story.append(Spacer(1, DS.SPACE_SM))
            advisory = f"<b>{tr(locale, 'health_advisory')}:</b> {tr(locale, 'health_advisory_message')}"
            story.append(Paragraph(advisory, styles['WarningText']))
        story.append(Spacer(1, DS.SPACE_LG))

    story.append(PageBreak())

    story.append(Paragraph(tr(locale, 'comparative_analysis'), styles['PageTitle']))
    story.append(Spacer(1, DS.SPACE_MD))
    if alts_list:
        cost_chart = create_cost_comparison_chart(current.get('monthly_cost', 0), alts_list, is_commercial=True, locale=locale)
        emissions_chart = create_emissions_comparison_chart(current.get('annual_emissions', 0), alts_list, locale=locale)
        if cost_chart and emissions_chart:
            chart_row = [
                Image(cost_chart, width=3.3 * inch, height=2.3 * inch),
                Image(emissions_chart, width=3.3 * inch, height=2.3 * inch)
            ]
            chart_table = Table([chart_row], colWidths=[3.4 * inch, 3.4 * inch])
            chart_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            story.append(chart_table)
            story.append(Spacer(1, DS.SPACE_LG))

    story.append(Paragraph(tr(locale, 'comparison_table_title_commercial'), styles['SectionHeader']))
    story.append(create_detailed_comparison_table(current, alternatives, styles, locale=locale))

    story.append(PageBreak())

    story.append(Paragraph(tr(locale, 'technical_specifications'), styles['PageTitle']))
    solar_alt = get_alternative_by_fuel(alternatives, 'Solar + BESS')
    if solar_alt and isinstance(solar_alt.get('bess_system'), dict):
        story.append(Paragraph(tr(locale, 'solar_bess'), styles['SectionHeader']))
        bess_table = create_solar_specs_table(solar_alt['bess_system'], locale=locale)
        if bess_table:
            story.append(bess_table)

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    buffer.seek(0)

    try:
        if cost_chart and os.path.exists(cost_chart):
            os.remove(cost_chart)
        if emissions_chart and os.path.exists(emissions_chart):
            os.remove(emissions_chart)
    except Exception:
        pass

    return buffer



# ==================== MAIN ENTRY POINT ====================

def generate_report(analysis_type, analysis_data, user_data, locale='en'):
    """
    Main entry point for report generation
    
    Args:
        analysis_type: 'residential' or 'commercial'
        analysis_data: Complete analysis results
        user_data: All user/household/institution data
    
    Returns:
        io.BytesIO: PDF file buffer
    """
    # Cleanup old reports
    cleanup_old_reports(MAX_REPORT_FILES)
    
    # Ensure reports directory exists
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    locale = normalize_locale(locale)

    if analysis_type == 'residential':
        household_data = user_data.get('household_data', {})
        kitchen_data = user_data.get('kitchen_data', {})
        energy_data = user_data.get('energy_data', {})
        
        return generate_residential_report(
            analysis_data,
            household_data,
            kitchen_data,
            energy_data,
            locale=locale
        )
    
    elif analysis_type == 'commercial':
        institution_data = user_data.get('institution_data', {})
        kitchen_data = user_data.get('kitchen_data', {})
        energy_data = user_data.get('energy_data', {})
        
        return generate_commercial_report(
            analysis_data,
            institution_data,
            kitchen_data,
            energy_data,
            locale=locale
        )
    
    else:
        raise ValueError(f"Unknown analysis type: {analysis_type}")


# ==================== EXPORT ====================

__all__ = [
    'generate_report',
    'generate_residential_report',
    'generate_commercial_report',
    'cleanup_old_reports',
    'DesignSystem'
]
