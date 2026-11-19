# Feature Specification: sdd-grill 依需求追問出 constitution 與 spec

**Feature Branch**: `005-sdd-grill`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "以維護者給的需求描述為起點，逐題追問到每個決策都有結論，確認後交給 Spec Kit 產生 constitution 與 spec，然後停止。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 從一段需求描述追問出完整的決策 (Priority: P1)

維護者輸入 `/sdd-grill` 並附上一段需求描述。Claude 依這段需求找出尚未決定的事項，
一次問一題、每題附上建議，直到 constitution 的原則與每個功能都有結論。

**Why this priority**: 這是本功能的核心：把含糊的需求變成一組明確、經維護者同意的決策。

**Independent Test**: 以一段刻意含糊的需求描述啟動，確認每一則提問只有一題、都有建議與理由，
且問題內容都能對應到該需求，而不是與需求無關的制式題目。

**Acceptance Scenarios**:

1. **Given** 專案已導入 Spec Kit，**When** 維護者以一段需求描述啟動 sdd-grill，
   **Then** Claude 先讀取專案現有內容，再提出第一個問題；問題源自該需求中未決定的事項。
2. **Given** 追問進行中，**When** Claude 提問，
   **Then** 每則訊息只有一個問題，附上建議的答案與理由，且建議排在第一個選項。
3. **Given** 某件事可以從專案內容查到，**When** 追問進行到該事項，
   **Then** Claude 自行查出並採用，不向維護者提問。
4. **Given** 維護者的回答含糊（例如「要快」），**When** Claude 收到回答，
   **Then** 繼續追問，直到能判斷一個做法是否符合為止。
5. **Given** 新的回答與先前的決定矛盾，**When** Claude 收到回答，
   **Then** 指出矛盾的兩邊並要求維護者取捨。
6. **Given** 追問開始，**When** 依序進行，
   **Then** 先完成 constitution 的原則，再列出功能清單與相依關係，然後逐一討論每個功能的使用情境、範圍與邊界情況。
7. **Given** 討論觸及語言、框架、資料庫等技術選型，**When** Claude 處理該話題，
   **Then** 只記錄為「留給 plan」，不展開討論。

---

### User Story 2 - 確認摘要後才產生文件 (Priority: P1)

所有決策都有結論或已明確延後時，Claude 呈現一份決策摘要。維護者確認後，
Claude 才透過 Spec Kit 產生 constitution 與每個功能的 spec，然後停止。

**Why this priority**: 「先確認再寫入」是 constitution 的原則；spec 是後續實作的依據，不能未經同意就寫入。

**Independent Test**: 走完一次追問，確認在維護者確認之前 constitution 與 `specs/` 沒有任何變化；
確認之後產生的文件內容與摘要一致，沒有多出未確認的規則。

**Acceptance Scenarios**:

1. **Given** 所有決策都有結論或已延後，**When** Claude 呈現摘要，
   **Then** 摘要包含已決定、已延後（含原因）、留給 plan 的事項，以及依相依關係排列的功能順序。
2. **Given** 維護者尚未確認摘要，**When** 檢查專案，
   **Then** constitution 與 spec 都沒有被寫入或修改。
3. **Given** 維護者要求修改摘要，**When** Claude 完成修改，
   **Then** 再次請維護者確認，仍不寫入文件。
4. **Given** 維護者確認摘要，**When** Claude 產生文件，
   **Then** constitution 只包含確認過的原則，每個功能各有一份 spec，編號依相依順序，被依賴的功能排在前面；
   已延後的事項記錄在對應 spec 的假設中。
5. **Given** 文件已產生，**When** 流程結束，
   **Then** Claude 列出每份 spec 的位置、相依關係與建議順序，說明下一步是由維護者輸入 `/sdd-drive`，
   然後停止，不自動開始 plan 或實作。

---

### User Story 3 - 中斷後接續 (Priority: P2)

追問可能很長。維護者可以隨時結束，之後再執行 `/sdd-grill` 時從上次的進度繼續，不必重答。

**Why this priority**: 需求討論常跨越多次工作階段；沒有接續能力，長討論的成本會高到讓人放棄。

**Independent Test**: 回答數題後結束對話，開新的對話再次啟動，確認已決定的事項被列出且可選擇接續。

**Acceptance Scenarios**:

1. **Given** 追問進行中，**When** 維護者做出一個決定，**Then** 進度立即被保存。
2. **Given** 維護者要求結束，**When** Claude 收到要求，
   **Then** 呈現目前的摘要、保留進度，然後停止。
3. **Given** 專案有先前的進度，**When** 再次啟動 sdd-grill，
   **Then** Claude 先列出已決定的事項，請維護者選擇接續或重新開始；選擇重新開始時清除舊進度。
4. **Given** 專案在上次討論之後有變更，**When** 再次啟動，
   **Then** Claude 先提示有變更，由維護者決定是否沿用舊進度。
5. **Given** 文件已成功產生，**When** 流程結束，**Then** 進度被清除。

---

### User Story 4 - 為已有 spec 的專案加入新需求 (Priority: P2)

專案已經有 constitution 與若干 spec。維護者帶著新需求執行 `/sdd-grill`，
Claude 在既有決定的基礎上追問，只為新需求產生新的 spec。

**Why this priority**: 這是每個專案流程中反覆出現的步驟：實作完一批之後，新需求仍由 sdd-grill 進入。

**Independent Test**: 在已有 constitution 與 3 份 spec 的專案以新需求啟動，
確認既有文件不被覆蓋，新 spec 的編號接在既有之後。

**Acceptance Scenarios**:

1. **Given** 專案已有 constitution 與 spec，**When** 以新需求啟動，
   **Then** Claude 讀取既有文件，不重問已記錄的決定，只追問新需求帶來的未決事項。
2. **Given** 新需求與既有 constitution 的原則衝突，**When** 討論到該點，
   **Then** Claude 指出衝突，由維護者決定修訂原則或調整需求。
3. **Given** 維護者確認摘要，**When** 產生文件，
   **Then** 既有 spec 不被覆蓋，新 spec 的編號接在既有之後；constitution 只在維護者同意修訂時更動。

### Edge Cases

- 專案未導入 Spec Kit：回報並請維護者先執行 `/sdd-init`，不開始追問，也不自行建立 Spec Kit 的檔案。
- 專案的 Spec Kit 缺少產生 constitution 或 spec 所需的能力：回報可能有不相容的變更並停止，不自行寫出文件。
- 啟動時沒有附需求描述：先請維護者說明需求，再開始追問。
- 產生文件的過程中途失敗：回報已產生與未產生的文件，保留進度，不自行補寫。
- 互動式提問工具不能用：改用文字提問，仍然一次一題並附建議。
- 維護者提供的內容含有機密值：不寫入進度與產生的文件。
- 產生的 constitution 多出未確認的規則：移除多出的內容；想保留的先問維護者。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 維護者 MUST 能以 `/sdd-grill` 加上一段需求描述啟動追問；Claude 也 MAY 在維護者方向未定時主動使用它。
- **FR-002**: 問題與建議 MUST 從維護者的需求描述與專案現有內容推導，MUST NOT 套用與需求無關的固定題庫。
- **FR-003**: 每一則提問 MUST 只包含一個問題，並 MUST 附上建議答案與理由，建議排在第一個。
- **FR-004**: 能從專案內容查到的事項 MUST 由 Claude 自行查出，MUST NOT 向維護者提問。
- **FR-005**: 回答不足以判斷做法是否符合時，Claude MUST 繼續追問到可以判斷為止。
- **FR-006**: 回答與先前的決定矛盾時，Claude MUST 指出兩邊並要求維護者取捨。
- **FR-007**: 追問 MUST 先完成 constitution 的原則，再列出功能清單與相依關係，然後逐一討論每個功能。
- **FR-008**: 技術選型 MUST 只被記錄為留給 plan 的事項，MUST NOT 在追問中討論。
- **FR-009**: 每個決定之後 MUST 保存進度；進度 MUST NOT 入庫，MUST NOT 包含機密值。
- **FR-010**: 再次啟動時若有既有進度，MUST 先列出已決定的事項並讓維護者選擇接續或重新開始；
  專案在上次討論後有變更時 MUST 先提示。
- **FR-011**: 所有決策都有結論或已延後時，MUST 呈現決策摘要：已決定、已延後與原因、留給 plan、功能順序。
- **FR-012**: 維護者確認摘要之前，MUST NOT 寫入或修改 constitution 與 spec。
- **FR-013**: 確認後 MUST 透過 Spec Kit 產生 constitution 與每個功能各一份 spec；MUST NOT 自行手寫這些文件。
- **FR-014**: 產生的 constitution MUST 只包含確認過的原則；多出的規則 MUST 被移除，或先經維護者同意才保留。
- **FR-015**: spec MUST 依相依順序產生，使編號等於建議的施工順序；已延後的事項 MUST 記錄在對應 spec 的假設中。
- **FR-016**: 專案已有 constitution 或 spec 時，MUST NOT 覆蓋既有文件；新 spec 的編號 MUST 接在既有之後。
- **FR-017**: 文件產生後 MUST 列出每份 spec 的位置、相依關係與建議順序，說明下一步是 `/sdd-drive`，
  並 MUST 停止，MUST NOT 自動開始 plan 或實作。
- **FR-018**: 文件成功產生後 MUST 清除進度；維護者中途結束或產生失敗時 MUST 保留進度。
- **FR-019**: 專案未導入 Spec Kit 或 Spec Kit 無法使用時，MUST 回報並停止，MUST NOT 自行建立或寫出相關檔案。
- **FR-020**: 產生的文件 MUST 使用專案既有文件的語言；無法判斷時使用繁體中文，規範詞保留英文。
- **FR-021**: 本 skill 在 Windows 與 Linux MUST 有相同的行為。
- **FR-022**: 本 skill MUST 以英文撰寫，其資料夾 MUST 包含一份繁體中文的 README 簡述。

### Key Entities

- **需求描述**: 維護者啟動時提供的文字，是所有問題的起點。
- **決定**: 一個有結論的事項，屬於 constitution 的原則或某個功能。
- **進度**: 目前為止的決定、延後事項、留給 plan 的事項與正在討論的功能；只存在於本機。
- **決策摘要**: 呈現給維護者確認的完整結果，是產生文件的唯一依據。
- **功能清單**: 需求拆出的功能及其相依關係，決定 spec 的編號順序。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% 的提問訊息只含一個問題，且都附有建議答案與理由。
- **SC-002**: 維護者確認摘要之前，constitution 與 spec 的異動數量為 0。
- **SC-003**: 產生的 constitution 中，未出現在確認摘要裡的規則數量為 0。
- **SC-004**: 中斷後接續時，維護者需要重新回答的已決定事項數量為 0。
- **SC-005**: 產生的 spec 編號順序 100% 符合相依關係（被依賴的功能編號較小）。
- **SC-006**: 維護者檢視追問過程時，能把每一個問題對應到需求描述或專案內容中的某個未決事項。
- **SC-007**: 流程結束後，維護者不需要追問就知道下一步該輸入什麼指令。

## Assumptions

- 進度保存的位置與格式由 plan 決定。
- 對話式流程的自動測試能涵蓋的範圍由 plan 決定；依 constitution，本功能仍 MUST 有自動測試並在兩個平台的 CI 通過。
- 維護者指定的限制：產出只有 skill 文件或 script；Python script 一律用 uv 執行。
- 提問時使用互動式提問工具是全域 CLAUDE.md（002）的偏好；本 skill 與它相容。
- 從舊專案帶入需求屬於 006 sdd-export 與 007 sdd-rebuild；本功能只處理維護者直接提出的需求。
- 實作由 008 sdd-drive 負責，本功能止於 spec。
