@echo off
cd /d "%~dp0"
echo Opening EcoCanvas Web App in your browser...
start "" "index.html"
echo If you would like to run a local web server instead:
echo python -m http.server 8000
