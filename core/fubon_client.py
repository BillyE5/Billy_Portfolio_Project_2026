import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from fubon_neo.sdk import FubonSDK
## 2.2.4 及以後版本 (使用 Exception 進行例外處理)
from fubon_neo.fugle_marketdata.rest.base_rest import FugleAPIError
from dotenv import load_dotenv
from core.db_handler import save_kbars_to_db, load_kbars_from_db
from core.utils import get_stock_name, get_yf_suffix
import time
import logging
import yfinance as yf
import pandas_market_calendars as mcal
import platform
from pathlib import Path

LOGGER = logging.getLogger(__name__)
# 確保在模組載入時設置基本配置，這樣它就會顯示出來
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
# 載入 .env 檔案中的所有變數
load_dotenv()

class FubonClient:
    """
    富邦 API 連線與數據獲取核心類別。
    封裝登入、行情連線、REST Client 實例。
    """
    def __init__(self):
        """初始化時執行登入，並準備 API 實例。"""
        
        # 初始化台灣行事曆
        self.twse_calendar = mcal.get_calendar('XTAI')

        # 從 .env 讀取四個憑證
        self.user_id = os.getenv("FUBO_USER_ID")
        self.user_password = os.getenv("FUBO_PASSWORD")

        # 跨平台動態偵測路徑
        current_system = platform.system()
        
        if current_system == "Windows":
            raw_path = os.getenv("CERT_PATH_WIN")
        else:
            raw_path = os.getenv("CERT_PATH_MAC")

        # 使用 Path 處理格式並確保路徑存在（防呆）
        if raw_path:
            p = Path(raw_path)
            self.cert_path = str(p) 
            
            if not p.exists():
                print(f"⚠️ 警告：找不到憑證檔案於 {self.cert_path}")
        else:
            print("❌ 錯誤：.env 中未設定憑證路徑")
        self.cert_pass = os.getenv("FUBO_CERT_PASS")

        # 核心 API 實例：由登入步驟產生
        self.sdk = None           # 整個 SDK 實例
        self.restStock = None    # 專門用於取 K 棒的 restStock 實例
        
        # 執行登入
        self._login()
        
    def _login(self):
        """
        處理富邦 API 的登入邏輯。
        """
        # print("--- 正在嘗試連接並登入富邦 API ---")
        if not all([self.user_id, self.user_password, self.cert_path, self.cert_pass]):
            print("❌ 錯誤：.env 憑證設定不完整，無法登入。")
            # 這裡可以選擇 sys.exit(0) 強制退出
            return
            
        try:
            # 1. 連結 API Server
            self.sdk = FubonSDK()
            
            # 2. 登入
            accounts = self.sdk.login(
                self.user_id, 
                self.user_password, 
                self.cert_path, 
                self.cert_pass
            )

            # 3. 初始化行情連線
            self.sdk.init_realtime() 
            
            self.restStock = self.sdk.marketdata.rest_client.stock
            
            print(f"✅ 富邦 API 登入成功！")
            
        except Exception as e:
            print(f"❌ 富邦 API 連線或登入發生錯誤。錯誤: {e}")
            self.restStock = None # 確保登入失敗時，rest_stock 為空
            # sys.exit(0) # 實戰中建議登入失敗時強制退出

    # 取得股票資訊
    def intraday_ticker(self, symbol):
        try:
            return self.restStock.intraday.ticker(symbol=symbol)
        except FugleAPIError as e:
                function_name = sys._getframe(0).f_code.co_name
                print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
                print(f"Error: {e}")
                print(f"Status Code: {e.status_code}")
                print(f"Response Text: {e.response_text}")
        except Exception as e:
            print(f" > 抓取或整合 [{symbol}] 資料時發生錯誤: {e}")

    # 股票即時報價
    def intraday_quote(self, symbol):
        try:
            return self.restStock.intraday.quote(symbol=symbol)
        except FugleAPIError as e:
                function_name = sys._getframe(0).f_code.co_name
                print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
                print(f"Error: {e}")
                print(f"Status Code: {e.status_code}")
                print(f"Response Text: {e.response_text}")
        except Exception as e:
            print(f" > 抓取或整合 [{symbol}] 資料時發生錯誤: {e}")

    # 股票價格Ｋ線
    def intraday_candles(self, symbol, timeframe='5'):
        try:
            return self.restStock.intraday.candles(symbol=symbol, timeframe=timeframe)
        except FugleAPIError as e:
                function_name = sys._getframe(0).f_code.co_name
                print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
                print(f"Error: {e}")
                print(f"Status Code: {e.status_code}")
                print(f"Response Text: {e.response_text}")
        except Exception as e:
            print(f" > 抓取或整合 [{symbol}] 資料時發生錯誤: {e}")

    # 取得股票分價量表
    def intraday_volumes(self, symbol):
        try:
            return self.restStock.intraday.volumes(symbol=symbol)
        except FugleAPIError as e:
                function_name = sys._getframe(0).f_code.co_name
                print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
                print(f"Error: {e}")
                print(f"Status Code: {e.status_code}")
                print(f"Response Text: {e.response_text}")
        except Exception as e:
            print(f" > 抓取或整合 [{symbol}] 資料時發生錯誤: {e}")
    
    # 歷史行情
    # 取得 1 年內的上市櫃歷史股價
    def historical_candles(self, symbol: str, timeframe: str = "D", start_date_str: str = None, end_date_str: str = None):
        """
        通用地獲取歷史 K 棒資料，根據 timeframe 處理日期參數。
        
        - 日 K ("D")：必須傳遞 start_date_str 和 end_date_str。
        - 分 K ("5", "10", etc.)：忽略日期參數。
        """
        # 1. 初始化 API 參數字典 (只放一定需要的參數)
        api_params = {
            "symbol": symbol,
            "timeframe": timeframe
        }

        try:
            # print("api_params: ", api_params)
            res = self.restStock.historical.candles(**api_params)
            # print("res: ", res)
            return res
        except FugleAPIError as e:
            function_name = sys._getframe(0).f_code.co_name
            print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
            print(f"Error: {e}")
            print(f"Status Code: {e.status_code}")
            print(f"Response Text: {e.response_text}")
        except Exception as e:
            print(f" > 抓取或整合 [{symbol}] 資料時發生錯誤: {e}")


    def find_intraday_strong_stocks(self):
        """【模組 B】: 在盤中掃描即時排行，找出新的人氣股"""
        # print(f"\n--- [{datetime.now().strftime('%H:%M:%S')}] 開始掃描強勢股 ---")

        TOP_N = 80
        try:            
            # --- 步驟 1: 使用 actives 抓取「成交額排行」 ---
            # print("  - 正在抓取成交額排行 (actives)...")
            # trade='value' 代表成交額排行
            actives_by_value = self.restStock.snapshot.actives(market='TSE', trade='value', type='COMMONSTOCK') 
            otc_actives_by_value = self.restStock.snapshot.actives(market='OTC', trade='value', type='COMMONSTOCK')
            actives_by_volume = self.restStock.snapshot.actives(market='TSE', trade='volume', type='COMMONSTOCK') 
            otc_actives_by_volume = self.restStock.snapshot.actives(market='OTC', trade='volume', type='COMMONSTOCK')

            # --- 步驟 2: 使用 movers 抓取「漲幅排行」 ---
            # print("  - 正在抓取漲幅排行 (movers)...")
            # direction='up', change='percent' 代表漲幅排行
            movers_by_amplitude = self.restStock.snapshot.movers(market='TSE', direction='up', change='percent', type='COMMONSTOCK', gte=2, lte=9)
            otc_movers_by_amplitude = self.restStock.snapshot.movers(market='OTC', direction='up', change='percent', type='COMMONSTOCK', gte=2, lte=9)

            # --- 步驟 3: 合併兩份名單，建立初步觀察池 ---
            candidate_symbols = set() # 使用 set 自動過濾重複        

            # 取得當前時間
            now = datetime.now()
            # 3000張
            dynamic_threshold = 3000

            # 排除成交金額小於 1億 的股票
            value_threshold = 100000000

            # 處理 actives 成交額結果
            if actives_by_value.get('data'):
                for stock in actives_by_value['data'][:TOP_N]:
                    if stock.get('tradeVolume', 0) > dynamic_threshold and stock.get('tradeValue', 0) > value_threshold: # 張數>3000, 金額>1E
                        candidate_symbols.add(stock['symbol'])
            if otc_actives_by_value.get('data'):
                for stock in otc_actives_by_value['data'][:TOP_N]:
                    if stock.get('tradeVolume', 0) > dynamic_threshold and stock.get('tradeValue', 0) > value_threshold: # 張數>3000, 金額>1E
                        candidate_symbols.add(stock['symbol'])
            
            # 處理 actives 成交量結果
            if actives_by_volume.get('data'):
                for stock in actives_by_volume['data'][:TOP_N]:
                    if stock.get('tradeVolume', 0) > dynamic_threshold and stock.get('tradeValue', 0) > value_threshold: # 張數>3000, 金額>1E
                        candidate_symbols.add(stock['symbol'])
            if otc_actives_by_volume.get('data'):
                for stock in otc_actives_by_volume['data'][:TOP_N]:
                    if stock.get('tradeVolume', 0) > dynamic_threshold and stock.get('tradeValue', 0) > value_threshold: # 張數>3000, 金額>1E
                        candidate_symbols.add(stock['symbol'])

            # 處理 movers 結果
            if movers_by_amplitude.get('data'):
                for stock in movers_by_amplitude['data'][:TOP_N]:
                    if stock.get('tradeVolume', 0) > dynamic_threshold and stock.get('tradeValue', 0) > value_threshold: # 張數>3000, 金額>1E
                        candidate_symbols.add(stock['symbol'])
            if otc_movers_by_amplitude.get('data'):
                for stock in otc_movers_by_amplitude['data'][:TOP_N]:
                    if stock.get('tradeVolume', 0) > dynamic_threshold and stock.get('tradeValue', 0) > value_threshold: # 張數>3000, 金額>1E
                        candidate_symbols.add(stock['symbol'])
            
            if not candidate_symbols:
                # print("actives/movers 未回傳任何股票。")
                return []
                        
            final_watchlist = list(candidate_symbols)

            print(f"篩選完畢，找到 {len(final_watchlist)} 支強勢股。")
            return final_watchlist

        except FugleAPIError as e:
                function_name = sys._getframe(0).f_code.co_name
                print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
                print(f"Error: {e}")
                print(f"Status Code: {e.status_code}")
                print(f"Response Text: {e.response_text}")
        except Exception as e:
            print(f"執行掃描時發生錯誤: {e}")
            return []

    def filter_daytrade_stocks(self, stock_list: list, market_info_dict: dict = None) -> list:
        """
        過濾股票，排除不能當沖/高價股，並可選地將參考價存入 market_info_dict。
        """
        # 只負責一次性檢查 canDayTrade
        filtered_list = []
        
        # 判斷是否需要存入參考價 (當 market_info_dict 傳入字典時才執行)
        should_save_ref_price = market_info_dict is not None
        if len(stock_list) > 0:
            # print("\n--- 正在過濾非當沖標的 ---")
            for symbol in stock_list:
                try:
                    # 這裡的 API 呼叫只在名單建立時執行一次
                    ticker_res = self.intraday_ticker(symbol)
                    if ticker_res.get('canBuyDayTrade', False):
                        filtered_list.append(symbol)

                        # 只有在當沖模式 (傳入字典) 下才存入參考價
                        if should_save_ref_price:
                            # 存參考價
                            market_info_dict[symbol] = ticker_res.get('referencePrice', None)
                except FugleAPIError as e:
                        function_name = sys._getframe(0).f_code.co_name
                        print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
                        print(f"Error: {e}")
                        print(f"Status Code: {e.status_code}")
                        print(f"Response Text: {e.response_text}")
                except Exception as e:
                    print(f" > 過濾 [{symbol}] 時發生錯誤: {e}")
                    
            # print(f"過濾完畢，剩下 {len(filtered_list)} 支股票(可當沖多 且 股價小於500)。")
        return filtered_list

    def get_prev_5mK_data(self, stock_list: list) -> dict:
        """為指定的股票清單，抓取前一交易日的尾盤 K 棒"""
        # print(f"\n開始抓取過去20根 的 5分K 棒資料...")
        
        d_5mK_day_data = {}
        
        for symbol in stock_list:
            try:
                result = self.historical_candles(symbol=symbol, timeframe="5") 
                # "from": target_day, "to": target_day,  分K中  時間範圍無效 都預設回傳一個月的資料 由新到舊

                # 檢查回傳結果是否有錯誤碼
                if result.get('statusCode') == 429:
                    print(f" > 警告：[{symbol}] 抓取歷史 K 棒資料失敗，原因：{result.get('message', '未知錯誤')}")
                    continue # 跳過這支股票，進行下一輪

                kbars_data = result.get('data', [])

                if len(kbars_data) < 20:
                    # 判斷是完全沒有資料，還是資料不足
                    if not kbars_data:
                        print(f" > 注意：[{symbol}] 未抓取到任何歷史 K 棒資料。")
                    else:
                        print(f" > 注意：[{symbol}] 歷史 K 棒資料不足20筆，已忽略。")
                    continue

                # 將資料載入 Pandas，準備進行本地端篩選
                df = pd.DataFrame(kbars_data)
                df['datetime'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                
                # --- 找出最近一個已收盤的交易日  ---
                # 由於資料由新到舊排列，我們取第一個 K 棒的日期
                unique_dates = df['datetime'].dt.date.unique()
                
                if len(unique_dates) < 1:
                    print(f" > 注意：[{symbol}] 歷史 K 棒資料只有 {unique_dates[0]}，不足兩個交易日，已忽略。")
                    continue
                
                # 取得第一個獨特的日期 (即前一個交易日)
                prev_trading_day_obj = unique_dates[0]

                # 篩選資料為前一個交易日
                df_previous_day = df[df['datetime'].dt.date == prev_trading_day_obj]
                if df_previous_day.empty:
                    continue

                # 排序並取出最後 20 根
                df_previous_day_sorted = df_previous_day.sort_values(by='datetime', ascending=True)

                # 將 DataFrame 轉換回 List of Dictionaries
                # 使用 .to_dict('records') 方法可以將每一行轉換為一個字典，並組成一個列表。
                last_20_kbars_list = df_previous_day_sorted.tail(20).to_dict('records')

                # key 是股票代號，value 是最前面 20 根 K 棒的 dic
                # 注意：這裡的 value 變成了一個 list
                d_5mK_day_data[symbol] = last_20_kbars_list
            
            except FugleAPIError as e:
                function_name = sys._getframe(0).f_code.co_name
                print(f"--- 🚨 錯誤發生在: {function_name} 🚨 ---")
                print(f"Error: {e}")
                print(f"Status Code: {e.status_code}")
                print(f"Response Text: {e.response_text}")

            except Exception as e:
                print(f"  > 抓取 [{symbol}] 昨日資料時發生錯誤: {e}")

        # print(f"資料準備完畢，共取得 {len(d_5mK_day_data)} 支股票的數據。")
        
        # 3. 在函式結束時，回傳包含所有結果的字典
        return d_5mK_day_data


    def _process_single_stock_history(self, symbol, target_days, today_str, today_date):
        """
        處理單一股票的歷史 K 棒抓取與整合邏輯 (供 fetch_daily_kbars_with_today 用)
        """
        # 轉換 symbol 格式：會自動查stock_info.json表，回傳 ".TW" 或 ".TWO"
        suffix = get_yf_suffix(symbol) 
        yf_symbol = f"{symbol}{suffix}"
        
        daily_df = pd.DataFrame() # 最終要回傳的 df

        try:
            # ----------------------------------------------------
            # 🌟 1. DB 查詢階段：嘗試從 DB 讀取 🌟
            # ----------------------------------------------------
            db_df = load_kbars_from_db(symbol, target_days)

            # 清理 DB 中的今日資料 (若有)，避免重複
            # 盤中的話是沒有今天的 收盤才會跑 upd_daily_kbars
            if not db_df.empty:
                db_df['date'] = pd.to_datetime(db_df['date']) # 確保是 datetime
                last_db_date = db_df['date'].max().strftime('%Y-%m-%d')
                if last_db_date == today_str:
                    db_df = db_df[db_df['date'] != today_str]

            # ----------------------------------------------------
            # 🌟 2. 補歷史資料階段 (yfinance / Fugle) 🌟
            # ----------------------------------------------------
            api_df = pd.DataFrame()
            
            # 情境 A: DB 有資料，只需要補齊中間的空窗期
            if not db_df.empty:
                # API 只需要抓取從 DB 記錄的最後一天『之後』到今天的 K 棒
                last_db_date = db_df['date'].max().date()
                
                # 計算空窗期
                # API 開始抓取的日期是 DB 最後一天 + 1 天
                start_date = last_db_date + timedelta(days=1)
                # 結束日：昨天 (因為今天盤中不抓)
                end_date = today_date - timedelta(days=1)
                
                # 判斷是否需要補資料 (如果 start > end，代表 DB 已經是最新的)
                if start_date <= end_date:
                    start_str = start_date.strftime('%Y-%m-%d')
                    end_str = end_date.strftime('%Y-%m-%d')
                    # yfinance 的 end 是 exclusive (不包含)，所以要設為「今天」，才會抓到「昨天」
                    yf_end_str = today_str 

                    # schedule() 會回傳這段時間內所有的交易時段
                    # 雖然 yfinance 不會報錯，但用 Calendar 先檢查可以省一次網路請求
                    schedule = self.twse_calendar.schedule(start_date=start_str, end_date=end_str)
                    
                    if not schedule.empty:
                        # print(f" > [{symbol}] 發現缺漏，呼叫 yfinance 補資料: {start_str} ~ {yf_end_str}")
                        try:
                            yf_data = yf.download(
                                yf_symbol, 
                                start=start_str, 
                                end=yf_end_str, 
                                progress=False
                            )
                            
                            if not yf_data.empty:
                                # --- 資料清洗 (與情境 B 保持一致) ---
                                yf_data = yf_data.reset_index()
                                yf_data.rename(columns={'Date': 'date'}, inplace=True)
                                
                                yf_data['date'] = yf_data['date'].dt.tz_localize(None)
                                api_df = yf_data
                            else:
                                pass
                                # print(f"   ⚠️ yfinance在此區間無資料 (可能休市)。")
                        except Exception as e:
                            print(f"   ⚠️ yfinance 補資料失敗: {e}")
                            api_df = pd.DataFrame()
                    else:
                        # print(f" > [{symbol}] 區間內無交易日 (假日/休市)，跳過。")
                        pass
            
            # 情境 B: DB 為空，使用 yfinance 抓取大量歷史資料(至少三個月)
            else:
                # print(f" > [{symbol}] DB 為空，使用 yfinance 抓取歷史數據...")
                try:
                    # yfinance 下載 (自動處理假日)
                    yf_data = yf.download(yf_symbol, period="4mo", interval="1d", progress=False, auto_adjust=True) # 文件寫3mo 或6mo 不過測試有4mo
                    
                    if not yf_data.empty:
                        # yfinance 格式整理：Reset Index 把 Date 變成欄位
                        yf_data = yf_data.reset_index()
                        
                        # 統一欄位名稱為小寫，以符合後續邏輯
                        yf_data.rename(columns={'Date': 'date'}, inplace=True)
                        
                        # 移除時區資訊 (如果有)
                        yf_data['date'] = yf_data['date'].dt.tz_localize(None)
                        
                        # 篩選掉今天的資料 (如果 yfinance 已經有今天的話)
                        yf_data = yf_data[yf_data['date'].dt.date < today_date]
                        
                        api_df = yf_data
                        
                        # print(f"   ✅ yfinance 成功取得 {len(api_df)} 筆資料。")
                    else:
                        print(f"   ⚠️ yfinance 未回傳資料 ({symbol})。")
                        
                except Exception as e:
                    print(f"   ❌ yfinance 下載失敗 ({symbol}): {e}")

            # ----------------------------------------------------
            # 🌟 3. DB 寫入階段：將 API 新數據寫入 DB 🌟
            # ----------------------------------------------------
            if not api_df.empty:
                # 確保必要欄位存在
                required_cols = ['date', 'Open', 'High', 'Low', 'Close', 'Volume']
                # yfinance 有時會產生 MultiIndex columns，需要平面化
                if isinstance(api_df.columns, pd.MultiIndex):
                    api_df.columns = api_df.columns.get_level_values(0)
                    api_df.rename(columns={'Date': 'date'}, inplace=True)

                # 簡單檢查欄位
                if all(col in api_df.columns for col in required_cols):
                    # 格式化 date 為字串 (如果 DB handler 需要) 或保持 datetime
                    # 加入 symbol 欄位
                    api_df['symbol'] = symbol
                    api_df['stock_name'] = get_stock_name(symbol)
                    save_kbars_to_db(api_df)
                else:
                    print(f"   ⚠️ [{symbol}] 資料欄位不符，跳過寫入。")
            
            # ----------------------------------------------------
            # 🌟 4. 數據整合與今日K棒更新 🌟
            # ----------------------------------------------------

            # 重新讀取完整歷史 (包含剛剛 yfinance 寫入的)
            # 為了效率，如果不怕 DB 延遲，其實可以直接拿 db_df + api_df，
            # 但為了保險起見 (且 load_kbars_from_db 通常很快)，重讀確保一致性
            history_df = load_kbars_from_db(symbol, target_days)
            
            if history_df.empty:
                return symbol, None

            # 確保 history_df 是 Open/High/Low/Close (首字大寫) 以符合 pandas-ta 習慣
            history_df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            
            # 確保時間由舊到新
            history_df = history_df.sort_values(by='date', ascending=True).reset_index(drop=True)
            
            # 補上今天的 Quote
            today_quote = self.intraday_quote(symbol)
            
            # 確保有抓到資料
            if not today_quote or 'total' not in today_quote:
                # 如果連報價都沒有，視為資料異常，看你要 return None 還是只回傳歷史資料
                # 沒報價就跳過
                return symbol, None
            
            # ----------------------------------------------------
            # 🛑 過濾器 A：檢查「五檔掛單深度」 (防範滑價/流動性陷阱)
            # ----------------------------------------------------
            # 取得五檔委買與委賣的總張數
            # today_quote['bids'] 是一個 list of dict [{'price':.., 'size':..}, ...]
            bid_sum = sum([item['size'] for item in today_quote.get('bids', [])])
            ask_sum = sum([item['size'] for item in today_quote.get('asks', [])])
            depth_total = bid_sum + ask_sum

            # 設定門檻：委買賣十檔合計少於 400 張，視為淺盤
            if depth_total < 400:
                # print(f" 🗑️ [{symbol}] 剔除：五檔掛單過少 ({depth_total} 張)")
                return symbol, None  # 直接回傳 None，不處理後續

            # ----------------------------------------------------
            # 🛑 過濾器 B：檢查「平均每筆成交張數」 (防範散戶盤)
            # ----------------------------------------------------
            total_data = today_quote['total']
            trade_vol = total_data.get('tradeVolume', 0)  # 總成交張數
            trans_cnt = total_data.get('transaction', 0)  # 總成交筆數
            
            # 避免除以零錯誤
            if trans_cnt > 0:
                avg_tx_size = trade_vol / trans_cnt
            else:
                avg_tx_size = 0
            
            # 設定門檻：例如平均每筆小於 5 張 (雖然你算出來是 3 張，建議可設 3~5)
            # 註：這裡用簡單總量除總筆數即可，雖然包含開盤集合競價，但對於過濾「極爛股」已經足夠
            if avg_tx_size < 3:  # 這裡設 3 比較安全，設 5 可能會殺掉一些中型股
                # print(f" 🗑️ [{symbol}] 剔除：散戶盤 (平均每筆 {avg_tx_size:.2f} 張)")
                return symbol, None
            
            # 預設結果就是歷史資料
            combined_df = history_df 

            # 如果今天有報價且已開盤，嘗試進行合併
            if today_quote and today_quote.get('closePrice'):
                today_data = {
                    'date': pd.to_datetime(today_str),
                    'Open': today_quote['openPrice'],
                    'High': today_quote['highPrice'],
                    'Low': today_quote['lowPrice'],
                    'Close': today_quote['closePrice'],
                    'VWAP': today_quote['avgPrice'], # 成交均價 VWAP
                    'Volume': today_quote['total']['tradeVolume']*1000, # tradeVolume 張數 *1000 換成股數
                    'change': today_quote['change'], # 漲跌%
                    'referencePrice': today_quote['referencePrice'], # 參考價
                }
                df_today = pd.DataFrame([today_data])
                
                # 1. 建立初步清單
                raw_candidates = [history_df, df_today]

                # 2. 過濾掉 None、empty 或 全 NA 的項目
                dataframes_to_concat = [
                    df for df in raw_candidates 
                    if df is not None and not df.empty and not df.dropna(how='all').empty
                ]

                # 3. 合併
                if dataframes_to_concat:
                    combined_df = pd.concat(dataframes_to_concat, ignore_index=True)
                else:
                    combined_df = pd.DataFrame()

            return symbol, combined_df

        except FugleAPIError as e:
            # 429 check (Optional, though usually requests handles this)
            print(f"   ⚠️ [{symbol}] API 錯誤: {e}")
            return symbol, None
       
        except Exception as e:
            print(f" > 處理 [{symbol}] 時發生未預期錯誤: {e}")
            # import traceback
            # traceback.print_exc()
            return symbol, None


    def fetch_daily_kbars_with_today(self, stock_list):
        """
        抓取歷史日K資料 (平行化運算版)。
        """
        print(f"\n開始抓取歷史 K 棒並整合當天收盤資料 ({len(stock_list)})...")
        daily_kbars_dict = {}
        today_date = datetime.now().date()
        today_str = today_date.strftime('%Y-%m-%d')
        
        target_days = 120
        # 設定90天 還不夠 遇到年假9天(還有T+2 兩天 共11天) 大約也只有56天 開盤日無法計算60MA
        
        # 使用 ThreadPoolExecutor 平行處理
        # 建議 workers 設為 10-20 左右，不要太高以免被 Fubon/Yahoo 鎖 IP
        
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=20) as executor:
            # 提交所有任務
            future_to_symbol = {
                executor.submit(self._process_single_stock_history, symbol, target_days, today_str, today_date): symbol 
                for symbol in stock_list
            }
            
            # 使用 tqdm 顯示進度條 (如果有裝的話，沒有就用簡單計數)
            try:
                from tqdm import tqdm
                futures = tqdm(as_completed(future_to_symbol), total=len(stock_list), desc="Downloading", unit="stock")
            except ImportError:
                print("   (未安裝 tqdm，使用一般進度顯示)")
                futures = as_completed(future_to_symbol)
            
            count = 0
            for future in futures:
                try:
                    symbol, df = future.result()
                    if df is not None and not df.empty:
                        daily_kbars_dict[symbol] = df
                    
                    count += 1
                    # 每 50 筆顯示一次進度 (如果沒 tqdm)
                    if 'tqdm' not in sys.modules and count % 50 == 0:
                        print(f"   - 已完成 {count}/{len(stock_list)}...")

                except Exception as e:
                    print(f"   ❌ 任務執行失敗: {e}")

        return daily_kbars_dict
