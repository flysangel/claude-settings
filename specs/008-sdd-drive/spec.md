# Feature Specification: sdd-drive 由子 session 依序把每份 spec 做到完成

**Feature Branch**: `008-sdd-drive`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "維護者在主 session 輸入 /sdd-drive，由子 session 全自動依序把每份 spec 跑完 plan、tasks、implement，只在失敗時停止並回報；只需要 Claude Code。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 一個指令把整批 spec 做到完成 (Priority: P1)

維護者已確認 constitution 與 spec，在主 session 輸入 `/sdd-drive`。主 session 開一個子 session，
子 session 依編號一次處理一份 spec，自動完成 plan、tasks 與實作，全部完成後把結果回報到主 session。

**Why this priority**: 這是本功能的核心：spec 確認之後，維護者不必再逐份、逐步驟下指令。

**Independent Test**: 在有 2 份小型 spec 的專案執行，確認兩份都依序完成 plan、tasks 與實作，
主 session 收到完成的回報，且主 session 自己沒有執行這些步驟。

**Acceptance Scenarios**:

1. **Given** 專案有尚未完成的 spec，**When** 維護者在主 session 輸入 `/sdd-drive`，
   **Then** 主 session 開子 session 執行，並告知維護者已開始處理哪些 spec、依什麼順序。
2. **Given** 子 session 執行中，**When** 處理一份 spec，
   **Then** 依序完成 plan、tasks、implement，過程不停下來等維護者核可。
3. **Given** 一份 spec 需要技術選型，**When** 進行 plan，
   **Then** 由 AI 依 constitution 決定，不向維護者提問。
4. **Given** 有多份未完成的 spec，**When** 子 session 執行，
   **Then** 依 spec 編號由小到大一次只處理一份，前一份確認完成後才開始下一份。
5. **Given** 全部 spec 都完成，**When** 子 session 結束，
   **Then** 主 session 向維護者回報每份 spec 的結果。
6. **Given** 子 session 執行中，**When** 檢查主 session 的動作，
   **Then** 主 session 沒有親自產生 plan、tasks 或程式碼，只負責啟動、等待與回報。

---

### User Story 2 - 確認真的完成才往下 (Priority: P1)

一份 spec 被視為完成，必須是它的任務全部做完而且測試通過，而不是子 session 自己宣稱完成。

**Why this priority**: 全自動沒有人工關卡，完成的判定就是唯一的品質閘門；判定不可靠，後面的 spec 會建立在壞掉的基礎上。

**Independent Test**: 安排一份 spec 的實作留下未完成的任務或失敗的測試，
確認它不被判定為完成，後續的 spec 沒有開始。

**Acceptance Scenarios**:

1. **Given** 一份 spec 的實作結束，**When** 判定是否完成，
   **Then** 只有在任務全部完成且測試通過時才判定為完成。
2. **Given** 一份 spec 還有未完成的任務或失敗的測試，**When** 判定，
   **Then** 不判定為完成，也不開始下一份。
3. **Given** 某份 spec 的 plan 或 tasks 只是未填寫的範本，**When** 判定該步驟，
   **Then** 不視為已產生。

---

### User Story 3 - 失敗時停止並回報 (Priority: P1)

某一份 spec 在任何步驟失敗時，整個流程停下來，主 session 告訴維護者是哪一份、哪個步驟、為什麼，
不跳過它去做後面的 spec。

**Why this priority**: 後面的 spec 依賴前面的；跳過失敗的項目會讓錯誤擴散，也讓維護者難以判斷狀態。

**Independent Test**: 安排第 2 份 spec 必定失敗，確認第 1 份完成、第 2 份回報失敗、第 3 份完全沒有開始。

**Acceptance Scenarios**:

1. **Given** 某份 spec 在 plan、tasks 或 implement 失敗，**When** 子 session 偵測到，
   **Then** 停止處理，不開始後續的 spec。
2. **Given** 流程因失敗停止，**When** 主 session 回報，
   **Then** 說明失敗的 spec、步驟與原因，以及已完成與尚未開始的 spec。
3. **Given** 子 session 異常結束而沒有回報，**When** 主 session 發現，
   **Then** 向維護者回報流程中斷，並依檔案的實際狀態說明進度。

---

### User Story 4 - 中斷後接續 (Priority: P2)

流程因失敗、關機或維護者中止而停下。維護者處理完問題後再次輸入 `/sdd-drive`，
流程從未完成的地方繼續，已完成的 spec 不重做。

**Why this priority**: 整批實作耗時長，中斷難免；不能接續就得從頭再來。

**Independent Test**: 在第 2 份 spec 的 tasks 之後中止，再次執行，
確認第 1 份沒有被重做、第 2 份從實作開始。

**Acceptance Scenarios**:

1. **Given** 前一次執行完成了部分 spec，**When** 再次輸入 `/sdd-drive`，
   **Then** 已完成的 spec 不重做，從第一份未完成的 spec 繼續。
2. **Given** 某份 spec 已有 plan 但沒有 tasks，**When** 接續，
   **Then** 從 tasks 開始，不重新產生 plan。
3. **Given** 上一次失敗的 spec，**When** 維護者修正原因後再次執行，
   **Then** 該 spec 從失敗的步驟重試。
4. **Given** 所有 spec 都已完成，**When** 輸入 `/sdd-drive`，
   **Then** 不開子 session，回報沒有待處理的 spec。

### Edge Cases

- 專案未導入 Spec Kit，或沒有任何 spec：回報並說明應先執行 `/sdd-init` 與 `/sdd-grill` 或 `/sdd-rebuild`，不開子 session。
- 前一次的子 session 仍在執行時再次輸入 `/sdd-drive`：不開第二個子 session，回報已有執行中的流程。
- 專案有未提交的變更：先告知維護者，不自行捨棄或覆蓋這些變更。
- spec 編號不連續或有缺號：依實際存在的編號由小到大處理。
- 專案沒有可執行的測試：無法以測試確認完成時，回報這一點並停止，不逕自判定為完成。
- Spec Kit 缺少 plan、tasks 或 implement 的能力：回報可能有不相容的變更並停止。
- 子 session 無法啟動：回報原因，主 session 不改為親自實作。
- 專案不是 git repository：仍可執行，並說明無法依版本紀錄判斷變更。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 維護者 MUST 能在主 session 以 `/sdd-drive` 啟動流程；本 skill MUST 只由維護者手動啟動，
  `sdd-grill` 與 `sdd-rebuild` MUST NOT 自動觸發它。
- **FR-002**: 主 session MUST 開子 session 來執行工作，且 MUST NOT 親自執行 plan、tasks 或 implement。
- **FR-003**: 子 session MUST 依 spec 編號由小到大一次只處理一份。
- **FR-004**: 每份 spec MUST 依序完成 plan、tasks、implement，且 MUST NOT 停下來等待維護者核可。
- **FR-005**: plan 階段的技術選型 MUST 由 AI 依 constitution 決定。
- **FR-006**: plan、tasks、implement MUST 透過 Spec Kit 進行；本 skill MUST NOT 手寫它們的產物。
- **FR-007**: 一份 spec MUST 在任務全部完成且測試通過時才被判定為完成；未填寫的範本 MUST NOT 被視為已產生的 plan 或 tasks。
- **FR-008**: 前一份 spec 判定為完成之前，MUST NOT 開始下一份。
- **FR-009**: 任何步驟失敗時 MUST 停止整個流程，MUST NOT 跳過失敗的 spec 去處理後續的 spec。
- **FR-010**: 流程結束或停止時，主 session MUST 回報每份 spec 的狀態；失敗時 MUST 說明 spec、步驟與原因。
- **FR-011**: 進度 MUST 依專案內檔案的實際狀態判定，使流程能在中斷後接續；已完成的 spec 與步驟 MUST NOT 重做。
- **FR-012**: 同一個專案同時 MUST 只有一個執行中的流程；已有流程執行時 MUST 回報而不重複啟動。
- **FR-013**: 本 skill MUST 只需要 Claude Code 本身即可運作，MUST NOT 要求 Orca 或其他額外工具。
- **FR-014**: 專案未導入 Spec Kit、沒有 spec 或子 session 無法啟動時，MUST 回報原因並停止。
- **FR-015**: 本 skill MUST NOT 捨棄或覆蓋維護者未提交的變更。
- **FR-016**: 本 skill MUST NOT 修改 constitution 與 spec 的需求內容；需求有問題時 MUST 以失敗回報，由維護者處理。
- **FR-017**: 本 skill 在 Windows 與 Linux MUST 有相同的行為。
- **FR-018**: 本 skill MUST 以英文撰寫，其資料夾 MUST 包含一份繁體中文的 README 簡述。

### Key Entities

- **主 session**: 維護者輸入指令的對話；只負責啟動、等待與回報。
- **子 session**: 實際執行 plan、tasks、implement 的對話。
- **spec 狀態**: 每份 spec 目前到哪個步驟（未開始、已有 plan、已有 tasks、實作中、完成、失敗），由檔案的實際狀態推得。
- **回報**: 流程結束或停止時給維護者的結果，包含每份 spec 的狀態與失敗原因。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 從輸入指令到全部 spec 完成，維護者需要輸入的指令數為 1，需要回答的問題數為 0（沒有失敗時）。
- **SC-002**: 被判定為完成的 spec 中，仍有未完成任務或失敗測試的數量為 0。
- **SC-003**: 某份 spec 失敗後，編號在它之後的 spec 被開始處理的數量為 0。
- **SC-004**: 中斷後接續時，已完成的 spec 被重做的數量為 0。
- **SC-005**: 失敗時，維護者只讀主 session 的回報就知道是哪一份、哪個步驟與原因，不需要開啟子 session 的紀錄。
- **SC-006**: 在只安裝了 Claude Code 與本專案 skill 的機器上，流程可以完整執行。
- **SC-007**: 主 session 親自產生的 plan、tasks 與程式碼數量為 0。

## Assumptions

- 開子 session 的機制、主 session 如何得知子 session 的結果，由 plan 決定。
- 全自動代表維護者不會在實作前看到 plan；想限制的技術決定應寫進專案的 constitution。這是維護者已知悉並接受的取捨。
- 「測試通過」以專案自己的測試為準；沒有測試時依 Edge Cases 處理。
- 指定只處理某一份或某個範圍的指令形式未經維護者確認，不在本 spec 的需求內；需要時另行提出。
- 自動測試能涵蓋的範圍（例如狀態判定可測，實際的實作過程難以在 CI 重現）由 plan 決定；
  依 constitution，本功能仍 MUST 有自動測試並在兩個平台的 CI 通過。
- 維護者指定的限制：產出只有 skill 文件或 script；Python script 一律用 uv 執行。
- 產生 spec 屬於 005 sdd-grill 與 007 sdd-rebuild；本功能從已確認的 spec 開始。
