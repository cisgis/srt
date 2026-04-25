@echo off
setlocal enabledelayedexpansion

REM ===== CONFIG =====
set "SOURCE_DIR=D:\Documents\Career\APT\srt"
set "DB_FILE=srt.db"
set "UPLOADS_DIR=%SOURCE_DIR%\data\uploads"
set "BACKUP_DIR=C:\Users\YourName\Documents\SRT_Backups"
set "LOG_DIR=%BACKUP_DIR%\logs"
set "RETENTION_DAYS=30"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "DATE=%%i"
set "TIMESTAMP=%DATE%_000000"
set "BACKUP_FILE=srt_full_%DATE%.zip"
set "LOG_FILE=%LOG_DIR%\backup_%DATE%.log"

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ======================================= > "%LOG_FILE%"
echo Backup started: %date% %time% >> "%LOG_FILE%"

set "FAILED=0"

REM ===== BACKUP DATABASE =====
set "DB_BACKUP=srt.db"
if exist "%SOURCE_DIR%\data\%DB_FILE%" (
    echo Backing up database... >> "%LOG_FILE%"
    copy "%SOURCE_DIR%\data\%DB_FILE%" "%BACKUP_DIR%\%DB_BACKUP%" >nul
    if errorlevel 1 (
        echo   ERROR: DB copy failed >> "%LOG_FILE%"
        set "FAILED=1"
    ) else (
        echo   OK: %DB_FILE% >> "%LOG_FILE%"
    )
) else (
    echo   WARNING: DB not found at %SOURCE_DIR%\data\%DB_FILE% >> "%LOG_FILE%"
)

REM ===== CREATE ZIP ARCHIVE =====
set "ZIP_TEMP=%BACKUP_DIR%\.temp_%DATE%"
if exist "%ZIP_TEMP%" rmdir /s /q "%ZIP_TEMP%"
mkdir "%ZIP_TEMP%"

if exist "%BACKUP_DIR%\%DB_BACKUP%" (
    copy "%BACKUP_DIR%\%DB_BACKUP%" "%ZIP_TEMP%\" >nul
    del "%BACKUP_DIR%\%DB_BACKUP%" >nul 2>&1
)

if exist "%UPLOADS_DIR%" (
    echo Backing up uploads folder... >> "%LOG_FILE%"
    robocopy "%UPLOADS_DIR%" "%ZIP_TEMP%\uploads" /E >nul 2>&1
    echo   OK: uploads\ included >> "%LOG_FILE%"
) else (
    echo   WARNING: uploads folder not found >> "%LOG_FILE%"
)

echo Creating archive: %BACKUP_FILE% >> "%LOG_FILE%"
powershell -NoProfile -Command "Compress-Archive -Path '%ZIP_TEMP%\*' -DestinationPath '%BACKUP_DIR%\%BACKUP_FILE%' -Force"

if exist "%BACKUP_DIR%\%BACKUP_FILE%" (
    for %%A in ("%BACKUP_DIR%\%BACKUP_FILE%") do echo   Archive size: %%~zA bytes >> "%LOG_FILE%"
) else (
    echo   ERROR: Archive creation failed >> "%LOG_FILE%"
    set "FAILED=1"
)

rmdir /s /q "%ZIP_TEMP%"

REM ===== RETENTION CLEANUP =====
echo. >> "%LOG_FILE%"
echo Cleaning backups older than %RETENTION_DAYS% days... >> "%LOG_FILE%"
forfiles /p "%BACKUP_DIR%" /m srt_full_*.zip /d -%RETENTION_DAYS% /c "cmd /c del @path" >> "%LOG_FILE%" 2>&1

echo. >> "%LOG_FILE%"
echo ======================================= >> "%LOG_FILE%"
if %FAILED%==0 (
    echo Backup completed: %date% %time% >> "%LOG_FILE%"
    echo RESULT: SUCCESS >> "%LOG_FILE%"
    exit /b 0
) else (
    echo Backup completed with errors: %date% %time% >> "%LOG_FILE%"
    echo RESULT: FAILED >> "%LOG_FILE%"
    exit /b 1
)