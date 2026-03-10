@echo off
REM Windows batch script to compile translation files
echo Compiling translation files...
echo.

REM Check if Babel is installed
python -c "import babel" 2>nul
if errorlevel 1 (
    echo Babel is not installed. Installing...
    pip install Babel
    if errorlevel 1 (
        echo Failed to install Babel. Please install manually: pip install Babel
        pause
        exit /b 1
    )
)

REM Compile English translations
echo Compiling English translations...
pybabel compile -d translations -l en
if errorlevel 1 (
    echo Failed to compile English translations
    pause
    exit /b 1
)

REM Compile Malayalam translations
echo Compiling Malayalam translations...
pybabel compile -d translations -l ml
if errorlevel 1 (
    echo Failed to compile Malayalam translations
    pause
    exit /b 1
)

echo.
echo ======================================
echo Translation compilation successful!
echo ======================================
echo.
echo You can now run the application:
echo    python app.py
echo.
pause
