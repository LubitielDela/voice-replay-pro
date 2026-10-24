@echo off
REM Voice Replay PRO launcher | Author: LubitielDela (https://github.com/LubitielDela)
REM Запуск Voice Replay PRO | Автор: LubitielDela
chcp 65001 >nul

:: Нужны права администратора, иначе горячие клавиши не работают в играх
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Перезапуск в свёрнутом окне
if not "%1"=="min" start /min cmd /c "%~f0" min & exit /b

cd /d "%~dp0"
python voice_replay_pro.py
pause
