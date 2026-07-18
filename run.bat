@echo off
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting PlayMate Flask server on http://localhost:5000
python app.py
pause
