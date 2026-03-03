@echo off
:: 設定編碼為 UTF-8
chcp 65001 >nul
setlocal enabledelayedexpansion

:: 跑 upd_daily_kbars.py 與 pf_tracker.py


:: ========================================================
:: 0. 設定區域與變數
:: ========================================================
:: 取得腳本所在的資料夾路徑 (最後帶有 \)
set "SCRIPT_DIR=%~dp0"

:: 切換到 bat 所在目錄
cd /d "%SCRIPT_DIR%"

:: 1. 取得今日日期 (yyyyMMdd)
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -format 'yyyyMMdd'"') do set TODAY=%%a

:: 2. 設定今天的鎖檔名稱
set "CURRENT_LOCK=%SCRIPT_DIR%daily_job_%TODAY%.lock"

:: ========================================================
:: [自動清理] 刪除非今日的舊鎖檔
:: ========================================================
:: 邏輯：搜尋所有 daily_job_*.lock 如果找到的檔案名稱 "不等於" 今天的鎖檔，就刪除它
:: 會把日期寫在檔名，而非把日期寫在內容，檔名固定是因為bat 讀取，可能有一些問題 會讀取不到日期，而直接閃退
for %%F in ("%SCRIPT_DIR%daily_job_*.lock") do (
    if /i not "%%F"=="%CURRENT_LOCK%" (
        echo [系統] 刪除舊鎖檔: %%F
        del "%%F"
    )
)

:: ========================================================
:: [防呆檢查]
:: ========================================================
:: 3. 檢查今天的檔案是否存在
if exist "%CURRENT_LOCK%" goto StopRun

:: 4. 如果不存在，跳去開始工作
goto StartTask

:: ========================================================
:: [攔截區]
:: ========================================================
:StopRun
echo.
echo ========================================================
echo  [STOP] Prevent Double Run
echo  Lock File Found: %CURRENT_LOCK%
echo  Task for TODAY (%TODAY%) is already done.
echo ========================================================
echo.
echo  Window will close in 30 seconds...
timeout /t 30
exit /b

:: ========================================================
:: 1. 環境變數設定
:: ========================================================
:StartTask
set PROJECT_DIR=F:\trading_project
set LOG_DIR=%PROJECT_DIR%\scripts\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: 取得當前日期 (格式: YYYYMMDD)
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -format 'yyyyMMdd'"') do set TODAY=%%a

:: 設定 Log 檔案名稱
set LOG_FILE=%LOG_DIR%\daily_ops_%TODAY%.log
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
:: 守門員：檢查今日是否開盤
:: --------------------------------------------------------
echo [%time%] 檢查今日是否開盤 (check_market_open.py)...
echo [%time%] Running check_market_open.py... >> "%LOG_FILE%"

"%PYTHON_EXE%" "%PROJECT_DIR%\scripts\check_market_open.py" >> "%LOG_FILE%" 2>&1

:: 判斷回傳碼
if %errorlevel% equ 99 goto MarketClosedSkip
if %errorlevel% neq 0 goto CheckMarketFailed

echo [%time%] [OK] 今日正常開盤，繼續執行後續任務。 >> "%LOG_FILE%"

:: --------------------------------------------------------
:: 啟動 Docker 與資料庫
:: --------------------------------------------------------
echo [%time%] Checking Docker status...
echo [%time%] Checking Docker status... >> "%LOG_FILE%"

:CheckDocker
:: 檢查 Docker 引擎是否回應
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
echo [%time%] Starting MySQL container... >> "%LOG_FILE%"
echo Starting MySQL container...
docker start mysql_fubon_db >> "%LOG_FILE%" 2>&1

echo [%time%] Waiting for DB connection (15s)... >> "%LOG_FILE%"
echo Waiting for DB connection (15s)...
timeout /t 15 /nobreak >nul

goto Step0_PreCalcBackup


:: --------------------------------------------------------
:: 1. 全資料庫備份 (Python: bak_all_db_sql.py)
:: --------------------------------------------------------
:Step0_PreCalcBackup
echo [%time%] Running 1. Pre-Calc DB Backup (bak_all_db_sql.py)... >> "%LOG_FILE%"
echo [%time%] Running Pre-Calc Backup...

:: 呼叫 Python 執行備份腳本
"%PYTHON_EXE%" "%PROJECT_DIR%\scripts\bak_all_db_sql.py" before_calc >> "%LOG_FILE%" 2>&1

:: 檢查回傳值 (Python 腳本若失敗需 raise Exception 或 exit(1))
if %errorlevel% neq 0 goto PreCalcBackupFailed

echo [%time%] [OK] Pre-Calc Backup Success. >> "%LOG_FILE%"
echo [OK] Pre-Calc Backup Success.
goto Step2_Update

:PreCalcBackupFailed
echo [%time%] [ERROR] Pre-Calc bak_all_db_sql.py FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] Pre-Calc Backup Failed!
goto ErrorEnd


:: --------------------------------------------------------
:: 2.資料初始化 (upd_daily_kbars.py)  收盤後抓日K棒到 daily_kbars
:: --------------------------------------------------------
:Step2_Update
echo [%time%] Running 2. Update Daily Kbars (upd_daily_kbars.py)... >> "%LOG_FILE%"
echo [%time%] Running upd_daily_kbars...

"%PYTHON_EXE%" %PROJECT_DIR%\scripts\upd_daily_kbars.py >> "%LOG_FILE%" 2>&1

:: 直接判斷跳轉
if %errorlevel% neq 0 goto UpdateFailed

:: 成功區
echo [%time%] [OK] upd_daily_kbars Success. >> "%LOG_FILE%"
echo [OK] Update Data Success.
goto Step3_Tracker

:UpdateFailed
echo [%time%] [ERROR] upd_daily_kbars FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] Update Data Failed!
goto ErrorEnd

:: --------------------------------------------------------
:: 3. 績效追蹤 (pf_tracker.py)
:: --------------------------------------------------------
:Step3_Tracker
echo [%time%] Running 3. Performance Tracker (pf_tracker.py)... >> "%LOG_FILE%"
echo [%time%] Running pf_tracker...

"%PYTHON_EXE%" %PROJECT_DIR%\scripts\pf_tracker.py >> "%LOG_FILE%" 2>&1

:: 直接判斷跳轉
if %errorlevel% neq 0 goto TrackerFailed

:: 成功區
echo [%time%] [OK] pf_tracker Success. >> "%LOG_FILE%"
echo [OK] Performance Tracker Success.
goto Step4_FullBackup

:TrackerFailed
echo [%time%] [ERROR] pf_tracker FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] Performance Tracker Failed!
goto ErrorEnd

:: --------------------------------------------------------
:: 4. 全資料庫備份 (Python: bak_all_db_sql.py)
:: --------------------------------------------------------
:Step4_FullBackup
echo [%time%] Running 4. Full DB Backup (bak_all_db_sql.py)... >> "%LOG_FILE%"
echo [%time%] Running bak_all_db_sql.py...

:: 呼叫 Python 執行備份腳本
"%PYTHON_EXE%" "%PROJECT_DIR%\scripts\bak_all_db_sql.py" >> "%LOG_FILE%" 2>&1

:: 檢查回傳值 (Python 腳本若失敗需 raise Exception 或 exit(1))
if %errorlevel% neq 0 goto FullBackupFailed

echo [%time%] [OK] Full Backup Success. >> "%LOG_FILE%"
echo [OK] Full Backup Success.
goto AllDone

:FullBackupFailed
echo [%time%] [ERROR] bak_all_db_sql.py FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] Full Backup Failed!
goto ErrorEnd


:: --------------------------------------------------------
:: 休市提早結束處理
:: --------------------------------------------------------
:MarketClosedSkip
:: 休市也算是一種「完成」，所以我們要建立鎖檔，避免排程一直重試
echo Done_Holiday > "%CURRENT_LOCK%"

echo. >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"
echo [END] %date% %time% - [INFO] 台灣股市休市，排程提早結束。 >> "%LOG_FILE%"
echo ======================================================== >> "%LOG_FILE%"

echo [INFO] 今日休市，程式平安結束！
timeout /t 3 >nul
goto End

:: (這用來處理日曆套件壞掉的極端情況)
:CheckMarketFailed
echo [%time%] [ERROR] check_market_open.py FAILED (Code: %errorlevel%) >> "%LOG_FILE%"
echo [ERROR] 股市日曆檢查失敗！
goto ErrorEnd


:: --------------------------------------------------------
:: 結束處理
:: --------------------------------------------------------
:AllDone
:: [任務完成] 建立今天的鎖檔
echo Done > "%CURRENT_LOCK%"
echo [SYSTEM] Lock file created at: %CURRENT_LOCK% >> "%LOG_FILE%"

echo. >> "%LOG_FILE%"
echo [END] %date% %time% - All tasks completed. >> "%LOG_FILE%"
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
:: [注意] 失敗時「不」寫入鎖檔，這樣晚上的排程才有機會重試
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