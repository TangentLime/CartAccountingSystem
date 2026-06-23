@echo off
cd /d C:\NFC-Tracker

:: Start Flask server in a minimized window
start "Cart Tracker Server" /min cmd /k python serverSystem.py

:: Give the server a few seconds to boot
timeout /t 5 /nobreak >nul

:: Launch the dashboard in fullscreen kiosk mode
:: Try Chrome first, fall back to Edge
where chrome >nul 2>nul
if %errorlevel%==0 (
    start chrome --kiosk --noerrdialogs --disable-infobars ^
                 --ignore-certificate-errors --no-first-run ^
                 "https://localhost:5000/"
) else (
    start msedge --kiosk "https://localhost:5000/" ^
                 --edge-kiosk-type=fullscreen ^
                 --no-first-run ^
                 --ignore-certificate-errors
)