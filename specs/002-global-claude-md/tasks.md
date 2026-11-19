---

description: "Task list for 002 全域 CLAUDE.md"
---

# Tasks: 全域 CLAUDE.md

**Input**: Design documents from `/specs/002-global-claude-md/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/claude-md-structure.md、quickstart.md

**Tests**: 需要。Constitution 原則 II 要求每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
自動測試驗證文件結構；Claude 的實際行為以 quickstart 的情境人工驗收（research.md R4）。

**Organization**: 依 user story 分組。兩個 story 寫入同一份 `home/CLAUDE.md` 的不同段落。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、沒有未完成的相依）
- **[Story]**: 所屬的 user story（US1、US2）
- 路徑相對於 repo 根目錄

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認 001 提供的基礎可用

- [X] T001 確認 `home/`、`tests/unit/` 與 `.github/workflows/ci.yml` 已存在，且 `uv run --with pytest pytest` 在目前的分支全部通過

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 兩個 story 共用的文件骨架與測試輔助

**⚠️ CRITICAL**: 這個階段完成前不能開始任何 user story

- [X] T002 建立 `home/CLAUDE.md` 骨架：一個一級標題與依序的三個二級標題「溝通」「Git」「規格驅動開發」，UTF-8、LF、結尾有換行（data-model.md「文件」）
- [X] T003 [P] 建立 `tests/unit/test_claude_md.py`：讀取 `home/CLAUDE.md` 的輔助函式（以位元組讀取後解碼）、把文件切成段落與規則的解析函式，以及文件層級的測試：恰好三個二級標題且順序正確、不含 CR、結尾有換行（contracts/claude-md-structure.md 約定 1、6）

**Checkpoint**: 骨架與解析就緒

---

## Phase 3: User Story 1 - 每個專案都依維護者的溝通與 Git 偏好運作 (Priority: P1) 🎯 MVP

**Goal**: 「溝通」與「Git」兩段完成，每條規則都附可觀察的預期

**Independent Test**: 結構測試通過；安裝後在新專案對話，quickstart 第 1 至 4 項符合

### Tests for User Story 1 ⚠️

> 先寫測試並確認失敗，再實作

- [X] T004 [US1] 在 `tests/unit/test_claude_md.py` 加入：每個頂層清單項目的下一個非空行以兩個空白加「預期：」開頭（data-model.md「規則」，contracts 約定 2）；「溝通」段有 3 條規則、「Git」段有 3 條規則
- [X] T005 [US1] 在 `tests/unit/test_claude_md.py` 加入：文件不含電子信箱、以 `/home/` 或 `/Users/` 開頭的路徑、`C:\` 這類磁碟路徑（FR-009，contracts 約定 5）

### Implementation for User Story 1

- [X] T006 [US1] 在 `home/CLAUDE.md` 撰寫「溝通」段的 3 條規則與預期：繁體中文回覆並保留原文術語；以 AskUserQuestion 呈現選項並標出建議；skill 要求文字或表格提問時仍改用 AskUserQuestion（FR-002、FR-003，research.md R1）
- [X] T007 [US1] 在 `home/CLAUDE.md` 撰寫「Git」段的 3 條規則與預期：每項異動就 commit；不直接 commit 到 `main`；明確要求才 push（FR-004，research.md R1）

**Checkpoint**: 文件已可部署並提供溝通與 Git 偏好

---

## Phase 4: User Story 2 - 新功能自動導向本專案的 SDD 流程 (Priority: P2)

**Goal**: 「規格驅動開發」段以本專案的 6 個 skill 描述流程

**Independent Test**: 結構測試通過；quickstart 第 5 至 10 項符合（skill 尚未安裝時，預期 Claude 回報不存在）

### Tests for User Story 2 ⚠️

- [X] T008 [US2] 在 `tests/unit/test_claude_md.py` 加入：文件中出現的所有 `sdd-<名稱>` 都屬於 `sdd-init`、`sdd-update`、`sdd-grill`、`sdd-export`、`sdd-rebuild`、`sdd-drive`，六個名稱都至少出現一次，且不出現 `sdd-derive`（FR-006、FR-007，contracts 約定 3、4）
- [X] T009 [US2] 在 `tests/unit/test_claude_md.py` 加入：文件引用的每個 skill 在 `home/skills/<名稱>/SKILL.md` 存在；6 個資料夾尚未到齊時以 skip 跳過並在原因中列出缺少的 skill（SC-002，research.md R3）

### Implementation for User Story 2

- [X] T010 [US2] 在 `home/CLAUDE.md` 撰寫「規格驅動開發」段：前言說明新功能走 Spec Kit、不改變行為的小改動除外；依 research.md R2 的表格寫 5 條規則與預期（`/sdd-init`、`sdd-grill`、`/sdd-export` 與 `/sdd-rebuild`、`/sdd-drive`、`/sdd-update`）（FR-005、FR-006、FR-008）

**Checkpoint**: 三段都完成

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: 收尾與驗證

- [ ] T011 [P] 更新 `README.md`：在開頭的內容說明加入全域 CLAUDE.md，並註明其中引用的 skill 在 003 至 008 完成前尚未提供
- [ ] T012 在暫存家目錄以 `uv run tools/deploy.py` 驗證 `home/CLAUDE.md` 被安裝且位元組與來源相同，並執行完整測試 `uv run --with pytest pytest`
- [ ] T013 推送後確認 CI 在 `ubuntu-latest` 與 `windows-latest` 都通過；Windows 以 CI 結果為準
- [ ] T014 由維護者依 `specs/002-global-claude-md/quickstart.md` 的 10 個情境人工驗收；這一項需要維護者在真實的 Claude Code session 進行，無法自動完成

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依賴 001 已合併
- **Foundational (Phase 2)**: 依賴 Setup
- **US1 (Phase 3)**: 依賴 Foundational
- **US2 (Phase 4)**: 依賴 Foundational；與 US1 寫入同一個檔案的不同段落，依序進行
- **Polish (Phase 5)**: 依賴 US1 與 US2

### Within Each User Story

- 測試先寫並確認失敗，再撰寫對應的段落
- `home/CLAUDE.md` 與 `tests/unit/test_claude_md.py` 各是單一檔案，改同一個檔案的任務依序進行

### Parallel Opportunities

- T003 可與 T002 平行（不同檔案）
- T011 可與 T012 平行
- 其餘任務集中在兩個檔案，沒有其他平行機會

## Parallel Example: Foundational

```text
Task: "T002 建立 home/CLAUDE.md 骨架"
Task: "T003 建立 tests/unit/test_claude_md.py 的解析與文件層級測試"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 與 Phase 2
2. 完成 Phase 3（US1）：溝通與 Git 兩段
3. 此時「規格驅動開發」段只有標題，T008 的「六個名稱都出現」尚未滿足，所以 US1 單獨不能通過完整測試；
   US1 與 US2 應在同一個 PR 內完成

### Incremental Delivery

1. Foundational：骨架與解析
2. US1：溝通與 Git
3. US2：規格驅動開發
4. Polish：README、部署驗證、CI、人工驗收

## Notes

- 每完成一個任務或一組相關任務就 commit
- T014 是人工驗收，完成與否由維護者回報
- 在 003 至 008 完成前，不建議把這份文件部署到維護者實際的 `~/.claude`（plan.md 的說明）
