@echo off
TITLE Eco-Loop Building Agents — Demonstration Launcher
CLS
COLOR 0A

echo =================================================================───────────────
echo         ECO-LOOP BUILDING AGENTS: AUTONOMOUS ENERGYPLUS HVAC SYSTEM
echo =================================================================───────────────
echo.
echo [1/3] Checking environment & virtual environment setup...

IF EXIST "venv\Scripts\python.exe" (
    SET PYTHON_EXEC=venv\Scripts\python.exe
) ELSE (
    SET PYTHON_EXEC=python
)

echo [2/3] Using Python interpreter: %PYTHON_EXEC%
echo [3/3] Launching automated live terminal demonstration...
echo.
echo =================================================================───────────────
echo.

%PYTHON_EXEC% scripts\run_terminal_demo.py

echo.
echo Demonstration completed successfully! Press any key to exit.
pause > nul
