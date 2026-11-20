---

description: "Task list for 004 sdd-update 更新 Spec Kit"
---

# Tasks: sdd-update 更新 Spec Kit

**Input**: Design documents from `/specs/004-sdd-update/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/cli.md、contracts/skill.md、quickstart.md；
共用 [003 的設計文件](../003-sdd-init/)（data-model.md、contracts/cli.md）與 `home/skills/sdd-init/scripts/sdd_init.py`

**Tests**: 需要。Constitution（v1.0.1）原則 II 要求每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
每個 user story 先寫測試並確認失敗，再實作。測試指令是 `uv run --with pytest pytest`；
本機離線時以 `uv run --with pytest pytest -m "not network"` 只跑不需要網路的測試。

**Organization**: 依 user story 分組。更新的邏輯都在同一支 `home/skills/sdd-update/scripts/sdd_update.py`，
單元測試都在同一份 `tests/unit/test_sdd_update.py`，改同一個檔案的任務依編號依序進行。
plan.md「需要維護者注意的取捨」的 10 項已由維護者全部核可，本清單照 plan 的寫法，不再確認。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、沒有未完成的相依）
- **[Story]**: 所屬的 user story（US1 至 US3）
- 路徑相對於 repo 根目錄
- 「data-model.md」未加路徑時指 `specs/004-sdd-update/data-model.md`；003 的檔案一律寫出 `specs/003-sdd-init/` 前綴

## 所有任務共同的限制

- 實作與驗證 MUST NOT 讀寫真正的家目錄 `~/.claude`，也 MUST NOT 把這個 skill 部署到那裡。
- MUST NOT 在這個 repo 自己的目錄執行 `sdd_init.py` 或 `sdd_update.py`（包含 `init`、`remove`、更新）。
  這個 repo 既有的 `.specify/` 是另一個工具留下的（其中的 `sdd-init.json` 格式與本功能的紀錄不同），MUST NOT 修改或刪除。
- 所有實際執行（測試、整合測試、quickstart 情境）都在暫存目錄進行：pytest 用 `tmp_path`，手動情境用 `mktemp -d` 建立的目錄；
  fixture 與子程序把 `HOME` 與 `USERPROFILE` 指向暫存目錄。
- 可以修改的檔案只有本清單點名的檔案；MUST NOT 修改 `specs/003-sdd-init/` 的 `spec.md`、`plan.md`、`tasks.md`，
  也 MUST NOT 修改 `specs/004-sdd-update/` 的 `spec.md`、`plan.md` 與其他設計文件（`tasks.md` 的勾選除外）。
- 設計文件沒有寫明、而測試需要逐字比對的地方，不自行決定，向主代理提問。
- 實作的 worker 不 push；需要推送才能確認的工作只有 T047。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認既有基礎可用，備妥測試 fixture

- [X] T001 確認 `home/skills/sdd-init/scripts/sdd_init.py`、`tests/unit/test_sdd_init.py`、`tests/integration/test_sdd_init_real.py`、`tests/e2e/test_cross_platform.py`、`tests/conftest.py` 與 `.github/workflows/ci.yml` 已存在，`uv`、`git`、`bash` 都在 `PATH` 上，且 `uv run --with pytest pytest` 在目前的分支全部通過（`tests/unit/test_claude_md.py` 中「引用的 skill 資料夾存在」一項跳過是預期的）；記下通過的測試數，供 T008 比對
- [X] T002 [P] 擴充 `tests/conftest.py`（不改動既有的 fixture 與輔助函式）：新增以模組方式載入 `home/skills/sdd-update/scripts/sdd_update.py` 的 session fixture（檔案不存在時由使用它的測試失敗，不是 conftest 載入失敗）；新增「兩個版本的假官方產出」輔助函式（舊版與新版：兩版都有、內容不同的 `.claude/skills/speckit-*/SKILL.md` 與 `.specify/templates/` 範本；兩版都有、內容不同的 `.specify/scripts/bash/*.sh`；只有舊版有的 `.claude/skills/speckit-legacy/SKILL.md`；只有新版有的 `.specify/scripts/bash/markdown_sections.py` 與一支新的 `.sh`；兩版相同的檔案；`.specify/memory/constitution.md`；含各自 `speckit_version` 的 `.specify/init-options.json`），並提供可替換「執行官方工具」的假函式，能依要求的版本寫出對應的產出；新增「以指定的舊版導入專案」輔助函式，在行程內呼叫 `sdd_init.main(["init"], resolve_version=<回傳指定版本的函式>, run_official=<假函式或真的官方工具>)`（官方工具實際執行的版本只用於整合與跨平台測試）；新增在子程序執行 `sdd_update.py` 的輔助函式（沿用既有 `real_run_env` 與 `find_bash`）；既有的暫存專案 fixture 保持原樣可用

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 對 003 產出的共用變更（plan.md「取捨」第 3 項，research.md R6），以及 `sdd_update.py` 的骨架：載入共用程式、版本比較、比對副本的路徑對應、輸出

**⚠️ CRITICAL**: 這個階段完成前不能開始任何 user story

### 對 003 產出的共用變更（會修改 003 的產出）

- [X] T003 在 `tests/unit/test_sdd_init.py` 增補共用變更的測試（既有的測試不改動），確認在 T004 至 T006 實作前失敗：(a) 紀錄的 `entries[].origin` 接受 `sdd-update`（data-model.md `Record.entries[].origin`），其 `path` 位於 `.specify/sdd-update/` 之下且以 `.new` 結尾、`staged_executable` 為 false 時紀錄有效；`origin` 為 `sdd-update` 但路徑不在 `.specify/sdd-update/` 之下、不以 `.new` 結尾，或 `staged_executable` 為 true，以及其他 `origin` 的項目位於 `.specify/sdd-update/` 之下，都被判為無效紀錄（`init` 結束碼 1、`remove` 不刪除任何檔案，與不認得的 `schema` 相同）；`schema` 仍為 1，序列化後鍵值順序與排序規則不變；(b) 紀錄為 `complete`、檔案齊全，但 `origin` 為 `sdd-update` 的檔案不存在時，`init` 仍輸出 `is already initialized. Nothing changed.`、不連線、不執行官方工具、零異動；`origin` 為 `speckit` 的檔案缺少時仍然補齊；(c) `remove` 對內容未變的 `origin: sdd-update` 項目刪除（`deleted` 行）、內容被改過的保留（`kept … (modified since init)`），並刪除因此變空且在 `created_dirs` 內的 `.specify/sdd-update/` 目錄；(d) 既有情境的輸出逐字不變由 T008 以既有測試確認
- [X] T004 在 `home/skills/sdd-init/scripts/sdd_init.py` 變更一：紀錄讀取、驗證與寫入接受 `entries[].origin` 為 `sdd-update`，並依 data-model.md 的「新增的規則」驗證其路徑與 `staged_executable`（`Record.entries[].origin`、`Record.entries[].staged_executable`）；`schema` 維持 1；其餘驗證規則不變
- [X] T005 在 `home/skills/sdd-init/scripts/sdd_init.py` 變更二：`init` 判斷「已完整導入」與補齊時，不要求 `origin` 為 `sdd-update` 的檔案存在，也不為它們重新執行官方工具（`Record.status`、`Record.entries[].origin`）
- [X] T006 在 `home/skills/sdd-init/scripts/sdd_init.py` 變更三：把 init 內「建立 `.specify/.gitattributes`」（含 `.sh` 的 `eol` 檢查與 `warning` 行）與少數寫死 `/sdd-init` 的訊息整理成可由 sdd-update 呼叫的函式（函式名稱與參數由實作者決定，只需讓 `sdd_update.py` 能呼叫）；sdd-init 的 SKILL.md、README.md、指令介面、結束碼與既有情境的輸出一個字都不變
- [X] T007 [P] 更新 003 的設計文件，**只動** `specs/003-sdd-init/data-model.md` 與 `specs/003-sdd-init/contracts/`，不動 `specs/003-sdd-init/spec.md`、`plan.md`、`tasks.md`：`specs/003-sdd-init/data-model.md` 的 `entries[].origin` 欄位（目前為 `"speckit"` \| `"sdd-init"`）改為多一個值 `"sdd-update"` 並說明其路徑規則（沿用 data-model.md「對 003 格式的變更」）；「已完整導入」的條件改為不要求 `origin` 為 `sdd-update` 的檔案存在；`specs/003-sdd-init/contracts/cli.md` 中與「已完整導入」判定與 `origin` 有關的敘述同步更新（只改這兩處，不改其他內容）；`specs/003-sdd-init/contracts/skill.md` 只在有提到上述兩項時才更新，沒有就不動
- [X] T008 確認既有的 003 測試在 T004 至 T007 之後繼續通過：執行 `uv run --with pytest pytest tests/unit/test_sdd_init.py tests/unit/test_sdd_init_skill.py tests/integration/test_sdd_init_real.py tests/e2e`，T001 記下的既有測試都通過，T003 的新測試也通過；`git diff` 確認 `specs/003-sdd-init/` 只有 `data-model.md` 與 `contracts/` 有變動，`home/skills/sdd-init/` 只有 `scripts/sdd_init.py` 有變動

### `sdd_update.py` 骨架

- [X] T009 建立 `tests/unit/test_sdd_update.py` 並加入核心測試，確認在 T010、T011 實作前失敗：以模組方式載入時不執行任何動作、不連線、不載入 `sdd_init.py` 以外的任何東西；載入的是相鄰的 `home/skills/sdd-init/scripts/sdd_init.py`（`<本檔>/../../../sdd-init/scripts/sdd_init.py`）；找不到它時結束碼 1，stdout 只有 `Spec Kit was not updated: the sdd-init skill is not installed next to sdd-update. Nothing was changed.`，專案內零異動；出現任何參數時結束碼 1、stderr 為 `usage: sdd_update.py`；結束碼常數沿用 003（0、1、3、4），沒有新增；版本比較依 data-model.md「版本」的規則（取開頭的數字段、逐段整數比較、長度不足補 0；`1.5.0rc1` 取 `(1, 5, 0)`；`1.4.3rc1` 對 `1.4.3` 視為較舊的數字段相同而照常更新）；比對副本的路徑雙向對應（`<P>` ↔ `.specify/sdd-update/<P>.new`，`<P>` 包含開頭的 `.`）；`.specify/memory/` 之下的路徑被判為受保護；官方產出含 `.specify/sdd-update/` 之下的路徑或紀錄本身時視為官方工具失敗（結束碼 4）
- [X] T010 建立 `home/skills/sdd-update/scripts/sdd_update.py` 骨架：uv inline metadata（`requires-python = ">=3.11"`、`dependencies` 為空）；只用標準函式庫；執行時以 `importlib` 載入相鄰的 `sdd_init.py`（MUST NOT 複製其內容，MUST NOT 自行實作紀錄的讀寫、雜湊、版本挑選與必要工具的判定）；找不到時依 contracts/cli.md 結束碼 1；參數檢查；`main()` 以關鍵字參數接受「查詢版本」與「執行官方工具」兩個可替換的函式，不提供環境變數或隱藏選項；被載入為模組時不執行任何動作（contracts/cli.md「指令」「結束碼」「只為測試存在的入口」，contracts/skill.md「scripts/sdd_update.py」）
- [X] T011 在 `home/skills/sdd-update/scripts/sdd_update.py` 實作共用的小函式：版本比較與 data-model.md「版本」的四種判定（依序：比最新穩定版還新、已是最新穩定版、被中斷的導入、更新）；比對副本的路徑對應；受保護路徑的判斷；輸出一行的格式（沿用 `sdd_init.py` 的動作行格式：動作名稱靠左補滿 10 個字元）

**Checkpoint**: 骨架就緒，003 的既有測試通過；可以開始 user story

---

## Phase 3: User Story 1 - 把專案的 Spec Kit 更新到最新版 (Priority: P1) 🎯 MVP

**Goal**: `/sdd-update` 把由 sdd-init 導入且未被修改的專案更新到最新穩定版：取代、建立、移除，回報版本變化；已是最新版時零異動；所有停止的情況零寫入；skill 資料夾完成

**Independent Test**: 以較舊的版本導入暫存專案，不修改任何檔案後執行更新，所有 Spec Kit 檔案都變成新版，回報的版本變化與檔案清單符合 contracts/cli.md

### Tests for User Story 1 ⚠️

> 先寫測試並確認失敗，再實作。T012 至 T019 都以兩個版本的假官方產出與替換的「查詢版本」「執行官方工具」函式進行，不需要網路

- [X] T012 [US1] 在 `tests/unit/test_sdd_update.py` 加入全新更新（沒有任何檔案被修改）的測試：以舊版導入後更新到新版，結束碼 0；內容不同的檔案以位元組原樣換成新版內容並各有一行 `updated`；新版才有的檔案建立並各有一行 `created`；不再提供且未被修改的檔案刪除並各有一行 `removed`，因刪除而變空、且在 `created_dirs` 內的目錄一併刪除並從 `created_dirs` 移除；兩版相同的檔案不寫入（mtime 不變）、不列出、不計數；各段依 `updated`、`created`、`removed` 的順序輸出，段內依路徑排序，路徑一律以 `/`；摘要第一行逐字為 `Spec Kit updated from <舊版> to <新版>: <u> updated, <c> created, <r> removed, 0 kept.`，四個數字等於各動作的行數；沒有任何 `kept` 行與 `Next:` 行；暫存產出的目錄在結束後不存在；`.specify/memory/` 內容、`specs/` 內容與專案內不在紀錄內的檔案位元組與 mtime 都不變（FR-001、FR-003、FR-004、FR-006、FR-007、SC-004，data-model.md「更新的動作」的 `create`、`same`、`update`、`remove`）
- [X] T013 [US1] 在 `tests/unit/test_sdd_update.py` 加入紀錄改寫的測試：更新完成後 `.specify/sdd-init.json` 的 `speckit_version` 為新版、`status` 為 `complete`（`Record.speckit_version`、`Record.status`）；`create`、`update`、`same`（原本在紀錄內者）的項目 `sha256` 為新版內容的雜湊（`Record.entries[].sha256`）；`remove` 與 `forget` 的項目從紀錄移除；`.specify/memory/` 下的項目與 `.specify/.gitattributes`（`origin: sdd-init`）的項目不變；新建立的目錄加入 `created_dirs`；`entries` 依 `path` 排序，不含絕對路徑與時間戳，位元組為 UTF-8 與 LF；更新後以 `sdd_init` 的 `remove` 能依紀錄正確刪除未修改的檔案；紀錄中 `staged_executable` 與 `origin` 的值依 data-model.md「各種項目在更新後的 `sha256`」（FR-009，`Record.entries[].origin`）
- [X] T014 [US1] 在 `tests/unit/test_sdd_update.py` 加入「不需要更新」的測試：已是最新穩定版（紀錄為 `complete` 且版本相等）時，兩個替換函式中「執行官方工具」沒有被呼叫、目錄快照（含 mtime）與 `git status --porcelain`、`git ls-files -s` 完全相同，stdout 只有 `Spec Kit <版本> is already the latest stable release. Nothing changed.` 一行，沒有 `Git:` 一行，結束碼 0；連續執行 5 次結果相同（SC-005）；紀錄的版本或 `.specify/init-options.json` 的 `speckit_version` 數字段大於最新穩定版時（例如 `1.5.0rc1`）不降版，stdout 為 `Spec Kit <專案的版本> is newer than the latest stable release <最新穩定版>. Nothing changed.`，`<專案的版本>` 是兩個來源中較新的一個、原樣輸出，零異動且不執行官方工具；`init-options.json` 不存在、無法解析或 `speckit_version` 不是字串時視為沒有，只看紀錄（FR-002、FR-008，data-model.md「版本」）
- [X] T015 [US1] 在 `tests/unit/test_sdd_update.py` 加入停止情況的測試（每一項的目錄快照都完全不變，連 `.specify/sdd-update/` 都沒有建立）：缺少 `uv`、`git`、`bash` 中的任何幾個時，每個缺少的工具一行 `missing`（格式與 003 逐字相同），再加 `Missing required tools. Nothing was changed. Install them and run /sdd-update again.`，結束碼 3，兩個替換函式都沒有被呼叫；沒有 `.specify/sdd-init.json`（包含完全沒有 `.specify/`，以及有 Spec Kit 檔案但沒有紀錄）時結束碼 1，stdout 為 `Spec Kit was not updated: this project has no sdd-init record. Run /sdd-init first, then run /sdd-update again.`，不連線；紀錄無法解析、`schema` 不認得、欄位不合規則、路徑違反規則時結束碼 1，stdout 為 `Spec Kit was not updated: .specify/sdd-init.json cannot be used. Nothing was changed.`，stderr 第一行以 `error: .specify/sdd-init.json is not a record this version of ` 開頭並含具體原因（stderr 其餘文字只檢查含原因與處理方式，不逐字比對）；紀錄為 `applying` 且版本等於最新穩定版時結束碼 1，stdout 為 `Spec Kit was not updated: the setup by /sdd-init was interrupted. Run /sdd-init to finish it, then run /sdd-update again.`；查詢版本失敗、官方工具以非零結束、產出的 `.specify/init-options.json` 的 `speckit_version` 與要求的版本不符，或產出含 `.specify/sdd-update/` 之下的路徑或紀錄本身時，結束碼 4，stdout 為 `Could not get the latest stable Spec Kit release: <原因>. Nothing was changed. Check the network connection and run /sdd-update again.`；兩個替換函式各只被呼叫一次（不重試）；暫存產出的目錄已刪除（FR-011，contracts/cli.md「停止」）
- [X] T016 [US1] 在 `tests/unit/test_sdd_update.py` 加入 `.sh` 與暫存區的測試：在 git repository 更新後，新建立的 `.sh` 每支一行 `staged … (executable bit recorded in the git index)`，`git ls-files -s` 顯示 100755（在 `core.fileMode=false` 的 repository 也成立），`staged_executable` 為 true；被取代的既有 `.sh` 不加入暫存區、index 內既有的項目不改寫（已以 100755 提交的仍是 100755）、不輸出 `staged`，工作目錄的檔案模式與暫存產出相同（Linux）；003 定義的「待補登的 `.sh`」（紀錄內 `origin` 為 `speckit`、`staged_executable` 為 false、檔案存在且不在 index 也不在 `HEAD`）一併補登；被刪除且 `staged_executable` 為 true、仍在 index 且不在 `HEAD` 的 `.sh` 以 `git rm --cached` 取消；HEAD 與 commit 數、分支不變；`Git:` 一行的第一種與第二種形式逐字符合 contracts/cli.md（`<n>` 等於 `staged` 的行數）；`git add --chmod=+x` 失敗時 stderr 一行 `note: <路徑> was not added to the git index: <原因>`、不輸出該檔案的 `staged` 行、`staged_executable` 維持 false、結束碼不受影響；不是 git repository 時沒有 `staged` 行，摘要有 `Git: not a git repository, and none was created. Executable bits cannot be recorded until the files are added with: git add --chmod=+x .specify/scripts/bash/*.sh`（與 003 逐字相同），目錄內沒有 `.git`（FR-010，data-model.md「更新的動作」，contracts/cli.md「不變的保證」）
- [X] T017 [US1] 在 `tests/unit/test_sdd_update.py` 加入 `.specify/.gitattributes` 與 `warning` 的測試：`.specify/.gitattributes` 不存在時建立（內容的位元組恰為 `scripts/bash/*.sh text eol=lf` 加一個 LF）、列為 `created`、`origin` 為 `sdd-init`、計入 `<c> created`；已存在就不動、不列出；專案是 git repository 且新版產出的 `.sh` 以 `git check-attr eol` 檢查結果不是 `lf` 時各輸出一行 `warning   <路徑> has no eol=lf rule in git; it will not run after a checkout that converts line endings`，是 `lf` 就不輸出；有警告時結束碼仍為 0；`warning` 行排在 `staged` 之後（FR-010，research.md R3）
- [X] T018 [US1] 在 `tests/unit/test_sdd_update.py` 加入寫入失敗與中斷後重跑的測試：寫入途中（取代檔案、建立檔案、刪除檔案各選一個時間點）拋出例外時結束碼 1，stdout 沒有摘要，stderr 含 `error: writing into the project failed: <原因>` 與 `Some files may already have been updated. Fix the cause, then run /sdd-update again; it finishes the update and never overwrites a file you changed.`，專案內留有 `status` 為 `applying`、版本仍是舊版、`entries` 含原有項目與要新建的檔案的紀錄；取代檔案是先寫同目錄的暫存檔（原檔名加固定後綴）再以 `os.replace` 換上，失敗後不留下寫到一半的原檔；再次執行完成更新，結束後 `status` 為 `complete`、版本為新版，內容與一次完成時相同；那一次的回報只包含它自己做的事（上一次已取代的檔案不再列為 `updated`）；`applying` 且版本小於最新穩定版時與 `complete` 時走相同的流程；中途失敗期間被修改的檔案仍沒有被寫入（FR-011，data-model.md「狀態轉移」「中斷後重新判定為什麼會收斂」）
- [X] T019 [P] [US1] 建立 `tests/unit/test_sdd_update_skill.py`，依 contracts/skill.md 檢查 `home/skills/sdd-update/`：資料夾內只有 `SKILL.md`、`README.md`、`scripts/sdd_update.py`；SKILL.md 的 frontmatter 為 `name: sdd-update`、一句英文的 `description`、`disable-model-invocation: true`，沒有 `argument-hint`；SKILL.md 內文含 `${CLAUDE_SKILL_DIR}/scripts/sdd_update.py`、不接受參數的說明、`MUST NOT` 重試與自行執行 `specify`、不自行合併被保留的檔案與不修改 `.specify/sdd-update/`、不 commit、請維護者執行 `/sdd-init`，且不含中日韓文字、絕對路徑與信箱；README.md 含繁體中文，並提到 `/sdd-update`、`uv`、`git`、`bash`、`.specify/memory/`、`specs/`、`.specify/sdd-update/`、`.new`、`/sdd-init`；腳本開頭有 inline metadata 且 `dependencies` 為空、`requires-python = ">=3.11"`；腳本內沒有 `sdd_init.py` 內容的複本，能從相鄰的 `sdd-init` 載入共用程式（FR-013）
- [X] T020 [P] [US1] 建立 `tests/integration/test_sdd_update_real.py`，整個檔案標記 `network`，網路失敗就是失敗、不自動跳過；只在 `tmp_path` 執行，不碰這個 repo 的 `.specify/` 與真正的 `~/.claude`：以 `sdd_init.main(["init"], resolve_version=lambda: "1.2.6")`（官方工具實際執行）導入並 commit，再以子程序執行 `uv run home/skills/sdd-update/scripts/sdd_update.py`；紀錄與摘要的版本等於測試自行從 PyPI 查到的最新穩定版；更新後的檔案集合與內容等於另一個空目錄直接以最新版導入的結果（涵蓋新增與移除，斷言只比對性質、不比對固定的檔案清單）；紀錄內每個檔案的雜湊相符；以 `bash` 執行 `.specify/scripts/bash/create-new-feature.sh --json --short-name demo "Demo"` 與 `.specify/scripts/bash/setup-plan.sh --json`，結束碼 0；commit 後再執行 5 次，每次輸出 `is already the latest stable release` 且目錄快照與 `git status --porcelain` 不變；整個更新在 2 分鐘內完成（SC-001、SC-004、SC-005，research.md R5）。起點固定為 1.2.6，該版本若被 PyPI 撤回，測試失敗並換起點版本（plan.md「取捨」第 9 項）

### Implementation for User Story 1

- [X] T021 [US1] 在 `home/skills/sdd-update/scripts/sdd_update.py` 實作必要工具的檢查與紀錄讀取：呼叫 `sdd_init.py` 的必要工具判定（`uv`、`git`、`bash`，Windows 只承認 Git Bash，判定方式與 003 完全相同）與紀錄讀取，依 contracts/cli.md「執行順序」第 1 至 3 步與「停止」表處理缺少工具（結束碼 3）、沒有紀錄、紀錄無法使用、被中斷的導入（結束碼 1），全部在任何寫入與任何連線之前
- [X] T022 [US1] 在 `home/skills/sdd-update/scripts/sdd_update.py` 實作查詢版本、版本判定與官方工具執行：呼叫 `sdd_init.py` 共用的「取得最新穩定版」與「執行官方工具並核對版本」（暫存目錄在專案之外，結束時包含失敗都刪除）；依 T011 的判定處理「已是最新穩定版」「比最新穩定版還新」（不執行官方工具、零異動、只輸出一行）；任何失敗結束碼 4，不重試、不改用其他來源；產出的路徑須通過 003 的路徑檢查且不得是紀錄本身或位於 `.specify/sdd-update/` 之下，否則視為官方工具失敗
- [X] T023 [US1] 在 `home/skills/sdd-update/scripts/sdd_update.py` 實作規劃（純讀取，只存在於記憶體）：對暫存產出與紀錄內 `origin` 為 `speckit` 的項目的聯集中、不受保護的每個路徑，依 data-model.md「更新的動作」判定 `create`、`same`、`update`、`remove`、`forget`（`cur == new` 優先於 `cur == rec`；專案內的路徑存在但不是一般檔案時視為與任何雜湊都不同；雜湊先正規化換行）；`.specify/.gitattributes` 不存在時視為一個 `create`；`keep` 與 `keep-orphan` 的處理留給 US2（T033 至 T035），此任務遇到時先以明確的未實作錯誤停止（`Record.entries[].sha256`、`Record.entries[].origin`）
- [X] T024 [US1] 在 `home/skills/sdd-update/scripts/sdd_update.py` 實作寫入：先把紀錄改寫為 `status: applying`、版本仍是原版本、`entries` 為原有項目加上要新建的檔案；再依序建立、取代（先寫同目錄的暫存檔再 `os.replace`，模式設成與暫存產出相同）、刪除（由深到淺刪除 `created_dirs` 中已變空的目錄）；最後寫入 `status: complete`、版本為新版、`entries` 為更新後的結果；內容以官方產出的位元組原樣寫入、不轉換換行；寫入失敗時輸出 contracts/cli.md「寫入失敗」的 stderr 並結束碼 1，不輸出摘要；MUST NOT 讀寫 `.specify/memory/` 與 `specs/`（FR-006、FR-007、FR-009，data-model.md「狀態轉移」，`Record.status`、`Record.speckit_version`）
- [X] T025 [US1] 在 `home/skills/sdd-update/scripts/sdd_update.py` 實作暫存區與 `.specify/.gitattributes`：專案是 git repository 時，對 `create` 的 `.sh` 與 003 定義的待補登的 `.sh` 呼叫 `sdd_init.py` 共用的 `git add --chmod=+x` 函式並把 `staged_executable` 設為 true（失敗時 stderr 一行 `note:`，維持 false）；`update` 的檔案不加入暫存區；`remove` 的 `.sh` 依條件以 `git rm --cached` 取消；`.specify/.gitattributes` 與 `warning` 行呼叫 T006 整理出的共用函式；不 commit、不建立 repository、不對其他檔案執行 `git add`（FR-010，contracts/cli.md「不變的保證」）
- [X] T026 [US1] 在 `home/skills/sdd-update/scripts/sdd_update.py` 完成輸出並串起 T021 至 T025：依 contracts/cli.md「已更新」的順序輸出 `updated`、`created`、`removed`、`kept`（US2 完成）、`staged`、`warning`，各段內依路徑排序；摘要三行（`Spec Kit updated from … to …` 的四個數字、`Git:` 一行的三種形式、`Next:` 一行只在寫入了至少一份比對副本時輸出）；「不需要更新」的輸出；結束碼依 contracts/cli.md；兩個平台輸出逐字相同（FR-003、FR-012）
- [X] T027 [P] [US1] 撰寫 `home/skills/sdd-update/SKILL.md`（英文）：frontmatter 與內文的六項指示依 contracts/skill.md「SKILL.md」，包含不接受參數（維護者輸入參數時說明不能指定版本或降版、不執行任何指令）、只執行一次、完整回報輸出（`kept` 連同比對副本的路徑）、非零結束碼與 `uv` 不存在時回報原因與處理方式後停止（不重試、不自行執行 `specify`、不手動建立或修改 `.specify/` 與 `speckit-*` 的檔案、要求先執行 `/sdd-init` 時請維護者執行而不是自己執行）、不自行合併被保留的檔案、不修改或刪除 `.specify/sdd-update/` 下的比對副本、不 commit、不 push；內文不含中日韓文字、絕對路徑與信箱
- [X] T028 [P] [US1] 撰寫 `home/skills/sdd-update/README.md`（繁體中文）：內容依 contracts/skill.md「README.md」的六項（用法與不能指定版本、前置需求與與 `sdd-init` 一起部署、更新／建立／移除／保留的範圍、永遠不動的 `.specify/memory/` 與 `specs/`、比對副本的位置與生命週期、git 暫存區的行為）
- [X] T029 [US1] 確認 US1 的測試通過：`uv run --with pytest pytest tests/unit/test_sdd_update.py tests/unit/test_sdd_update_skill.py tests/unit/test_sdd_init.py -m "not network"` 中 T009 至 T019 與 003 的既有測試全部通過；`tests/integration/test_sdd_update_real.py` 的實際執行（T020）只在暫存目錄進行，通過

**Checkpoint**: `/sdd-update` 可在單一平台更新未被修改的專案；已是最新版與所有停止情況零異動

---

## Phase 4: User Story 2 - 保留維護者的修改與專案內容 (Priority: P1)

**Goal**: 被修改過的 Spec Kit 檔案保留不動並附新版供比對；constitution 與 `specs/` 完全不變；合併後不重複列出

**Independent Test**: 導入後寫入 constitution、新增一份 spec、修改一個範本，再執行更新，這三者內容不變，被修改的範本附有新版內容的比對副本

### Tests for User Story 2 ⚠️

> 先寫測試並確認失敗，再實作

- [X] T030 [US2] 在 `tests/unit/test_sdd_update.py` 加入保留被修改檔案的測試：紀錄內且內容與紀錄不同的檔案（`keep`）內容與 mtime 不變，不加入暫存區，輸出 `kept      <路徑> (modified; new version: .specify/sdd-update/<路徑>.new)`；比對副本內容為新版官方產出的位元組、模式為一般檔案、不設定執行權限、不加入暫存區；比對副本一筆列入紀錄（`origin` 為 `sdd-update`、`sha256` 為副本內容的雜湊、`staged_executable` 為 false），所在的新目錄列入 `created_dirs`；被保留檔案的 `sha256` 改為新版內容的雜湊（之後仍是被修改）；其餘未修改的檔案照常 `updated`；摘要第一行的 `<k> kept` 等於 `kept` 的行數；摘要最後一行為 `Next: compare each kept file with its .new copy under .specify/sdd-update/, merge what you want, then delete the copies.`；`kept` 段內依路徑排序，位於 `removed` 之後、`staged` 之前（FR-005、SC-003，data-model.md「比對副本」「各種項目在更新後的 `sha256`」，`Record.entries[].origin`、`Record.entries[].sha256`）
- [X] T031 [US2] 在 `tests/unit/test_sdd_update.py` 加入「不是由 sdd-init 導入」與「不再提供」的測試：新版提供、專案內存在、不在紀錄內且內容不同的檔案，輸出 `kept … (not created by sdd-init; new version: <比對副本的路徑>)`、寫比對副本、檔案不列入紀錄；內容與新版相同的同類檔案不列出、不寫入、仍不在紀錄內；新版不再提供、紀錄內且內容被修改的檔案，輸出 `kept … (modified; no longer part of Spec Kit <新版本>)`、沒有比對副本、從紀錄移除；新版不再提供、紀錄內但專案內已不存在的檔案只從紀錄移除、不列出；維護者刪掉的 Spec Kit 檔案（新版仍提供）被重新建立；不在紀錄內、新版也不提供的檔案完全不看、不碰；專案內的路徑是目錄或符號連結時視為被修改；紀錄內的 `speckit_version` 為舊版時 `/sdd-init` 之後緊接 `/sdd-update` 的情況（紀錄版本等於最新穩定版）回報已是最新版，不比對既有檔案（plan.md「取捨」第 5 至 8 項，data-model.md「更新的動作」，research.md R2 的「限制」）
- [X] T032 [US2] 在 `tests/unit/test_sdd_update.py` 加入專案內容與比對副本管理的測試：改寫過的 `.specify/memory/constitution.md`、仍是空白範本的 constitution、`.specify/memory/.constitution-template.json`、`specs/` 內多份文件在更新前後位元組與 mtime 完全相同，輸出沒有任何與它們有關的行，紀錄內 `.specify/memory/` 下的項目原樣保留（即使新版的 constitution 內容不同，FR-006、SC-002，plan.md「取捨」第 4 項）；上一次更新留下的比對副本在下一次實際更新開始時全部被刪除（不論內容是否被改過）再寫入這一次的，其項目從紀錄移除再重新列入；維護者先刪掉比對副本時更新不失敗；要寫入比對副本的路徑上已有不在紀錄內的檔案，或要建立的檔案的某個上層路徑存在但不是目錄時，規劃階段就停止，結束碼 1，stdout 為 `Spec Kit was not updated: <路徑> is in the way. Nothing was changed. Move it away and run /sdd-update again.`，`<路徑>` 是依路徑排序的第一個，專案內零異動且不寫任何比對副本
- [X] T033 [US2] 在 `tests/unit/test_sdd_update.py` 加入已是最新穩定版時「不重複列出」的測試：有比對副本且專案檔案仍與之不同（換行正規化後的雜湊）時，輸出每個檔案一行 `kept      <路徑> (still differs from Spec Kit <版本>; new version: <比對副本的路徑>)`，再接 `Spec Kit <版本> is already the latest stable release. Nothing changed.`，最後一行為與「已更新」逐字相同的 `Next:` 行，專案內零異動（檔案與 index）、不執行官方工具；維護者把比對副本的內容複製到專案檔案後（包含換行為 CRLF 的情況）不再列出，只輸出最新版那一行；比對副本被刪除、或專案檔案不存在時不列出；連續執行多次輸出相同且比對副本留在原處（不清理，plan.md「取捨」第 1 項）；比對副本在 `git status` 中是未追蹤檔案，不加入暫存區、不寫任何 ignore 規則（plan.md「取捨」第 2 項，data-model.md「比對副本」的「仍待合併」，FR-008）
- [X] T034 [US2] 在 `tests/unit/test_sdd_update.py` 加入兩個平台對等的測試：把專案的所有文字檔改寫成 CRLF（模擬經 git 到 Windows）後執行更新，未被修改的檔案仍被判為未修改而更新，被判為被修改的集合與 LF 時相同；stdout 與紀錄內都沒有反斜線；同一組假產出在兩個不同的暫存目錄更新，stdout 逐字相同、紀錄位元組相同（FR-012，research.md R2）

### Implementation for User Story 2

- [X] T035 [US2] 在 `home/skills/sdd-update/scripts/sdd_update.py` 完成規劃的 `keep` 與 `keep-orphan`：依 data-model.md「更新的動作」判定（`cur != rec`、不在紀錄內、新版不再提供且被修改）、決定 `kept` 一行括號內三種文字之一，並產生比對副本的路徑；比對副本路徑上已有不在紀錄內的檔案、或要建立的檔案的某個上層路徑不是目錄時視為衝突，規劃階段停止並輸出 contracts/cli.md 的衝突訊息（結束碼 1，零寫入）；`.specify/memory/` 之下的路徑完全排除（取代 T023 的未實作錯誤）
- [X] T036 [US2] 在 `home/skills/sdd-update/scripts/sdd_update.py` 完成寫入的比對副本部分：實際更新開始時先刪除紀錄內全部的比對副本，再原樣寫入這一次的（一般檔案、不設定執行權限、不加入暫存區），所在的新目錄列入 `created_dirs`，每份一筆 `origin: sdd-update`；被保留的檔案從頭到尾不寫入；`applying` 階段的紀錄含新的比對副本（FR-005、FR-006，data-model.md「比對副本」）
- [X] T037 [US2] 在 `home/skills/sdd-update/scripts/sdd_update.py` 完成「已是最新穩定版」時仍待合併的列出：只讀取，對紀錄內每一份仍存在的比對副本，專案檔案存在且（換行正規化後）雜湊不同才輸出 `still differs from` 一行，之後輸出最新版那一行與 `Next:` 一行；沒有待合併的檔案時只輸出最新版那一行；MUST NOT 寫入或清理任何東西（FR-008，contracts/cli.md「不需要更新」）
- [X] T038 [US2] 確認 US2 的測試通過：`uv run --with pytest pytest tests/unit/test_sdd_update.py -m "not network"` 中 T030 至 T034 全部通過，US1 的測試沒有退步

**Checkpoint**: US1 與 US2 在單一平台完整可用；本機的單元測試通過

---

## Phase 5: User Story 3 - 更新後兩個平台仍可直接使用 (Priority: P2)

**Goal**: 更新並提交後，另一個平台取得即可執行 Spec Kit 流程，不需要再次更新或導入；兩個平台的更新結果與輸出相同

**Independent Test**: CI 的跨平台 job 在兩個方向都通過（T047）；本機以 `core.autocrlf=true` clone 更新並提交的 repository 後直接執行 Spec Kit 腳本成功

### Tests for User Story 3 ⚠️

> 先寫測試並確認失敗，再實作

- [X] T039 [US3] 在 `tests/integration/test_sdd_update_real.py` 加入實際執行 Spec Kit 腳本的測試（標記 `network`，只在 `tmp_path` 進行）：以 1.2.6 導入並 commit，刪掉一支 `.sh` 並 commit、修改一份範本並 commit，執行更新後 `git add -A` 並 commit；以 `git clone -c core.autocrlf=true` 得到第二份工作目錄，確認其中的 `.sh` 是 LF 且 `git ls-files -s` 為 100755（包含內容被取代的 `common.sh`、`create-new-feature.sh` 與重新出現的那支 `.sh`），`markdown_sections.py` 之類的非 `.sh` 為 100644，再以 `bash` 執行 `create-new-feature.sh --json --short-name demo "Demo"` 與 `setup-plan.sh --json`，結束碼 0 並產生 `specs/001-demo/plan.md`（US3 情境 1，SC-006，research.md R3 與實測紀錄第 11、12 項）
- [X] T040 [P] [US3] 建立 `tests/e2e/test_cross_platform_update.py`：只在 CI 的跨平台 job 執行，以該 job 設定的環境變數判斷（沿用 `tests/e2e/test_cross_platform.py` 的做法與同一組變數名稱，兩個測試檔共用 `.github/workflows/ci.yml` 設定的變數），沒有設定時以 skip 跳過並說明原因。「產出」：在暫存目錄 `git init`、以 1.2.6 導入並 commit、刪除一支 `.sh` 並 commit、修改一份範本並 commit、執行 sdd-update、`git add -A` 後 commit，以 `git bundle` 打包並寫出依路徑排序且含檔案模式的檔案清單與 sdd-update 的 stdout；「驗證」：clone 另一個平台的 bundle（Windows 一側明確設定 `core.autocrlf=true`），不做任何額外步驟就以 `bash` 執行 `create-new-feature.sh` 與 `setup-plan.sh` 成功，並比對兩個平台更新後的檔案清單（含模式）與 sdd-update 的輸出相同（US3 情境 1、2，SC-006，research.md R5）

### Implementation for User Story 3

- [X] T041 [US3] 在 `.github/workflows/ci.yml` 擴充既有的 `cross-platform-produce` 與 `cross-platform` 兩個 job，不新增 job、不改 `test` job：兩個 job 都多執行一個測試檔 `tests/e2e/test_cross_platform_update.py`（`shell: bash`，兩個平台指令相同）；update 的 bundle、檔案清單與輸出放進同一個 artifact（與 sdd-init 的 artifact 並存，不覆蓋既有檔案），「驗證」步驟下載另一個平台的 artifact；必要的檢查仍是 `test`、`cross-platform-produce`、`cross-platform` 三個，各兩個平台（plan.md「Structure Decision」，research.md R5）
- [X] T042 [US3] 確認 US3 在本機可驗證的部分：`uv run --with pytest pytest tests/integration/test_sdd_update_real.py` 全部通過（含 T039）；`tests/e2e/test_cross_platform_update.py` 在本機未設定環境變數時跳過並說明原因；`.github/workflows/ci.yml` 的 YAML 可被解析，且三個 job 名稱與矩陣不變；兩個平台的實際結果待 T047 以 CI 確認

**Checkpoint**: 本機的單元與整合測試通過；跨平台的結果待 T047

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 文件、實跑驗證與 CI

- [X] T043 [P] 更新 `README.md`（繁體中文）：「目前狀態」加入 `sdd-update` 已提供，並加入 `/sdd-update` 的簡短說明與前置需求（`uv`、`git`、`bash`，Windows 的 `bash` 是 Git Bash；專案已由 `/sdd-init` 導入）；只改與本功能有關的敘述
- [X] T044 依 `specs/004-sdd-update/quickstart.md`「手動情境（腳本）」的 9 個情境，在 `mktemp -d` 建立的暫存目錄逐一實跑 `uv run <repo>/home/skills/sdd-update/scripts/sdd_update.py`，並修正與預期不符之處；每個情境用新的暫存目錄，「以舊版導入」依 quickstart 的方式以 `sdd_init.main(['init'], resolve_version=lambda: '1.2.6')` 準備；MUST NOT 在這個 repo 的目錄或真正的 `~/.claude` 執行，MUST NOT 在這個 repo 自己的 `.specify/` 執行 sdd-init 或 sdd-update。情境 8（無法取得版本）只在能夠只對該次執行隔離網路時實跑（例如 Linux 的 `unshare -rn`），MUST NOT 中斷整台機器的網路，也 MUST NOT 為此在腳本加入環境變數或隱藏選項；無法隔離時在回報中註明未實跑，該行為由 T015 的測試涵蓋
- [X] T045 執行完整測試 `uv run --with pytest pytest`（含 `network`）與 `uv run --with pytest pytest -m "not network"`，兩者全部通過；`tests/e2e/test_cross_platform.py` 與 `tests/e2e/test_cross_platform_update.py` 在本機跳過是預期的；確認 003 的既有測試（T001 記下的數量）沒有失敗或被刪除，`git status` 中這個 repo 既有的 `.specify/` 檔案都沒有被這次的工作更動
- [X] T046 確認 plan.md「需要維護者注意的取捨」的 10 項在實作與測試中都有對應：逐項列出對應的任務或測試（例如第 1、2 項對應 T033，第 3 項對應 T003 至 T007，第 4 項對應 T032，第 5 至 8 項對應 T031，第 9 項對應 T020，第 10 項對應 T018 的說明），缺漏的補上測試；不改動 plan.md
- [ ] T047 **由主代理在推送後處理，實作的 worker 不執行這一項、不 push**：推送分支後確認 `.github/workflows/ci.yml` 的 `test`、`cross-platform-produce`、`cross-platform` 三個 job 在 `ubuntu-latest` 與 `windows-latest` 都通過（共六個結果）；Windows 與跨平台的行為以 CI 結果為準，失敗時依紀錄修正後再確認

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依賴 001 至 003 已完成
- **Foundational (Phase 2)**: 依賴 Setup；T003 的測試先於 T004 至 T006；T007 可與 T004 至 T006 平行；T008 依賴 T003 至 T007；
  T009 先於 T010、T011，且依賴 T008（骨架載入的是修改後的 `sdd_init.py`）
- **US1 (Phase 3)**: 依賴 Foundational
- **US2 (Phase 4)**: 依賴 US1（在規劃與寫入上增加 `keep`、`keep-orphan` 與比對副本）
- **US3 (Phase 5)**: 依賴 US1 與 US2（驗證完整的更新流程）
- **Polish (Phase 6)**: 依賴 US1 至 US3；T047 依賴 T045，且需要在推送之後由主代理處理

### Within Each User Story

- 測試先寫並確認失敗，再實作
- `home/skills/sdd-update/scripts/sdd_update.py`、`tests/unit/test_sdd_update.py`、`tests/integration/test_sdd_update_real.py`、
  `home/skills/sdd-init/scripts/sdd_init.py`、`tests/unit/test_sdd_init.py` 各是單一檔案，改同一個檔案的任務依編號依序進行
- 修改 003 產出的任務是 T003、T004、T005、T006、T007，其餘任務不得修改 003 的檔案

### Parallel Opportunities

- T002 可與 T001 平行
- T007 可與 T004 至 T006 平行（不同檔案）
- T019、T020 可與 T012 至 T018 平行（不同檔案）
- T027、T028 可與 T021 至 T026 平行
- T040 可與 T039、T041 平行
- T043 可與 T044 平行
- 其餘任務集中在 `sdd_update.py` 與 `test_sdd_update.py`，沒有其他平行機會

## Parallel Example: User Story 1

```text
Task: "T019 建立 tests/unit/test_sdd_update_skill.py"
Task: "T020 建立 tests/integration/test_sdd_update_real.py"
Task: "T027 撰寫 home/skills/sdd-update/SKILL.md"
Task: "T028 撰寫 home/skills/sdd-update/README.md"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 與 Phase 2（含對 003 產出的共用變更）
2. 完成 Phase 3（US1）：更新未被修改的專案、已是最新版零異動、停止情況、skill 資料夾
3. 此時遇到被修改的檔案會以明確錯誤停止（T023），不會覆蓋；US2 同為 P1，維護者的修改是否被保留是這個功能能不能被信任的前提，
   所以 US1 與 US2 應在同一個 PR 內完成，不單獨合併 US1

### Incremental Delivery

1. Foundational：003 的共用變更、骨架、版本比較、路徑對應
2. US1：取代、建立、移除、零異動、失敗時零寫入、skill 文件
3. US2：保留被修改的檔案、比對副本、`.specify/memory/` 與 `specs/` 不動、不重複列出
4. US3：跨平台測試與 CI 擴充
5. Polish：README、quickstart 實跑、完整測試、CI（T047）

## Notes

- 每完成一個任務或一組相關任務就 commit；不 push，推送由主代理在維護者授權後進行（T047）
- 人工驗收不列為勾選任務：`quickstart.md`「人工驗收（skill 與跨平台）」的 5 個情境需要真實的 Claude Code session，
  並先以部署工具安裝到測試用的家目錄再開新的 session，其中第 4 項還需要 Windows 與 Linux 兩台機器，
  由維護者在合併並部署後進行；worker 不執行這些情境，也不把這個 skill 部署到真正的 `~/.claude`
- 「Spec Kit 流程」在自動測試中指 `speckit-*` skill 所呼叫的腳本能執行並產出預期的檔案；
  Claude 依 SKILL.md 走完整個對話流程屬於人工驗收
- 可由 worker 在暫存目錄以腳本實跑的情境（quickstart 的 9 個手動情境）仍是一般任務（T044）
- stderr 的文字：設計文件只逐字規定了 stdout 的行；`contracts/cli.md` 的「紀錄無法使用」一行寫成
  `error: .specify/sdd-init.json is not a record this version of … can use: <原因>.`，其中 `…` 沒有寫明是哪個 skill 的名稱，
  所以 T015 只檢查這一行以 `error: .specify/sdd-init.json is not a record this version of ` 開頭並含原因，
  其餘 stderr 只檢查含原因與處理方式；實作時 sdd-update 自己的訊息寫 `sdd-update`，不要求逐字
- T006 要求的共用函式名稱沒有在設計文件中指定，由實作者決定；測試只透過行為驗證（輸出與 003 既有測試逐字不變）
- 這個 repo 既有的 `.specify/` 是另一個工具留下的，本功能的任何任務都不在它上面執行 sdd-init 或 sdd-update
