#!/usr/bin/env python
"""
Keralam Cooking Energy Analysis Tool - Run Script
=================================================

This script provides easy commands to run and manage the Flask application.

Usage:
    python run.py [command]

Commands:
    run         - Run the development server (default)
    setup       - Setup translations and database
    extract     - Extract messages for translation
    compile     - Compile translation files
    update      - Update existing translations
    clean       - Clean temporary files
    help        - Show this help message

Examples:
    python run.py                    # Run development server
    python run.py setup              # Initial setup
    python run.py extract            # Extract translatable strings
"""

import sys
import os
import subprocess
from pathlib import Path


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def run_command(cmd):
    """Execute a shell command and return the result."""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return False

def setup_translations():
    """Setup initial translations."""
    print("Setting up translations...")
    
    # Create directories if they don't exist
    os.makedirs("translations/en/LC_MESSAGES", exist_ok=True)
    os.makedirs("translations/ml/LC_MESSAGES", exist_ok=True)
    
    # Extract messages
    if run_command("pybabel extract -F babel.cfg -k _ -o messages.pot ."):
        print("✓ Messages extracted")
    
    # Initialize translations if they don't exist
    if not os.path.exists("translations/en/LC_MESSAGES/messages.po"):
        if run_command("pybabel init -i messages.pot -d translations -l en"):
            print("✓ English translations initialized")
    
    if not os.path.exists("translations/ml/LC_MESSAGES/messages.po"):
        if run_command("pybabel init -i messages.pot -d translations -l ml"):
            print("✓ Malayalam translations initialized")
    
    # Compile translations
    if run_command("pybabel compile -d translations"):
        print("✓ Translations compiled")
    
    print("Setup complete!")

def extract_messages():
    """Extract translatable messages."""
    print("Extracting messages...")
    if run_command("pybabel extract -F babel.cfg -k _ -o messages.pot ."):
        print("✓ Messages extracted to messages.pot")

def update_translations():
    """Update existing translations with new messages."""
    print("Updating translations...")
    if run_command("pybabel update -i messages.pot -d translations"):
        print("✓ Translations updated")
        print("Remember to edit .po files and then run 'python run.py compile'")

def compile_translations():
    """Compile translation files."""
    print("Compiling translations...")
    if run_command("pybabel compile -d translations"):
        print("✓ Translations compiled")

def clean_files():
    """Clean temporary files."""
    print("Cleaning temporary files...")
    
    # Remove Python cache
    for root, dirs, files in os.walk("."):
        for dir_name in dirs[:]:
            if dir_name == "__pycache__":
                import shutil
                shutil.rmtree(os.path.join(root, dir_name))
                print(f"Removed {os.path.join(root, dir_name)}")
        for file_name in files:
            if file_name.endswith(('.pyc', '.pyo')):
                os.remove(os.path.join(root, file_name))
                print(f"Removed {os.path.join(root, file_name)}")
    
    # Remove message template
    if os.path.exists("messages.pot"):
        os.remove("messages.pot")
        print("Removed messages.pot")
    
    print("✓ Cleanup complete")

def run_app():
    """Run the Flask development server."""
    host = os.environ.get("FLASK_RUN_HOST") or os.environ.get("HOST") or "0.0.0.0"
    port = int(os.environ.get("FLASK_RUN_PORT") or os.environ.get("PORT") or "5000")
    print("Starting Keralam Cooking Energy Analysis Tool...")
    print(f"Server will be available at: http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    print("-" * 50)
    
    try:
        from app import app
        debug = env_flag("FLASK_DEBUG", bool(app.config.get("DEBUG")))
        app.run(debug=debug, host=host, port=port)
    except ImportError as e:
        print(f"Error importing app: {e}")
        print("Make sure all dependencies are installed: pip install -r requirements.txt")
    except Exception as e:
        print(f"Error starting server: {e}")

def show_help():
    """Show help message."""
    print(__doc__)

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        command = "run"
    else:
        command = sys.argv[1].lower()
    
    commands = {
        "run": run_app,
        "setup": setup_translations,
        "extract": extract_messages,
        "compile": compile_translations,
        "update": update_translations,
        "clean": clean_files,
        "help": show_help
    }
    
    if command in commands:
        try:
            commands[command]()
        except KeyboardInterrupt:
            print("\n\nServer stopped by user")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print(f"Unknown command: {command}")
        print("Use 'python run.py help' for available commands")

if __name__ == "__main__":
    main()
