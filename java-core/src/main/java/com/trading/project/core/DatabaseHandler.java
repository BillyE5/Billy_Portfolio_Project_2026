package com.trading.project.core;

import java.util.List;

/**
 * 資料庫操作介面。
 * 對應 db_handler.py。
 */
public interface DatabaseHandler {

    /**
     * 獲取當前持有的股票庫存。
     * 
     * @return 目前持有的股票代碼列表。
     */
    List<String> getCurrentInventory();

    /**
     * 將交易訊號或訂單記錄儲存到資料庫中。
     * 
     * @param strategyName 策略名稱 (例如: "SWING", "DAY")。
     * @param stockId      股票代碼。
     * @param action       動作："BUY" (買進) 或 "SELL" (賣出)。
     * @param price        執行價格。
     */
    void saveTradeRecord(String strategyName, String stockId, String action, double price);

    /**
     * 獲取歷史收盤價。
     * 
     * @param stockId 股票代號
     * @param days    天數
     * @return 收盤價列表
     */
    List<Double> getHistoricalClosingPrices(String stockId, int days);

    /**
     * 更新每日 K 棒資料 (對應 upd_daily_kbars.py)。
     */
    void updateDailyKbars();

    /**
     * 執行資料庫備份 (對應 bak_all_db_sql.py)。
     * 
     * @param backupPrefix 備份檔名前綴 (例如 "before_calc" 或是計算完成後的備份)
     */
    void backupDatabase(String backupPrefix);
}
