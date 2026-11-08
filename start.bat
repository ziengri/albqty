@echo off
title Albion Fishing QTE Assistant
cd /d "%~dp0"
python app.py
if errorlevel 1 (
    echo.
    echo Ошибка при запуске скрипта. Нажмите любую клавишу для выхода...
    pause >nul
)
