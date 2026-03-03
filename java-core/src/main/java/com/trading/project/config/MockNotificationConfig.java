package com.trading.project.config;

import com.trading.project.core.NotificationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.File;

/**
 * 提供通知服務的模擬 (Mock) 實作。
 */
@Configuration
public class MockNotificationConfig {

    private static final Logger log = LoggerFactory.getLogger(MockNotificationConfig.class);

    @Bean
    public NotificationService notificationService() {
        return new NotificationService() {
            @Override
            public void sendMessage(String message) {
                log.info("[模擬 TG BOT] 已發送訊息: {}", message);
            }

            @Override
            public void sendReportAsImage(File pdfReport, String caption) {
                log.info("[模擬 TG BOT] 正在將 PDF ({}) 轉為圖片...", pdfReport.getName());
                log.info("[模擬 TG BOT] 已發送圖片報表: {}", caption);
            }
        };
    }
}
