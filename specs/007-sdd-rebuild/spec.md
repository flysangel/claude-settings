# Feature Specification: sdd-rebuild 在新專案以養分重建

**Feature Branch**: `007-sdd-rebuild`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "在新專案執行 /sdd-rebuild 並指定舊專案，讀取它的養分，逐項保留、修改、合併、捨棄並加入新需求，確認後產生 constitution 與 spec，並留下世代紀錄供下一次重生使用。"

## User Scenarios & Testing *(mandatory)*

本功能是重生循環的後半：006 sdd-export 在舊專案留下養分，本功能在新專案把養分變成新的 constitution 與 spec。

### User Story 1 - 以舊專案的養分原樣重建 (Priority: P1)

維護者在一個已導入 Spec Kit 的新專案輸入 `/sdd-rebuild` 並指定舊專案的路徑。
Claude 讀取養分，呈現將要產生的 constitution 與 spec 摘要，維護者確認後由 Spec Kit 產生文件。

**Why this priority**: 這是最基本的重生：同樣的需求，從乾淨的 spec 重新實作。其他用法都建立在它之上。

**Independent Test**: 以一份含 3 個功能的養分在空的新專案重建並全部保留，
確認產生 1 份 constitution 與 3 份 spec，內容對應養分，沒有帶入 plan、tasks 或程式碼。

**Acceptance Scenarios**:

1. **Given** 新專案已導入 Spec Kit 且舊專案有養分，**When** 以舊專案路徑執行 `/sdd-rebuild`，
   **Then** Claude 讀取養分並呈現摘要：原則、功能清單與相依關係、經驗教訓，以及建議的 spec 順序。
2. **Given** 摘要已呈現，**When** 維護者尚未確認，**Then** 新專案的 constitution 與 spec 沒有任何變化。
3. **Given** 維護者選擇全部保留並確認，**When** Claude 產生文件，
   **Then** constitution 與每個功能各一份 spec 由 Spec Kit 產生，spec 依相依順序重新編號，被依賴的功能排在前面。
4. **Given** 文件已產生，**When** 檢視新專案，
   **Then** 其中沒有來自舊專案的 plan、tasks 與程式碼。
5. **Given** 文件已產生，**When** 流程結束，
   **Then** Claude 列出每份 spec 的位置與順序，說明下一步是由維護者輸入 `/sdd-drive`，然後停止，不自動開始實作。

---

### User Story 2 - 逐項調整並加入新需求 (Priority: P1)

舊專案的需求已經零散或過時。維護者在重建時逐項決定保留、修改、合併或捨棄，並加入這一代的新需求；
Claude 也依經驗教訓提出調整建議。

**Why this priority**: 重生不只是複製；讓維護者在這個時間點整理需求，是「每一代比上一代好」的關鍵。

**Independent Test**: 以含 4 個功能的養分重建，捨棄 1 個、合併 2 個、修改 1 個並新增 1 個，
確認產生的 spec 數量與內容符合這些決定。

**Acceptance Scenarios**:

1. **Given** 養分已讀取，**When** 維護者選擇逐項檢視，
   **Then** 每個原則與功能都可以被保留、修改、合併或捨棄，且一次只處理一個決定並附上建議。
2. **Given** 養分包含經驗教訓，**When** Claude 提出摘要，
   **Then** 每一項由教訓引發的調整（例如新增一條原則、修改某個需求）都單獨標示來源教訓，由維護者決定是否採用。
3. **Given** 維護者提出這一代的新需求，**When** 討論該需求，
   **Then** Claude 像追問新需求一樣釐清到有結論，並納入功能清單與相依關係。
4. **Given** 維護者的調整彼此矛盾，或與保留的原則衝突，**When** Claude 發現，
   **Then** 指出兩邊並要求取捨。
5. **Given** 所有項目都有結論，**When** Claude 呈現最終摘要，
   **Then** 摘要列出保留、修改、合併、捨棄、新增的項目與採用的教訓，維護者確認後才產生文件。

---

### User Story 3 - 留下世代紀錄，讓循環繼續 (Priority: P1)

重建完成後，新專案記得自己是第幾代、每項需求來自哪一代、繼承了哪些教訓。
日後這個專案執行 `/sdd-export` 時，這些資訊會連同新增的需求一起成為下一代的養分。

**Why this priority**: 沒有世代紀錄，重生就只能做一次；它是「可重複的循環」成立的必要條件。

**Independent Test**: 重建後檢查新專案的世代紀錄，再新增 1 份 spec 並執行 sdd-export，
確認養分的世代編號加一，且繼承與新增的需求來源正確。

**Acceptance Scenarios**:

1. **Given** 文件已產生，**When** 重建結束，
   **Then** 新專案留有世代紀錄：世代編號、每份 spec 對應的需求來自哪一代、繼承的經驗教訓。
2. **Given** 重建時新增的需求，**When** 檢視世代紀錄，**Then** 它們的來源是這一代。
3. **Given** 被合併或修改過的需求，**When** 檢視世代紀錄，
   **Then** 仍可追溯到它們在前代的來源。
4. **Given** 被捨棄的需求，**When** 檢視世代紀錄，
   **Then** 記錄了它們被捨棄，不會在下一次匯出時重新出現為有效需求。

---

### User Story 4 - 舊專案沒有養分時直接從路徑重建 (Priority: P2)

舊專案還沒有執行過 `/sdd-export`。維護者直接指定它的路徑，Claude 先對舊專案完成匯出的步驟（含確認），
再繼續重建，不必切換到舊專案另外執行一次。

**Why this priority**: 兩個專案在同一台機器時省下一個步驟；沒有它流程仍可完成，所以排在後面。

**Independent Test**: 指定一個沒有養分的舊專案路徑，確認 Claude 先走完匯出的確認，再進入重建的確認，
最後舊專案多出養分目錄、新專案產生文件。

**Acceptance Scenarios**:

1. **Given** 指定的舊專案沒有養分，**When** 執行 `/sdd-rebuild`，
   **Then** Claude 說明將先進行匯出，並依 006 sdd-export 的規則完成，包含維護者的確認。
2. **Given** 匯出的確認完成，**When** 養分寫入舊專案，
   **Then** 舊專案只多出養分的專用目錄，其他檔案不變；接著繼續重建流程。
3. **Given** 維護者不同意在舊專案寫入養分，**When** 表示拒絕，
   **Then** 流程停止，兩個專案都沒有被寫入。

### Edge Cases

- 新專案未導入 Spec Kit：回報並請維護者先執行 `/sdd-init`，不開始重建。
- 新專案已有 constitution 或 spec：不覆蓋，只提出養分與既有內容的差異，由維護者決定要新增哪些。
- 指定的路徑不存在、不是專案，或養分無法讀取：回報原因並停止，不產生任何文件。
- 養分的格式比本 skill 認得的版本新或舊：說明無法安全讀取的部分，不猜測內容。
- 養分含有標為待確認的項目：重建時逐項請維護者決定，不當成事實寫入。
- 沒有指定舊專案：請維護者提供路徑，不自行搜尋。
- 產生文件的過程中途失敗：回報已產生與未產生的文件，不自行補寫；再次執行時不重複產生已存在的 spec。
- 維護者中途結束：不產生文件，不留下不完整的世代紀錄。
- 舊專案與新專案是同一個目錄：回報並停止。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 維護者 MUST 能在新專案以 `/sdd-rebuild` 加上舊專案的路徑啟動重建。
- **FR-002**: 新專案 MUST 已導入 Spec Kit；未導入時 MUST 回報並請維護者先執行 `/sdd-init`。
- **FR-003**: 舊專案有養分時 MUST 讀取它；沒有時 MUST 先依 006 sdd-export 的規則對舊專案完成匯出（含維護者確認），再繼續。
- **FR-004**: 除了 FR-003 經確認的匯出之外，本 skill MUST NOT 修改舊專案的任何內容。
- **FR-005**: 維護者 MUST 能選擇原樣重建，或逐項保留、修改、合併、捨棄養分中的原則與功能。
- **FR-006**: 維護者 MUST 能在重建時加入這一代的新需求；新需求 MUST 被釐清到有結論才納入。
- **FR-007**: 由經驗教訓引發的每一項調整 MUST 單獨呈現並標示來源教訓，由維護者決定是否採用；
  MUST NOT 未經同意就改變原則或需求。
- **FR-008**: 逐項討論時 MUST 一次只處理一個決定並附上建議；矛盾 MUST 被指出並由維護者取捨。
- **FR-009**: 產生文件前 MUST 呈現最終摘要：保留、修改、合併、捨棄、新增的項目，採用的教訓，以及 spec 的順序。
- **FR-010**: 維護者確認摘要之前，MUST NOT 寫入或修改新專案的 constitution、spec 與世代紀錄。
- **FR-011**: 確認後 MUST 透過 Spec Kit 產生 constitution 與每個功能各一份 spec；MUST NOT 自行手寫這些文件。
- **FR-012**: spec MUST 依相依順序重新編號，使編號等於建議的施工順序；MUST NOT 沿用舊專案的編號。
- **FR-013**: 產生的 constitution MUST 只包含確認過的原則；多出的規則 MUST 被移除，或先經維護者同意才保留。
- **FR-014**: 舊專案的 plan、tasks 與程式碼 MUST NOT 被帶入新專案。
- **FR-015**: 新專案已有 constitution 或 spec 時，MUST NOT 覆蓋它們；MUST 只提出差異，由維護者決定。
- **FR-016**: 重建完成後 MUST 在新專案留下世代紀錄：世代編號、每項需求來自哪一代、繼承的經驗教訓，
  以及被捨棄的項目；該紀錄 MUST 可被 006 sdd-export 讀取。
- **FR-017**: 文件產生後 MUST 列出每份 spec 的位置與順序，說明下一步是 `/sdd-drive`，並 MUST 停止，
  MUST NOT 自動開始 plan 或實作。
- **FR-018**: 養分中標為待確認的項目 MUST 逐項請維護者決定，MUST NOT 當成事實寫入。
- **FR-019**: 路徑無效、養分無法讀取或 Spec Kit 無法使用時，MUST 回報原因並停止，MUST NOT 產生任何文件。
- **FR-020**: 在一個平台匯出的養分 MUST 能在另一個平台重建；本 skill 在 Windows 與 Linux MUST 有相同的行為。
- **FR-021**: 產生的文件 MUST 使用繁體中文，規範詞保留英文，除非新專案既有文件使用其他語言。
- **FR-022**: 本 skill MUST 以英文撰寫，其資料夾 MUST 包含一份繁體中文的 README 簡述。

### Key Entities

- **養分**: 舊專案由 006 sdd-export 產生的內容，是重建的輸入。
- **重建決定**: 對養分中每個原則、功能與教訓的處置：保留、修改、合併、捨棄，或採用與否。
- **新需求**: 這一代才加入的需求，來源世代是這一代。
- **重建摘要**: 呈現給維護者確認的最終結果，是產生文件的唯一依據。
- **世代紀錄**: 留在新專案的延續資訊，連接這一代與下一次匯出。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 維護者確認摘要之前，新專案的 constitution、spec 與世代紀錄的異動數量為 0。
- **SC-002**: 原樣重建時，養分中 100% 的功能在新專案都有對應的 spec。
- **SC-003**: 新專案中來自舊專案的 plan、tasks 與程式碼的數量為 0。
- **SC-004**: 產生的 spec 編號順序 100% 符合相依關係。
- **SC-005**: 未經維護者同意而由教訓引發的原則或需求變更數量為 0。
- **SC-006**: 重建後不做任何手動補充，新專案即可執行 sdd-export 並得到世代編號加一、來源正確的養分。
- **SC-007**: 新專案既有的 constitution 與 spec 被覆蓋的數量為 0。
- **SC-008**: 除了經確認的匯出，舊專案被修改的檔案數量為 0。

## Assumptions

- 世代紀錄的格式與位置由 plan 決定，並與 006 sdd-export 的養分格式一致。
- 對話式流程的自動測試能涵蓋的範圍由 plan 決定；依 constitution，本功能仍 MUST 有自動測試並在兩個平台的 CI 通過。
- 維護者指定的限制：產出只有 skill 文件或 script；Python script 一律用 uv 執行。
- 舊專案必須能以本機路徑存取；跨機器時由維護者先取得舊專案的 repo。
- 一次重建只接受一個舊專案；合併多個舊專案不在範圍內。
- 重建中斷後的接續方式比照 005 sdd-grill 的進度保存，細節由 plan 決定。
- 實作由 008 sdd-drive 負責，本功能止於 spec。
