"""
Configuration settings for Keralam Cooking Energy Analysis Tool
==============================================================

This file contains configuration settings for different environments
(development, testing, production).

NOTE: Research constants (emission factors, efficiencies, fuel costs, etc.)
are now loaded from the database via helper.load_constants_from_db().
This file only contains Flask/app configuration.
"""

import os
import secrets
from pathlib import Path

# Base directory of the application
BASE_DIR = Path(__file__).parent


def _env_flag(name, default=False):
    """Parse a boolean environment flag."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _generate_dev_secret_key():
    """Generate a secure secret key for development.
    
    In development, we use a fixed key to prevent session invalidation
    when the server reloads due to file changes.
    """
    return "dev-secret-btgvrfcdbgbhnjm-tgdc"


class Config:
    """Base configuration class."""
    
    # Flask settings - Use env var or generate secure random key
    SECRET_KEY = os.environ.get('SECRET_KEY') or _generate_dev_secret_key()
    
    # Database settings
    DATABASE_PATH = BASE_DIR / 'cooking_webapp.db'
    
    # Babel settings for internationalization
    LANGUAGES = {
        'en': 'English',
        'ml': 'മലയാളം'
    }
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'Asia/Kolkata'
    
    # File upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
    
    # Application settings
    APP_NAME = 'Keralam Cooking Energy Analysis Tool'
    APP_VERSION = '1.0'
    APP_AUTHOR = 'Vasudha Foundation'

    # Commercial Cooking Parameters
    SERVINGS_THRESHOLDS = {
        'small': 100,
        'medium': 500,
        'large': 2000
    }
    
    COMMERCIAL_WASTAGE_FACTORS = {
        'School': {'base': 1.05, 'min': 1.02},
        'Anganwadi': {'base': 1.08, 'min': 1.03},
        'Hotel': {'base': 1.12, 'min': 1.05},
        'Factory': {'base': 1.05, 'min': 1.02},
        'Community Kitchen': {'base': 1.03, 'min': 1.01}
    }
    
    INSTITUTION_MEAL_CALORIES_DEFAULTS = {
        'Breakfast': 450,
        'Lunch': 650,
        'Dinner': 650,
        'Snacks': 250
    }

    VOLUME_EFFICIENCY_DEFAULTS = {
        'small': 1.0,
        'medium': 0.95,
        'large': 0.90,
        'very_large': 0.85, 
        'huge': 0.80
    }


class DevelopmentConfig(Config):
    """Development configuration."""
    
    DEBUG = True
    TESTING = False
    
    # Flask settings for development
    FLASK_ENV = 'development'
    
    # Logging
    LOG_LEVEL = 'DEBUG'
    LOG_TO_STDOUT = True


class TestingConfig(Config):
    """Testing configuration."""
    
    DEBUG = True
    TESTING = True
    WTF_CSRF_ENABLED = False
    
    # Use in-memory database for testing
    DATABASE_PATH = ':memory:'
    
    # Logging
    LOG_LEVEL = 'INFO'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    
    # Use environment variables for sensitive data
    # Use environment variables for sensitive data
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # Try to load from local .flask_secret file to allow persistence across reloads
        secret_file = BASE_DIR / '.flask_secret'
        if secret_file.exists():
            with open(secret_file, 'r') as f:
                SECRET_KEY = f.read().strip()
        
        if not SECRET_KEY:
            import secrets
            SECRET_KEY = secrets.token_hex(32)
            try:
                with open(secret_file, 'w') as f:
                    f.write(SECRET_KEY)
                print("WARNING: SECRET_KEY not set. Generated and saved temporary key to .flask_secret")
            except:
                print("WARNING: SECRET_KEY not set in Production environment. Generated temporary key (not saved).")
    
    # Database path for production. Prefer explicit env vars, then a local data directory.
    DATABASE_PATH = Path(os.environ.get('DATABASE_PATH') or (BASE_DIR / 'data' / 'cooking_webapp.db'))
    
    # File paths for production
    UPLOAD_FOLDER = Path(os.environ.get('UPLOAD_FOLDER') or (BASE_DIR / 'uploads'))
    
    # Disable debug toolbar
    DEBUG_TB_ENABLED = False
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_TO_STDOUT = True
    
    # Security settings
    SESSION_COOKIE_SECURE = _env_flag('SESSION_COOKIE_SECURE', True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PREFERRED_URL_SCHEME = 'https' if SESSION_COOKIE_SECURE else 'http'


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(config_name=None):
    """Get configuration based on environment variable or parameter."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    return config.get(config_name, config['default'])


# =============================================================================
# DEPRECATED CONSTANTS - Now loaded from database
# =============================================================================
# The following constants have been moved to the database and are loaded
# dynamically via helper.load_constants_from_db():
#
# - LPG_CALORIFIC_VALUE, LPG_CYLINDER_WEIGHT, LPG_SUBSIDY_AMOUNT
# - PNG_CALORIFIC_VALUE, PNG_SLAB_RATES
# - Keralam_SOLAR_GHI, SOLAR_SYSTEM_EFF, Keralam_WEATHER_FACTOR, etc.
# - EMISSION_FACTORS, PM25_BASE_EMISSIONS
# - DEFAULT_EFFICIENCIES
# - KITCHEN_FACTORS, VENTILATION_FACTORS (now scenarios in DB)
# - Keralam_DISTRICTS (use db_helper.get_districts())
#
# For commercial cooking constants, see the database tables:
# - group_cooking_efficiency
# - meal_energy_distribution
# =============================================================================
