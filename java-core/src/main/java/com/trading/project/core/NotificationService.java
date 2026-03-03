package com.trading.project.core;

import java.io.File;

/**
 * 系統通知服務介面。
 */
public interface NotificationService {

    /**
     * 傳送純文字訊息到 TG Bot。
     * 
     * @param message 訊息內容
     */
    void sendMessage(String message);

    /**
     * 將 PDF 報告轉換為圖片，並發送至 TG Bot。
     * 
     * @param pdfReport 產生的 PDF 報告檔案
     * @param caption   圖片說明
     */
    void sendReportAsImage(File pdfReport, String caption);
}
