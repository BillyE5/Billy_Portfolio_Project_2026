@echo off
:: 設定編碼為 UTF-8
chcp 65001 >nul

:: 產三竹 大單匯集csv 跟 選股策略 ST_PRocket.py


:: ========================================================
:: 1. 環境變數設定
:: ========================================================
set PROJECT_DIR=F:\trading_project
set LOG_DIR=%PROJECT_DIR%\automation\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: 取得當前日期 (格式: YYYYMMDD)
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -format 'yyyyMMdd'"') do set TODAY=%%a

:: 設定 Log 檔案名稱
set LOG_FILE=%LOG_DIR%\autoPRocket_%TODAY%.log
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
:: 0. 守門員：檢查今日是否開盤
:: --------------------------------------------------------
echo [%time%] 檢查今日是否開盤 (check_market_open.py)...
echo [%time%] Running check_market_open.py... >> "%LOG_FILE%"

"%PYTHON_EXE%" "%PROJECT_DIR%\scripts\check_market_open.py" >> "%LOG_FILE%" 2>&1

:: 判斷回傳碼
if %errorlevel% equ 99 goto MarketClosedSkip
if %errorlevel% neq 0 goto CheckMarketFailed

echo [%time%] [OK] 今日正常開盤，繼續執行 RPA。 >> "%LOG_FILE%"

:: --------------------------------------------------------
:: Step 1: 執行 Python RPA (產出 CSV) 🤖
:: Robotic Process Automation (機器人流程自動化)
:: --------------------------------------------------------
:Step1_RPA
echo [%time%] 正在操作三竹軟體匯出 CSV...
echo [%time%] [Step 1] Running auto_export_mitake.py... >> "%LOG_FILE%"

"%PYTHON_EXE%" %PROJECT_DIR%\automation\auto_export_mitake.py >> "%LOG_FILE%" 2>&1

:: 檢查回傳值
if %errorlevel% neq 0 goto MitakeCSVFailed

:: 成功區
echo [%time%] [OK] auto_export_mitake.py Success. >> "%LOG_FILE%"
echo [OK] Mitake CSV Export Success.
goto Step2_Docker

:: --------------------------------------------------------
:: 休市
:: --------------------------------------------------------
:MarketClosedSkip
:: 休市也算是一種「完成」，所以我們要建立鎖檔，避免排程一直重試
echo Done_Holiday > "%CURRENT_LOCK%"

echo. >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"
echo [END] %date% %time% - [INFO] 台灣股市休市，排程提早結束。 >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"

echo [INFO] 今日休市，程式平安結束！
:: 停留 3 秒讓手動執行時能看見結果，隨後自動關閉 (加 >nul 可隱藏倒數提示文字)
timeout /t 3 >nul
goto End

:: (這用來處理日曆套件壞掉的極端情況)
:CheckMarketFailed
echo [%time%] [ERROR] check_market_open.py FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] 股市日曆檢查失敗！
goto ErrorEnd

:MitakeCSVFailed
echo [%time%] [ERROR] auto_export_mitake.py FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] Mitake CSV Export Failed! 請檢查 Log。
goto ErrorEnd

:: --------------------------------------------------------
:: Step 2: 啟動 Docker 與資料庫 🐳
:: --------------------------------------------------------
:Step2_Docker
echo [%time%] Checking Docker status...
echo [%time%] [Step 2] Checking Docker status... >> "%LOG_FILE%"

:CheckDocker
:: 檢查 Docker 引擎是否回應 (防止 Docker Desktop 根本沒開)
docker info >nul 2>&1
if %errorlevel% equ 0 goto DockerIsReady

echo [%time%] [WARN] Docker Desktop not running, trying to start... >> "%LOG_FILE%"
echo [WARN] Docker Desktop not running, starting...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

:WaitForDocker
:: 進入迴圈等待，每 5 秒檢查一次，直到 Docker 醒來
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if %errorlevel% equ 0 goto DockerStarted
echo [%time%] Waiting for Docker init... >> "%LOG_FILE%"
echo Waiting for Docker init...
goto WaitForDocker

:DockerStarted
echo [%time%] [OK] Docker engine started. >> "%LOG_FILE%"

:DockerIsReady
echo [%time%] Docker is ready. Starting MySQL container... >> "%LOG_FILE%"
echo Starting MySQL container...

:: 啟動資料庫容器 (如果已經是 Up 狀態，docker start 也不會報錯，很安全)
docker start mysql_fubon_db >> "%LOG_FILE%" 2>&1

echo [%time%] Waiting for DB connection (15s)... >> "%LOG_FILE%"
echo Waiting for DB connection (15s)...
timeout /t 15 /nobreak >nul

:: --------------------------------------------------------
:: 選股策略 (ST_PRocket.py)
:: --------------------------------------------------------
:Step3_Strategy
echo [%time%] Running Stock Strategy (ST_PRocket.py)... >> "%LOG_FILE%"
echo [%time%] Running ST_PRocket...

"%PYTHON_EXE%" %PROJECT_DIR%\swingTrade\ST_PRocket.py >> "%LOG_FILE%" 2>&1

:: 檢查回傳值
if %errorlevel% neq 0 goto PRocketFailed

:: 成功區
echo [%time%] [OK] ST_PRocket Success. >> "%LOG_FILE%"
echo [OK] ST_PRocket Success.
goto AllDone

:PRocketFailed
echo [%time%] [ERROR] ST_PRocket FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] ST_PRocket Failed!
goto ErrorEnd


:: --------------------------------------------------------
:: 結束處理
:: --------------------------------------------------------
:AllDone
echo. >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"
echo [END] %date% %time% - All tasks completed successfully. >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"

echo [OK] All tasks completed successfully!
echo.
echo ========================================================
echo       Log Content Preview
echo ========================================================
type "%LOG_FILE%"
timeout /t 60
goto End

:ErrorEnd
echo [END] %date% %time% - Task Interrupted by ERROR. >> "%LOG_FILE%"
echo.
echo ========================================================
echo       ERROR LOG
echo ========================================================
type "%LOG_FILE%"
timeout /t 60
exit /b 1



:End
exit /b 0