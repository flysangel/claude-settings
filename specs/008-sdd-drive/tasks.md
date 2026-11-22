---

description: "Task list for 008 sdd-drive 由子 session 依序把每份 spec 做到完成"
---

# Tasks: sdd-drive 由子 session 依序把每份 spec 做到完成

**Input**: Design documents from `/specs/008-sdd-drive/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/cli.md、contracts/skill.md、quickstart.md

**Tests**: 需要。Constitution（v1.0.2）原則 II 要求每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
腳本 `sdd_drive.py` 的每個指令（`status`、`brief`、`run`、`watch`、`cancel`、`test`、`finalize`、`clear`，與內部的 `_drive`）先寫測試、確認失敗，再實作；
`SKILL.md` 與 `README.md` 以結構與內容檢查驗證（關鍵字與段落順序，不比對完整文字）。
測試指令是 `uv run --with pytest pytest`。

**Organization**: 依 user story 分組。這是**協調式的 skill**（主 session 只執行腳本、等待、回報；判斷與可測的行為集中在腳本）：
腳本的行為以單元測試（假的 `claude`，環境變數 `SDD_DRIVE_CLAUDE`）涵蓋，SKILL.md 的指示以內容檢查涵蓋；
真實子 session 與部署才能進行的驗收（quickstart.md「人工驗收」1–16）無法在 CI 驗證，**只寫在最後的 Notes，不列為勾選任務**。
腳本的所有指令在同一支 `home/skills/sdd-drive/scripts/sdd_drive.py`，單元測試在 `tests/unit/test_sdd_drive.py`，
skill 的結構與內容檢查在 `tests/unit/test_sdd_drive_skill.py`，假的 `claude` 在 `tests/unit/fixtures/sdd_drive/fake_claude.py`；
改同一個檔案的任務依序進行。`SKILL.md` 的各階段由多個任務寫入同一個檔案：**段落依 contracts/skill.md 的階段編號排列，與任務的先後無關**；
每個 SKILL.md 任務都標明它負責 contracts/skill.md 的哪些條目與哪些「結果」列。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、沒有未完成的相依）
- **[Story]**: 所屬的 user story（US1 至 US4）；Setup、Foundational、Polish 階段不加 story 標籤
- 路徑相對於 repo 根目錄
- `contracts/skill.md 通則 N` 指該文件「SKILL.md 的內文／通則」的第 N 項（1 至 13）；`階段 N 的結果列` 指該階段表格中的每一列
- 引用 data-model.md 的欄位時寫作 `data-model.md` 的 `欄位名`（例如 `attempts[].outcome`、`tests[].tasks_hash`、`baseline`、`driver`、`launch`）；
  這些欄位的格式與驗證以 data-model.md「紀錄」的表為準，任務不重複其內容
- 四個 user story 對應 spec.md：US1 一個指令把整批 spec 做到完成、US2 確認真的完成才往下、US3 失敗時停止並回報、US4 中斷後接續（含用量上限的自動接續）

## 所有任務共同的限制

- 實作與驗證 MUST NOT 讀寫真正的家目錄 `~/.claude`，也 MUST NOT 把這個 skill 部署到那裡。
- 這台機器的 `~/.claude/skills/` 下有另一個專案留下的同名 `sdd-drive`。實作者 MUST NOT 讀取、複製或沿用它，也 MUST NOT 讀取相鄰的專案目錄；
  `SKILL.md`、`README.md` 與腳本只依本目錄的設計文件，以及本 repo 的 `home/skills/sdd-grill/`、`home/skills/sdd-rebuild/` 與既有測試撰寫。
- MUST NOT 在這個 repo 內執行 `sdd_drive.py` 的任何寫入指令（`run`、`test`、`finalize`、`clear`、`cancel`），也不對這個 repo 或這台機器上其他真實的專案執行；
  這個 repo 不得出現 `.specify/sdd-drive/`。所有實際執行（測試、手動情境、走查）都在暫存目錄建立的假專案進行：pytest 用 `tmp_path`，手動情境用 `mktemp -d`，每個情境用新的暫存目錄。
- MUST NOT 在任何測試或手動情境啟動真正的 `claude`；子 session 一律是 `SDD_DRIVE_CLAUDE` 指定的假的 `claude`（`tests/unit/fixtures/sdd_drive/fake_claude.py`），不得消耗用量。
- 測試 MUST NOT 依賴執行順序：每個測試自己用 `tmp_path` 建立專案與狀態，不共用模組層級的可變狀態，不依賴其他測試留下的檔案，可單獨執行、可亂序執行。
- 測試與 fixture 建立的資料夾、分支與檔案名稱 MUST NOT 含冒號等 Windows 不允許的字元（時間戳記用 `-` 或 `T` 加數字，不用 `:`）；路徑以 `/` 比較時先正規化。
- 測試的 fixture 把 `HOME` 與 `USERPROFILE` 指向暫存目錄，所有 `git` 操作使用暫存 repository 並設定測試用的 `user.name`、`user.email`
  （並關閉全域與系統設定的影響，例如 `GIT_CONFIG_GLOBAL`／`GIT_CONFIG_NOSYSTEM`）；遵循 `tests/conftest.py` 既有的慣例（停用 git 背景維護）。
- 005 的 `home/skills/sdd-grill/scripts/sdd_grill.py` 只被載入、不修改；005、006、007 的腳本、`SKILL.md` 與既有測試 MUST NOT 修改。
- 不修改 CI（`.github/workflows/ci.yml`；plan.md：不新增或修改 job）、`.specify/`（含 `.specify/feature.json`）、`tools/deploy.py` 與 `home/CLAUDE.md`；
  不修改 `spec.md`、`plan.md` 與 `specs/008-sdd-drive/` 的其他設計文件；設計文件有疑義、互相矛盾或需要逐字比對而文件沒有寫明時，向主代理提問，不自行決定。
- 每完成一項異動就 commit 到目前的分支 `008-sdd-drive`（commit 訊息用繁體中文，結尾加 `Co-Authored-By` 行）；不 commit 到 `main`、不切換或建立分支、不合併；**不 push**；
  需要推送才能確認的工作只有 T059。
- 產出只有 skill 文件或 script；Python 一律用 uv 執行；`SKILL.md`、`README.md`（內文英文／繁中依 contracts/skill.md）、腳本與工作說明 MUST NOT 含絕對路徑與信箱。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認既有基礎可用，備妥假的 `claude` 與測試的共用輔助

- [X] T001 [P] 唯讀確認 `tools/deploy.py` 會自動納入 `home/skills/sdd-drive/`（不需要修改）、`.github/workflows/ci.yml` 的 `test` job 會執行 `tests/unit/` 下的新測試（CI 不變）、`tests/unit/test_claude_md.py::test_referenced_skills_exist_in_home_skills` 目前因缺少 `home/skills/sdd-drive` 而 skip，並讀 `tests/conftest.py`、`tests/unit/test_sdd_rebuild.py` 與 `tests/unit/test_sdd_rebuild_skill.py` 的結構作為本功能測試的寫法依據；若與 plan.md 不符，向主代理提問而不是自行修改
- [X] T002 [P] 建立 `tests/unit/fixtures/sdd_drive/fake_claude.py`（假的 `claude`，一支只用標準函式庫的 Python 腳本，經 `SDD_DRIVE_CLAUDE`＝JSON 陣列 `[python, fake_claude.py]` 取代 `claude`，contracts/cli.md「共通」；quickstart.md「自動測試」）：依環境變數指定的情境動作，把收到的 argv 與 stdin 寫入環境變數指定的檔案供斷言（路徑由測試的 `tmp_path` 提供，不共用）；以 stream-json 逐行輸出並以 `type: "result"` 結尾，`structured_output` 符合 data-model.md「子 session 的回報」。情境至少涵蓋：各階段成功（寫 plan.md、tasks.md、勾選任務並 commit）、回報 `failed`（含 `failure.kind` 的五種）、不輸出結果就結束、輸出 `is_error` 的 API 錯誤（401、404、`error_max_turns`）、用量上限（`status: "rejected"` 的 `rate_limit_event`：時間窗有 `resetsAt`、只有 `overage`、缺 `resetsAt`、只有文字、花費上限＋5 小時時間窗的組合；`api_error_status` 429）、`--resume` 失敗（session 不存在）、做完後留下未提交的變更、刪除或減少任務、修改 spec.md／constitution／`.specify/templates`、`git push` 到暫存的 bare remote、對照檢查（`tasks.md` 不變、附加合格的 Convergence 段落並只 commit 該檔、說 converged 卻附加、說找到卻沒附加、改寫或勾選既有任務、改動程式碼或 plan.md、附加後不 commit）；情境可指定「第 N 次呼叫」的行為（供自動接續：第一次用量上限、第二次成功或再次用量上限）。用途是測試，不得有網路或真實 API 行為
- [X] T003 [P] 建立 `tests/unit/test_sdd_drive.py` 的共用輔助（之後所有腳本測試共用；依 T001 讀到的既有測試寫法）：以 `tmp_path` 建立假專案的 fixture（`git init`、設定 `user.name`／`user.email`、提交一次；`.specify/` 骨架由複製本 repo 的 `.specify/templates` 與 `.specify/scripts` 取得，`.claude/skills/speckit-plan`、`speckit-tasks`、`speckit-implement`、`speckit-converge` 的資料夾以最小內容建立）；建立 `specs/NNN-name/` 的輔助（寫 spec.md、plan.md 含 `**Testing**:` 行、tasks.md 含 N 個任務並勾選前 K 個、範本內容的 plan／tasks）；暫存的 bare remote；執行 `uv run <repo>/home/skills/sdd-drive/scripts/sdd_drive.py <command>` 並解析 stdout JSON 與結束碼的輔助；把 `SDD_DRIVE_CLAUDE` 與 `SDD_DRIVE_TEST_TIMING`（contracts/cli.md「共通」）指向假的 `claude` 與縮短的時間的輔助；子程序持有鎖的輔助。夾具名稱與資料夾名稱不含冒號

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 腳本的骨架、紀錄檔、鎖、git 輔助與 spec 狀態的計算；所有 user story 都建立在這些之上

**⚠️ CRITICAL**: 在這個階段完成之前，不開始任何 user story

- [X] T004 在 `tests/unit/test_sdd_drive.py` 加入腳本骨架的測試（contracts/cli.md「共通」「結束碼與 `reason`」；FR-017）：未知子指令、缺少或多出參數 → 結束碼 1、`reason: "usage"`，`error` 同時寫到 stderr；stdout 只有一份 JSON（UTF-8、LF、縮排 2、`ensure_ascii=False`、結尾換行、鍵的順序固定），路徑以 `/` 分隔且相對於專案根目錄；相鄰的 `sdd-grill` 缺少時所有指令結束碼 3、`reason: "dependency"`（以暫存的 skill 資料夾副本驗證）；`SDD_DRIVE_CLAUDE` 必須是 JSON 字串陣列、`SDD_DRIVE_TEST_TIMING` 必須是含 `poll_seconds`、`margin_seconds`、`watch_seconds` 的 JSON 物件，不合格時 `usage`；任何輸出都不含絕對的家目錄路徑
- [X] T005 建立 `home/skills/sdd-drive/scripts/sdd_drive.py` 的骨架（contracts/cli.md「共通」；research.md D16）：uv inline metadata（Python 3.11+，只用標準函式庫）；以 `importlib` 載入 `../../sdd-grill/scripts/sdd_grill.py`（Spec Kit 狀態、spec 編號、原子寫入、機密樣式；載入失敗 → 結束碼 3、`reason: "dependency"`）；八個子指令與內部的 `_drive --token <uuid>` 的參數解析；統一的 JSON 輸出、`error`／`reason`／結束碼的輔助；`SDD_DRIVE_CLAUDE`、`SDD_DRIVE_TEST_TIMING` 的解析與驗證。各指令的本體先回傳「尚未實作」的內部錯誤，由後續任務填入；T004 的測試通過
- [X] T006 在 `tests/unit/test_sdd_drive.py` 加入紀錄檔的測試（data-model.md「本 skill 的檔案」「紀錄」；FR-011、FR-015；research.md D14、D23）：`own_dir` 的 `none`／`ours`／`conflict`（資料夾有不明檔案、`.gitignore` 內容不同）；`.gitignore` 固定兩行；`state.json` 寫入一律「同資料夾暫存檔再取代」（暫存檔已移除、既有檔案不變）；讀回時逐欄位驗證 `data-model.md` 的 `tool`、`schema`、`attempts[].id`（嚴格遞增）、`attempts[].spec`（不含 `/`、`\`）、`attempts[].phase`、`attempts[].session_id`、`attempts[].model`、`attempts[].model_used`、`attempts[].reason`、`attempts[].started_at`、`attempts[].ended_at`、`attempts[].outcome`、`attempts[].detail`、`attempts[].report`、`attempts[].worktree`、`attempts[].task_ids`、`attempts[].tasks_hash`、`attempts[].limit`、`attempts[].auto_resume`、`launch`、`driver`、`baseline`、`baseline_reset`、`tests[].spec`、`tests[].tasks_hash`、`tests[].head`、`tests[].command`、`tests[].exit_code`，每個欄位至少一個不合格案例 → `reason: "state-unreadable"`，`detail` 指出欄位路徑而不含值；機密掃描的欄位（`reason`、`detail.text`、`detail.paths`、`report`、`tests[].command`）寫入時命中則取代為 `(not shown: looks like a secret)`、`reason` 命中時拒絕，讀回時以同一組欄位掃描（寫入與讀取對稱）；`baseline` 在第一次寫入時凍結、之後不再新增，紀錄尚不存在時以「tasks 已產生且全部勾選」即時計算且與寫入後一致（FR-025、D23）；不讀取、不修改 `.specify/sdd-drive-state.json` 與 `.specify/.gitignore`（T8）
- [X] T007 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作紀錄檔的讀寫與驗證（依 T006；`data-model.md` 的 `attempts[]` 全部欄位、`launch`、`driver`、`baseline`、`baseline_reset`、`tests[]`；`own_dir` 判定；原子寫入使用 sdd-grill 提供的輔助；機密掃描使用 sdd-grill 的機密樣式）；`detail.code` 的列舉與 `outcome` 的列舉（含 `gaps-found`）依 data-model.md「紀錄」
- [X] T008 在 `tests/unit/test_sdd_drive.py` 加入鎖的測試（FR-012；research.md D7、D20）：另一個程序持有鎖時 `status` 回報 `running: true`、`run`／`test`／`finalize`／`clear` 以 `reason: "running"` 結束碼 1 拒絕；持有鎖的程序結束（含被終止）後鎖釋放；`launch` 記號在 60 秒內視同 `running`，超過 60 秒且鎖未被持有視為啟動失敗（以注入的時間驗證）；`own_dir` 為 `conflict` 時讀寫紀錄的指令 `reason: "conflict"` 且 `clear` 也不刪除
- [X] T009 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作檔案鎖（`.specify/sdd-drive/lock`，Linux `fcntl.flock`、Windows `msvcrt.locking`，非阻塞與最多 60 秒的阻塞兩種取得方式）、`running` 的判斷與 `launch` 記號的 60 秒規則（依 T008；`data-model.md` 的 `launch`、`driver`）；不使用 PID 判斷存活
- [X] T010 在 `tests/unit/test_sdd_drive.py` 加入 git 與受保護檔案輔助的測試（FR-015、FR-016、FR-017；data-model.md「工作區（git）」「受保護的檔案」；research.md D9–D11）：`git` 與非 git 專案的判斷；`dirty` 的路徑（排除 `.specify/feature.json` 與 `.specify/sdd-drive/`、被 ignore 的檔案不列出、含未追蹤檔案）；工作區指紋（路徑加內容的雜湊、不記路徑本身、內容改變指紋就不同、CRLF 與 LF 各自穩定）；機密樣式的路徑以 `(not shown)` 取代；remote-tracking refs 的快照比較；分支處理（目前分支就是 spec 的分支 → 不動、不存在 → 從目前 HEAD 建立並切換使後一份疊在前一份之上、存在且 HEAD 是其祖先 → 切換、分岔 → `branch-diverged` 且不合併不重設；永遠不 commit 到預設分支）；`.specify/feature.json` 的 `feature_directory` 設定（保留其他鍵、不是 JSON 物件時改寫為只有這個鍵的物件）；受保護檔案（`.specify/memory/constitution.md`、`specs/*/spec.md`、`.specify/templates/**`、`.specify/scripts/**`、`.claude/skills/speckit-*/**`）前後雜湊比對、被改動的路徑列表
- [X] T011 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 git 輔助、工作區指紋、受保護檔案雜湊與 `feature.json` 的設定（依 T010；只使用 `git rev-parse`、`status`、`for-each-ref`、`merge-base --is-ancestor`、`switch`、`switch -c`；不使用 `stash`、`reset`、`checkout -- <path>`、`clean`、`restore`、`merge`；`data-model.md` 的 `attempts[].worktree` 的格式）
- [X] T012 在 `tests/unit/test_sdd_drive.py` 加入 spec 狀態計算的測試（FR-003、FR-007、FR-011、FR-014；data-model.md「spec 的狀態」；research.md D5、D6）：只看 `specs/` 下符合 Spec Kit 編號的資料夾、依編號由小到大、缺號依實際存在的處理；plan 未產生的判定（不存在、與 `.specify/templates/plan-template.md` 相同、第一個 `# ` 標題仍含 `[FEATURE]`）；tasks 未產生的判定（不存在、與範本相同、標題含 `[FEATURE NAME]`、沒有任何任務行）；任務行格式 `^\s*- \[( |x|X)\] (T\d{3,})\b`、`x`／`X` 皆算勾選；`not-started`／`planned`／`tasked`／`implementing` 各列的 `state` 與 `next_phase`；測試指令擷取（`**Testing**:` 行第一個反引號區段；沒有、空白、`N/A`／`none`／`TBD` 不分大小寫、命中機密樣式 → 無可用指令）；`tasks_hash` 為 `sha256:` 加 64 個十六進位字元、換行正規化後計算
- [X] T013 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 spec 狀態的計算與測試指令擷取（依 T012）：實作 data-model.md「spec 的狀態」表中**不依賴測試紀錄、對照檢查與基準**的列（`not-started`、`planned`、`tasked`、`implementing`）；全部勾選之後依 `tests[].tasks_hash` 與 `attempts[].convergence` 的列、既有的基準與失敗的疊加留待 T031、T038 補上；狀態每次由檔案重新計算，不快取

**Checkpoint**: 骨架、紀錄、鎖、git、狀態的基礎完成，T004、T006、T008、T010、T012 的測試通過——user story 可以開始

---

## Phase 3: User Story 1 - 一個指令把整批 spec 做到完成 (Priority: P1) 🎯 MVP

**Goal**: 維護者輸入 `/sdd-drive`，主 session 依 `status` 逐個階段開子 session（模型逐次選擇並記錄理由），由子 session 依編號一次一份地完成 plan、tasks、implement；主 session 只啟動、等待與回報。

**Independent Test**: 在暫存的假專案放 2 份小 spec，以假的 `claude` 依序執行 `status` → `run`（plan、tasks、implement）→ `status`，確認依編號由小到大一次一份、前一份完成才開始下一份、每次 `run` 必須帶 `--model` 與 `--reason`、結果列出模型與理由；SKILL.md 的內容檢查確認主 session 沒有親自做 plan、tasks 或程式碼的指示。

### Tests for User Story 1

- [X] T014 [US1] 在 `tests/unit/test_sdd_drive.py` 加入 `status` 的測試（contracts/cli.md「status」；FR-003、FR-008、FR-014；spec.md US1-1、US1-4、Edge Cases）：輸出的鍵與順序固定；前置條件與 `reason` 的優先順序（`dependency`、`speckit-missing`、`speckit-incomplete`（`missing` 列出缺少的 `speckit-plan`、`speckit-tasks`、`speckit-implement`）、`no-specs`、`claude-missing`、`conflict`、`state-unreadable`）；`claude` 以 `shutil.which` 或 `SDD_DRIVE_CLAUDE` 解析；`specs[]` 每份的 `state`、`next_phase`、`baseline`、`tasks_total`、`tasks_open`、`failures`；`next` 只由第一份 `state` 不是 `done` 的 spec 決定、後面的 spec 一律不處理（兩份 spec 時第一份未完成則 `next.spec` 是第一份）；`next.action` 為 `run`（附 `phase`、`branch`、`failures`、`hints`：`requirements`、`user_stories`、`plan_bytes`、`contracts`、`tasks_total`、`tasks_open`、`phase_failures`、`models_used_this_run`）、`wait`、`none`（其餘 `next` 欄位為 `null`）；`git: false`、`dirty`、`leftovers`；`status` 不寫入任何檔案（前後檔案樹相同）
- [X] T015 [US1] 在 `tests/unit/test_sdd_drive.py` 加入 `brief` 的測試（contracts/skill.md「子 session 的工作說明」；FR-005、FR-006、FR-016、FR-023；research.md D12）：對 plan、tasks、implement、check 四個階段各印出純文字，並逐一斷言該表中每個事項都出現（目標只做這一份 spec 的這一個階段與 spec 目錄、分支；以 Skill 工具呼叫的 skill 名稱與 MUST NOT 手寫產物；不提問、不等核可、技術決定依 constitution 並記下理由；需求矛盾時以 `failed`、`kind: requirements` 回報且 MUST NOT 修改 spec.md 或 constitution；MUST NOT 修改 Spec Kit 的範本、腳本與 `speckit-*` skill、其他 spec 的資料夾與 `.specify/sdd-drive/`；plan 的 `**Testing**:` 反引號指令；tasks 的 Notes 與任務行格式；implement 只做未勾選、做完就勾選、不得刪除改寫合併、做不到時 `blocked-task`、完成前執行腳本填入的測試指令且新測試不得依賴執行順序；check 唯一的寫入是 `speckit-converge` 在 tasks.md 末尾附加的段落、不得修正問題、有附加時一個只含該檔的 commit、沒有發現時不得有任何 commit；git 規則（commit、不得 push／切換分支／amend／rebase／reset／merge／stash／clean）；非 git 時不 commit；接續時先重新檢查檔案狀態；機密不得寫入；結構化回報，check 另回報 `convergence`）；工作說明以 `.` 表示專案根目錄、不含絕對路徑；`--spec` 不存在時 `reason: "usage"`；`brief` 不寫入任何檔案
- [X] T016 [US1] 在 `tests/unit/test_sdd_drive.py` 加入 `run` 準備階段的測試（contracts/cli.md「run」步驟 1–8；FR-001、FR-012、FR-015、FR-019；`data-model.md` 的 `launch`、`attempts[].model`、`attempts[].reason`）：缺少 `--model` 或 `--reason`、`--reason` 超過 300 字元或多行 → `usage`；`--reason` 符合機密樣式 → `reason: "secret"` 且不寫入；前置條件失敗（`speckit-*`、`claude-missing`、`conflict`、`state-unreadable`）不寫入嘗試；鎖被持有 → `running`；指定的 `--spec`／`--phase` 不是 `status` 的 `next` → `not-next`；有 `dirty` 且不是 `leftovers` → `dirty`（列出路徑、檔案內容不變）；`branch-diverged`；成功時 `.specify/feature.json` 的 `feature_directory` 被設為 `specs/<dir>`、寫入一筆 `outcome: null` 的嘗試與 `launch` 記號、殘留的 `cancel` 檔案被刪除；`run` 不 commit、不 push、不 stash
- [X] T017 [US1] 在 `tests/unit/test_sdd_drive.py` 加入 driver 成功路徑與 `watch` 的測試（contracts/cli.md「driver」步驟 1–5、「watch」；FR-002、FR-004、FR-020、SC-001、SC-008；research.md D1、D4、D12、D13、D18）：以假的 `claude` 驗證傳給它的 argv（`-p`、`--output-format stream-json`、`--verbose`、`--model <model>`、`--session-id <uuid>`、`--json-schema`、`--permission-mode acceptEdits`、`--permission-prompts none`、`--allowedTools Bash Skill`、`--disallowedTools AskUserQuestion "Bash(git push*)"`）與 stdin 的工作說明（等於 `brief` 的輸出加上腳本填入的值）；`plan`／`tasks`／`implement` 各階段成功後 `succeeded`，且 plan 或 tasks 仍是範本時為 `verify-failed`（`plan-missing`／`tasks-missing`，FR-007）；`model_used` 取自結果的 `modelUsage` 鍵；`worktree` 指紋與（tasks 成功時）`task_ids`（`data-model.md` 的 `attempts[].task_ids`）被寫入；driver 取得鎖後清除 `launch`、寫入 `driver`、結束前清除；driver 不開始下一個階段；`watch` 的 `status`（`finished`、`running`、`launch-failed`）、`attempts[]` 的欄位（含 `model`、`model_used`、`reason`、`duration_seconds`、`permission_denials`）、`state_after`、`failures`；沒有 driver 且最後一筆已有結果時回報該筆、連嘗試都沒有時 `no-driver`；`--minutes` 範圍 1–115；兩份 spec 的完整序列（第一份的 plan→tasks→implement→測試之後才輪到第二份）以 `status` 的 `next` 驗證（FR-008）
- [X] T018 [P] [US1] 在 `tests/unit/test_sdd_drive_skill.py` 加入 `SKILL.md` 的 frontmatter、通則與階段 1 的內容檢查（以關鍵字與段落順序，不比對完整文字；contracts/skill.md「SKILL.md 的 frontmatter」與通則 1–11；FR-001、FR-002、FR-004、FR-013、FR-014、FR-018、FR-019、SC-001、SC-006、SC-007）：frontmatter 只有 `name: sdd-drive`、英文 `description`、`disable-model-invocation: true`，沒有其他欄位（沒有 `argument-hint`）；內文沒有中日韓文字、絕對路徑、信箱、`Orca`；腳本一律以 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_drive.py"` 執行；通則 1（`never run`、`speckit-implement`、`do not take over`）、2（`status`、`memory`）、3（`sdd-drive-state.json`）、4（`run_in_background`、`7200000`、`watch`）、5（`do not ask`）、6（`never push`）、7（`uncommitted`）、8（`model`、`reason`、`sonnet`、`opus`，且不得每個子 session 都用最強的模型）、9（`secret`）、10（`unexpected`）、11（`language`）；階段 1 逐一涵蓋該表的 16 列結果（`dependency`、`speckit-missing`、`speckit-incomplete`、`no-specs`、`claude-missing`、`conflict`、`state-unreadable`、`running` 的 `running`／`resuming`、`running` 的 `waiting`、只有 `launch`、`last_attempt` 的「你不在時」回報、`finalize`、`dirty` 且非 leftovers、`none`、`git: false`、`run`／`resume`／`test` 的宣告），每個失敗結果都有「停止」且沒有開子 session；順序：`status` → 表 → 宣告 → 階段 3 或 4；SKILL.md 沒有任何指示要求主 session 呼叫 `speckit-*` 或寫入 plan、tasks、程式碼

### Implementation for User Story 1

- [X] T019 [US1] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `status`（依 T014；contracts/cli.md「status」；`hints` 依 research.md D3；`next` 只取第一份未完成的 spec；`running`、`driver`、`running_attempt`、`last_attempt`、`dirty`、`leftovers`、`pending_finalize` 欄位依 data-model.md「下一步」；只讀）
- [X] T020 [US1] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `brief` 與固定的英文工作說明範本（依 T015；contracts/skill.md「子 session 的工作說明」；research.md D12；同一個函式供 `run` 使用；可計算的值：專案根目錄以 `.`、spec 目錄、分支、階段、skill 名稱、測試指令、是否為 git、是否為接續；含回報用的 JSON Schema，`data-model.md`「子 session 的回報」）
- [X] T021 [US1] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `run` 的準備階段與脫離啟動（依 T016；contracts/cli.md「run」步驟 1–8；FR-001、FR-012、FR-015；`data-model.md` 的 `launch`、`attempts[].session_id`（`uuid4`）、`attempts[].model`、`attempts[].reason`、`attempts[].auto`）：兩層啟動 `_drive --token`（Linux 以 `start_new_session=True`、Windows 以 `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` 並在可用時加 `CREATE_BREAKAWAY_FROM_JOB`，標準輸入輸出接空裝置）；啟動失敗時記為 `launch-failed`；準備完成後接 `watch`
- [X] T022 [US1] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 driver 的成功路徑（依 T017；contracts/cli.md「driver」步驟 1–5 的 `succeeded` 與產物檢查、7；research.md D1、D4、D12、D13）：以阻塞方式取得鎖並確認 `launch.token`、寫入 `driver`；以 `subprocess` 啟動 `claude`（提示走 stdin，不經 shell）；逐行解析 stream-json 只保留結果物件與限額資訊、stderr 丟棄、完整輸出不寫入檔案；`structured_output` 以同一份 Schema 再驗證；`plan`／`tasks` 的產物檢查（不是範本，D5）；`implement` 的完成檢查留待 US3；寫入 `attempts[].outcome`、`model_used`、`worktree`、`task_ids`、`report`；`SDD_DRIVE_TEST_TIMING` 控制輪詢間隔
- [X] T023 [US1] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `watch`（依 T017；contracts/cli.md「watch」；只讀；等待條件與 `status` 欄位、`attempts[]` 輸出、`state_after`、`failures`；每個等待中的嘗試只回報一次；`--minutes` 預設 110）
- [X] T024 [US1] 建立 `home/skills/sdd-drive/SKILL.md`（英文），先寫 frontmatter、通則與階段 1：frontmatter 依 contracts/skill.md（`name`、英文 `description`、`disable-model-invocation: true`，沒有其他欄位）；通則 1–11（通則 12、13 由 T050 寫入）；階段 1 的 16 列結果與宣告（含 `baseline: true` 的 spec 只測試、不做對照檢查的說明）；所有腳本以 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_drive.py" <command>` 在專案根目錄執行。內文 MUST NOT 含中日韓文字、絕對路徑、信箱、`Orca`。完成後 T018 的檢查應通過
- [X] T025 [US1] 在 `home/skills/sdd-drive/SKILL.md` 寫階段 3（`run`）的骨架與階段 3B（`watch`）（contracts/skill.md 階段 3、3B；FR-002、FR-004、FR-008、FR-020）：順序 `status` → 決定模型與理由（通則 8）→ 以背景執行 `run --spec … --phase … --model … --reason …` → 等待通知 → 讀取輸出 → 對 `attempts` 的每一筆以一兩行回報 spec、階段、`outcome`、`auto`、要求的模型與 `model_used`、理由；本任務寫入的結果列：`succeeded`（回到開頭先 `status`、不等核可）、`status: running`、`status: launch-failed`、`outcome: launch-failed`、`reason: secret`、`running`、`pending-finalize`／`not-next`、`dirty`、`branch-diverged`、`speckit-*`／`claude-missing`／`conflict`／`state-unreadable`、`os-error`、背景指令沒有輸出 JSON；階段 3B 的 `no-driver`、取消要求（指向階段 6）、等待期間維護者輸入其他訊息。把 T018 中對應階段 3 與 3B 的檢查補上並確認通過

**Checkpoint**: US1 可獨立運作——兩份 spec 的 plan、tasks、implement 以假的 `claude` 依序完成，`status`／`brief`／`run`／`watch` 的測試與 SKILL.md 的內容檢查通過

---

## Phase 4: User Story 2 - 確認真的完成才往下 (Priority: P1)

**Goal**: 「完成」＝任務全部勾選、主 session 親自（經腳本）執行測試通過，且對照檢查（`speckit-converge`）沒有找到漏做；範本不算已產生；導入前已完成的 spec 是既有的基準，只測試、不檢查。

**Independent Test**: 在暫存假專案安排：一份 spec 留下未勾選任務或失敗的測試 → 不被判定完成、後面的 spec 沒有開始；一份任務全勾、測試通過但對照檢查附加了任務 → 不完成、停止並列出 `findings`；既有的基準只執行測試就完成、不開 check。

### Tests for User Story 2

- [X] T026 [US2] 在 `tests/unit/test_sdd_drive.py` 加入 `test` 指令的測試（contracts/cli.md「test」；FR-007、SC-002；research.md D5、D6；`data-model.md` 的 `tests[].command`、`tests[].exit_code`、`tests[].head`、`tests[].tasks_hash`、`tests[].spec`）：`--spec` 必須是 `next.action: test` 的 spec（`not-next`）；`pending-finalize`、`dirty`、`running` 同 `run`；plan.md 沒有可用測試指令 → `no-test-command`（含 `N/A`／`none`／`TBD`、命中機密樣式時 `detail` 不含值、不執行）；以 shell 在專案根目錄執行、stdin 為空；結束碼 0 → 為 `covers` 中每一份 spec 寫入 `exit_code: 0` 的紀錄（含當時的 HEAD，非 git 時 `null`）、非 0 → 只為 `--spec` 寫入；`output_tail` 為最後 40 行且每行先做機密掃描（命中的行以 `(line not shown: looks like a secret)` 取代）；`passed`、`duration_seconds`；同一次測試為連續、指令相同的多份 spec 記錄通過；測試輸出不寫入任何檔案
- [X] T027 [US2] 在 `tests/unit/test_sdd_drive.py` 加入完成判定與既有的基準的測試（data-model.md「spec 的狀態」的 `done`／`implementing` 各列；FR-007、FR-008、FR-023、FR-024、FR-025、SC-002；research.md D22、D23）：有未勾選的任務 → `implementing`／`implement`、且 `next` 停在該 spec 不開始下一份；全部勾選但沒有測試紀錄 → `implementing`／`test`；全部勾選且有目前 `tasks_hash` 與目前 HEAD 下通過的測試紀錄、沒有 `check` 成功紀錄 → `implementing`／`check`（非 git 時只比 `tasks_hash`）；有 `check` 的 `succeeded`／`converged` 且其 `attempts[].tasks_hash` 等於目前雜湊 → `done`、之後不重複檢查；`tasks.md` 改變（補做時勾選、維護者手動處理）後先前的測試與檢查紀錄失效；測試之後有新的 commit → 先重新測試再檢查；測試失敗（最後一筆 `tests[].exit_code` 非 0）→ `failed`／`test` 且 `failures.test` 加一；既有的基準（`baseline` 內、沒有 `implement` 嘗試）：全部勾選且有目前 `tasks_hash` 的通過紀錄 → `done`，沒有則 `implementing`／`test`，**永遠不出現 `next_phase: check`**；基準的 spec 被加了新任務並經 `implement` 嘗試補做後改依一般規則（需要測試與 check）；`clear` 之後（`baseline: []`、`baseline_reset: true`）沒有任何基準；第一次 `status` 與寫入後的基準清單一致；每份 spec 的 `status` 輸出附 `baseline: true|false`；同一專案多份既有的基準由一次 `test` 記錄通過（`covers`）
- [X] T028 [US2] 在 `tests/unit/test_sdd_drive.py` 加入 check 階段的測試（contracts/cli.md「driver」步驟 2、4；FR-007、FR-023、FR-024；research.md D22；`data-model.md` 的 `attempts[].convergence`、`attempts[].appended`、`attempts[].task_ids`、`attempts[].tasks_hash`）：driver 在啟動前記下 `tasks.md` 內容與 HEAD；以假的 `claude` 的各情境驗證——`tasks.md` 不變且沒有任何 commit → `succeeded`、`convergence: converged`（立即 `done`、不重複檢查）；子 session 說 `tasks-appended` 但檔案不變 → `verify-failed`／`check-no-tasks`；`tasks.md` ＝ 原內容＋合格的 Convergence 段落（空行、一行 `## Phase N: Convergence`、未勾選的 `- [ ] Tnnn` 任務與縮排續行、新編號都大於原最大編號）且 commit 與工作區只動到該檔 → `gaps-found`、`convergence: tasks-appended`、`appended` 為新編號、`task_ids` 併入、`failures.check` 加一、`next` 回到 `implementing`／`implement` 而不是 `failed`；子 session 說 `converged` 但檔案有合格附加 → 以檔案為準 `gaps-found` 並記 `detail.code: report-mismatch`；改寫或勾選既有任務 → `verify-failed`／`check-rewrote-tasks`；動到程式碼或 plan.md → `check-touched-files`（`detail.paths`）；動到 spec.md 或 constitution → `protected-changed`；附加後未 commit → `uncommitted`；push → `pushed`；以上都不還原；`gaps-found` 後再次執行：補做 → 測試 → 再檢查，找到漏做不會自行循環（每一次停止）；`watch` 的 `findings`（從 `tasks.md` 附加段落解析 `id`、`text`、`source_ref`、`gap_type`，解析不出時兩者為 `null`；`text` 機密取代且最多 300 字元、最多 50 項並附 `findings_total`；其他情況為 `null`）；既有的基準不開 check 子 session；`next` 為 `run` 且 `phase: check` 時 `hints` 附 `check_failures`
- [X] T029 [P] [US2] 在 `tests/unit/test_sdd_drive_skill.py` 加入 SKILL.md 階段 4 與對照檢查相關列的內容檢查（contracts/skill.md 階段 4、階段 3 的 `succeeded`（`phase: check`）／`gaps-found`／`verify-failed` 的 check 相關說明、通則 1、8；FR-007、FR-023、FR-024、FR-025、SC-002）：階段 4 順序 `status` → `next.action: test` → 背景執行 `test --spec` → 依表，字樣 `do not trust`；逐一涵蓋 6 列（`passed: true` 且 `baseline: true` → 不做對照檢查並回到開頭、`passed: true` 其他 → 下一步是 check、`passed: false` → 停止並回報 spec／測試指令／結束碼／`output_tail`／失敗次數、`no-test-command` → 不判定完成並停止、`running`／`pending-finalize`／`not-next`／`dirty` 同階段 3、背景指令沒有輸出 JSON → 階段 1）；階段 3 含 `gaps-found` 列（停止、不自動修正、不開始後面的 spec、以 `findings` 逐項列出並註明超過 50 項的總數、說明已附加到 tasks.md 並 commit、再次 `/sdd-drive` 會先補做再重新測試與檢查、維護者可自行在 tasks.md 處理某項、`report-mismatch` 時以檔案為準）、check 的 `succeeded`／`converged` 列（判定完成並開始下一份）、`check-no-tasks`／`check-rewrote-tasks`／`check-touched-files` 三個 `detail.code` 的說明；通則 1 禁止主 session 呼叫 `speckit-converge`；通則 8 的 check 預設 `opus`

### Implementation for User Story 2

- [X] T030 [US2] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `test` 指令（依 T026；contracts/cli.md「test」；research.md D6；`data-model.md` 的 `tests[]` 全部欄位；以 shell 執行——Linux `/bin/sh`、Windows `cmd.exe`，不設逾時；`covers` 的計算依 research.md D5；輸出的機密掃描；持有鎖期間執行）
- [X] T031 [US2] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 補上 spec 狀態表中依賴測試紀錄、對照檢查與基準的列、與 `status` 的對應欄位（依 T027；data-model.md「spec 的狀態」「下一步」；FR-007、FR-024、FR-025；`data-model.md` 的 `baseline`、`baseline_reset`、`tests[].tasks_hash`、`tests[].head`、`attempts[].convergence`、`attempts[].tasks_hash`）：`next_phase` 為 `test`／`check` 的判定、`next.action: test` 附 `test_command` 與 `covers`、`next.phase: check` 附 `check_failures`、既有的基準規則（凍結、有 `implement` 嘗試即不再是基準）；失敗的疊加與 `failures` 的計算留待 T038
- [X] T032 [US2] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 的 driver 實作 check 階段的判定（依 T028；contracts/cli.md「driver」步驟 2、4；research.md D22；`data-model.md` 的 `attempts[].convergence`、`attempts[].appended`、`attempts[].task_ids`、`attempts[].tasks_hash`）：啟動前記下 `tasks.md` 內容與 HEAD；結束後依序以檔案判定 `converged`、`gaps-found`、`report-mismatch`、`check-no-tasks`、`check-rewrote-tasks`、`check-touched-files`、`protected-changed`、`pushed`、`uncommitted`；不還原；附加的任務編號併入 `task_ids`
- [X] T033 [US2] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 的 `watch` 實作 `findings` 的解析（依 T028；contracts/cli.md「watch」；內容取自檔案，不取自子 session 的輸出；每項 `text` 機密取代、最多 300 字元、最多 50 項並附 `findings_total`）
- [X] T034 [US2] 在 `home/skills/sdd-drive/SKILL.md` 寫階段 4（`test`）並在階段 3 的表加入 `gaps-found`、check 的 `succeeded`／`converged`、check 相關 `detail.code` 的說明（依 T029；contracts/skill.md 階段 4 的 6 列與階段 3 對應列；主 session 親自經腳本執行測試、不採信子 session 的說法）；完成後 T029 的檢查通過

**Checkpoint**: US1 與 US2 都可獨立測試——完成的判定只依檔案、親自執行的測試與對照檢查的結果

---

## Phase 5: User Story 3 - 失敗時停止並回報 (Priority: P1)

**Goal**: 任何步驟失敗都停止整個流程、不跳過、不開始後面的 spec；回報 spec、步驟、原因與已完成／尚未開始；子 session 異常結束時依檔案的實際狀態回報中斷；SKILL.md 與結束報告涵蓋每一種結果。

**Independent Test**: 安排第 2 份 spec 必定失敗（假的 `claude` 回報 `failed`，或留下不合規的檔案狀態），確認第 1 份完成、第 2 份回報失敗與原因、第 3 份完全沒有開始；子 session 沒有結果就結束時 `finalize` 記為 `interrupted`。

### Tests for User Story 3

- [X] T035 [US3] 在 `tests/unit/test_sdd_drive.py` 加入失敗分類與驗證的測試（contracts/cli.md「driver」步驟 4；FR-006、FR-007、FR-009、FR-015、FR-016、SC-003；research.md D4、D9、D10、D11、O1）：`failed`（`structured_output.status: failed`，`failure.kind` 五種與 `step`／`reason` 被記錄，且計入失敗）；`verify-failed` 的每個 `detail.code`——`plan-missing`、`tasks-missing`、`tasks-unfinished`（implement 後仍有未勾選任務）、`tasks-removed`（任務編號比 tasks 階段記下的 `task_ids` 少）、`protected-changed`（改動 spec.md、constitution、Spec Kit 範本／腳本／`speckit-*` skill，列出路徑、不還原）、`pushed`（remote-tracking refs 改變，以暫存的 bare remote）、`uncommitted`（成功卻留下未提交的變更，不替它 commit、不捨棄）；`blocked-task` 回報會列出任務編號；失敗的疊加：該 spec 在 `next_phase` 上最後一筆嘗試是 `failed` 或 `verify-failed` → `state: failed`、`next_phase` 不變、`next` 仍停在同一份（SC-003：第 2 份失敗後第 3 份被開始的數量為 0）；`failures` 只計 `failed`、`verify-failed`、`gaps-found` 與測試失敗；再次執行時從失敗的步驟重試；`run` 結束碼為 0 即使子 session 失敗；`attempts[].report` 與 `detail.text` 的機密取代；`permission_denials` 只列工具名稱（去重、不含參數）
- [X] T036 [US3] 在 `tests/unit/test_sdd_drive.py` 加入非失敗的結束與 `finalize` 的測試（FR-009、FR-010、FR-021；contracts/cli.md「finalize」；research.md D4、D8；spec.md US3-3）：`launch-failed`（找不到 `claude`）、`api-error`（401、404、`error_max_turns`，含 `detail.text`）、`interrupted`（沒有可解析的結果物件，`detail.code: no-result`；有結果卻沒有 `structured_output`，`detail.code: no-report`）都不計入 `failures`、保留進度；最後一筆嘗試 `outcome: null` 且鎖未被持有（或 `driver` 不為 `null`、或 `launch` 超過 60 秒）→ `status` 的 `pending_finalize: true`、`next.action: finalize`（附該嘗試的 `spec`、`phase`）、`run`／`test` 以 `pending-finalize` 拒絕；`finalize` 把它記為 `interrupted`（`detail.code: no-result`）並寫入目前的工作區指紋、清除 `launch` 與 `driver`、輸出 `state_after`；沒有需要處理的嘗試 → `nothing-to-finalize`；鎖被持有 → `running`；`finalize` 冪等
- [X] T037 [P] [US3] 在 `tests/unit/test_sdd_drive_skill.py` 加入階段 2、階段 3 的失敗與中斷列、階段 5 的內容檢查（contracts/skill.md 階段 2、階段 3 的對應列、階段 5；FR-009、FR-010、FR-016、SC-005）：階段 2 逐一涵蓋 5 列（`lost` 時依通則 13 回報、成功（其他）回報流程曾經中斷與進度並說明下次會接續且不計入失敗、`running`、`nothing-to-finalize` 回階段 1、其他依通則 10）；階段 3 的 `failed`（停止整個流程、不開始後面的 spec、回報 spec／階段／`failure.kind`／`failure.step`／`failure.reason`／累計失敗次數、`requirements` 時請維護者修正 spec 或 constitution、`blocked-task` 時列出任務編號、子 session 若留下未提交的變更由維護者決定、修正後再次 `/sdd-drive` 會從該階段重試）、`verify-failed` 的每個 `detail.code`（`plan-missing`、`tasks-missing`、`tasks-unfinished`、`tasks-removed`、`protected-changed`、`pushed`、`uncommitted`）、`api-error`、`interrupted`、`resume_failed`、`permission_denials`；階段 5 的結束報告四項（每份 spec 的狀態、停止的原因、每個子 session 的 spec／階段／`outcome`／要求的模型與實際模型／理由、下一步與提醒維護者自行 push 並確認兩個平台的 CI 與 tasks.md 的 Notes），字樣 `final report`，且維護者只讀報告就知道是哪一份、哪個步驟與原因

### Implementation for User Story 3

- [X] T038 [US3] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作失敗分類、驗證與失敗的疊加（依 T035；contracts/cli.md「driver」步驟 4；research.md D4、D9–D11；`data-model.md` 的 `attempts[].outcome`、`attempts[].detail`（`code` 的列舉、`paths`、`text`）、`attempts[].report`）：`failed`／`verify-failed` 的判定順序（產物、任務編號沒有減少、受保護檔案未變、remote-tracking refs 未變、工作區乾淨，第一個不符合的成為 `detail.code`）；`failures` 的計算與 `state: failed` 的疊加（data-model.md「spec 的狀態」）；`watch` 輸出的 `failure`（`kind`、`step`、`reason`、`tasks`）與 `counts_as_failure`；不還原任何檔案
- [X] T039 [US3] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `launch-failed`、`api-error`、`interrupted` 的分類與 `finalize`（依 T036；contracts/cli.md「finalize」；research.md D4、D8；`data-model.md` 的 `attempts[].outcome`、`attempts[].worktree`、`launch`、`driver`）：這三者不計入失敗；`status` 的 `pending_finalize` 與 `next.action: finalize`；`run`／`test` 的 `pending-finalize` 拒絕；`finalize` 冪等
- [X] T040 [US3] 在 `home/skills/sdd-drive/SKILL.md` 寫階段 2（`finalize`）、階段 3 的失敗與中斷列、階段 5（結束報告）（依 T037；contracts/skill.md 階段 2、階段 3 的 `failed`、`verify-failed`、`api-error`、`interrupted`、`resume_failed: true`、`permission_denials` 列、階段 5；通則 10 的未預期結果）；完成後 T037 的檢查通過

**Checkpoint**: US1、US2、US3 都可獨立測試——失敗時停止、回報具體、不跳過

---

## Phase 6: User Story 4 - 中斷後接續 (Priority: P2)

**Goal**: 中斷（失敗、關機、維護者中止、用量上限）之後再次 `/sdd-drive` 從未完成的地方接續，已完成的 spec 與階段不重做；用量上限不算失敗、不計入重試，有重置時間時由 driver 在重置後自動接續一次，再次中斷或沒有重置時間時停止並回報；`clear` 重設紀錄。

**Independent Test**: 在第 2 份 spec 的 tasks 之後中止，再次執行，第 1 份沒有被重做、第 2 份從 implement 開始；假的 `claude` 回報有重置時間的用量上限時 driver 在（縮短的）重置後以同一 session `--resume` 自動接續一次且失敗次數不變；再次用量上限時停止。

### Tests for User Story 4

- [X] T041 [US4] 在 `tests/unit/test_sdd_drive.py` 加入手動接續的測試（FR-011、FR-022、SC-004；contracts/cli.md「run」步驟 3–4；data-model.md「下一步」「工作區（git）」；spec.md US4-1 至 US4-4）：已完成的 spec 不重做、從第一份未完成的 spec 繼續；有 plan 沒有 tasks → 下一步 `tasks`、不重新產生 plan；失敗的 spec 修正後從失敗的步驟重試；所有 spec 都完成 → `next.action: none` 且不開子 session；`next.action: resume`（最後一筆嘗試是 `usage-limit`／`api-error`／`interrupted` 且有 `session_id`，附 `session_id`、`model`、`last_outcome`、`limit`、`auto_resume`）；`run --resume` 以同一 `session_id` 傳 `--resume` 給假的 `claude`、沿用 `next.model`、工作說明含接續的指示；`next.action` 不是 `resume` 卻帶 `--resume` → `not-next`；`--resume --fresh` 開新 session（用於 `resume_failed`），`--fresh` 單獨出現 → `not-next`；假的 `claude` 的 `--resume` 失敗 → `resume_failed: true` 且不計入失敗；`leftovers`（`dirty` 不為空、下一步是 `resume` 或 `finalize`、最後一筆嘗試的 `worktree` 等於目前指紋）允許接續、指紋不同則 `dirty`；`finalize` 記錄 `interrupted` 時一併寫入目前的指紋；接續不重做已勾選的任務（以 `status` 的 `tasks_open` 驗證）
- [X] T042 [US4] 在 `tests/unit/test_sdd_drive.py` 加入用量上限判讀的測試（FR-021、SC-009；contracts/cli.md「driver」步驟 3–5；research.md D4、D17、D21；`data-model.md` 的 `attempts[].limit`）：`usage-limit` 的判定（結果物件 `is_error: true` 且 `api_error_status` 為 429，或 `result` 文字符合 `usage limit`／`hit your limit`／`rate limit` 不分大小寫）；`limit` 的計算：被拒絕的時間窗有 `resetsAt` → `waitable: true`、`resets_at` 為被拒絕時間窗的最大值、`types` 屬於列舉；只有 `overage`、缺 `resetsAt`、只有文字、花費上限加 5 小時時間窗的組合、無法判斷 → `waitable: false`、`resets_at: null`；`overage_status` 的值；`limit` 只由腳本計算的欄位組成、訊息文字不解析、`rate_limit_info` 的其他欄位與完整輸出不保存；用量上限不計入 `failures`、重試次數與中斷前相同、保留已完成的進度（含尚未提交的檔案，不 stash、不 reset、不 checkout）
- [X] T043 [US4] 在 `tests/unit/test_sdd_drive.py` 加入自動接續、`cancel` 與 driver 存活的測試（FR-012、FR-021、FR-022、SC-009、SC-010；contracts/cli.md「driver」步驟 6–7、「cancel」；data-model.md「自動接續的狀態轉移」；research.md D18–D20；`data-model.md` 的 `attempts[].auto`、`attempts[].auto_resume`、`driver`；以 `SDD_DRIVE_TEST_TIMING` 縮短等待，以假的 `resetsAt` 模擬重置時間，不改變判斷規則）：可等待的 `usage-limit` → `auto_resume: waiting`、`driver.phase: waiting`、`driver.waiting_until` ＝ `resets_at` 加緩衝；等待期間 `status` 為 `running: true` 且附 `driver.phase`、`waiting_until`、`limit`；等待期間第二個 `run`／`test` → `running`（FR-012）；到時工作區指紋相同 → 新嘗試 `auto: true`、`resume: true`、同一 `session_id` 與 `model`、`reason` 為 `Automatic resume after the usage limit reset.`、`auto_resume: started`，成功後 driver 結束且**不開始下一個階段**；自動接續後再次 `usage-limit` → `already-auto`、停止；`waitable: false` → `not-waitable` 且 driver 結束；自動接續只一次（`auto: true` 的嘗試不再自動接續）；維護者再次啟動的 `run`（`auto: false`）使之後遇到可等待的上限時可再自動接續一次；`cancel`：`driver.phase` 不是 `waiting` → `not-waiting`，否則建立 `cancel` 檔案、輸出 `cancel_requested: true` 與 `waiting_until`，driver 看到後 `cancelled`、刪除該檔案、不接續（接續前再檢查一次）；等待期間工作區被改動 → `skipped-changed`；driver 消失（鎖釋放、`driver` 仍有記錄）→ `pending_finalize`，`finalize` 把 `waiting` 改為 `lost`；`watch` 在 driver 進入等待時回報一次（`status: waiting`、`waiting_until`）並在結束時回報全部嘗試（被中斷的與自動接續的）；`resets_at` 已過時只等緩衝；driver 存活：以「終止啟動 `run` 的行程樹」（Linux：`os.killpg` 加 `os.kill`；Windows：`taskkill /T /F`）後 driver 仍存活並完成（兩個平台的測試都要能執行，此項由 T059 在 Windows CI 確認）
- [X] T044 [US4] 在 `tests/unit/test_sdd_drive.py` 加入 `clear` 的測試（contracts/cli.md「clear」；FR-025；research.md D23；`data-model.md` 的 `baseline`、`baseline_reset`）：鎖被持有、有 `driver` 或 `launch` → `running`；`own_dir` 為 `conflict` → `conflict` 且不刪除；`state.json` 無法讀取時仍可執行（不讀舊內容）；清除後 `state.json` 為空的紀錄（`attempts`、`tests` 為空、`baseline: []`、`baseline_reset: true`），刪除 `cancel` 與暫存檔，必要時建立 `.gitignore`，輸出 `{"cleared": true, "baseline_reset": true}`；清除後沒有任何 spec 是既有的基準（已勾選的 spec 都要測試與檢查）；冪等
- [X] T045 [P] [US4] 在 `tests/unit/test_sdd_drive_skill.py` 加入通則 12、13、階段 6 與用量上限列、接續列的內容檢查（contracts/skill.md 通則 12–13、階段 6、階段 3 的對應列、階段 1 的 `state-unreadable` 與 `clear`；FR-021、FR-022、SC-009、SC-010；research.md D20、D21）：通則 12（`automatic resume`、`once`；主 session 不自己等待重置、不排程喚醒（不得出現 `CronCreate` 作為手段）、不為用量上限自行再 `run --resume`；主 session 被擋下後稍後繼續時從階段 1 的 `status` 重新開始）；通則 13（每則用量上限回報含原因（不是失敗、未計入重試）、`limit.types`、`resets_at` 轉當地時間或說沒有重置時間、目前進度 `state_after`、會自動接續或需要維護者再輸入 `/sdd-drive`，字樣 `resets_at`）；階段 3 的 `status: waiting`、`not-waitable`、`already-auto`、`cancelled`、`skipped-changed`、自動接續成功、自動接續後的其他 `outcome`、`resume_failed`（`--resume --fresh` 一次）、主 session 自己曾被擋下的列；階段 6 的 3 列（`cancel_requested: true`、`not-waiting`、其他）與只在維護者明確要求時執行（字樣 `cancel`）；階段 1 的 `state-unreadable` 列說明清除後沒有任何 spec 是基準、MUST NOT 建議手動刪除 `.specify/sdd-drive/`

### Implementation for User Story 4

- [X] T046 [US4] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作手動接續（依 T041；contracts/cli.md「run」步驟 3–4；data-model.md「下一步」「工作區（git）」；research.md D8；`data-model.md` 的 `attempts[].resume`、`attempts[].session_id`、`attempts[].worktree`）：`next.action: resume`、`run --resume`／`--fresh` 的參數與 `not-next` 規則、`--session-id`／`--resume` 的選擇、`resume_failed` 的判定、`leftovers`、工作說明的接續指示
- [X] T047 [US4] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `usage-limit` 的判讀與 `limit` 的計算（依 T042；research.md D4、D17；`data-model.md` 的 `attempts[].limit`、`attempts[].outcome`）：stream-json 中只保留 `status: "rejected"` 的 `rate_limit_event.rate_limit_info` 與 assistant 訊息的 `api_error`／`api_error_params.rate_limit_info`；判斷不出來一律 `waitable: false`；不計入 `failures`
- [X] T048 [US4] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 driver 的自動接續、`cancel` 與等待期間的行為（依 T043；contracts/cli.md「driver」步驟 6–7、「cancel」；research.md D18–D20；`data-model.md` 的 `driver`、`attempts[].auto`、`attempts[].auto_resume`；FR-021、SC-010）：每 30 秒（測試時依 `SDD_DRIVE_TEST_TIMING`）以牆上時鐘檢查、等到 `resets_at` 加 120 秒、檢查 `cancel`、比對工作區指紋、寫入 `auto: true` 的新嘗試並回到啟動步驟；`status`／`watch`／`finalize`（`lost`）／`cancel` 對等待狀態的處理；driver 不開始下一個階段
- [X] T049 [US4] 在 `home/skills/sdd-drive/scripts/sdd_drive.py` 實作 `clear`（依 T044；contracts/cli.md「clear」；`data-model.md` 的 `baseline`、`baseline_reset`；只重寫 `state.json`、刪除 `cancel` 與暫存檔）
- [X] T050 [US4] 在 `home/skills/sdd-drive/SKILL.md` 寫通則 12、13、階段 6（`cancel`）、階段 3 的用量上限與接續列、階段 1 的 `state-unreadable` 列的 `clear` 說明（依 T045；contracts/skill.md 對應條目與列）；完成後 T045 的檢查通過

**Checkpoint**: 四個 user story 都可獨立運作；腳本的所有指令與 SKILL.md 的所有階段都已寫成

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: README、skill 資料夾的整體檢查、需求涵蓋的核對、SKILL.md 的通讀走查、腳本情境實跑、完整測試與 CI

- [X] T051 [P] 建立 `home/skills/sdd-drive/README.md`（繁體中文；contracts/skill.md「README.md」；FR-018、constitution 原則 VI）：涵蓋用途（spec 確認後一次做完 plan、tasks、implement、測試與對照檢查）、啟動方式（只能由維護者輸入 `/sdd-drive`）、會在什麼情況停止（失敗、對照檢查找到漏做、中斷、用量上限且沒有重置時間或再次中斷）、如何接續、不 push 與分支的做法（每份 spec 一個分支、後一份疊在前一份之上）、紀錄放在 `.specify/sdd-drive/`（不入庫）、子 session 使用 `claude -p`（只需要 Claude Code 與 uv）、模型的選擇原則、既有的基準只測試不做對照檢查、用量上限的自動接續與其代價（維護者不在場時仍會接續一次，research.md T9）、要重設紀錄用 `clear` 而不是手動刪除資料夾、不使用 Orca
- [X] T052 [P] 在 `tests/unit/test_sdd_drive_skill.py` 加入資料夾與 README 的檢查（contracts/skill.md「檔案」「README.md」；FR-013、FR-018）：`home/skills/sdd-drive/` 內只有 `SKILL.md`、`README.md`、`scripts/sdd_drive.py` 三個檔案；`SKILL.md` 英文、無中日韓文字、無絕對路徑與信箱、不提及 `Orca`（T018 已涵蓋，合併成一次完整檢查即可）；`README.md` 含繁體中文並涵蓋 T051 列出的各項關鍵字；腳本與工作說明沒有絕對路徑與信箱
- [X] T053 更新 repo 根目錄的 `README.md`（plan.md「Project Structure」；原則 VI）：更新「目前狀態」並新增 `/sdd-drive` 一節（6 個 SDD skill 到齊），敘述與 `home/skills/sdd-drive/README.md` 一致，不含機器路徑與信箱；不修改 `home/CLAUDE.md`
- [X] T054 執行 `uv run --with pytest pytest tests/unit/test_claude_md.py -v`，確認 `test_referenced_skills_exist_in_home_skills` 在 `home/skills/sdd-drive/SKILL.md` 存在後**不再 skip 並通過**（6 個被引用的 skill 都有 `SKILL.md`；plan.md「需求與驗證方式」）；若仍 skip 或失敗，查出原因並如實回報，不修改 `home/CLAUDE.md`
- [X] T055 逐條核對 plan.md「需求與驗證方式」表與本檔「FR 與 SC 的涵蓋」表：FR-001 至 FR-025 與 SC-001 至 SC-010 每一條都至少有一個測試或內容檢查任務實際涵蓋，列出每條對應的測試函式名稱；表中只能以人工驗收確認的部分（對話行為、真實子 session、用量上限的實際訊息、Windows 上 driver 撐過 Claude Code 終止背景指令）MUST NOT 為它們新增自動測試任務，只以「SKILL.md 含有該指示」的內容檢查涵蓋；缺少的補上測試或內容檢查（補在對應的測試檔，並於 commit 訊息說明）；若發現設計文件之間矛盾，向主代理提問，不自行修改設計文件
- [X] T056 依 `specs/008-sdd-drive/quickstart.md`「自動測試」，在 `mktemp -d` 建立的暫存假專案以**假的 `claude`**（`SDD_DRIVE_CLAUDE`）實跑 `uv run <repo>/home/skills/sdd-drive/scripts/sdd_drive.py`，逐一核對 contracts/cli.md 的輸出鍵與 `reason`，並修正與預期不符之處；**每個情境用新的暫存目錄**；情境：(1) 兩份 spec 的 `status` → `run` plan／tasks／implement → `test` → `run` check → 第二份（輸出的鍵與順序、`next` 的演進）；(2) 第 2 份失敗時第 3 份不開始；(3) 沒有結果就結束 → `pending_finalize` → `finalize` → `resume`；(4) 有重置時間的用量上限 → driver 等待與自動接續一次（以 `SDD_DRIVE_TEST_TIMING` 縮短）、`cancel`、`not-waitable`；(5) 對照檢查 `gaps-found` 的 `findings`；(6) 既有的基準只測試；(7) `clear` 後的 `status`；(8) 每個 `reason`（`usage`、`secret`、`running`、`not-waiting`、`no-driver`、`pending-finalize`、`not-next`、`dirty`、`branch-diverged`、`no-test-command`、`nothing-to-finalize`、`conflict`、`os-error`（可模擬者）、`dependency`、`speckit-missing`、`speckit-incomplete`、`no-specs`、`claude-missing`、`state-unreadable`）至少各觸發一次。MUST NOT 在這個 repo、真正的 `~/.claude` 或其他真實專案執行；MUST NOT 啟動真正的 `claude`；MUST NOT 讀取 `~/.claude/skills/`；quickstart.md「人工驗收」1–16 不在本任務範圍（見 Notes）
- [X] T057 **SKILL.md 通讀走查**（T056 之後、SKILL.md 全部寫完才做）：實作者以「沒有任何背景的讀者」身分，只依 `home/skills/sdd-drive/SKILL.md` 與它引用的指令輸出，**逐步對照 contracts/skill.md 走過 SKILL.md**，涵蓋**每個階段的每一種結果**（階段 1 的 16 列、階段 2 的 5 列、階段 3 的 28 列、階段 3B 的 4 列、階段 6 的 3 列、階段 4 的 6 列，總數以逐列計數為準，與 plan.md 所述的「61 種」若有出入，在回報中指出差異並向主代理提問，不自行修改設計文件；另加通則 10 與 12 在每個階段的行為與階段 5 的四項），確認：(1) 沒有死路——每個結果都有明確的下一步（繼續、回到某階段、停止），沒有「未定義」；(2) 沒有互相矛盾的指示（例如通則 1「主 session 只協調」與任何階段的實作、`running` 時不 `finalize` 與階段 2、`watch` 兩個主 session 同時推進、停止時是否說明進度與是否需要維護者再輸入 `/sdd-drive`）；(3) 沒有被取代後殘留的舊指示（舊階段編號、舊選項名稱、舊的 `reason` 值、`usage-limit` 的「不自動重試」舊說法）；(4) 提到的每個指令、參數、輸出欄位與 `reason` 值都與 contracts/cli.md 及**腳本的實際輸出**一致（T056 的實跑結果，不憑記憶）；(5) 階段間的交叉引用（階段 1 → 3／4、階段 3B → 3、階段 6 → 3B、通則 4 的 `watch`、通則 12 → 階段 1）指向存在且正確的段落；(6) 沒有要求 Claude 做 SKILL.md 禁止的事（親自 plan／tasks／implement／converge、手寫 `.specify/sdd-drive/` 或 `feature.json`、自己組 `claude` 指令、自己等待或排程、push、捨棄變更）；(7) 每種結果都對應到結束報告（階段 5）的某一項。把走查的結果寫進任務回報：列出每個階段走過的結果數量、發現的缺漏與矛盾及其修正（修正直接改 `SKILL.md`，並補上對應的內容檢查）；若沒有發現問題也要明說「走查 N 條路徑，沒有發現缺漏」。若發現 contracts/skill.md 本身與 cli.md 矛盾，向主代理提問。這是本清單中唯一不產生新功能、只做檢查的 SKILL.md 任務，不可省略
- [X] T058 執行完整測試 `uv run --with pytest pytest`，結束碼 0；執行 `uv run --with pytest pytest tests/unit/test_sdd_drive.py tests/unit/test_sdd_drive_skill.py tests/unit/test_claude_md.py -v` 並回報通過數與 skip 數；以亂序（例如 `-p no:randomly` 關閉與逆序各跑一次，或單獨執行各測試檔與各測試函式的抽樣）確認測試不依賴執行順序；確認 `git status` 中 `.specify/`（含 `.specify/feature.json`）、`specs/008-sdd-drive/` 的設計文件（`tasks.md` 除外）、`.github/workflows/ci.yml`、`tools/deploy.py`、`home/CLAUDE.md`、005 至 007 的腳本／`SKILL.md`／測試與 `~/.claude` 都沒有被這次的工作更動，這個 repo 內沒有 `.specify/sdd-drive/`；確認工作區沒有未提交的內容。Windows 上的結果由 T059 的 CI 確認（constitution 原則 II）
- [x] T059 **由主代理推送分支後處理，implement 的 worker 不執行這一項、不 push**：維護者授權推送後，確認 `.github/workflows/ci.yml` 的 `test`（`ubuntu-latest` 與 `windows-latest`）、`cross-platform-produce`、`cross-platform` 都通過；Windows 上需特別確認：driver 的脫離啟動與「終止啟動它的行程樹後仍存活」（T043）、檔案鎖（`msvcrt`）、輸出與紀錄逐位元組與 Linux 相同（LF、`/` 路徑）、測試指令經 `cmd.exe` 執行、工作區指紋在 CRLF 下穩定、資料夾與分支名稱沒有 Windows 不允許的字元；失敗時依紀錄修正後再確認（不新增或修改 CI job）

---

## FR 與 SC 的涵蓋

| 需求 | 涵蓋的任務 |
|---|---|
| FR-001 只由維護者啟動 | T018、T024、T016、T021、T052 |
| FR-002 主 session 不親自做 | T017、T018、T024、T025 |
| FR-003 依編號、一次一份 | T012、T013、T014、T019 |
| FR-004 不等核可 | T017、T018、T024、T025 |
| FR-005 技術選型依 constitution | T015、T020 |
| FR-006 透過 Spec Kit、不手寫 | T015、T020、T035、T038 |
| FR-007 完成的判定、範本不算 | T012、T013、T017、T022、T026、T027、T028、T030、T031、T032、T034 |
| FR-008 前一份完成才開始下一份 | T014、T017、T019、T027、T035、T038 |
| FR-009 失敗即停止 | T035、T036、T038、T039、T040 |
| FR-010 回報 | T033、T037、T040、T038 |
| FR-011 依檔案判定、不重做 | T006、T007、T012、T013、T041、T046 |
| FR-012 單一流程 | T008、T009、T016、T021、T043、T048 |
| FR-013 只需要 Claude Code | T018、T024、T052、T056 |
| FR-014 前置條件 | T014、T018、T019、T024、T025 |
| FR-015 不捨棄變更 | T010、T011、T016、T021、T035、T038、T041、T046 |
| FR-016 不改 constitution 與 spec | T015、T020、T035、T038 |
| FR-017 兩平台相同 | T004、T005、T043、T059 |
| FR-018 英文與繁中 README | T018、T024、T051、T052 |
| FR-019 逐次選模型 | T016、T017、T018、T021、T024 |
| FR-020 回報模型與理由 | T017、T022、T023、T025、T037、T040 |
| FR-021 用量上限不算失敗、自動接續一次 | T036、T042、T043、T045、T047、T048、T050 |
| FR-022 接續不重做 | T041、T043、T046、T048 |
| FR-023 對照檢查找到漏做即失敗 | T015、T020、T028、T029、T032、T033、T034 |
| FR-024 補做後重新測試與檢查 | T027、T028、T031、T032 |
| FR-025 既有的基準不檢查 | T006、T027、T031、T044、T049 |
| SC-001 指令數 1、問題數 0 | T017、T018、T024（通則 5）；Notes 人工驗收 1 |
| SC-002 完成後沒有未完成任務、失敗測試或未檢查 | T026、T027、T028、T030、T031、T032 |
| SC-003 失敗後編號在後的 spec 不開始 | T035、T038 |
| SC-004 接續後已完成的 spec 不重做 | T041、T046 |
| SC-005 只讀回報就知道原因 | T037、T040、T033 |
| SC-006 只需 Claude Code 與本專案 skill | T018、T052、T056；Notes 人工驗收 |
| SC-007 主 session 親自產生的 plan／tasks／程式碼為 0 | T018、T024；Notes 人工驗收 1 |
| SC-008 子 session 都列出模型與理由、不全用最強 | T016、T017、T018、T025；Notes 人工驗收 2 |
| SC-009 用量上限接續後不重做、重試次數不變 | T042、T043、T047 |
| SC-010 重置後自動接續、不超過 1 次 | T043、T045、T048、T050 |

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依賴 001 至 007 已在目前的分支；T001、T002、T003 可同時進行（T002 與 T003 不同檔案）
- **Foundational (Phase 2)**: 依賴 Setup（T002、T003）；T004 先於 T005；T006 先於 T007；T008 先於 T009；T010 先於 T011；T012 先於 T013；腳本的任務（T005、T007、T009、T011、T013）依序進行（同一個檔案），測試任務（T004、T006、T008、T010、T012）依序進行（同一個檔案）
- **US1 (Phase 3)**: 依賴 Foundational；T014 至 T017 先於 T019 至 T023；T018 先於 T024、T025；T024 先於 T025（同一個 SKILL.md）；T021 在 T020 之後（共用範本）、T022 在 T021 之後、T023 在 T022 之後
- **US2 (Phase 4)**: 依賴 US1 的 `run`、driver 與 `status`（T019、T021、T022）；T026 至 T028 先於 T030 至 T033；T029 先於 T034；T031 在 T013 之後、T032 在 T022 之後、T033 在 T023 與 T032 之後；T034 在 T025 之後
- **US3 (Phase 5)**: 依賴 US1 的 driver（T022）與 US2 的狀態表（T031）；T035、T036 先於 T038、T039；T037 先於 T040；T040 在 T034 之後（同一個 SKILL.md）
- **US4 (Phase 6)**: 依賴 US3 的 `finalize` 與失敗疊加（T038、T039）；T041 至 T044 先於 T046 至 T049；T045 先於 T050；T047 先於 T048；T050 在 T040 之後（同一個 SKILL.md）
- **Polish (Phase 7)**: 依賴 Phase 3 至 6；T051 與 T052 可同時進行；T052 在 T051 與所有 SKILL.md 任務之後才能全數通過；T053 在 T051 之後；T054 依賴 T024；T055 依賴 T050 與 T052；T056 依賴 T050；T057 依賴 T056、T055；T058 依賴 T057；T059 依賴 T058，且需要維護者授權推送

### Within Each User Story

- 測試先寫、先確認失敗，再實作
- 腳本的任務（`sdd_drive.py`、`test_sdd_drive.py`）依序進行；`SKILL.md` 的段落任務依序進行；`test_sdd_drive_skill.py` 的測試任務標 [P]（與腳本任務不同檔案），各自先於對應的 `SKILL.md` 任務完成

### Parallel Opportunities

- T001、T002、T003 可同時進行
- T018、T029、T037、T045 這些 `test_sdd_drive_skill.py` 的內容檢查（標 [P]）可與腳本任務同時撰寫；但各自要先於對應的 `SKILL.md` 任務完成
- T051、T052 可同時進行

### Parallel Example: User Story 1

```text
# 不同檔案，可同時進行：
Task: "T014 至 T017 status、brief、run 準備、driver 與 watch 的單元測試 in tests/unit/test_sdd_drive.py"
Task: "T018 SKILL.md 的 frontmatter、通則與階段 1 的內容檢查 in tests/unit/test_sdd_drive_skill.py"
```

---

## Implementation Strategy

### MVP First (US1)

1. 完成 Phase 1 與 Phase 2
2. 完成 Phase 3（US1）：`status`、`brief`、`run`、driver 成功路徑、`watch`、SKILL.md 的通則與階段 1、3、3B
3. **STOP and VALIDATE**: 單元測試與內容檢查通過；以假的 `claude` 的兩份 spec 序列在暫存目錄跑通（T056 情境 1）；真實子 session 的行為交給維護者以人工驗收確認

### Incremental Delivery

1. US2：`test`、完成判定、既有的基準、對照檢查——US1、US2、US3 都是 P1，合起來才是完整的主流程
2. US3：失敗分類、`finalize`、結束報告
3. US4：手動接續、用量上限的判讀與自動接續、`cancel`、`clear`
4. Polish：README、涵蓋核對（T055）、情境實跑（T056）、通讀走查（T057）、完整測試（T058）、CI（T059）

---

## Notes

- 每完成一個任務或一組相關任務就 commit（分支 `008-sdd-drive`，不 commit 到 `main`）；不 push，推送由主代理在維護者授權後進行（T059）。本 skill 自己「不 commit」主 session 的專案、由子 session commit（plan.md、research.md D11），這與實作本功能時的 commit 規則是兩回事
- 維護者已核可 plan.md「設計取捨」T1–T15（T5 納入對照檢查、T14 既有的基準不檢查、T15 多做的工作也停止流程），實作時照 plan 的寫法，不需要再確認；與任務直接相關者：每個階段一個子 session（T1，T017、T025）、測試指令取自 plan.md 的 `**Testing**:` 行（T2，T012、T026）、子 session 的 Bash 權限（T3，T017）、一律不 push（T4，T035）、中斷被發現時先回報再接續（T7，T036、T040）、自動接續的代價（T9–T13，T043、T048、T051）、既有的基準（T14，T027、T031、T044）、`unrequested` 也停止（T15，T028）
- **人工驗收不列為勾選任務**：quickstart.md「人工驗收（真實的子 session）」1–16 需要真實的 `claude`、已登入的 Claude Code 與部署，由維護者在合併並部署後，於暫存目錄的假專案進行並記錄結果與日期；不要拿這個 repo 或機器上其他真實的專案，也不要把測試專案留在機器上（結束後刪除暫存專案，`claude purge <暫存目錄>` 可清除紀錄）。項目：
  1. 兩份小 spec 一個指令跑完（US1、SC-001、SC-007、FR-020）、2. 分支疊加與不同模型（D11、SC-008）、3. 再輸入一次回報沒有待處理（US4-4）、4. 矛盾的 spec 以 `requirements` 失敗（US3、FR-016）、
  4a. 既有的基準只測試不檢查（FR-025）、4b. 對照檢查找到漏做與補做（US2-4 至 US2-6、FR-023、FR-024）、5. 中斷後接續（US3-3、US4、SC-004、T7）、6. 同時兩個主 session（FR-012）、
  7. 未提交的變更（FR-015）、8. 沒有測試指令（Edge Case）、9. 沒有 Spec Kit（FR-014）、10. 非 git 專案（Edge Case）、11. 有重置時間的用量上限與自動接續（FR-021、FR-022、SC-009、SC-010，research E9、E10；無法刻意製造，需實際遇到）、
  12. 沒有重置時間的上限（FR-021）、13. 等待期間取消（D20）、14. 等待期間關閉終端機（D20、T9）、15. Windows 上 driver 撐過 Claude Code 終止背景指令（原則 II、T10、E11）、16. Windows 上重複 1–3（原則 II、FR-017）。
  核心情境 1、4b、5 在 Windows 與 Linux 各做一次，其餘在任一平台做一次即可
- 自動測試只證明「腳本的行為」與「必要的指示存在於 SKILL.md」，不證明 Claude 會照做（plan.md「需求與驗證方式」、research.md D15）：對話行為（模型與理由的品質、回報的語氣與完整度、通則的遵守）、真實子 session 的行為、用量上限的實際訊息（`rate_limit_info` 的形狀依程式內容推得，無法實測，research.md E5、E9）只由人工驗收確認，因此沒有對應的自動測試任務（T055）
- **逐字比對的範圍**：測試只逐字比對設計文件有明寫的字串：`.specify/sdd-drive/.gitignore` 的兩行、自動接續的 `reason`（`Automatic resume after the usage limit reset.`）、`(not shown: looks like a secret)`、`(not shown)`、`(line not shown: looks like a secret)`、`reason` 與 `detail.code`、`outcome`、`auto_resume` 的列舉值、`status` 的 `next.action` 值；其餘以關鍵字與結構檢查
- `SDD_DRIVE_CLAUDE` 與 `SDD_DRIVE_TEST_TIMING` 是測試用的環境變數（contracts/cli.md「共通」），SKILL.md 不提及；目前時間與重置時間以注入的值或假的 `resetsAt` 模擬，不改變判斷規則
- 這個 repo 本身不是被驅動的專案：不要在其中產生 `.specify/sdd-drive/`；`tools/deploy.py`、`home/CLAUDE.md`、`.github/workflows/ci.yml` 不在本功能的修改範圍，除非 T001、T054 發現不符並經主代理同意

---

## Phase 8: Convergence

對照檢查（`speckit-converge`）在 2026-11-22 找到的工作。設計文件已依維護者核可的修訂 A1／B1／C1 更新（commit `912ba86`）；A1 只改文件，沒有對應的任務。

- [X] T060 在 `home/skills/sdd-drive/SKILL.md` 的 Stage 3 表格新增一列：最後一筆嘗試的 `outcome` 是 `null`（`status: finished`，driver 異常消失）時，回到 Stage 1（`status` 會要求 `finalize`，交給 Stage 2）。在 `tests/unit/test_sdd_drive_skill.py` 把這一列加進 Stage 3 的列清單，並檢查它指向 Stage 1。依據：B1、contracts/skill.md 階段 3（新列）、contracts/cli.md「watch」（driver 異常消失）。現況證據：在暫存專案 `run` 一個 sleep 60 的假 `claude`，同時開一個 `watch`，再 `kill -9` 掉 driver；`run` 和 `watch` 都輸出 `status: finished`，最後一筆 `outcome: null`、`detail: null`；SKILL.md 的 Stage 3 沒有對應的列。結果總數變成 62（階段 3 共 29 列）。per contracts/skill.md 階段 3 (missing)
- [X] T061 在 `tests/unit/test_sdd_drive.py` 加一個測試：driver 被終止而沒有清掉記錄時（鎖已釋放、`driver` 不是 `null`、沒有 `launch`），`watch` 和 `run` 轉入的 watch 都輸出 `status: finished`，最後一筆嘗試是 `outcome: null`，之後 `status` 的 `next.action` 是 `finalize`。可以用寫入的紀錄模擬，不一定要真的終止行程。依據：B1、contracts/cli.md「watch」。現況證據：腳本 `watch_loop` 的「driver disappeared」分支已經會這樣輸出（實跑結果見 T060），但目前沒有測試直接檢查這個情況（`grep -n "disappear" tests/unit/test_sdd_drive.py` 沒有結果）。per contracts/cli.md watch (partial)
- [X] T062 把 `home/skills/sdd-drive/scripts/sdd_drive.py` 的 `REQUIRED_SKILLS` 加上 `speckit-converge`，讓 `status` 和 `run` 在缺少它時以結束碼 3、`reason: speckit-incomplete` 停止，並在 `missing` 列出它。同步更新 `tests/unit/test_sdd_drive.py`：`test_status_prerequisite_order` 預期的 `missing` 要包含 `speckit-converge`，另加一個只缺 `speckit-converge` 的案例。依據：C1、contracts/cli.md「結束碼與 reason」的 `speckit-incomplete`、FR-023。現況證據：`REQUIRED_SKILLS = ("speckit-plan", "speckit-tasks", "speckit-implement")`；少了 converge 時 `status` 回 `ok`，流程會一路跑完 plan、tasks、implement、test，直到 check 階段才由子 session 失敗。per contracts/cli.md speckit-incomplete (missing)
- [X] T063 在 `home/skills/sdd-drive/README.md` 的「前置需求」把 `speckit-converge` 列為必要的 skill（現在只列 `speckit-plan`、`speckit-tasks`、`speckit-implement`）。SKILL.md 的 Stage 1 `speckit-incomplete` 列如果要寫出必要 skill 的清單，也要列入它；`test_sdd_drive_skill.py` 視需要補上檢查。依據：C1、contracts/skill.md 階段 1 的 `speckit-incomplete` 列、contracts/skill.md「README.md」。現況證據：README.md 第 19 行。per contracts/skill.md 階段 1 (partial)
- [ ] T064 **主代理推送分支後處理；implement 的 worker 不執行這一項，也不 push**（比照 T059）：維護者授權推送後，確認 `.github/workflows/ci.yml` 的 `test`（`ubuntu-latest` 與 `windows-latest`）、`cross-platform-produce`、`cross-platform` 都通過 T060–T063 的修改；失敗時依紀錄修正後再確認。per Constitution II (missing)
