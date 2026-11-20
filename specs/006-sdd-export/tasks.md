---

description: "Task list for 006 sdd-export 從舊專案匯出養分"
---

# Tasks: sdd-export 從舊專案匯出養分

**Input**: Design documents from `/specs/006-sdd-export/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/cli.md、contracts/skill.md、quickstart.md

**Tests**: 需要。Constitution（v1.0.2）原則 II 要求每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
腳本 `sdd_export.py` 的每個指令（`check`、`files`、`validate`、`write`）先寫測試、確認失敗，再實作；
`SKILL.md` 與 `README.md` 以結構與內容檢查驗證（關鍵字與段落順序，不比對完整文字）。
測試指令是 `uv run --with pytest pytest`。

**Organization**: 依 user story 分組。這是**對話式的 skill**（與 003 不同，與 005 同類）：對話行為（導出需求的品質、疑點與待確認的呈現、
教訓整理、確認前不寫入、差異呈現）無法在 CI 驗證，research.md R8 把每條 FR 對應到單元測試、結構／內容檢查或人工驗收。
本清單只為前兩類產生任務；只能人工驗收的部分（FR-004、FR-007 的判斷、FR-009 的整理等）見最後的 Notes，不列為勾選任務。
腳本的所有指令在同一支 `home/skills/sdd-export/scripts/sdd_export.py`，單元測試在同一份 `tests/unit/test_sdd_export.py`，
skill 的結構與內容檢查在 `tests/unit/test_sdd_export_skill.py`；改同一個檔案的任務依序進行。
SKILL.md 的各階段由多個任務依序寫入同一個檔案：每個任務都標明它負責 contracts/skill.md 的哪些條目與哪些「結果」列。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、沒有未完成的相依）
- **[Story]**: 所屬的 user story（US1 至 US4）；「契約鎖定」與 Polish 階段不加 story 標籤
- 路徑相對於 repo 根目錄
- `contracts/skill.md 第 N 項` 指該文件「SKILL.md 的內文」中編號為 N 的條目（1 至 39）；
  `階段 N 的結果列` 指該階段表格中的每一列（成功、各種失敗、維護者改變主意）
- 引用 data-model.md 的欄位時寫作 `data-model.md` 的 `Entity.field`；Entity 名稱對應小節：`Nutrients`（養分頂層）、`Scope`、
  `Item`（共通的項目欄位）、`Evidence`（依據）、`Principle`、`Feature`、`Requirement`、`Lesson`、`Discarded`、
  `Lineage`（世代紀錄頂層）、`LineageFeature`（世代紀錄中的功能）、`ReadScope`（讀取範圍）、`ExportDir`（專用目錄的狀態）

## 所有任務共同的限制

- 實作與驗證 MUST NOT 讀寫真正的家目錄 `~/.claude`，也 MUST NOT 把這個 skill 部署到那裡。
- MUST NOT 對這個 repo 自己、或這台機器上任何其他真實的專案執行 `sdd_export.py` 的 `write`（也不要拿它們當成「舊專案」實跑 `check`、`files`）；
  這個 repo 不得出現 `.sdd-export/` 或 `.sdd-rebuild/`。所有實際執行（測試、quickstart 手動情境）都在暫存目錄建立的假專案進行：
  pytest 用 `tmp_path`，手動情境用 `mktemp -d`，每個情境用新的暫存目錄。
- 這台機器的 `~/.claude/skills/` 下有另一個專案留下的 skill（可能含 `sdd-export`）。實作者 MUST NOT 讀取、複製或沿用它們；
  `SKILL.md`、`README.md` 與腳本只依本目錄的設計文件撰寫。
- 測試的 fixture 把 `HOME` 與 `USERPROFILE` 指向暫存目錄，所有 `git` 操作使用暫存 repository 並設定測試用的 `user.name`、`user.email`
  （並關閉全域與系統設定的影響，例如 `GIT_CONFIG_GLOBAL`／`GIT_CONFIG_NOSYSTEM`）。
- 不 commit 到 `main`、不切換或建立分支（目前在 `006-sdd-export`）；不 push；需要推送才能確認的工作只有 T056。
- 不修改 `.specify/`（含 `.specify/feature.json`）、`spec.md`、`plan.md` 與其他設計文件；設計文件有疑義時向主代理提問，不自行改文件。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認既有基礎可用，備妥測試 fixture

- [X] T001 確認 `home/skills/`、`tests/unit/`、`tests/conftest.py` 與 `.github/workflows/ci.yml` 已存在，`uv`、`git` 都在 `PATH` 上，且 `uv run --with pytest pytest` 在目前的分支全部通過（`tests/unit/test_claude_md.py` 中「引用的 skill 資料夾存在」一項在 6 個 skill 到齊之前跳過是預期的）；確認 `home/skills/sdd-export/` 與 `tests/unit/fixtures/sdd_export/` 尚不存在，且不讀取 `~/.claude/skills/` 下的任何內容
- [X] T002 擴充 `tests/conftest.py`（不改動既有的 fixture）：新增以 `importlib` 載入 `home/skills/sdd-export/scripts/sdd_export.py` 的 session fixture（載入時 MUST NOT 執行任何動作，見 contracts/cli.md「以模組方式載入」）；新增建立「假的舊專案」的輔助函式（可選擇是否 `git init`、可選擇是否有 `.specify/memory/constitution.md` 與 `specs/<名稱>/spec.md`、可放入任意檔案樹）；新增記錄目錄樹快照（相對路徑、型別、內容雜湊）並比對前後是否相同的輔助函式；新增以 `main(argv, root=…, stdin=…, stdout=…, stderr=…)` 呼叫腳本並取回結束碼、解析後的 stdout JSON、stderr 的輔助函式；新增把 `HOME`、`USERPROFILE` 指向暫存目錄並隔離全域 git 設定的 autouse fixture。不得在 fixture 中呼叫 `uv run` 以外的網路操作
- [X] T003 [P] 唯讀確認 `tools/deploy.py` 會自動納入 `home/skills/sdd-export/`（plan.md「Structure Decision」：不需要修改它），且 `.github/workflows/ci.yml` 的 `test` job 會執行 `tests/unit/` 下的新測試（plan.md：CI 不變）；若不成立，向主代理提問而不是自行修改

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 四個指令共用的核心：腳本骨架、輸出與結束碼、序列化與雜湊、路徑規則、機密樣式、只讀的 git 呼叫

**⚠️ CRITICAL**: 這個階段完成前不能開始任何 user story

- [X] T004 建立 `tests/unit/test_sdd_export.py` 並加入核心測試，確認在 T006 至 T009 實作前失敗：(1) 參數錯誤（沒有子指令、不認得的子指令、缺少必要選項如 `write` 沒有 `--expect`、多出參數）時結束碼 1、`reason` 為 `usage`、stderr 顯示用法；載入模組時不執行任何動作；(2) stdout 只有一份 JSON（UTF-8、LF、縮排 2、`ensure_ascii=False`、結尾換行、鍵順序固定），失敗時 JSON 有 `error` 與 `reason`，同一句 `error` 也寫到 stderr（contracts/cli.md「共通」「結束碼與 reason」）；結束碼常數 0、1、3（2 保留、4 不使用）；`--project` 不存在或不是目錄 → 結束碼 3、`reason: "project"`；`main(argv, root=None, stdin=None, stdout=None, stderr=None)` 的簽章可指定專案根目錄與 stdin；(3) 序列化（`data-model.md` 的「共通的序列化規則」）：UTF-8 無 BOM、LF、縮排 2、非 ASCII 不跳脫、結尾一個換行、物件鍵依 data-model 的順序（養分、世代紀錄各一組）、陣列保留給定的順序；(4) 內容雜湊：CRLF、CR 先換成 LF 再算 SHA-256，LF 與 CRLF 版本相同、其他差異不同；(5) 路徑規則：相對、`/` 分隔、不以 `/` 或 `./` 開頭、不含 `..`、不含磁碟代號，絕對路徑被拒；(6) `id` 格式 `^[a-z0-9]+(-[a-z0-9]+)*$` 與長度 ≤ 64；(7) `schema` 大於支援版本被辨識為「較新」而不是被猜測；(8) 機密樣式掃描對 data-model.md「機密樣式」列出的每一類（私鑰標頭、`ghp_`／`github_pat_`、`sk-`／`xox[abpr]-`／`AKIA`、URL 中的 `user:password@`、`password`／`secret`／`token`／`api_key`（含 `api-key`、`apikey`，不分大小寫）後接 `=` 或 `:` 與非空白值）都回報位置且輸出與錯誤訊息不含該值，一般的長識別字與一般文字不誤判；(9) 機密檔案的路徑判定對 data-model.md「機密檔案」列出的每一種名稱與 `.ssh`、`.aws`、`.gnupg` 目錄逐項測試，大小寫不分，`.env.example` 也算；(10) git 呼叫：只用 `rev-parse`、`ls-files`、`cat-file -e`，一律帶 `--no-optional-locks`（以放在 `PATH` 最前面的假 `git` 記錄收到的引數來驗證）；`git` 不存在或不是 git repository 時照常運作
- [X] T005 [P] 建立 `tests/unit/test_sdd_export_skill.py`，先加入針對腳本的靜態檢查（contracts/skill.md「scripts/sdd_export.py」；research.md R8 的 FR-020 列）：開頭有 uv inline metadata 且 `requires-python = ">=3.11"`、`dependencies` 為空；只 import 標準函式庫；不載入其他 skill 的程式；內容沒有絕對路徑與信箱；訊息與註解沒有中日韓文字（養分的繁體中文字串由使用者資料提供，不寫在腳本內）；腳本內沒有 `unlink`、`remove`、`rmtree`、`rmdir` 以外的刪除呼叫，且刪除只出現在 `write` 清理自己建立的暫存檔與本次建立的空目錄的程式路徑中（plan.md：沒有任何刪除指令）
- [X] T006 建立 `home/skills/sdd-export/scripts/sdd_export.py` 骨架：uv inline metadata（`requires-python = ">=3.11"`、`dependencies` 為空）；只用標準函式庫；`main(argv, root=None, stdin=None, stdout=None, stderr=None)` 回傳結束碼；四個子指令的分派（先回傳「尚未實作」的失敗，由後續任務實作）；`--project`、`--scope`（可重複）、`--expect` 的解析與用法錯誤；結束碼 0、1、3 的常數；JSON 輸出與錯誤輸出的共用函式（鍵順序固定、`error` 同步寫到 stderr）；`--project` 驗證（`reason: "project"`）；取得當天 UTC 日期的獨立函式（例如 `utc_today()`，讓測試可以注入固定日期；`exported_at` 只經由它取得）；載入為模組時不執行任何動作（contracts/cli.md「指令」「共通」「結束碼與 reason」「以模組方式載入」，contracts/skill.md「scripts/sdd_export.py」），讓 T004 的 (1)(2) 與 T005 通過
- [X] T007 在 `sdd_export.py` 實作共通的序列化與讀取規則，讓 T004 的 (3)(4)(5)(6)(7) 通過：序列化函式（養分與世代紀錄共用，依 `data-model.md` 的「共通的序列化規則」）、內容雜湊（先正規化換行）、讀取檔案時的換行正規化與 UTF-8 解碼（BOM 與非 UTF-8 視為無法讀取）、路徑檢查、`id` 檢查、`schema` 比較（較新時回報而不是猜測）；欄位 `Item.id` 與路徑規則依 `data-model.md`，所有輸出的路徑一律以 `/` 分隔、順序固定
- [X] T008 在 `sdd_export.py` 實作機密判定，讓 T004 的 (8)(9) 通過：機密樣式的字串掃描（回報位置，MUST NOT 回傳或印出該值）、檔案內容逐行掃描（回傳行號，不回傳內容）、機密檔案的路徑判定（只看路徑，MUST NOT 開啟檔案）；樣式與 005 相同但**複製一份**，不跨 skill 載入；樣式刻意保守（contracts/cli.md「以模組方式載入」的「機密掃描」）
- [X] T009 在 `sdd_export.py` 實作只讀的 git 輔助函式，讓 T004 的 (10) 通過：偵測 `git` 是否存在與專案是否為 git repository（`git --no-optional-locks rev-parse`）、列出檔案（`ls-files -z --cached --others --exclude-standard`，`git` 不可用時改為走訪目錄樹，不跟隨目錄的符號連結）、`cat-file -e <hash>^{commit}`；任何情況下都不執行會寫入的 git 子指令；`git` 不存在時 `commit:` 依據視為不存在（contracts/cli.md「共通」）

**Checkpoint**: 核心就緒，可以開始 user story

---

## Phase 3: User Story 1 - 把已有 spec 的專案匯出成養分 (Priority: P1) 🎯 MVP

**Goal**: `check`、`validate`、`write` 可用（含差異與 `README.md` 產生）；`SKILL.md` 寫出通則與階段 1、4（一般部分）、5 至 9 的完整指示，每個階段涵蓋每一種結果。

**Independent Test**: 三個指令的單元測試全部通過（在有 constitution 與 3 份 spec 的暫存專案，`write` 後只多出 `.sdd-export/` 的三個檔案、其餘檔案雜湊不變）；
`SKILL.md` 的結構與內容檢查涵蓋 contracts/skill.md 第 1–11、22、25–28、30–39 項與階段 1、4、5、6、7、8、9 的每一列結果。
對話行為（草稿內容、需求不描述實作、確認前零寫入、結束報告）由 quickstart.md 人工驗收情境 1 確認，不是本階段的勾選任務。

### Tests for User Story 1 ⚠️

> **NOTE: 先寫測試並確認失敗，再實作**

- [X] T010 [US1] 在 `tests/unit/test_sdd_export.py` 加入 `check` 的測試（contracts/cli.md「check」，data-model.md「專用目錄」「手動編輯的偵測」「`state`」）：在**沒有 `.specify/`、不是 git repository** 的目錄正常完成（FR-001），`project` 為目錄名稱、`git` 為 `false`、`constitution` 為 `null`、`specs` 為空、`lineage` 為 `"none"`、`generation` 為 1；有 `.specify/memory/constitution.md` 與 3 份 `specs/*/spec.md` 的專案（FR-005）列出 constitution 與依名稱排序的 `specs`、不檢查其他 Spec Kit 檔案；`export_dir` 逐一涵蓋 `none`、`empty`、`ours`（`README.md` 與 `.gitattributes` 可缺少）、`conflict`（路徑是檔案；目錄內有表外的項目；沒有 `nutrients.json` 卻有其他檔案；`nutrients.json` 的 `tool` 不是 `"sdd-export"`）、`unreadable`（非 UTF-8 JSON 物件）、`newer`、`invalid`（輸出 `errors` 含欄位路徑），結束碼 3 與對應的 `reason`（`conflict`、`nutrients-unreadable`、`nutrients-newer`、`nutrients-invalid`）、`conflict` 的 `error` 為 `.sdd-export/ holds files sdd-export did not create; nothing was read or written`，且結束碼 3 時仍輸出已能判定的欄位、不能判定的為 `null`；`nutrients` 為 `none`／`unchanged`／`edited`／`unknown`、`view` 為 `none`／`current`／`stale`／`edited`／`missing`、`gitattributes` 為 `ok`／`missing`／`edited` 逐值測試（以真實寫入的檔案再手動修改來製造）；`state` 在兩個檔案都不存在時是 `"none"`、內容改變時改變、CRLF 版本與 LF 版本相同；`writable` 在唯讀目錄為 `false`（Windows 以屬性設定；無法在該平台製造唯讀時以 `os.access` 的替身驗證）；**只讀**：`check` 前後的目錄樹快照相同，且沒有 `.venv`、`uv.lock`、`.sdd-export/` 被建立（SC-001）；`check` 以 `main` 與子行程 `uv run` 各執行一次的輸出相同（子行程版本在目前專案的暫存複本上執行，不在本 repo）
- [X] T011 [US1] 在 `tests/unit/test_sdd_export.py` 加入 `validate` 的結構與依據測試（contracts/cli.md「validate」，data-model.md「驗證規則」，research.md R8 FR-002、FR-003、FR-006、FR-007、FR-009 列），依 `check` 名稱逐項：`json`（stdin 不是有效 UTF-8 JSON 物件）；`field`（鍵齊全、多出的鍵如 `plan`、`tasks`、`code` 被拒、型別與列舉值：`Nutrients.language` 只能是 `zh-Hant`、`Feature.source`、`Requirement.kind`、`Requirement.source`、`Principle.source`、`Lesson.kind` 只接受三種值、`Discarded.kind` 含 `doubt`、草稿含 `tool`、`schema` 或 `exported_at` 被拒）；`id`（格式與整份唯一）；`range`（`Item.origin`、`Item.revised` 嚴格遞增且大於 `origin`、`Discarded.discarded_in`）；`code-block`（三個以上的 `` ` `` 或 `~` 開頭的行被拒，單行行內的反引號不被拒）；`secret`（字串含機密樣式 → `reason: "secret"`，同時有其他錯誤時仍是 `secret`，輸出沒有該值）；`evidence`（相對路徑存在、目錄也可以、不存在被拒、絕對路徑與 `..` 被拒、指向機密檔案被拒；`.sdd-rebuild/lineage.json` 與 `.specify/memory/constitution.md` 允許；`commit:<7–40 位小寫十六進位>` 在真實 git repository 中存在才通過，不存在、非 git repository、大寫或長度不符被拒；`maintainer` 通過）；`unsupported`（`Item.status` 為 `confirmed` 但 `Item.evidence` 為空被拒、`pending` 且為空通過，SC-003）；`spec`（`Feature.source` 為 `spec` 或 `mixed` 時 `Feature.spec` 必須是存在的檔案、`code` 或 `maintainer` 時可為 `null`）；`dependency`（`Feature.depends_on` 只能指向排在前面的功能，自我依賴與後面的功能被拒、因此沒有循環）；`scope`（`Scope.coverage` 為 `partial` 時 `Scope.included` 非空且每一項存在、`full` 時為空）；`Feature.requirements` 與 `features` 至少一個、`principles`／`lessons`／`discarded` 可為空（US3-3）；`Nutrients.project` 不得含 `/`、`\`；所有錯誤一次列出並依欄位路徑排序；`errors[].detail` 不含被判為機密的值；`counts` 的 `pending`、`inherited`、`new`；失敗時結束碼 1、`reason` 為 `invalid` 或 `secret`、`error` 為 `the draft is not valid nutrients`／`the draft looks like it contains a secret; describe what is needed instead of recording the value`；`validate` 不寫入任何檔案（前後目錄樹快照相同）。依據指向 `node_modules/` 等排除路徑的案例不在此任務，見 T027
- [X] T012 [US1] 在 `tests/unit/test_sdd_export.py` 加入差異的測試（data-model.md「差異」，contracts/cli.md「validate」的 `diff`）：沒有既有養分時 `base` 為 `"none"`、全部項目為 `added`；有既有養分時 `base` 為 `"nutrients"`，`added`、`removed`、`changed`（`fields` 的 `field`、`from`、`to`）以 `id` 為單位、各區段（`principles`、`features`、`requirements`、`lessons`、`discarded`）分開；`generation`、`scope` 有改變時是 `{"from","to"}`、否則 `null`；需求的 `id` 不變但移到另一個功能時 `field` 為 `"feature"`；`order_changed` 在功能順序改變時為 `true`；`title` 對沒有 `title` 的需求取 `text` 第一行至多 80 個字元；沒有差異時 `added`、`removed`、`changed` 皆為空；草稿無法解析時 `diff` 為 `null`；差異是純函式（給兩份養分回傳 `diff`，不依賴目前目錄）
- [X] T013 [US1] 在 `tests/unit/test_sdd_export.py` 加入 `write` 與 `README.md` 產生的測試（contracts/cli.md「write」「README.md 的產生」，data-model.md「專用目錄」，research.md R8 FR-010、FR-011、FR-014、FR-018 列）：**寫入範圍**：在有 constitution 與 3 份 spec 的專案 `write` 之後，目錄樹快照的差異只有 `.sdd-export/` 的三個檔案，其餘檔案的內容雜湊與模式不變，`.git/` 內容不變（SC-001）；`check`、`files`、`validate` 以外只有 `write` 會建立檔案（逐指令比對快照）；`write` 輸出 `written`（只列實際寫入的檔案）、`created`、`state`、`generation`、`counts`、`diff`；填入 `tool`、`schema`（1）、`exported_at`（以注入的固定日期，其他欄位的值不被草稿覆寫）；`nutrients.json` 為 LF、無 BOM；`.gitattributes` 為固定兩行（`# Created by sdd-export; keeps these files LF on every platform.` 與 `* text eol=lf`）、已存在時不改寫（維護者改過也不動，`check` 回報 `gitattributes: "edited"`）；`README.md` 第一行是標記 `<!-- Generated by sdd-export from nutrients.json; do not edit. source-sha256: <64 hex> view-sha256: <64 hex> -->`，`source-sha256` 等於 `nutrients.json`（換行正規化後）的 SHA-256、`view-sha256` 等於第二行起內容的 SHA-256；`README.md` 的結構依 contracts/cli.md：`# Nutrients: <project>` 與世代／匯出日期／範圍／數量、`## Principles`、`## Features`（每功能一個小節、其下依 `kind` 分組、每條需求標出 `id`、`origin`、`status`、依據，待確認標為 `(pending)`）、`## Lessons`（Decisions、Pitfalls、Reversed approaches）、`## Discarded`（表格）；相同輸入產生相同位元組；寫入後 `check` 回報 `export_dir: "ours"`、`nutrients: "unchanged"`、`view: "current"`；**`--expect`**：與目前 `state` 不同 → 結束碼 1、`reason: "changed"`、`error` 為 `.sdd-export/ changed since it was checked; check again and confirm the differences before writing`、不寫入；`--expect none` 對應目錄不存在；**寫入前再驗證**：草稿無效或含機密時 `write` 失敗（同 `validate`）且不寫入任何檔案；專案狀態結束碼 3（衝突等）時 `write` 照樣回報且不寫入、衝突目錄的檔案不變；**原子性**：以替身讓第二個 `os.replace` 失敗，確認 `nutrients.json` 是完整的新內容、暫存檔（`.nutrients.json.tmp-*`、`.README.md.tmp-*`）都被清除、`check` 之後回報 `view: "stale"`；以替身讓寫暫存檔失敗，確認舊的 `nutrients.json` 不變；本次建立的 `.sdd-export/` 在失敗後被移除、既有的空目錄不被移除；失敗時結束碼 1、`reason: "os-error"`、`error` 以 `could not write .sdd-export/: ` 開頭；唯讀專案（Linux `chmod -w`，在 Windows 上以替身；以 `skipif` 標明 root 或平台限制）`write` 失敗且沒有留下 `.sdd-export/`；以相同草稿、相同日期重複 `write`（第二次帶第一次輸出的 `state`），三個檔案內容逐位元組相同；`write` 不接受從檔案讀入草稿（沒有此選項）
- [X] T014 [P] [US1] 在 `tests/unit/test_sdd_export_skill.py` 加入 `SKILL.md` 的 frontmatter、通則與階段 1、4（一般部分）、5 至 9 的內容檢查（以關鍵字與段落順序，不比對完整文字；contracts/skill.md「SKILL.md 的 frontmatter」與「內文」第 1–11、22、25–28、30–39 項；research.md R8 的 FR-001、FR-002、FR-003、FR-008、FR-010、FR-011、FR-018 列）：frontmatter 只有 `name: sdd-export`、英文 `description`（含用途、在舊專案執行、不需要 Spec Kit、確認前不寫入、`/sdd-rebuild`）、`disable-model-invocation: true`、`argument-hint: "[scope path ...]"`，沒有其他欄位；內文沒有中日韓文字、絕對路徑、信箱；通則：`read-only`、`build`、`test`、`stdin`、禁止暫存檔；`.sdd-export/`；`speckit-` 與 `/sdd-init` 只在「不呼叫、不要求」的脈絡出現；`secret_files`、`secret_hits`；`AskUserQuestion`（建議排第一、一次一個決定、疑點一題一項、工具不能用時改用文字）；`Traditional Chinese`；`nothing is saved`；改變主意時修改草稿；`commit`（禁止 `git add`／`commit`／`push`）；`pending`（不編造）；階段 1：`check` 是第一個動作且在任何讀取專案檔案之前，且**逐一**涵蓋 contracts/skill.md 階段 1 的每一列結果（`uv` 不存在、`conflict`、`nutrients-unreadable`、`nutrients-invalid`、`nutrients-newer`、`lineage-newer`、`lineage-unreadable`、`lineage-invalid`、`lineage-conflict`、`writable`、`existing_generation`、`edited`、`unknown`、`inventory.files`、其他成功）且每個失敗結果都有「停止」與「不覆蓋」；階段 4：`generation` 取自 `check`、新項目 `id` 不重複；階段 5：區段順序（世代資訊 → 原則 → 功能 → 疑點 → 教訓）、`doubt`、`discarded`、每段決定後的簡短清單、確認前不寫入且在階段 8 之前，以及該階段每一列結果；階段 6：`validate` 在最終確認之前，且逐一涵蓋 `ok`、`secret`、結構錯誤（`field`、`id`、`range`、`code-block`、`dependency`、`scope`）、`unsupported`／`evidence`、世代規則錯誤（`lineage-item-missing`、`origin-changed`、`revision-unmarked`、`discard-lost`）、結束碼 3；階段 7：`counts`、`diff`、`view` 為 `edited` 時的告知、一題詢問，且涵蓋確認／修改／停止；階段 8：`write`、`--expect`，逐一涵蓋 `changed`、`conflict`、其他結束碼 3、`os-error`、維護者處理後重試、`invalid`／`secret`，且 `conflict`／`os-error` 時完整呈現確認後的草稿；階段 9：`/sdd-rebuild`、位置、可以提交但本 skill 不提交、`scope` 為 `partial` 時的說明、寫入後改變主意的說明

### Implementation for User Story 1

- [X] T015 [US1] 在 `sdd_export.py` 實作 `check`（`lineage` 先只處理 `.sdd-rebuild/lineage.json` 不存在的情況，固定為 `"none"` 與 `generation` 1；存在時的讀取與驗證在 T041 補完；`inventory` 先輸出空殼，T030 補完）：專案名稱、`git`、`writable`、專用目錄狀態與結束碼 3 的各個 `reason`、既有養分的讀取與驗證（獨立函式，給定路徑回傳狀態與內容或錯誤清單，contracts/cli.md「以模組方式載入」）、`nutrients`、`view`、`gitattributes`、`state`（兩個檔案的正規化雜湊以固定順序串接再取 SHA-256，不存在以空字串代表，兩者都不存在時為 `"none"`）、`constitution`（只檢查 `.specify/memory/constitution.md`）、`specs`（`specs/*/spec.md`，依名稱排序）、`existing`、`existing_generation`；衝突時在讀取專案之前就停止；只讀，不寫入。欄位與規則依 `data-model.md` 的 `ExportDir`（目錄的狀態表）、`Nutrients.tool`、`Nutrients.schema`、`Nutrients.generation`；讓 T010 通過
- [X] T016 [US1] 在 `sdd_export.py` 實作 `validate` 的驗證規則（除了世代規則與對排除路徑的依據檢查，它們分別在 T042 與 T029 補上）：草稿驗證為獨立函式（給定草稿、世代紀錄、既有養分與專案根目錄，回傳錯誤清單，contracts/cli.md「以模組方式載入」）；`json`、`field`、`id`、`range`、`code-block`、`secret`、`evidence`、`unsupported`、`spec`、`dependency`、`scope` 依 data-model.md「驗證規則」的順序，所有錯誤一次列出並依欄位路徑排序，`detail` 不含機密值；`counts`；失敗時結束碼 1 與 `reason`（含 `secret` 優先）。欄位依 `data-model.md` 的 `Nutrients.generation`、`Nutrients.project`、`Nutrients.language`、`Nutrients.scope`、`Scope.coverage`、`Scope.included`、`Item.id`、`Item.origin`、`Item.revised`、`Item.derived_from`、`Item.status`、`Item.evidence`、`Evidence`（三種形式）、`Principle.source`、`Feature.source`、`Feature.spec`、`Feature.depends_on`、`Feature.requirements`、`Requirement.kind`、`Requirement.source`、`Lesson.kind`、`Discarded.kind`、`Discarded.origin`、`Discarded.discarded_in`；`validate` 只讀；讓 T011 通過
- [X] T017 [US1] 在 `sdd_export.py` 實作差異計算（獨立純函式，給兩份養分回傳 `diff`）並接到 `validate` 的輸出，讓 T012 通過；欄位與規則依 data-model.md「差異」
- [X] T018 [US1] 在 `sdd_export.py` 實作 `write` 與 `README.md` 產生：專案狀態檢查 → `--expect` 比對 → 重新驗證（共用 T016 的函式，不複製）→ 填入 `tool`、`schema`、`exported_at`（經 `utc_today()`）→ 序列化 → 產生 `README.md`（含標記與兩個雜湊）→ 目錄不存在時建立並記下「本次建立」→ `.gitattributes` 不存在時寫入固定內容、存在時不動 → 兩個檔案各自先寫同目錄暫存檔（`.nutrients.json.tmp-<隨機>`、`.README.md.tmp-<隨機>`）→ 依序 `os.replace` → 任何 OS 錯誤時清除自己的暫存檔與本次建立的空目錄並回報 `os-error`；`write` 只寫 `.sdd-export/`；`README.md` 產生為純函式（養分 → 位元組）；讓 T013 通過。欄位與標記格式依 `data-model.md` 的 `Nutrients.tool`、`Nutrients.schema`、`Nutrients.exported_at`、`ExportDir`（`.gitattributes` 與「手動編輯的偵測」）
- [X] T019 [US1] 建立 `home/skills/sdd-export/SKILL.md`（英文），先寫 frontmatter 與通則：frontmatter 依 contracts/skill.md「SKILL.md 的 frontmatter」與 research.md R9（`name`、英文 `description`、`disable-model-invocation: true`、`argument-hint: "[scope path ...]"`，沒有其他欄位）；通則滿足 contracts/skill.md 第 1–10 項：只讀與允許的指令（Read、Grep、Glob 與只讀的 `git --no-pager log`／`show`／`ls-files`／`blame`，禁止建置、測試、安裝、格式化、專案自己的腳本，禁止 Write／Edit 建立任何檔案含暫存檔，草稿只經 stdin）；唯一的寫入是確認後的 `write`；不呼叫 `speckit-*`、不要求 `/sdd-init`；機密（`secret_files`、`secret_hits`，只記錄位置）；提問規則（`AskUserQuestion`、建議排第一並附理由、一次一個決定、是非題可複選、疑點一題一項、工具不能用時改用文字）；語言（`Traditional Chinese`、規範詞保留英文、其他語言的來源翻譯並於確認草稿時一併確認）；**維護者在確認前要求結束**（任何階段：不寫入、說明 `nothing is saved`、再執行會重新開始、停止）；**維護者在確認前改變先前的決定**（修改對應項目、最終確認時一併呈現、不重新討論其他項目）；不提交；不編造。所有腳本以 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" <command>` 在目前目錄執行、不使用 `--project`。內文 MUST NOT 含中日韓文字、絕對路徑、信箱。不使用 `~/.claude/skills/` 下任何內容
- [X] T020 [US1] 在 `SKILL.md` 加入階段 1「開始」，滿足 contracts/skill.md 第 11 項與**階段 1 的每一列結果**：第一個動作是執行 `check`（在讀取任何專案檔案之前）；`uv` 不存在或腳本無法執行 → 回報需要安裝 `uv` 並停止；結束碼 3 且 `reason` 為 `conflict` → 列出 `.sdd-export/` 中不是本功能產生的內容、說明不會覆蓋、請維護者移走或改名後再執行、停止；`nutrients-unreadable`／`nutrients-invalid` → 說明無法讀取並列出 `errors` 的欄位路徑、請維護者修正（或自行刪除 `.sdd-export/`）後再執行、停止、MUST NOT 覆蓋；`nutrients-newer`／`lineage-newer` → 說明來自較新版本、請更新 skill 後再執行、停止；`lineage-unreadable`／`lineage-invalid`／`lineage-conflict` → 列出原因、MUST NOT 把專案當成第一代、請修正後再執行、停止；結束碼 0 且 `writable: false` → 告知可以照常整理草稿但最後可能無法寫入，以一題詢問繼續（建議）或停止；`existing_generation` 不是 `null` 且不等於 `generation` → 列出兩者與可能原因（世代紀錄被移除、專案由其他專案複製），以一題詢問停止並檢查（建議）或以 `generation` 繼續；`nutrients` 為 `edited` 或 `unknown` → 告知既有養分被修改過（或無法判斷）、之後當成維護者的決定、繼續；`inventory.files` 為 0 → 說明專案沒有可讀取的內容並列出 `skipped` 數量、停止、不寫入；其餘成功 → 告知世代（`lineage` 為 `none` 時說明視為第一代）、是否已有養分（再次匯出）、是否有 constitution 與 spec，進入階段 2。每個停止的結果都說明沒有寫入任何東西。完成後 T014 中階段 1 的檢查應通過
- [X] T021 [US1] 在 `SKILL.md` 加入階段 4「組草稿」的一般部分，滿足 contracts/skill.md 第 22、25 項與階段 4 的「草稿組好 → 進入階段 5」一列：草稿的 `generation` 使用 `check` 的 `generation`、不自行計算；沒有世代紀錄也沒有既有養分時全部項目的 `origin` 為這一代；新項目的 `id` 不與世代紀錄或既有養分中任何 `id`（含 `discarded`）重複；草稿不含 `tool`、`schema`、`exported_at`。第 23、24 項與「世代紀錄中的項目無法對應」一列由 T043、T044 補上，本任務在階段 4 預留這兩處
- [X] T022 [US1] 在 `SKILL.md` 加入階段 5「呈現與逐項決定」，滿足 contracts/skill.md 第 26–28、30、31 項與**階段 5 的每一列結果**：依序呈現世代資訊 → 原則 → 功能、需求與相依關係（依相依順序）→ 疑點 → 經驗教訓，每項標出來源、來源世代與依據，待確認標為 `pending`／待確認；每段後請維護者決定全部接受、修改或刪除，被刪除的項目若是前代的或維護者希望記錄則移到 `discarded` 並記下理由；疑點一題一項：納入（成為需求或教訓並可修改文字）、標為待確認、捨棄（以 `doubt` 記入 `discarded`）；spec 與程式碼矛盾時兩邊都列、不自行選擇（呈現的是階段 3 記下的疑點）；每段決定後以簡短清單留下結論；確認之前不寫入任何檔案；結果列：接受／修改／刪除 → 更新草稿並繼續下一段；維護者要補充 → 加入草稿，依據為 `maintainer` 或維護者指出的檔案；要回頭修改已決定的段落 → 依通則第 8 項；全部區段決定完 → 階段 6；要求結束 → 依通則第 7 項。第 29 項由 T036 補上
- [X] T023 [US1] 在 `SKILL.md` 加入階段 6「驗證」，滿足 contracts/skill.md 第 32 項與**階段 6 的每一列結果**：在最終確認之前以 stdin 把完整草稿交給 `validate`；`ok: true` → 階段 7；`reason: "secret"` → 把 `errors` 指出的欄位改寫成不含該值的描述、MUST NOT 在對話中重複該值、再 `validate`；`reason: "invalid"` 的結構或格式錯誤（`field`、`id`、`range`、`code-block`、`dependency`、`scope`）→ 修正後再 `validate`，不涉及內容意義的修正不必詢問；`unsupported` 或 `evidence` → 補上正確的依據或改為待確認並告訴維護者；世代規則的錯誤（`lineage-item-missing`、`origin-changed`、`revision-unmarked`、`discard-lost` 等）→ 依錯誤修正，需要維護者決定的以一題詢問；結束碼 3 → 依階段 1 的同名結果處理（專案狀態在對話途中改變）
- [X] T024 [US1] 在 `SKILL.md` 加入階段 7「最終確認」，滿足 contracts/skill.md 第 33–35 項與**階段 7 的每一列結果**：呈現整體摘要（`counts`、待確認的項目、捨棄的項目）；`diff.base` 為 `nutrients` 時呈現新增、移除、修改（新舊值），沒有差異時明說；`view` 為 `edited` 時告知寫入會重新產生 `.sdd-export/README.md` 並蓋掉手動修改，請維護者決定併入草稿或放棄；以一題詢問確認寫入（建議）、修改、停止；確認 → 階段 8；要修改 → 回到階段 5 的對應區段，修改後重新經過階段 6、7；停止 → 依通則第 7 項
- [X] T025 [US1] 在 `SKILL.md` 加入階段 8「寫入」，滿足 contracts/skill.md 第 36 項與**階段 8 的每一列結果**：以 stdin 把確認後的草稿交給 `write --expect <check 的 state>`；結束碼 0 → 階段 9；`reason: "changed"` → 說明養分在對話途中被修改、重新 `check`、以新的 `existing` 重新組差異並 `validate`、回到階段 7 再次確認；`reason: "conflict"`（結束碼 3）→ 停止、回報衝突的路徑、把確認後的草稿完整呈現在對話中讓維護者自行保存、不寫到其他地方；其他結束碼 3 → 依階段 1 的同名結果處理並完整呈現確認後的草稿；`reason: "os-error"` → 回報原因、完整呈現確認後的草稿、說明 `.sdd-export/` 沒有留下半份檔案、以一題詢問維護者處理後重試或停止（建議）；維護者處理後要求重試 → 重新 `check`，`state` 與先前相同時以同一份確認後的草稿再次 `write`、不同時依 `changed` 處理；`reason: "invalid"` 或 `"secret"`（不應發生）→ 回到階段 6
- [X] T026 [US1] 在 `SKILL.md` 加入階段 9「結束報告」，滿足 contracts/skill.md 第 37–39 項與**階段 9 的每一列結果**（此階段沒有表格，內容如下全部要有）：依 `write` 的輸出回報養分的位置（`.sdd-export/nutrients.json`、可讀版本 `.sdd-export/README.md`）、世代、納入的項目（各類數量、繼承與新增）、待確認的項目、捨棄的項目；說明可以提交到 repo（由維護者決定、本 skill 不提交）；下一步是在**新專案**執行 `/sdd-rebuild` 並指定這個舊專案的路徑；然後停止、不 commit、不 push；`scope` 為 `partial` 時另外說明可以再執行 `/sdd-export` 匯出其他範圍（範圍外既有項目原樣保留）；寫入後維護者改變主意 → 說明可以再執行 `/sdd-export` 修改（以這份養分為起點），或自行編輯、刪除 `.sdd-export/`。完成後 T014 的全部檢查應通過

**Checkpoint**: `check`、`validate`、`write` 的測試通過；`SKILL.md` 的通則與階段 1、4（一般）、5 至 9 的內容檢查通過；US1 的主流程完整

---

## Phase 4: User Story 2 - 沒有 spec 時從程式碼導出需求 (Priority: P1)

**Goal**: `files` 與 `check` 的 `inventory` 可用（排除規則、機密位置、過大判定、範圍）；`SKILL.md` 寫出階段 2「範圍」與階段 3「讀取」的完整指示。

**Independent Test**: 在只有程式碼、沒有 Spec Kit、不是 git repository 的暫存專案，`files` 列出的清單排除相依套件、建置產物與機密檔案，`secret_hits` 只有路徑與行號；`SKILL.md` 的內容檢查涵蓋 contracts/skill.md 第 12–21 項與階段 2、3 的每一列結果。
導出的需求品質、依據與待確認的呈現、疑點獨立一節、沒有執行建置或測試（quickstart.md 人工驗收情境 2、3）由維護者驗收。

### Tests for User Story 2 ⚠️

- [X] T027 [US2] 在 `tests/unit/test_sdd_export.py` 加入 `files` 與 `inventory` 的測試（contracts/cli.md「files」，data-model.md「讀取範圍」「機密」，research.md R8 FR-008、FR-015、FR-016、FR-017 列）：排除類別（`skipped` 的每個鍵）逐項——`dependency`（data-model 列出的每個目錄名）、`build`（每個目錄名與 `*.egg-info`）、`tooling`（頂層 `.git`、`.idea`、`.vscode`、`.claude`、`.sdd-export`、`.sdd-rebuild`、`.specify`，且 `.specify/memory/constitution.md` 可讀）、`generated`（每個鎖定檔名與 `.min.js`、`.min.css`、`.map`）、`secret`、`binary`（副檔名與開頭 8 KiB 含 NUL）、`large`（大於 1 MiB）、`ignored`（git repository 中被 `.gitignore` 忽略的檔案，以及指向專案外的符號連結；不跟隨目錄的符號連結，無法建立符號連結的平台以 `skipif` 標明）；以真實 `git` 與不是 git 的目錄各測一次，兩者的結果在沒有 `.gitignore` 時相同，`ignore_source` 分別為 `git` 與非 git 的值；`files` 帶 `--scope`（可重複）只含這些路徑之下的可讀檔案，**一律**加上 constitution 與 `specs/*/spec.md`；`--scope` 的路徑不存在、在專案外或屬於排除範圍 → 結束碼 1、`reason: "usage"`；`too_large` 的三個條件各測一次（可讀檔案數 > 1500、總大小 > 10 MiB、兩個以上區塊的頂層含套件描述檔，逐一涵蓋 data-model 列出的描述檔名稱含 `*.csproj`、`*.sln`），剛好等於門檻時不算過大；`too_large` 時不帶範圍的 `files` 回傳空的 `files` 與 `secret_hits`，帶 `--scope` 縮小後列出；`areas` 為頂層目錄各一、頂層檔案合為 `"."`，各有 `files`、`bytes`、`manifests`；機密：機密檔案**不被開啟**（以 `open` 的替身或讀取權限被移除的檔案驗證腳本沒有嘗試開啟，且 `.env.example` 也不被開啟）、`secret_files` 只有路徑、`secret_hits` 只有 `path` 與 `line`，整份輸出沒有被掃描到的機密值；輸出的路徑一律 `/` 分隔且排序固定；`files` 與 `check` 前後目錄樹快照相同、沒有 `.venv`／`uv.lock`；在 T011 未涵蓋的部分補上 `validate` 的 `evidence` 對排除路徑（`node_modules/…`、`dist/…`）的拒絕；`check` 的 `inventory` 與 `files`（不帶範圍）的數量一致、不列出個別檔案；同一份資料樹在 Linux 與 Windows 的清單相同（比對路徑以小寫化名稱判定的規則）
- [X] T028 [P] [US2] 在 `tests/unit/test_sdd_export_skill.py` 加入階段 2、3 的內容與順序檢查（contracts/skill.md 第 12–21 項；research.md R8 的 FR-005、FR-006、FR-008、FR-016、FR-017 列）：階段 2：啟動時附範圍路徑就用 `files --scope`、`too_large` 時先列出 `areas` 並以 `AskUserQuestion`（可複選）請維護者選擇、**在選定範圍前不讀取專案檔案**、`scope` 為 `partial` 並列出 `included`、之後可以再執行 `/sdd-export` 與範圍外項目原樣保留；順序：`too_large`／`--scope` 在階段 3 之前；且逐一涵蓋階段 2 的每一列結果（不過大、`files` 結束碼 1 與 `usage`、`too_large` 仍為 `true`、維護者不願縮小範圍（建議分批、仍拒絕則停止不寫入）、維護者選擇停止）；階段 3：只讀取 `files` 列出的檔案、`constitution` 與 `specs` 一定要讀、`mixed`、只描述程式碼目前實際的行為並附依據檔案、不描述實作、疑點（疑似 bug、文件與程式碼矛盾、spec 與程式碼矛盾兩邊都記）不混入需求、plan／tasks／程式碼不抄進養分（plan 類文件只作教訓依據），且逐一涵蓋階段 3 的四列結果（至少一個有依據的功能 → 階段 4；內容不足 → 說明原因並停止不寫入；檔案無法讀取 → 略過並記下、不改用其他指令；內容讀不完 → 停止讀取、建議縮小範圍、回到階段 2）；第 4 項的 `secret_files` 不讀取在階段 3 重申

### Implementation for User Story 2

- [X] T029 [US2] 在 `sdd_export.py` 實作讀取範圍（獨立函式，給專案根目錄與範圍回傳可讀檔案、各類排除的數量與機密檔案，contracts/cli.md「以模組方式載入」）：data-model.md「讀取範圍」的七類排除與常數（目錄名、檔名、副檔名、門檻、套件描述檔，集中成常數）、`.specify/memory/constitution.md` 例外、以路徑各段小寫化後比對（兩個平台一致）、`git` 可用時以 T009 的 `ls-files`、否則走訪目錄樹、符號連結規則、`binary` 判定（副檔名與開頭 8 KiB 的 NUL，不對機密檔案做這件事）、`large` 判定（stat，不讀內容）、`too_large` 與 `areas`；機密檔案只以路徑判斷、**不開啟**；並補上 `validate` 的 `evidence` 對排除路徑的拒絕（接入 T016）；欄位與規則依 `data-model.md` 的 `ReadScope`（類別表、過大、區塊）與「機密檔案」，讓 T027 的排除與過大部分通過
- [X] T030 [US2] 在 `sdd_export.py` 實作 `files` 指令與補完 `check` 的 `inventory`：`--scope`（可重複、不存在或在專案外或被排除 → `usage`）、一律包含 constitution 與 `specs/*/spec.md`、`scope`、`too_large`、`files`、`secret_hits`（掃描可讀檔案、只輸出路徑與行號，使用 T008 的逐行掃描）、`skipped`、`secret_files`；`too_large` 時 `files` 與 `secret_hits` 為空陣列；`check` 的 `inventory` 不列出個別檔案；兩者只讀；讓 T027 全部通過
- [X] T031 [US2] 在 `SKILL.md` 加入階段 2「範圍」，滿足 contracts/skill.md 第 12–14 項與**階段 2 的每一列結果**：啟動時附範圍路徑就以 `files --scope <路徑>...` 使用；沒有附範圍且 `inventory.too_large` 為 `true` 時 MUST 先列出 `areas`（檔案數、大小、套件描述檔）、以 `AskUserQuestion`（可複選）請維護者選擇範圍、再以 `files --scope` 取得清單，選定範圍前 MUST NOT 讀取專案檔案；範圍不是整個專案時草稿的 `scope` 為 `partial` 並列出 `included`，並說明之後可再執行 `/sdd-export` 選擇其他範圍、範圍外既有項目原樣保留；結果列：不過大且沒有範圍 → 以 `files`（不帶 `--scope`）取得清單進入階段 3；`files` 結束碼 1 且 `reason: "usage"` → 說明哪個路徑無效、重新請維護者選擇；`files` 的 `too_large` 仍為 `true` → 說明範圍仍太大、請再縮小；維護者不願縮小 → 說明一次讀不完、建議分批匯出、仍拒絕則停止不寫入；維護者選擇停止 → 依通則第 7 項
- [X] T032 [US2] 在 `SKILL.md` 加入階段 3「讀取」（不含第 19 項的教訓整理，那是 T036），滿足 contracts/skill.md 第 15–18、20、21 項與**階段 3 的每一列結果**：只讀取 `files` 列出的檔案、`constitution` 與 `specs` 列出的文件一定要讀、`secret_files` 不讀取；有 spec 的功能以 spec 為來源，沒有或部分涵蓋的從文件、設定、測試與程式結構導出，部分涵蓋時功能的 `source` 為 `mixed` 且各需求標明自己的來源；從程式碼導出的需求只描述程式碼目前實際的行為、每項附依據檔案、無法確定的標為待確認；需求只描述使用者需求與可驗收的行為、MUST NOT 描述現行實作方式；疑似 bug、文件與程式碼的矛盾、spec 與程式碼的矛盾、改進建議記為疑點、不混入需求、spec 與程式碼矛盾時兩邊的說法都記下；養分 MUST NOT 含 plan、tasks、程式碼，plan 類文件只作教訓依據；結果列：讀完能提出至少一個有依據的功能 → 階段 4；內容不足以提出任何有依據的需求 → 說明原因（例如只有設定檔）、停止、不寫入；某個檔案無法讀取 → 略過並記下、在草稿的說明中列出、不改用其他指令；範圍內讀不完（context 不足）→ 停止讀取、說明並建議縮小範圍、回到階段 2。完成後 T028 的檢查應全部通過

**Checkpoint**: `files`、`inventory` 的測試與 `SKILL.md` 階段 2、3 的內容檢查通過；US1 與 US2 合起來是完整的主流程

---

## Phase 5: User Story 3 - 帶出經驗教訓 (Priority: P2)

**Goal**: 教訓的資料規則（三類、依據、待確認、可為空）由腳本驗證；`SKILL.md` 寫出教訓整理與「找不到依據」的指示。

**Independent Test**: `validate`／`write` 的單元測試證明教訓只接受三種 `kind`、沒有依據必須是 `pending`、刪除一項後寫入的養分不含它、沒有教訓的養分有效；`SKILL.md` 的內容檢查涵蓋 contracts/skill.md 第 19、29 項。
教訓整理的品質與依據可追溯（quickstart.md 人工驗收情境 4）由維護者驗收。

### Tests for User Story 3 ⚠️

- [X] T033 [US3] 在 `tests/unit/test_sdd_export.py` 加入教訓的測試（research.md R8 FR-009 列，spec US3）：`Lesson.kind` 只接受 `decision`、`pitfall`、`reversed`，其他值被拒；`confirmed` 的教訓需要依據（檔案路徑、`commit:<hash>`（真實 git repository 中存在的 commit）、`maintainer`），沒有依據必須是 `pending`；`evidence` 為 `commit:` 但專案不是 git repository 或 commit 不存在時被拒；`lessons` 為空的草稿有效且 `write` 成功（US3-3：找不到且維護者不補充）；兩份草稿相同、其中一份少了一條教訓（維護者刪除）時，`write` 後 `nutrients.json` 不含它且 `validate` 的 `diff` 列為 `removed`（有既有養分時）；教訓內容含程式碼區塊被拒；這些測試若在 T016、T018 完成後已全部通過，保留為鎖定測試（先確認它們對錯誤實作會失敗，例如暫時放寬 `kind` 驗證）
- [X] T034 [P] [US3] 在 `tests/unit/test_sdd_export_skill.py` 加入教訓的內容檢查（contracts/skill.md 第 19、29 項；research.md R8 的 FR-009 列）：階段 3 的教訓整理來源（文件、spec 與 plan 類文件、只讀的 git 歷史）、三類字樣 `decision`、`pitfall`、`reversed`、每項附依據（檔案或 `commit:<hash>`）、沒有依據標為待確認；階段 5 的第 29 項：找不到任何可作為教訓的依據時說明沒有找到、詢問維護者是否口頭補充、口頭補充的依據記為 `maintainer`、MUST NOT 自行編造（字樣：`maintainer`）；以及該情境的每一個結果（維護者補充 → 加入教訓；維護者不補充 → `lessons` 為空並繼續）

### Implementation for User Story 3

- [X] T035 [US3] 依 T033 的結果修正 `sdd_export.py` 的 `validate`、`write`，使 T033 全部通過（欄位依 `data-model.md` 的 `Lesson.kind`、`Item.status`、`Item.evidence`、`Evidence`）；若 T033 在前面任務完成後已全部通過，在回報中註明沒有需要修正的地方
- [X] T036 [US3] 在 `SKILL.md` 補上教訓的指示，滿足 contracts/skill.md 第 19、29 項（並涵蓋其所有結果）：階段 3 加入「從專案的文件、spec 與 plan 類文件、git 歷史（只讀的 git 指令）整理教訓，分為重要決定與理由（`decision`）、踩過的坑（`pitfall`）、被推翻的做法（`reversed`），每項附依據（檔案或 `commit:<hash>`），沒有依據標為待確認」；階段 5 的教訓區段加入第 29 項：找不到任何可作為教訓的依據時說明沒有找到並以一題詢問維護者是否口頭補充；口頭補充 → 加入教訓、依據記為 `maintainer`；維護者不補充 → `lessons` 為空並繼續；MUST NOT 自行編造。只在對應的既有階段內補充，不改動其他段落的順序。完成後 T034 的檢查應全部通過

**Checkpoint**: US1 至 US3 可獨立運作

---

## Phase 6: User Story 4 - 世代延續 (Priority: P2)

**Goal**: 世代紀錄的讀取與驗證、世代編號、世代規則 1–9、再次匯出（既有養分為起點、手動編輯、並行保護、分批匯出）可用；`SKILL.md` 寫出世代與再次匯出的組草稿指示。

**Independent Test**: 在帶有 `generation: 2` 的世代紀錄與 2 份新增 spec 的暫存專案，`check` 回報世代 2，繼承項目保留 `origin: 1`、新增項目為 `origin: 2`，`validate` 依世代規則拒絕每一種違反；`SKILL.md` 的內容檢查涵蓋 contracts/skill.md 第 23、24 項與階段 4 的剩餘結果列。
世代延續與再次匯出的實際對話（quickstart.md 人工驗收情境 5、6）由維護者驗收。

### Tests for User Story 4 ⚠️

- [X] T037 [US4] 在 `tests/unit/test_sdd_export.py` 加入世代紀錄讀取的測試（contracts/cli.md「check」，data-model.md「世代紀錄」「006 讀取時的驗證」，research.md R8 FR-012 列）：沒有 `.sdd-rebuild/lineage.json` → `lineage: "none"`、`generation` 1；有效紀錄 → `"present"`、`generation` 為紀錄的 `generation`、`lineage_content` 為完整內容、`specs[].in_lineage` 依 `LineageFeature.spec_dir` 對應、`lineage_missing_specs` 列出 `spec_dir` 已不存在的功能；`existing_generation`（既有養分的世代）與 `generation` 不同時兩者如實輸出；`unreadable`（非 UTF-8 JSON 物件）、`newer`（`schema` 較大）、`invalid`（結構錯誤並輸出 `errors`：`Lineage.generation` 不等於 `source.generation` + 1 或小於 2、`Item.origin` 與 `Item.revised` 範圍、`id` 重複、`depends_on` 沒有排在前面、`LineageFeature.spec_dir` 不是 `specs/` 底下一層資料夾、有 `status` 或 `evidence`（世代紀錄不含它們）、`source` 值 `rebuild` 被接受）、`conflict`（`tool` 不是 `"sdd-rebuild"`）→ 結束碼 3 與 `lineage-unreadable`、`lineage-newer`、`lineage-invalid`、`lineage-conflict`，且不會把專案當成第一代（`generation` 為 `null`）；CRLF 版本的世代紀錄可讀；`.sdd-rebuild/` 內的其他檔案不被讀取（以 `open` 的替身驗證只開了 `lineage.json`）；`check` 只讀（目錄樹快照不變）
- [X] T038 [US4] 在 `tests/unit/test_sdd_export.py` 加入世代規則的測試（data-model.md「世代規則」，research.md R8 FR-012、FR-013 列、SC-006），對每一條規則各有一個通過案例與一個違反案例，違反時 `errors` 的 `check` 名稱為規定的值、一次列出所有違反：規則 1 `generation`（草稿與 `check` 的世代不同）；規則 2 `lineage-item-missing`（世代紀錄中的原則、功能、需求、教訓各一種都不能無聲消失，可以是仍為有效項目、在 `discarded`、或出現在其他項目的 `derived_from`）；規則 3 `origin-changed`；規則 4 `origin-unknown`（`origin` 小於 `generation` 的項目能在世代紀錄或既有養分找到）；規則 5 `revision-unmarked`（`title`、`text`、`summary` 不同時 `revised` 必須含這一代）；規則 6 `discard-lost`（世代紀錄的 `discarded` 與既有養分中 `discarded_in` 小於 `generation` 的捨棄紀錄必須原樣出現，內容被改也算違反）；規則 7 `discarded-active`；規則 8 `derived-unknown`（含「沿用前代記下的來源、那些 `id` 屬於更早的世代」的通過案例）；規則 9 `id-reused`（`origin` 等於 `generation` 的項目不得與世代紀錄任何項目含 `discarded` 同 `id`）；沒有世代紀錄也沒有既有養分時，世代規則 2、3、5、6 不產生錯誤；`lineage-item-missing` 的 `detail` 指出項目 `id`；**三代追溯（SC-006）**：以固定的測試資料建立三代——第 1 代匯出的養分、依 data-model.md「007 寫入時 MUST 遵守的規則」表手寫的第 2 代世代紀錄、第 2 代匯出（繼承項目 `origin: 1`、新增項目 `origin: 2`）、手寫的第 3 代世代紀錄（含合併與捨棄）、第 3 代匯出——每一代的 `validate` 與 `write` 通過，且第 3 代養分中第 1 代的需求仍以同一個 `id` 與 `origin: 1` 出現，或以 `discarded` 記錄它在哪一代被捨棄；每一代使用 `tmp_path` 中的假專案，固定資料放在 `tests/unit/fixtures/sdd_export/`
- [X] T039 [US4] 在 `tests/unit/test_sdd_export.py` 加入再次匯出的測試（data-model.md「手動編輯的偵測」「狀態轉移」，research.md R4、R7，R8 FR-014 列）：第二次 `write`（以第一次輸出的 `state`）取代同一個 `nutrients.json`，目錄中仍只有三個檔案、沒有第二份；`check` 的 `existing` 為既有養分的完整內容；手動修改 `nutrients.json` 一條需求的文字後 `check` 回報 `nutrients: "edited"`、`view: "stale"`，以原本草稿 `validate` 的 `diff.changed` 列出那一條；把 `nutrients.json` 改成無效 JSON → 結束碼 3、`nutrients-unreadable`，復原後恢復；手動修改 `README.md` 本文 → `view: "edited"`，刪除 `README.md` → `view: "missing"` 且 `nutrients: "unknown"`；`write` 在 `view` 為 `edited` 時重新產生 `README.md` 並覆蓋；`.sdd-export/.gitattributes` 被改過不被改寫；以舊 `state` 寫入 → `changed` 且檔案不變；兩批匯出：第一批 `scope` 為 `partial` 並列出 `included`，第二批以既有養分為起點加入其他範圍的項目並改為 `full`，第二批的 `diff` 只有 `added` 與 `scope` 變更、第一批的項目不在 `removed` 與 `changed`；功能順序改變時 `order_changed` 為 `true`；依據沒有改變的項目重複匯出的 `diff` 為空
- [X] T040 [P] [US4] 在 `tests/unit/test_sdd_export_skill.py` 加入階段 4 世代與再次匯出的內容檢查（contracts/skill.md 第 23、24 項與階段 4 的第二列結果；research.md R8 的 FR-012、FR-013、FR-014 列）：`lineage` 為 `present` 時：`in_lineage` 的 spec 沿用紀錄的 `id` 與 `origin`、內容不同時在 `revised` 加上這一代、不在紀錄中的 spec 成為 `origin` 為這一代的新功能、`lineage_missing_specs` 以一題詢問保留（依紀錄的內容）或捨棄、紀錄的教訓詢問是否仍適用（可複選）且不適用的移到 `discarded`、紀錄的 `discarded` 原樣保留（字樣：`lineage`、`origin`、`discarded`）；`export_dir` 為 `ours` 時：以 `existing` 為起點、沿用 `id`、依據沒有改變的項目不改寫文字、範圍外的既有項目原樣保留、`nutrients` 為 `edited` 或 `unknown` 時要改動既有內容 MUST 逐項詢問（字樣：`existing`）；階段 4 的「世代紀錄中的項目無法對應到目前的任何內容」一列：依第 23 項詢問保留或捨棄、不讓它無聲消失；檢查階段 1 的 `existing_generation` 不一致與 `lineage-*` 的處理已在 T014 涵蓋，此處確認兩處的敘述一致（同一個字樣）

### Implementation for User Story 4

- [X] T041 [US4] 在 `sdd_export.py` 補完 `check` 的世代部分並實作世代紀錄的讀取與驗證（獨立函式，給定路徑回傳狀態與內容或錯誤清單，contracts/cli.md「以模組方式載入」）：`lineage` 六個值與結束碼 3 的四個 `reason`、`generation`（`present` 為紀錄的 `generation`、`none` 為 1、其他為 `null`）、`lineage_content`、`specs[].in_lineage`、`lineage_missing_specs`、`existing_generation`；只讀 `.sdd-rebuild/lineage.json`、不讀該目錄的其他檔案；可檢查的規則依 data-model.md「006 讀取時的驗證」；讓 T037 通過。欄位依 `data-model.md` 的 `Lineage.tool`、`Lineage.schema`、`Lineage.generation`、`Lineage.source`、`Lineage.features`、`LineageFeature.spec_dir`、`Item.origin`、`Item.revised`、`Item.id`、`Feature.depends_on`
- [X] T042 [US4] 在 `sdd_export.py` 的 `validate` 加入世代規則 1 至 9（接在 T016 的驗證之後，與其他錯誤一起一次列出並依欄位路徑排序；`check` 名稱與 data-model.md「世代規則」一致；「前代的項目」的定義依該節），讓 T038、T039 通過；欄位依 `data-model.md` 的 `Nutrients.generation`、`Item.origin`、`Item.revised`、`Item.derived_from`、`Discarded.discarded_in`、`Discarded.origin`；若 T039 中某些測試在前面任務後已通過，在回報中註明
- [X] T043 [US4] 在 `SKILL.md` 階段 4 加入世代延續，滿足 contracts/skill.md 第 23 項與階段 4 的「世代紀錄中的項目無法對應」一列：`lineage` 為 `present` 時，世代紀錄中 `in_lineage` 的 spec 對應的功能沿用紀錄的 `id` 與 `origin`；內容與紀錄不同時在 `revised` 加上這一代；不在紀錄中的 spec 成為 `origin` 為這一代的新功能；`lineage_missing_specs` 中的每個功能以一題詢問保留（依紀錄的內容）或捨棄；紀錄中的教訓詢問是否仍然適用（可複選），仍適用的沿用 `id` 與 `origin`、不適用的移到 `discarded`；紀錄中的 `discarded` 全部原樣保留；`lineage` 為 `none` 時視為第一代、所有項目 `origin` 為這一代；紀錄中的項目無法對應到目前任何內容時依本項詢問保留或捨棄、不讓它無聲消失。只在階段 4 內補充，不改動其他階段
- [X] T044 [US4] 在 `SKILL.md` 加入再次匯出，滿足 contracts/skill.md 第 24 項並與階段 1、7、8 一致：`export_dir` 為 `ours` 時以 `existing` 為起點、既有項目沿用 `id`、依據沒有改變的項目不改寫文字、範圍外的既有項目原樣保留（與階段 2 的 `partial` 呼應）；`nutrients` 為 `edited` 或 `unknown` 時，要改動既有內容 MUST 逐項詢問（把維護者手動編輯的內容視為維護者的決定）；呈現差異與 `view: "edited"` 的處理引用階段 7；`write` 回報 `changed` 時重新以新的 `existing` 組差異引用階段 8；確認寫入後仍只有一份 `nutrients.json`。完成後 T040 的檢查應全部通過

**Checkpoint**: 四個 user story 都可獨立運作

---

## Phase 7: 007 依賴的契約鎖定 (Cross-Cutting)

**Purpose**: 養分（`nutrients.json`）與世代紀錄（`lineage.json`）的格式是 007 sdd-rebuild 的契約（data-model.md 開頭）。以測試鎖定：兩個平台寫出的位元組相同、`schema` 版本、世代規則的每一條（T038 已逐條測試，這裡鎖定 007 的寫入規則表）、以及 data-model.md 的範例本身通過 `validate`，讓文件與腳本不會各自漂移。

- [X] T045 在 `tests/unit/test_sdd_export.py` 加入位元組鎖定測試（FR-019、SC-007，research.md R8 的 FR-019 列第 1 點）：建立 `tests/unit/fixtures/sdd_export/`，放入一份固定的草稿（`draft.json`）、預期的 `nutrients.json` 與 `README.md` 位元組；測試以注入的固定日期（`utc_today()`）`write` 同一份草稿，`nutrients.json`、`README.md`、`.gitattributes` 逐位元組等於 fixture（兩個平台的 `test` job 都執行，因此兩個平台都等於同一份位元組）；比對前先確認 fixture 檔案不含 CR（避免 checkout 設定改變時誤判）；`nutrients.json` 的 fixture 以 data-model.md 的序列化規則**手動推導**（鍵順序、縮排、非 ASCII 不跳脫、結尾換行；可從 data-model.md「最小範例」去掉 `exported_at` 以外的差異後比對），不得直接以腳本輸出覆蓋；`README.md` 的 fixture 在 T018 完成後依 contracts/cli.md「README.md 的產生」逐項檢視確認結構與內容無誤後才固定，之後任何變更 MUST 同時說明理由；另測 `schema` 為 1、`schema` 較大的養分被辨識為較新而不被讀取、鍵順序固定；`README.md` 標記中的兩個雜湊以測試自己計算的值比對
- [X] T046 在 `tests/unit/test_sdd_export.py` 加入文件範例測試（防止 data-model.md 的範例過時）：測試從 `specs/006-sdd-export/data-model.md` 擷取「最小範例」的 JSON 區塊（以標題定位，找不到時測試失敗而不是跳過），在暫存專案中依範例的前提建立所需檔案（`specs/001-deploy/spec.md`、`.specify/memory/constitution.md`、依 data-model.md「007 寫入時 MUST 遵守的規則」寫成的第 2 代 `.sdd-rebuild/lineage.json` fixture，含 `deploy`、`cross-platform`、`atomic-write` 與被捨棄的 `deploy-symlink`），把範例去掉 `tool`、`schema`、`exported_at` 後當成草稿，`validate` 回傳 `ok: true` 且 `write` 成功，寫出的 `nutrients.json` 去掉 `exported_at` 後在語意上等於範例；同樣擷取 data-model.md 中其他完整的 JSON 範例（若有）驗證；另加一個測試確認「最小範例」的 `generation` 與 fixture 世代紀錄的 `generation` 一致
- [X] T047 在 `tests/unit/test_sdd_export.py` 加入換行與 `.gitattributes` 的鎖定測試（FR-019，research.md R8 的 FR-019 列第 2、3 點）：把 `nutrients.json`、`README.md`、`.gitattributes` 與世代紀錄改成 CRLF 版本，`check` 仍能讀取與驗證、`nutrients` 為 `unchanged`、`view` 為 `current`、`state` 與 LF 版本相同、不被判為手動編輯；以真實 `git` 建立含 `.sdd-export/`（`.gitattributes` 與 `nutrients.json`）與另一個一般文字檔的 repository，`git -c core.autocrlf=true clone` 後刪除檔案再 `git checkout -- .`，確認 `.sdd-export/` 下的檔案為 LF（一般檔案可為 CRLF，不比對）；沒有 `git` 時整個測試以 `skipif` 標明
- [X] T048 在 `tests/unit/test_sdd_export.py` 加入「007 寫入規則」的鎖定測試（data-model.md「007 寫入時 MUST 遵守的規則」表的每一列，research.md R3）：以八個小案例各自手寫一份依該列規則產生的世代紀錄與對應的下一次匯出草稿，驗證被接受——原樣保留、修改後保留（`revised` 加上這一代）、合併多個項目（新 `id`、`origin` 為這一代、`derived_from` 為被合併的 `id`、被合併的項目不必另記為捨棄）、拆分一個項目、重建時新增（`source` 為 `rebuild`）、捨棄（移到 `discarded`、`discarded_in` 為 `generation`）、來源養分的 `discarded` 原樣帶入、來源養分中 `pending` 的項目依維護者決定套用其他列（世代紀錄中不得有 `status`）；再各寫一個違反該列的案例（例如合併後 `derived_from` 缺少來源、捨棄後 `id` 消失且不在 `discarded`、`origin` 被重設）驗證 `check` 或 `validate` 以世代規則拒絕；schema 較大的世代紀錄 → `lineage-newer`
- [X] T049 依 T045 至 T048 的結果修正 `sdd_export.py` 與 fixtures，使全部通過；若發現 data-model.md 或 contracts 與實作在逐字處矛盾，向主代理提問，不自行修改設計文件；若這四個任務在前面任務完成後已全部通過，在回報中註明沒有需要修正的地方

**Checkpoint**: 007 依賴的兩份格式與規則由測試鎖定

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: README、skill 資料夾的整體檢查、SKILL.md 的通讀走查、腳本手動情境實跑、完整測試與 CI

- [X] T050 [P] 在 `tests/unit/test_sdd_export_skill.py` 加入資料夾與 README 的檢查（contracts/skill.md「檔案」「README.md」；research.md R8 的 FR-020 列）：`home/skills/sdd-export/` 內只有 `SKILL.md`、`README.md`、`scripts/sdd_export.py` 三個檔案；`SKILL.md` 英文、無中日韓文字、無絕對路徑與信箱（T014 已涵蓋，合併成一次完整檢查即可）；`README.md` 含繁體中文，並涵蓋：用法 `/sdd-export [範圍路徑...]` 與不需要 Spec Kit、只能由維護者啟動；前置需求（`uv`、`git` 非必要）；流程（讀取只讀 → 草稿 → 逐項決定 → 確認 → 寫入，確認前不寫入、中途結束不留下任何東西）；產出（`.sdd-export/` 三個檔案、`nutrients.json` 是唯一資料來源、`README.md` 是產生的版本、可提交到 repo、下一步在新專案執行 `/sdd-rebuild`）；世代（沒有 `.sdd-rebuild/lineage.json` 是第一代、有時沿用）；再次匯出（更新同一份、差異、手動編輯逐項詢問）；大型專案（先選範圍、分批匯出）；機密（不開啟的檔案類型、樣式攔截與其限制）；不做的事（不修改 `.sdd-export/` 以外的任何檔案、不執行建置或測試、不呼叫 Spec Kit、不提交、不刪除）；腳本檔案沒有 `write` 以外的寫入路徑已由 T005 涵蓋
- [X] T051 撰寫 `home/skills/sdd-export/README.md`（繁體中文，指令與識別字保留原文），依 contracts/skill.md「README.md」逐項涵蓋，讓 T050 通過；若 repo 根目錄的 `README.md` 列有 skill 的現況，同步更新 `sdd-export` 的狀態（先 `grep` 確認；沒有列則不改）；不修改 `home/CLAUDE.md`、`specs/` 下任何設計文件（若發現 `home/CLAUDE.md` 引用 `/sdd-export` 的敘述與實作不符，向主代理提問）
- [X] T052 逐項核對 contracts/skill.md「內文」第 1–39 項與每個階段表格的**每一列結果**都有至少一條對應的內容檢查（在 `tests/unit/test_sdd_export_skill.py` 以一個以條目編號為鍵的對照表實作，讓新增或遺漏條目時測試失敗而不是靜默通過），缺少的補上測試；確認順序檢查齊全：`check` 在讀取任何專案檔案之前、範圍選擇（`too_large`／`--scope`）在階段 3 之前、`validate` 在最終確認之前、最終確認在 `write` 之前、`write` 在結束報告之前；確認 `SKILL.md` 提到的每個指令與欄位（`check`、`files --scope`、`validate`、`write --expect`、`generation`、`existing_generation`、`export_dir`、`nutrients`、`view`、`state`、`lineage`、`lineage_missing_specs`、`inventory.too_large`、`inventory.files`、`areas`、`secret_files`、`secret_hits`、`counts`、`diff`、`reason` 的每個值）都存在於 contracts/cli.md（測試以文字集合比對，對 cli.md 中沒有的欄位名稱失敗）
- [X] T053 **SKILL.md 通讀走查**（SKILL.md 全部寫完後）：實作者以「沒有任何背景的讀者」身分，只依 `home/skills/sdd-export/SKILL.md` 與它引用的指令輸出通讀一遍，依 contracts/skill.md 走過**每個階段的每一種結果**（階段 1 至 9 的每一列，以及通則第 7、8 項在每個階段的行為），確認：(1) 沒有死路——每個結果都有明確的下一步（繼續、回到某階段、停止），沒有「未定義」；(2) 沒有互相矛盾的指示（例如「確認前不寫入」與任何階段的寫入、`check` 優先與提前讀取、建議選項的排序、停止時是否說明沒有寫入）；(3) 提到的每個指令、選項、欄位與 `reason` 值都與 contracts/cli.md 一致（逐一核對，不憑記憶）；(4) 階段間的交叉引用（階段 6 的「依階段 1 同名結果處理」、階段 7 回到階段 5、階段 8 的 `changed` 回到階段 7、重試時重新 `check`）指向存在且正確的段落；(5) 沒有要求 Claude 做 SKILL.md 禁止的事（寫暫存檔、`git add`、呼叫 `speckit-*`）。把走查的結果寫進任務回報：列出每個階段走過的結果數量、發現的缺漏與矛盾及其修正（修正直接改 `SKILL.md`，並補上對應的內容檢查）；若沒有發現問題也要明說「走查 N 條路徑，沒有發現缺漏」。若發現 contracts/skill.md 本身與 cli.md 矛盾，向主代理提問，不自行修改設計文件。這是本清單中唯一不產生新功能、只做檢查的 SKILL.md 任務，不可省略
- [X] T054 依 `specs/006-sdd-export/quickstart.md`「手動情境（腳本）」的 9 個情境，在 `mktemp -d` 建立的暫存目錄逐一實跑 `uv run <repo>/home/skills/sdd-export/scripts/sdd_export.py`，並修正與預期不符之處；每個情境用新的暫存目錄（情境 1 的專案不是 git repository、沒有 Spec Kit，含 `node_modules/x/index.js`、`dist/app.js`、`.env`（`API_KEY=dummy`）、`src/settings.py`（一行 `password = "hunter2"`））；情境 6 另建專案；情境 7 的世代紀錄依 data-model.md「世代紀錄」自行寫成；情境 8 在 Linux 以 `chmod -w`（以非 root 身分，root 時說明並略過）、Windows 無法實跑時說明；情境 9 以腳本產生 1600 個小檔案。每個情境記錄目錄樹前後比較的結果。MUST NOT 在這個 repo 的目錄、真正的 `~/.claude` 或這台機器上其他真實專案執行；MUST NOT 讀取 `~/.claude/skills/`
- [X] T055 執行完整測試 `uv run --with pytest pytest`，結束碼 0；確認 `git status` 中 `.specify/`（含 `.specify/feature.json`）、`specs/` 的設計文件與 `~/.claude` 都沒有被這次的工作更動，這個 repo 內沒有 `.sdd-export/` 或 `.sdd-rebuild/`；確認 `tests/unit/test_claude_md.py` 在 `home/skills/sdd-export/SKILL.md` 存在後仍通過（「引用的 skill 資料夾存在」一項在 6 個 skill 到齊之前可能仍跳過，如實回報）；確認工作區沒有未提交的內容。Windows 上的結果由 T056 的 CI 確認（constitution 原則 II）
- [ ] T056 **由主代理在維護者授權推送後處理，實作的 worker 不執行這一項、不 push**：推送分支後確認 `.github/workflows/ci.yml` 的 `test`、`cross-platform-produce`、`cross-platform` 三個 job 在 `ubuntu-latest` 與 `windows-latest` 都通過；Windows 上的位元組鎖定（T045）、CRLF 與 `core.autocrlf`（T047）、唯讀情境、符號連結的 `skipif` 行為以 CI 結果為準，失敗時依紀錄修正後再確認

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依賴 001 至 005 已在目前的分支
- **Foundational (Phase 2)**: 依賴 Setup；T004 先於 T006 至 T009；T005 與 T004 可同時進行（不同檔案）
- **US1 (Phase 3)**: 依賴 Foundational；T010 至 T013 先於 T015 至 T018；T014 先於 T019 至 T026；`SKILL.md` 的段落依 T019 → T026 的順序寫入同一個檔案；T018 依賴 T016、T017
- **US2 (Phase 4)**: 依賴 US1 的 `check`（T015）與 `validate`（T016）；T027 先於 T029、T030；T028 先於 T031、T032；T029 補上 T016 預留的排除路徑依據檢查
- **US3 (Phase 5)**: 依賴 US1；T033 先於 T035；T034 先於 T036；T036 在 T032 之後（階段 3 已存在）與 T022 之後（階段 5 已存在）
- **US4 (Phase 6)**: 依賴 US1（`check` 的既有養分、`write`）；T037 至 T039 先於 T041、T042；T040 先於 T043、T044；T043、T044 在 T021 之後（階段 4 已存在）
- **契約鎖定 (Phase 7)**: 依賴 US1 與 US4（T018、T042）；T045 的 `README.md` fixture 在 T018 之後才固定
- **Polish (Phase 8)**: 依賴 Phase 3 至 7；T053 依賴 T019 至 T044 與 T051；T056 依賴 T055，且需要維護者授權推送

### Within Each Story

- 測試先寫、先確認失敗，再實作
- 腳本的任務（`sdd_export.py`、`test_sdd_export.py`）依序進行；`SKILL.md` 的段落任務依序進行；`test_sdd_export_skill.py` 的測試任務標 [P]（與腳本任務不同檔案）

### Parallel Opportunities

- T003 與 T001、T002 可同時進行
- T005 與 T004、T006 至 T009 可同時進行（不同檔案）
- 各 story 中標 [P] 的 skill 內容檢查（T014、T028、T034、T040）可與腳本任務同時撰寫；但各自要先於對應的 `SKILL.md` 任務完成
- T050 可與腳本相關任務（T045 至 T049）同時進行

### Parallel Example: User Story 1

```text
# 不同檔案，可同時進行：
Task: "T010 至 T013 check、validate、diff、write 的單元測試 in tests/unit/test_sdd_export.py"
Task: "T014 SKILL.md 的通則與階段 1、4、5 至 9 的內容檢查 in tests/unit/test_sdd_export_skill.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. 完成 Phase 1 與 Phase 2
2. 完成 Phase 3（US1）：`check`、`validate`、`write`、`SKILL.md` 的通則與階段 1、4、5 至 9
3. 完成 Phase 4（US2）：`files`、讀取範圍、`SKILL.md` 的階段 2、3；US1 與 US2 都是 P1，合起來才是完整的主流程
4. **STOP and VALIDATE**: 單元測試與內容檢查通過；對話行為交給維護者以人工驗收確認

### Incremental Delivery

1. US3：教訓的鎖定測試與指示
2. US4：世代紀錄、世代規則、再次匯出
3. 契約鎖定：位元組、範例、CRLF、007 寫入規則
4. Polish：README、通讀走查、quickstart 實跑、完整測試、CI（T056）

---

## Notes

- 每完成一個任務或一組相關任務就 commit（分支 `006-sdd-export`，不 commit 到 `main`）；不 push，推送由主代理在維護者授權後進行（T056）。本 skill 自己不 commit 舊專案（plan.md 取捨第 7 點），這與實作本功能時的 commit 規則是兩回事
- 維護者已核可 plan.md「需要維護者注意的取捨」全部 11 項，實作時照 plan 的寫法，不需要再確認。其中與任務直接相關的：專用目錄 `.sdd-export/` 與世代紀錄 `.sdd-rebuild/lineage.json`（第 1 點）、單一 JSON 加產生的 `README.md`（第 2 點）、字串內容一律繁體中文（第 3 點）、沒有進度檔（第 4 點，所以沒有 `save`／`clear` 與接續的任務）、世代規則由腳本強制（第 5 點）、`disable-model-invocation: true`（第 6 點）、不 commit（第 7 點）、固定常數的門檻（第 8 點）、FR-019 不新增 cross-platform job（第 9 點）
- **人工驗收不列為勾選任務**：quickstart.md「人工驗收（真實 session）」的 7 個情境需要真實的 Claude Code session（部署到暫存的家目錄，`HOME=<test-home>` 與 `CLAUDE_CONFIG_DIR=<test-home>/.claude`，或在測試機上），由維護者在合併並部署後進行並記錄結果與日期：
  1. 有 spec 的專案（US1、FR-002 至 FR-004、FR-010、FR-011、FR-018）：草稿內容完整、確認前 `git status` 無變化、確認後只多出 `.sdd-export/`、養分不含 plan／tasks／程式碼、需求不描述實作、結束報告、沒有呼叫 `speckit-*`、沒有 commit
  2. 只有程式碼的專案（US2、FR-001、FR-005 至 FR-008、FR-015）：不要求 `/sdd-init`、依據或待確認、疑點一節與一題一項、沒有開啟 `.env`、密碼不出現在對話與養分、沒有建置或測試
  3. 大型專案與部分 spec（FR-016、FR-017、US2-4）：先列出區塊並選範圍、`node_modules/` 不被讀取、`scope` 為 `partial`、再次執行其他範圍時前一次的項目保留
  4. 經驗教訓（US3、FR-009）：三類、各附依據、刪除後不在養分；沒有歷史時說明沒有找到並詢問
  5. 世代延續（US4、FR-012、FR-013、SC-006）：世代為 2、繼承項目 `origin: 1`、新增項目 `origin: 2`、前代教訓逐項詢問、捨棄紀錄保留；手寫第 3 代世代紀錄再匯出一次，第 1 代需求仍以 `origin: 1` 出現
  6. 再次匯出（FR-014、US4-4）：說明養分被手動編輯過、改動前逐項詢問、最終確認前呈現差異、確認後從另一個終端機修改 `nutrients.json` 時回報被修改並重新確認、寫入後仍只有一份
  7. 中斷與失敗（Edge Cases）：(a) 中途要求結束、(b) `.sdd-export/` 已有別的檔案時讀取前就停止、(c) 唯讀專案草稿照常整理且寫入失敗時完整呈現草稿、(d) 只有一個設定檔的專案說明內容不足並停止

  核心情境 1、2、5 在 Windows 與 Linux 各做一次，其餘在任一平台做一次即可
- 自動測試只證明「腳本的行為」與「必要的指示存在於 SKILL.md」，不證明 Claude 會照做（research.md R8）；FR-004、FR-005 的導出品質、FR-007 的疑點判斷、FR-009 的教訓整理、FR-006 的依據是否真實，只由人工驗收確認，因此沒有對應的自動測試任務
- **逐字比對的範圍**：測試只逐字比對設計文件有明寫的字串：`error` 的句子（contracts/cli.md 列出的 `.sdd-export/ holds files sdd-export did not create; nothing was read or written`、`.sdd-export/ changed since it was checked; check again and confirm the differences before writing`、`the draft is not valid nutrients`、`the draft looks like it contains a secret; describe what is needed instead of recording the value`、`could not write .sdd-export/: <原因>` 的前綴）、`reason` 與 `check` 名稱的列舉值、`README.md` 的標記格式、`.gitattributes` 的兩行、`README.md` 的標題與標籤（`# Nutrients: <project>`、`## Principles`、`## Features`、`## Lessons`、`## Discarded`、`(pending)`）。**`README.md` 其餘排版與 `detail` 的完整句子設計文件沒有逐字規定**：前者以「結構斷言＋T045 的 golden fixture（plan.md R8 規定的固定位元組，由實作者在依 contracts/cli.md 逐項檢視 T018 的輸出後固定）」鎖定，後者只檢查欄位與 `check` 名稱、不比對句子；`state` 的串接細節只測性質（內容改變則改變、換行無關、兩個檔案都不存在為 `"none"`），不比對雜湊值。若實作時發現需要逐字比對而設計文件沒有寫明，向主代理提問，不自行假設
- `exported_at` 取決於當下日期：腳本經獨立的 `utc_today()` 取得，測試注入固定日期；這是實作內部的測試縫，不是設計文件規定的介面，名稱由 T006 決定即可
- 這個 repo 本身不是「舊專案」：不要在其中產生 `.sdd-export/`；`tools/deploy.py` 與 `home/CLAUDE.md` 不在本功能的修改範圍，除非 T003、T051 發現不符並經主代理同意
