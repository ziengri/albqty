@echo off
title Установка зависимостей Albion Fishing QTE
cd /d "%~dp0"
echo Установка необходимых библиотек...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Возникла ошибка при установке библиотек.
) else (
    echo.
    echo Все зависимости успешно установлены!
)
pause
