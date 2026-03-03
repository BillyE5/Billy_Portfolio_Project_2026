package com.trading.project.service;

import com.trading.project.strategy.TradingStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 負責執行交易策略的服務。
 */
@Service
public class StrategyExecutionService {

    private static final Logger log = LoggerFactory.getLogger(StrategyExecutionService.class);

    // Key 是策略名稱 ("SWING", "DAY_TRADE")
    private final Map<String, TradingStrategy> strategyRegistry;

    @Autowired
    public StrategyExecutionService(List<TradingStrategy> strategies) {
        this.strategyRegistry = strategies.stream()
                .collect(Collectors.toMap(TradingStrategy::getStrategyName, Function.identity()));
    }

    /**
     * 執行特定策略
     * 
     * @param strategyName 策略名稱 ("SWING", "DAY_TRADE")
     * @param targetDate   日期 (YYYYMMDD)
     */
    public void executeStrategy(String strategyName, String targetDate) {
        TradingStrategy strategy = strategyRegistry.get(strategyName);
        if (strategy == null) {
            log.warn("策略 '{}' 未在註冊表中找到。執行終止。", strategyName);
            return;
        }

        try {
            log.info("---- 開始執行策略: {} ----", strategyName);
            strategy.execute(targetDate);
            log.info("---- 執行策略完成: {} ----", strategyName);
        } catch (Exception e) {
            log.error("執行策略 {} 失敗", strategyName, e);
        }
    }

    /**
     * 執行所有策略
     */
    public void executeAllStrategies(String targetDate) {
        log.info("執行所有 {} 註冊策略，日期: {}", strategyRegistry.size(), targetDate);
        strategyRegistry.keySet().forEach(name -> executeStrategy(name, targetDate));
    }
}
