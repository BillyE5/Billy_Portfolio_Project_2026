package com.trading.project.strategy.impl;

import com.trading.project.core.DatabaseHandler;
import com.trading.project.core.TradingClient;
import com.trading.project.strategy.TradingStrategy;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * 波段交易策略
 * 對應 ST_PRocket.py
 */
@Component
public class SwingTradingStrategy implements TradingStrategy {

    private static final Logger log = LoggerFactory.getLogger(SwingTradingStrategy.class);
    private static final String STRATEGY_NAME = "SWING";

    private final TradingClient tradingClient;
    private final DatabaseHandler databaseHandler;

    @Autowired
    public SwingTradingStrategy(TradingClient tradingClient, DatabaseHandler databaseHandler) {
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

        // 1. 對應 ST_PRocket.py：掃描市場尋找新的買進訊號 (拿大單 CSV + 排行榜清單)
        log.info("正在根據大單 CSV 與排行榜掃描新的波段突破買進訊號...");
        scanForBuySignals(targetDate);

        log.info("{} 策略執行完畢。", STRATEGY_NAME);
    }

    private void scanForBuySignals(String date) {
        log.info("--- 開始執行波段突破選股 (ST_PRocket) ---");

        // 1. 模擬: 從大單 CSV 讀取股票清單 (約 50 檔)
        List<String> largeOrderList = getMockLargeOrderList();
        log.info("從大單 CSV 成功讀取 {} 檔股票", largeOrderList.size());

        // 2. 模擬: 從排行榜 API 取得近期強勢股清單 (約 30 檔)
        List<String> rankingList = getMockRankingList();
        log.info("從強勢排行榜 API 取得 {} 檔股票", rankingList.size());

        // 3. 將兩個清單合併並去重
        List<String> combinedList = new java.util.ArrayList<>(largeOrderList);
        for (String stock : rankingList) {
            if (!combinedList.contains(stock)) {
                combinedList.add(stock);
            }
        }
        log.info("合併去重後，本期母體共 {} 檔潛在標的", combinedList.size());

        // 4. 針對每檔股票執行策略過濾
        List<String> finalBuySignals = new java.util.ArrayList<>();

        for (String stockId : combinedList) {
            boolean isPassingStrategy = evaluateSwingStrategy(stockId);
            if (isPassingStrategy) {
                finalBuySignals.add(stockId);
                // 儲存訊號到資料庫，狀態預設為: TRACKING 或 VIRTUAL_OBSERVE
                databaseHandler.saveTradeRecord(STRATEGY_NAME, stockId, "BUY_SIGNAL", 0.0);
                log.info("🎯 發現波段突破買進訊號: {}", stockId);
            }
        }

        log.info("選股完成！本日共選出 {} 檔波段標的。", finalBuySignals.size());

        // 5. 模擬產出 PDF 報表並發送 TG
        // notificationService.sendReportAsImage(report, "本日波段選股報告");
    }

    /**
     * 模擬策略核心邏輯: 判斷各種技術指標 (對應 ST_PRocket 核心條件)
     */
    private boolean evaluateSwingStrategy(String stockId) {

        // 寫入自己的策略 比如KD黃金交叉等

        // 模擬KD黃金交叉
        boolean isKDGoldenCross = false;

        return isKDGoldenCross;
    }

    // --- 輔助模擬資料產生方法 ---
    private List<String> getMockLargeOrderList() {
        return java.util.Arrays.asList("2330", "2317", "2454", "3231", "2382");
    }

    private List<String> getMockRankingList() {
        return java.util.Arrays.asList("2330", "2317", "2454", "3231", "2382");
    }
}
