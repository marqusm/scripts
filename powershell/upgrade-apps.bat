@echo off
:: Winget Upgrade Script — self-elevates to admin

:: Relaunch elevated if not already admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

winget upgrade --all --accept-source-agreements --accept-package-agreements --include-unknown
pause
