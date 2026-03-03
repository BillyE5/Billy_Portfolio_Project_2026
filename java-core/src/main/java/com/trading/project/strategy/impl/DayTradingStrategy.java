package com.trading.project.strategy.impl;

import com.trading.project.core.DatabaseHandler;
import com.trading.project.core.TradingClient;
import com.trading.project.strategy.TradingStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * 未來當沖策略的預留佔位類別。
 */
@Component
public class DayTradingStrategy implements TradingStrategy {

    private static final Logger log = LoggerFactory.getLogger(DayTradingStrategy.class);
    private static final String STRATEGY_NAME = "DAY_TRADE";

    private final TradingClient tradingClient;
    private final DatabaseHandler databaseHandler;

    @Autowired
    public DayTradingStrategy(TradingClient tradingClient, DatabaseHandler databaseHandler) {
        this.tradingClient = tradingClient;
        this.databaseHandler = databaseHandler;
    }

    @Override
    public String getStrategyName() {
        return STRATEGY_NAME;
    }

    @Override
    public void execute(String targetDate) {
        log.info("開始執行 {} 策略，日期: {}", STRATEGY_NAME, targetDate);
        // 當沖邏輯將會放在這裡：
        // - 快速移動平均線
        // - 波動率檢查
        // - 確保所有部位在收盤前平倉
        log.info("{} 策略邏輯尚未實作。", STRATEGY_NAME);
    }
}
