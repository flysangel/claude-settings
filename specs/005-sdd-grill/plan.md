# Implementation Plan: sdd-grill 依需求追問出 constitution 與 spec

**Branch**: `005-sdd-grill` | **Date**: 2026-11-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-sdd-grill/spec.md`

## Summary

維護者輸入 `/sdd-grill` 加一段需求描述（或 Claude 在方向未定時主動使用），Claude 依需求與專案現有內容找出未決事項，
一次一題、附建議地追問：先 constitution 的原則，再功能清單與相依，再逐一功能。每個決定之後保存進度；
全部有結論後呈現決策摘要，維護者確認才透過 `speckit-constitution` 與 `speckit-specify` 依相依順序產生文件，
最後列出每份 spec 並說明下一步是 `/sdd-drive`，然後停止。

做法：與 003、004 不同，這是**對話式的 skill**。提問、追問、指出矛盾、整理摘要、呼叫 Spec Kit 都寫在 SKILL.md 由 Claude 執行；
可以決定性完成的事集中在一支由 uv 執行的 Python 腳本 `sdd_grill.py`：前置檢查與專案現況（`check`）、
進度的驗證與寫入（`save`）、檢查產生的文件是否符合確認的摘要與順序（`verify`）、清除進度（`clear`）。
進度存在 `.specify/sdd-grill/progress.json`，同一資料夾內一份忽略自己的 `.gitignore` 讓它不入庫，
不修改 Spec Kit 的 `.specify/.gitignore`。分工、決定與理由見 [research.md](./research.md)。

## Technical Context

**Language/Version**: Python 3.11+（由 uv 依腳本內的 inline metadata 自動提供）；SKILL.md 與 README.md 為 Markdown

**Primary Dependencies**: 執行期只用 Python 標準函式庫；外部指令只有 `git`（只讀，可有可無）。
產生文件時由 Claude 以 Skill 工具呼叫目標專案內 Spec Kit 的 `speckit-constitution` 與 `speckit-specify`

**Storage**: 檔案。目標專案的 `.specify/sdd-grill/progress.json`（進度）與 `.specify/sdd-grill/.gitignore`（讓資料夾不入庫）

**Testing**: pytest，`uv run --with pytest pytest`；GitHub Actions 矩陣 `ubuntu-latest` 與 `windows-latest`。
腳本的單元測試與 skill 的結構／內容檢查都不需要網路；對話行為以 [quickstart.md](./quickstart.md) 的人工驗收在真實 session 驗證

**Target Platform**: Linux 與 Windows 上的 Claude Code

**Project Type**: Claude Code skill（一份 SKILL.md、一份 README、一支腳本）

**Performance Goals**: 腳本的每個指令在一般專案內於 1 秒內完成（只讀少數檔案與一次 `git rev-parse`）；對話本身沒有效能目標

**Constraints**:

- 維護者確認摘要之前，constitution 與 spec 零異動；腳本的寫入與刪除只發生在 `.specify/sdd-grill/`，唯一的例外是收尾時 `focus` 寫入 `.specify/feature.json`
- 不修改任何 Spec Kit 產生的檔案（包含 `.specify/.gitignore`）；`.specify/feature.json` 是 Spec Kit 的本機狀態，只由 `focus` 在產生完畢後改成這一批新 spec 中編號最小的一份（見 Constitution Check 原則 I）
- constitution 與 spec 只由 Spec Kit 的 skill 產生；不手寫、不自行指定編號
- 進度不入庫、不含機密值
- 不 push；不自動開始 plan、tasks 或實作
- 產出只有 skill 文件或 script；Python 一律用 uv 執行

**Scale/Scope**: 一次討論數個到十幾個功能、數十個決定；進度檔數十 KB 以內；單一使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 constitution v1.0.1 逐條檢查。

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | constitution 與 spec 由 Claude 以 Skill 工具呼叫 `speckit-constitution`、`speckit-specify` 產生；sdd-grill 不手寫、不自行指定編號。本功能在 `.specify/` 內新增自己的檔案：`.specify/sdd-grill/progress.json` 與 `.specify/sdd-grill/.gitignore`。依 v1.0.1「MUST 記錄哪些檔案是自己建立的」，以專用資料夾為紀錄：sdd-grill 只在這裡寫檔、這裡只有上述兩個檔案，`.gitignore` 的註解與 `progress.json` 的 `tool` 欄位標明來源，README 與 contracts 寫明這個約定（R2）。不修改 Spec Kit 產生的 `.specify/.gitignore`。**`.specify/feature.json`**：產生多份 spec 後，腳本 `focus` 把它的 `feature_directory` 指向這一批新 spec 中編號最小的一份。判斷：原則 I 禁止的是手寫或修改 Spec Kit 產出的內容，理由是不修改上游檔案才不會在更新 Spec Kit 時衝突或遺失修改；`feature.json` 是 Spec Kit 記錄「目前處理哪個功能」的本機狀態，Spec Kit 自己的 `.specify/.gitignore` 列為不入庫，`speckit-specify` 與 `common.sh` 每次切換功能都改寫它，切換功能的方式就是改這個值。`focus` 寫的內容與格式與 Spec Kit 相同，是使用它提供的切換機制，不是修改它的產出，也不會造成更新衝突；範圍僅限這個檔案的這個鍵（R4）。原則 I 的條文沒有為狀態檔另列例外，此為本計畫的判斷，列入下方取捨第 4 點請維護者核可。 |
| II. Windows 與 Linux 完全對等 | 通過 | 兩個平台執行同一支腳本與同一份 SKILL.md；雜湊先正規化換行，輸出的路徑以 `/` 分隔、順序固定。腳本的單元測試與 skill 的結構檢查在既有 `test` job 的兩個平台執行。進度不入庫、不在平台間交換，所以不需要新的跨平台 job。對話行為無法在 CI 驗證（R3），以人工驗收補足，核心情境在兩個平台各做一次。 |
| III. 保護既有檔案 | 通過 | 腳本只寫、只刪 `.specify/sdd-grill/` 內自己的兩個檔案（`focus` 另外只改寫不入庫的 `.specify/feature.json`，而且只在 `verify` 的全部檢查通過後，所以不會指向不存在的目錄）；資料夾內有其他檔案或 `.gitignore` 不是自己寫的時視為衝突，停止並回報。既有 spec 由 Spec Kit 依序編號而不會被覆蓋，`verify` 以確認時記下的基準證明它們沒有被動到；constitution 只在維護者同意修訂時更動。產生失敗時不刪除已產生的文件。`check`、`verify` 只讀，重複執行結果相同；`save` 以相同輸入重複執行得到相同內容（`saved_at` 除外），`clear` 重複執行為零異動。 |
| IV. 先確認再寫入 | 通過 | 這是本功能的核心：確認摘要前不寫入 constitution 與 spec（FR-012），確認後才產生；產生的內容逐條比對摘要，多出的規則移除或先問維護者（FR-014），spec 中沒有依據的內容移除或標為待確認。進度檔是 spec 明訂的例外。 |
| V. 個人使用、repo 公開 | 通過 | 沒有可調選項。進度只在目標專案本機、不入庫；腳本攔截常見的機密樣式（R8），SKILL.md 指示不記錄機密。skill 的檔案不含絕對路徑與信箱（結構測試檢查）。 |
| VI. 文件語言 | 通過 | SKILL.md 與腳本訊息為英文；skill 資料夾有繁體中文 README；本功能的 plan 文件為繁體中文，規範詞保留英文。產生的 constitution 與 spec 依 FR-020 使用專案既有文件的語言，無法判斷時繁體中文。 |

Phase 1 設計後重新檢查（2026-11-20）：結果相同。設計階段確定的幾點都已涵蓋在上表：
自我忽略的資料夾（原則 I、V）、`verify` 以基準證明既有文件未被動到（原則 III）、`save` 只在 `phase` 改為 `confirmed` 時記下基準，
產生途中不能改回討論（原則 IV）。沒有需要記錄在 Complexity Tracking 的違反。

## Project Structure

### Documentation (this feature)

```text
specs/005-sdd-grill/
├── plan.md              # 本檔
├── research.md          # Phase 0：分工、進度保存、測試範圍、產生文件的做法、frontmatter、與 007 的關係
├── data-model.md        # Phase 1：自己的資料夾、進度、指紋、基準、驗證規則與狀態轉移
├── quickstart.md        # Phase 1：自動測試、腳本手動情境與人工驗收情境
├── contracts/
│   ├── cli.md           # sdd_grill.py 的指令、結束碼與 JSON 輸出
│   └── skill.md         # skill 資料夾的結構與 SKILL.md 的必要指示
├── checklists/
│   └── requirements.md  # 由 /speckit-specify 產生
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
home/skills/sdd-grill/               # 本功能的產出，部署後位於 ~/.claude/skills/sdd-grill/
├── SKILL.md                         # 英文；對話的進行方式與何時呼叫腳本
├── README.md                        # 繁體中文簡述
└── scripts/
    └── sdd_grill.py                 # check、save、verify、clear

tests/
├── unit/
│   ├── test_sdd_grill.py            # 腳本：在暫存目錄以真實的檔案與 git 測試，不需要網路
│   └── test_sdd_grill_skill.py      # skill 資料夾的結構與 SKILL.md 的必要指示
└── conftest.py                      # 新增載入 sdd_grill.py 的 fixture

.github/workflows/ci.yml             # 不變；既有 test job 會執行新的測試
```

**Structure Decision**: 沿用 003、004 的 skill 結構（SKILL.md、README.md、scripts/ 一支腳本）。
`home/skills/sdd-grill/` 會被部署工具自動納入，不需要修改 `tools/deploy.py`。腳本不載入其他 skill 的程式。
CI 維持 `test`、`cross-platform-produce`、`cross-platform` 三個 job，不新增。

## SKILL.md 與腳本的分工摘要

詳表見 [research.md](./research.md) 的 R1。

- **只能寫在 SKILL.md**：讀取專案並推導問題、一次一題附建議、追問含糊的回答、指出矛盾與原則衝突、辨認技術選型、
  決定何時保存、呈現摘要與確認、呼叫 `speckit-constitution` 與 `speckit-specify`、比對產生的內容與摘要、決定文件語言、
  結束報告與停止。
- **由腳本決定性完成**：Spec Kit 是否可用與缺少什麼、這一批 spec 中編號最小的一份與 `.specify/feature.json` 的寫入（`focus`）、constitution 是否仍是空白範本、既有 spec 與編號方式、
  進度的位置、結構驗證、原子寫入與不入庫、機密樣式攔截、專案變更偵測、確認時的基準、產生結果的順序與不覆蓋檢查、
  清除的範圍。
- **兩邊都做**：機密（指示 + 攔截）、順序與不覆蓋（Claude 依序呼叫 + `verify` 檢查）、清除時機（Claude 決定 + `verify` 把關）。

## 需要維護者注意的取捨

核可 plan 時請特別確認以下幾點；每一點在 [research.md](./research.md) 都有替代方案。

1. **進度放在 `.specify/sdd-grill/`，以資料夾內自己的 `.gitignore` 不入庫，且不登記在 sdd-init 的導入紀錄**（R2）。
   原則 I 的「記錄自己建立的檔案」以專用資料夾與標記達成，與 004 把比對副本登記在紀錄的做法不同。
   若希望一律登記在 `.specify/sdd-init.json`，sdd-grill 會依賴 sdd-init 的紀錄格式，且入庫的紀錄會指向不入庫的檔案。
2. **本 repo 自己的 `.specify/.gitignore` 有一行 `sdd-grill-progress.md`**（以及 `sdd-drive-state.json`），是 v1.0.1 之前手動加的；
   本設計不使用這個檔名，也不處理那一行。是否移除由維護者決定，不在本功能範圍。
3. **「專案有變更」只看 constitution、每份 spec.md 與 git 的 HEAD**（R2）。未 commit 的程式碼變更不會被提示。
4. **產生多份 spec 後，sdd-grill 把 `.specify/feature.json` 指向這一批新 spec 中編號最小的一份**（R4，維護者決定），
   由腳本新增的第五個指令 `focus` 在 `verify` 通過後寫入，結束報告會告訴維護者它指向哪一份。這樣維護者跳過 `/sdd-drive`、
   直接用原生的 `/speckit-plan` 時會依施工順序從第一份開始。代價是 sdd-grill 會寫入一個 Spec Kit 的檔案：
   我們判斷它是不入庫的本機狀態、改寫它就是 Spec Kit 的切換機制，因此不違反原則 I，但原則 I 的條文沒有明寫這類例外，
   請核可時一併確認；腳本「只寫 `.specify/sdd-grill/`」的保證也因此改為「除 `focus` 之外」。
5. **spec 中沒有依據的內容**：`speckit-specify` 會補上合理的推斷（例如 Success Criteria）。constitution 依 FR-014 移除多出的規則；
   spec 則是「移除或標為待確認」（原則 IV），不是一律移除，因為範本的必要段落需要填寫。
6. **確認後 `speckit-specify` 若要求澄清而摘要沒有答案**，Claude 會再問一題並把答案補進進度，視為對已確認摘要的修訂，不重新確認整份摘要（R4）。
7. **commit**：SKILL.md 不要求也不禁止 commit 產生的文件，由維護者的全域設定（`home/CLAUDE.md`：每完成一項異動就 commit、
   不直接 commit 到 `main`）決定；只禁止 push。這與 sdd-update 明確禁止 commit 不同。
8. **機密攔截是保守的樣式比對**（R8），無法涵蓋所有機密；產生的 constitution 與 spec 不經過腳本，只能靠指示與摘要確認把關。
9. **自動測試不證明對話行為**（R3）。FR-002 至 FR-008、FR-011、FR-014、FR-017、FR-020 的實際行為只由人工驗收確認；
   CI 只證明對應的指示存在於 SKILL.md。
10. **description 允許 Claude 主動使用**（R5），因此可能在不需要時被觸發；確認摘要前不寫入任何文件，誤觸發的代價只是一段對話。

## Complexity Tracking

沒有需要說明的違反。
