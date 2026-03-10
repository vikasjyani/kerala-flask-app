"""
Error handling utilities for Keralam Clean Cooking Tool
=====================================================

Provides custom exceptions and error handling decorators
for consistent error management across the application.
"""

import functools
import logging
from typing import Callable, Any, Optional
from flask import jsonify, flash, redirect, url_for

# Get logger
logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class CookingToolError(Exception):
    """Base exception for Keralam Clean Cooking Tool."""
    def __init__(self, message: str, code: str = "ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class DatabaseError(CookingToolError):
    """Database operation errors."""
    def __init__(self, message: str, operation: str = "unknown"):
        super().__init__(f"Database error during {operation}: {message}", "DB_ERROR")
        self.operation = operation


class ValidationError(CookingToolError):
    """Input validation errors."""
    def __init__(self, field: str, message: str):
        super().__init__(f"Validation error for '{field}': {message}", "VALIDATION_ERROR")
        self.field = field


class CalculationError(CookingToolError):
    """Calculation errors."""
    def __init__(self, calculation_type: str, message: str):
        super().__init__(f"Calculation error in {calculation_type}: {message}", "CALC_ERROR")
        self.calculation_type = calculation_type


class ConfigurationError(CookingToolError):
    """Configuration errors."""
    def __init__(self, config_key: str, message: str):
        super().__init__(f"Configuration error for '{config_key}': {message}", "CONFIG_ERROR")
        self.config_key = config_key


# =============================================================================
# ERROR HANDLING DECORATORS
# =============================================================================

def handle_database_errors(operation_name: str = "database operation"):
    """Decorator to handle database errors in functions.
    
    Usage:
        @handle_database_errors("fetching user data")
        def get_user(user_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Database error in {operation_name}: {str(e)}", exc_info=True)
                raise DatabaseError(str(e), operation_name)
        return wrapper
    return decorator


def handle_calculation_errors(calculation_type: str = "calculation"):
    """Decorator to handle calculation errors.
    
    Usage:
        @handle_calculation_errors("energy consumption")
        def calculate_energy(data):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except CookingToolError:
                raise  # Re-raise our custom errors
            except Exception as e:
                logger.error(f"Calculation error in {calculation_type}: {str(e)}", exc_info=True)
                raise CalculationError(calculation_type, str(e))
        return wrapper
    return decorator


def api_error_handler(func: Callable) -> Callable:
    """Decorator for API endpoints to return JSON errors.
    
    Usage:
        @app.route('/api/data')
        @api_error_handler
        def get_data():
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            logger.warning(f"Validation error: {e.message}")
            return jsonify({
                'error': True,
                'code': e.code,
                'message': e.message,
                'field': e.field
            }), 400
        except DatabaseError as e:
            logger.error(f"Database error: {e.message}")
            return jsonify({
                'error': True,
                'code': e.code,
                'message': 'A database error occurred. Please try again.'
            }), 500
        except CookingToolError as e:
            logger.error(f"Application error: {e.message}")
            return jsonify({
                'error': True,
                'code': e.code,
                'message': e.message
            }), 500
        except Exception as e:
            logger.exception(f"Unexpected error in API: {str(e)}")
            return jsonify({
                'error': True,
                'code': 'INTERNAL_ERROR',
                'message': 'An unexpected error occurred.'
            }), 500
    return wrapper


def web_error_handler(redirect_to: str = 'index', flash_errors: bool = True):
    """Decorator for web routes to handle errors gracefully.
    
    Usage:
        @app.route('/submit', methods=['POST'])
        @web_error_handler(redirect_to='household_profile')
        def submit_household():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except ValidationError as e:
                if flash_errors:
                    flash(f'Validation error: {e.message}', 'danger')
                return redirect(url_for(redirect_to))
            except DatabaseError as e:
                logger.error(f"Database error: {e.message}")
                if flash_errors:
                    flash('A database error occurred. Please try again.', 'danger')
                return redirect(url_for(redirect_to))
            except CookingToolError as e:
                logger.error(f"Application error: {e.message}")
                if flash_errors:
                    flash(e.message, 'danger')
                return redirect(url_for(redirect_to))
            except Exception as e:
                logger.exception(f"Unexpected error: {str(e)}")
                if flash_errors:
                    flash('An unexpected error occurred. Please try again.', 'danger')
                return redirect(url_for(redirect_to))
        return wrapper
    return decorator


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_required(data: dict, required_fields: list, field_names: Optional[dict] = None) -> None:
    """Validate that required fields are present in data.
    
    Args:
        data: Dictionary of form data
        required_fields: List of required field keys
        field_names: Optional mapping of field keys to human-readable names
        
    Raises:
        ValidationError: If a required field is missing
    """
    field_names = field_names or {}
    for field in required_fields:
        if field not in data or data[field] is None or str(data[field]).strip() == '':
            name = field_names.get(field, field.replace('_', ' ').title())
            raise ValidationError(field, f"{name} is required")


def validate_numeric(value: Any, field_name: str, 
                     min_val: Optional[float] = None, 
                     max_val: Optional[float] = None) -> float:
    """Validate and convert a numeric value.
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        min_val: Optional minimum value
        max_val: Optional maximum value
        
    Returns:
        float: The validated numeric value
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValidationError(field_name, f"{field_name} must be a number")
    
    if min_val is not None and num < min_val:
        raise ValidationError(field_name, f"{field_name} must be at least {min_val}")
    
    if max_val is not None and num > max_val:
        raise ValidationError(field_name, f"{field_name} must be at most {max_val}")
    
    return num


def validate_choice(value: Any, field_name: str, valid_choices: list) -> Any:
    """Validate that a value is one of the valid choices.
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        valid_choices: List of valid choices
        
    Returns:
        The validated value
        
    Raises:
        ValidationError: If value is not in valid_choices
    """
    if value not in valid_choices:
        raise ValidationError(
            field_name, 
            f"{field_name} must be one of: {', '.join(str(c) for c in valid_choices)}"
        )
    return value


# =============================================================================
# SAFE OPERATION UTILITIES
# =============================================================================

def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        float: Converted value or default
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        int: Converted value or default
    """
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_get(dictionary: dict, *keys, default: Any = None) -> Any:
    """Safely get nested dictionary values.
    
    Usage:
        value = safe_get(data, 'fuel_details', 'lpg', 'cost', default=0)
    
    Args:
        dictionary: The dictionary to search
        *keys: Keys to access in order
        default: Default value if any key is missing
        
    Returns:
        The value at the nested key path, or default
    """
    result = dictionary
    for key in keys:
        try:
            result = result[key]
        except (KeyError, TypeError, IndexError):
            return default
    return result
