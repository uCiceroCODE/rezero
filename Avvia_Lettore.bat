@echo off
chcp 65001 > nul
title Re:Zero Japanese Light Novel Reader (PC & iPad)
cd /d "%~dp0"
echo Avvio del lettore Re:Zero Japanese Reader in corso...
python run_reader.py
pause
