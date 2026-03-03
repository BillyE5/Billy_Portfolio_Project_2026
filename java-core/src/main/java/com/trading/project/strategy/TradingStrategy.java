package com.trading.project.strategy;

/**
 * 策略模式介面。
 */
public interface TradingStrategy {

    /**
     * @return 策略的唯一識別名或名稱 (例如："SWING", "DAY_TRADE")
     */
    String getStrategyName();

    /**
     * 執行策略邏輯。
     * 
     * @param targetDate 要執行分析/處理的目標日期 (YYYYMMDD)。
     */
    void execute(String targetDate);
}
