@echo off
title MASQPro Release Manager
color 0B

cd /d "%~dp0"

:MENU
cls
echo.
echo ==========================================
echo         MASQPro Release Manager
echo ==========================================
echo.
echo  [1] Patch Release
echo  [2] Minor Release
echo  [3] Major Release
echo.
echo  [4] Build Only
echo.
echo  [5] Exit
echo.
set /p choice=Select an option: 

if "%choice%"=="1" goto PATCH
if "%choice%"=="2" goto MINOR
if "%choice%"=="3" goto MAJOR
if "%choice%"=="4" goto BUILD
if "%choice%"=="5" goto END

echo.
echo Invalid option.
timeout /t 2 >nul
goto MENU

:PATCH
echo.
echo Starting PATCH release...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" patch
goto FINISH

:MINOR
echo.
echo Starting MINOR release...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" minor
goto FINISH

:MAJOR
echo.
echo Starting MAJOR release...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" major
goto FINISH

:BUILD
echo.
echo Building project...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" build
goto FINISH

:FINISH

echo.
echo ==========================================
if %ERRORLEVEL% EQU 0 (
    echo Finished successfully.
) else (
    echo Finished with errors.
    echo Error Code: %ERRORLEVEL%
)
echo ==========================================
echo.

pause
goto MENU

:END
exit