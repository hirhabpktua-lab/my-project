@echo off
set DEEPSEEK_API_KEY=sk-086415409ba24a0b8ae7da55ac2f6c98
cd /d "%~dp0backend"
start "" http://localhost:5000
python app.py
pause
