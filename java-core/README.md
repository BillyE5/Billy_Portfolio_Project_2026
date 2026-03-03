# Java 交易架構雛型 (Java Trading Architecture Prototype) ☕🚀

這是我原本基於 Python 的波段交易 (Swing Trading) 自動化系統的企業級 Java 移植版本 (雛型)。
雖然原始系統使用 Python 進行 API 互動和 pandas 處理資料，但建立這個雛型是為了展示在 **Java、Spring Boot、物件導向設計模式 (OOP Design Patterns) 以及整潔架構 (Clean Architecture)** 上的熟練度。

系統具備高度擴充性，旨在展示一個穩健、低耦合的交易後端是如何被架構出來的。

## 🛠️ 展示的核心技術與概念

- **Java 17 & Spring Boot 3**: 運用業界標準的後端微服務框架。
- **控制反轉 (IoC) & 依賴注入 (DI)**: 業務邏輯 (`@Service`) 與實際的富邦 API 實作及資料庫層完全解耦，使系統具備極高的可測試性。
- **策略設計模式 (Strategy Design Pattern)**: 系統的核心使用了策略模式 (`TradingStrategy`)。
  - 若要新增一個演算法（例如：當沖、配對交易），只需要實作 `TradingStrategy` 介面並加上 `@Component` 註解。
  - Spring 會自動將它註冊到 `StrategyExecutionService` (策略註冊表 / 工廠) 中。完全不需要修改核心執行程式碼。
- **自動化排程 (Automated Scheduling)**: 將舊有的 Windows `.bat` 排程邏輯轉移到企業級的 Spring `@Scheduled` 任務 (`DailyJobScheduler`) 中，集中管理盤後分析與報表產生的流程。

## 📂 架構概覽

```text
com.trading.project
├── config/              # Mock Beans (模擬物件)，讓雛型在沒有實際 DB 的情況下也能執行
├── core/                # 介面層，將業務邏輯與基礎設施解耦
│   ├── DatabaseHandler      # 資料庫操作抽象化
│   └── TradingClient        # 券商 API 抽象化 (富邦 API)
├── strategy/            # 可擴充的演算法層
│   ├── TradingStrategy      # 核心介面 (策略模式)
│   └── impl/
│       ├── SwingTradingStrategy # 波段策略: 盤中掃描大單與排行榜尋找買進標的 (對應 ST_PRocket.py)
│       └── DayTradingStrategy   # 未來擴充的預留位置 (當沖)
├── service/             # 服務與調度層
│   ├── StrategyExecutionService # 使用 Map<String, TradingStrategy> 來執行演算法
│   └── PerformanceService       # 盤後結算服務: 追蹤績效、判斷停損/停利及殭屍股淘汰邏輯 (對應 pf_tracker.py & ST_tracking.py)
└── automation/          # 排程自動化層
    └── DailyJobScheduler        # 使用 @Scheduled 的 cron job 來自動化每日交易流程
```

## 🚀 如何執行此展示程式

因為這是一個架構展示雛型，`TradingClient` 與 `DatabaseHandler` 目前是透過 Spring `@Bean` 配置進行資料模擬 (Mock)。

您可以直接透過命令列使用 Maven 來執行應用程式：

```bash
cd java_prototype
mvn spring-boot:run
```

啟動後，`PrototypeDemoRunner` 會自動執行，並透過日誌 (log) 輸出展示依賴注入的運作以及各項策略的執行流程。

## 🏗️ 未來發展藍圖 (Roadmap)
1. **JPA/Hibernate 整合**: 將 `DatabaseHandler` 替換為連接 MySQL 後端的 Spring Data JPA `Repository` 介面。
2. **WebSocket 整合**: 實作 `TradingClient` 介面，使用 Java WebSockets 來串流接收即時的 Tick 資料。
3. **REST API**: 新增 `@RestController` 端點，將績效指標資料提供給 React 或 Angular 前端儀表板使用。
