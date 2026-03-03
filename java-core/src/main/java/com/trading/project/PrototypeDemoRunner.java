package com.trading.project;

import com.trading.project.service.StrategyExecutionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

@Component
public class PrototypeDemoRunner implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(PrototypeDemoRunner.class);
    private final StrategyExecutionService strategyExecutionService;

    @Autowired
    public PrototypeDemoRunner(StrategyExecutionService strategyExecutionService) {
        this.strategyExecutionService = strategyExecutionService;
    }

    @Override
    public void run(String... args) throws Exception {
        log.info("=========================================");
        log.info("  交易原型 Demo  ");
        log.info("=========================================");

        String today = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMMdd"));

        log.info("-> 執行 Swing 策略...");
        strategyExecutionService.executeStrategy("SWING", today);

        log.info("=========================================");
        log.info("  Demo 完成  ");
        log.info("=========================================");
    }
}
