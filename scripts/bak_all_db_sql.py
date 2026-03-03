import subprocess
import datetime
import os
import sys
import time
from dotenv import load_dotenv
# 1. 載入 .env 檔案中的變數
# 確保 .env 檔案在專案根目錄
load_dotenv() 


# --- 設定區 ---
CONTAINER_NAME = "mysql_fubon_db"
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
RETENTION_DAYS = 14  # 設定保留天數

# 專案路徑 (自動抓當前檔案所在位置)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 動態決定子資料夾 ---
# 如果有傳參數就用參數，否則預設為 "final_done"
sub_dir = sys.argv[1] if len(sys.argv) > 1 else "final_done"
BACKUP_DIR = os.path.join(BASE_DIR, "backups", sub_dir)

def clean_old_backups(directory, days):
    """
    掃描指定資料夾，刪除超過指定天數的 .sql 檔案。
    """
    print(f"🧹 開始清理 {days} 天前的舊備份...")
    now = time.time()
    cutoff = now - (days * 86400)  # 86400 秒 = 1 天

    try:
        count = 0
        for filename in os.listdir(directory):
            if filename.endswith(".sql"):
                filepath = os.path.join(directory, filename)
                # 取得檔案最後修改時間
                file_mtime = os.path.getmtime(filepath)
                
                if file_mtime < cutoff:
                    os.remove(filepath)
                    print(f"🗑️ 已刪除過期檔案: {filename}")
                    count += 1
        print(f"✨ 清理完成，共刪除 {count} 個檔案。")
    except Exception as e:
        print(f"⚠️ 清理過程發生錯誤: {e}")

def backup_database():
    # 1. 確保備份資料夾存在
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    # 2. 產生檔名 (包含日期時間)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{DB_NAME}_backup_{timestamp}.sql"
    filepath = os.path.join(BACKUP_DIR, filename)

    print(f"📦 正在備份資料庫 {DB_NAME} 到 {filepath} ...")

    # 3. 組合 Docker 指令
    # 指令邏輯: docker exec [容器] /usr/bin/mysqldump -u[帳號] -p[密碼] [資料庫] > [本機路徑]
    # 注意：密碼 -p 和密碼中間不能有空格
    command = f"docker exec {CONTAINER_NAME} /usr/bin/mysqldump --default-character-set=utf8mb4 -u {DB_USER} -p{DB_PASSWORD} {DB_NAME} > {filepath}"
    
    # 4. 執行指令 (要在 Shell 模式下執行才能用 > 輸出檔案)
    try:
        # shell=True 允許使用 > 進行檔案導向
        subprocess.run(command, shell=True, check=True)
        
        # 檢查檔案是否真的產生且有內容
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            print(f"✅ 備份成功！檔案大小: {os.path.getsize(filepath)} bytes")

            # --- 備份成功後執行清理 ---
            clean_old_backups(BACKUP_DIR, RETENTION_DAYS)
        else:
            raise Exception("備份檔案建立失敗或為空檔案")
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Docker 指令執行失敗: {e}")
        exit(1) # 回傳錯誤代碼給 .bat 抓
    except Exception as e:
        print(f"❌ 備份過程發生錯誤: {e}")
        exit(1) # 回傳錯誤代碼給 .bat 抓

if __name__ == "__main__":
    backup_database()