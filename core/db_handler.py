# core/db_handler.py

import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, IntegrityError, ProgrammingError
import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert # 導入 MySQL 專用的 INSERT 擴展

# 1. 載入 .env 檔案中的變數
# 確保 .env 檔案在專案根目錄
load_dotenv() 

# -----------------
# 1. 數據庫引擎連線
# -----------------
def get_db_engine():
    """
    建立並返回 SQLAlchemy 數據庫引擎，使用 PyMySQL 驅動。
    """
    
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")
    
    # 建立使用 PyMySQL 驅動的連線 URL
    db_url = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    
    # 建立數據庫引擎
    # pool_recycle=3600: 每隔一小時重新連線，避免 MySQL 連線超時問題
    engine = create_engine(db_url, pool_recycle=3600)

    return engine




def _generic_upsert_method(table, conn, keys, data_iter):
    """
    實現 MySQL 的 ON DUPLICATE KEY UPDATE (Upsert)。
    此函數會自動偵測表格的主鍵。
    """
    
    # 1. 🌟 自動偵測主鍵 (Primary Keys) 🌟
    # 從 SQLAlchemy 的 Table 物件中獲取所有組成主鍵的欄位名稱
    primary_keys = [col.name for col in table.table.primary_key.columns]
    
    # 2. 處理資料
    # 將 DataFrame 的行轉換為 list of dicts
    values = [dict(zip(keys, row)) for row in data_iter]
    insert_stmt = insert(table.table).values(values)
    
    # 3. 🌟 動態設定要更新的欄位：排除主鍵 🌟
    # 迭代表格的所有欄位，如果欄位名稱不在主鍵列表中，就納入更新
    update_cols = {
        col.name: insert_stmt.inserted[col.name]
        for col in table.table.columns
        if col.name not in primary_keys 
    }

    # 4. 執行 Upsert
    # 如果沒有要更新的欄位（例如整個表格都是主鍵），則跳過
    if not update_cols:
         print(f"警告：表 '{table.table.name}' 似乎只有主鍵，Upsert 邏輯將只嘗試插入。")
         conn.execute(insert_stmt)
    else:
        # 合併 INSERT 和 ON DUPLICATE KEY UPDATE 邏輯
        upsert_stmt = insert_stmt.on_duplicate_key_update(**update_cols)
        conn.execute(upsert_stmt)

def _write_dataframe_to_sql(df: pd.DataFrame, table_name: str, if_exists: str = 'append'):
    """
    【私有】通用底層寫入函數，執行 df.to_sql 邏輯。
    """
    if df.empty:
        print(f"警告：DataFrame 為空，跳過 '{table_name}' 數據庫寫入。")
        return False
        
    try:
        engine = get_db_engine()
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists=if_exists,
            index=False,
            method=_generic_upsert_method
        )
        return True # 成功寫入
        
    # except IntegrityError:
    #     print(f"警告：'{table_name}' 數據寫入失敗，可能存在主鍵衝突。")
    #     return False
    except OperationalError as e:
        print(f"❌ '{table_name}' 數據庫操作失敗，請檢查連線或 MySQL 服務狀態。錯誤: {e}")
        return False
    except Exception as e:
        print(f"發生未知錯誤: {e}")
        return False

# ----------------------------------------------------
# 儲存 K 線數據
# ----------------------------------------------------
def save_kbars_to_db(df: pd.DataFrame, table_name: str = 'daily_kbars', if_exists: str = 'append'):
    """將 K 線數據 DataFrame 寫入數據庫中的指定表格。"""
    
    if _write_dataframe_to_sql(df, table_name, if_exists):
        # print(f"✅ 成功將 {len(df)} 筆 K 線數據寫入 '{table_name}' 表。")
        pass

# ----------------------------------------------------
# 儲存策略訊號
# ----------------------------------------------------
def save_signals_to_db(df: pd.DataFrame, table_name: str = 'signal_reports', if_exists: str = 'append'):
    """將策略訊號結果 DataFrame 寫入數據庫中的指定表格。"""
        
    if _write_dataframe_to_sql(df, table_name, if_exists):
        print(f"✅ 成功將 {len(df)} 筆訊號結果寫入 '{table_name}' 表。")





# -----------------
# 3. 數據庫查詢
# -----------------
def _read_dataframe_from_sql(sql_query: str) -> pd.DataFrame:
    """
    【私有】通用底層讀取函數，執行 pd.read_sql 邏輯。
    """
    try:
        engine = get_db_engine()
        
        # 使用 read_sql 執行查詢
        df = pd.read_sql(sql_query, con=engine)
        
        return df
        
    except ProgrammingError:
        print(f"❌ 數據庫查詢失敗：請確認表格名稱、欄位或 SQL 語法是否正確。SQL: {sql_query[:50]}...")
        return pd.DataFrame()
    except OperationalError as e:
        print(f"❌ 數據庫連線操作失敗，請檢查配置或 MySQL 服務狀態。錯誤: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"發生未知讀取錯誤: {e}")
        return pd.DataFrame()
    
# ----------------------------------------------------
# 抓某支股票 過去90天的日K棒數據
# ----------------------------------------------------
def load_kbars_from_db(symbol: str, days: int = 90) -> pd.DataFrame:
    """
    從數據庫讀取單檔股票的 K 線數據。
    
    Args:
        symbol (str): 股票代號
        days (int): 要讀取過去幾天的資料 (預設 90 天)
        table_name (str): 資料表名稱
    """
    # 計算 N 天前的日期
    start_date_dt = datetime.now() - timedelta(days=days)
    start_date_str = start_date_dt.strftime('%Y-%m-%d')
    
    # 構建專屬於 K 線的 SQL 查詢語句 yyyy-mm-dd 格式
    query = f"""
        SELECT * FROM daily_kbars
        WHERE symbol = '{symbol}' AND date >= '{start_date_str}'
        ORDER BY date ASC;
    """
    
    df = _read_dataframe_from_sql(query)
    if not df.empty:
        # print(f"✅ 成功從 DB 讀取 {len(df)} 筆 {symbol} K 線數據。")
        
        # 確保 date 欄位是 datetime 物件，方便後續比較
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            
    return df

# ----------------------------------------------------
# 查詢策略訊號表
# ----------------------------------------------------
def load_signals_for_analysis(start_date: str, end_date: str = None, table_name: str = 'signal_reports') -> pd.DataFrame:
    """
    從數據庫讀取指定時間範圍內的策略訊號紀錄，用於績效回測分析。
    """
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
        
    # 構建 SQL 查詢語句
    query = f"""
        SELECT * FROM {table_name} 
        WHERE date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY date ASC, symbol ASC;
    """
    
    df = _read_dataframe_from_sql(query)
    
    if not df.empty:
        print(f"✅ 成功從 DB 讀取 {len(df)} 筆訊號紀錄，用於回測。")
    
    return df


# ----------------------------------------------------
# 抓 daily_kbars表 現有的股票號 要更新日K數據
# ----------------------------------------------------
def get_existing_symbols_in_db() -> list[str]:
    """
    從 daily_kbars 資料庫中撈出所有現存的股票代號 (不重複)。
    用於資料初始化時，確保舊有的股票也能持續更新數據。
    """
    engine = get_db_engine()
    
    query = text("SELECT DISTINCT symbol FROM daily_kbars;")
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query)
            # result 每一列的第一個欄位就是 symbol
            symbols = [str(row[0]) for row in result]
            return symbols
            
    except Exception as e:
        # 如果表還不存在 (第一次執行)，或是連線錯誤，就回傳空陣列
        print(f"⚠️ 無法讀取資料庫現有股票 (可能是初次執行或表不存在): {e}")
        return []

# ----------------------------------------------------
# 抓某支股票 某一天的日K棒數據
# ----------------------------------------------------
def get_one_day_kbar(symbol: str, target_date: str) -> dict | None:
    """
    精準抓取單一檔股票、特定日期的 K 棒數據 (開/高/低/收)。
    
    Args:
        symbol (str): 股票代號 (如 '2330')
        target_date (str): 目標日期 (格式 'YYYY-MM-DD')
    
    Returns:
        dict: {'Open': 100, 'High': 105, 'Low': 98, 'Close': 102} 或 None (若無資料)
    """
    query = f"""
        SELECT Open, High, Low, Close 
        FROM daily_kbars
        WHERE symbol = '{symbol}' AND date = '{target_date}'
    """
    
    try:
        df = _read_dataframe_from_sql(query)
        
        if not df.empty:
            # 轉成字典回傳，方便取用
            # iloc[0] 抓第一列 (也是唯一的一列)
            data = df.iloc[0].to_dict()
            return data
        else:
            return None
            
    except Exception as e:
        print(f"❌ 查詢 K 棒失敗 ({symbol} @ {target_date}): {e}")
        return None

# 抓取該股票「最新一天」的收盤價，不管今天是 T+幾
def get_latest_close_from_db(symbol):
    query = f"""
        SELECT date, Close 
        FROM daily_kbars 
        WHERE symbol = '{symbol}' 
        ORDER BY date DESC 
        LIMIT 1;
    """
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            result = conn.execute(text(query)).fetchone()
            if result:
                return result[0], float(result[1])
    except Exception as e:
        print(f"   ⚠️ 查詢最新價格失敗: {e}")
    return None, None

def get_close_price_from_db(symbol, target_date):
    """
    從 daily_kbars 撈取該股票「最新一筆」的收盤價
    (因為 upd_daily_kbars 剛跑完，裡面一定有今天的最新資料)
    """
    query = f"""
        SELECT Close FROM daily_kbars 
        WHERE symbol = '{symbol}' AND date = '{target_date}'
        LIMIT 1;
    """
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            result = conn.execute(text(query)).fetchone()
            if result:
                return float(result[0])
    except Exception as e:
        print(f"   ⚠️ 查詢價格失敗: {e}")
    return None

def get_period_max_price(symbol, entry_date, days_held):
    """
    抓取從進場日到現在這段期間內，資料庫裡紀錄的「最高價」。
    """
    # 1. 計算日期範圍
    # start: 進場隔天
    # end: 今天 (current_date)
    start_date_str = (entry_date + timedelta(days=1)).strftime('%Y-%m-%d')
    end_date_str = pd.Timestamp.now().strftime('%Y-%m-%d')

    # 2. 寫 SQL 查詢
    # 邏輯：從 K棒表 撈出這段時間內 High 欄位的最大值
    query = f"""
        SELECT MAX(High) 
        FROM daily_kbars
        WHERE symbol = '{symbol}' 
            AND date >= '{start_date_str}' 
            AND date <= '{end_date_str}'
    """
    
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            result = conn.execute(text(query)).scalar()
        
        # 如果資料庫沒資料 (None)，回傳 0
        period_high = float(result) if result is not None else 0.0
        
        return period_high

    except Exception as e:
        print(f"查詢 DB 最高價失敗: {e}")
        return 0.0

def get_stock_ma_indicators(symbol, target_date):
    """
    撈取 K 棒並計算 MA5, MA10。
    target_date: 計算基準日 (例如 2026-01-05)
    """
    sql = text("""
        SELECT date, Close 
        FROM daily_kbars 
        WHERE symbol = :symbol AND date <= :target_date 
        ORDER BY date DESC 
        LIMIT 25
    """)
    
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={"symbol": symbol, "target_date": target_date})
            
        if df.empty or len(df) < 10:
            return None

        # SQL 撈出來是 DESC (最新的在上面)，計算 MA 必須先轉回 ASC (舊到新)
        df = df.sort_values('date', ascending=True)

        # 計算移動平均線
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()

        # 取得最後一筆 (即 target_date 當天) 的數值
        latest = df.iloc[-1]
        
        return {
            'MA5': round(latest['MA5'], 2),
            'MA10': round(latest['MA10'], 2),
            'MA20': round(latest['MA20'], 2),
            'Close': latest['Close']
        }
    except Exception as e:
        print(f"❌ 計算 {symbol} MA 失敗: {e}")
        return None

def get_latest_data_with_atr(symbol):
    """
    抓取最近 20 筆 K 棒，計算 ATR(14) 與 取得前日收盤價
    Returns: (latest_price, pre_close, atr_value, latest_date)
    """
    engine = get_db_engine()
    
    # 抓 25 筆確保 rolling 計算足夠
    query = f"""
        SELECT date, High, Low, Close 
        FROM daily_kbars 
        WHERE symbol = '{symbol}' 
        ORDER BY date DESC LIMIT 25
    """
    df = pd.read_sql(query, engine)
    
    if len(df) < 15: # 資料不足無法計算
        return None, None, 0.0, None
        
    df = df.iloc[::-1].reset_index(drop=True) # 轉為時間正序
    
    # 1. 計算 TR
    # High - Low
    tr1 = df['High'] - df['Low']
    # |High - PreClose|
    tr2 = (df['High'] - df['Close'].shift(1)).abs()
    # |Low - PreClose|
    tr3 = (df['Low'] - df['Close'].shift(1)).abs()
    
    df['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 2. 計算 ATR (14日平均)
    df['ATR'] = df['TR'].rolling(window=14).mean()
    
    # 取得最新一筆資料
    latest = df.iloc[-1]
    prev = df.iloc[-2] # 前一筆
    
    return float(latest['Close']), float(prev['Close']), float(latest['ATR']), latest['date']

def close_trade_signal(row_id: int, entry_price: float, exit_price: float, exit_reason: str, exit_date=None, status='CLOSED') -> bool:
    """
    適用於「手動結案」、「硬停損」、「T+10 逾期結案」。
    
    核心機制：
    使用 SQL COALESCE 函數保護已鎖定的績效。
    - 若資料庫中 exit_price 為 NULL (現役)，則寫入 exit_price。
    - 若資料庫中 exit_price 已有值 (殭屍/復活)，則保留原值，不被覆蓋。

    Args:
        symbol (str): 股票代號
        buy_date (str/date): 買進日期 (定位用)
        exit_price (float): 當前結案價格 (若為殭屍股，此數值會被忽略)
        exit_reason (str): 結案原因 (會附加在原本的 note 後面)
        exit_date (str/date, optional): 結案日期，預設為今天

    Returns:
        bool: True 代表更新成功，False 代表找不到資料或更新失敗。
    """
    try:
        engine = get_db_engine()
        
        final_roi = 0.0
        if entry_price and entry_price > 0:
            final_roi = round(((exit_price - entry_price) / entry_price) * 100, 2)

        # 1. 日期格式處理
        if exit_date is None:
            exit_date = date.today()
        
        # 轉字串 (防呆)
        ed_str = exit_date.strftime('%Y-%m-%d') if hasattr(exit_date, 'strftime') else str(exit_date)

        # 2. 準備 SQL
        # 使用 COALESCE 保護價格與日期
        query = text("""
            UPDATE signal_reports 
            SET final_status = :status, 
                exit_price = COALESCE(exit_price, :p), 
                exit_roi = COALESCE(exit_roi, :r), 
                exit_date = COALESCE(exit_date, :d),
                note = CASE 
                    WHEN note IS NULL OR note = '' THEN :n 
                    ELSE CONCAT(note, ' | ', :n) 
                END
            WHERE id = :row_id
            AND final_status != :status
        """)

        # 3. 執行
        with engine.connect() as conn:
            result = conn.execute(query, {
                "row_id": row_id, 
                "p": exit_price, 
                "r": final_roi, 
                "d": ed_str, 
                "n": exit_reason, 
                "status": status
            })
            conn.commit()
            
            if result.rowcount > 0:
                return True
            else:
                return False

    except Exception as e:
        print(f"❌ 執行 close_trade_signal 發生錯誤: {e}")
        return False

def update_to_watchlist(row_id:int, symbol: str, buy_date: str, note: str, exit_price: float = None, exit_date: str = None):
    """
    將股票轉入殭屍名單 (WATCH_LIST)。
    
    Args:
        exit_price: 
            - 若傳入數值 (現役股淘汰): 會更新 exit_price, exit_date (鎖定績效)。
            - 若為 None (復活股淘汰): 不會更動 exit_price, exit_date (純觀察)。
    """
    try:
        engine = get_db_engine()
        
        price_sql = ""
        params = {
            # "s": symbol, 
            # "bd": buy_date, 
            "row_id": row_id, 
            "n": note
        }

        if exit_price is not None:
            price_sql = ", exit_price = :p, exit_date = :d"
            params["p"] = exit_price
            params["d"] = exit_date

        query = text(f"""
            UPDATE signal_reports 
            SET final_status = 'WATCH_LIST',
                note = CASE 
                    WHEN note IS NULL OR note = '' THEN :n 
                    ELSE CONCAT(note, ' | ', :n) 
                END
                {price_sql}
            WHERE id = :row_id
        """)

        with engine.connect() as conn:
            conn.execute(query, params)
            conn.commit()
            return True
            
    except Exception as e:
        print(f"❌ update_to_watchlist 錯誤({symbol} {buy_date}): {e}")
        return False

def update_to_resurrected(row_id:int, symbol: str, buy_date: str, note: str):
    """
    將殭屍股復活 (RESURRECTED)。
    只改狀態與筆記，不動價格。
    """
    try:
        engine = get_db_engine()
        query = text("""
            UPDATE signal_reports 
            SET final_status = 'RESURRECTED',
                note = CASE 
                    WHEN note IS NULL OR note = '' THEN :n 
                    ELSE CONCAT(note, ' | ', :n) 
                END
            WHERE id = :row_id
        """)
        
        with engine.connect() as conn:
            conn.execute(query, {"row_id": row_id, "n": note})
            conn.commit()
            return True
            
    except Exception as e:
        print(f"❌ update_to_resurrected 錯誤({symbol} {buy_date}): {e}")
        return False

def append_note(row_id:int, note: str):
    """
    純粹追加筆記 (例如 T+9 警告)。
    """
    try:
        engine = get_db_engine()
        query = text("""
            UPDATE signal_reports 
            SET note = CASE 
                    WHEN note IS NULL OR note = '' THEN :n 
                    ELSE CONCAT(note, ' | ', :n) 
                END
            WHERE id = :row_id
        """)
        with engine.connect() as conn:
            conn.execute(query, {"row_id": row_id, "n": note})
            conn.commit()
    except Exception as e:
        print(f"❌ append_note 錯誤({row_id}): {e}")

def update_signal_pf(row_id:int, updates: dict):
    """
    動態更新訊號績效資料 (包含現價、T+1/5/10 績效、狀態等)。
    
    Args:
        row_id: 股票資料ID
        updates: 要更新的欄位與數值字典, e.g., {'current_price': 100, 'roi_1d': 5.2}
    """
    if not updates:
        return False

    try:
        engine = get_db_engine()
        
        # 1. 動態組裝 SET 子句 (使用參數化綁定)
        # 例如: "current_price = :current_price, roi_1d = :roi_1d"
        set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
        
        query = text(f"""
            UPDATE signal_reports 
            SET {set_clause}
            WHERE id = :row_id
        """)
        
        # 2. 準備參數字典 (合併 where 條件與 update 資料)
        params = updates.copy()
        params["row_id"] = row_id
        
        with engine.connect() as conn:
            conn.execute(query, params)
            conn.commit()
            return True
            
    except Exception as e:
        print(f"❌ update_signal_performance 錯誤: {e}")
        return False

def dup_sort_save(df, strategy_name, table_name='signal_reports'):
    if df is None or df.empty:
        print(f" ⚠️ [{strategy_name}] 無訊號，跳過儲存。")
        return

    # 1. 精準去重：確保 [日期, 股號, 策略] 的組合唯一
    df.drop_duplicates(subset=['date', 'symbol', 'signal_type'], inplace=True)

    # 2. 排序：先按策略類別，再按漲幅排序
    # 注意：change_pct 轉浮點數排序會更精準
    df['temp_change_pct'] = df['change_pct'].str.rstrip('%').astype(float)
    df.sort_values(by=['signal_type', 'temp_change_pct'], ascending=[True, False], inplace=True)
    df.drop(columns=['temp_change_pct'], inplace=True)

    # 3. 儲存到 DB
    save_signals_to_db(df, table_name=table_name)
    print(f" ✅ [{strategy_name}] 已去重並儲存 {len(df)} 筆資料。")

def update_to_tracking(row_id:int, symbol: str, buy_date: str, note: str):
    """
    將股票轉入現役名單 (TRACKING)。
    """
    try:
        engine = get_db_engine()
        
        params = {
            "row_id": row_id, 
            "n": note
        }

        query = text(f"""
            UPDATE signal_reports 
            SET final_status = 'TRACKING',
                note = CASE 
                    WHEN note IS NULL OR note = '' THEN :n 
                    ELSE CONCAT(note, ' | ', :n) 
                END
            WHERE id = :row_id
        """)

        with engine.connect() as conn:
            conn.execute(query, params)
            conn.commit()
            return True
            
    except Exception as e:
        print(f"❌ update_to_tracking 錯誤({symbol} {buy_date}): {e}")
        return False

