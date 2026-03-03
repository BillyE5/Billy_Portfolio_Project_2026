# upd_daily_kbars.py
# python .\scripts\upd_daily_kbars.py
# 收盤後執行 
# 根據CSV檔案 與 已存在daily_kbars 的股票名單 取得今天的 日K棒 寫入到 daily_kbars

import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

# --- 路徑設定 ---
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from core.utils import get_filtered_csv_stocks, get_yf_suffix, get_stock_name
    from core.db_handler import save_kbars_to_db, get_existing_symbols_in_db
except ImportError as e:
    print(f"❌ 匯入錯誤: {e}")
    sys.exit(1)

def initialize_data():
    print("啟動資料初始化程序 (讀取 JSON 對照表模式)...")
    
    # 1. 獲取股票名單 (CSV + 資料庫同步)
    try:
        csv_stocks = set(get_filtered_csv_stocks())
        db_stocks = set(get_existing_symbols_in_db())
        
        stock_list = sorted(list(csv_stocks | db_stocks))

        if not stock_list:
            print("⚠️ 名單為空，程式結束。")
            return

        print(f"📋 從 CSV + 資料庫同步 讀取到 {len(stock_list)} 支股票。")
    except Exception as e:
        print(f"❌ 讀取 CSV 名單失敗: {e}")
        return

    # 2. 準備 yfinance 代號
    symbol_to_ticker = {}
    download_list = []
    for symbol in stock_list:
        suffix = get_yf_suffix(symbol) # 這裡會去讀 stock_info.json
        ticker = f"{symbol}{suffix}"
        
        symbol_to_ticker[symbol] = ticker
        download_list.append(ticker)
    
    print(f"📥 準備從 yfinance 下載 {len(download_list)} 檔資料...")
    
    try:
        # 批次下載
        all_data = yf.download(
            download_list, 
            period="4mo", # 文件寫3mo 或6mo 不過測試有4mo
            interval="1d", 
            group_by='ticker', 
            auto_adjust=True, 
            progress=True,
            threads=True # yfinance 內部的下載可以用多執行緒，因為這是對網路，不影響 DB
        )
        
        if all_data.empty:
            print("❌ yfinance 下載失敗，回傳為空。")
            return

        print("\n🔄 開始處理並寫入資料庫...")
        success_count = 0
        fail_count = 0

        # 3. 逐一處理
        for symbol in stock_list:
            try:
                target_ticker = symbol_to_ticker[symbol]
                df = pd.DataFrame()

                if target_ticker in all_data.columns.levels[0]:
                    df = all_data[target_ticker].copy()

                # 基本檢查：是否全空
                if df.empty or df.dropna(how='all').empty:
                    # print(f"⚠️ {symbol} 無資料")
                    fail_count += 1
                    continue

                # --- 資料清洗 ---
                df = df.reset_index()
                df.rename(columns={'Date': 'date'}, inplace=True)
                
                # 移除時區
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                
                df['symbol'] = symbol
                df['stock_name'] = get_stock_name(symbol)
                
                # 去除空值列
                df = df.dropna(subset=['Close'])

                # 寫入 DB
                if not df.empty:
                    save_kbars_to_db(df)
                    success_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                print(f"❌ 處理 {symbol} 時發生錯誤: {e}")
                fail_count += 1

        print("\n" + "="*40)
        print(f"🎉 初始化完成！")
        print(f"✅ 成功寫入: {success_count} 檔")
        print(f"❌ 失敗/無資料: {fail_count} 檔")
        print("="*40)

    except Exception as e:
        print(f"❌ 下載過程發生致命錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    initialize_data()