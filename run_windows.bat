@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 not found. Install it from python.org and tick "Add to PATH". & pause & exit /b 1)
python -c "import PySide6, spellchecker" 2>nul || (echo Installing PySide6, first run only... & python -m pip install -r requirements.txt)
start "" pythonw run.py %*
