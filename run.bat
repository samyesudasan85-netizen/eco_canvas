@echo off
cd /d "%~dp0"
echo Starting EcoCanvas...
.\.venv\Scripts\python.exe -m streamlit run app.py
pause
