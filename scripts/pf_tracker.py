# pf_tracker.py
# 更新選股出來的名單績效成果

import sys
import os
import pandas as pd
import pandas_market_calendars as mcal
from datetime import datetime, timedelta, date
import re
import unicodedata

# --- 路徑設定 ---
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)
from core.utils import calculate_holding_days, check_stock_survival_rules

try:
    from core.db_handler import get_db_engine, _read_dataframe_from_sql, get_close_price_from_db, get_stock_ma_indicators, get_latest_data_with_atr, close_trade_signal, update_to_watchlist, update_to_resurrected, append_note, update_signal_pf, get_one_day_kbar, load_kbars_from_db, update_to_tracking
    from core.notifier import send_line_message, send_tg_msg
except ImportError as e:
    print(f"❌ 匯入錯誤: {e}")
    sys.exit(1)

class PfTracker:
    def __init__(self):
        self.engine = get_db_engine()
        self.calendar = mcal.get_calendar('XTAI')
        print("✅ 績效追蹤器已啟動")

    def get_target_dates(self, entry_date_str, days_list=[1, 3, 5, 10]):
        # 往後抓 40 天確保覆蓋
        start_date = pd.to_datetime(entry_date_str)
        end_date = start_date + timedelta(days=40)
        
        schedule = self.calendar.schedule(start_date=start_date, end_date=end_date)
        trading_days = schedule.index.strftime('%Y-%m-%d').tolist()
        
        targets = {}
        # trading_days[0] 應該是 entry_date (如果那天有開市)
        # trading_days[1] 就是 T+1
        
        for d in days_list:
            if len(trading_days) > d:
                targets[d] = trading_days[d]
            else:
                targets[d] = None
        
        return targets
    
    def evaluate_stock_health(self, row, days_held):
        """
        根據策略類型與持有天數，判斷股票是否健康。
        Returns: (is_passing: bool, message: str)
        """
        today_str = datetime.now().strftime('%Y-%m-%d')

        row_id = row['id']
        symbol = row['symbol']
        signal_type = str(row['signal_type'])
        current_price = float(row['current_price'])
        pre_close = float(row['pre_close']) if pd.notna(row['pre_close']) else float(row['Close'])
        current_roi = float(row['current_roi']) if pd.notna(row['current_roi']) else 0.0
        status = row['final_status']
        buy_price = float(row['Close']) # 訊號日買價

        strategy_name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', signal_type)
        strategy_name = unicodedata.normalize('NFKC', strategy_name)

        # ====================================================
        # 實戰部位檢查
        # ====================================================
        # 準備 MA 數據
        ma_data = None
        ma_data = get_stock_ma_indicators(symbol, today_str)

        is_safe, msg = check_stock_survival_rules(
            current_price=current_price,
            current_roi=current_roi,
            days_held=days_held,
            ma_data=ma_data,
            strategy_name=strategy_name,
            current_status=status,
            pre_close=pre_close
        )
        return is_safe, msg

    def _process_single_signal(self, row):
        """
        處理單筆訊號的績效更新邏輯 (供 update_performance 平行化呼叫)
        Returns: (bool) 是否有更新
        """
        try:
            row_id = row['id']
            symbol = row['symbol']
            stock_name = row['stock_name']
            entry_date = row['date']
            entry_price = float(row['Close'])
            entry_date_str = entry_date.strftime('%Y-%m-%d')

            # 計算 T+1, T+5, T+10 目標日期
            target_dates = self.get_target_dates(entry_date_str, [1, 3, 5, 10])
            
            updates = {}

            # 1. 更新最新現價 與 ATR 與 Pre_Close
            latest_price, pre_close, atr_value, latest_date = get_latest_data_with_atr(symbol)
            
            if latest_price:
                current_roi = ((latest_price - entry_price) / entry_price) * 100
                updates["current_price"] = latest_price
                updates["current_roi"] = round(current_roi, 2)
                
                # 寫入 ATR 與 昨收
                if atr_value > 0:
                    updates["atr_value"] = round(atr_value, 2)
                if pre_close:
                    updates["pre_close"] = pre_close

            # 2. 檢查 T+1
            if pd.isna(row['roi_1d']):
                target_date = target_dates[1]
                price = get_close_price_from_db(symbol, target_date)
                if price:
                    roi = ((price - entry_price) / entry_price) * 100
                    updates["price_1d"] = price
                    updates["roi_1d"] = round(roi, 2)
                    # print(f"   📈 [{symbol + ' ' + stock_name + ' ' + entry_date_str}] T+1 收盤 {price}, 績效: {roi:.2f}%")
            
            # --- 檢查 T+5 ---
            if pd.isna(row['roi_5d']):
                target_date = target_dates[5]
                price = get_close_price_from_db(symbol, target_date)
                if price:
                    roi = ((price - entry_price) / entry_price) * 100
                    updates["price_5d"] = price
                    updates["roi_5d"] = round(roi, 2)
                    # print(f"   📈 [{symbol + ' ' + stock_name + ' ' + entry_date_str}] T+5 收盤 {price}, 績效: {roi:.2f}%")

            # --- 檢查 T+10 ---
            if pd.isna(row['roi_10d']):
                target_date = target_dates[10]
                price = get_close_price_from_db(symbol, target_date)
                if price:
                    roi = ((price - entry_price) / entry_price) * 100
                    updates["price_10d"] = price
                    updates["roi_10d"] = round(roi, 2)
                    # print(f"   📈 [{symbol + ' ' + stock_name + ' ' + entry_date_str}] T+10 收盤 {price}, 績效: {roi:.2f}%")
            
            # 執行更新 SQL
            if updates:
                success = update_signal_pf(row_id, updates)
                return success
            
            return False
            
        except Exception as e:
            print(f"❌ 處理 {symbol} 績效時發生錯誤: {e}")
            return False

    def update_performance(self):
        """更新當前績效 與 計算 T+1 +5 +10的績效"""
        # 1. 撈出還在追蹤的訊號
        # 包含：TRACKING (一般現役), WATCH_LIST (殭屍), RESURRECTED (復活軍團)
        query = "SELECT * FROM signal_reports WHERE final_status IN ('TRACKING', 'WATCH_LIST', 'RESURRECTED') OR (final_status = 'CLOSED' AND roi_10d IS NULL)"
        signals_df = _read_dataframe_from_sql(query)
        
        if signals_df.empty:
            # print("👍 目前沒有需要追蹤績效的訊號。")
            return

        print(f"🔍 正在檢查 {len(signals_df)} 筆訊號的績效 (平行運算中)...")
        
        updates_count = 0
        
        # 使用 ThreadPoolExecutor 平行處理
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # 轉換為 row dict list 以便處理
        rows = [row for _, row in signals_df.iterrows()]

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_row = {executor.submit(self._process_single_signal, row): row for row in rows}
            
            for future in as_completed(future_to_row):
                try:
                    updated = future.result()
                    if updated:
                        updates_count += 1
                except Exception as e:
                    print(f"Update error: {e}")

        print("-" * 30)
        print(f"📊 更新完成: {updates_count} 筆資料更新。")

    def check_underperformers(self):
        print("👮 正在考核「現役股」與「復活股」績效...")

        # 撈出 'TRACKING', 'RESURRECTED' 的股票
        query = "SELECT * FROM signal_reports WHERE final_status IN ('TRACKING', 'RESURRECTED')"
        df = _read_dataframe_from_sql(query)
        
        if df.empty:
            # print("   (沒有 TRACKING 狀態的股票)")
            return
        
        # 設定截止日 (收盤晚上跑用 today, 隔天開盤前跑用 yesterday)
        calc_end_date = pd.Timestamp.now().normalize()

        zombie_count = 0
        
        for index, row in df.iterrows():
            row_id = row['id']
            symbol = row['symbol']
            stock_name = row['stock_name']
            entry_date = pd.to_datetime(row['date'])
            entry_date_str = entry_date.strftime('%Y-%m-%d')
            entry_price = float(row['Close'])

            # 讀取最新 ROI，並強制轉為 float
            current_roi = float(row['current_roi']) if pd.notna(row['current_roi']) else 0.0
            current_price = float(row['current_price']) if pd.notna(row['current_price']) else 0.0

            # 計算持有天數
            days_held = 0
            if calc_end_date >= entry_date:
                days_held = calculate_holding_days(entry_date, calc_end_date)
            
            # 防呆：避免除以 0
            if days_held <= 0:
                continue
            
            # 檢驗是否達到績效標準
            is_passing, msg = self.evaluate_stock_health(row, days_held) # underperformers
            
            # 定義必殺關鍵字
            critical_exit_keywords = ["硬停損"]
            is_critical_death = any(k in msg for k in critical_exit_keywords)

            # 只處理不及格的
            if not is_passing:
                # --- 情境 A: 硬停損 (直接結案) ---
                if is_critical_death:
                    death_reason = f"🛑 強制止損 (T+{days_held}): {msg}"
                    print(f"🛑 [停損] {entry_date_str} {symbol} {stock_name} 觸發硬停損/強制出場。原因: {death_reason}")
                    
                    close_trade_signal(
                        row_id=row_id,
                        entry_price=entry_price,
                        exit_price=current_price,
                        exit_reason=death_reason,
                        exit_date=calc_end_date.strftime('%Y-%m-%d')
                    )
                    # return 或 continue，因為已經賣了，不用再做下面的降級處理
                
                # --- 情境 B: 獲利了結 (Hero Retirement) ---
                # 如果是賺很多的飆股 (>20%) 破10MA線，直接讓它光榮退役
                elif current_roi > 20.0:
                    death_reason = f"(T+{days_held}) ({current_roi:.2f}%) 獲利了結: 跌破趨勢線10MA"
                    print(f"💰 [止盈] {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%) 獲利出場。原因: {death_reason}")

                    close_trade_signal(
                        row_id=row_id,
                        entry_price=entry_price,
                        exit_price=current_price,
                        exit_reason=death_reason,
                        exit_date=calc_end_date.strftime('%Y-%m-%d')
                    )
                    # 直接結案，不經過殭屍流程

                # --- 情境 C: 普通違規 (轉殭屍) ---
                else:
                    # 根據天數決定命運
                    
                    # 1. 如果已經持有超過 10 天 -> 不進殭屍，直接結案！
                    if days_held >= 10:
                        # 分流寫理由
                        if current_roi > 0:
                            death_reason = f"(T+{days_held}) ({current_roi:.2f}%) 逾期獲利了結: 盤整過久且轉弱，獲利出場。"
                            print(f"💰 [止盈] {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%)。原因: {death_reason}")

                        else:
                            death_reason = f"(T+{days_held}) ({current_roi:.2f}%) 資金效率回收: 盤整逾期且轉弱，換股操作"
                            print(f"💀 [結案] {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%)。原因: {death_reason}")

                        close_trade_signal(
                            row_id=row_id,
                            entry_price=entry_price,
                            exit_price=current_price,
                            exit_reason=death_reason,
                            exit_date=calc_end_date.strftime('%Y-%m-%d')
                        )
                        # 這裡不需要 closed_count，因為這是在 check_underperformers 裡

                    # 2. 如果還是年輕人 (T < 10) -> 給機會進殭屍區
                    else:
                        # 準備要淘汰了，先看它原本是什麼身分
                        origin_status = row['final_status']

                        if origin_status == 'RESURRECTED':
                            # 曾經復活過，現在又死 -> 二度淘汰
                            new_note = f"(T+{days_held}) ({current_roi:.2f}%) 二度淘汰: {msg}"
                            print(f"⚰️ {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%) 二度淘汰。原因: {msg}")
                            
                            update_to_watchlist(
                                row_id=row_id, 
                                symbol=symbol, 
                                buy_date=entry_date_str, 
                                note=new_note,
                                exit_price=None # 關鍵：不傳價格 # 不要更動到 exit_price 
                            )
                        else:
                            # 首次轉殭屍
                            new_note = f"(T+{days_held}) ({current_roi:.2f}%) 轉入殭屍: {msg}"
                            print(f"🧟 [轉殭屍] {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%) 轉入殭屍名單。原因: {msg}")
                            
                            update_to_watchlist(
                                row_id=row_id, 
                                symbol=symbol, 
                                buy_date=entry_date_str, 
                                note=new_note,
                                exit_price=current_price, # 關鍵：傳入價格 # exit_price 鎖定績效
                                exit_date=calc_end_date.strftime('%Y-%m-%d')
                            )
                            zombie_count += 1                     
            
            else:
                # --- [合格] ---
                print(f"✅ [續抱] {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%); {msg}")
                
        print(f"👮 考核完成，共 {zombie_count} 檔轉弱，移入觀察區。")

    def check_resurrection(self):
        """
        巡視觀察名單 (WATCH_LIST):
        1. 判斷是否復活 (RESURRECTED) - 需過基本健檢 + 階梯式 ROI 門檻
        2. 判斷是否逾期 (CLOSED)      - T+10 仍未復活者強制結案
        """

        print("🚑 正在巡視殭屍名單，檢查是否有「殭屍復活」...")
        
        # 1. 撈出所有被打入冷宮 (WATCH_LIST) 的股票
        query = "SELECT * FROM signal_reports WHERE final_status = 'WATCH_LIST'"
        df = _read_dataframe_from_sql(query)
        
        if df.empty:
            # print("   (觀察名單是空的，沒人需要復活)")
            return

        # 設定計算日 (跟 update_zombie 是一樣的基準)
        calc_end_date = pd.Timestamp.now().normalize()
        resurrect_count = 0
        closed_count = 0
        
        with self.engine.begin() as conn:
            for index, row in df.iterrows():
                row_id = row['id']
                symbol = row['symbol']
                stock_name = row['stock_name']
                entry_price = float(row['Close'])
                entry_date = pd.to_datetime(row['date'])
                entry_date_str = entry_date.strftime('%Y-%m-%d')

                # 確保數值正確
                current_roi = float(row['current_roi']) if pd.notna(row['current_roi']) else 0.0
                current_price = float(row['current_price']) if pd.notna(row['current_price']) else entry_price

                # 計算持有天數
                days_held = 0
                if calc_end_date >= entry_date:
                    days_held = calculate_holding_days(entry_date, calc_end_date)

                # 核心健檢
                is_passing_health, msg = self.evaluate_stock_health(row, days_held) # resurrection
                
                # 定義必殺關鍵字
                critical_exit_keywords = ["硬停損"]
                is_critical_death = any(k in msg for k in critical_exit_keywords)

                # 1. 殭屍還能觸發硬停損？ (代表跌爛了，不用再看了)
                if is_critical_death:
                    death_note = f"🛑 強制止損 (T+{days_held}): {msg}"
                    print(f"🛑 [停損] {entry_date_str} {symbol} {stock_name} 觸發硬停損/強制出場 (ROI: {current_roi}%)。原因: {death_note}")
                    close_trade_signal(
                        row_id=row_id,
                        entry_price=entry_price,
                        exit_price=current_price,
                        exit_reason=death_note,
                        exit_date=calc_end_date.strftime('%Y-%m-%d')
                    )
                    closed_count += 1
                
                # 次優先：是否符合復活條件？ (健檢通過 且 還在黃金救援期 T<9)
                elif is_passing_health and days_held < 9:
                    # --- [復活] ---
                    note = f"(T+{days_held}) 復活成功 ({msg})"
                    print(f"🚀 [復活] {entry_date_str} {symbol} {stock_name} 醒了！ (ROI: {current_roi}%): {note}")
                    
                    update_to_resurrected(
                        row_id=row_id,
                        symbol=symbol,
                        buy_date=entry_date_str,
                        note=f"復活: {note}"
                    )
                    resurrect_count += 1 

                # 3. 既沒死透也沒復活 -> 檢查過期(T+10 老殭屍)
                else:
                    if days_held < 9:
                        # --- [繼續觀察] ---
                        # 沒復活 小於九天的
                        pass
                    else:
                        if is_passing_health and days_held >= 9:
                            # 如果它活起來了，但因為太老(T+9以上)被擋下 資金滯留
                            msg = f"雖達標但已逾期，放棄治療"
                            death_note = f"💀 殭屍股 (T+{days_held}) 逾期不復活 ({msg})"
                            
                            append_note(row_id, death_note)
                            
                        # 時間到了 (T>=10)，強制結案
                        if days_held >= 10:
                            
                            # 依據損益，給予不同的結案理由
                            if current_roi > 0.6:
                                # 雖然動能不足(沒復活)，但至少是賺錢的
                                death_note = f"💰 逾期獲利了結: 動能不足，獲利入袋 ({msg})"
                                print(f"💰 [止盈] {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%)。原因: {death_note}")

                            else:
                                # 賠錢又浪費時間，真正的殭屍
                                death_note = f"💀 殭屍股: 逾期結案 ({msg})"
                                print(f"💀 [結案] {entry_date_str} {symbol} {stock_name} (T+{days_held}) ({current_roi:.2f}%)。原因: {death_note}")

                            close_trade_signal(
                                row_id=row_id,
                                entry_price=entry_price,
                                exit_price=current_price,
                                exit_reason=death_note,
                                exit_date=calc_end_date.strftime('%Y-%m-%d')
                            )
                            closed_count += 1
        
        print(f"✨ 觀察名單巡視完成: {resurrect_count} 檔復活, {closed_count} 檔結案淘汰。")

    def export_ST_inventory(self):
        """
        匯出目前持有的庫存 (TRACKING, RESURRECTED, WATCH_LIST) 到 Excel，
        並發送通知
        """
        # print("💾 正在匯出最新庫存狀態與發送通知...")
        
        query = "SELECT * FROM signal_reports WHERE final_status IN ('TRACKING', 'RESURRECTED', 'WATCH_LIST') ORDER BY final_status, date DESC"
        df = _read_dataframe_from_sql(query)
        
        if df.empty:
            msg = "✅ 今日績效結算完成。\n目前無任何持有或觀察中的庫存。"
            send_line_message(msg)
            send_tg_msg(msg)
            return

        # 狀態中文化
        status_map = {
            'TRACKING': '現役股',
            'RESURRECTED': '復活股',
            'WATCH_LIST': '轉弱殭屍'
        }
        df['final_status'] = df['final_status'].map(status_map).fillna(df['final_status'])

        # 整理欄位與表頭中文化
        col_map = {
            'date': '日期',
            'symbol': '股號',
            'stock_name': '名稱',
            'Close': '進場價',
            'current_price': '今日現價',
            'current_roi': '報酬率(%)',
            'final_status': '目前狀態',
            'signal_type': '策略類型',
            'note': '備註'
        }
        
        # 只取出有定義在 col_map 裡的欄位，並過濾掉 df 沒有的
        available_cols = [c for c in col_map.keys() if c in df.columns]
        export_df = df[available_cols].copy()
        
        # 執行重新命名
        export_df = export_df.rename(columns=col_map)
        
        if '報酬率(%)' in export_df.columns:
            export_df['報酬率(%)'] = pd.to_numeric(export_df['報酬率(%)'], errors='coerce').round(2)

        # 定義狀態的順序
        status_order = ['現役股', '轉弱殭屍', '復活股']
        
        # 將「目前狀態」轉為 Categorical 型態並指定順序
        export_df['目前狀態'] = pd.Categorical(
            export_df['目前狀態'], 
            categories=status_order, 
            ordered=True
        )

        # 執行多重排序：狀態按自定義順序(正向)，報酬率按數值(倒序)
        # ascending=[True, False] 代表第一個欄位由小到大(依自定義順序)，第二個由大到小
        export_df = export_df.sort_values(
            by=['目前狀態', '報酬率(%)'], 
            ascending=[True, False]
        )

        # 準備存檔路徑
        output_dir = os.path.join(current_dir, 'swingTrade', 'out', 'inventory')
        os.makedirs(output_dir, exist_ok=True)
        excel_path = os.path.join(output_dir, "ST_Inventory.xlsx")

        try:
            # 使用 Excel 格式方便長輩閱讀
            export_df.to_excel(excel_path, index=False, engine='openpyxl')
            print(f"   ✅ 庫存表已存至: {excel_path}")
        except Exception as e:
            print(f"   ❌ 匯出 Excel 失敗: {e}")

        # 組合訊息
        today_str = datetime.now().strftime('%Y%m%d')
        # 統計各狀態數量
        status_counts = export_df['目前狀態'].value_counts()
        
        # 計算總資金與總損益來得到真實投報率
        total_invest = export_df['進場價'].sum() * 1000
        total_pnl = ((export_df['今日現價'] - export_df['進場價']) * 1000).sum()
        
        avg_roi = (total_pnl / total_invest * 100) if total_invest > 0 else 0.0

        summary_msg = (
            f"✅ {today_str} 盤後績效結算完成\n\n"
            f"📊 目前庫存總結\n"
            f"🔸 現役股: {status_counts.get('現役股', 0)} 檔\n"
            f"🔸 復活股: {status_counts.get('復活股', 0)} 檔\n"
            f"🔸 轉弱殭屍: {status_counts.get('轉弱殭屍', 0)} 檔\n"
            f"💰 整體未實現平均 ROI: {avg_roi:.2f}%\n"
            "完整明細已同步至雲端。\n"
            f"雲端連結: {os.getenv('GD_ST_PF_REPORT_URL')}"
        )
        
        send_line_message(summary_msg)
        send_tg_msg(summary_msg)

if __name__ == "__main__":
    tracker = PfTracker()
    
    # 1. 負責更新所有狀態的 ROI，並處理 WATCH_LIST 的 T+10 死刑
    tracker.update_performance()
    
    # 2. 檢查 TRACKING 和 RESURRECTED，表現差的丟進 WATCH_LIST
    tracker.check_underperformers()
    
    # 3. 殭屍復活巡視 (處理 WATCH_LIST 表現好的拉回 RESURRECTED)
    tracker.check_resurrection()
    
    # 4. 匯出未結案的庫存並發送通知
    tracker.export_ST_inventory()
