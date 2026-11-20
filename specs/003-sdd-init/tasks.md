---

description: "Task list for 003 sdd-init 導入 Spec Kit"
---

# Tasks: sdd-init 導入 Spec Kit

**Input**: Design documents from `/specs/003-sdd-init/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/cli.md、contracts/skill.md、quickstart.md

**Tests**: 需要。Constitution 原則 II 要求每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
每個 user story 先寫測試並確認失敗，再實作。測試指令是 `uv run --with pytest pytest`；
本機離線時以 `uv run --with pytest pytest -m "not network"` 只跑不需要網路的測試。

**Organization**: 依 user story 分組。三個 story 的邏輯都在同一支 `home/skills/sdd-init/scripts/sdd_init.py`，
單元測試都在同一份 `tests/unit/test_sdd_init.py`，改同一個檔案的任務依序進行。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、沒有未完成的相依）
- **[Story]**: 所屬的 user story（US1 至 US3）
- 路徑相對於 repo 根目錄

## 所有任務共同的限制

- 實作與驗證 MUST NOT 讀寫真正的家目錄 `~/.claude`，也 MUST NOT 把這個 skill 部署到那裡。
- MUST NOT 在這個 repo 自己的目錄執行 `sdd_init.py init` 或 `remove`。這個 repo 既有的 `.specify/sdd-init.json`
  是另一個工具留下的，格式與本功能的紀錄不同，MUST NOT 修改或刪除它。
- 所有實際執行（測試、整合測試、quickstart 情境）都在暫存目錄進行：pytest 用 `tmp_path`，手動情境用 `mktemp -d` 建立的目錄。
- 實作的 worker 不 push；需要推送才能確認的工作只有 T042。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認既有基礎可用，補齊契約，備妥測試 fixture

- [X] T001 確認 `home/skills/`、`tests/unit/`、`tests/e2e/`、`tests/conftest.py` 與 `.github/workflows/ci.yml` 已存在，`uv`、`git`、`bash` 都在 `PATH` 上，且 `uv run --with pytest pytest` 在目前的分支全部通過（`tests/unit/test_claude_md.py` 中「引用的 skill 資料夾存在」一項跳過是預期的）
- [X] T002 把維護者核可 plan 時補充的三點寫進 `specs/003-sdd-init/contracts/cli.md`（只補這三點，不改其他內容）：(a) init 在「缺少工具」（結束碼 3）與「無法取得最新穩定版或官方工具執行失敗」（結束碼 4）這兩種失敗情況下，摘要只輸出第一行，不輸出 `Git:` 一行與兩行下一步建議；(b) `Git:` 一行的 `<k> paths are uncommitted` 中，k 是本次執行後導入紀錄 `entries` 內的路徑中尚未在 `HEAD` 的數量，不含紀錄 `.specify/sdd-init.json` 本身，也不含專案其他未提交的內容；(c) 紀錄 `.specify/sdd-init.json` 不輸出 `created` 行，也不計入摘要的 `<n> created`。以下任務以「cli.md 補充 (a)(b)(c)」引用
- [X] T003 [P] 擴充 `tests/conftest.py`（不改動既有的 fixture）：以 `pytest_configure` 註冊 `network` 標記；新增以模組方式載入 `home/skills/sdd-init/scripts/sdd_init.py` 的 session fixture；新增建立「假的官方產出」的輔助函式（至少含 2 個 `.claude/skills/speckit-*/SKILL.md`、2 支 `.specify/scripts/bash/*.sh`、1 份 `.specify/templates/` 範本、`.specify/memory/constitution.md` 與含 `speckit_version` 的 `.specify/init-options.json`）；新增暫存專案 fixture（可選擇是否 `git init`，並在該 repository 設定測試用的 `user.name`、`user.email`），fixture 內把 `HOME` 與 `USERPROFILE` 指向暫存目錄，不使用真正的家目錄

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 三個 story 共用的核心：腳本骨架、專案根目錄、內容雜湊、導入紀錄讀寫、輸出格式

**⚠️ CRITICAL**: 這個階段完成前不能開始任何 user story

- [X] T004 建立 `home/skills/sdd-init/scripts/sdd_init.py` 骨架：uv inline metadata（`requires-python = ">=3.11"`、`dependencies` 為空）；只用標準函式庫；參數解析（`init`、`remove`，沒有子指令或有未知參數時顯示用法並以結束碼 1 結束）；結束碼常數 0、1、3、4；`main()` 以函式參數接受「查詢版本」與「執行官方工具」兩個可替換的步驟，不提供環境變數或隱藏選項；被載入為模組時不執行任何動作（contracts/cli.md「指令」「結束碼」「只為測試存在的入口」，contracts/skill.md「scripts/sdd_init.py」）
- [X] T005 建立 `tests/unit/test_sdd_init.py` 並加入核心的測試，確認在 T006 至 T008 實作前失敗：參數錯誤時結束碼 1 且顯示用法；專案根目錄的判定（在 git 工作目錄的子目錄內執行時是最上層，否則是目前目錄）；內容雜湊把 CRLF 換成 LF 後計算，同一內容的 LF 與 CRLF 版本雜湊相同，其他位元組差異雜湊不同；紀錄寫入後再讀取內容相同、位元組為 UTF-8 與 LF、鍵值順序固定、`entries` 依 `path` 排序、不含絕對路徑與時間戳；無法解析、`schema` 不認得、路徑不在 `.specify/` 或 `.claude/skills/speckit-*/` 之下的紀錄都被判為無效（data-model.md「導入紀錄」「內容識別資訊」）
- [X] T006 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作專案根目錄的判定與內容雜湊；所有相對路徑一律以 `/` 分隔（data-model.md 開頭與「內容識別資訊」）
- [X] T007 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作導入紀錄 `.specify/sdd-init.json` 的讀取、驗證與寫入，欄位與規則依 data-model.md 的 `Record.schema`、`Record.status`、`Record.speckit_version`、`Record.init_options`、`Record.entries[].path`、`Record.entries[].sha256`、`Record.entries[].origin`、`Record.entries[].staged_executable`、`Record.created_dirs`；讀取結果要能區分「不存在」與「無效」
- [X] T008 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作輸出：stdout 每行一筆的動作行（`created`、`skipped`、`staged`、`warning`、`missing`、`deleted`、`kept`、`unstaged`），各段內依路徑排序，路徑一律用 `/`，文字為英文；錯誤訊息輸出到 stderr（contracts/cli.md「輸出」）

**Checkpoint**: 核心就緒，可以開始 user story

---

## Phase 3: User Story 1 - 在專案導入 Spec Kit (Priority: P1) 🎯 MVP

**Goal**: `init` 導入當下最新穩定版，不覆蓋既有檔案，重複執行零異動，失敗時零寫入；skill 資料夾完成

**Independent Test**: 在暫存的空目錄與已有同名檔案的目錄各執行一次 `init`，檔案齊全、既有檔案不變、回報內容符合 contracts/cli.md

### Tests for User Story 1 ⚠️

> 先寫測試並確認失敗，再實作。T009 至 T014 都以假的官方產出與替換的「查詢版本」函式進行，不需要網路

- [X] T009 [US1] 在 `tests/unit/test_sdd_init.py` 加入版本挑選的測試：從仿 PyPI 回應的 `releases` 選出最大的穩定版；排除帶 `a`、`b`、`rc`、`dev`、`post` 後綴的版本；排除檔案全部被 yank 或沒有檔案的版本；依數值比較（`1.10.0` 大於 `1.9.0`）；沒有符合的版本時視為失敗（FR-002，research.md R3）
- [X] T010 [US1] 在 `tests/unit/test_sdd_init.py` 加入全新導入的測試：結束碼 0；假產出的每個檔案都以位元組原樣出現在專案；每個檔案一行 `created`；紀錄為 `complete`，`speckit_version` 與 `init_options` 正確，`entries` 涵蓋建立的檔案且 `origin` 為 `speckit`，`created_dirs` 只含本次新建的目錄；紀錄本身沒有 `created` 行、不計入 `<n> created`（cli.md 補充 (c)）；摘要第 1 行為 `Spec Kit <版本> initialized: <n> created, <m> skipped.`，第 2 行以 `Git: ` 開頭，第 3、4 行與 contracts/cli.md 的兩行下一步建議逐字相同；不是 git repository 時第 2 行與 contracts/cli.md 的第三種形式逐字相同且目錄內沒有 `.git`；是 git repository 時沒有新的 commit、分支不變；暫存產出的目錄在結束後不存在（FR-001、FR-003、FR-005、FR-007）
- [X] T011 [US1] 在 `tests/unit/test_sdd_init.py` 加入不覆蓋的測試：預先放入內容為 `MINE` 的同名範本與 SKILL.md，導入後內容與 mtime 都不變，各有一行 `skipped … (already exists, left untouched)`，不出現在 `entries`，其餘檔案照常建立，摘要的 `<m> skipped` 正確；沒有紀錄且官方產出的檔案全部已存在時全部列為 `skipped`（FR-004、SC-002，research.md R6）
- [X] T012 [US1] 在 `tests/unit/test_sdd_init.py` 加入重複執行的測試：完整導入後再執行一次，「查詢版本」與「執行官方工具」兩個替換函式都沒有被呼叫，目錄快照（含 mtime）與 `git status --porcelain` 完全相同，stdout 只有一行 `Spec Kit <版本> is already initialized. Nothing changed.`（FR-011，research.md R6）
- [X] T013 [US1] 在 `tests/unit/test_sdd_init.py` 加入中途失敗後補齊與無效紀錄的測試：紀錄為 `applying`，或紀錄為 `complete` 但有檔案不存在時，以**紀錄內的版本**（不查詢最新版）重新產生並只補上缺少的檔案，已存在的檔案不重寫，結束後為 `complete`；複製途中拋出例外時結束碼 1，專案內留有 `applying` 的紀錄，再次執行能補齊；紀錄無法解析、`schema` 不認得或路徑違反規則時結束碼 1、stderr 說明原因、目錄快照完全不變（spec 的邊界情況，research.md R6，data-model.md「狀態轉移」）
- [X] T014 [US1] 在 `tests/unit/test_sdd_init.py` 加入失敗時零寫入的測試：缺少 `uv`、`git`、`bash` 中的任何幾個時，每個缺少的工具一行 `missing`，一次列出全部，結束碼 3；查詢版本失敗、官方工具以非零結束、產出的 `.specify/init-options.json` 的 `speckit_version` 與要求的版本不符時，結束碼 4；這兩類失敗的摘要都只有 contracts/cli.md 表中對應的第一行，沒有 `Git:` 一行與兩行下一步建議（cli.md 補充 (a)）；stderr 含原因與處理方式；目錄快照完全不變（連 `.specify/` 都沒有建立）；替換函式各只被呼叫一次（不重試）；暫存產出的目錄已刪除（FR-010、SC-006，research.md R3、R9）
- [X] T015 [P] [US1] 建立 `tests/unit/test_sdd_init_skill.py`，依 contracts/skill.md 檢查 `home/skills/sdd-init/`：資料夾內只有 `SKILL.md`、`README.md`、`scripts/sdd_init.py`；SKILL.md 的 frontmatter 四個欄位與值；SKILL.md 內文含 `${CLAUDE_SKILL_DIR}/scripts/sdd_init.py`、兩條下一步建議的指令名稱，且不含中日韓文字、絕對路徑與信箱；README.md 含繁體中文，並提到 `/sdd-init`、`/sdd-init remove`、`uv`、`git`、`bash`、`.specify/sdd-init.json`、`.specify/.gitattributes`；腳本開頭有 inline metadata 且 `dependencies` 為空（FR-013）
- [X] T016 [P] [US1] 建立 `tests/integration/test_sdd_init_real.py`，整個檔案標記 `network`，網路失敗就是失敗、不自動跳過：在 `tmp_path` 內 `git init` 的空目錄以子程序執行 `uv run home/skills/sdd-init/scripts/sdd_init.py init`；摘要與紀錄內的版本等於測試自行從 PyPI 查到的最新穩定版；`.specify/scripts/bash/` 有 `.sh`、沒有 `.specify/scripts/powershell/`；`.claude/skills/` 下有 `speckit-*` 的 SKILL.md；再執行一次輸出 `is already initialized` 且目錄快照不變；整個導入在 2 分鐘內完成（SC-001）。只在 `tmp_path` 執行，不碰這個 repo 的 `.specify/` 與真正的 `~/.claude`（research.md R4）

### Implementation for User Story 1

- [X] T017 [US1] 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作必要工具的檢查：`uv`、`git`、`bash`，一次列出全部缺少的項目後以結束碼 3 結束，在任何寫入之前進行；摘要依 cli.md 補充 (a) 只輸出第一行（research.md R9）
- [X] T018 [US1] 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作「查詢版本」：以標準函式庫讀取 `https://pypi.org/pypi/specify-cli/json`，依 research.md R3 第 1 步的規則挑出最大的穩定版；挑選規則寫成不連線的純函式供 T009 測試；任何失敗都回報為結束碼 4，不重試、不改用其他來源
- [X] T019 [US1] 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作「執行官方工具」：在專案之外的暫存空目錄執行 `uv tool run --from specify-cli==<版本> specify init --here --non-interactive --ignore-agent-tools --integration claude --script sh`，核對產出的 `speckit_version`，不符或非零結束都以結束碼 4 停止；暫存目錄在結束時（包含失敗）刪除；失敗時摘要依 cli.md 補充 (a) 只輸出第一行（research.md R3 第 2 步、R5）
- [X] T020 [US1] 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作規劃：純讀取，為暫存產出的每個檔案決定 `create`、`keep` 或 `skip`（data-model.md「導入的動作」），並依 research.md R6 的表處理五種情況（已完整導入時不連線、不寫入；`applying` 或缺少檔案時使用紀錄內的版本；紀錄無效時以結束碼 1 停止）
- [X] T021 [US1] 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作執行：先寫入 `Record.status` 為 `applying` 的紀錄，再把 `create` 的檔案以位元組原樣複製（不做任何轉換，包含換行）、記錄新建的目錄到 `Record.created_dirs`，最後把 `Record.status` 改為 `complete`；MUST NOT 寫入已存在的檔案（FR-003、FR-004，data-model.md「狀態轉移」）
- [X] T022 [US1] 在 `home/skills/sdd-init/scripts/sdd_init.py` 完成 `init` 的摘要並串起 T017 至 T021：四種情況的第一行、固定的兩行下一步建議、`Git:` 一行的第二與第三種形式（第一種形式在 T031 完成），`<k>` 與 `<n> created` 的算法依 cli.md 補充 (b)(c)；除了讀取狀態之外不執行任何會改變 repository 的 git 指令（contracts/cli.md「各種情況的摘要」「不變的保證」，research.md R10）
- [X] T023 [P] [US1] 撰寫 `home/skills/sdd-init/SKILL.md`（英文）：frontmatter 與內文的五項指示依 contracts/skill.md「SKILL.md」，包含非零結束碼與 `uv` 不存在時回報後停止、不重試、不改用其他方式安裝、不手動建立 `.specify/` 與 `speckit-*` 的檔案、不 commit、不 push
- [X] T024 [P] [US1] 撰寫 `home/skills/sdd-init/README.md`（繁體中文）：內容依 contracts/skill.md「README.md」的五項

**Checkpoint**: `init` 可在單一平台使用；T009 至 T016 通過

---

## Phase 4: User Story 2 - 同一專案在 Windows 與 Linux 都能直接使用 (Priority: P1)

**Goal**: 導入時補上換行規則並把 `.sh` 的執行權限記進 index，使導入並提交的專案在另一個平台不需重新導入

**Independent Test**: 以 `core.autocrlf=true` clone 導入並提交的 repository 後直接執行 Spec Kit 腳本成功；CI 的 cross-platform job 在兩個方向都通過（T042）

### Tests for User Story 2 ⚠️

> 先寫測試並確認失敗，再實作

- [X] T025 [US2] 在 `tests/unit/test_sdd_init.py` 加入 `.specify/.gitattributes` 的測試：全新導入時建立，內容的位元組恰為 `scripts/bash/*.sh text eol=lf` 加一個 LF，有一行 `created`，列入 `entries` 且 `origin` 為 `sdd-init`，計入 `<n> created`；已存在且不在紀錄內時內容不變、列為 `skipped`、不列入 `entries`；此時 `git check-attr eol` 對 `.sh` 的結果不是 `lf` 就輸出 contracts/cli.md 的 `warning` 行，是 `lf` 就不輸出；不是 git repository 而無法檢查時同樣輸出警告；有警告時導入仍以結束碼 0 完成（research.md R1「`.specify/.gitattributes` 已存在時」，data-model.md「sdd-init 自己的檔案」）
- [X] T026 [US2] 在 `tests/unit/test_sdd_init.py` 加入暫存區的測試：在 git repository 導入後，每支新建的 `.sh` 一行 `staged … (executable bit recorded in the git index)`，`git ls-files -s` 顯示它們為 100755（在 `core.fileMode=false` 的 repository 也成立），`staged_executable` 為 true；其他檔案不在 index；被略過的既有 `.sh` 不被加入；`HEAD` 與 commit 數不變；`Git:` 一行與第一種形式逐字相同，`<n>` 等於加入的檔案數，`<k>` 依 cli.md 補充 (b) 計算（全新導入時等於 `entries` 的筆數；把導入的檔案 commit 後刪掉一個非 `.sh` 檔案再補齊，得到第二種形式且 `<k>` 為 1）；不是 git repository 時沒有 `staged` 行，`staged_executable` 全為 false（plan.md Constraints「會動到暫存區」，data-model.md「導入的動作」）
- [X] T027 [US2] 在 `tests/unit/test_sdd_init.py` 加入兩個平台對等的測試：導入後把所有文字檔改寫成 CRLF（模擬經 git 到 Windows），再執行 `init` 仍輸出 `is already initialized` 且零異動；stdout 與紀錄內都沒有反斜線；同一份假產出在兩個不同的暫存目錄導入，stdout 逐字相同、紀錄位元組相同（FR-006、FR-012，research.md R2）
- [X] T028 [US2] 在 `tests/integration/test_sdd_init_real.py` 加入實際執行 Spec Kit 腳本的測試（標記 `network`，只在 `tmp_path` 進行）：導入後 commit，以 `git clone -c core.autocrlf=true` 得到第二份工作目錄，確認其中的 `.sh` 是 LF 且 index 為 100755，再以 `bash` 執行 `.specify/scripts/bash/create-new-feature.sh --json --short-name demo "Demo"` 與 `.specify/scripts/bash/setup-plan.sh --json`，兩者結束碼 0 並產生 `specs/001-demo/plan.md`（research.md R1 的兩個缺口、實測紀錄第 11、13、14 項）
- [X] T029 [P] [US2] 建立 `tests/e2e/test_cross_platform.py`：只在 CI 的 cross-platform job 執行，以該 job 設定的環境變數判斷（變數名稱由實作者決定，`.github/workflows/ci.yml` 與測試使用同一個），沒有設定時以 skip 跳過並說明原因。內容分兩部分：「產出」在暫存目錄 `git init`、執行 `init`、commit、以 `git bundle` 打包並寫出依路徑排序的檔案清單；「驗證」clone 另一個平台的 bundle（Windows 一側明確設定 `core.autocrlf=true`），不做任何額外步驟就以 `bash` 執行 `create-new-feature.sh` 與 `setup-plan.sh` 成功，並比對兩個平台的檔案清單相同（US2 情境 1 至 3、SC-003，research.md R4）

### Implementation for User Story 2

- [X] T030 [US2] 在 `home/skills/sdd-init/scripts/sdd_init.py` 把 `.specify/.gitattributes` 納入規劃與執行：不存在時建立並以 `Record.entries[].origin` 為 `sdd-init` 列入紀錄；已存在且不在紀錄內時略過，並依 `git check-attr eol` 的結果決定是否輸出 `warning` 行（research.md R1，data-model.md「sdd-init 自己的檔案」）
- [X] T031 [US2] 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作暫存區：專案是 git repository 時，對動作為 `create` 的 `.sh` 執行 `git add --chmod=+x`，把 `Record.entries[].staged_executable` 設為 true，輸出 `staged` 行與 `Git:` 一行的第一種形式（`<k>` 依 cli.md 補充 (b)）；不 commit，不對其他檔案執行 `git add`（plan.md Constraints，contracts/cli.md「不變的保證」）
- [X] T032 [P] [US2] 在 `.github/workflows/ci.yml` 新增 `cross-platform` job，既有的 `test` job 不變：矩陣 `ubuntu-latest` 與 `windows-latest`；第一步每個平台執行 T029 的「產出」並把 bundle 與檔案清單上傳為 artifact；第二步每個平台下載**另一個平台**的 artifact 並執行 T029 的「驗證」；步驟以 `shell: bash` 執行，使兩個平台的指令相同（plan.md「Structure Decision」，research.md R4）

**Checkpoint**: 本機的單元與整合測試通過；跨平台的結果待 T042 以 CI 確認

---

## Phase 5: User Story 3 - 移除 Spec Kit (Priority: P3)

**Goal**: `remove` 只刪除紀錄內且未被修改的檔案，導入後立即移除時專案與 index 都回到原狀

**Independent Test**: 導入後修改一個檔案並新增 `specs/` 內容，執行 `remove`，只有未被修改的導入檔案被刪除

### Tests for User Story 3 ⚠️

> 先寫測試並確認失敗，再實作

- [X] T033 [US3] 在 `tests/unit/test_sdd_init.py` 加入導入後立即移除的測試：在只有一個已 commit 的 `README.md` 的 repository 執行 `init` 再執行 `remove`，目錄快照、`git status --porcelain` 與 `git ls-files -s` 都和導入前完全相同（`.specify/`、`.claude/` 與紀錄都不存在）；每個檔案一行 `deleted`，每支曾被加入暫存區的 `.sh` 一行 `unstaged`；摘要為 `Spec Kit removed: <n> deleted, 0 kept because they were modified.`；不是 git repository 時同樣回到原狀且沒有 `unstaged` 行（FR-008、SC-004，research.md R7）
- [X] T034 [US3] 在 `tests/unit/test_sdd_init.py` 加入保留修改與不碰其他內容的測試：修改過的 `.specify/memory/constitution.md` 列為 `kept … (modified since init)` 且內容不變，所在的目錄保留；只把檔案換成 CRLF 不算修改，仍被刪除；紀錄內但已不存在的檔案不輸出也不報錯；`specs/` 的內容、導入時被略過的檔案、不在紀錄內的 `.specify/feature.json` 都原封不動；導入的檔案已 commit 時移除不動 index（沒有 `unstaged` 行，刪除顯示為未暫存的變更）；移除後紀錄不存在（FR-008、FR-009、SC-005，data-model.md「移除的動作」）
- [X] T035 [US3] 在 `tests/unit/test_sdd_init.py` 加入沒有紀錄與無效紀錄的測試：沒有紀錄時結束碼 0、輸出 contracts/cli.md 的 `Nothing to remove: …` 一行、目錄快照不變（即使專案內有以其他方式導入的 Spec Kit 檔案）；紀錄無法解析時結束碼 0、輸出 `Nothing was removed: …` 一行、零刪除；紀錄內有路徑不在 `.specify/` 或 `.claude/skills/speckit-*/` 之下（例如 `specs/x.md`、`../x`）時結束碼 1、零刪除（spec 的邊界情況，research.md R7）
- [X] T036 [US3] 在 `tests/integration/test_sdd_init_real.py` 加入實際官方產出的往返測試（標記 `network`，只在 `tmp_path` 進行）：在只有一個已 commit 的 `README.md` 的 repository 執行 `init` 再執行 `remove`，目錄快照與 `git status --porcelain` 和導入前完全相同（SC-004）

### Implementation for User Story 3

- [X] T037 [US3] 在 `home/skills/sdd-init/scripts/sdd_init.py` 實作 `remove` 的規劃與刪除：只依紀錄行事，比對 `Record.entries[].sha256` 把每一筆分為 `delete`、`keep-modified`、`gone`（data-model.md「移除的動作」）；紀錄不存在或無法解析時不刪除任何檔案並以結束碼 0 輸出對應的摘要；路徑違反 `Record.entries[].path` 的規則時以結束碼 1 拒絕；MUST NOT 讀寫 `specs/`
- [X] T038 [US3] 在 `home/skills/sdd-init/scripts/sdd_init.py` 完成 `remove`：被刪除的檔案若 `Record.entries[].staged_executable` 為 true、仍在 index 且不在 `HEAD`，以 `git rm --cached` 取消並輸出 `unstaged` 行；由深到淺刪除 `Record.created_dirs` 中已變空的目錄；最後刪除紀錄；輸出 contracts/cli.md「remove」的動作行與摘要

**Checkpoint**: 三個 story 的本機測試全部通過

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 文件、實跑驗證與 CI

- [X] T039 [P] 更新 `README.md`（繁體中文）：「目前狀態」改為 `sdd-init` 已提供、其餘 5 個 skill 由 004 至 008 提供；加入 `/sdd-init` 與 `/sdd-init remove` 的簡短說明與前置需求（`uv`、`git`、`bash`，Windows 的 `bash` 是 Git Bash）
- [X] T040 依 `specs/003-sdd-init/quickstart.md`「手動情境（腳本）」的 9 個情境，在 `mktemp -d` 建立的暫存目錄逐一實跑 `uv run <repo>/home/skills/sdd-init/scripts/sdd_init.py`，並修正與預期不符之處；每個情境用新的暫存目錄，MUST NOT 在這個 repo 的目錄或真正的 `~/.claude` 執行。情境 8（無法取得版本）只在能夠只對該次執行隔離網路時實跑（例如 Linux 的 `unshare -rn`），MUST NOT 中斷整台機器的網路，也 MUST NOT 為此在腳本加入環境變數或隱藏選項；無法隔離時在回報中註明未實跑，該行為由 T014 的測試涵蓋
- [X] T041 執行完整測試 `uv run --with pytest pytest`（含 `network`）與 `uv run --with pytest pytest -m "not network"`，兩者全部通過；`tests/e2e/test_cross_platform.py` 在本機跳過是預期的；確認 `git status` 中 `.specify/sdd-init.json` 與 `.specify/` 其他既有檔案都沒有被這次的工作更動
- [X] T042 **由主代理在維護者授權推送後處理，實作的 worker 不執行這一項、不 push**：推送分支後確認 `.github/workflows/ci.yml` 的 `test` job 與 `cross-platform` job 在 `ubuntu-latest` 與 `windows-latest` 都通過（共四個結果）；Windows 與跨平台的行為以 CI 結果為準，失敗時依紀錄修正後再確認

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依賴 001、002 已合併
- **Foundational (Phase 2)**: 依賴 Setup；T005 的測試先於 T006 至 T008
- **US1 (Phase 3)**: 依賴 Foundational
- **US2 (Phase 4)**: 依賴 US1（在 `init` 的規劃與執行上增加 `.gitattributes` 與暫存區）
- **US3 (Phase 5)**: 依賴 US1；T033 的 `unstaged` 與 index 比對另外依賴 US2 的 T031
- **Polish (Phase 6)**: 依賴 US1 至 US3；T042 依賴 T041，且需要維護者授權推送

### Within Each User Story

- 測試先寫並確認失敗，再實作
- `home/skills/sdd-init/scripts/sdd_init.py`、`tests/unit/test_sdd_init.py`、`tests/integration/test_sdd_init_real.py`
  各是單一檔案，改同一個檔案的任務依編號依序進行
- 引用「cli.md 補充 (a)(b)(c)」的任務依賴 T002

### Parallel Opportunities

- T003 可與 T002 平行
- T015、T016 可與 T009 至 T014 平行（不同檔案）
- T023、T024 可與 T017 至 T022 平行
- T029、T032 可與 US2 的其他任務平行
- T039 可與 T040 平行
- 其餘任務集中在 `sdd_init.py` 與 `test_sdd_init.py`，沒有其他平行機會

## Parallel Example: User Story 1

```text
Task: "T015 建立 tests/unit/test_sdd_init_skill.py"
Task: "T016 建立 tests/integration/test_sdd_init_real.py"
Task: "T023 撰寫 home/skills/sdd-init/SKILL.md"
Task: "T024 撰寫 home/skills/sdd-init/README.md"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 與 Phase 2
2. 完成 Phase 3（US1）：`init` 與 skill 資料夾
3. 此時導入的專案只保證在導入的平台可用；US2 同為 P1，且 constitution 原則 II 要求兩個平台對等，
   所以 US1 與 US2 應在同一個 PR 內完成，不單獨合併 US1

### Incremental Delivery

1. Foundational：骨架、雜湊、紀錄、輸出
2. US1：導入、不覆蓋、冪等、失敗時零寫入、skill 文件
3. US2：換行規則、執行權限、跨平台測試與 CI job
4. US3：移除
5. Polish：README、quickstart 實跑、完整測試、CI（T042）

## Notes

- 每完成一個任務或一組相關任務就 commit；不 push，推送由主代理在維護者授權後進行（T042）
- 人工驗收不列為勾選任務：`quickstart.md`「人工驗收（skill 與跨平台）」的 5 個情境需要真實的 Claude Code session、
  部署到真正的 `~/.claude`，其中第 3 項還需要 Windows 與 Linux 兩台機器，由維護者在合併並部署後進行
- 「Spec Kit 流程」在自動測試中指 `speckit-*` skill 所呼叫的腳本能執行並產出預期的檔案；
  Claude 依 SKILL.md 走完整個對話流程屬於人工驗收（research.md R4）
- T002 的三點是維護者核可 plan 時與主代理代答的決定，在 T002 完成前 contracts/cli.md 尚未寫明
- `remove` 遇到 `schema` 不認得的紀錄時，T035 與 T037 依 data-model.md「不刪除任何檔案」處理；
  結束碼與摘要文件沒有另外寫明，實作前若需要區分它與「無法解析」，向主代理提問
- 這個 repo 既有的 `.specify/sdd-init.json` 是另一個工具留下的，本功能的任何任務都不讀寫它

---

## Phase 7: 維護者追加：Windows 上只承認 Git Bash

**Purpose**: T041 之後維護者追加的決定。原本的檢查只看 `PATH` 上有沒有 `bash`；在沒有 Git Bash 但有 WSL 的 Windows 機器上，
`bash` 會解析到 WSL 的啟動器，檢查會通過。改為在 Windows 上分辨兩者，只承認 Git Bash；Linux 的行為不變。
這個階段不依賴 T042，T042 仍由主代理處理。

- [X] T043 在 `specs/003-sdd-init/contracts/cli.md` 新增「必要工具的判定」一節，並更新 init 輸出範例旁的 `missing` 行說明：Windows 上判定 Git Bash 的方法（不依賴固定的安裝路徑、不受 `PATH` 上 `bash` 的順序影響）、`missing` 行在兩個平台的文字、stderr 的說明、這項檢查保證與不保證的事（sdd-init 不執行 Spec Kit 的 `.sh`，執行者是 Claude Code 的 Bash tool），以及判定不出來的情況
- [X] T044 在 `tests/unit/test_sdd_init.py` 加入 Windows 判定的測試，以替換「平台判斷」與「詢問 git」兩個函式、並在 `tmp_path` 建立假的安裝目錄來模擬，在 Linux 與 Windows 都能執行，確認在 T045 實作前失敗：只有 Git Bash；只有 WSL 啟動器（沒有 git，以及有不是 Git for Windows 的 git 兩種）；兩者都有且 WSL 啟動器排在 `PATH` 前面；兩者都沒有；Git for Windows 不在預設路徑；`PATH` 上第一個 git 不是 Git for Windows 而後面的是；Git for Windows 內沒有 `bash.exe`；設定了 `GIT_EXEC_PATH` 時不受影響。找不到 Git Bash 時結束碼 3、`missing` 行與摘要第一行符合 cli.md、stderr 提到 Git for Windows、目錄快照不變、兩個替換步驟都沒有被呼叫。既有的缺少工具測試固定為非 Windows 平台，確認 Linux 的輸出不變
- [X] T045 在 `home/skills/sdd-init/scripts/sdd_init.py` 依 cli.md「必要工具的判定」實作：Windows 上 `bash` 的判定改為尋找 Git for Windows 附的 Git Bash，找不到時列為缺少的工具（結束碼 3、零寫入），`missing` 行與 stderr 依 cli.md；Linux 上仍以 `PATH` 上有沒有 `bash` 判定，輸出逐字不變
- [X] T046 [P] 更新 `home/skills/sdd-init/README.md` 的「前置需求」（繁體中文）：Windows 上只承認 Git for Windows 附的 Git Bash、WSL 的 `bash.exe` 不算，Git for Windows 的 `git` 必須在 `PATH` 上；`tests/unit/test_sdd_init_skill.py` 的既有檢查繼續通過
- [X] T047 執行 `uv run --with pytest pytest`，結束碼 0；這項判定在真正的 Windows 上的結果由 T042 的 CI（`windows-latest` 的 `test` 與 `cross-platform` job）確認

---

## Phase 8: Convergence

**Purpose**: `/speckit-converge` 找到的漏做工作。`init` 補齊時，先前已複製但沒有成功加入暫存區的 `.sh` 不會再被
`git add --chmod=+x`：複製途中失敗後再次執行（紀錄為 `applying`），或先前 `git add --chmod=+x` 本身失敗（紀錄已是 `complete`）
都是如此。這樣的專案在 Windows 提交後，`.sh` 在 index 內是 100644，於 Linux clone 後無法執行。
主代理已決定這是漏做（FR-006 是 MUST），不是已知限制。T048 先於 T049 至 T051；T050 先於 T051；T052 最後。

- [ ] T048 在 `specs/003-sdd-init/contracts/cli.md` 寫明「補登執行權限」的行為、輸出與摘要（只補這一項，不改其他內容）：`init` 在專案是 git repository 時，對紀錄內 `origin` 為 `speckit`、`staged_executable` 為 false、檔案存在、且不在 index 也不在 `HEAD` 的 `.sh`，同樣執行 `git add --chmod=+x`、把 `staged_executable` 設為 true 並輸出 `staged` 行；這適用於 (1) 紀錄為 `applying` 或缺少檔案而補齊時，(2) 紀錄為 `complete` 且檔案齊全、但仍有符合上述條件的 `.sh` 時（此時 MUST NOT 只回報 `is already initialized`，也 MUST NOT 連線或執行官方工具）。文件 MUST 寫明：情況 (2) 的摘要第一行、`Git:` 一行與下一步建議各怎麼輸出，`<n> created` 與 `<k>` 怎麼算；沒有符合條件的 `.sh` 時「已完整導入」的輸出與零異動不變（FR-011）；補登成功後再次執行為零異動；`git add --chmod=+x` 失敗時的輸出與結束碼；並同步更新「不變的保證」中 init 對暫存區的敘述。這條規則也會涵蓋「導入時不是 git repository、之後才 `git init`」的專案，文件 MUST 寫明這種情況的結果；文件無法決定之處向主代理提問，不自行假設 per FR-006、SC-003、邊界情況「導入中途失敗」、FR-012 (partial)
- [ ] T049 [P] 在 `specs/003-sdd-init/data-model.md`「導入的動作」補上這條規則：動作為 `keep` 的 `.sh` 若 `origin` 為 `speckit`、`staged_executable` 為 false、且不在 index 也不在 `HEAD`，在專案是 git repository 時同樣執行 `git add --chmod=+x` 並把 `staged_executable` 設為 true；「狀態轉移」補上「`status=complete` 且檔案齊全、但仍有這樣的 `.sh`」不再是「不做任何事」；`entries[].staged_executable` 的說明與 T048 一致。MUST NOT 修改 `spec.md` 與 `plan.md` per FR-006、SC-003、邊界情況「導入中途失敗」 (partial)
- [ ] T050 在 `tests/unit/test_sdd_init.py` 加入補登執行權限的測試，確認在 T051 實作前失敗，全部以假的官方產出在 `tmp_path` 進行，不需要網路：(1) 複製途中失敗留下 `applying` 的紀錄後再次執行，上一次已複製的 `.sh` 與這次補上的 `.sh` 各有一行 `staged`，`git ls-files -s` 全部是 100755（在 `core.fileMode=false` 且工作目錄的檔案沒有執行權限的 repository 也成立），`staged_executable` 全為 true，`Git:` 一行的 `<n>` 等於實際加入的檔案數；(2) 紀錄為 `complete`、檔案齊全，但 `.sh` 的 `staged_executable` 為 false 且不在 index 也不在 `HEAD`（模擬先前 `git add --chmod=+x` 失敗）時再次執行，這些 `.sh` 被加入為 100755，輸出與摘要逐字符合 T048 寫進 cli.md 的內容，「查詢版本」與「執行官方工具」兩個替換函式都沒有被呼叫，除了 index 與紀錄之外目錄快照不變；(3) 上述兩種情況之後再執行一次都只輸出 `is already initialized` 且零異動；(4) 不受影響的情況維持原狀：`.sh` 已在 `HEAD` 或已在 index 時不動 index、不輸出 `staged`，被略過（不在紀錄內）的 `.sh` 不被加入，不是 git repository 時沒有 `staged` 行，`origin` 不是 `speckit` 的檔案與非 `.sh` 檔案不被加入；(5) 沒有新的 commit、分支不變 per FR-006、SC-003、邊界情況「導入中途失敗」、FR-011 (partial)
- [ ] T051 在 `home/skills/sdd-init/scripts/sdd_init.py` 依 T048 的 cli.md 與 T049 的 data-model.md 實作補登執行權限：補齊時與「已完整導入」的判定都納入紀錄內 `origin` 為 `speckit`、`staged_executable` 為 false、檔案存在且不在 index 也不在 `HEAD` 的 `.sh`，對它們執行 `git add --chmod=+x`、更新紀錄並輸出 `staged` 行；情況 (2) 不連線、不執行官方工具、不複製任何檔案；不 commit，不對其他檔案執行 `git add`；Linux 與 Windows 的輸出逐字相同；既有測試（包含 T012 的零異動與 T026 的暫存區測試）繼續通過 per FR-006、SC-003、邊界情況「導入中途失敗」 (partial)
- [ ] T052 執行 `uv run --with pytest pytest`（含 `network`）與 `uv run --with pytest pytest -m "not network"`，兩者結束碼 0；在 `mktemp -d` 的暫存 repository（`core.fileMode=false`，並移除 `.sh` 的執行權限以模擬 Windows）實跑 T050 的情況 (1)(2) 各一次，確認之後 `git add -A` 得到的 `.sh` 都是 100755；MUST NOT 在這個 repo 的目錄或真正的 `~/.claude` 執行。這項行為在真正的 Windows 上的結果由推送後的 CI（`windows-latest` 的 `test` job）確認，推送由主代理處理 per FR-006、SC-003、Constitution II (partial)
