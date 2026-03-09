import os
import glob
import sys
import re
import pandas as pd
import pandas_market_calendars as mcal
from datetime import datetime
from playwright.sync_api import sync_playwright
import dataframe_image as dfi

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
    
# 2. 強制重載模組
if 'core.notifier' in sys.modules:
    importlib.reload(sys.modules['core.notifier'])


from core.notifier import send_tg_msg, send_tg_photo



# ================= 設定區塊 =================
URL = "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"
SAVE_DIR = "./etf_data"
# ============================================

def check_trading_day():
    tw_cal = mcal.get_calendar('XTAI')
    today_str = datetime.now().strftime('%Y-%m-%d')
    valid_days = tw_cal.valid_days(start_date=today_str, end_date=today_str)
    if valid_days.empty:
        print(f"[{today_str}] 📅 今日股市休市，程式停止。")
        sys.exit(0)

def fetch_with_playwright():
    print("正在開啟瀏覽器並點擊「基金投資組合」...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # 測試時可改為 False
        page = browser.new_page()
        
        try:
            page.goto(URL, wait_until="domcontentloaded")
            
            # 1. 點擊紅框內的標籤 (使用 href 選擇器最精準)
            portfolio_tab = page.locator('a[href="#asset"]')
            if portfolio_tab.is_visible():
                portfolio_tab.click()
                print("✅ 已成功點擊分頁")
            else:
                print("❌ 找不到按鈕，請檢查網址。")
                return None, None

            # 2. 等待表格數據載入 (等待內容區塊出現文字)
            # 我們等待包含「代號」的表格內容出現
            page.wait_for_selector("#asset table", timeout=10000)
            page.wait_for_timeout(1000) # 給予 1 秒渲染緩衝

            # 3. 修正後的日期抓取 (相容西元與民國)
            content_text = page.locator("#asset").inner_text()
            # 尋找 2 到 4 位數的年份
            date_match = re.search(r'(\d{2,4})/(\d{2})/(\d{2})', content_text)
            if date_match:
                y, m, d = date_match.groups()
                year = int(y)
                # 如果年份小於 1000，視為民國年；否則視為西元年
                final_year = year + 1911 if year < 1000 else year
                ad_date = f"{final_year}{m}{d}"
                print(f"📅 辨識到資料日期: {ad_date}")
            else:
                print("❌ 無法從頁面辨識日期字串")
                return None, None

            # 4. 抓取表格資料
            rows = page.locator("#asset table tr").all()
            data = []
            for row in rows:
                tds = row.locator("td").all_text_contents()
                # 關鍵防錯：確保列數足夠且代號為純數字
                if len(tds) >= 3 and tds[0].strip().isdigit():
                    data.append({
                        '股票代號': tds[0].strip(), 
                        '股票名稱': tds[1].strip(), 
                        '股數': float(tds[2].replace(',', '').strip()) 
                    })
            if not data:
                print("❌ 表格解析完成但無股票資料")
                return None, None

            # 5. 存檔
            df = pd.DataFrame(data)
            os.makedirs(SAVE_DIR, exist_ok=True)
            file_path = f"{SAVE_DIR}/holdings_{ad_date}.csv"
            df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print(f"💾 資料已存為: {file_path}")
            browser.close()
            return df, ad_date

        except Exception as e:
            print(f"❌ 模擬執行失敗: {e}")
            browser.close()
            return None, None


def compare_with_prev_trading_day(current_date_str):
    # 1. 透過 mcal 算出「真正的」前一個交易日
    tw_cal = mcal.get_calendar('XTAI')
    today_dt = pd.to_datetime(current_date_str)
    
    # 往前推 10 天抓取有效交易日 (確保能跨過過年或長連假)
    valid_days = tw_cal.valid_days(start_date=today_dt - pd.Timedelta(days=10), end_date=today_dt)
    
    # 將日曆轉成 YYYYMMDD 的字串清單
    valid_days_list = [d.strftime('%Y%m%d') for d in valid_days]
    
    if current_date_str not in valid_days_list:
        print(f"⚠️ {current_date_str} 不在交易日曆中。")
        return None, None
        
    current_idx = valid_days_list.index(current_date_str)
    if current_idx == 0:
        print("⚠️ 交易日曆資料不足，無法找到前一天。")
        return None, None
         
    # 🌟 取得精準的前一交易日
    prev_date_str = valid_days_list[current_idx - 1]
    
    # 2. 定義兩個目標檔案的路徑
    file_new = f"{SAVE_DIR}/holdings_{current_date_str}.csv"
    file_old = f"{SAVE_DIR}/holdings_{prev_date_str}.csv"
    
    # 3. 🚨 嚴格防呆：如果昨天的檔案不存在，直接拒絕比對
    if not os.path.exists(file_old):
        error_msg = f"❌ 缺少前一個交易日 ({prev_date_str[:4]}-{prev_date_str[4:6]}-{prev_date_str[6:]}) 的檔案，請確認當天是否有成功爬取資料。"
        print(error_msg)
        return error_msg, None
        
    print(f"\n[比對分析] 今日: {current_date_str} vs 前一交易日: {prev_date_str}")
    
    # 4. 讀取檔案
    df_new = pd.read_csv(file_new)
    df_old = pd.read_csv(file_old)
    
    # 確保代號一致性
    df_new['股票代號'] = df_new['股票代號'].astype(str)
    df_old['股票代號'] = df_old['股票代號'].astype(str)

    # 以代號為 Key 合併
    merged = pd.merge(df_new[['股票代號', '股票名稱', '股數']], 
                      df_old[['股票代號', '股票名稱', '股數']], 
                      on='股票代號', suffixes=('_今日', '_前一日'), how='outer')
    
    # 解決名稱變 0 的問題：如果今天沒有名稱 (代表被清空)，就拿昨天的名稱來補
    merged['股票名稱'] = merged['股票名稱_今日'].fillna(merged['股票名稱_前一日'])
    
    # 剩下沒有數值的股數，才補上 0
    merged = merged.fillna(0)

    # 差異
    merged['張數'] = merged['股數_今日'] - merged['股數_前一日']
    
    # 換算為張數並轉為整數 (移除 .0)
    merged['張數'] = (merged['張數'] / 1000).astype(int)

    # 篩選變動項目
    changes = merged[merged['張數'].abs() >= 1].copy()

    if not changes.empty:
        # 新增精準的判斷邏輯
        def get_action_label(row):
            if row['股數_前一日'] == 0:
                return "🟢 新買入"
            elif row['股數_今日'] == 0:
                return "🔴 全清空"
            elif row['張數'] > 0:
                return "🟢 買進"
            else:
                return "🔴 賣出"
            
        changes['動作'] = changes.apply(get_action_label, axis=1)
        # ✅ 補上「動作」欄位，讓表格圖片能顯示買賣標籤
        # changes['動作'] = changes['張數'].apply(lambda x: "🟢 買進" if x > 0 else "🔴 賣出")
        
        # 將資料分為買進與賣出
        buy_df = changes[changes['張數'] > 0].sort_values(by='張數', ascending=False)
        sell_df = changes[changes['張數'] < 0].sort_values(by='張數', ascending=True)

        # 組合訊息字串 (維持你原本的寫法，可以在終端機看)
        msg = f"📊 *00981A 統一投信 買賣異動報告*\n"
        msg += f"📅 比較日: {current_date_str[:4]}-{current_date_str[4:6]}-{current_date_str[6:]} vs {prev_date_str[:4]}-{prev_date_str[4:6]}-{prev_date_str[6:]}\n"
        msg += f"-----------------------------------\n\n"

        if not buy_df.empty:
            msg += "🟢 *買進 (張)*\n"
            for _, row in buy_df.iterrows():
                msg += f"  {row['股票代號']:<5} {row['股票名稱']:<6} | {row['張數']}\n"
            msg += "\n"

        if not sell_df.empty:
            msg += "🔴 *賣出 (張)*\n"
            for _, row in sell_df.iterrows():
                msg += f"  {row['股票代號']:<5} {row['股票名稱']:<6} | {row['張數']}\n"
        
        print(msg)
        # ✅ 關鍵修改：同時回傳字串與 DataFrame
        return msg, changes
    else:
        print("\n--- 持股數量無變動 ---")
        return None, None

if __name__ == "__main__":
    check_trading_day()
    df, date = fetch_with_playwright()

    if df is not None:
        report_msg, changes_df = compare_with_prev_trading_day(date)        
        # 發送 Telegram 訊息與圖片
        if changes_df is not None:
            # 先排序，讓買進的在上面，賣出的在下面
            changes_df = changes_df.sort_values(by='張數', ascending=False)
            
            # 重設 DataFrame 的索引，消除排序造成的亂碼
            changes_df = changes_df.reset_index(drop=True)
            
            # 在最左側（第 0 欄）插入「序號」，數值為 index + 1 (讓它從 1 開始)
            changes_df.insert(0, '序號', changes_df.index + 1)
            
            # 將 '序號' 加進要在圖片中顯示的欄位清單
            styled_df = changes_df[['序號', '股票代號', '股票名稱', '動作', '張數']].style.set_properties(**{
                'text-align': 'center',
                'border': '1px solid black',
                'font-family': 'Microsoft JhengHei' 
            }).hide(axis="index") # 依然隱藏原生 index

            # 存成圖片
            img_path = f"{SAVE_DIR}/00981A_change.png"
            dfi.export(styled_df, img_path, max_rows=-1)

            # 發送圖片
            send_tg_photo(img_path, caption=f"📊 00981A 統一投信 買賣異動 ({date})")

            # # 傳送完畢後，把本地端的暫存圖片刪除
            # if os.path.exists(img_path):
            #     os.remove(img_path)
            #     print("🗑️ 暫存圖檔已刪除")
        elif report_msg:
            send_tg_msg(report_msg)
