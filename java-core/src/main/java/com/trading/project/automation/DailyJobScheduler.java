package com.trading.project.automation;

import com.trading.project.core.DatabaseHandler;
import com.trading.project.core.NotificationService;
import com.trading.project.service.PerformanceService;
import com.trading.project.service.StrategyExecutionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

@Component
public class DailyJobScheduler {

    private static final Logger log = LoggerFactory.getLogger(DailyJobScheduler.class);

    private final StrategyExecutionService strategyService;
    private final PerformanceService performanceService;
    private final NotificationService notificationService;
    private final DatabaseHandler databaseHandler;
    private final DateTimeFormatter DATE_FORMAT = DateTimeFormatter.ofPattern("yyyyMMdd");

    @Autowired
    public DailyJobScheduler(StrategyExecutionService strategyService, PerformanceService performanceService,
            NotificationService notificationService, DatabaseHandler databaseHandler) {
        this.strategyService = strategyService;
        this.performanceService = performanceService;
        this.notificationService = notificationService;
        this.databaseHandler = databaseHandler;
    }

    /**
     * 13:00 執行波段選股 (對應 run_daily_PRocket.bat)
     * 執行 auto_export_mitake 與 ST_PRocket
     */
    @Scheduled(cron = "0 00 13 * * MON-FRI", zone = "Asia/Taipei")
    public void runDailyPRocket() {
        String today = LocalDate.now().format(DATE_FORMAT);
        log.info("--- [排程] 13:00 觸發波段選股作業 (run_daily_PRocket) 日期: {} ---", today);

        // 執行波段選股策略 (ST_PRocket)
        log.info("執行核心策略: SWING");
        strategyService.executeStrategy("SWING", today);

        notificationService.sendMessage("波段選股 (ST_PRocket) 與匯出作業執行完畢。");
    }

    /**
     * 收盤後 20:00 執行每日維護與績效計算 (對應 daily_job.bat)
     * 執行備份 -> 更新 K 棒 -> 績效計算 -> 完整備份
     */
    @Scheduled(cron = "0 00 20 * * MON-FRI", zone = "Asia/Taipei")
    public void runDailyJob() {
        String today = LocalDate.now().format(DATE_FORMAT);
        log.info("--- [排程] 20:00 觸發盤後批次作業 (daily_job) 日期: {} ---", today);

        log.info("1. 執行計算前資料庫備份...");
        databaseHandler.backupDatabase("before_calc");

        // upd_daily_kbars.py
        log.info("2. 執行收盤 K 棒更新...");
        databaseHandler.updateDailyKbars();

        // pf_tracker.py
        log.info("3. 執行績效追蹤與計算...");
        performanceService.trackDailyPerformance(today);

        log.info("4. 執行計算後完整資料庫備份...");
        databaseHandler.backupDatabase("full_backup_" + today);

        log.info("--- [排程] 20:00 盤後批次作業 (daily_job) 順利完成 ---");
    }
}
