import sys
import pandas_market_calendars as mcal
from datetime import datetime

# check_market_open.py  檢查是否有開盤

if __name__ == "__main__":
    try:
        tw_cal = mcal.get_calendar('XTAI')
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        valid_days = tw_cal.valid_days(start_date=today_str, end_date=today_str)
        valid_dates_list = [d.strftime('%Y-%m-%d') for d in valid_days]

        if today_str not in valid_dates_list:
            print(f"[{today_str}] 📅 今日台灣股市休市。")
            sys.exit(99)  # 休市回傳 99
        else:
            print(f"[{today_str}] 📈 今日正常開盤。")
            sys.exit(0)   # 開盤回傳 0 (正常結束)
            
    except Exception as e:
        print(f"🔥 日曆檢查發生未預期錯誤: {e}")
        sys.exit(1)       # 發生錯誤回傳 1