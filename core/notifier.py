# core/notifier.py
import requests
import os
import fitz  # PyMuPDF
from dotenv import load_dotenv

# ==========================================
# 🔑 設定區
# ==========================================
load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

def send_tg_msg(message, parse_mode="Markdown"):
    """
    發送純文字訊息到 Telegram
    :param parse_mode: 預設 "Markdown"，如果傳入 None 則為純文字模式
    """
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TG_CHAT_ID,
            "text": message,
        }
        # 只有當 parse_mode 有值的時候才加入 payload
        if parse_mode:
            payload["parse_mode"] = parse_mode
            
        # 設定 timeout 避免網路卡死程式
        resp = requests.post(url, json=payload, timeout=10)
        
        if resp.status_code == 200:
            print("✅ TG 訊息發送成功")
        else:
            print(f"❌ TG 發送失敗: {resp.text}")
            
    except Exception as e:
        print(f"❌ TG 連線錯誤: {e}")

def send_tg_file(file_path, caption=""):
    """
    發送檔案 (PDF, 圖片) 到 Telegram
    """
    if not os.path.exists(file_path):
        print(f"❌ 找不到檔案: {file_path}")
        return

    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendDocument"
        
        # 開啟檔案並傳送
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': TG_CHAT_ID, 'caption': caption}
            resp = requests.post(url, files=files, data=data, timeout=30)
            
        if resp.status_code == 200:
            print(f"✅ 檔案發送成功: {os.path.basename(file_path)}")
        else:
            print(f"❌ 檔案發送失敗: {resp.text}")

    except Exception as e:
        print(f"❌ TG 傳檔錯誤: {e}")

def pdf_to_image_simple(pdf_path):
    """
    使用 PyMuPDF 將 PDF 第一頁轉成圖片 (無需安裝 Poppler)
    """
    try:
        # 1. 打開 PDF
        doc = fitz.open(pdf_path)
        
        # 2. 讀取第一頁 (頁碼從 0 開始)
        page = doc.load_page(0) 
        
        # 3. 設定解析度 (Zoom=2 代表放大兩倍，讓文字在手機看更清晰)
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        
        # 4. 存成圖片 (跟 PDF 同檔名，只是副檔名改 .png)
        img_path = pdf_path.replace(".pdf", "_preview.png")
        pix.save(img_path)
        
        doc.close()
        return img_path
        
    except Exception as e:
        print(f"❌ 圖片轉換失敗: {e}")
        return None

def send_tg_photo(file_path, caption=""):
    """
    發送圖片 (會自動壓縮並直接顯示預覽)
    """
    if not os.path.exists(file_path):
        print(f"❌ 找不到圖片: {file_path}")
        return

    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
        
        with open(file_path, 'rb') as f:
            # 注意：這裡的 key 是 'photo'，不是 'document'
            files = {'photo': f}
            data = {'chat_id': TG_CHAT_ID, 'caption': caption}
            resp = requests.post(url, files=files, data=data, timeout=30)
            
        if resp.status_code == 200:
            print(f"✅ 圖片預覽發送成功: {os.path.basename(file_path)}")
        else:
            print(f"❌ 圖片發送失敗: {resp.text}")

    except Exception as e:
        print(f"❌ TG 傳圖錯誤: {e}")

