---

description: "Task list for 001 部署工具"
---

# Tasks: 部署工具

**Input**: Design documents from `/specs/001-deploy-tool/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/cli.md、quickstart.md

**Tests**: 需要。Constitution 原則 II 要求每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
每個 user story 先寫測試並確認失敗，再實作。

**Organization**: 依 user story 分組，每個 story 可以獨立實作與驗證。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、沒有未完成的相依）
- **[Story]**: 所屬的 user story（US1 至 US4）
- 路徑相對於 repo 根目錄

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建立專案骨架與兩個平台一致的基礎

- [X] T001 建立目錄骨架 `home/skills/`、`tools/`、`tests/unit/`、`tests/e2e/`，並在 `home/skills/` 放 `.gitkeep`
- [X] T002 [P] 建立 `.gitattributes`，內容為 `* text=auto eol=lf`（research.md R7）
- [X] T003 [P] 建立 `.gitignore`，排除 `__pycache__/`、`.pytest_cache/`、`.venv/`
- [X] T004 [P] 建立 `.github/workflows/ci.yml`：矩陣 `ubuntu-latest` 與 `windows-latest`，安裝 uv 後執行 `uv run --with pytest pytest`（research.md R8）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有 user story 共用的核心：來源掃描、雜湊、manifest 讀寫、動作計畫與測試 fixture

**⚠️ CRITICAL**: 這個階段完成前不能開始任何 user story

- [X] T005 建立 `tools/deploy.py` 骨架：uv inline metadata（`requires-python = ">=3.11"`、無相依）、參數解析（預設、`--replace`、`remove`，未知參數結束碼 1）、結束碼常數 0/1/2/3（contracts/cli.md）
- [X] T006 在 `tools/deploy.py` 實作來源掃描與 SHA-256：列出 `home/` 下所有檔案的相對路徑（一律以 `/` 分隔），位元組原樣讀取（data-model.md「部署內容」）
- [X] T007 在 `tools/deploy.py` 實作 manifest 讀寫，欄位依 data-model.md 的 `Manifest.schema`、`Manifest.status`、`Manifest.repo_commit`、`Manifest.entries[].path`、`Manifest.entries[].sha256`、`Manifest.entries[].backup`、`Manifest.created_dirs`；寫入用暫存檔加 `os.replace`；無法解析時視為不存在
- [X] T008 在 `tools/deploy.py` 實作規劃函式：純讀取，依 data-model.md「動作計畫」的七種動作為每個路徑分類並回傳計畫
- [X] T009 在 `tools/deploy.py` 實作輸出格式：每行一筆的動作行與最後的摘要行，路徑一律用 `/`（contracts/cli.md「輸出」）
- [X] T010 [P] 建立 `tests/conftest.py`：暫存家目錄 fixture（同時設定 `HOME` 與 `USERPROFILE`）、暫存部署來源 fixture、以子程序執行 `uv run tools/deploy.py` 並回傳結束碼與輸出的輔助函式、比對目錄快照的輔助函式

**Checkpoint**: 核心就緒，可以開始 user story

---

## Phase 3: User Story 1 - 在新機器上一行指令完成安裝 (Priority: P1) 🎯 MVP

**Goal**: 一行指令把 `home/` 的內容安裝到 `~/.claude`；缺少必要指令時列出全部並停止

**Independent Test**: 在沒有安裝紀錄的暫存家目錄執行，`~/.claude` 內容與 `home/` 完全相同

### Tests for User Story 1 ⚠️

> 先寫測試並確認失敗，再實作

- [X] T011 [P] [US1] 在 `tests/unit/test_deploy.py` 加入全新安裝的測試：所有檔案被建立、內容位元組相同、輸出每筆為 `created`、結束碼 0、manifest 的 `Manifest.status` 為 `complete`
- [X] T012 [P] [US1] 在 `tests/unit/test_deploy.py` 加入 `~/.claude` 不存在時直接建立並安裝的測試
- [X] T013 [P] [US1] 在 `tests/unit/test_deploy.py` 加入 manifest 不含絕對路徑、使用者名稱與家目錄字串的測試（FR-013，data-model.md `Manifest.entries[].path`）
- [X] T014 [P] [US1] 在 `tests/e2e/test_setup_sh.py`（非 Linux 時跳過）加入：以本機 bare repo 經 `CLAUDE_SETTINGS_REPO` 執行 `tools/setup.sh` 完成安裝；`PATH` 找不到 `uv` 或 `git` 時結束碼 3、一次列出全部 `missing`、沒有 clone 也沒有寫入
- [X] T015 [P] [US1] 在 `tests/e2e/test_setup_ps1.py`（非 Windows 時跳過）加入與 T014 相同情境的 `tools/setup.ps1` 測試

### Implementation for User Story 1

- [X] T016 [US1] 在 `tools/deploy.py` 實作執行階段的 `create` 動作：先寫入 `Manifest.status` 為 `applying` 的 manifest，以暫存檔加 `os.replace` 寫入檔案，記錄 `Manifest.created_dirs`，最後改為 `complete`（research.md R5）
- [X] T017 [US1] 在 `tools/deploy.py` 實作 `Manifest.repo_commit` 的取得（`git rev-parse HEAD`，取不到時為空字串）與安裝完成的摘要行
- [X] T018 [P] [US1] 實作 `tools/setup.sh`：檢查 `git` 與 `uv` 並一次列出全部缺少的指令（結束碼 3）、clone 或 `git pull --ff-only` 到 `~/.claude-settings`、以 `uv run` 執行 `tools/deploy.py` 並原樣轉交參數、回傳其結束碼；repo URL 為單一常數，可由 `CLAUDE_SETTINGS_REPO` 覆寫（research.md R2、R3）
- [X] T019 [P] [US1] 實作 `tools/setup.ps1`：行為與 T018 完全相同，支援 `irm | iex` 與 scriptblock 帶參數兩種呼叫方式
- [X] T020 [US1] 在 `tools/deploy.py` 與兩支開機腳本處理無法取得 repo 或寫入失敗：結束碼 1、錯誤訊息到 stderr、取得失敗時不寫入 `~/.claude`

**Checkpoint**: 可以在兩個平台以開機腳本完成全新安裝

---

## Phase 4: User Story 2 - 重跑同一行指令即更新 (Priority: P2)

**Goal**: 重跑即更新到最新版；沒有變更時零異動

**Independent Test**: 安裝後修改來源再執行，`~/.claude` 反映新內容；不修改再執行一次，沒有任何異動

### Tests for User Story 2 ⚠️

- [X] T021 [P] [US2] 在 `tests/unit/test_deploy.py` 加入更新測試：來源檔案內容改變後輸出 `updated`，新增的檔案輸出 `created`，來源不再提供的檔案輸出 `deleted` 並從目標移除，manifest 同步
- [X] T022 [P] [US2] 在 `tests/unit/test_deploy.py` 加入冪等測試：沒有變更時連續執行 10 次，目錄快照（含修改時間）完全不變，輸出 `Already up to date.`（SC-004）
- [X] T023 [P] [US2] 在 `tests/unit/test_deploy.py` 加入中途失敗後收斂的測試：模擬寫到一半中斷而留下 `Manifest.status` 為 `applying`，再次執行後狀態一致且沒有歸屬不明的檔案

### Implementation for User Story 2

- [X] T024 [US2] 在 `tools/deploy.py` 實作 `keep`、`update`、`delete` 動作，以及刪除後清理 `Manifest.created_dirs` 中已變空的目錄
- [X] T025 [US2] 在 `tools/deploy.py` 實作無異動時的短路：計畫全為 `keep` 時不寫入任何檔案（包含 manifest）
- [X] T026 [US2] 在 `tools/deploy.py` 實作從 `applying` 狀態恢復：以 manifest 的目標狀態重新規劃並完成

**Checkpoint**: 安裝與更新都可用，重複執行零異動

---

## Phase 5: User Story 3 - 不覆蓋別人的檔案與手動修改 (Priority: P2)

**Goal**: 任何衝突都整批不寫入；只有 `--replace` 才覆蓋，且先備份

**Independent Test**: 預先放置同名檔案後安裝，零寫入且衝突清單完整；加上 `--replace` 後原檔已備份

### Tests for User Story 3 ⚠️

- [X] T027 [P] [US3] 在 `tests/unit/test_deploy.py` 加入別人的同名檔案測試：結束碼 2、列出全部 `conflict ... (not installed by this tool)`、目錄快照完全不變，包含沒有衝突的其他檔案也沒有被寫入（FR-007）
- [X] T028 [P] [US3] 在 `tests/unit/test_deploy.py` 加入手動修改測試：已安裝的檔案被改後執行更新，結束碼 2、列出 `conflict ... (modified since install)`、零寫入（FR-008）
- [X] T029 [P] [US3] 在 `tests/unit/test_deploy.py` 加入 `--replace` 測試：別人的原檔出現在 `backups/` 且 `Manifest.entries[].backup` 為 true；被手動改過的版本出現在 `discarded/<時間戳>/`；輸出含 `backup` 行；同一路徑第二次取代不覆寫第一次的備份
- [X] T030 [P] [US3] 在 `tests/unit/test_deploy.py` 加入邊界測試：既有檔案內容與來源完全相同時輸出 `adopted`、不備份、不算衝突；manifest 遺失或損毀時既有檔案一律依「別人的」處理

### Implementation for User Story 3

- [X] T031 [US3] 在 `tools/deploy.py` 實作衝突閘門：計畫含任何 `conflict-foreign` 或 `conflict-modified` 且沒有 `--replace` 時，輸出全部衝突與摘要後以結束碼 2 結束，不進入執行階段
- [X] T032 [US3] 在 `tools/deploy.py` 實作 `adopt` 動作與 `--replace` 下的備份：`conflict-foreign` 備份到 `backups/<path>`（只保留第一次），`conflict-modified` 搬到 `discarded/<UTC 時間戳>/<path>`，再寫入新內容（data-model.md「備份」「捨棄的修改」）

**Checkpoint**: 既有檔案在所有情境下都受到保護

---

## Phase 6: User Story 4 - 移除並還原 (Priority: P3)

**Goal**: 移除只刪自己安裝的檔案並還原備份，`~/.claude` 回到安裝前的狀態

**Independent Test**: 在已有其他內容的 `~/.claude` 安裝後移除，其他內容不變、被取代的原檔已還原

### Tests for User Story 4 ⚠️

- [X] T033 [P] [US4] 在 `tests/unit/test_deploy.py` 加入往返測試：預先放置無關檔案與一個會被取代的同名檔案，執行 `--replace` 安裝再 `remove`，目錄快照與安裝前完全相同，`.claude-settings/` 不存在（SC-005）
- [X] T034 [P] [US4] 在 `tests/unit/test_deploy.py` 加入：從未安裝時 `remove` 結束碼 0、零異動；已安裝檔案被手動修改時 `remove` 結束碼 2、零刪除；`remove --replace` 把被改的版本搬到 `discarded/` 後完成移除並保留該目錄；manifest 內但目標已不存在的檔案不算衝突

### Implementation for User Story 4

- [X] T035 [US4] 在 `tools/deploy.py` 實作 `remove`：規劃（比對 `Manifest.entries[].sha256`）→ 衝突閘門 → 刪除自己的檔案 → 依 `Manifest.entries[].backup` 把備份搬回原位並輸出 `restored` → 清理 `Manifest.created_dirs` 中變空的目錄 → 刪除狀態目錄（`discarded/` 有內容時保留並回報位置）

**Checkpoint**: 四個 user story 都可獨立運作

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 跨 story 的收尾

- [X] T036 [P] 在 `tests/unit/test_deploy.py` 加入輸出一致性測試：相同輸入下，輸出的動作行與摘要行不含反斜線與平台相關字串（FR-012、SC-002）
- [X] T037 [P] 撰寫 `README.md`（繁體中文）：兩個平台的一行指令、`--replace` 與 `remove` 的用法、結束碼、備份位置；repo 位址以佔位標示，待建立 remote 後填入
- [X] T038 依 `specs/001-deploy-tool/quickstart.md` 的七個手動情境在暫存家目錄逐一驗證並修正差異
- [ ] T039 推送後確認 `.github/workflows/ci.yml` 在 `ubuntu-latest` 與 `windows-latest` 都通過；本機無法驗證 Windows，這一項以 CI 結果為準

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 無相依
- **Foundational (Phase 2)**: 依賴 Setup，阻擋所有 user story
- **US1 (Phase 3)**: 依賴 Foundational
- **US2 (Phase 4)**: 依賴 US1（更新建立在安裝之上）
- **US3 (Phase 5)**: 依賴 US1；`--replace` 對手動修改的處理另需要 US2 的 `update`
- **US4 (Phase 6)**: 依賴 US1；還原備份需要 US3
- **Polish (Phase 7)**: 依賴所有 user story

### Within Each User Story

- 測試先寫並確認失敗，再實作
- `tools/deploy.py` 是單一檔案，同一階段內修改它的任務依序進行，不標 [P]
- 兩支開機腳本（T018、T019）是不同檔案，可平行

### Parallel Opportunities

- Phase 1：T002、T003、T004 可平行
- Phase 2：T010 可與 T005 至 T009 平行
- 每個 story 的測試任務都在加入獨立的測試函式，可平行撰寫（合併時注意同檔案）
- US1：T018 與 T019 可平行

## Parallel Example: User Story 1

```text
Task: "T011 全新安裝的測試 in tests/unit/test_deploy.py"
Task: "T014 setup.sh 的 E2E 測試 in tests/e2e/test_setup_sh.py"
Task: "T015 setup.ps1 的 E2E 測試 in tests/e2e/test_setup_ps1.py"

Task: "T018 實作 tools/setup.sh"
Task: "T019 實作 tools/setup.ps1"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 與 Phase 2
2. 完成 Phase 3（US1）
3. 停下來驗證：在暫存家目錄以開機腳本完成全新安裝
4. 注意：只有 US1 時，遇到既有的同名檔案還沒有保護；在真正的 `~/.claude` 使用前 MUST 先完成 US3

### Incremental Delivery

1. Setup 加 Foundational
2. US1：全新安裝
3. US2：更新與冪等
4. US3：衝突保護，之後才可在真正的家目錄使用
5. US4：移除與還原
6. Polish：文件、quickstart 驗證、兩個平台的 CI

## Notes

- 每完成一個任務或一組相關任務就 commit
- `home/` 的實際內容由 002 至 008 提供；本功能的測試一律使用 fixture 內容
- repo 位址尚未決定，開機腳本以常數保存，T037 的 README 以佔位標示
