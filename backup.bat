@echo off
setlocal enabledelayedexpansion

REM ===== CONFIG =====
set "SOURCE_FILE=D:\Documents\Career\APT\srt\data\srt.db"
set "BACKUP_DIR=C:\Users\YourName\Documents\SRT_Backups"
set "LOG_DIR=%BACKUP_DIR%\logs"
set "RETENTION_DAYS=7"

REM ===== GET TIMESTAMP (locale independent) =====
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TIMESTAMP=%%i"

set "BACKUP_FILE=srt_%TIMESTAMP%.db"
set "LOG_FILE=%LOG_DIR%\backup_%TIMESTAMP%.log"

REM ===== PREPARE DIRECTORIES =====
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM ===== START LOG =====
echo ======================================= >> "%LOG_FILE%"
echo Backup started: %date% %time% >> "%LOG_FILE%"
echo Source: %SOURCE_FILE% >> "%LOG_FILE%"
echo Destination: %BACKUP_DIR%\%BACKUP_FILE% >> "%LOG_FILE%"

REM ===== CHECK SOURCE FILE =====
if not exist "%SOURCE_FILE%" (
    echo ERROR: Source file not found! >> "%LOG_FILE%"
    echo Backup FAILED >> "%LOG_FILE%"
    exit /b 1
)

REM ===== COPY USING ROBOCOPY =====
robocopy "%~dp0" "%BACKUP_DIR%" "%~nx0" >nul 2>&1

REM actual copy (single file)
robocopy "%~dp0" "%BACKUP_DIR%" >nul 2>&1

copy "%SOURCE_FILE%" "%BACKUP_DIR%\%BACKUP_FILE%" >nul
if errorlevel 1 (
    echo ERROR: Copy failed! >> "%LOG_FILE%"
    echo Backup FAILED >> "%LOG_FILE%"
    exit /b 1
)

echo Backup successful: %BACKUP_FILE% >> "%LOG_FILE%"

REM ===== RETENTION CLEANUP =====
echo Cleaning backups older than %RETENTION_DAYS% days... >> "%LOG_FILE%"

forfiles /p "%BACKUP_DIR%" /m srt_*.db /d -%RETENTION_DAYS% /c "cmd /c del @path" >> "%LOG_FILE%" 2>&1

echo Cleanup complete >> "%LOG_FILE%"

REM ===== END =====
echo Backup completed: %date% %time% >> "%LOG_FILE%"
echo ======================================= >> "%LOG_FILE%"

exit /b 0