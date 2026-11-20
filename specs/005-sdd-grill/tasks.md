---

description: "Task list for 005 sdd-grill 依需求追問出 constitution 與 spec"
---

# Tasks: sdd-grill 依需求追問出 constitution 與 spec

**Input**: Design documents from `/specs/005-sdd-grill/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/cli.md、contracts/skill.md、quickstart.md

**Tests**: 需要。Constitution（v1.0.1）原則 II 要求每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
腳本 `sdd_grill.py` 的每個指令（`check`、`save`、`verify`、`focus`、`clear`）先寫測試、確認失敗，再實作；
`SKILL.md` 與 `README.md` 以結構與內容檢查驗證（關鍵字與段落順序，不比對完整文字）。
測試指令是 `uv run --with pytest pytest`。

**Organization**: 依 user story 分組。這是**對話式的 skill**（與 003 不同）：對話行為（提問形式、追問、矛盾、摘要、產生的內容）
無法在 CI 驗證，research.md R3 把每條 FR 對應到單元測試、結構／內容檢查或人工驗收。
本清單只為前兩類產生任務；只能人工驗收的部分見最後的 Notes，不列為勾選任務。
腳本的所有指令在同一支 `home/skills/sdd-grill/scripts/sdd_grill.py`，單元測試在同一份 `tests/unit/test_sdd_grill.py`，
skill 的結構與內容檢查在 `tests/unit/test_sdd_grill_skill.py`；改同一個檔案的任務依序進行。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、沒有未完成的相依）
- **[Story]**: 所屬的 user story（US1 至 US4）
- 路徑相對於 repo 根目錄
- `contracts/skill.md 第 N 項` 指該文件「SKILL.md 的內文」中編號為 N 的條目（1 至 31）
- 引用 data-model.md 的欄位時寫作 `data-model.md` 的 `Entity.field`；Entity 名稱對應小節：`Progress`（進度）、`Constitution`、
  `Feature`（功能）、`Fingerprint`（指紋）、`Baseline`（基準）、`FeatureJson`（目前的功能目錄）

## 所有任務共同的限制

- 實作與驗證 MUST NOT 讀寫真正的家目錄 `~/.claude`，也 MUST NOT 把這個 skill 部署到那裡。
- MUST NOT 在這個 repo 自己的 `.specify/`（或這個 repo 的任何目錄）執行 `sdd_grill.py` 的任何指令；這個 repo 的 `.specify/feature.json`
  與其他 `.specify/` 內容 MUST NOT 被修改。所有實際執行（測試、quickstart 手動情境）都在暫存目錄：pytest 用 `tmp_path`，手動情境用 `mktemp -d`。
- 這台機器的 `~/.claude/skills/` 下有另一個專案留下的同名 skill（`sdd-grill`）。實作者 MUST NOT 讀取、複製或沿用它；
  `SKILL.md` 與腳本只依本目錄的設計文件撰寫。
- 測試的 fixture 把 `HOME` 與 `USERPROFILE` 指向暫存目錄，所有 `git` 操作使用暫存 repository 並設定測試用的 `user.name`、`user.email`。
- 不 push；需要推送才能確認的工作只有 T044。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認既有基礎可用，備妥測試 fixture

- [X] T001 確認 `home/skills/`、`tests/unit/`、`tests/conftest.py` 與 `.github/workflows/ci.yml` 已存在，`uv`、`git` 都在 `PATH` 上，且 `uv run --with pytest pytest` 在目前的分支全部通過（`tests/unit/test_claude_md.py` 中「引用的 skill 資料夾存在」一項跳過是預期的）；確認 `home/skills/sdd-grill/` 尚不存在，且不讀取 `~/.claude/skills/sdd-grill`
- [X] T002 擴充 `tests/conftest.py`（不改動既有的 fixture）：新增以 `importlib` 載入 `home/skills/sdd-grill/scripts/sdd_grill.py` 的 session fixture（載入時 MUST NOT 執行任何動作，見 contracts/cli.md「以模組方式載入」）；新增建立「假的 Spec Kit 專案」的輔助函式，包含 research.md R4「Spec Kit 缺少能力」列出的六個必要檔案（`.specify/`、`.claude/skills/speckit-constitution/SKILL.md`、`.claude/skills/speckit-specify/SKILL.md`、`.specify/scripts/bash/resolve-template.sh`、`.specify/templates/spec-template.md`、`.specify/templates/constitution-template.md`）與可選的 `.specify/memory/constitution.md`、`.specify/init-options.json`、`specs/<名稱>/spec.md`；新增可選擇是否 `git init` 的暫存專案 fixture；新增以 `main(argv, …)` 指定專案根目錄與 stdin 呼叫腳本並取回結束碼、stdout JSON、stderr 的輔助函式
- [X] T003 [P] 唯讀確認 `tools/deploy.py` 會自動納入 `home/skills/sdd-grill/`（plan.md「Structure Decision」：不需要修改它）；若不成立，向主代理提問而不是自行修改

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 五個指令共用的核心：腳本骨架、輸出與結束碼、雜湊與指紋、自我忽略的資料夾、原子寫入、機密掃描

**⚠️ CRITICAL**: 這個階段完成前不能開始任何 user story

- [X] T004 建立 `tests/unit/test_sdd_grill.py` 並加入核心測試，確認在 T005 至 T008 實作前失敗：參數錯誤（沒有子指令、不認得的子指令、多出參數）時結束碼 1 且 stderr 顯示用法；載入模組時不執行任何動作；stdout 只有一份 JSON（UTF-8、LF、縮排 2、結尾換行、鍵順序固定）；失敗時 JSON 有 `error` 且同一句寫到 stderr（contracts/cli.md「共通」「結束碼」）。以及共用函式：內容雜湊先把 CRLF、CR 換成 LF 再算 SHA-256，LF 與 CRLF 版本相同、其他差異不同；指紋依 `data-model.md` 的 `Fingerprint.constitution`、`Fingerprint.specs`、`Fingerprint.head` 計算（`head` 在非 git、沒有 commit、沒有 `git` 時為 `null`）；自我忽略資料夾的 `.gitignore` 內容恰為 data-model.md「自己的資料夾」的兩行固定內容；資料夾衝突判定（`.gitignore` 內容不同、或有兩個檔案以外的檔案或子資料夾）；原子寫入（先寫同資料夾暫存檔再取代，失敗時不留下半寫的檔案）；機密掃描對 research.md R8 列出的各類樣式（私鑰標頭、權杖前綴、URL 中的 `user:password@`、`password`／`secret`／`token`／`api_key` 後接 `=` 或 `:` 與非空白值）都回報欄位路徑且不含該值，一般的長識別字與一般文字不誤判
- [X] T005 建立 `home/skills/sdd-grill/scripts/sdd_grill.py` 骨架：uv inline metadata（`requires-python = ">=3.11"`、`dependencies` 為空）；只用標準函式庫；`main(argv)` 回傳結束碼並可指定專案根目錄與 stdin；五個子指令的分派（先回傳「尚未實作」的失敗，由後續任務實作）；結束碼 0、1、3 的常數（2 保留、4 不使用）；JSON 輸出與錯誤輸出的共用函式；載入為模組時不執行任何動作（contracts/cli.md「指令」「共通」「結束碼」「以模組方式載入」，contracts/skill.md「scripts/sdd_grill.py」）
- [X] T006 在 `sdd_grill.py` 實作內容雜湊（換行正規化）、指紋計算與 `git rev-parse HEAD` 的讀取（`git` 不存在時視為不是 git repository），欄位依 `data-model.md` 的 `Fingerprint.constitution`、`Fingerprint.specs`、`Fingerprint.head`；所有輸出的路徑一律以 `/` 分隔、順序固定
- [X] T007 在 `sdd_grill.py` 實作自我忽略的資料夾 `.specify/sdd-grill/`：建立資料夾與固定內容的 `.gitignore`、衝突判定、原子寫入、刪除自己的兩個檔案（資料夾變空時一併刪除）；每個函式以資料夾名稱為參數，能獨立呼叫（contracts/cli.md「以模組方式載入」；data-model.md「自己的資料夾」）
- [X] T008 在 `sdd_grill.py` 實作機密掃描：依 research.md R8 的樣式掃描所有字串值，符合時回報欄位路徑，錯誤訊息 MUST NOT 印出該值；樣式刻意保守
- [X] T009 [P] 建立 `tests/unit/test_sdd_grill_skill.py`，先加入針對腳本的靜態檢查：開頭有 uv inline metadata 且 `requires-python = ">=3.11"`、`dependencies` 為空；只 import 標準函式庫；不載入其他 skill 的程式；內容沒有中日韓文字、絕對路徑與信箱（contracts/skill.md「scripts/sdd_grill.py」；research.md R3 的 FR-022 列）

**Checkpoint**: 核心就緒，可以開始 user story

---

## Phase 3: User Story 1 - 從一段需求描述追問出完整的決策 (Priority: P1) 🎯 MVP

**Goal**: 前置檢查與進度保存可用；`SKILL.md` 寫出啟動、追問規則、追問順序與保存的指示。

**Independent Test**: `check` 與 `save`（`discussing` 路徑）的單元測試全部通過，且 `SKILL.md` 的結構與內容檢查涵蓋 contracts/skill.md 第 1–4、7–18 項。
對話行為（一次一題、建議排第一、追問、矛盾、技術選型）由 quickstart.md 人工驗收情境 1、2、10、11、12 確認，不是本階段的勾選任務。

### Tests for User Story 1 ⚠️

> **NOTE: 先寫測試並確認失敗，再實作**

- [X] T010 [US1] 在 `tests/unit/test_sdd_grill.py` 加入 `check` 的前置與專案現況測試（contracts/cli.md「check」，data-model.md「專案現況」）：`.specify/` 不存在 → 結束碼 3、`speckit` 為 `"missing"`、`error` 為規定的句子、目錄仍是空的；缺少六個必要檔案之一 → 結束碼 3、`speckit` 為 `"incomplete"`、`missing` 依路徑排序列出缺少的檔案、`error` 為規定的另一句；完整 → 結束碼 0、`speckit` 為 `"ok"`；`constitution` 的 `missing`／`template`（與範本換行正規化後相同、或含 `[PROJECT_NAME]`／`[PRINCIPLE_1_NAME]`）／`written`；`specs` 只列含 `spec.md` 的一層資料夾、依名稱排序、`number` 依 `\d{3,}-` 與 `\d{8}-\d{6}-` 取值、其他為 `null`；`numbering` 取 `.specify/init-options.json` 的 `feature_numbering`，其次 `branch_numbering`，都沒有或無法讀取時為 `"sequential"`；`check` 不寫入任何檔案（前後的檔案樹相同）
- [X] T011 [US1] 在 `tests/unit/test_sdd_grill.py` 加入 `save`（`discussing` 路徑）的測試（contracts/cli.md「save」，data-model.md「驗證規則」1–5、7、9）：最小有效進度寫入成功，輸出 `saved`、`phase`、`baseline: false`，`progress.json` 為 UTF-8、LF、縮排 2、結尾換行，腳本填入 `saved_at` 與 `fingerprint`、`baseline` 為 `null`，Claude 送來的 `saved_at`、`fingerprint`、`baseline` 被忽略；`.specify/sdd-grill/.gitignore` 同時被建立；以真實 `git` 驗證寫入後 `git status --porcelain --untracked-files=all` 沒有輸出、`git add -A` 之後仍沒有；以相同輸入重複 `save` 內容相同（`saved_at` 除外）；stdin 不是 JSON → `progress is not valid JSON: …`；逐一違反規則 1–5、7 的欄位（多出的欄位、型別錯誤、空字串、`schema`、`tool`、`stage` 不是 `principles`／`features`／`feature`／`summary`、`stage` 與 `current_feature` 不一致、`id` 重複或不符樣式、`depends_on` 指向後面的功能或不存在的資料夾、`deferred`／`for_plan` 的 `feature` 不存在、`discussing` 時 `spec_dir` 不是 `null`）→ 結束碼 1、`progress is invalid at <欄位路徑>: …`、不寫入任何檔案；含機密樣式 → 結束碼 1、`error` 指出欄位路徑且不含該值、既有 `progress.json` 不變；資料夾衝突 → 結束碼 1、`.specify/sdd-grill/ holds files sdd-grill did not create; nothing was written`；`save` 不檢查 Spec Kit 是否存在；`save` 只寫 `.specify/sdd-grill/` 之內
- [X] T012 [P] [US1] 在 `tests/unit/test_sdd_grill_skill.py` 加入 `SKILL.md` 的 frontmatter 與前半內容檢查（以關鍵字與段落順序，不比對完整文字；contracts/skill.md「SKILL.md 的 frontmatter」與「內文」第 1–4、7–18 項；research.md R3 的 FR-001 至 FR-009 列）：frontmatter 有 `name: sdd-grill`、英文 `description`（含用途、使用時機與不使用的時機）、`argument-hint`、**沒有** `disable-model-invocation`、沒有其他欄位；內文沒有中日韓文字、絕對路徑、信箱；有「沒有需求描述時先請維護者說明」、執行 `check`（字樣：`sdd_grill.py" check` 或等同的完整指令）且**在任何提問之前**；結束碼 3 時 `speckit` 為 `"missing"`／`"incomplete"` 的處理、`/sdd-init`、`.specify/`、`uv` 不存在時停止；`progress` 為 `"conflict"`／`"unreadable"` 的處理；追問規則段落含「自己查出不提問」「從需求與專案內容推導、不用固定題庫」「`AskUserQuestion`」「`one question`」「建議排第一與理由」「工具不能用時改用文字」「含糊時繼續追問」「矛盾時指出兩邊」「`for_plan`」「機密不記錄」「結束時呈現摘要並停止」；順序段落中 constitution 原則 → 功能清單與相依 → 逐一功能三段的先後正確；保存段落含 `save` 完整指令、失敗時修正重試、只透過 `save` 寫入

### Implementation for User Story 1

- [X] T013 [US1] 在 `sdd_grill.py` 實作 `check`（不含 `progress` 與 `changed` 的實際判定，這兩欄先固定為 `"none"` 與空陣列，T031 補完）：Spec Kit 狀態與 `missing`、`constitution` 判定、`specs` 清單與 `number`、`numbering`，結束碼 3 與規定的 `error` 句子，其餘欄位在失敗時照常輸出；只讀，不寫入（contracts/cli.md「check」，data-model.md「專案現況」），讓 T010 通過
- [X] T014 [US1] 在 `sdd_grill.py` 實作 `save` 的 `discussing` 路徑與驗證，讓 T011 通過。欄位與規則依 `data-model.md` 的 `Progress.schema`、`Progress.tool`、`Progress.requirement`、`Progress.language`、`Progress.phase`、`Progress.stage`、`Progress.current_feature`、`Progress.deferred`、`Progress.for_plan`、`Progress.saved_at`、`Progress.fingerprint`、`Progress.baseline`，`Constitution.action`、`Constitution.principles`、`Constitution.governance`，`Feature.id`、`Feature.title`、`Feature.depends_on`、`Feature.status`、`Feature.decisions`、`Feature.spec_dir`；錯誤只回報第一個錯誤的欄位路徑；依序：驗證 → 機密掃描 → 資料夾衝突 → 建立資料夾與 `.gitignore` → 原子寫入 `progress.json`（contracts/cli.md「save」）
- [X] T015 [US1] 建立 `home/skills/sdd-grill/SKILL.md`（英文），先寫 frontmatter 與「開始」段落：frontmatter 依 contracts/skill.md「SKILL.md 的 frontmatter」（`name`、英文 `description` 含使用時機與不使用的時機、`argument-hint: "<requirement description>"`、不加 `disable-model-invocation`）；內文滿足 contracts/skill.md 第 1–4 項：沒有需求描述先請維護者說明；任何提問之前先執行 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" check`；結束碼 3 依 `speckit` 值處理（`"missing"` 請維護者執行 `/sdd-init`、`"incomplete"` 回報不相容並列出 `missing`），MUST NOT 自己執行 `/sdd-init`、MUST NOT 建立或修改 `.specify/` 與 `speckit-*` 的檔案，`uv` 不存在時回報並停止；`progress` 為 `conflict`／`unreadable` 時回報原因，`unreadable` 時詢問是否 `clear` 後重新開始。不使用 `~/.claude/skills/sdd-grill` 的內容
- [X] T016 [US1] 在 `SKILL.md` 加入「追問的規則」段落（集中在一個段落，research.md R6），滿足 contracts/skill.md 第 7–14 項：先讀專案現有內容並自行查出可查到的事（FR-004）；問題從需求與專案內容推導、不用固定題庫（FR-002）；每則訊息一個問題、建議排第一並附理由、使用 `AskUserQuestion`、工具不能用時改用文字且仍一次一題附建議（FR-003）；含糊時繼續追問（FR-005）；矛盾時指出兩邊並請維護者取捨，與既有 constitution 衝突時請維護者決定修訂原則或調整需求（FR-006）；技術選型只記到 `for_plan`、不討論（FR-008）；機密值不記錄、只記需要什麼並告知維護者（FR-009）；維護者要求結束時呈現目前摘要、確認進度已保存、停止
- [X] T017 [US1] 在 `SKILL.md` 加入「追問的順序」段落，滿足 contracts/skill.md 第 15–16 項：依序為 constitution 的原則 → 功能清單與相依關係 → 逐一討論每個功能的使用情境、範圍與邊界情況（FR-007），對應 `stage` 的 `principles`、`features`、`feature`、`summary`；產生文件的語言依專案既有文件，無法判斷時使用繁體中文、規範詞保留英文（FR-020）；`SKILL.md` 本身不得含中日韓文字，語言規則以英文描述
- [X] T018 [US1] 在 `SKILL.md` 加入「保存」段落，滿足 contracts/skill.md 第 17–18 項：每個決定之後以 stdin 把完整進度交給 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" save`；`save` 失敗時修正後重試，因機密被拒時改寫成不含該值的描述；進度只透過 `save` 寫入，MUST NOT 以其他方式建立或修改 `.specify/sdd-grill/` 的檔案。完成後執行 T012 的檢查應全部通過

**Checkpoint**: `check`、`save` 的測試與 `SKILL.md` 前半的內容檢查通過；MVP 的追問流程具備可保存的進度

---

## Phase 4: User Story 2 - 確認摘要後才產生文件 (Priority: P1)

**Goal**: 確認摘要的進度、`verify`、`focus` 可用；`SKILL.md` 寫出摘要與確認、產生文件、失敗與收尾的指示。

**Independent Test**: `save` 的 `confirmed` 路徑、`verify`、`focus` 的單元測試全部通過，`SKILL.md` 的內容檢查涵蓋 contracts/skill.md 第 19–31 項與其順序。
產生文件的實際內容、確認前沒有任何寫入、結束報告（quickstart.md 人工驗收情境 5、6、7）由維護者驗收，不是本階段的勾選任務。

### Tests for User Story 2 ⚠️

- [X] T019 [US2] 在 `tests/unit/test_sdd_grill.py` 加入 `save` 的 `confirmed` 路徑測試（data-model.md「驗證規則」6、7、8，「基準」，「狀態轉移」）：`phase` 為 `confirmed` 時 `stage` 必須是 `summary`、每個功能 `status` 都是 `decided`、`language` 不是 `null`，違反時 → 結束碼 1 並指出欄位路徑；第一次以 `confirmed` 保存時記下 `baseline`（`constitution` 與 `specs` 的雜湊，同 `Fingerprint`），輸出 `"baseline": true`；之後的 `save`（含填入 `spec_dir`）沿用原值，不論 Claude 送來什麼；`spec_dir` 只在 `confirmed` 時可以不是 `null`，且必須是 `specs/` 之下一層資料夾的 `/` 分隔相對路徑（絕對路徑、`..`、巢狀、反斜線被拒）；已有任何 `spec_dir` 的 `confirmed` 進度改回 `discussing` → 結束碼 1、`specs were already generated from the confirmed summary; it can no longer go back to discussing`；還沒有任何 `spec_dir` 時可以改回 `discussing` 且 `baseline` 回到 `null`
- [X] T020 [US2] 在 `tests/unit/test_sdd_grill.py` 加入 `verify` 測試（contracts/cli.md「verify」，data-model.md「驗證產生的結果」）：進度不存在或 `phase` 不是 `confirmed` → 結束碼 1、`there is no confirmed summary to verify`；全部正確 → `ok` 為 `true`、結束碼 0、`specs` 依 `features` 順序且 `depends_on` 的功能 `id` 換成 `spec_dir`（還沒有時保留 `id`）；逐一製造失敗並確認項目名稱與 `detail` 含相關路徑：`existing-spec-changed`（基準中的 spec 被改或被刪）、`constitution-changed`（`keep` 但 constitution 變了）、`constitution-not-written`（`create` 但仍是範本或不存在；`amend` 但雜湊不變）、`spec-missing`、`spec-not-new`（`spec_dir` 在基準中或彼此重複）、`order`（編號沒有嚴格遞增、不大於基準的最大編號、或無法取得編號）、`dependency-order`（依賴的編號不比自己小）；多項同時失敗時全部列出、不在第一個失敗時停止；`unexpected` 列出基準之外、也不屬於任何功能的新 spec 資料夾且不算失敗；`ok` 為 `false` 時結束碼 1、`the generated documents do not match the confirmed summary`；`sequential` 以整數比較、`timestamp` 以字串比較；`verify` 只讀（前後檔案樹相同）
- [X] T021 [US2] 在 `tests/unit/test_sdd_grill.py` 加入 `focus` 測試（contracts/cli.md「focus」情況表，data-model.md「目前的功能目錄」）：進度不是 `confirmed` → 結束碼 1、`there is no confirmed summary to point at`、不寫入；`verify` 任何一項失敗 → 結束碼 1、`… ; .specify/feature.json was not changed`、`failures` 同 `verify`、`feature.json` 位元組不變；`feature.json` 原本指向最後一份 → 改為 `features` 第一個功能的 `spec_dir`、輸出 `feature_directory`／`previous`／`changed: true`、檔案內容恰為只有 `feature_directory` 一個鍵的 JSON（UTF-8、LF、縮排 2、結尾換行）；已指向目標 → `changed: false` 且不寫入、再執行一次結果相同；檔案不存在 → 建立、`previous` 為 `null`；內容不是 JSON／不是物件／沒有字串型 `feature_directory` → 改寫、`previous` 為 `null`；路徑存在但不是一般檔案（例如資料夾）→ 結束碼 1、`.specify/feature.json is not a regular file; nothing was written`；只有一份 spec 的情況；以真實 `git` 驗證 `feature.json` 不入庫（Spec Kit 的 `.specify/.gitignore` 列有它，fixture 需模擬）；`focus` 只寫 `.specify/feature.json`，不讀不寫 `.specify/` 其他 Spec Kit 檔案；`check`、`verify`、`save`、`clear` 都不會寫入 `.specify/feature.json`

### Implementation for User Story 2

- [X] T022 [US2] 在 `sdd_grill.py` 的 `save` 實作 `confirmed` 路徑：驗證規則 6、7、8、第一次 `confirmed` 時記下基準並於之後沿用、`discussing` 時 `baseline` 為 `null`、`spec_dir` 路徑形式檢查，讓 T019 通過。欄位依 `data-model.md` 的 `Progress.phase`、`Progress.stage`、`Progress.language`、`Progress.baseline`、`Feature.status`、`Feature.spec_dir`、`Baseline.constitution`、`Baseline.specs`
- [X] T023 [US2] 在 `sdd_grill.py` 實作 `verify`：七項檢查與 `unexpected`、編號比較（`sequential` 整數、`timestamp` 字串）、輸出欄位與結束碼，只讀，讓 T020 通過。檢查依 `data-model.md` 的 `Baseline.constitution`、`Baseline.specs`、`Constitution.action`、`Feature.spec_dir`、`Feature.depends_on`、`Feature.id`
- [X] T024 [US2] 在 `sdd_grill.py` 實作 `focus`：先執行與 `verify` 相同的全部檢查（共用同一份實作，不複製），全部通過才寫入；目標為 `features` 第一個功能的 `spec_dir`；有效值判定、不是一般檔案的失敗、值相同不寫入、原子寫入、輸出欄位依 contracts/cli.md「focus」；讓 T021 通過。目標與有效值依 `data-model.md` 的 `FeatureJson.目標`、`FeatureJson.有效值`、`FeatureJson.寫入條件`，`Feature.spec_dir`

### Tests for SKILL.md of User Story 2 ⚠️

- [X] T025 [P] [US2] 在 `tests/unit/test_sdd_grill_skill.py` 加入 `SKILL.md` 後半的內容與順序檢查（contracts/skill.md 第 19–31 項；research.md R3 的 FR-011 至 FR-020 列）：摘要含四部分（已決定、已延後與原因、留給 plan、依相依排列的功能順序）；以一題詢問確認、修改後再確認；`speckit-constitution`、`speckit-specify` 以 Skill 工具呼叫、`keep` 時不呼叫、constitution 只傳確認過的原則並移除多出的規則、`spec_dir`、`Assumptions`、澄清時依摘要回答；MUST NOT 手寫 constitution 與 spec、MUST NOT 自行指定編號、MUST NOT 自己修改 `.specify/feature.json`（字樣：`feature.json`）；失敗時回報已產生與未產生、保留進度、不補寫不刪除；收尾執行 `verify`、`focus`、`clear`；`/sdd-drive`；停止且不開始 plan、tasks、實作；MUST NOT push。順序：「確認摘要」段落在「產生文件」段落之前、`check` 在提問之前（T012 已涵蓋）、`verify` 在 `focus` 之前、`focus` 在 `clear` 之前

### Implementation of SKILL.md for User Story 2

- [X] T026 [US2] 在 `SKILL.md` 加入「摘要與確認」段落，滿足 contracts/skill.md 第 19–21 項：全部有結論或已延後時呈現四部分摘要；以一題詢問確認，要求修改時修改並再次確認；確認之前 MUST NOT 寫入或修改 constitution 與任何 spec（FR-011、FR-012）；段落位置在「產生文件」之前
- [X] T027 [US2] 在 `SKILL.md` 加入「產生文件」段落，滿足 contracts/skill.md 第 22–25 項（research.md R4 步驟 1 至 3）：確認後先以 `phase: "confirmed"` 保存；`constitution.action` 為 `create`／`amend` 時以 Skill 工具呼叫 `speckit-constitution`、只傳入確認過的原則與治理規則並要求不要推斷其他原則，完成後逐條比對、移除未確認的規則、想保留的先問維護者，`keep` 時不呼叫；依功能順序一次一個以 Skill 工具呼叫 `speckit-specify`，傳入該功能確認過的內容並要求延後事項寫在 Assumptions，完成後把回報的資料夾寫入 `spec_dir` 並保存，要澄清時依摘要回答、摘要沒有答案時以一題詢問維護者並補進進度，產生後比對 spec 與摘要、沒有依據的內容移除或標為待確認（plan.md 取捨第 5、6 點）；MUST NOT 手寫、MUST NOT 自行指定編號、MUST NOT 自己修改 `.specify/feature.json`（它只由 `focus` 寫入）
- [X] T028 [US2] 在 `SKILL.md` 加入「失敗」段落，滿足 contracts/skill.md 第 26 項：任何一步失敗時回報已產生與未產生的文件、保留進度、停止；MUST NOT 補寫、MUST NOT 刪除已產生的文件；`verify` 或 `focus` 失敗時同樣處理且不執行 `clear`（FR-018）
- [X] T029 [US2] 在 `SKILL.md` 加入「收尾」段落，滿足 contracts/skill.md 第 27–31 項：依序執行 `verify`、`focus`、`clear`（`verify` 通過才 `focus`，`focus` 成功才 `clear`，失敗時依「失敗」段落處理）；依 `verify` 的輸出列出每份 spec 的位置、相依與建議順序，並告知 `.specify/feature.json` 現在指向哪一份（`focus` 輸出的 `feature_directory`）；說明下一步是由維護者輸入 `/sdd-drive`，也可依序以原生的 `/speckit-plan` 處理；然後停止，MUST NOT 開始 plan、tasks 或實作；MUST NOT push。完成後 T025 的檢查應全部通過

**Checkpoint**: `confirmed`、`verify`、`focus` 的測試與 `SKILL.md` 後半的內容檢查通過；US1 與 US2 合起來是完整的主流程

---

## Phase 5: User Story 3 - 中斷後接續 (Priority: P2)

**Goal**: `check` 能回報既有進度與改變的項目，`clear` 能清除進度；`SKILL.md` 寫出接續的指示。

**Independent Test**: `check` 的進度與變更偵測、`clear` 的單元測試通過，`SKILL.md` 的內容檢查涵蓋 contracts/skill.md 第 5–6 項。
中斷後接續的實際對話（quickstart.md 人工驗收情境 3、4、7）由維護者驗收。

### Tests for User Story 3 ⚠️

- [X] T030 [US3] 在 `tests/unit/test_sdd_grill.py` 加入 `check` 的進度與變更偵測測試（contracts/cli.md「check」，data-model.md「指紋」）：沒有進度 → `progress` 為 `"none"`、`saved` 為 `null`；有效進度 → `"present"`、`saved` 為完整內容、`changed` 為空；之後修改 constitution、修改或新增 spec.md、新增 commit，`changed` 依固定順序（`constitution`、`specs`、`head`）列出不同的項目；非 git repository 或沒有 `git` 時 `head` 不算變更；`progress.json` 不是有效 JSON、`schema` 或 `tool` 不符、不符合驗證規則 → `"unreadable"`、`saved` 為 `null`；資料夾衝突 → `"conflict"`；`check` 在以上各情況都不寫入
- [X] T031 [US3] 在 `tests/unit/test_sdd_grill.py` 加入 `clear` 測試（contracts/cli.md「clear」）：刪除 `progress.json` 與 `.gitignore`、資料夾變空時一併刪除、輸出 `{"cleared": true}`；本來就沒有 → `{"cleared": false}` 且結束碼 0、重複執行結果相同；`unreadable` 的進度也能清除；資料夾有其他檔案或 `.gitignore` 不是自己寫的 → 結束碼 1、同 `save` 的衝突 `error`、任何檔案都不刪除；`clear` 不寫入或刪除 `.specify/sdd-grill/` 以外的任何東西（包含 `.specify/feature.json` 與 `specs/`）

### Implementation for User Story 3

- [X] T032 [US3] 在 `sdd_grill.py` 補完 `check` 的 `progress`、`changed`、`saved`：以 T007 的資料夾函式判定 `none`／`present`／`unreadable`／`conflict`，`present` 時重新計算指紋並與 `Progress.fingerprint` 逐項比較（`Fingerprint.constitution`、`Fingerprint.specs`、`Fingerprint.head`），讓 T030 通過；`check` 仍然只讀
- [X] T033 [US3] 在 `sdd_grill.py` 實作 `clear`，讓 T031 通過：只刪自己的兩個檔案與（變空時的）資料夾、不看進度內容、衝突時不刪任何檔案

### Tests and implementation of SKILL.md for User Story 3

- [X] T034 [P] [US3] 在 `tests/unit/test_sdd_grill_skill.py` 加入「接續」的內容檢查（contracts/skill.md 第 5–6 項；research.md R3 的 FR-010、FR-018 列）：`progress` 為 `"present"` 時先列出已決定的事項、`changed` 不是空的時先說明、以一題詢問接續或重新開始、重新開始時執行 `clear`（字樣：`changed`、`clear`）；接續時從 `stage` 與 `current_feature` 繼續、不重問已決定的事項；`phase` 為 `"confirmed"` 時詢問是否從尚未產生的文件繼續、不重新討論
- [X] T035 [US3] 在 `SKILL.md` 加入「接續」段落（位置在「開始」之後、「追問的規則」之前），滿足 contracts/skill.md 第 5–6 項：`progress` 為 `"present"` 時先列出已決定的事項，`changed` 非空時先說明哪些改變了，再以一題詢問接續或重新開始，重新開始時執行 `clear`；接續時依 `stage` 與 `current_feature` 繼續且 MUST NOT 重問已決定的事項；`confirmed` 時詢問是否從尚未產生的文件繼續。完成後 T034 的檢查應全部通過

**Checkpoint**: US1 至 US3 可獨立運作；進度可中斷與接續

---

## Phase 6: User Story 4 - 為已有 spec 的專案加入新需求 (Priority: P2)

**Goal**: 已有 constitution 與 spec 的專案不會被覆蓋、編號接續；`SKILL.md` 寫出既有專案的處理指示。

**Independent Test**: 在含 constitution 與 3 份 spec 的暫存專案，`save`、`verify`、`focus` 的單元測試證明既有文件不被動到、新編號接在既有之後、`focus` 指向這一批的第一份。
實際對話（quickstart.md 人工驗收情境 8）由維護者驗收。

### Tests for User Story 4 ⚠️

- [X] T036 [US4] 在 `tests/unit/test_sdd_grill.py` 加入既有專案的測試（FR-015、FR-016、SC-005；research.md R3 的 FR-015、FR-016 列）：專案已有 constitution 與 `specs/001-…`、`specs/002-…`、`specs/003-…` 時，`save` 接受 `depends_on` 指向既有的 `specs/003-…`、拒絕指向沒有 `spec.md` 或不存在的資料夾；確認時 `baseline` 含三份既有 spec 的雜湊；模擬新 spec 為 `004`、`005` → `verify` 通過；既有 spec 被修改 → `existing-spec-changed`；新 spec 編號不大於 `003` → `order`；`keep` 且 constitution 沒變 → 通過、`amend` 且 constitution 有變 → 通過；`focus` 的目標是這一批的第一份（`004`），不是專案的第一份（`001`）；`timestamp` 編號方式下新舊 spec 的字串比較與 `order`；專案原有的 spec 不在 `unexpected`
- [X] T037 [US4] 依 T036 的結果修正 `sdd_grill.py` 的 `save`、`verify`、`focus`，使 T036 全部通過（欄位依 `data-model.md` 的 `Feature.depends_on`、`Baseline.specs`、`Baseline.constitution`、`Constitution.action`、`Feature.spec_dir`）；若 T036 在前面任務完成後已全部通過，在回報中註明沒有需要修正的地方
- [X] T038 [P] [US4] 在 `tests/unit/test_sdd_grill_skill.py` 加入既有專案的內容檢查（contracts/skill.md 第 11、15、23、24 項；research.md R3 的 FR-016、FR-020 列）：讀取既有 constitution 與 spec、不重問已記錄的決定；專案已有 constitution 時，原則段落只處理新需求與既有原則的衝突或新增，`action` 依維護者的決定設為 `keep` 或 `amend`（字樣：`keep`、`amend`）；與既有 constitution 衝突時請維護者決定修訂原則或調整需求；`depends_on` 可以指向既有的 spec 資料夾；不覆蓋既有 spec
- [X] T039 [US4] 在 `SKILL.md` 補上既有專案的指示，滿足 contracts/skill.md 第 11、15、23、24 項中涉及既有文件的部分：既有 constitution 與 spec 視為已決定的內容、不重問；原則段落只處理衝突或新增，維護者同意修訂才把 `action` 設為 `amend`、否則 `keep`；`depends_on` 可指向既有 spec 的資料夾路徑；新 spec 的編號由 `speckit-specify` 決定、不覆蓋既有 spec。只在對應的既有段落內補充，不改動其他段落的順序。完成後 T038 的檢查應全部通過

**Checkpoint**: 四個 user story 都可獨立運作

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: README、skill 資料夾的整體檢查、腳本手動情境實跑、完整測試與 CI

- [X] T040 [P] 在 `tests/unit/test_sdd_grill_skill.py` 加入資料夾與 README 的檢查（contracts/skill.md「檔案」「README.md」；research.md R3 的 FR-022 列）：`home/skills/sdd-grill/` 內只有 `SKILL.md`、`README.md`、`scripts/sdd_grill.py` 三個檔案；`SKILL.md` 英文、無中日韓文字、無絕對路徑與信箱（T012 已涵蓋，合併成一次完整檢查即可）；`README.md` 含繁體中文，並涵蓋：用法 `/sdd-grill`、前置需求（Spec Kit、`/sdd-init`、`uv`、`git` 非必要）、流程（先原則、再功能清單、再逐一功能、確認前不寫入、`/sdd-drive`）、進度（`.specify/sdd-grill/`、自己的 `.gitignore`、成功後清除、中途結束或失敗時保留、不記錄機密、變更偵測範圍與限制）、收尾（`.specify/feature.json` 指向這一批編號最小的一份）、不做的事
- [X] T041 撰寫 `home/skills/sdd-grill/README.md`（繁體中文，指令與識別字保留原文），內容依 contracts/skill.md「README.md」逐項涵蓋，讓 T040 通過；若 repo 根目錄的 `README.md` 列有 skill 的現況，同步更新 `sdd-grill` 的狀態（先 `grep` 確認；沒有列則不改）
- [X] T042 依 `specs/005-sdd-grill/quickstart.md`「手動情境（腳本）」的 8 個情境，在 `mktemp -d` 建立的暫存目錄逐一實跑 `uv run <repo>/home/skills/sdd-grill/scripts/sdd_grill.py`，並修正與預期不符之處；每個情境用新的暫存目錄。準備「導入 Spec Kit 的專案」時，可以用 T002 的假專案輔助函式的結構手動建立（不需要網路），也可以在有網路時執行 `sdd_init.py init`；MUST NOT 在這個 repo 的目錄、真正的 `~/.claude`，或這個 repo 的 `.specify/` 執行；MUST NOT 讀取 `~/.claude/skills/sdd-grill`。情境 5 中手動建立的 `spec.md` 只為測試腳本
- [X] T043 執行完整測試 `uv run --with pytest pytest`，結束碼 0；確認 `git status` 中 `.specify/`（含 `.specify/feature.json`）與 `~/.claude` 都沒有被這次的工作更動；逐項核對 contracts/skill.md「內文」第 1–31 項都有至少一條對應的內容檢查，缺少的補上測試；確認 `tests/unit/test_claude_md.py` 在 `home/skills/sdd-grill/SKILL.md` 存在後仍通過。Windows 上的結果由 T044 的 CI 確認（constitution 原則 II）
- [X] T044 **由主代理在維護者授權推送後處理，實作的 worker 不執行這一項、不 push**：推送分支後確認 `.github/workflows/ci.yml` 的 `test`、`cross-platform-produce`、`cross-platform` 三個 job 在 `ubuntu-latest` 與 `windows-latest` 都通過；Windows 與跨平台的行為以 CI 結果為準，失敗時依紀錄修正後再確認

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依賴 001 至 004 已在目前的分支
- **Foundational (Phase 2)**: 依賴 Setup；T004 的測試先於 T005 至 T008
- **US1 (Phase 3)**: 依賴 Foundational；T010、T011 先於 T013、T014；T012 先於 T015 至 T018
- **US2 (Phase 4)**: 依賴 US1 的 `save`（T014）與 `check`（T013）；T019 至 T021 先於 T022 至 T024；T025 先於 T026 至 T029；`SKILL.md` 的段落依 T015 → T029 的順序寫入同一個檔案
- **US3 (Phase 5)**: 依賴 US1；T032 補完 T013 的 `check`，`clear`（T033）只依賴 Foundational 的資料夾函式；`SKILL.md` 的 T035 在 T015 之後
- **US4 (Phase 6)**: 依賴 US2（`baseline`、`verify`、`focus`）
- **Polish (Phase 7)**: 依賴 US1 至 US4；T044 依賴 T043，且需要維護者授權推送

### Within Each Story

- 測試先寫、先確認失敗，再實作
- 腳本的任務（`sdd_grill.py`、`test_sdd_grill.py`）依序進行；`SKILL.md` 的段落任務依序進行；`test_sdd_grill_skill.py` 的測試任務標 [P]（與腳本任務不同檔案）

### Parallel Opportunities

- T003 與 T001、T002 可同時進行
- T009 與 T004 至 T008 可同時進行（不同檔案）
- 各 story 中標 [P] 的 skill 內容檢查（T012、T025、T034、T038）可與腳本任務同時撰寫；但各自要先於對應的 `SKILL.md` 任務完成
- T040 可與 T041 以外的腳本任務同時進行

### Parallel Example: User Story 1

```text
# 不同檔案，可同時進行：
Task: "T010/T011 check 與 save 的單元測試 in tests/unit/test_sdd_grill.py"
Task: "T012 SKILL.md 前半的內容檢查 in tests/unit/test_sdd_grill_skill.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. 完成 Phase 1 與 Phase 2
2. 完成 Phase 3（US1）：`check`、`save`、`SKILL.md` 的開始／追問／保存
3. 完成 Phase 4（US2）：`confirmed`、`verify`、`focus`、`SKILL.md` 的摘要／產生／失敗／收尾；US1 與 US2 都是 P1，合起來才是完整的主流程
4. **STOP and VALIDATE**: 單元測試與內容檢查通過；對話行為交給維護者以人工驗收確認

### Incremental Delivery

1. US3：`clear` 與變更偵測、接續指示
2. US4：既有專案的測試與指示
3. Polish：README、quickstart 實跑、完整測試、CI（T044）

---

## Notes

- 每完成一個任務或一組相關任務就 commit；不 push，推送由主代理在維護者授權後進行（T044）
- 維護者已核可 plan.md「需要維護者注意的取捨」全部 10 項，實作時照 plan 的寫法，不需要再確認。其中第 4 點（`focus` 改寫 `.specify/feature.json`，
  維護者確認不違反原則 I）是核可時特別確認過的；腳本「只寫 `.specify/sdd-grill/`」的保證因此是「除 `focus` 之外」
- **人工驗收不列為勾選任務**：quickstart.md「人工驗收（真實 session）」的 12 個情境需要真實的 Claude Code session（部署到測試用的家目錄，
  以 `HOME=<test-home>` 與 `CLAUDE_CONFIG_DIR=<test-home>/.claude` 啟動），由維護者在合併並部署後進行並記錄結果：
  1. 含糊需求的追問：一次一題、建議排第一、問題對應需求、順序為原則 → 功能清單 → 逐一功能
  2. 「要快」的追問、矛盾、技術選型只記為留給 plan
  3. 中斷後接續與重新開始
  4. 專案有變更時的提示
  5. 摘要的四部分、確認前沒有任何寫入、修改後再確認
  6. 確認後以 `speckit-constitution`／`speckit-specify` 產生、編號與語言、`feature.json` 指向第一份、結束報告與 `/sdd-drive`
  7. 產生途中中斷後的處理
  8. 已有 constitution 與 3 份 spec 的專案加入新需求
  9. 未導入 Spec Kit 的目錄
  10. 主動使用與不觸發的判斷（description）
  11. `--disallowedTools AskUserQuestion` 時改用文字提問
  12. 機密值不被記錄

  情境 1 至 6 在 Linux 與 Windows 各做一次（FR-021），其餘在任一平台做一次即可
- 自動測試只證明「必要的指示存在於 `SKILL.md`」，不證明 Claude 會照做（research.md R3）；FR-002 至 FR-008、FR-011、FR-014、FR-017、FR-020 的實際行為只由人工驗收確認
- 設計文件沒有寫明逐字內容之處（例如機密掃描的測試字串、`detail` 的完整句子）由實作者自行選擇，測試只比對設計文件有明寫的字串（`error` 句子、`.gitignore` 的兩行、欄位與項目名稱）；若實作時發現需要逐字比對而設計文件沒有寫明，向主代理提問，不自行假設
- 這個 repo 本身 `.specify/.gitignore` 中的 `sdd-grill-progress.md` 一行是 v1.0.1 之前手動加的，不在本功能範圍（plan.md 取捨第 2 點），不處理

## Phase 8: Convergence

- [X] T045 [US3] 讓 `confirmed` 階段的接續也能「重新開始」，並給不會自行消失的失敗一條出路 per FR-010, US3-3, US3-4, FR-018 (contradicts)。現況：`home/skills/sdd-grill/SKILL.md`「Resume」第 4 步明訂 `phase` 為 `"confirmed"` 時 "Skip step 3: do not offer to start over"，只問「繼續產生／停止」；「When something fails」禁止 `clear`，並告訴維護者再執行 `/sdd-grill` 就會接續。維護者若在兩次 session 之間改了既有 spec 或 constitution（`action` 為 `keep`），`verify` 每次都回報 `existing-spec-changed`／`constitution-changed`，每次重跑都停在同一個失敗，只能手動刪除 `.specify/sdd-grill/`。FR-010 與 US3-3 要求有既有進度時 MUST 讓維護者選擇接續或重新開始，沒有排除 `confirmed`。逐項處理：(1) `SKILL.md`「Resume」第 4 步：`confirmed` 時的那一題改為三個選項：繼續產生尚未產生的文件（Recommended）、重新開始、停止。說明選擇重新開始時執行 `clear` 清除進度，已產生的 constitution 與 spec 保留給維護者處理，MUST NOT 刪除或還原它們；清除後依「Start」第 5 步開始新的討論，並提醒新一批 spec 的編號會接在這些已產生的 spec 之後。原有的「do not reopen the discussion」要保留，意思是不在舊進度上改決定，不是不能重新開始。第 4 步中「`verify` 回報其他失敗時不繼續」的分支也要提供重新開始。(2) `SKILL.md`「When something fails」：分開兩種失敗。一種會在重跑後自行消失（例如中斷、Spec Kit skill 暫時失敗）；另一種不會：`existing-spec-changed`、`constitution-changed`，以及已記錄的 `spec_dir` 失去 `spec.md` 的 `spec-missing`。第二種要告訴維護者出路：把 `detail` 指出的檔案還原後再執行 `/sdd-grill`，或再執行 `/sdd-grill` 並選擇重新開始；不要只說「再執行就會接續」。(3) 同步修改 `specs/005-sdd-grill/contracts/skill.md`「接續」第 6 項，讓它與 spec 及新的 SKILL.md 一致：`confirmed` 時也可以重新開始，並說明已產生文件的處理方式（不修改 spec.md、plan.md）。(4) `tests/unit/test_sdd_grill_skill.py`：`test_resume` 的 `has_any(resume, "do not reopen", ...)` 若與新文字衝突就調整；加入檢查，確認「Resume」的 confirmed 分支提到 start over 與 `clear`，以及已產生的文件不刪除（字樣如 "do not delete"）；確認「When something fails」提到 `existing-spec-changed`、`constitution-changed` 與還原或重新開始的出路。(5) 腳本：已確認 `clear` 不看進度內容（`command_clear` 只檢查資料夾衝突），`confirmed` 階段也能清除，腳本不需要修改。但 `tests/unit/test_sdd_grill.py` 沒有這條路徑的測試：加入一個測試，在 `phase: "confirmed"`、有 `spec_dir`、已建立 spec 資料夾並改寫 constitution 的進度上執行 `clear`，確認只刪除 `.specify/sdd-grill/` 的兩個檔案與資料夾，`specs/`、`.specify/memory/constitution.md` 與 `.specify/feature.json` 都不變
- [ ] T046 [US2] 在 `SKILL.md` 補上 `confirmed` 階段兩個會讓 constitution 多出未確認規則或驗證誤判的情況 per FR-014, SC-003, FR-012 (partial)。(1)「Resume」第 4 步：接續時若 `verify` 沒有回報 `constitution-not-written`（constitution 已由 `speckit-constitution` 寫入），而且 `constitution.action` 是 `create` 或 `amend`，原本的步驟會直接跳過 constitution，但上次可能在「Generating the documents」第 2 步逐條比對、移除多出規則之前就中斷了。要指示讀者接續時先把 constitution 與摘要逐條比對一次（同第 2 步的規則：沒有依據的規則移除，想保留的一題一題問維護者），再繼續產生 spec。這與「unexpected 的 spec 資料夾要先比對內容」的處理對稱。(2)「Generating the documents」最後一段允許在還沒有任何 spec 時把 `phase` 改回 `"discussing"`，但沒有說明 constitution 已經產生的情況。改回 `discussing` 會讓 `baseline` 變成 `null`，重新確認時以已修改的 constitution 為新基準。結果：`amend` 若再次以相同內容呼叫 `speckit-constitution`，constitution 沒有變化，`verify` 會誤報 `constitution-not-written`；`create` 則會因為檔案已非範本而通過，即使改過的原則沒有寫入。請擇一寫明並讓兩處一致：只在 constitution 也尚未產生時才允許改回 `discussing`；或者說明 constitution 已產生時，改過的決定若涉及原則，重新確認後 MUST 再呼叫 `speckit-constitution` 套用差異並重新比對，若只涉及功能則不重跑 constitution 這一步。可以的話在 `tests/unit/test_sdd_grill_skill.py` 加上對應字樣的檢查
- [ ] T047 [US2] 讓 `SKILL.md`「Finishing」處理只修訂 constitution、沒有任何功能的一批 per FR-017, SC-007 (partial)。現況：`features` 為空時，`focus` 輸出 `"feature_directory": null` 且不寫入（`sdd_grill.py` 的 `command_focus`，測試 `test_focus_without_features_changes_nothing`），`verify` 的 `specs` 也是空陣列。但「Finishing」的報告一律寫「`.specify/feature.json` now points at the `feature_directory` from `focus`」，下一步一律是 `/sdd-drive` 或 `/speckit-plan`，讀者會回報「指向 null」，或要維護者對不存在的 spec 執行 `/sdd-drive`。補上這個分支：`feature_directory` 為 `null` 時說明沒有產生 spec、`.specify/feature.json` 沒有被更動，只回報 constitution 是建立或修訂；下一步改為提醒維護者既有 spec 是否需要依新的原則調整，有新需求時再執行 `/sdd-grill`，不建議 `/sdd-drive`。同時在「Order of the discussion」第 2 段寫明：需求只涉及原則、拆不出功能時，`features` 可以是空的（腳本允許），這時跳過第 3 段直接進入摘要。在 `tests/unit/test_sdd_grill_skill.py` 加入「Finishing」提到 `null` 或沒有 spec 時的處理的檢查
