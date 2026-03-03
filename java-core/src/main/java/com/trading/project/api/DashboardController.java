package com.trading.project.api;

import com.trading.project.core.DatabaseHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 儀表板 (ST_tracker 及 Streamlit UI)。
 */
@RestController
@RequestMapping("/api/dashboard")
public class DashboardController {

    private static final Logger log = LoggerFactory.getLogger(DashboardController.class);
    private final DatabaseHandler databaseHandler;

    @Autowired
    public DashboardController(DatabaseHandler databaseHandler) {
        this.databaseHandler = databaseHandler;
    }

    /**
     * 獲取波段交易監控資料。
     */
    @GetMapping("/swing_monitor")
    public Map<String, Object> getSwingData() {
        log.info("Streamlit 前端請求了波段交易監控資料");

        List<String> inventory = databaseHandler.getCurrentInventory();

        Map<String, Object> response = new HashMap<>();
        response.put("status", "success");
        response.put("active_holdings", inventory);
        // 模擬波段策略選出的最新清單 (待修改)
        response.put("new_swing_signals", List.of("2330", "2881", "3008"));

        return response;
    }
}
