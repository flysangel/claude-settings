# Feature Specification: sdd-init 導入 Spec Kit

**Feature Branch**: `003-sdd-init`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "以 /sdd-init 在目前專案導入最新穩定版 Spec Kit，不覆蓋既有檔案，可移除；任一平台導入的專案在另一平台不需重新導入就能使用。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 在專案導入 Spec Kit (Priority: P1)

維護者在一個還沒有 Spec Kit 的專案輸入 `/sdd-init`，專案就具備執行 Spec Kit 流程所需的一切，
並得知安裝的版本、建立了哪些檔案與下一步該做什麼。

**Why this priority**: 這是每個專案 SDD 流程的第一步；sdd-grill、sdd-rebuild、sdd-drive 都以它為前提。

**Independent Test**: 在空目錄與既有專案各執行一次，確認 Spec Kit 的檔案齊全、版本是當下最新穩定版，
且後續的 Spec Kit 指令可以執行。

**Acceptance Scenarios**:

1. **Given** 專案沒有 Spec Kit，**When** 執行 `/sdd-init`，
   **Then** 導入當下最新的穩定版（不含預覽版），並回報版本、建立的檔案與下一步建議。
2. **Given** 專案已有部分同名檔案，**When** 執行 `/sdd-init`，
   **Then** 既有檔案保持原樣，被略過的檔案逐一列出，其餘缺少的檔案照常建立。
3. **Given** 專案已完整導入，**When** 再次執行 `/sdd-init`，
   **Then** 不產生任何檔案異動，並回報已導入的版本。
4. **Given** 缺少必要工具，或無法取得最新版本，**When** 執行 `/sdd-init`，
   **Then** 停止並說明原因與處理方式，不建立任何檔案，也不改用其他方式安裝。

---

### User Story 2 - 同一專案在 Windows 與 Linux 都能直接使用 (Priority: P1)

維護者在其中一個平台導入 Spec Kit 並提交，之後在另一個平台 clone 同一個專案，
不需要重新導入就能執行 Spec Kit 流程。

**Why this priority**: spec 跟著 repo 走；若 Spec Kit 只能在導入時的平台運作，「兩個平台完全對等」就不成立。

**Independent Test**: 在 Linux 導入並提交，於 Windows clone 後直接執行一次 Spec Kit 流程（反向亦同），
確認不需要任何額外的導入步驟。

**Acceptance Scenarios**:

1. **Given** 在 Linux 導入並提交的專案，**When** 在 Windows clone 後執行 Spec Kit 流程，
   **Then** 流程正常完成，不需要重新導入或手動補檔。
2. **Given** 在 Windows 導入並提交的專案，**When** 在 Linux clone 後執行 Spec Kit 流程，
   **Then** 流程正常完成，不需要重新導入或手動補檔。
3. **Given** 相同的空專案，**When** 分別在兩個平台執行 `/sdd-init`，
   **Then** 兩邊建立的檔案集合相同。

---

### User Story 3 - 移除 Spec Kit (Priority: P3)

維護者決定某個專案不再使用 Spec Kit 時，可以把它移除，而不影響自己寫的內容。

**Why this priority**: 讓導入是可逆的；使用頻率遠低於導入。

**Independent Test**: 導入後修改其中一個檔案並新增 spec，再執行移除，
確認只有未被修改的導入檔案被刪除。

**Acceptance Scenarios**:

1. **Given** 已導入且檔案未被修改，**When** 執行移除，
   **Then** 導入時建立的檔案全部刪除，專案其他內容不變。
2. **Given** 已導入且部分檔案被修改過（例如已寫好的 constitution），**When** 執行移除，
   **Then** 被修改的檔案保留並逐一列出，其餘導入的檔案刪除；`specs/` 內的內容不受影響。
3. **Given** 專案沒有導入紀錄，**When** 執行移除，**Then** 不刪除任何檔案，並說明沒有可移除的內容。

### Edge Cases

- 專案不是 git repository：仍可導入，並說明是否建立了 repository 及是否有未提交的內容。
- 導入中途失敗：回報失敗的步驟；再次執行時能補齊缺少的檔案，不重複建立、不覆蓋已存在的檔案。
- 專案先前以其他方式（非本 skill）導入過 Spec Kit：既有檔案一律視為不是自己建立的，略過並列出，
  移除時也不會刪除它們。
- 導入紀錄遺失：移除時無法證明檔案是自己建立的，不刪除任何檔案並說明原因。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 維護者 MUST 能以 `/sdd-init` 在目前專案導入 Spec Kit。
- **FR-002**: 導入的版本 MUST 是執行當下最新的穩定版，MUST NOT 是預覽版。
- **FR-003**: Spec Kit 的檔案 MUST 由 Spec Kit 官方工具產生；本 skill MUST NOT 手寫或修改這些檔案的內容。
- **FR-004**: 導入 MUST NOT 覆蓋既有檔案；被略過的檔案 MUST 逐一列出。
- **FR-005**: 導入完成後 MUST 回報安裝的版本、建立的檔案、略過的檔案，以及下一步建議。
- **FR-006**: 在任一平台導入並提交的專案，在另一平台取得後 MUST 不需重新導入就能執行 Spec Kit 流程。
- **FR-007**: 本 skill MUST 記錄自己建立了哪些檔案及其建立時的內容識別資訊，供移除與更新判斷。
- **FR-008**: 維護者 MUST 能移除 Spec Kit；移除 MUST 只刪除本 skill 建立且之後未被修改的檔案，
  被修改過的檔案 MUST 保留並列出。
- **FR-009**: 移除 MUST NOT 更動 `specs/` 與專案的其他內容。
- **FR-010**: 缺少必要工具或無法取得版本時，MUST 停止並說明原因與處理方式，
  MUST NOT 建立任何檔案，MUST NOT 自行重試或改用其他方式安裝。
- **FR-011**: 重複執行導入 MUST NOT 產生額外的異動。
- **FR-012**: 導入與移除在 Windows 與 Linux MUST 有相同的行為與相同的回報內容。
- **FR-013**: 本 skill MUST 以英文撰寫，其資料夾 MUST 包含一份繁體中文的 README 簡述。

### Key Entities

- **導入紀錄**: 某個專案中由本 skill 建立的檔案清單、各檔案建立時的內容識別資訊，以及導入的 Spec Kit 版本。
- **Spec Kit 檔案**: 官方工具產生的設定、範本、腳本與 `speckit-*` skill。
- **專案內容**: 維護者自己撰寫的 constitution、`specs/` 與其他檔案，不屬於本 skill。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 維護者以一個指令完成導入，不需要其他手動步驟，過程不超過 2 分鐘。
- **SC-002**: 導入後，專案中既有檔案被覆蓋的數量為 0。
- **SC-003**: 在一個平台導入的專案，於另一個平台不做任何額外步驟即可完成一次 Spec Kit 流程，兩個方向都成立。
- **SC-004**: 導入後立即移除，專案回到與導入前 100% 相同的狀態。
- **SC-005**: 移除時，被維護者修改過的檔案遺失的數量為 0。
- **SC-006**: 失敗時，維護者只讀回報內容就知道原因與下一步，不需要查看其他紀錄。

## Assumptions

- 同一專案如何同時支援兩個平台所需的 Spec Kit 腳本，且不違反「不修改 Spec Kit 檔案」，由 plan 決定。
- 導入紀錄的格式與位置由 plan 決定。
- 維護者指定的限制：產出只有 skill 文件或 script；Python script 一律用 uv 執行。
- 更新已導入的 Spec Kit 屬於 004 sdd-update，不在本功能範圍。
- 本 skill 由維護者手動以 `/sdd-init` 執行，不由 Claude 自行觸發。
- 依 constitution，本功能 MUST 有自動測試，並在 Windows 與 Linux 的 CI 上都通過才能合併。
