import pyautogui
import pyperclip  # 用來複製中文檔名
import subprocess
import time
import os
import sys
from datetime import datetime
import ctypes
import pygetwindow as gw

# =================設定區=================
# 軟體執行檔路徑 (注意前面的 r 防止轉義)
APP_PATH = r"D:\軟體區\免安裝\MitakeGU\三竹股市.exe"

# 請確認這是三竹軟體視窗左上角顯示的「確切標題」或「部分標題」
TARGET_WINDOW_TITLE = "三竹股市"

# 取得目前腳本所在的目錄 (即 automation/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 圖片資料夾路徑
IMG_DIR = os.path.join(BASE_DIR, "images")

# 3. 輸出的目標檔案完整路徑 (用來檢查是否成功)
OUT_DIR = r"D:\軟體區\免安裝\MitakeGU\USER\OUT"
TODAY_STR = datetime.now().strftime("%Y%m%d")
FILENAME = f"{TODAY_STR}_大單匯集.csv"
FULL_FILE_PATH = os.path.join(OUT_DIR, FILENAME)
# =======================================
# 儲存 CMD 視窗的 ID，方便最後叫回來
CONSOLE_HWND = ctypes.windll.kernel32.GetConsoleWindow()

def set_console_visibility(show=True):
    """ 控制 CMD 視窗：True=顯示並置頂, False=縮小 """
    if not CONSOLE_HWND: return
    
    if show:
        # 9 = SW_RESTORE (還原視窗)
        ctypes.windll.user32.ShowWindow(CONSOLE_HWND, 9)
        # 強制設為前景
        ctypes.windll.user32.SetForegroundWindow(CONSOLE_HWND)
        print("📺 CMD 視窗已回歸！")
    else:
        # 6 = SW_MINIMIZE (縮小)
        ctypes.windll.user32.ShowWindow(CONSOLE_HWND, 6)
    time.sleep(1)

def focus_target_window():
    """ 
    把三竹軟體抓到最前面，移到主螢幕 (0,0)，並回傳原本的位置資訊
    回傳: (window_object, original_x, original_y)
    如果失敗則回傳: (None, 0, 0)
    """
    print(f"🔍 正在尋找視窗標題含 '{TARGET_WINDOW_TITLE}' 的視窗...")
    
    try:
        # 找出所有標題包含關鍵字的視窗
        windows = gw.getWindowsWithTitle(TARGET_WINDOW_TITLE)
        
        if windows:
            win = windows[0] # 取第一個找到的
            
            # 1. 如果是最小化，先還原
            if win.isMinimized:
                win.restore()
                time.sleep(0.5)
            
            # 2. 記住原本的位置(如果在副螢幕)
            org_x, org_y = win.left, win.top
            print(f"📍 視窗原本在: ({org_x}, {org_y})，準備移往主螢幕...")

            # 3. 強制移回主螢幕 (0, 0) 以便截圖辨識
            win.moveTo(0, 0)
            time.sleep(0.5) # 等它移動到位

            # 2. 啟動並聚焦
            win.activate()
            
            # 3. (選用) 如果你想嘗試最大化，把下面這行註解拿掉
            # win.maximize() 
            
            time.sleep(0.5) # 給視窗動畫一點時間
            print(f"✅ 已鎖定視窗：{win.title}")
            return win, org_x, org_y
            # return True
        else:
            print(f"❌ 找不到視窗，請確認軟體是否已開啟？")
            return None, 0, 0
            
    except Exception as e:
        print(f"⚠️ 視窗控制失敗 (可能權限不足): {e}")
        # 備案：如果 pygetwindow 失敗，嘗試用 Alt+Tab 盲切（不推薦，但可當備案）
        return None, 0, 0

def click_image(image_name, retry=10, confidence=0.9):
    """ 找圖點擊 (含路徑處理) """
    img_path = os.path.join(IMG_DIR, image_name)
    # print(f"🔍 尋找: {image_name} ...", end="")
    
    for i in range(retry):
        try:
            location = pyautogui.locateOnScreen(img_path, confidence=confidence, grayscale=True)
            if location:
                pyautogui.click(pyautogui.center(location))
                print(f" -> 點擊 {image_name}")
                return True
            else:
                print(".", end="")
                time.sleep(0.5)
        except Exception as e:
            print(f"\n⚠️ 錯誤: {e}")
            return False
            
    print(f"\n❌ 找不到 {image_name}")
    return False

def minimize_console():
    """ 
    🔮 魔法函數：把目前的 CMD 黑視窗縮小到工作列 
    這樣就不會擋住三竹軟體了
    """
    try:
        # 取得目前 Console 視窗的控制代碼
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            # 2 = SW_SHOWMINIMIZED (縮小視窗)
            # 6 = SW_MINIMIZE (也是縮小)
            ctypes.windll.user32.ShowWindow(hwnd, 6)
            print("📉 已將 CMD 視窗縮小，避免遮擋畫面...")
    except Exception as e:
        print(f"⚠️ 縮小視窗失敗: {e}")

def main():
    # 1. 把自己 (CMD) 縮小，騰出畫面空間
    set_console_visibility(show=False)
    
    # 給它 1 秒縮下去，以免還殘留在畫面上
    time.sleep(0.5) 

    print("🚀 啟動三竹 RPA (大單匯集匯出)...")

    target_win, start_x, start_y = focus_target_window()
    if target_win is None:
        # 如果找不到視窗，嘗試啟動它
        print("嘗試啟動軟體...")
        app_dir = os.path.dirname(APP_PATH)
        subprocess.Popen(APP_PATH, cwd=app_dir)
        time.sleep(25)
        # 再次嘗試抓取
        target_win, start_x, start_y = focus_target_window()
        if target_win is None:
            return # 真的沒救了就退出


    # [Step 1] 點熱門排行 (Menu)
    if not click_image("step1_hot.png"): 
        set_console_visibility(True) # 失敗也要把 CMD 叫回來
        return
    time.sleep(0.5)

    # [Step 2] 點排行類型下拉三角形
    if not click_image("step2_rank_type.png"): 
        set_console_visibility(True)
        return
    time.sleep(0.5)

    # 強制下拉條往上移：按 6 次 PageUp 確保到頂
    print("正在強制歸零選單位置...")
    for _ in range(6): # 測試過最多五次 但保險一點按六次
        pyautogui.press('pageup')
        time.sleep(0.2) # 快速按，給一點點緩衝時間即可

    time.sleep(0.3) # 確保列表滾動停止

    print("⌨️ 嘗試尋找大單按鈕 (使用 PageDown)...")
    
    # [Step 3] 點大單匯集
    # 先檢查一次，說不定不用滾就看得到
    if not click_image("step3_big_order.png", retry=2):
        # 如果沒看到，開始按 PageDown
        print("開始按 PageDown...")
        pyautogui.press('pagedown')
        time.sleep(0.5)
        for _ in range(5):
            pyautogui.press('down')
            time.sleep(0.2)
        time.sleep(0.5)
        print("PageDown + 5 down完成...")
        if not click_image("step3_big_order.png"): 
            set_console_visibility(True)
            return
    

    print("⏳ 等待數據載入 (4秒)...")
    time.sleep(4)

    # [Step 4] 點擊匯出 (Export Icon)
    if not click_image("step4_expert.png", retry=3):
        print("⚠️ 找不到 [匯出] 按鈕 (可能已在該頁面或圖示改變?)")
    
    print("⏳ 等待檔案產出...")
    time.sleep(0.5)

    # 把三竹丟回去副螢幕
    if target_win:
        print(f"👋 任務結束，將三竹視窗送回原本位置 ({start_x}, {start_y})...")
        try:
            target_win.moveTo(start_x, start_y)
        except Exception as e:
            print(f"⚠️ 視窗歸位失敗 (不影響檔案產出): {e}")
    
    # 把 CMD 叫回來
    set_console_visibility(show=True)

    # 最終驗證
    if os.path.exists(FULL_FILE_PATH):
        print(f"✅ 成功產出：{FILENAME}")
        sys.exit(0)
    else:
        print(f"❌ 檔案未產生，請檢查。")
        sys.exit(1)

if __name__ == "__main__":
    pyautogui.FAILSAFE = True
    try:
        main()
    except Exception as e:
        # 捕捉所有未預期的錯誤，避免 Bat 檔接到奇怪的錯誤碼
        set_console_visibility(show=True)
        print(f"🔥 發生未預期錯誤: {e}")
        sys.exit(1)