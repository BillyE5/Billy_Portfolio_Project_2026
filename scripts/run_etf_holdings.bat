@echo off
:: 設定編碼為 UTF-8
chcp 65001 >nul
setlocal enabledelayedexpansion

:: 跑 upd_etf_holdings.py


:: ========================================================
:: 0. 設定區域與變數
:: ========================================================
:: 取得腳本所在的資料夾路徑 (最後帶有 \)
set "SCRIPT_DIR=%~dp0"

:: 切換到 bat 所在目錄
cd /d "%SCRIPT_DIR%"

:: ========================================================
:: 1. 環境變數設定
:: ========================================================
:StartTask
set PROJECT_DIR=F:\trading_project
set LOG_DIR=%PROJECT_DIR%\etf_data\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: 取得當前日期 (格式: YYYYMMDD)
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -format 'yyyyMMdd'"') do set TODAY=%%a

:: 設定 Log 檔案名稱
set LOG_FILE=%LOG_DIR%\00981A_%TODAY%.log
set PYTHON_EXE=%PROJECT_DIR%\fubon_venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8

:: 紀錄開始時間到 Log
echo. > "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"
echo [START] %date% %time% >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"


:: ========================================================
:: 2. 開始執行任務
:: ========================================================
cd /d "%PROJECT_DIR%"

:: --------------------------------------------------------
:: 抓 ETF 00981A 差異
:: --------------------------------------------------------
echo [%time%] 抓 00981A 差異 (upd_etf_holdings.py)...
echo [%time%] Running upd_etf_holdings.py... >> "%LOG_FILE%"

"%PYTHON_EXE%" "%PROJECT_DIR%\scripts\upd_etf_holdings.py" >> "%LOG_FILE%" 2>&1

:: 判斷回傳碼
if %errorlevel% neq 0 goto UpdETFFailed

echo [%time%] [OK] 抓 ETF 00981A 差異。 >> "%LOG_FILE%"
goto AllDone

:UpdETFFailed
echo [%time%] [ERROR] upd_etf_holdings.py FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] 抓 ETF 00981A 差異 失敗！
goto ErrorEnd


:: --------------------------------------------------------
:: 結束處理
:: --------------------------------------------------------
:AllDone
echo. >> "%LOG_FILE%"
echo [END] %date% %time% - 抓 ETF 00981A 差異 completed. >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"

echo [OK] 抓 ETF 00981A 差異 completed successfully!
echo.
echo ========================================================
echo       Log Content Preview
echo ========================================================
type "%LOG_FILE%"
timeout /t 60
goto End

:ErrorEnd
echo [END] %date% %time% - 抓 ETF 00981A 差異 by ERROR. >> "%LOG_FILE%"
echo.
echo ========================================================
echo       ERROR LOG
echo ========================================================
type "%LOG_FILE%"
timeout /t 60
exit /b 1

:End
exit /b 0