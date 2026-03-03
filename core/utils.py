import os
import json
import pandas as pd
import pandas_ta as ta
import numpy as np
import sys
from datetime import datetime, timedelta
import time
from fpdf import FPDF
import pandas as pd
import pandas_market_calendars as mcal

from dotenv import load_dotenv

# 載入 .env 檔案中的所有變數
load_dotenv()

# 載入日曆
tw_calendar = mcal.get_calendar('XTAI')

# 1. 取得 utils.py 所在的目錄 (即 core 資料夾)
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 往上一層取得專案根目錄 (即 TRADING_PROJECT 資料夾)
project_root = os.path.dirname(current_dir)

# 3. 組合正確路徑 (從根目錄進入 fonts)
FONT_PATH = os.path.join(project_root, 'fonts', 'NotoSansTC-Regular.ttf')

# print(f"字體路徑: {FONT_PATH}")

# --- 參數設定 ---
# 觀察「大單匯集」
DATA_DIRECTORY = r'D:\軟體區\免安裝\MitakeGU\USER\OUT'
BASE_CSV_FILES = [
    # "周轉排行.csv",
    "大單匯集.csv",
    # "大單流入.csv",
    # "成量排行.csv",
    # "漲幅排行.csv",
]
# 全域變數，用來快取讀取的資料
_STOCK_MAP_CACHE = None


# 判斷是否為收盤後
def is_after_close(market: str = 'TSE') -> bool:
    """判斷目前時間是否已超過台股收盤時間 (13:30)。"""
    return datetime.now().time() > datetime.time(13, 30)
    # return False

class PDFReportGenerator(FPDF):
    """繼承 FPDF 類別，用於自訂頁首和頁尾"""
    def __init__(self, report_title="選股報告", *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 將標題存入 self 變數，這樣 header() 才能讀取到
        self.report_title = report_title

        self.chinese_font_loaded = False

        # 1. 嘗試載入字體 (add_font)
        if os.path.exists(FONT_PATH):
            try:
                # 載入字體庫，確保成功
                self.add_font('NotoSans', '', FONT_PATH, uni=True) 
                self.chinese_font_loaded = True # 只有成功時才設為 True
            except Exception as e:
                # 如果這裡拋出錯誤，可能是字體檔案損壞或 fpdf2版本問題
                print(f"❌ NotoSans 字體載入失敗，錯誤: {e}")
        
    def header(self):
        report_date_str = datetime.now().date().strftime('%Y/%m/%d')
        
        # 2. 在 header 內部，設定字體 (set_font)
        if self.chinese_font_loaded:
            self.set_font('NotoSans', '', 16) # 使用載入成功的字體
        else:
            self.set_font('Arial', 'B', 16) # 使用預設字體 (會亂碼)
            print("Warning: 中文字體未載入，報告中的中文可能顯示為方塊。 header")
            
        # 3. 執行 cell 繪製
        self.cell(0, 10, f'{self.report_title} - {report_date_str}', 0, 1, 'C') 
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_daily_signal_report(df: pd.DataFrame, file_path: str, title_text: str):
    """
    產生單日選股訊號報告 (不需要回測參數)，使用 df_result 的欄位。
    
    Args:
        df: 策略分析結果 DataFrame (包含 '股號', '收盤價', '訊號類型', '漲幅%', '站上均價')
        file_path: 完整的輸出路徑和檔案名稱。
    """
    if df.empty:
        print("警告：選股結果為空，跳過 PDF 報表生成。")
        return

    # 1. 建立橫向 PDF (Landscape)
    pdf = PDFReportGenerator(report_title=title_text, orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    # --- 字體設定 ---
    if pdf.chinese_font_loaded:
        pdf.set_font('NotoSans', '', 12)
    else:
        pdf.set_font('Arial', '', 12)
        print("Warning: 中文字體 NotoSansTC-Regular.ttf 不可用，報告將使用 Arial。")
        # 由於載入失敗，我們無法繪製中文，所以直接退出函數
        if not pdf.chinese_font_loaded: 
            return

    # --- 1. 表格設定：同步化欄位與寬度 ---
    if title_text == "ST_4RLow":
        headers = ['股票', '當前價', '關鍵一條線', '漲幅%', '均價', '站上均價', '策略類型']
        col_widths = [30, 30, 40, 30, 30, 20, 80]
    else:
        headers = ['股票', '當前價', '漲幅%', '均價', '站上均價', '策略類型']
        col_widths = [30, 30, 30, 30, 20, 80]
    
    # 表頭繪製
    pdf.set_fill_color(200, 220, 255)
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 10, header, 1, 0, 'C', fill=True)
    pdf.ln()

    # --- 3. 內容繪製：使用動態索引控制 ---
    for index, row in df.iterrows():
        # 使用 cur_idx 來確保 col_widths[cur_idx] 永遠跟著當前輸出的格子走
        cur_idx = 0    
   
        # 股票
        # pdf.cell(col_widths[cur_idx], 10, str(row['symbol']), 1, 0, 'C'); cur_idx += 1
        display_symbol = f"{row['symbol']} {row['stock_name']}"
        pdf.cell(col_widths[cur_idx], 10, display_symbol, 1, 0, 'C'); cur_idx += 1

        # 日期 
        # pdf.cell(col_widths[cur_idx], 10, str(row['date']), 1, 0, 'C'); cur_idx += 1

        # 當前價
        pdf.cell(col_widths[cur_idx], 10, f"{row['Close']:.2f}", 1, 0, 'R'); cur_idx += 1
            
        # 漲幅 (處理顏色)
        perf_str = str(row['change_pct']).replace('%', '').strip()
        try:
            perf = float(perf_str)
        except ValueError:
            perf = 0.0

        if perf > 0:
            pdf.set_text_color(255, 0, 0) # 紅色
        elif perf < 0:
            pdf.set_text_color(0, 128, 0) # 綠色
        
        pdf.cell(col_widths[cur_idx], 10, str(row['change_pct']), 1, 0, 'R')
        pdf.set_text_color(0, 0, 0)
        cur_idx += 1
        
        # 均價
        pdf.cell(col_widths[cur_idx], 10, f"{row['VWAP']:.2f}", 1, 0, 'R'); cur_idx += 1

        # 站上均價
        pdf.cell(col_widths[cur_idx], 10, str(row['above_vwap']), 1, 0, 'C'); cur_idx += 1

        # 策略類型
        pdf.cell(col_widths[cur_idx], 10, str(row['signal_type']), 1, 0, 'L')
        pdf.ln()

    # --- 輸出檔案 ---
    # 確保資料夾存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        pdf.output(file_path)
        print(f"\n✅ PDF 報告已產生: {file_path}")
    except Exception as e:
        print(f"\n❌ 產生 PDF 報告時發生錯誤: {e}")

def get_filtered_csv_stocks(csv_cnt:int = 1) -> set:
    """
    讀取並篩選大單匯集 CSV 檔案，返回符合基礎條件的股票集合。
    這個邏輯適用於所有策略。
    csv_cnt = 1 
    預設為1 代表只讀取大單匯集csv
    大於1的 代表讀取三個 大單匯集csv 成量排行csv
    """
    all_stocks = set()
    
    date_strings = []
    today_str_yyyymmdd = datetime.now().strftime("%Y%m%d")
    date_strings.append(today_str_yyyymmdd)

    if csv_cnt > 1:
        BASE_CSV_FILES.extend(["成量排行.csv"])
        # BASE_CSV_FILES.extend(["成量排行.csv", "漲幅排行.csv"])
    
    # 2. 處理CSV
    for date_str in date_strings:
        for base_name in BASE_CSV_FILES:
            file_name = f"{date_str}_{base_name}"
            full_path = os.path.join(DATA_DIRECTORY, file_name)
            try:
                df = pd.read_csv(
                    full_path, 
                    skiprows=3, 
                    usecols=[2, 3, 5, 6], # C, D, F, G 欄 (索引 2, 3, 5, 6) 代號、產業別、成交量、成交
                    names=['Symbol', 'Industry', 'Volume', 'Price'], # 給予對應的欄位名稱
                    encoding='utf-8'
                )
                # --- 基礎篩選 ---
                df.dropna(subset=['Symbol', 'Industry', 'Volume', 'Price'], inplace=True)
                
                # --- 兩個排除條件 ---
                # 條件一：排除 ETF 和存託憑證
                exclusion_list = ['ETF', '存託憑證', '金融保險', '公司債']
                df = df[~df['Industry'].isin(exclusion_list)]
                
                # 條件二：排除成交量小於 3000 張的股票
                volume_threshold = 3000
                df = df[df['Volume'] >= volume_threshold]

                # 條件三：排除成交金額小於 1億 的股票
                value_threshold = 100000000
                df = df[df['Volume'] * 1000 * df['Price'] >= value_threshold]
                
                if not df.empty:
                    valid_stocks = df['Symbol'].astype(int).astype(str).str.zfill(4).tolist()
                    all_stocks.update(valid_stocks)

                print(f"  > 從 '{file_name}' 讀取 {len(valid_stocks)} 支股票。")
            except FileNotFoundError:
                print(f"  > 警告：找不到檔案 '{file_name}'，已跳過。")
            except Exception as e:
                print(f"  > 處理 '{file_name}' 時發生錯誤: {e}")
            
    watchlist = sorted(list(all_stocks))
    # print(f"基礎觀察名單建立完畢，共 {len(watchlist)} 支股票。")
    return watchlist

def get_user_defined_list(runtime_list: list = None) -> set:
    """
    獲取使用者輸入的必選名單 (集合 Set)。
    """
    
    sector_stocks = [
        '2330',
    ]

    final_list = set(sector_stocks)

    # 合併運行時從使用者互動中獲得的名單
    if runtime_list:
        final_list.update(set(runtime_list)) # 確保 runtime_list 是可迭代的
        
    return final_list

# --- 台灣三竹系統專用 KD 計算函式 ---
def calculate_taiwan_kd(df, length=9):
    """
    計算台灣券商常用的 KD 指標 (N=9, 1/3權重)
    公式: K = 2/3 * PreK + 1/3 * RSV
    """
    # 1. 計算 RSV (Row Stochastic Value)
    # 取最近 N 天的最低價與最高價
    low_min = df['Low'].rolling(window=length).min()
    high_max = df['High'].rolling(window=length).max()
    
    # RSV 公式: (今日收盤 - 最近N天最低) / (最近N天最高 - 最近N天最低) * 100
    # fillna(50) 是為了處理一開始數據不足時的預設值
    rsv = 100 * (df['Close'] - low_min) / (high_max - low_min)
    rsv = rsv.fillna(50)

    # 2. 使用 Pandas 的 ewm (指數加權移動平均) 來模擬 1/3 權重的迭代計算
    # alpha=1/3 對應於公式中的 (1/3) * 新值 + (2/3) * 舊值
    # adjust=False 是關鍵，確保它使用遞迴方式計算
    df['KD_K'] = rsv.ewm(alpha=1/3, adjust=False).mean()
    df['KD_D'] = df['KD_K'].ewm(alpha=1/3, adjust=False).mean()
    
    return df

def is_golden_cross(series_fast: pd.Series, series_slow: pd.Series) -> bool:
    """
    判斷兩條序列 (快線 series_fast, 慢線 series_slow) 是否在最新一期發生金叉。
    
    Args:
        series_fast: 快線序列 (例如 KD_K, MA5, MACD)。
        series_slow: 慢線序列 (例如 KD_D, MA20, MACDs)。
        
    Returns:
        bool: True 表示最新一期發生金叉 (快線從下往上穿越慢線)。
    """
    if len(series_fast) < 2 or len(series_slow) < 2:
        return False
        
    # 取得最新一期 (今天) 的值
    latest_fast = series_fast.iloc[-1]
    latest_slow = series_slow.iloc[-1]
    
    # 取得前一期 (昨天) 的值
    previous_fast = series_fast.iloc[-2]
    previous_slow = series_slow.iloc[-2]
    
    # 判斷金叉條件：
    # 1. 昨天：快線在慢線下方 (快線 < 慢線)
    # 2. 今天：快線在慢線上方 (快線 > 慢線)
    if (previous_fast < previous_slow) and (latest_fast > latest_slow):
        return True
        
    return False

def load_stock_info():
    """讀取本地的股票靜態資訊表"""
    global _STOCK_MAP_CACHE
    if _STOCK_MAP_CACHE is not None:
        return _STOCK_MAP_CACHE

    # 當前檔案所在的目錄 (F:/trading_project/core/)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 組合路徑
    json_path = os.path.join(base_dir, 'stock_info.json')

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            _STOCK_MAP_CACHE = json.load(f)
        return _STOCK_MAP_CACHE
    except FileNotFoundError:
        print("⚠️ 找不到 stock_info.json，請先執行 generate_stock_map.py")
        return {}

def get_stock_name(symbol):
    """輸入代號，回傳中文名稱 (如果找不到回傳代號本身)"""
    info = load_stock_info()
    return info.get(symbol, {}).get('name', symbol)

def get_yf_suffix(symbol):
    """輸入代號，回傳 .TW 或 .TWO (預設回傳 .TW)"""
    info = load_stock_info()
    return info.get(symbol, {}).get('suffix', '.TW')

def calculate_holding_days(start_date, end_date):
    """
    計算持有交易日數 (T+N)
    :param start_date: 建倉日 (字串或 datetime/date)
    :param end_date: 截止日 (通常是今天或昨天)
    :return: int (持有天數，若日期無效回傳 0)
    """
    try:
        # 1. 確保轉成 pandas Timestamp 並正規化 (去除時間，只留日期)
        start = pd.Timestamp(start_date).normalize()
        end = pd.Timestamp(end_date).normalize()
        
        # 2. 防呆：如果截止日比開始日還早 (例如資料錯誤)，回傳 0
        if end < start:
            return 0

        # 3. 計算區間內的開盤日
        # schedule 包含 start_date 和 end_date 本身 (如果有開盤)
        schedule = tw_calendar.schedule(start_date=start, end_date=end)
        
        # 4. 計算邏輯：總開盤日數 - 1
        # 原理：T+0 (當天買) => schedule 只有 1 筆 => 1-1 = 0
        #      T+1 (隔天)   => schedule 有 2 筆 => 2-1 = 1
        days = len(schedule.index) - 1
        
        return max(0, days) # 確保不回傳負數

    except Exception as e:
        print(f"⚠️ 天數計算錯誤 (Start: {start_date}, End: {end_date}): {e}")
        return 0

def check_stock_survival_rules(current_price, current_roi, days_held, ma_data, strategy_name, current_status, pre_close=None):
    """
    持股檢查邏輯。
    整合：硬停損、MA防守、策略分流、殭屍復活、資金效率。
    
    Returns: (is_safe: bool, message: str)
    """

    # ====================================================
    # 0. 天條：絕對硬停損 (Hard Stop)
    # ====================================================
    global_hard_stop = -9.0
    if current_roi <= global_hard_stop:
        return False, f"觸發全局硬停損 ({current_roi:.2f}%)"

    # ====================================================
    # 1. 殭屍復活審查 (WATCH_LIST Resurrection)
    # ====================================================
    if current_status in ['WATCH_LIST', 'RESURRECTED']:
        # 條件 A: 必須站上 MA
        target_ma = 'MA10' if current_roi > 20.0 else 'MA5'
        ref_price = ma_data.get(target_ma)
        if not ref_price or current_price <= ref_price:
            return False, f"維持殭屍：股價仍弱 (低於 {target_ma})"
        
        # 條件 B: 獲利必須翻正 (> 0.6%) -> 防止「弱勢反彈」詐屍
        # 避免那種跌沒破線，但也沒漲上去的爛股一直復活
        if current_roi < 0.6:
            return False, f"復活失敗：雖站上均線但未獲利 ({current_roi:.2f}%)"
        
        return True, f"🧟 復活成功：帶量站上 5MA 且 獲利翻紅"

    # ====================================================
    # 2. 現役防守審查 (Active Defense)
    #    針對 ACTIVE 股票，根據策略類型分流
    # ====================================================
    
    # --- 金叉 ---
    # [T < 5]: 洗盤寬容期 (MA 防守)
    target_ma = 'MA10' if current_roi > 20.0 else 'MA5'
    ref_price = ma_data.get(target_ma)
    
    if ref_price and current_price < ref_price:
        # 雖然破了 5MA，但如果只是小賠 (ROI < 0)，檢查月線保命
        if days_held < 5 and current_roi < 0:
            ma20 = ma_data.get('MA20')
            if ma20 and current_price < ma20:
                return False, "趨勢破壞：5天內跌破月線"
            else:
                return True, "續抱：動能策略洗盤(守住月線)"
        
        # 如果已經賺錢了，或持有超過 5 天 -> 破線就跑
        return False, f"趨勢破壞：跌破 {target_ma}"

    # 資金效率審查
    # 給了 5 天還沒賺1% (ROI < 1.6%) 就換股
    if days_held >= 5 and current_roi < 1.60:
        return False, f"資金效率汰換：T+{days_held} 獲利過低 ({current_roi:.2f}%)"
 
    return True, "續抱：狀態健康"

