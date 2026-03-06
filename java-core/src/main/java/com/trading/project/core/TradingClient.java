package com.trading.project.core;

import java.util.List;
import java.util.Map;

/**
 * 券商 API 的介面。
 */
public interface TradingClient {

    /**
     * 使用券商系統進行身分驗證。
     */
    boolean login(String username, String password);

    /**
     * 獲取指定股票和日期範圍的 K 線資料。
     * 
     * @param stockId   股票代碼 (例如："2330")。
     * @param startDate 開始日期 (YYYYMMDD)。
     * @param endDate   結束日期 (YYYYMMDD)。
     * @return 每日價格資訊的列表。
     */
    List<Map<String, Object>> getKBars(String stockId, String startDate, String endDate);

}
