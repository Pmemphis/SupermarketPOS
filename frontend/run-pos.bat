@echo off
title NextGen UltraPOS Desktop Workstation
echo Force-closing background terminal threads...

:: Kill any hidden or dangling Edge processes to force-apply the new flags
taskkill /f /im msedge.exe >nul 2>&1

echo Waking UltraPOS Desktop Layer Offline...

:: Launches Edge in App Mode, isolates the session, and enforces immediate hardware printing
start msedge.exe --app="file:///C:/Users/Administrator/SupermarketPOS/frontend/index.html" --window-size=1200,800 --kiosk-printing --user-data-dir="C:\Users\Administrator\SupermarketPOS\pos-profile"

exit