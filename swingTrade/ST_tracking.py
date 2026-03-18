# fubon_venv 執行 streamlit run .\swingTrade\ST_tracking.py
# streamlit

import pandas as pd
from datetime import datetime, date, time as dt_time, timedelta
import time
import sys
import os
import streamlit as st
import numpy as np
import pandas_market_calendars as mcal
from sqlalchemy import text

# --- 路徑設定 ---
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)
from core.fubon_client import FubonClient
from core.db_handler import _read_dataframe_from_sql, close_trade_signal
from core.utils import calculate_holding_days
from streamlit_autorefresh import st_autorefresh

# # 設定半小時 (1800000毫秒) 自動刷新一次頁面
# count = st_autorefresh(interval=1800000, key="fubon_monitor")

# ==========================================
# 自動刷新控制
# ==========================================
now = datetime.now().time()
market_close_time = now.replace(hour=13, minute=30, second=0, microsecond=0)
hard_stop_time = now.replace(hour=13, minute=40, second=0, microsecond=0) # 設定 13:40(多給10分鐘緩衝，確保抓到最後一盤)
# 2. 核心邏輯：用 13:40 (hard_stop_time) 來當作自動刷新的斷點
if now < hard_stop_time:
    # --- 狀況 A: 13:40 之前 (包含 13:39) ---
    
    # 開啟自動刷新 (1800秒 = 30分鐘)
    # 注意：如果現在是 13:09，下次刷新會是 13:39，這時候 < 13:40，所以會執行最後一次刷新
    count = st_autorefresh(interval=1800000, key="fubon_monitor")

    # 雖然都在刷新，但我們可以區分「盤中」跟「最後緩衝期」的 UI 顯示
    if now < market_close_time:
        # 09:00 ~ 13:30
        st.success(f"🟢 盤中交易 ({now.strftime('%H:%M')}) - 自動監控中")
        btn_label = "🔄 立即更新報價"
        btn_disabled = False
        time_label = "每 30 分鐘自動刷新"
    else:
        # 13:30 ~ 13:40 (這就是你要的緩衝區)
        st.warning(f"🟡 已收盤，等待最後結算 ({now.strftime('%H:%M')}) - 13:40 停止更新")
        btn_label = "🔄 取得最後收盤價"
        btn_disabled = False
        time_label = "盤後緩衝模式 (30分刷新)"
else:
    # --- 狀況 B: 13:40 之後 ---
    # 這裡不呼叫 st_autorefresh，所以程式會徹底靜止，除非手動按按鈕
    
    st.info(f"😴 市場已完全收盤 ({now.strftime('%H:%M')})，監控結束。")
    
    btn_label = "⛔ 停止更新 (已收盤)"
    btn_disabled = True # 這裡看你想不想鎖死，通常可以鎖死
    time_label = "已停止自動刷新"

# ==========================================
# 核心邏輯
# ==========================================

# 1. 針對「連線資源」做快取：確保只登入一次，除非重啟 Server
@st.cache_resource
def get_fubon_client():
    try:
        client = FubonClient()
        return client
    except Exception as e:
        st.error(f"無法登入 API: {e}")
        return None

# 2. 針對「數據運算」做快取：ttl=1800 秒更新一次
# 注意：把 client 當作參數傳進去，讓 Streamlit 知道這個函式依賴它
@st.cache_data(ttl=1800) 
def get_data_and_calculate(_client):
    # 下底線 _client 是告訴 Streamlit：這個參數不要拿來做 Hash (因為連線物件很難 Hash)
    
    # A. 載入 DB 名單
    query = "SELECT * FROM signal_reports WHERE final_status IN ('TRACKING', 'WATCH_LIST', 'RESURRECTED', 'CLOSED')"
    signals_df = _read_dataframe_from_sql(query)
    
    if signals_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), datetime.now().strftime("%H:%M:%S")

    # B. 資料清理
    df = signals_df.rename(columns={
        'id': 'row_id', 
        'symbol': 'Symbol', 
        'stock_name': 'Name', 
        'date': 'BuyDate', 
        'Close': 'BuyPrice', 
        'signal_type': 'Type', 
    })
    
    df['BuyDate'] = pd.to_datetime(df['BuyDate']).dt.date
    
    # 分離「已結案」與「需更新報價」的股票
    # CLOSED 的股票不用去抓報價
    no_quote_mask = df['final_status'].isin(['CLOSED'])

    # 2. 準備抓報價的名單 (Active + Zombie + Resurrected)
    live_df = df[~no_quote_mask].copy()
    closed_df = df[no_quote_mask].copy()

    # 3. 抓取即時報價
    # Using ThreadPoolExecutor to fetch quotes in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    price_map = {}
    
    if not live_df.empty:
        stock_list = live_df['Symbol'].tolist()

        def fetch_quote(sym):
            try:
                quote = _client.intraday_quote(sym)
                
                # 抓現價：先取值，若為 None 或空字串則給 0，最後轉 float
                raw_p = quote.get('closePrice')
                p = float(raw_p) if raw_p else 0.0
                
                # 抓開盤價：同樣邏輯，避免 float() 參數錯誤
                raw_o = quote.get('openPrice')
                o = float(raw_o) if raw_o else 0.0

                return sym, p, o
            except Exception as e:
                print(f"Error fetching {sym}: {e}")
                return sym, 0.0, 0.0
            
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_symbol = {executor.submit(fetch_quote, sym): sym for sym in stock_list}
            for future in as_completed(future_to_symbol):
                sym, p, o = future.result()
                price_map[sym] = (p, o) # 存成 Tuple (現價, 開盤價)

        # 將資料映射回 DataFrame (確保順序正確)
        # 這裡用列表生成式拆解 Tuple
        live_df['NowPrice'] = [price_map.get(sym, (0.0, 0.0))[0] for sym in live_df['Symbol']]
        live_df['OpenPrice'] = [price_map.get(sym, (0.0, 0.0))[1] for sym in live_df['Symbol']]
        
    # 4. 處理 CLOSED (已結案的不用抓報價，補上預設值 exit_price)
    if 'exit_price' not in closed_df.columns:
        closed_df['NowPrice'] = 0 
        closed_df['OpenPrice'] = 0 # 補 0 避免合併時報錯
    else:
        closed_df['NowPrice'] = closed_df['exit_price'].fillna(0)
        closed_df['OpenPrice'] = 0 # 已結案的不需要今日開盤價

    # 5. 合併所有資料
    df = pd.concat([live_df, closed_df])

    
    # --- 6. 計算邏輯 ---
    # [A] 策略視角 (Strategy View)：用於計算獲利因子
    # 規則：如果有 exit_price (殭屍/復活/結案)，就用 exit_price；否則用 NowPrice (現役)
    df['CalcPrice'] = df['exit_price'].fillna(df['NowPrice'])
    df['PnL_Strategy'] = (df['CalcPrice'] - df['BuyPrice']) * 1000
    df['ROI_Strategy'] = (df['CalcPrice'] - df['BuyPrice']) / df['BuyPrice'] * 100

    # [B] 資產視角 (Asset View)：用於計算帳戶真實餘額
    # 規則：不管狀態為何，計算如果現在賣掉的真實績效
    # 注意：如果 CLOSED (已真的賣掉)，NowPrice 應該等於 exit_price
    df['PnL_M2M'] = (df['NowPrice'] - df['BuyPrice']) * 1000  # Mark-to-Market
    df['ROI_M2M'] = (df['NowPrice'] - df['BuyPrice']) / df['BuyPrice'] * 100
    
    # [C] 策略對決 (Diff)：現價損益 - 策略鎖定損益
    # 正數(紅) = 現價比較高 = 策略賣飛了 (可惜)
    # 負數(綠) = 現價比較低 = 策略跑對了 (好險)
    df['Strategy_Diff'] = df['PnL_M2M'] - df['PnL_Strategy']

    # 為了兼容你原本的 UI 變數名，將主要顯示設為 Strategy (因為這是策略追蹤表)
    df['PnL'] = df['PnL_Strategy']
    df['ROI%'] = df['ROI_Strategy']
    
    # (c) 計算「潛在/觀察」回報 (這是給表格看的，顯示如果還活著會怎樣)
    # 只有 Zombie/Resurrected 需要這個對照
    df['Obs_ROI%'] = (df['NowPrice'] - df['BuyPrice']) / df['BuyPrice'] * 100

    # # 計算：(現價 - 鎖定價)
    # # 正數 = 賣飛了 (早知道守 10MA)
    # # 負數 = 跑對了 (好險守 5MA)
    # df['Strategy_Diff'] = (df['NowPrice'] - df['exit_price'].fillna(df['NowPrice'])) * 1000

    today = date.today()
    # 注意：CLOSED 的 Days 其實應該是 (exit_date - BuyDate)，這裡簡化先算持有到今天，僅供參考
    df['Days'] = df['BuyDate'].apply(lambda x: calculate_holding_days(x, today))

    def format_holding_status(row):
        days = row['Days']
        status = row['final_status']
        type = row['Type']
        
        if status == 'CLOSED': 
            return f"🏁 已結案 (賣出價 {row.get('exit_price', 0)})"
        
        # 殭屍股
        if status == 'WATCH_LIST':
            if int(days) < 5:
                return f"⚠️ T+{days} (太爛/應出)"
            else:
                return f"⚠️ T+{days} (逾期/應出)"
        
        # 決定策略狀態文字
        target_msg = ""
        if days < 5:
            target_msg = "觀察期"
        else:
            ma_line = "5MA"
            if status == 'RESURRECTED':
                if row['Obs_ROI%'] >= 20:
                    ma_line = "10MA"
            else:
                if row['ROI%'] >= 20:
                    ma_line = "10MA"
            target_msg = f"獲利中 未跌破{ma_line}"

        # 3. 組合顯示文字
        if days < 5:
            return f"👀 T+{days} ({target_msg})"
        elif days == 5:
            return f"🔥 T+{days} (決戰日)"
        else:
            # days > 5 且還在 TRACKING，代表它是強勢股
            return f"✅ T+{days} ({target_msg})"
        
    df['T_Plus_Display'] = df.apply(lambda row: format_holding_status(row), axis=1)
    
    # 計算投入成本
    df['InvestAmt'] = df['BuyPrice'] * 1000 

    # 根據 DB 的狀態直接拆分
    active_df = df[df['final_status'] == 'TRACKING'].copy()
    zombie_df = df[df['final_status'] == 'WATCH_LIST'].copy()
    resurrected_df = df[df['final_status'] == 'RESURRECTED'].copy()
    closed_df_final = df[df['final_status'] == 'CLOSED'].copy()

    # 紀錄這一刻的時間
    update_time = datetime.now().strftime("%H:%M:%S")
    
    # 回傳：現役表、殭屍表、復活表、賣出表、更新時間
    return active_df, zombie_df, resurrected_df, closed_df_final, update_time


# ==========================================
# 渲染前端畫面
# ==========================================

# 初始化 Client (只會執行一次)
client = get_fubon_client()

if not client:
    st.stop() # 如果沒登入成功，停止執行下方程式

st.set_page_config(layout="wide", page_title="個股追蹤 Dashboard")

# --- 標題置中 ---
# st.title("🔍 策略追蹤放大鏡")
st.markdown("<h1 style='text-align: center;'>🔍 策略追蹤放大鏡</h1>", unsafe_allow_html=True)

# 執行主要資料抓取
with st.spinner('正在連線 DB 並抓取即時報價...'):
    active_df_raw, zombie_df_raw, resurrected_df_raw, closed_df_raw, last_updated = get_data_and_calculate(client)

# --- 按鈕與時間排在同一列 ---
# 建立兩欄：左邊窄(按鈕)，右邊寬(時間文字)
col_btn, col_time = st.columns([1, 5])

with col_btn:
    # 重新整理按鈕
    if st.button(btn_label, disabled=btn_disabled):
        st.cache_data.clear()
        st.rerun()

with col_time:
    # 顯示最後更新時間 (紅框位置)
    # padding-top 是為了讓文字垂直置中，對齊左邊的按鈕
    st.markdown(
        f"""
        <div style="padding-top: 10px; color: gray; font-size: 16px;">
             ⏱️ 資料最後更新: {last_updated} 【{time_label}】
        </div>
        """, 
        unsafe_allow_html=True
    )

# 合併總表 (不含 Closed，用於搜尋過濾顯示)
# ignore_index=True 避免索引重複
all_holding_df = pd.concat([active_df_raw, zombie_df_raw, resurrected_df_raw], ignore_index=True)

# ==========================================
# 🕵️ 側邊欄：進階篩選器 (Search & Filter)
# ==========================================
# 準備篩選資料來源
if not all_holding_df.empty:
    # 策略選單
    strategy_options = sorted(all_holding_df['Type'].unique().tolist())
    
    # 日期範圍 (預設全選)
    min_date = all_holding_df['BuyDate'].min()
    max_date = all_holding_df['BuyDate'].max()
    default_date_range = (min_date, max_date)
    
    # 天數範圍
    max_days = int(all_holding_df['Days'].max())
    default_days_range = (0, max_days + 5)
else:
    strategy_options = []
    min_date = date.today()
    max_date = date.today()
    default_date_range = (date.today(), date.today())
    max_days = 30
    default_days_range = (0, 30)

# 初始化 session_state
if 'filter_search' not in st.session_state: st.session_state.filter_search = ""
if 'filter_strategy' not in st.session_state: st.session_state.filter_strategy = []
if 'filter_date' not in st.session_state: st.session_state.filter_date = default_date_range
if 'filter_pnl' not in st.session_state: st.session_state.filter_pnl = "全部"
if 'filter_days' not in st.session_state: st.session_state.filter_days = default_days_range

# 日期防呆校正 (Clamping)
current_range = st.session_state.filter_date

# 確保它是 list 或 tuple 且有兩個值 (起始, 結束)
if isinstance(current_range, (list, tuple)) and len(current_range) == 2:
    start_d, end_d = current_range
    
    # 1. 校正起始日
    safe_start = max(start_d, min_date)
    
    # 2. 校正結束日
    safe_end = min(end_d, max_date)
    
    # 3. 特殊狀況防呆：如果校正後 起始 > 結束 (極少見，但以防萬一)，就重置為全選
    if safe_start > safe_end:
        safe_start, safe_end = min_date, max_date
        
    # 4. 如果校正後的日期跟原本不一樣，更新 session_state
    if (safe_start != start_d) or (safe_end != end_d):
        st.session_state.filter_date = (safe_start, safe_end)

# 重置按鈕的回調函式
def reset_filters_callback():
    # 直接指定值，強迫 Streamlit 更新
    st.session_state['filter_search'] = ""           # 清空文字
    st.session_state['filter_strategy'] = []         # 清空多選
    st.session_state['filter_date'] = default_date_range # 還原日期全選
    st.session_state['filter_pnl'] = "全部"          # 還原下拉選單
    st.session_state['filter_days'] = default_days_range # 還原滑桿

# UI 佈局修改
col_header, col_btn = st.sidebar.columns([3, 1], gap="small")
with col_header:
    # 使用 Markdown 模擬 Header，方便與右邊按鈕垂直對齊
    st.markdown("### 🔍 搜尋與篩選")

with col_btn:
    # 建立一個小型的重置按鈕
    # help 參數會在滑鼠移上去時顯示提示
    st.button(
        "↺", 
        key="btn_reset_top", 
        on_click=reset_filters_callback, 
        help="重置所有篩選條件",
        use_container_width=True # 填滿右邊那一小格
    )


# A. 文字搜尋
search_query = st.sidebar.text_input(
    "搜尋股號或股名", 
    placeholder="輸入 2330...",
    key="filter_search"
)

# B. 策略類型
selected_strategies = st.sidebar.multiselect(
    "🏷️ 策略類型", 
    options=strategy_options,
    placeholder="預設顯示全部",
    key="filter_strategy"
)

# C. 日期範圍
date_range = st.sidebar.date_input(
    "📅 訊號日期範圍",
    min_value=min_date,
    max_value=max_date,
    key="filter_date",
    help="篩選「進場日」在指定區間的股票"
)

# D. 損益狀態
pnl_filter = st.sidebar.selectbox(
    "💰 損益狀態", 
    options=["全部", "只看獲利 (Red)", "只看虧損 (Green)"],
    key="filter_pnl"
)

# E. 持有天數
days_filter = st.sidebar.slider(
    "⏳ 持有天數 (T+N)",
    min_value=0,
    max_value=default_days_range[1],
    key="filter_days"
)
st.sidebar.markdown("")

if all_holding_df.empty:
    st.warning("目前沒有追蹤中的個股訊號。")
else:
    # ==========================================
    # 第一排 KPI：總資產情況
    # ==========================================
    st.subheader("📊 總資產情況")
    
    # --- 1. 計算數據 (分三層) ---

    # [層次 A] 真實現金入袋 (CLOSED)
    closed_pnl = closed_df_raw['PnL'].sum() if not closed_df_raw.empty else 0

    # [層次 B] 殭屍/復活股的已鎖定損益 (WATCH_LIST/RESURRECTED with exit_price)
    # 已實現損益：不是看 CLOSED，而是看「有 exit_price 的」(包含：真正結案的 + 轉殭屍鎖定虧損的)
    locked_mask = all_holding_df['exit_price'].notna()
    locked_holding_df = all_holding_df[locked_mask]
    locked_pnl = locked_holding_df['PnL'].sum() if not locked_holding_df.empty else 0
    
    # [層次 C] 真正的浮動未實現 (TRACKING without exit_price)
    # 現役 = "未實現"
    floating_df = all_holding_df[~locked_mask]
    unrealized_pnl = floating_df['PnL'].sum() if not floating_df.empty else 0

    # 總策略淨利 (A + B + C)
    total_pnl = closed_pnl + locked_pnl + unrealized_pnl

    # 市場曝險：只計算未實現的部位 (排除殭屍/復活)
    # 因為殭屍股的 exit_price 已經確定，理論上那筆錢已經視為撤出，不該算在風險曝險中
    exposure_df = floating_df
    current_exposure = exposure_df['InvestAmt'].sum() if not exposure_df.empty else 0
    all_TWR_exposure = all_holding_df['InvestAmt'].sum() if not exposure_df.empty else 0

    # 2. 顯示 4 個 Metrics
    tot_c1, tot_c2, tot_c3, tot_c4 = st.columns(4)
    
    tot_c1.metric(
        "💎 總策略淨利", 
        f"${total_pnl:,.0f}", 
        help="總和 = 現金入袋(CLOSED) + 殭屍(WATCH_LIST) + 復活(RESURRECTED) + 現役浮動(TRACKING)"
    )
    
    # 總已實現 = 完全結案 + 殭屍鎖定
    realized_display = closed_pnl + locked_pnl
    tot_c2.metric(
        "💰 已實現損益 (入袋+鎖定)", 
        f"${realized_display:,.0f}", 
        delta=f"+${locked_pnl:,.0f} (殭屍/復活鎖定)", 
        help=f"""
        結構拆解：
        1. 💵 真金白銀 (CLOSED): ${closed_pnl:,.0f}
        2. 🔒 帳面鎖定 (殭屍/復活): ${locked_pnl:,.0f}
        ---------------------------
        會計總已實現: ${realized_display:,.0f}
        """
    )

    tot_c3.metric(
        "🚀 未實現損益 (浮動)", 
        f"${unrealized_pnl:,.0f}", 
        delta="現役部位",
        help="僅計算 TRACKING 的持股"
    )
    
    tot_c4.metric(
        "🌊 目前市場曝險 (投入)", 
        f"${current_exposure:,.0f}",
        delta="水位",
        delta_color="off",
        help="還卡在股市裡的本金總額 (排除殭屍/復活股)"
    )
    
    # --- 規則說明區塊 ---
    with st.expander("ℹ️ 關於「損益計算」與「績效鎖定」的規則說明"):
        st.markdown("""
        - **已實現損益 (Realized PnL)**：
            1. **`CLOSED`**：歷史已結案的交易。
            2. **`WATCH_LIST` / `RESURRECTED`**：雖然還在觀察名單，但 **`exit_price` 已寫入**，故損益已鎖定，視為已實現。
        - **未實現損益 (Unrealized PnL)**：
            - 僅包含 **`TRACKING`** (現役) 的股票。這是真正的浮動損益。
        - **復活股觀察**：
            - 復活股的報價雖然會跳動，但**不會影響總資產損益**，僅供驗證策略。
        """)

    st.markdown("---")
    
    holding_count = len(all_holding_df)
    
    # 修正：所有持股的平均 ROI 應該要用 總損益 / 總投入資金
    total_holding_invest = all_holding_df['InvestAmt'].sum() if not all_holding_df.empty else 0
    total_holding_pnl = all_holding_df['PnL'].sum() if not all_holding_df.empty else 0
    holding_avg_roi = (total_holding_pnl / total_holding_invest * 100) if total_holding_invest > 0 else 0


    # ==========================================
    # 第二排 KPI：純現役績效 (排除殭屍/復活股)
    # ==========================================
    # 只計算 active_df_raw 的數據
    if not active_df_raw.empty:
        st.subheader("🚀 純現役績效 (排除殭屍/復活股)")
        
        act_count = len(active_df_raw)
        act_invest = active_df_raw['InvestAmt'].sum()
        act_pnl = active_df_raw['PnL'].sum()
        # act_roi = active_df_raw['ROI%'].mean()
        act_roi = (act_pnl / act_invest * 100) if act_invest > 0 else 0

        # 計算差異 (Delta) = 現役 - 整體
        diff_count = act_count - holding_count
        # diff_invest = act_invest - current_exposure
        diff_pnl = act_pnl - total_holding_pnl # 代表不含現役的未實現
        diff_roi = act_roi - holding_avg_roi

        # 計算殭屍數量作為 delta 提示
        zom_count = len(zombie_df_raw)

        ac1, ac2, ac3, ac4 = st.columns(4)
        
        ac1.metric(
            label="現役筆數", 
            value=f"{act_count}",
            delta=f"{diff_count} (排除殭屍/復活股)",
            delta_color="off" # 筆數變少是中性事實，不用紅綠變色，用灰色就好
        )
        
        ac2.metric(
            label="現役投入資金", 
            value=f"${act_invest:,.0f}",
            # delta=f"${diff_invest:,.0f} (資金釋放)",
            delta_color="off" # 資金變少也是中性事實 (釋放出來做別的)，用灰色
        )
        
        ac3.metric(
            label="現役帳面損益 (未實現損益)", 
            value=f"${act_pnl:,.0f}",
            # delta=f"${diff_pnl:,.0f} (現役-整體)", 
            # delta_color="normal" # 依照數值變色 (負數自動變紅)
        )
        
        ac4.metric(
            label="現役平均報酬", 
            value=f"{act_roi:+.2f}%",
            delta=f"{diff_roi:+.2f}%",
            delta_color="normal" # 正數變綠，代表績效變好！
        )
    else:
        st.info("目前無現役持股 (全數為觀察名單或空手)。")

    # ==========================================
    # 第三排 KPI：殭屍股績效 (WATCH_LIST) - 資金滯留區
    # ==========================================
    if not zombie_df_raw.empty:
        st.markdown("---")
        st.subheader("⚠️ 殭屍股概況 (WATCH_LIST)")
        
        zom_count = len(zombie_df_raw)
        zom_invest = zombie_df_raw['InvestAmt'].sum()
        
        # 1. 策略鎖定的損益 (帳面上認賠的)
        zom_pnl_locked = zombie_df_raw['PnL_Strategy'].sum()
        # 2. 實際市價的損益 (如果現在賣掉)
        zom_pnl_real = zombie_df_raw['PnL_M2M'].sum()
        # 3. 差異 (錯失的錢)
        zom_diff = zom_pnl_real - zom_pnl_locked
        
        # zom_pnl = zombie_df_raw['PnL'].sum()
        # zom_roi = zombie_df_raw['ROI%'].mean()

        # 設定 Delta 顏色：
        # 如果現價比鎖定價高 (Diff > 0)，代表策略「賣飛」，用紅色 (off/inverse) 
        # 如果現價比鎖定價低 (Diff < 0)，代表策略「跑對了」，用綠色 (normal)
        diff_color = "inverse" if zom_diff > 0 else "normal"
        diff_label = "賣飛/多賠" if zom_diff > 0 else "避險/少賠"

        zom_ratio = (zom_invest / all_TWR_exposure) * 100

        z1, z2, z3, z4 = st.columns(4)
        z1.metric("殭屍筆數", f"{zom_count}")
        z2.metric("卡彈資金", f"${zom_invest:,.0f}", delta=f"佔比 {zom_ratio:.1f}%", delta_color="off")

        # 重點修改：主數值是鎖定損益，小字是真實損益的差異
        z3.metric(
            "策略鎖定損益", 
            f"${zom_pnl_locked:,.0f}", 
            delta=f"{diff_label} ${abs(zom_diff):,.0f}", 
            delta_color=diff_color,
            help="大字：策略當初判定的損益\n小字：與目前現價的差額 (紅=賣飛 多賠了, 綠=跑對了)"
        )

        # ROI 也顯示雙軌
        # zom_roi_locked = zombie_df_raw['ROI_Strategy'].mean()
        # zom_roi_real = zombie_df_raw['ROI_M2M'].mean()

        zom_roi_locked = (zom_pnl_locked / zom_invest * 100) if zom_invest > 0 else 0
        zom_roi_real = (zom_pnl_real / zom_invest * 100) if zom_invest > 0 else 0
        z4.metric(
            "平均報酬 (鎖定vs現價)", 
            f"{zom_roi_locked:+.2f}%", 
            delta=f"現價 {zom_roi_real:+.2f}%",
            delta_color="off"
        )        
        # z3.metric("殭屍帳面損益", f"${zom_pnl:,.0f}", delta=f"{zom_pnl:,.0f}", delta_color="normal")
        # z4.metric("平均報酬率", f"{zom_roi:+.2f}%", delta_color="normal")

    # ==========================================
    # 第四排 KPI：復活股績效 (RESURRECTED) - 以現價為主
    # ==========================================
    if not resurrected_df_raw.empty:
        st.markdown("---")
        st.subheader("🚑 復活股概況 (RESURRECTED)")
        
        # 復活股因為已經「醒了」，我們更關心它現在賺多少，所以反過來
        # 主數值顯示：現價損益 (PnL_M2M)
        # 小字顯示：與鎖定價的差異
        
        res_pnl_real = resurrected_df_raw['PnL_M2M'].sum()
        res_pnl_locked = resurrected_df_raw['PnL_Strategy'].sum()
        res_diff = res_pnl_real - res_pnl_locked
        
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("復活筆數", f"{len(resurrected_df_raw)}")
        r2.metric("投入資金", f"${resurrected_df_raw['InvestAmt'].sum():,.0f}", delta_color="off")
        
        r3.metric(
            "目前真實損益", 
            f"${res_pnl_real:,.0f}", 
            delta=f"較鎖定 {res_diff:+,.0f}",
            delta_color="normal",
            help="復活股以「現價」為準，小字代表復活後多賺(或少賠)的錢"
        )
        
        # res_roi_real = resurrected_df_raw['ROI_M2M'].mean()
        res_invest = resurrected_df_raw['InvestAmt'].sum()
        
        res_roi_real = (res_pnl_real / res_invest * 100) if res_invest > 0 else 0

        r4.metric("目前平均報酬", f"{res_roi_real:+.2f}%", delta_color="normal")

    st.markdown("---")

    # ==========================================
    # 執行過濾邏輯 (Filter Logic)
    # ==========================================
    display_df = all_holding_df.copy() # 先複製一份總表

    # 1. 文字搜尋
    if search_query:
        mask_search = (
            display_df['Symbol'].astype(str).str.contains(search_query, case=False) | 
            display_df['Name'].astype(str).str.contains(search_query, case=False)
        )
        display_df = display_df[mask_search]

    # 2. 策略類型
    if selected_strategies:
        display_df = display_df[display_df['Type'].isin(selected_strategies)]

    # 3. 日期範圍 (新增)
    if len(date_range) == 2: # 確保使用者選了 起始+結束 兩個日期
        start_d, end_d = date_range
        display_df = display_df[
            (display_df['BuyDate'] >= start_d) & 
            (display_df['BuyDate'] <= end_d)
        ]

    # 4. 損益狀態
    if pnl_filter == "只看獲利 (Red)":
        display_df = display_df[display_df['PnL'] > 0]
    elif pnl_filter == "只看虧損 (Green)":
        display_df = display_df[display_df['PnL'] < 0]

    # 5. 持有天數 (新增)
    min_d, max_d = days_filter
    display_df = display_df[
        (display_df['Days'] >= min_d) & 
        (display_df['Days'] <= max_d)
    ]

    # ==========================================
    # 表格顯示設定
    # ==========================================
    display_cols = [
        'BuyDate', 'Symbol', 'Name', 
        'BuyPrice', 'exit_price', 'NowPrice',   # 價格三兄弟
        'PnL', 'ROI%',                          # 這是「策略鎖定」的 (驗證過去)
        'PnL_M2M', 'ROI_M2M',                   # 這是「真實當下」的 (驗證現在)
        'Strategy_Diff',        
        'T_Plus_Display',                       # 持有狀態
        'Type'
    ]
    
    def color_roi(val):
        """ROI 著色邏輯"""
        if pd.isna(val): return ''
        color = '#d32f2f' if val > 0 else '#2e7d32' if val < 0 else "#e2ec28"
        weight = 'bold' if abs(val) > 0 else 'normal'
        return f'color: {color}; font-weight: {weight}'

    def render_stock_table(df, hide_exit_info=False):
        """共用的表格渲染函式 (含動態高度)"""
 
        # 定義原本的 column_config
        my_column_config = {
            "BuyDate": "訊號日",
            "Symbol": "代號",
            "Name": "股名",
            "InvestAmt": "投入成本",
            "BuyPrice": st.column_config.NumberColumn("1️⃣ 建倉價", format="%.2f"),
            "exit_price": st.column_config.NumberColumn(
                "2️⃣ 鎖定價", 
                help="策略轉弱時的價格", format="%.2f"
            ),
            # "NowPrice": st.column_config.NumberColumn(
            #     "👀現價", 
            #     help="目前市場即時價格 (觀察用，不影響已鎖定損益)"
            # ),
            "NowPrice": st.column_config.NumberColumn(
                "3️⃣ 現價", 
                help="目前市場價格", format="%.2f"
            ),
            "Strategy_Diff": st.column_config.NumberColumn(
                "⚖️ 價差損益", 
                help="現價 - 鎖定價 (正數代表現價較高)", format="$%d"
            #     help="正數(紅)代表賣飛(現價贏)；負數(綠)代表跑對(鎖定價贏)"
            ),

            "PnL": st.column_config.NumberColumn(
                "🔒鎖定損益", 
                help="當初轉弱被踢出時的損益 (策略成績單)", format="$%d"
            ),
            "ROI%": st.column_config.NumberColumn(
                "🔒鎖定報酬", 
                format="%.2f%%"
            ),

            "PnL_M2M": st.column_config.NumberColumn(
                "👀現在損益", 
                help="如果不理會策略，抱到現在的損益 (復活股看這個才準)", 
                format="$%d"
            ),
            "ROI_M2M": st.column_config.NumberColumn(
                "👀現在報酬", 
                help="基於現價計算的報酬率", 
                format="%.2f%%"
            ),
            
            "T_Plus_Display": st.column_config.TextColumn(
                "持有狀態", 
                help="T+N 代表已持有的完整交易日數",
                width="medium" 
            ),
            "Type": "策略",
        }
        
        max_height = 600

        # 如果是現役模式 (hide_exit_info=True)，鎖定欄位設為 None 代表隱藏
        if hide_exit_info:
            my_column_config["exit_price"] = None 
            my_column_config["Strategy_Diff"] = None
            my_column_config["PnL"] = None
            my_column_config["ROI%"] = None
            max_height = 1000

        # 1. 計算理想高度 (每一列約 35px + 標題列 + 微調緩衝)
        row_height = 35
        calculated_height = (len(df) + 1) * row_height + 3
        
        # 2. 設定高度上限 (Max Height)
        #    殭屍股通常很少，會直接用 calculated_height
        #    高度 600px 卡住，變成可捲動
        final_height = calculated_height
        # final_height = min(calculated_height, max_height)

        st.dataframe(
            df[display_cols].style
            .format({
                'InvestAmt': '${:,.0f}',
                'BuyPrice': '{:.2f}',
                'exit_price': '{:.2f}', # 顯示鎖定價
                'NowPrice': '{:.2f}',   # 顯示目前市價
                'PnL': '{:+,.0f}',      # 這是「實際損益」(基於 exit_price)
                'ROI%': '{:+.2f}%',     # 這是「實際報酬率」
                'Strategy_Diff': '{:+,.0f}', # 顯示價差金額
                'BuyDate': '{:%Y-%m-%d}',
                'PnL_M2M': '{:+,.0f}',
                'ROI_M2M': '{:+.2f}%',
            })
            # 紅色 (正數) = 賣飛了
            # 綠色 (負數) = 跑對了
            .map(color_roi, subset=['ROI%', 'PnL', 'PnL_M2M', 'ROI_M2M', 'Strategy_Diff']),
            
            column_config=my_column_config,

            width='stretch',
            # use_container_width=True, # 填滿寬度
            height=final_height,
            hide_index=True
        )

    # ==========================================
    # 4. 渲染區塊
    # ==========================================

    # 如果搜尋結果完全是空的
    if display_df.empty:
        st.info(f"找不到與「{search_query}」相關的結果。")
    else:
        # 將「搜尋過濾後」的結果，再次拆分成 現役 殭屍 與 復活
        show_active = display_df[display_df['final_status'] == 'TRACKING']
        show_zombie = display_df[display_df['final_status'] == 'WATCH_LIST']
        show_resurrected = display_df[display_df['final_status'] == 'RESURRECTED']

        # A. 殭屍股區塊
        if not show_zombie.empty:
            # 判斷裡面有多少是已鎖定績效的
            locked_count = show_zombie['exit_price'].count()
            st.error(f"⚠️ 殭屍股名單 (共 {len(show_zombie)} 筆) - [其中 {locked_count} 筆已鎖定績效]")
            with st.expander("展開/收合", expanded=False):
                render_stock_table(show_zombie)
            st.markdown("---")

        # B. 復活股區塊
        if not show_resurrected.empty:
            st.info(f"🚑 復活觀察名單 ({len(show_resurrected)} 筆) - [復活股]")
            with st.expander("展開/收合", expanded=False):
                render_stock_table(show_resurrected)
            st.markdown("---")

        # C. 現役持股區塊 (維持綠色成功樣式)
        if not show_active.empty:
            st.success(f"🚀 現役持股清單 ({len(show_active)} 筆)")
            with st.expander("展開/收合", expanded=False):
                render_stock_table(show_active, hide_exit_info=True)
        elif not show_active.empty:
            # 如果只有殭屍股沒有現役股
            st.info("此搜尋條件下沒有 'TRACKING' 狀態的持股。")

    st.markdown("---")
    
    # ==========================================
    # 第五排 KPI：已結案績效總覽 (CLOSED) - 真正的戰績
    # ==========================================
    if not closed_df_raw.empty:
        st.subheader("🏆 已結案績效總覽 (CLOSED)")
        
        # 1. 基礎數據
        c_count = len(closed_df_raw)
        c_pnl = closed_df_raw['PnL'].sum()
        # c_roi_avg = closed_df_raw['ROI%'].mean()
        
        total_closed_invest = (closed_df_raw['BuyPrice'] * 1000).sum()
        
        c_roi_avg = (c_pnl / total_closed_invest * 100) if total_closed_invest > 0 else 0
        
        # 2. 進階數據：勝率 (Win Rate)
        # 賺錢的筆數
        win_count = len(closed_df_raw[closed_df_raw['PnL'] > 0])
        win_rate = (win_count / c_count) * 100 if c_count > 0 else 0
        
        # 3. 進階數據：獲利因子 (Profit Factor) - 總賺 / 總賠 (絕對值)
        gross_profit = closed_df_raw[closed_df_raw['PnL'] > 0]['PnL'].sum()
        gross_loss = abs(closed_df_raw[closed_df_raw['PnL'] < 0]['PnL'].sum())
        # 防呆：如果沒賠錢，獲利因子給無限大或一個大數字
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        pf_display = "∞" if profit_factor == float('inf') else f"{profit_factor:.2f}"

        # 4. 顯示 Metrics
        cc1, cc2, cc3, cc4 = st.columns(4)
        
        cc1.metric(
            "結案筆數", 
            f"{c_count}", 
            help="已經完全出場，現金落袋的交易"
        )
        
        cc2.metric(
            "累積實賺金額", 
            f"${c_pnl:,.0f}", 
            delta=f"獲利因子 {pf_display}",
            help="Profit Factor = 總獲利 / 總虧損 (大於 1.5 代表策略穩健)"
        )
        
        cc3.metric(
            "平均報酬率", 
            f"{c_roi_avg:+.2f}%", 
            delta_color="normal"
        )
        
        cc4.metric(
            "交易勝率", 
            f"{win_rate:.1f}%", 
            delta=f"{win_count} 勝 / {c_count - win_count} 敗",
            delta_color="off",
            help="勝率不需太高，重點是賺賠比 (大賺小賠)"
        )

    # 已結案歷史紀錄 Expander
    with st.expander(f"📚 已結案歷史紀錄 (共 {len(closed_df_raw)} 筆) - [點擊展開]"):
        if not closed_df_raw.empty:
            # 1. 挑選欄位並建立副本，避免動到原始資料
            df_display = closed_df_raw[['Symbol', 'Name', 'BuyPrice', 'exit_price', 'PnL', 'ROI%', 'Type', 'BuyDate', 'exit_date', 'note']].copy()
            
            # 2. 修改表頭為中文
            df_display.columns = ['股票代號', '股票名稱', '進場價格', '結案價格', '損益金額', '投報率', '策略', '進場日期', '結案日期', '備註']
            
            # 3. 顯示並套用樣式
            st.dataframe(
                df_display.style.format({
                    '進場價格': '{:.2f}', 
                    '結案價格': '{:.2f}', 
                    '損益金額': '{:+,.0f}', 
                    '投報率': '{:+.2f}%'
                })
                # 關鍵修正：將 '投報率' 加入 subset，讓它也能根據正負顯示紅綠
                .map(lambda x: 'color: red' if x > 0 else 'color: green' if x < 0 else '', 
                    subset=['損益金額', '投報率']),
                width='stretch'
            )
        else:
            st.info("尚無已結案資料。")

# 側邊欄「登記出場」功能
with st.sidebar.expander("💸 登記出場 (Sell)", expanded=False):
    st.header("💸 登記出場 (Sell)")
    
    # 為了讓下拉選單有東西選，我們先執行一次資料抓取(或另外寫輕量SQL)
    # 這裡直接用快取資料
    with st.spinner('載入持股清單...'):
        # 注意：這裡呼叫會觸發 cache，不會真的很慢
        _act, _zom, _resur, _cls, _last = get_data_and_calculate(client)
        # 合併所有「表格」的股票供選擇
        holdings = pd.concat([_act, _zom, _resur])
    
    if not holdings.empty:
        # 製作選單標籤: 代號 - 股名 (現價) .strftime('%m/%d')
        sell_options = all_holding_df.copy()
        sell_options['Label'] = sell_options.apply(
            lambda x: f"{x['Symbol']} - {x['Name']} (買進: {x['BuyDate']}, 策略: {x['Type']})", axis=1
        )

        selected_label = st.selectbox("選擇要結帳的股票", sell_options['Label'])
        
        # 抓出選到的那一行資料
        selected_row = sell_options[sell_options['Label'] == selected_label].iloc[0]
        
        selected_row_id = selected_row['row_id']
        selected_symbol = selected_row['Symbol']
        selected_buy_date = selected_row['BuyDate']
        selected_type = selected_row['Type']

        # 輸入賣出資訊
        c1, c2 = st.columns(2)
        if pd.notna(selected_row.get('exit_price')):
            st.warning(f"💡 此股已於 {selected_row['exit_date']} 鎖定績效 (價格 {selected_row['exit_price']})。本次結案僅更新狀態，不會覆蓋原績效。")
            exit_price_input = c1.number_input("賣出價格 (已鎖定)", value=float(selected_row['exit_price']), disabled=True)
        else:
            exit_price_input = c1.number_input("賣出價格", value=float(selected_row['NowPrice']), step=0.1)

        exit_date_input = c2.date_input("賣出日期", value=date.today())
        
        exit_reason = st.selectbox("出場理由", ["💰 獲利了結", "🔪 停損 / 換股", "⏰ T+10 到期結算", "🧟 殭屍股清除"])
        
        st.markdown("<br>", unsafe_allow_html=True) # 加一點間距
        
        # -------------------------------------------------------
        # 定義確認視窗
        # -------------------------------------------------------
        @st.dialog("⚠️ 確認賣出資訊")
        def show_sell_confirmation(row_id, symbol, name, signal_type, price, sell_date, reason, buy_date):
            st.write(f"即將對 **{symbol} {name} {signal_type}** 執行結案：")
            
            # 用表格或條列式顯示關鍵資訊，讓你在按下去前再看一眼
            st.info(f"""
            - **買進日期**: {buy_date}
            - **賣出價格**: {price}
            - **賣出日期**: {sell_date}
            - **出場理由**: {reason}
            """)
            
            st.warning("此動作將寫入資料庫並計算已實現損益，確定執行？")

            col_ok, col_cancel = st.columns([1, 1])
            
            with col_ok:
                if st.button("✅ 確認執行", type="primary", use_container_width=True):
                    # 真正的執行邏輯搬到這裡面
                    try:
                        success = close_trade_signal(
                            row_id=row_id,
                            symbol=symbol,
                            buy_date=buy_date,
                            exit_price=price,
                            exit_date=sell_date,
                            note=reason
                        )
                        if success:
                            st.success(f"{symbol} 已結帳！")
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("更新失敗，可能查無此股。")
                    except Exception as e:
                        st.error(f"錯誤: {e}")

            with col_cancel:
                if st.button("❌ 取消", use_container_width=True):
                    st.rerun() # 關閉視窗重新整理
                
        # st.markdown("<br>", unsafe_allow_html=True)
        sb_col1, sb_col2 = st.columns([1.5, 1])
        # 把按鈕放在右邊的欄位 (sb_col2)
        with sb_col2:
            if st.button("登記賣出", key="btn_sell_trigger"):
                # 按下去只呼叫 dialog
                show_sell_confirmation(
                    row_id=selected_row_id,
                    symbol=selected_symbol,
                    name=selected_row['Name'],
                    signal_type=selected_type,
                    price=exit_price_input,
                    sell_date=exit_date_input,
                    reason=exit_reason,
                    buy_date=selected_buy_date
                )
    else:
        st.info("目前沒有持股可賣。")
