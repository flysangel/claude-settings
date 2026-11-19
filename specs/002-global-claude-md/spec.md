# Feature Specification: 全域 CLAUDE.md

**Feature Branch**: `002-global-claude-md`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "一份所有專案共用的全域 CLAUDE.md，沿用維護者目前生效的溝通、Git、規格驅動開發三段偏好，並把規格驅動開發一段改成本專案的 6 個 SDD skill 與流程。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 每個專案都依維護者的溝通與 Git 偏好運作 (Priority: P1)

維護者在任何專案開啟 Claude Code，不必重複交代，Claude 就以繁體中文回覆、以互動式選項提問，
並依維護者的 Git 習慣提交異動。

**Why this priority**: 這是全域 CLAUDE.md 存在的主要理由：把每次都要重講的偏好變成預設行為。

**Independent Test**: 安裝後在一個沒有專案層級設定的專案進行一段對話並要求修改檔案，
逐條對照每條規則的預期行為。

**Acceptance Scenarios**:

1. **Given** 已安裝全域 CLAUDE.md，**When** 維護者以英文提問，
   **Then** 回覆是繁體中文，指令、程式碼識別字與專有名詞保留原文。
2. **Given** 已安裝，**When** Claude 需要維護者做決定，
   **Then** 以互動式提問工具呈現選項並標出建議的選項，而不是純文字提問。
3. **Given** 已安裝，**When** 某個 skill 要求以文字或表格提問，
   **Then** 仍改用互動式提問工具；只有該工具不能用時才用文字。
4. **Given** 已安裝且目前在 `main` 分支，**When** Claude 完成一項異動，
   **Then** 它先開分支再 commit，回合結束時改過的檔案沒有未提交的內容，且 `main` 沒有新增的 commit。
5. **Given** 已安裝，**When** Claude 完成 commit 而維護者沒有要求 push，**Then** 遠端沒有變化。

---

### User Story 2 - 新功能自動導向本專案的 SDD 流程 (Priority: P2)

維護者提出新功能時，Claude 依全域 CLAUDE.md 的指引，引導到正確的 SDD skill，
而不是直接動手實作或手動建立 Spec Kit 的檔案。

**Why this priority**: 讓 6 個 SDD skill 在各專案被一致地使用；它依賴這些 skill 已經存在，所以排在溝通與 Git 之後。

**Independent Test**: 在各種專案狀態下提出新功能需求，確認 Claude 建議的 skill 與下表一致。

**Acceptance Scenarios**:

1. **Given** 專案沒有 `.specify/`，**When** 維護者要求開發新功能，
   **Then** Claude 請維護者執行 `/sdd-init`，不手動建立 Spec Kit 的檔案。
2. **Given** 全新專案或有新需求，**When** 需求或方向未定，
   **Then** Claude 使用 `sdd-grill`，一次只問一題並附上建議。
3. **Given** 維護者要從舊專案重生，**When** 討論如何開始，
   **Then** Claude 指引在舊專案使用 `sdd-export`、在新專案使用 `sdd-rebuild`。
4. **Given** spec 已確認，**When** 維護者要開始實作，
   **Then** Claude 說明由維護者在主 session 輸入 `/sdd-drive`，交給子 session 實作。
5. **Given** 維護者只要求修正錯字這類不改變行為的小改動，**When** Claude 處理該請求，
   **Then** 直接修改，不要求走 Spec Kit 流程。
6. **Given** Spec Kit 有新版，**When** 維護者詢問如何更新，**Then** Claude 指引使用 `/sdd-update`。

### Edge Cases

- 專案自己的 CLAUDE.md 與全域偏好衝突時：依 Claude Code 既有的優先順序處理，本文件不另訂規則。
- 文件提到的 skill 在某台機器上尚未安裝（例如只複製了 CLAUDE.md）：Claude 回報該 skill 不存在，
  不自行模擬它的流程。
- 互動式提問工具在當下的環境不能用：改用文字提問，仍然一次呈現選項與建議。
- 專案不是 git repository：Git 一段的規則不適用，Claude 不因此自行初始化 repository。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 專案 MUST 提供一份全域 CLAUDE.md，由部署工具安裝為 `~/.claude/CLAUDE.md`，對所有專案生效。
- **FR-002**: 文件 MUST 包含「溝通」一段：以繁體中文回覆，指令、程式碼識別字與專有名詞保留原文；
  使用者以英文提問時仍以繁體中文回覆。
- **FR-003**: 「溝通」一段 MUST 規定需要維護者做決定時使用互動式提問工具 AskUserQuestion，
  每個待決定事項以選項呈現並標出建議的選項；skill 要求用文字或表格提問時同樣改用該工具，
  只有工具不能用時才用文字。
- **FR-004**: 文件 MUST 包含「Git」一段：每完成一項異動就 commit，不等要求；不直接 commit 到 `main`，
  在 `main` 上時先開分支；只在明確要求時才 push。
- **FR-005**: 文件 MUST 包含「規格驅動開發」一段：新功能以 Spec Kit 進行，不改變行為的小改動除外。
- **FR-006**: 「規格驅動開發」一段 MUST 以本專案的 6 個 skill 描述流程：沒有 `.specify/` 時請維護者執行
  `/sdd-init`；全新專案或新需求用 `sdd-grill`；重生時舊專案用 `sdd-export`、新專案用 `sdd-rebuild`；
  spec 確認後由維護者在主 session 輸入 `/sdd-drive`；Spec Kit 有新版時用 `/sdd-update`。
- **FR-007**: 文件 MUST NOT 提到本專案不提供的 skill（例如 `sdd-derive`）。
- **FR-008**: 每條規則 MUST 附上一句可觀察的預期行為，讓維護者能判斷規則是否被遵守。
- **FR-009**: 文件 MUST NOT 包含機密、憑證、機器專屬路徑與個人信箱。
- **FR-010**: 文件 MUST 只描述維護者個人的偏好，MUST NOT 為其他使用者提供可調選項或替代設定。

### Key Entities

- **全域 CLAUDE.md**: 對所有專案生效的偏好文件，分為溝通、Git、規格驅動開發三段。
- **規則**: 一條偏好，由要求的行為與一句可觀察的預期行為組成。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 文件中 100% 的規則都附有可觀察的預期行為。
- **SC-002**: 文件引用的每一個 skill 名稱都對應到本專案實際提供的 skill，不存在的引用數量為 0。
- **SC-003**: 安裝後，維護者在新專案的第一次對話不需要重新交代語言、提問方式與 Git 習慣。
- **SC-004**: 對照 User Story 1 與 2 的驗收情境逐條檢查，Claude 的行為 100% 符合。
- **SC-005**: 文件在 Windows 與 Linux 安裝後內容完全相同。

## Assumptions

- 全域 CLAUDE.md 本身以繁體中文撰寫；它是偏好文件，不是 skill，不適用「skill 以英文撰寫」的規定。
- 安裝、更新與移除由 001 部署工具負責，本功能只定義文件內容。
- 6 個 SDD skill 的行為由 003 至 008 各自的 spec 定義；本文件只引用名稱與使用時機。
- 自動測試能驗證的範圍（例如三段都存在、引用的 skill 名稱都存在、沒有機密與個人信箱）由 plan 決定；
  Claude 是否實際遵守規則屬於對話行為，以驗收情境人工確認。
- 內容沿用維護者目前生效的偏好，不新增其他規則。
