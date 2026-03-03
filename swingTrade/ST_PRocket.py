# ST_PRocket.py (多合一策略版)
__version__ = "20260303"

import os
import sys
# 1. 取得目前這個檔案所在的資料夾路徑
# current_dir = os.getcwd() 
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 向上移動一層，找到專案的根目錄 (例如: F:/trading_project)
project_root = os.path.dirname(current_dir) 

# 3. 將專案根目錄添加到 Python 的模組搜尋路徑中
if project_root not in sys.path:
    sys.path.append(project_root)

import importlib
# 1. 確保 core 模組已被載入
if 'core' not in sys.modules:
    import core
    
# 2. 強制重載模組 (開發時使用)
if 'core.fubon_client' in sys.modules:
    importlib.reload(sys.modules['core.fubon_client'])
if 'core.db_handler' in sys.modules:
    importlib.reload(sys.modules['core.db_handler'])
if 'core.utils' in sys.modules:
    importlib.reload(sys.modules['core.utils'])
if 'core.notifier' in sys.modules:
    importlib.reload(sys.modules['core.notifier'])

import pandas as pd
import pandas_ta as ta
from datetime import datetime
from fubon_neo.sdk import FubonSDK
import time
import shutil
import re
from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError
from core.fubon_client import FubonClient
from core.utils import (
    get_filtered_csv_stocks, 
    get_user_defined_list, 
    generate_daily_signal_report, 
    get_stock_name,
    calculate_taiwan_kd, 
    is_golden_cross
)
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.db_handler import dup_sort_save
from core.notifier import send_tg_msg, pdf_to_image_simple, send_tg_photo
import glob # 用來搜尋檔案

# =============================================================================
#  KD金叉 sample
# =============================================================================
def analyze_KD_Golden(daily_kbars_dict):
    """
    策略: KD金叉 demo
    """
    signal_list = []
    signal_date = datetime.now().date().strftime('%Y-%m-%d')

    def _process_single_procket(symbol, df):
        try:            
            latest = local_df.iloc[-1]
            
            # --- 核心篩選判斷 ---
            # KD
            local_df = calculate_taiwan_kd(local_df, length=9)
            is_kd_golden_cross = is_golden_cross(series_fast=local_df['KD_K'], series_slow=local_df['KD_D'])
            
            percent_change = (latest['Close'] - latest['referencePrice']) / latest['referencePrice'] * 100
                        
            if is_kd_golden_cross:
                stock_name_zh = get_stock_name(symbol)
                return {
                    'symbol': symbol,             
                    'stock_name': stock_name_zh,
                    'date': signal_date,          
                    'Close': latest['Close'],     
                    'change_pct': f"{percent_change:.2f}%", 
                    'above_vwap': '是' if latest['Close'] > latest['VWAP'] else '否', 
                    'signal_type': "KD金叉", 
                    'VWAP': latest['VWAP'],         
                    'final_status': 'TRACKING',
                }
        except Exception as e:
            print(f"Error processing {symbol} in PRocket: {e}")
            return None
        return None

    # Parallel Execution
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_symbol = {executor.submit(_process_single_procket, symbol, df): symbol for symbol, df in daily_kbars_dict.items()}
        for future in as_completed(future_to_symbol):
            res = future.result()
            if res:
                signal_list.append(res)

    return signal_list

def validate_liquidity(df, threshold_sheets=3000):
    """
    共用過濾器：檢查流動性是否充足
    :param df: 個股的 K 棒 DataFrame
    :param threshold_sheets: 最低均量門檻 (張數)，預設 3000 張
    :return: (bool, msg) -> (是否通過, 原因)
    """
    if df is None or df.empty or len(df) < 20:
        return False, "❌ 資料不足 20 天，無法計算均量"

    # 1. 計算成交量均線 (5日, 10日, 20日)
    # 注意：pandas_ta 預設 close='close'，算量要指定 close='Volume'
    # 這裡我們不一定要 append 到 df 裡汙染原始資料，直接算出來判斷即可
    vol_sma5 = df['Volume'].rolling(5).mean().iloc[-1]
    vol_sma10 = df['Volume'].rolling(10).mean().iloc[-1]
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]

    # 2. 單位轉換 (假設資料庫存的是 '股'，1張 = 1000股)
    # 如果你的資料庫存的是 '張'，就不用 * 1000
    threshold_shares = threshold_sheets * 1000 

    # 3. 判斷邏輯：寬鬆版 (只要其中一條均線達標就算過)
    # 波段操作建議看 5日 (熱度) 或 20日 (穩定度)
    pass_5ma = vol_sma5 >= threshold_shares
    pass_10ma = vol_sma10 >= threshold_shares
    pass_20ma = vol_sma20 >= threshold_shares

    if pass_5ma or pass_10ma or pass_20ma:
        # 詳細一點可以回傳是哪條線過了
        return True, f"✅ 流動性充足 (5MA:{int(vol_sma5/1000)}張, 20MA:{int(vol_sma20/1000)}張)"
    else:
        return False, f"❌ 流動性不足 (均量皆未達 {threshold_sheets} 張)"

def move_old_reports(report_folder_path):
    """
    將指定資料夾中，日期早於「今天」的 PDF 報表移動到 old 資料夾。
    """
    # 1. 確保 old 資料夾存在
    archive_dir = os.path.join(report_folder_path, "old")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
        print(f"📁 建立歸檔資料夾: {archive_dir}")

    # 2. 取得今天的日期字串 (格式: YYYYMMDD，例如 20260130)
    today_str = datetime.now().strftime('%Y%m%d')
    
    print(f"🧹 開始清理舊報表 (保留 {today_str}，其餘歸檔)...")
    
    count = 0
    # 3. 掃描資料夾
    for filename in os.listdir(report_folder_path):
        # 只處理 PDF 檔
        if filename.endswith(".pdf"):
            # 使用正規表達式抓取檔名中的日期 (假設格式為 _YYYYMMDD.pdf)
            match = re.search(r'_(\d{8})\.pdf$', filename)
            
            if match:
                file_date_str = match.group(1)
                
                # 4. 比較日期：如果檔案日期 < 今天 (字串比較即可，因為是 YYYYMMDD 格式)
                if file_date_str < today_str:
                    src_path = os.path.join(report_folder_path, filename)
                    dst_path = os.path.join(archive_dir, filename)
                    
                    try:
                        # 如果 old 裡面已經有同名檔案，shutil.move 可能會報錯或覆蓋，
                        # 這裡簡單處理，直接移動
                        shutil.move(src_path, dst_path)
                        print(f"   📦 已歸檔: {filename}")
                        count += 1
                    except Exception as e:
                        print(f"   ❌ 移動失敗 {filename}: {e}")

    print(f"✨ 清理完成，共歸檔 {count} 個舊報表。")


if __name__ == "__main__":
    print(f"version : {__version__}")
    today_str = datetime.now().date().strftime('%Y%m%d')

    # 確保 /out/reports 資料夾存在
    OUTPUT_DIR = os.path.join(current_dir, 'out', 'reports') 
    os.makedirs(OUTPUT_DIR, exist_ok=True) 

    try:
        client = FubonClient()
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit() # 登入失敗時強制退出

    # --- 1. 準備選股池 (所有策略共用) ---
    # 1.1 獲取用戶互動輸入名單 (這邊設為空，或你可以開啟互動功能)
    user_input_stocks = get_user_defined_list([]) 
    
    # 1.2 獲取 CSV 基礎名單 (大單匯集篩選)
    csv_stocks = get_filtered_csv_stocks(1) # 原先是3  成量改用api
    
    # 獲取盤中強勢股名單
    # print("--- 正在獲取當日盤中強勢股名單 (成交額/漲幅) ---")
    strong_intraday_stocks = client.find_intraday_strong_stocks()
    # print(f"✅ 找到 {len(strong_intraday_stocks)} 支當日強勢股。")

    # 1.3 建立總掃描池：合併所有來源，確保唯一性
    total_scan_pool = user_input_stocks.union(csv_stocks).union(set(strong_intraday_stocks))

    # 篩選：排除不能當沖
    final_watchlist = client.filter_daytrade_stocks(sorted(list(total_scan_pool)))

    print(f"總數據擷取目標池 (用戶輸入 + CSV + 排行榜) 共 {len(final_watchlist)} 檔。")
   
    if not final_watchlist:
        print("總觀察名單為空，程式結束。")
        sys.exit()

    # --- 2. 批次抓取資料 (只做一次！) ---
    print(f"\n🚀 開始批次抓取 {len(final_watchlist)} 檔股票的 K 棒資料...")
    daily_kbars_data_dict = client.fetch_daily_kbars_with_today(final_watchlist)    
    print("✅ 資料抓取完畢，開始執行多策略運算...\n")

    # ==========================================
    # 排除流動性差的
    # ==========================================
    print(f"🌊 正在執行流動性過濾 (過濾標準: 均量 >= 3000 張)...")
    
    qualified_dict = {}
    removed_count = 0

    for symbol, df in daily_kbars_data_dict.items():
        is_liquid, msg = validate_liquidity(df, threshold_sheets=3000)
        
        if is_liquid:
            qualified_dict[symbol] = df
        else:
            removed_count += 1

    # 用「過濾後的乾淨資料」取代原本的資料字典
    daily_kbars_data_dict = qualified_dict
    
    # --- 3. 執行策略與產出報告 ---
    # ==========================================
    # KD金叉 sample
    # ==========================================
    combined_signals = [] # 用來裝所有策略的結果

    # 執行 Pocket Rocket 策略
    print(f"\n--- 正在分析策略: KD金叉sample ---")
    signals_pr = analyze_KD_Golden(daily_kbars_data_dict)
    if signals_pr:
        combined_signals.extend(signals_pr)
        print(f"   ✅ [KD_Golden] 找到 {len(signals_pr)} 檔訊號。")
    else:
        print("   ⚠️ [KD_Golden] 今日無訊號。")

    # ==========================================
    # 3. 統一存檔與產出報告 (主策略 - 剔除漲停後)
    # ==========================================
    if combined_signals:
        df_combined = pd.DataFrame(combined_signals)
        dup_sort_save(df_combined, "ST_KD_Golden")
                
        # 產出「合併版」PDF 報告
        file_name = f'ST_KD_Golden_{today_str}.pdf' 
        file_path = os.path.join(OUTPUT_DIR, file_name)
        
        generate_daily_signal_report(df_combined, file_path, 'ST_KD_Golden')
        
        print(f"\n🎉 報告整合完成！共 {len(combined_signals)} 檔訊號，已產出至 {file_name}")
    else:
        print("\n😴 今日 KD 金叉無訊號。")

    # 執行歸檔清理
    move_old_reports(OUTPUT_DIR)

    print("\n" + "="*50)

    # ==========================================
    # 🚀 Telegram 通知發送區
    # ==========================================
    print("\n🚀 準備發送 Telegram 通知...")
    
    # 1. 準備文字摘要
    count_combined = len(combined_signals) if combined_signals else 0
    
    summary_msg = (
        f"✅ **{today_str} 選股策略報告**\n\n"
        f"🚀 **KD金叉**：{count_combined} 檔\n"
        "內容請查看圖片 👇"
    )
    
    # 發送文字訊息
    send_tg_msg(summary_msg)
    
    # 2. 發送 PDF 檔案 (批次發送)
    # 使用 glob 搜尋今天產生的所有 PDF
    pdf_pattern = os.path.join(OUTPUT_DIR, f"ST_*{today_str}.pdf")
    pdf_files = glob.glob(pdf_pattern)
    
    if pdf_files:
        for pdf_path in pdf_files:
            file_name = os.path.basename(pdf_path)
            print(f" 🖼️ 正在處理: {file_name} ...")
            
            # 1. 轉成預覽圖
            img_path = pdf_to_image_simple(pdf_path)
            
            # 2. 只發送圖片 (Send Photo Only)
            if img_path and os.path.exists(img_path):
                print(f"   📤 發送預覽圖...")
                
                caption_text = (
                    f"📸 {file_name}"
                )
                
                send_tg_photo(img_path, caption=caption_text)
                
                # 傳完刪除暫存的圖片
                try:
                    os.remove(img_path)
                except:
                    pass
            
            # print(f"   📄 發送完整 PDF...")
            # send_tg_file(pdf_path, caption=f"📊 完整報告下載")
        
        send_tg_msg(f"✅ 報告傳送完成！ \n", parse_mode=None)
    else:
        print(" ⚠️ 找不到今日產生的 PDF 報告。")
        send_tg_msg("⚠️ 系統回報：今日無產出任何 PDF 報告。")

    print("\n" + "="*50)
    print("🎉 全部作業完成！")
