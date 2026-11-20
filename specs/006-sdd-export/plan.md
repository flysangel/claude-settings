# Implementation Plan: sdd-export 從舊專案匯出養分

**Branch**: `006-sdd-export` | **Date**: 2026-11-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-sdd-export/spec.md`

## Summary

維護者在任意的舊專案（不必導入 Spec Kit、不必是 git repository）輸入 `/sdd-export`。Claude 以只讀的方式讀取專案：
有 spec 的功能以 spec 為準，其餘從文件、設定、測試與程式結構導出；整理原則、各功能的需求與相依、經驗教訓與世代資訊，
把疑點與需求分開，依區段呈現草稿、逐項請維護者決定；維護者確認後，養分一次寫入舊專案根目錄的 `.sdd-export/`，
然後回報位置並說明下一步是在新專案執行 `/sdd-rebuild`。

做法：與 005 相同，這是**對話式的 skill**。讀取與導出、判斷疑點、整理教訓、呈現與詢問寫在 SKILL.md 由 Claude 執行；
可以決定性完成的事集中在一支由 uv 執行、輸出 JSON 的 Python 腳本 `sdd_export.py`：專案現況與世代（`check`）、
可讀取的檔案清單與機密位置（`files`）、草稿的驗證與差異（`validate`）、確認後的寫入（`write`）。
養分是單一的 `nutrients.json`（唯一的資料來源，007 讀取它）加上由它產生的可讀版本 `README.md`。
世代紀錄由 007 寫在新專案的 `.sdd-rebuild/lineage.json`，格式由本 plan 定義（[data-model.md](./data-model.md)）。
沒有進度檔：確認前不寫入任何內容，大型專案以縮小範圍與分批匯出處理（[research.md](./research.md) R7）。

## Technical Context

**Language/Version**: Python 3.11+（由 uv 依腳本內的 inline metadata 自動提供）；SKILL.md 與 README.md 為 Markdown

**Primary Dependencies**: 執行期只用 Python 標準函式庫；外部指令只有只讀的 `git`（`rev-parse`、`ls-files`、`cat-file -e`，
帶 `--no-optional-locks`，可有可無）。不依賴 Spec Kit，不呼叫任何 `speckit-*` skill

**Storage**: 檔案。舊專案的 `.sdd-export/nutrients.json`、`.sdd-export/README.md`、`.sdd-export/.gitattributes`（入庫）；
讀取新專案（已重建的專案）的 `.sdd-rebuild/lineage.json`（由 007 寫入）

**Testing**: pytest，`uv run --with pytest pytest`；GitHub Actions 的 `test` job 在 `ubuntu-latest` 與 `windows-latest` 執行。
腳本的單元測試在暫存目錄以真實的檔案與 `git` 進行；skill 的結構／內容檢查比照 `tests/unit/test_sdd_grill_skill.py`；
對話行為以 [quickstart.md](./quickstart.md) 的人工驗收在真實 session 驗證

**Target Platform**: Linux 與 Windows 上的 Claude Code

**Project Type**: Claude Code skill（一份 SKILL.md、一份 README、一支腳本）

**Performance Goals**: `check`、`files` 在 1500 個可讀檔案以內的專案於數秒內完成（`git ls-files` 加上逐檔 stat 與機密樣式掃描）；
`validate`、`write` 在 1 秒內完成；對話本身沒有效能目標

**Constraints**:

- 維護者確認之前，專案零異動；腳本只有 `write` 會寫入，而且只寫 `.sdd-export/` 的三個檔案與同目錄的暫存檔；沒有任何刪除指令
- 全程只讀：不執行建置、測試或任何會產生檔案的指令；git 只用只讀的子指令；草稿只經 stdin 傳遞，不在專案內放暫存檔
- 不開啟機密檔案；機密值不出現在對話、草稿與養分中（指示 + 寫入前的樣式攔截）
- 養分的格式是 007 的輸入契約；世代紀錄的格式是 007 的輸出契約；兩者都有 `schema` 版本
- 不 commit、不 push；不依賴 `.specify/`
- 產出只有 skill 文件或 script；Python 一律用 uv 執行

**Scale/Scope**: 一次匯出數個到數十個功能、數百條需求；`nutrients.json` 數百 KB 以內；單一使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 constitution v1.0.2 逐條檢查。

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | sdd-export 不呼叫、不修改任何 Spec Kit 的檔案或 `speckit-*` skill，也不寫入 `.specify/`（包括 `.specify/feature.json`）。專案有 Spec Kit 時只讀取 `.specify/memory/constitution.md` 與 `specs/*/spec.md`。養分放在頂層的 `.sdd-export/`、世代紀錄放在頂層的 `.sdd-rebuild/`，都不在 `.specify/` 內，所以不需要處理「工具在 `.specify/` 內新增的檔案要記錄歸屬」這一條（R2、R3）。 |
| II. Windows 與 Linux 完全對等 | 通過 | 兩個平台執行同一支腳本與同一份 SKILL.md；序列化固定為 UTF-8、LF、`/` 分隔的相對路徑，讀取時先正規化換行；`.sdd-export/.gitattributes` 讓 checkout 維持 LF。單元測試與結構檢查在既有 `test` job 的兩個平台執行；FR-019 以「兩個平台寫出的位元組都等於同一份固定測試資料」、CRLF 版本可讀、`core.autocrlf=true` 的 clone 維持 LF 三項單元測試驗證，不新增 cross-platform job（R8）。對話行為無法在 CI 驗證，以人工驗收補足，核心情境在兩個平台各做一次。 |
| III. 保護既有檔案 | 通過 | 腳本只寫 `.sdd-export/` 內自己的三個檔案，從不刪除專案的檔案；目錄已存在但有不是本功能產生的內容（或同名檔案）時視為衝突，`check` 在讀取專案之前就停止並回報。既有養分被手動編輯而無法讀取時停止，不覆蓋；可讀取時以它為起點，手動編輯的內容改動前逐項詢問；`write --expect` 防止蓋掉對話途中的手動修改。`.gitattributes` 被維護者改過時不改寫。唯一會被重新產生而蓋掉手動修改的是本功能產生、標明「請勿編輯」的 `README.md`，寫入前先告知維護者並請他決定（R4）。只讀指令重複執行結果相同；以相同草稿、相同日期重複 `write`，檔案內容逐位元組相同。 |
| IV. 先確認再寫入 | 通過 | 本功能不產生 constitution 或 spec，但養分是 007 產生它們的依據，所以同樣適用：確認前不寫入（FR-010），草稿依區段逐項決定、最終確認時呈現差異；沒有依據的項目只能是 `pending`，`validate` 決定性地拒絕「`confirmed` 但沒有依據」與「依據不存在」（SC-003）；疑點不會以未決狀態進入養分。 |
| V. 個人使用、repo 公開 | 通過 | 沒有可調選項（門檻與排除清單是腳本內的常數）。養分會被提交到舊專案的 repo，所以不寫入機密值（指示 + `validate`／`write` 的樣式攔截，依據不得指向機密檔案），路徑一律相對、不含機器專屬路徑，`project` 只是名稱。本 skill 的檔案不含絕對路徑與信箱（結構測試檢查）。 |
| VI. 文件語言 | 通過 | SKILL.md 與腳本訊息為英文；skill 資料夾有繁體中文 README；本功能的 plan 文件為繁體中文，規範詞保留英文。養分的字串內容使用繁體中文（欄位名稱與列舉值英文），讓 007 產生的 constitution 與 spec 符合原則 VI（R2）。腳本產生的 `README.md` 標籤為英文、內容為養分原文。 |

Phase 1 設計後重新檢查（2026-11-20）：結果相同。設計階段確定的幾點都已涵蓋在上表：
頂層專用目錄與衝突規則（原則 I、III）、手動編輯的偵測與 `--expect`（原則 III）、世代規則與「`confirmed` 必須有依據」
由腳本驗證（原則 IV）、固定的序列化與 `.gitattributes`（原則 II）。沒有需要記錄在 Complexity Tracking 的違反。

## Project Structure

### Documentation (this feature)

```text
specs/006-sdd-export/
├── plan.md              # 本檔
├── research.md          # Phase 0：分工、養分格式與目錄、世代與世代紀錄、再次匯出、讀取範圍與只讀、機密、中斷與失敗、測試、frontmatter
├── data-model.md        # Phase 1：養分、世代紀錄（007 的契約）、草稿、世代規則、驗證、差異、讀取範圍、機密
├── quickstart.md        # Phase 1：自動測試、腳本手動情境與人工驗收情境
├── contracts/
│   ├── cli.md           # sdd_export.py 的指令、結束碼、reason 與 JSON 輸出
│   └── skill.md         # skill 資料夾的結構與 SKILL.md 的必要指示（每個階段的每種結果）
├── checklists/
│   └── requirements.md  # 由 /speckit-specify 產生
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
home/skills/sdd-export/              # 本功能的產出，部署後位於 ~/.claude/skills/sdd-export/
├── SKILL.md                         # 英文；對話的進行方式與何時呼叫腳本
├── README.md                        # 繁體中文簡述
└── scripts/
    └── sdd_export.py                # check、files、validate、write

tests/
├── unit/
│   ├── test_sdd_export.py           # 腳本：在暫存目錄以真實的檔案與 git 測試，不需要網路
│   ├── test_sdd_export_skill.py     # skill 資料夾的結構與 SKILL.md 的必要指示
│   └── fixtures/sdd_export/         # 固定的草稿、預期的 nutrients.json 與 README.md 位元組、三代的世代紀錄
└── conftest.py                      # 新增載入 sdd_export.py 的 fixture

.github/workflows/ci.yml             # 不變；既有 test job 會執行新的測試
```

**Structure Decision**: 沿用 003 至 005 的 skill 結構（SKILL.md、README.md、scripts/ 一支腳本）。
`home/skills/sdd-export/` 會被部署工具自動納入，不需要修改 `tools/deploy.py`。腳本不載入其他 skill 的程式
（機密樣式與 005 相同，但複製一份，不跨 skill 載入）。CI 維持 `test`、`cross-platform-produce`、`cross-platform` 三個 job，不新增。

## 養分與世代紀錄的摘要

完整定義見 [data-model.md](./data-model.md)，這裡只列 007 需要知道的重點。

- **養分**：舊專案的 `.sdd-export/nutrients.json`，`"tool": "sdd-export"`、`schema` 1。頂層有 `generation`、`project`、`exported_at`、
  `language`（`zh-Hant`）、`scope`、`principles`、`features`（依相依順序，各含 `requirements`）、`lessons`、`discarded`。
  每個項目有跨世代不變的 `id`、首次出現的世代 `origin`、修改過的世代 `revised`、合併或拆分的來源 `derived_from`；
  原則、需求、教訓另有 `status`（`confirmed`／`pending`）與 `evidence`。字串內容為繁體中文。
- **世代紀錄**（**007 要實作寫入的契約**）：新專案的 `.sdd-rebuild/lineage.json`，`"tool": "sdd-rebuild"`、`schema` 1、
  `generation` = 來源養分的 `generation` + 1。內容是重建時確認的項目，結構同養分但沒有 `status` 與 `evidence`，功能多一個 `spec_dir`；
  007 依 data-model 的「007 寫入時 MUST 遵守的規則」處理保留、修改、合併、拆分、新增與捨棄。MUST 入庫。
- **世代編號**：專案有世代紀錄時是它的 `generation`，沒有時是 1；同一個專案再次匯出世代不變。由 `check` 計算。
- **讀取者的版本規則**：`schema` 大於自己認得的版本時停止並說明需要更新 skill，不猜測內容。

## SKILL.md 與腳本的分工摘要

詳表見 [research.md](./research.md) 的 R1。

- **只能寫在 SKILL.md**：讀取 spec、文件、設定、測試與程式碼並導出功能與需求、判斷需求是否描述實作、辨認疑點與矛盾、
  整理與分類教訓、翻譯、依區段呈現草稿、逐項詢問、最終確認、選擇範圍的詢問、結束報告、何時呼叫 `write`。
- **由腳本決定性完成**：專用目錄的歸屬與衝突、既有養分與世代紀錄的讀取與驗證、世代編號、手動編輯的偵測、
  可讀檔案的清單與排除規則、過大的判定、機密檔案的辨認與可讀檔案中機密值的定位、草稿的結構驗證與世代規則、
  「`confirmed` 必須有存在的依據」、差異、序列化、原子寫入與 `--expect`。
- **兩邊都做**：機密（指示 + 攔截）、不含程式碼（指示 + 拒絕程式碼區塊與多餘欄位）、只讀（允許清單 + 腳本的只讀指令）、
  確認前不寫入（Claude 的時機 + 只有 `write` 會寫入）。

## 需要維護者注意的取捨

核可 plan 時請特別確認以下幾點；每一點在 [research.md](./research.md) 都有替代方案。

1. **專用目錄是頂層的 `.sdd-export/`，世代紀錄是頂層的 `.sdd-rebuild/lineage.json`**（R2、R3）。兩個都不在 `.specify/` 內，
   名稱表明歸屬。代價是重建後的專案根目錄會多一個點開頭的目錄；007 的 plan 必須照這個位置與格式寫入。
2. **養分是單一 JSON 檔加上一份產生的 `README.md`**（R2）。JSON 是唯一的資料來源，維護者要手動修改時改 JSON；
   `README.md` 被手動修改時，下一次寫入前會先詢問，但終究會被重新產生。不採用「每個功能一個檔案」，換取原子寫入與單一的解析入口。
3. **養分的字串內容一律繁體中文**（R2）。舊專案的 spec 是英文時，翻譯在匯出時由 Claude 完成、由維護者確認草稿時一併確認。
4. **沒有進度檔**（R7）。維持 spec 的「中途結束不寫入任何內容」，大型專案以縮小範圍與分批匯出（每次確認並寫入都是檢查點）
   處理；單一批次在確認前中斷，該批次的討論會遺失。若希望比照 005 保存進度，需要先修改 spec 的 Edge Cases 與 FR-010。
5. **世代規則由腳本強制**（R3、data-model「世代規則」）。前代的項目不能無聲消失，必須保留、被合併或明確捨棄；
   這讓 SC-006 可以自動驗證，但也代表 007 寫世代紀錄時必須嚴格遵守 data-model 的規則，否則下一次匯出會被拒絕。
6. **`disable-model-invocation: true`**（R9）。只能由維護者以 `/sdd-export` 啟動；007 的 US4（舊專案沒有養分時先匯出）
   因此不能以 Skill 工具呼叫本 skill，要改用腳本（`--project`，R11）加上 SKILL.md 的規則，由 007 的 plan 決定。
7. **不 commit**（R13）。spec 寫明提交由維護者決定，FR-011 也禁止修改專用目錄以外的檔案（含 `.git/`）。這與全域 CLAUDE.md
   「每完成一項異動就 commit」不同；結束報告會提醒養分可以提交。
8. **讀取範圍的門檻與排除清單是固定常數**（R5、data-model「讀取範圍」）：1500 個檔案、10 MiB、單檔 1 MiB、兩個以上帶套件描述檔的區塊。
   `.env.example` 這類範例檔一律不開啟。`out/`、`bin/` 這類名稱在少數專案是原始碼，會被誤排除；維護者可以用範圍參數指定，
   但被固定排除的目錄仍不會列入（如需調整，改常數）。
9. **FR-019 不新增 cross-platform job**（R8），以兩個平台的單元測試比對同一份固定位元組驗證。
10. **機密攔截是保守的樣式比對**（R6），無法涵蓋所有機密；Claude 讀取可讀檔案時一定會看到其中的值，只能靠指示不引用。
11. **自動測試不證明對話行為**（R8）。FR-004、FR-005 的導出品質、FR-007 的疑點判斷、FR-009 的教訓整理等，只由人工驗收確認；
    CI 只證明腳本的行為與對應的指示存在於 SKILL.md。

## Complexity Tracking

沒有需要說明的違反。
