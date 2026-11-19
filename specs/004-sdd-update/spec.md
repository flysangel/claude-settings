# Feature Specification: sdd-update 更新 Spec Kit

**Feature Branch**: `004-sdd-update`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "以 /sdd-update 把專案內的 Spec Kit 更新到最新穩定版；沒改過的檔案更新，改過的保留並附新版供比對，constitution 與 specs/ 永遠不動。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 把專案的 Spec Kit 更新到最新版 (Priority: P1)

Spec Kit 發布新版後，維護者在已導入的專案輸入 `/sdd-update`，專案的 Spec Kit 就更新到最新穩定版，
並得知版本的變化與哪些檔案被更新。

**Why this priority**: 這是本功能的核心價值：讓各專案跟上 Spec Kit，而不必手動比對與複製檔案。

**Independent Test**: 以較舊的版本導入一個專案，不修改任何檔案後執行更新，
確認所有 Spec Kit 檔案都變成新版，且回報的版本變化正確。

**Acceptance Scenarios**:

1. **Given** 專案的 Spec Kit 版本較舊且檔案未被修改，**When** 執行 `/sdd-update`，
   **Then** Spec Kit 的檔案更新為當下最新的穩定版（不含預覽版），並回報「從哪一版變成哪一版」與更新的檔案。
2. **Given** 專案已是最新穩定版，**When** 執行 `/sdd-update`，
   **Then** 不產生任何檔案異動，並回報已是最新版。
3. **Given** 新版新增了檔案或不再提供某些檔案，**When** 執行 `/sdd-update`，
   **Then** 新檔案被建立；不再提供且未被修改的檔案被移除，並在回報中列出。

---

### User Story 2 - 保留維護者的修改與專案內容 (Priority: P1)

維護者改過某些 Spec Kit 檔案（例如調整過範本），並且已經寫好 constitution 與多份 spec。
更新時這些內容都不會被覆蓋，維護者也能看到新版長什麼樣子以便自行合併。

**Why this priority**: 更新若會覆蓋 constitution、spec 或手動修改，維護者就不敢執行它。

**Independent Test**: 導入後寫入 constitution、新增一份 spec、修改一個範本，再執行更新，
確認這三者內容不變，且被修改的範本附有新版內容可比對。

**Acceptance Scenarios**:

1. **Given** 某個 Spec Kit 檔案的內容與導入時不同，**When** 執行 `/sdd-update`，
   **Then** 該檔案保留不動並被列出，同時提供它的新版內容供比對；其餘未修改的檔案照常更新。
2. **Given** 專案已有 constitution 與 `specs/` 內的文件，**When** 執行 `/sdd-update`，
   **Then** 這些專案內容完全不變。
3. **Given** 上一次更新留下了被保留的檔案，**When** 維護者自行合併後再次執行 `/sdd-update`，
   **Then** 不會重複列出已與新版一致的檔案。

---

### User Story 3 - 更新後兩個平台仍可直接使用 (Priority: P2)

維護者在其中一個平台更新並提交後，另一個平台取得更新，不需要再做一次更新就能繼續 Spec Kit 流程。

**Why this priority**: 維持 sdd-init 已建立的跨平台保證；更新不能破壞它。

**Independent Test**: 在 Linux 更新並提交，於 Windows 取得後直接執行 Spec Kit 流程，反向亦同。

**Acceptance Scenarios**:

1. **Given** 在任一平台完成更新並提交，**When** 在另一平台取得後執行 Spec Kit 流程，
   **Then** 流程正常完成，不需要再次更新或導入。
2. **Given** 相同狀態的專案，**When** 分別在兩個平台執行 `/sdd-update`，
   **Then** 更新、保留與列出的檔案完全相同。

### Edge Cases

- 專案沒有導入 Spec Kit，或沒有導入紀錄：停止並請維護者先執行 `/sdd-init`，不建立任何檔案。
- 專案的 Spec Kit 不是由 sdd-init 導入：無法判斷哪些檔案未被修改，一律視為被修改，保留並列出。
- 無法取得最新版本或缺少必要工具：停止並說明原因，不更動任何檔案。
- 更新中途失敗：回報失敗的步驟；再次執行時能從一致的狀態完成，不遺失被保留的檔案。
- 專案的版本比最新穩定版還新（例如曾手動安裝預覽版）：不降版，回報目前的狀況。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 維護者 MUST 能以 `/sdd-update` 更新目前專案的 Spec Kit。
- **FR-002**: 更新的目標 MUST 是執行當下最新的穩定版，MUST NOT 是預覽版。
- **FR-003**: 執行後 MUST 回報版本變化（原版本與新版本）、更新的檔案、新建立的檔案、移除的檔案與保留的檔案。
- **FR-004**: 內容與導入（或上次更新）時相同的 Spec Kit 檔案 MUST 更新為新版。
- **FR-005**: 內容與導入（或上次更新）時不同的 Spec Kit 檔案 MUST 保留不動並逐一列出，
  且 MUST 提供其新版內容供維護者比對。
- **FR-006**: constitution、`specs/` 與其他專案內容 MUST NOT 被更動。
- **FR-007**: 新版的 Spec Kit 檔案 MUST 由 Spec Kit 官方工具產生；本 skill MUST NOT 手寫或修改其內容。
- **FR-008**: 已是最新穩定版時 MUST NOT 產生任何檔案異動。
- **FR-009**: 更新完成後 MUST 更新導入紀錄，使下一次更新與移除能正確判斷哪些檔案未被修改。
- **FR-010**: 更新後的專案 MUST 維持在 Windows 與 Linux 都不需重新導入即可執行 Spec Kit 流程。
- **FR-011**: 專案未導入 Spec Kit、缺少必要工具或無法取得版本時，MUST 停止並說明原因與處理方式，
  MUST NOT 更動任何檔案。
- **FR-012**: 更新在 Windows 與 Linux MUST 有相同的行為與相同的回報內容。
- **FR-013**: 本 skill MUST 以英文撰寫，其資料夾 MUST 包含一份繁體中文的 README 簡述。

### Key Entities

- **導入紀錄**: 由 sdd-init 建立、本功能更新；記錄 Spec Kit 檔案清單、各檔案的內容識別資訊與目前版本。
- **保留的檔案**: 因內容被修改而未更新的 Spec Kit 檔案，附有對應的新版內容。
- **專案內容**: constitution、`specs/` 與維護者的其他檔案，永遠不在更新範圍內。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 維護者以一個指令完成更新，過程不超過 2 分鐘，不需要手動比對未修改的檔案。
- **SC-002**: 更新後，constitution 與 `specs/` 內被更動的檔案數量為 0。
- **SC-003**: 更新後，維護者修改過的 Spec Kit 檔案被覆蓋的數量為 0，且每一個都附有新版內容可比對。
- **SC-004**: 未被修改的 Spec Kit 檔案 100% 與新版一致。
- **SC-005**: 已是最新版時連續執行 5 次，檔案異動數量為 0。
- **SC-006**: 在一個平台更新後，另一個平台不做額外步驟即可完成一次 Spec Kit 流程，兩個方向都成立。

## Assumptions

- 新版內容以何種形式提供給維護者比對，以及是否入庫，由 plan 決定。
- 導入紀錄的格式沿用 003 sdd-init 的設計。
- 維護者指定的限制：產出只有 skill 文件或 script；Python script 一律用 uv 執行。
- 不提供指定版本或降版的選項；一律更新到最新穩定版。
- 本 skill 由維護者手動以 `/sdd-update` 執行。
- 更新 `~/.claude` 內的 skill 與全域 CLAUDE.md 屬於 001 部署工具，不在本功能範圍。
- 依 constitution，本功能 MUST 有自動測試，並在 Windows 與 Linux 的 CI 上都通過才能合併。
