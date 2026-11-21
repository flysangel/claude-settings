# Implementation Plan: sdd-update 更新 Spec Kit

**Branch**: `004-sdd-update` | **Date**: 2026-11-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-sdd-update/spec.md`

## Summary

維護者輸入 `/sdd-update`，就把由 sdd-init 導入的專案更新到當下最新穩定版的 Spec Kit：內容未被修改的檔案換成新版，
新版新增的檔案被建立，新版不再提供且未被修改的檔案被移除；被修改過的檔案保留不動，並附上新版內容供比對。
constitution 與 `specs/` 永遠不動。更新後的專案在 Windows 與 Linux 都不需要重新導入。

做法：與 003 相同，skill 是一份很薄的 SKILL.md，判斷集中在一支由 uv 執行的 Python 腳本 `sdd_update.py`。
腳本讀取 003 的導入紀錄 `.specify/sdd-init.json`，向 PyPI 查出最新穩定版，在專案之外的暫存目錄以該版本執行官方的
`specify init --integration claude --script sh`，再以「紀錄內的雜湊、專案檔案目前的雜湊、新版內容的雜湊」逐檔判定
要取代、建立、刪除還是保留。被保留的檔案的新版內容寫到 `.specify/sdd-update/<原路徑>.new`（比對副本），
是否入庫由維護者決定。完成後把紀錄改寫為新版本與新版內容的雜湊。

共用的程式不另起一套：`sdd_update.py` 在執行時從相鄰的 skill 資料夾載入 `sdd_init.py`，使用它的紀錄讀寫、雜湊、
版本挑選、官方工具的執行、必要工具的判定與 `.sh` 的暫存區處理。決定、理由與實測結果見 [research.md](./research.md)。

## Technical Context

**Language/Version**: Python 3.11+（由 uv 依腳本內的 inline metadata 自動提供）；SKILL.md 與 README.md 為 Markdown

**Primary Dependencies**: 執行期只用 Python 標準函式庫，加上相鄰 skill 的 `sdd_init.py`（003 的產出）；
外部指令為 `uv`、`git`、`bash`；官方工具是 PyPI 的 `specify-cli`，以 `uv tool run --from specify-cli==<版本>` 執行

**Storage**: 檔案。導入紀錄在目標專案的 `.specify/sdd-init.json`（沿用 003，`schema` 仍為 1）；
比對副本在目標專案的 `.specify/sdd-update/`

**Testing**: pytest，`uv run --with pytest pytest`；GitHub Actions 矩陣 `ubuntu-latest` 與 `windows-latest`。
單元測試不需要網路；整合與跨平台測試實際執行兩個版本的官方工具，需要網路（標記 `network`，失敗就算失敗）

**Target Platform**: Linux 與 Windows 上的 Claude Code；Windows 的前置需求與 003 相同（Git Bash）

**Project Type**: Claude Code skill（一份 SKILL.md、一份 README、一支腳本）

**Performance Goals**: 一個指令完成更新，不超過 2 分鐘（SC-001）；實測查詢版本加執行官方工具在數秒內完成

**Constraints**:

- 只取代、刪除紀錄內且內容未被修改的 Spec Kit 檔案；其餘檔案不寫入、不刪除
- `.specify/memory/`（constitution）與 `specs/` 不讀寫
- 新版的檔案只由官方工具產生，sdd-update 只原樣複製
- 已是最新穩定版、專案比最新穩定版還新、以及所有停止的情況：專案內零異動（包含不清理比對副本）
- 取得版本、執行官方工具與規劃都在第一次寫入之前；中途失敗後再次執行會收斂到一致的狀態
- 對暫存區的異動沿用 003 的範圍：只以 `git add --chmod=+x` 加入新建與待補登的 `.sh`，不改寫既有的 index 項目，不 commit
- 結束碼沿用 003（0、1、3、4），不新增
- 不提供指定版本或降版；沒有參數
- 產出只有 skill 文件或 script；Python 一律用 uv 執行

**Scale/Scope**: 每次更新處理約 30 個檔案（實測每一版至少有十幾個檔案內容不同）；單一使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 constitution v1.0.1 逐條檢查。

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | 新版的 Spec Kit 檔案全部由官方工具 `specify init` 在暫存目錄產生，sdd-update 只把位元組原樣複製到專案（取代或建立）或刪除新版不再提供的檔案，不手寫、不修改其內容；`git add --chmod=+x` 只在 index 記錄檔案模式。本功能在 `.specify/` 內新增自己的檔案：`.specify/sdd-update/` 下的比對副本。它們不是 Spec Kit 在該處產生的檔案；依 v1.0.1「MUST 記錄哪些檔案是自己建立的」，每一份都列入導入紀錄，`origin` 為 `sdd-update`，並集中在專用目錄，與 Spec Kit 的檔案分得清楚。 |
| II. Windows 與 Linux 完全對等 | 通過 | 兩個平台執行同一支腳本，雜湊先正規化換行，輸出的路徑與順序固定。單元與整合測試在兩個平台的 CI 執行；既有的跨平台 job 擴充為讓兩個平台互相 clone 對方**更新後**的 repository 並執行 Spec Kit 腳本，同時比對兩邊的檔案清單與模式。 |
| III. 保護既有檔案 | 通過 | 被取代與被刪除的只有「在紀錄內（由本專案工具建立）且雜湊等於紀錄（未被修改）」的檔案；被修改過的與不在紀錄內的一律保留。比對副本的路徑上有不在紀錄內的檔案時是衝突，規劃階段就停止並回報，不覆蓋。會被本功能無條件刪除的只有紀錄內的比對副本，它們是本工具自己建立的。沒有「取代」的選項，所以沒有需要備份的情況。已是最新版時重複執行零異動；中途失敗後重複執行收斂到相同結果。 |
| IV. 先確認再寫入 | 不適用 | sdd-update 不產生或改寫 constitution、spec 的內容；`.specify/memory/` 與 `specs/` 完全不在寫入範圍內。 |
| V. 個人使用、repo 公開 | 通過 | 沒有任何可調選項（不能指定版本、不能降版）。紀錄與比對副本只含相對路徑、雜湊、版本與官方工具的內容，沒有絕對路徑、時間戳以外的機器資訊或個人資料（官方檔案內的時間戳由官方工具產生，原樣複製）。 |
| VI. 文件語言 | 通過 | SKILL.md 與腳本內的訊息為英文；skill 資料夾有繁體中文的 README；spec 與 plan 文件為繁體中文，MUST、SHOULD 保留英文。結構測試檢查這幾點。 |

Phase 1 設計後重新檢查（2026-11-20）：結果相同。設計階段新增的兩件事都已涵蓋在上表：
比對副本列入紀錄並以 `origin: sdd-update` 區分（原則 I）；紀錄內的比對副本在下一次更新時不論內容一律刪除，
因為它們是本工具自己建立的檔案（原則 III）。沒有需要記錄在 Complexity Tracking 的違反。

## Project Structure

### Documentation (this feature)

```text
specs/004-sdd-update/
├── plan.md              # 本檔
├── research.md          # Phase 0：決定、理由、替代方案與實測紀錄
├── data-model.md        # Phase 1：紀錄的變更、比對副本、逐檔判定與狀態轉移
├── quickstart.md        # Phase 1：驗證情境
├── contracts/
│   ├── cli.md           # sdd_update.py 的指令、結束碼與輸出
│   └── skill.md         # skill 資料夾的結構，以及對 sdd-init 的變更範圍
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
home/skills/sdd-update/              # 本功能的產出，部署後位於 ~/.claude/skills/sdd-update/
├── SKILL.md                         # 英文；指示 Claude 執行腳本並回報
├── README.md                        # 繁體中文簡述
└── scripts/
    └── sdd_update.py                # 更新的判斷邏輯；執行時載入相鄰的 sdd_init.py

home/skills/sdd-init/scripts/
└── sdd_init.py                      # 003 的產出；為共用做三項小變更（research.md 的 R6）

tests/
├── unit/
│   ├── test_sdd_update.py           # 以兩個假版本的假產出測試全部判斷邏輯，不需要網路
│   ├── test_sdd_update_skill.py     # skill 資料夾的結構
│   └── test_sdd_init.py             # 既有；增補共用變更的測試
├── integration/
│   └── test_sdd_update_real.py      # 以 1.2.6 導入後實際更新到最新穩定版（標記 network）
├── e2e/
│   └── test_cross_platform_update.py  # 只在 CI 的跨平台 job 執行
└── conftest.py                      # 新增載入 sdd_update.py 的 fixture 與「以指定版本導入」的輔助函式

.github/workflows/ci.yml             # 兩個既有的跨平台 job 多執行一個測試檔；不新增 job
```

**Structure Decision**: 沿用 001 與 003 的結構。`home/skills/sdd-update/` 會被部署工具自動納入，不需要修改 `tools/deploy.py`。
兩個 skill 之間的共用以「執行時載入相鄰資料夾的 `sdd_init.py`」達成：部署工具一次安裝整個 `home/`，
所以兩個資料夾在 repo 與安裝後都相鄰。CI 維持 `test`、`cross-platform-produce`、`cross-platform` 三個 job。

## 需要維護者注意的取捨

核可 plan 時請特別確認以下幾點；每一點在 [research.md](./research.md) 都有替代方案。

1. **已是最新版時不清理比對副本**（R1）。為了符合 FR-008 的字面（不產生任何檔案異動），維護者合併之後再執行
   `/sdd-update`，只會不再列出該檔案，比對副本要等下一次實際更新或由維護者自行刪除。
   若希望合併後再執行時就自動清掉，需要放寬 FR-008。
2. **比對副本不自動入庫、也不自動忽略**（R1）。它們會出現在 `git status` 的未追蹤檔案中，由維護者決定提交或刪除。
3. **sdd-update 在執行時依賴 sdd-init 的腳本**（R6），並且要修改 `sdd_init.py` 三處：紀錄多接受 `origin: sdd-update`、
   「已完整導入」不要求比對副本存在、把兩段程式整理成可呼叫的函式。`schema` 維持 1；
   只部署了舊版 sdd-init 的機器讀到含比對副本的紀錄時會拒絕使用（結束碼 1，不寫入），與遇到不認得的 `schema` 相同。
   003 的設計文件中 `origin` 的值與「已完整導入」的條件要在實作時一併更新。
4. **`.specify/memory/` 整個目錄不動**（R7），包含 constitution 仍是空白範本的情況，以及同目錄的
   `.constitution-template.json`。新版若改了 constitution 的空白範本，專案不會跟著變。
5. **維護者刪掉的 Spec Kit 檔案會在更新時被重新建立**（R2 第 1 列），與 `/sdd-init` 的補齊行為一致。
6. **被修改、且新版不再提供的檔案會留下來並從紀錄移除**（R2 第 7 列），之後由維護者自行處理；
   例如改過的 `speckit-taskstoissues/SKILL.md` 更新後仍可被呼叫。
7. **沒有導入紀錄時以結束碼 1 停止**（R4），不是 0；「不是由 sdd-init 導入」的專案要先執行一次 `/sdd-init`
   取得紀錄（它會略過全部既有檔案），之後更新時這些檔案一律保留並附比對副本。
8. **「不是由 sdd-init 導入」的專案要等下一個穩定版才會被比對**（R2 的「限制」）。`/sdd-init` 在這種專案記下的版本是
   當下的最新穩定版，所以緊接著執行 `/sdd-update` 只會回報已是最新版，不會立刻列出那些既有檔案。
9. **整合與跨平台測試以固定的 1.2.6 為起點**（R5）。這個版本若被 PyPI 撤回，測試會失敗，需要換一個起點版本。
10. **更新中途失敗後、再次執行之前官方又發布新版**時，上一次已取代的檔案會被當成被修改而保留（R4 的「已知的窄縫」）。
   結果安全，但會多出需要人工比對的檔案。

## Complexity Tracking

沒有需要說明的違反。
