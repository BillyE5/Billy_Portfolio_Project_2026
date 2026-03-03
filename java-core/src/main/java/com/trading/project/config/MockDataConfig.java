package com.trading.project.config;

import com.trading.project.core.DatabaseHandler;
import com.trading.project.core.TradingClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * 提供介面的模擬 (Mock) 實作。
 * 讓雛型可在沒有連接真實資料庫或富邦 API 的情況下執行並輸出日誌。
 */
@Configuration
public class MockDataConfig {

    private static final Logger log = LoggerFactory.getLogger(MockDataConfig.class);

    @Bean
    public TradingClient tradingClient() {
        return new TradingClient() {
            @Override
            public boolean login(String username, String password) {
                log.info("[模擬富邦 API] 登入成功。");
                return true;
            }

            @Override
            public List<Map<String, Object>> getKBars(String stockId, String startDate, String endDate) {
                log.info("[模擬富邦 API] 已獲取 {} 的 K 線資料", stockId);
                return Collections.emptyList();
            }
        };
    }

    @Bean
    public DatabaseHandler databaseHandler() {
        return new DatabaseHandler() {
            @Override
            public List<String> getCurrentInventory() {
                log.info("[模擬 DB] 正在獲取當前庫存...");
                return List.of("2330", "2881");
            }

            @Override
            public void saveTradeRecord(String strategyName, String stockId, String action, double price) {
                log.info("[模擬 DB] 已儲存交易紀錄: {} | {} | {}", strategyName, stockId, action);
            }

            @Override
            public List<Double> getHistoricalClosingPrices(String stockId, int days) {
                log.info("[模擬 DB] 正在獲取 {} {} 天的歷史資料", stockId, days);
                return List.of(100.0, 101.5, 102.0, 99.0, 105.0);
            }

            @Override
            public void updateDailyKbars() {
                log.info("[模擬 DB] 正在執行更新 K 棒作業 (upd_daily_kbars.py)... 成功。");
            }

            @Override
            public void backupDatabase(String backupPrefix) {
                log.info("[模擬 DB] 資料庫備份完成: Backup Prefix = {}", backupPrefix);
            }
        };
    }
}
