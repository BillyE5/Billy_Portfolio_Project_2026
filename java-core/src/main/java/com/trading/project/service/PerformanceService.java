package com.trading.project.service;

import com.trading.project.core.DatabaseHandler;
import com.trading.project.core.NotificationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/**
 * 計算績效
 * 對應 pf_tracker.py
 */
@Service
public class PerformanceService {

    private static final Logger log = LoggerFactory.getLogger(PerformanceService.class);
    private final DatabaseHandler databaseHandler;
    private final NotificationService notificationService;

    @Autowired
    public PerformanceService(DatabaseHandler databaseHandler, NotificationService notificationService) {
        this.databaseHandler = databaseHandler;
        this.notificationService = notificationService;
    }

    /**
     * 追蹤投資組合價值的每日變化。
     */
    public void trackDailyPerformance(String date) {
        log.info("執行日期 {} 的績效追蹤作業", date);
        // 1. 獲取目前庫存
        var inventory = databaseHandler.getCurrentInventory();
        log.info("針對 {} 檔股票計算損益並判斷是否觸發賣出條件...", inventory.size());

        // 2. 獲取這些股票的收盤價，計算未實現/已實現損益
        for (String stockId : inventory) {
            checkAndProcessSellSignal(stockId, date);
        }

        // 3. 將每日快照更新至資料庫
        log.info("日期 {} 的績效資料已成功儲存。", date);

        // 4. 產生 PDF 報表並將其轉為圖片傳送至 Telegram Bot
        java.io.File dummyReport = new java.io.File("/reports/daily_performance_" + date + ".pdf");
        notificationService.sendReportAsImage(dummyReport, "今日績效報表出爐");
    }

    private void checkAndProcessSellSignal(String stockId, String date) {
        log.info("開始評估 [{}] 的績效狀態...", stockId);

        // 模擬從資料庫取得當前該筆交易的資訊 (例如: 買進價、當前持股天數、當前報酬率等)
        // 雛型展示，隨機給定一些假資料來模擬
        double currentRoi = Math.random() * 30 - 10; // 隨機產生 -10% 到 20% 的 ROI
        int daysHeld = (int) (Math.random() * 15) + 1; // 隨機產生 1 到 15 天的持有天數

        log.info(" - 股票 {}: 持有天數 T+{}, 當前 ROI = {}%", stockId, daysHeld, String.format("%.2f", currentRoi));

        // 模擬 evaluate_stock_health 檢查是否跌破均線或觸發關鍵出場條件
        boolean isPassingHealth = currentRoi > -5.0; // 隨機條件：ROI < -5% 就視為不及格
        boolean isCriticalDeath = currentRoi < -8.0; // 隨機條件：硬停損

        if (!isPassingHealth) {
            if (isCriticalDeath) {
                // 情境 A: 硬停損 (直接結案) - 對應 pf_tracker 中直接 mark_as_pending_sell
                String deathReason = String.format("🛑 強制止損 (T+%d): 硬停損/強制出場", daysHeld);
                log.info("🛑 [停損] {} 觸發硬停損/強制出場。原因: {}", stockId, deathReason);
                markAsPendingSell(stockId, deathReason);
            } else if (currentRoi > 20.0) {
                // 情境 B: 獲利了結 (Hero Retirement)
                String deathReason = String.format("(T+%d) (%.2f%%) 獲利了結: 跌破趨勢線10MA", daysHeld, currentRoi);
                log.info("💰 [止盈] {} (T+%d) (%.2f%%) 獲利出場。原因: {}", stockId, daysHeld, currentRoi, deathReason);
                markAsPendingSell(stockId, deathReason);
            } else {
                // 情境 C: 普通違規 (轉殭屍或逾期結案)
                if (daysHeld >= 10) {
                    // 如果已經持有超過 10 天 -> 不進殭屍，直接結案！
                    String deathReason;
                    if (currentRoi > 0) {
                        deathReason = String.format("(T+%d) (%.2f%%) 逾期獲利了結: 盤整過久且轉弱，獲利出場。", daysHeld, currentRoi);
                        log.info("💰 [止盈] {} (T+%d) (%.2f%%)。原因: {}", stockId, daysHeld, currentRoi, deathReason);
                    } else {
                        deathReason = String.format("(T+%d) (%.2f%%) 資金效率回收: 盤整逾期且轉弱，換股操作", daysHeld, currentRoi);
                        log.info("💀 [結案] {} (T+%d) (%.2f%%)。原因: {}", stockId, daysHeld, currentRoi, deathReason);
                    }
                    markAsPendingSell(stockId, deathReason);
                } else {
                    // 如果還是年輕人 (T < 10) -> 給機會進殭屍區 (WATCH_LIST)
                    log.info("🧟 [轉殭屍] {} (T+{}) (%.2f%%) 轉入殭屍名單。", stockId, daysHeld, currentRoi);
                    // databaseHandler.updateToWatchlist(stockId, ...);
                }
            }
        } else {
            // 合格，繼續續抱
            log.info("✅ [續抱] {} (T+{}) (%.2f%%) 表現良好。", stockId, daysHeld, currentRoi);
        }
    }

    /**
     * 對應 pf_tracker.py 中的 mark_as_pending_sell 方法
     */
    private void markAsPendingSell(String stockId, String reason) {
        log.info("📝 [{}] 已列入明日開盤賣出名單 (PENDING_SELL)，原因: {}", stockId, reason);
        // databaseHandler.updateSignalStatus(stockId, "PENDING_SELL");
        // databaseHandler.appendNote(stockId, reason);
    }

}
