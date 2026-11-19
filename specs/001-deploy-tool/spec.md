# Feature Specification: 部署工具

**Feature Branch**: `001-deploy-tool`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "以一行指令把 claude-settings repo 裡的全域 CLAUDE.md 與 6 個 SDD skill 安裝到 Windows 與 Linux 的 `~/.claude`，可更新與移除，且不覆蓋不是自己安裝的檔案。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 在新機器上一行指令完成安裝 (Priority: P1)

維護者在一台 Windows 或 Linux 機器上貼上一行指令，全域 CLAUDE.md 與 6 個 SDD skill
（sdd-init、sdd-update、sdd-grill、sdd-export、sdd-rebuild、sdd-drive）就安裝到 `~/.claude`，
不需要其他手動步驟。

**Why this priority**: 這是其他所有功能的基礎；沒有它，其餘內容只能手動複製，也無法在兩個平台驗證。

**Independent Test**: 在一個沒有本工具安裝紀錄的家目錄執行該指令，確認 CLAUDE.md 與 6 個 skill 都出現在
`~/.claude`，且內容與 repo 相同。

**Acceptance Scenarios**:

1. **Given** 一台具備所有必要指令、`~/.claude` 沒有同名檔案的機器，**When** 執行安裝指令，
   **Then** CLAUDE.md 與 6 個 skill 都安裝完成，並回報安裝了哪些檔案。
2. **Given** 機器缺少一個以上的必要指令，**When** 執行安裝指令，
   **Then** 工具停止、一次列出所有缺少的套件，不代為安裝，也不寫入任何檔案。
3. **Given** 相同的 repo 內容，**When** 分別在 Windows 與 Linux 執行安裝指令，
   **Then** 兩邊安裝的檔案集合與內容相同，回報的資訊相同。

---

### User Story 2 - 重跑同一行指令即更新 (Priority: P2)

repo 有新版時，維護者再執行一次同一行指令，`~/.claude` 內由本工具安裝的內容就更新到最新版。

**Why this priority**: 設定會持續演進，更新必須和安裝一樣簡單，否則各台機器會逐漸不一致。

**Independent Test**: 安裝後修改 repo 內容並重新執行指令，確認 `~/.claude` 反映新內容；
不修改 repo 再執行一次，確認沒有任何異動。

**Acceptance Scenarios**:

1. **Given** 已安裝且 repo 有新版，**When** 重新執行同一行指令，
   **Then** 本工具安裝的檔案更新為新版，新版已移除的檔案也從 `~/.claude` 移除，並回報異動。
2. **Given** 已安裝且沒有任何變更，**When** 重新執行同一行指令，
   **Then** 不產生任何檔案異動，並回報已是最新。

---

### User Story 3 - 不覆蓋別人的檔案與手動修改 (Priority: P2)

`~/.claude` 內已有不是本工具安裝的同名檔案，或本工具安裝的檔案被維護者直接手動改過時，
工具停下來說明，而不是悄悄覆蓋。

**Why this priority**: `~/.claude` 內有使用者自己的內容；維護者的機器上已有另一個專案
（claude-dotfiles）部署的 CLAUDE.md 與同名 sdd-* skill，第一次安裝必定會遇到。

**Independent Test**: 預先在 `~/.claude` 放置同名檔案後執行安裝，確認沒有任何檔案被寫入且衝突清單完整；
再明確要求取代，確認原檔已備份。

**Acceptance Scenarios**:

1. **Given** `~/.claude` 有不是本工具安裝的同名檔案，**When** 執行安裝或更新，
   **Then** 工具停止並列出所有衝突的檔案，整批不寫入任何檔案。
2. **Given** 同上的衝突，**When** 維護者明確要求取代後再次執行，
   **Then** 衝突的原檔先被備份，再寫入新內容，並回報備份的位置。
3. **Given** 本工具安裝的檔案之後被直接在 `~/.claude` 手動修改，**When** 執行更新或移除，
   **Then** 工具停止並列出與安裝時不同的檔案，整批不寫入、不刪除任何檔案。
4. **Given** 同上的手動修改，**When** 維護者把修改搬回 repo 使內容一致，或明確要求取代，
   **Then** 操作可以繼續；明確取代時被改過的檔案先備份。

---

### User Story 4 - 移除並還原 (Priority: P3)

維護者不再使用這份設定時，執行移除，`~/.claude` 回到安裝前的狀態。

**Why this priority**: 讓安裝是可逆的，維護者才能放心在既有環境試用；使用頻率低於安裝與更新。

**Independent Test**: 在已有其他內容的 `~/.claude` 安裝後再移除，確認本工具安裝的檔案都消失、
被取代過的原檔已還原、其他內容與安裝前完全相同。

**Acceptance Scenarios**:

1. **Given** 已安裝，**When** 執行移除，
   **Then** 只刪除本工具安裝的檔案，安裝時備份的原檔被還原，其他內容不受影響。
2. **Given** 從未安裝，**When** 執行移除，**Then** 不產生任何異動，並回報沒有可移除的內容。

### Edge Cases

- 安裝或更新在中途失敗（例如磁碟已滿、權限不足）：工具回報失敗的位置；再次執行時能完成或回到一致的狀態，
  不留下無法分辨歸屬的檔案。
- `~/.claude` 尚不存在：視為沒有任何既有檔案，直接建立並安裝。
- 安裝紀錄遺失或損毀：工具無法證明檔案是自己安裝的，一律視為別人的檔案，依衝突處理。
- 無法取得 repo 的最新內容（例如沒有網路）：停止並回報原因，不寫入任何檔案。
- 既有的同名檔案內容恰好與要安裝的內容完全相同：不算衝突，不需要備份，納入安裝紀錄。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 工具 MUST 讓維護者在 Windows 與 Linux 各以一行指令完成安裝，過程不需要其他互動。
- **FR-002**: 安裝內容 MUST 是 repo 中的全域 CLAUDE.md 與 6 個 SDD skill，安裝位置是使用者家目錄下的 `~/.claude`。
- **FR-003**: 工具 MUST 在寫入任何檔案前檢查所有需要的指令是否存在；有缺少時 MUST 停止並一次列出所有缺少的套件，
  MUST NOT 代為安裝。
- **FR-004**: 工具 MUST 記錄自己安裝過哪些檔案，並以此分辨「自己安裝的」與「不是自己安裝的」檔案。
- **FR-005**: 重新執行同一行指令 MUST 把已安裝的內容更新到 repo 的最新版，包含移除新版不再提供的檔案。
- **FR-006**: 沒有任何變更時，重複執行 MUST NOT 產生任何檔案異動。
- **FR-007**: 遇到不是自己安裝、且內容不同的同名檔案時，工具 MUST 停止、列出所有衝突，
  且 MUST NOT 寫入任何檔案。
- **FR-008**: 自己安裝的檔案被手動修改時，更新與移除 MUST 停止、列出與安裝時不同的檔案，
  且 MUST NOT 寫入或刪除任何檔案。
- **FR-009**: 只有維護者明確要求取代時，工具才可以覆蓋 FR-007 與 FR-008 所述的檔案，
  且覆蓋前 MUST 先備份原檔並回報備份位置。
- **FR-010**: 工具 MUST 提供移除：只刪除自己安裝的檔案，還原安裝時備份的原檔，
  MUST NOT 更動 `~/.claude` 內的其他內容。
- **FR-011**: 每次執行結束時，工具 MUST 回報結果：安裝、更新、移除、略過或衝突的檔案，以及失敗的原因。
- **FR-012**: 同一份 repo 內容在 Windows 與 Linux 上 MUST 產生相同的安裝結果與相同的衝突判定。
- **FR-013**: 安裝紀錄與 repo MUST NOT 包含機密、憑證、機器專屬路徑與個人信箱。
- **FR-014**: 工具 MUST NOT 提供上述以外的可調選項；它只為維護者個人使用而設計。

### Key Entities

- **部署內容**: repo 中要安裝的檔案集合，即全域 CLAUDE.md 與 6 個 SDD skill 的資料夾。
- **安裝紀錄**: 本工具在某台機器上安裝過哪些檔案、安裝時各檔案內容的識別資訊，以及是否有對應的備份。
- **備份**: 被明確取代的原檔副本，供移除時還原。
- **衝突清單**: 一次執行中所有不是自己安裝的同名檔案，以及被手動修改的已安裝檔案。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 在具備必要指令的新機器上，維護者從貼上指令到安裝完成不超過 2 分鐘，且不需要輸入其他內容。
- **SC-002**: 在 Windows 與 Linux 以相同的 repo 內容與相同的初始狀態執行，安裝結果 100% 相同。
- **SC-003**: 在任何衝突或手動修改的情境下，未經明確要求取代時，被工具覆蓋或刪除的既有檔案數量為 0。
- **SC-004**: 沒有變更時連續執行 10 次，`~/.claude` 內的檔案異動數量為 0。
- **SC-005**: 安裝後再移除，`~/.claude` 內不屬於本工具的內容與安裝前 100% 相同，被取代過的原檔 100% 還原。
- **SC-006**: 缺少必要指令時，維護者執行一次就能得知全部缺少的套件，不需要反覆執行。

## Assumptions

- 一行指令的實作方式、安裝紀錄與備份的格式和位置由 plan 決定。
- 維護者指定的限制：本專案的產出只有 skill 文件或 script；Python script 一律用 uv 執行。
- 依 constitution，本功能 MUST 有自動測試，並在 Windows 與 Linux 的 CI 上都通過才能合併。
- 「最新版」指 repo 預設分支的最新內容；不提供安裝指定版本的選項。
- 既有檔案內容與要安裝的內容完全相同時不視為衝突。
- 本功能沒有相依的其他功能；全域 CLAUDE.md 與各 skill 的內容由各自的 spec 定義。
- macOS 不在支援範圍。
