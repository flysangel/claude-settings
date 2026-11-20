# Research: 全域 CLAUDE.md

## R1 內容來源

- **Decision**: 以維護者目前生效的 `~/.claude/CLAUDE.md` 為底稿，「溝通」與「Git」兩段的規則與預期原樣沿用，
  只改寫「規格驅動開發」一段。
- **Rationale**: 維護者已確認沿用這三段偏好，不新增其他規則。這兩段沒有引用任何 skill，不需要更動。
- **Alternatives considered**: 重新撰寫全部內容（維護者已否決從零討論）。

## R2 規格驅動開發一段的寫法

- **Decision**: 開頭一句說明新功能走 Spec Kit、小改動除外，接著依「使用時機」列出規則，每條附預期：

  | 時機 | 指引 |
  |---|---|
  | 專案沒有 `.specify/` | 請維護者執行 `/sdd-init`，不手動建立 Spec Kit 的檔案 |
  | 全新專案、新需求或方向未定 | 使用 `sdd-grill`，一次只問一題並附建議 |
  | 從舊專案重生 | 舊專案用 `/sdd-export`，新專案用 `/sdd-rebuild` |
  | spec 已確認，要開始實作 | 由維護者在主 session 輸入 `/sdd-drive`；Claude 不自行開始實作 |
  | Spec Kit 有新版 | 使用 `/sdd-update` |

- **Rationale**: 對應 spec 的 FR-006 與 User Story 2 的六個驗收情境。以時機組織，Claude 才能從當下的狀況對應到該用的 skill。
  `sdd-grill` 不加斜線，因為 Claude 可以在方向未定時主動使用它；其餘的由維護者手動執行，所以寫成指令。
- **Alternatives considered**: 把完整的流程圖放進文件（每個 session 都會載入，過長；流程細節屬於各 skill 與 README）。

## R3 引用尚不存在的 skill

- **Decision**: 文件一次寫齊 6 個 skill 的名稱。測試以固定清單檢查「引用的名稱都在本專案規劃的 6 個之內」；
  另有一個測試檢查「引用的 skill 資料夾確實存在於 `home/skills/`」，在 6 個資料夾到齊之前自動跳過並列出缺少的項目。
- **Rationale**: SC-002 要求引用的 skill 都實際存在，但 003 至 008 還沒實作。分兩步可以現在就擋住打錯或過時的名稱
  （例如 `sdd-derive`），又不必等到 008 才能合併；6 個到齊後第二個測試自動生效，不需要再改。
  在那之前文件會提到還沒安裝的 skill，這是 spec 邊界情況已涵蓋的狀態：Claude 回報 skill 不存在，不自行模擬。
- **Alternatives considered**: 每完成一個 skill 才加一條規則（文件要改六次，且中間狀態的流程不完整）；
  現在就要求資料夾存在（002 無法在 003 至 008 之前合併，違反施工順序）。

## R4 自動測試的範圍

- **Decision**: 結構測試涵蓋：三個段落標題存在且順序固定；每條規則（頂層清單項目）緊接一行以「預期：」開頭的說明；
  引用的 `sdd-*` 名稱都在清單內且不含 `sdd-derive`；不含電子信箱、家目錄的絕對路徑與 Windows 磁碟路徑；
  檔案為 UTF-8、換行為 LF、結尾有換行。行為面以 quickstart 的情境人工驗收。
- **Rationale**: 這是 spec Assumptions 留給 plan 的決定。結構可以機械檢查；Claude 的實際行為無法在 CI 穩定重現。
- **Alternatives considered**: 在 CI 啟動 Claude Code 驗證行為（需要憑證、有費用、結果不穩定）。
