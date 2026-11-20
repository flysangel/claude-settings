# Implementation Plan: sdd-init 導入 Spec Kit

**Branch**: `003-sdd-init` | **Date**: 2026-11-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-sdd-init/spec.md`

## Summary

維護者輸入 `/sdd-init` 就在目前專案導入當下最新穩定版的 Spec Kit，不覆蓋既有檔案；`/sdd-init remove` 可移除，
只刪除自己建立且未被修改的檔案。任一平台導入並提交的專案，在另一個平台不需重新導入就能執行 Spec Kit 流程。

做法：skill 是一份很薄的 SKILL.md，所有判斷集中在一支由 uv 執行的 Python 腳本 `sdd_init.py`，
兩個平台跑同一份邏輯。腳本向 PyPI 查出最新穩定版，以 `uv tool run` 在專案之外的暫存目錄執行官方的
`specify init --integration claude --script sh`，再把產出逐檔原樣複製到專案中還不存在的位置，
並把建立的檔案與內容雜湊寫進導入紀錄 `.specify/sdd-init.json`。

兩個平台一律使用 `sh` 腳本，Windows 由 Git Bash 執行。實測這個做法有兩個跨平台缺口（換行被轉成 CRLF、
Windows 無法記錄執行權限），所以 sdd-init 另外新增一行規則的 `.specify/.gitattributes`，
並在專案是 git repository 時以 `git add --chmod=+x` 把自己建立的 `.sh` 加入暫存區。依據與實測結果見 [research.md](./research.md)。

## Technical Context

**Language/Version**: Python 3.11+（由 uv 依腳本內的 inline metadata 自動提供）；SKILL.md 與 README.md 為 Markdown

**Primary Dependencies**: 執行期只用 Python 標準函式庫；外部指令為 `uv`、`git`、`bash`；
官方工具是 PyPI 的 `specify-cli`，以 `uv tool run --from specify-cli==<版本>` 執行，不安裝到使用者環境

**Storage**: 檔案。導入紀錄在目標專案的 `.specify/sdd-init.json`

**Testing**: pytest，`uv run --with pytest pytest`；GitHub Actions 矩陣 `ubuntu-latest` 與 `windows-latest`。
單元測試不需要網路；整合與跨平台測試實際執行官方工具，需要網路（標記 `network`）

**Target Platform**: Linux 與 Windows 上的 Claude Code。**Windows 的前置需求是 Git Bash**，它隨 Git for Windows 安裝，
而 `git` 已是 001 部署工具的必要指令，所以不需要額外安裝

**Project Type**: Claude Code skill（一份 SKILL.md、一份 README、一支腳本）

**Performance Goals**: 一個指令完成導入，不超過 2 分鐘（SC-001）

**Constraints**:

- 不覆蓋、不修改任何既有檔案；失敗時零寫入；重複執行零異動
- Spec Kit 的檔案只由官方工具產生，sdd-init 只原樣複製
- **會動到暫存區**：專案是 git repository 時，把自己建立的 `.sh` 以 `git add --chmod=+x` 加入 index，不 commit；
  移除時把其中仍未 commit 的項目從 index 取消。除此之外不執行任何會改變 repository 的 git 指令
- 導入需要網路（查詢版本、下載官方工具）；已完整導入時再次執行不連線
- 紀錄不含絕對路徑、時間戳與個人資訊
- 產出只有 skill 文件或 script；Python 一律用 uv 執行

**Scale/Scope**: 每次導入約 30 個檔案加 2 個 sdd-init 自己的檔案；單一使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | Spec Kit 的檔案全部由官方工具 `specify init` 產生，sdd-init 只把產出原樣複製，不手寫、不修改其內容；`git add --chmod=+x` 只在 index 記錄執行權限，不改檔案內容。sdd-init 在 `.specify/` 內新增兩個**自己的**檔案（`.specify/sdd-init.json`、`.specify/.gitattributes`），兩者都不是 Spec Kit 產生的檔案。**這是維護者於 2026-11-20 確認的解讀**：原則 I 指「不手寫、不修改 Spec Kit 產生的檔案」，不禁止 sdd-init 在 `.specify/` 內放自己的檔案。本計畫不修改 constitution。 |
| II. Windows 與 Linux 完全對等 | 通過 | 邏輯集中在同一支 Python 腳本；兩個平台用同一種腳本（`sh`）、產生相同的檔案集合與相同的輸出。單元、整合測試在兩個平台的 CI 執行，另有跨平台 job 讓兩個平台互相 clone 對方導入的 repository 並執行 Spec Kit 腳本。 |
| III. 保護既有檔案 | 通過 | 目標已存在就略過並列出，包含已存在且不是自己建立的 `.specify/.gitattributes`（不覆蓋，改以警告說明要補的規則）。移除只刪除紀錄內且雜湊未變的檔案。先在專案外產生、規劃完才寫入；重複執行零異動。本功能沒有「取代」的選項，所以沒有需要備份的情況。 |
| IV. 先確認再寫入 | 不適用 | sdd-init 不產生或改寫 constitution、spec 的內容；`.specify/memory/constitution.md` 是官方工具複製的空白範本，且已存在時不會被碰。 |
| V. 個人使用、repo 公開 | 通過 | 只有導入與移除兩種用法，選項固定為 `claude` 與 `sh`，不提供可調選項。紀錄只存相對路徑、雜湊與版本。 |
| VI. 文件語言 | 通過 | SKILL.md 與腳本內的訊息為英文；skill 資料夾有繁體中文的 README；spec 與 plan 文件為繁體中文。結構測試檢查這幾點。 |

Phase 1 設計後重新檢查：結果相同，沒有需要記錄在 Complexity Tracking 的違反。

## Project Structure

### Documentation (this feature)

```text
specs/003-sdd-init/
├── plan.md              # 本檔
├── research.md          # Phase 0：決定、理由、替代方案與實測紀錄
├── data-model.md        # Phase 1：導入紀錄與判定規則
├── quickstart.md        # Phase 1：驗證情境
├── contracts/
│   ├── cli.md           # sdd_init.py 的指令、結束碼與輸出
│   └── skill.md         # skill 資料夾的結構
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
home/skills/sdd-init/            # 本功能的產出，部署後位於 ~/.claude/skills/sdd-init/
├── SKILL.md                     # 英文；指示 Claude 執行腳本並回報
├── README.md                    # 繁體中文簡述
└── scripts/
    └── sdd_init.py              # 導入與移除的全部邏輯（uv run，標準函式庫）

tests/
├── unit/
│   ├── test_sdd_init.py         # 以假的官方產出測試全部判斷邏輯，不需要網路
│   └── test_sdd_init_skill.py   # skill 資料夾的結構
├── integration/
│   └── test_sdd_init_real.py    # 實際查詢 PyPI 並執行官方工具（標記 network）
├── e2e/
│   └── test_cross_platform.py   # 只在 CI 的 cross-platform job 執行
└── conftest.py                  # 新增載入 sdd_init.py 的 fixture 與 network 標記

.github/workflows/ci.yml         # 既有的 test job 之外，新增 cross-platform job
```

**Structure Decision**: 沿用 001 建立的結構。`home/skills/sdd-init/` 會被部署工具自動納入，不需要修改 `tools/deploy.py`。
CI 新增的 `cross-platform` job 分兩步：每個平台導入一個新的 repository
並以 `git bundle` 上傳，再由每個平台下載另一個平台的 bundle、clone 並執行 Spec Kit 腳本。

## Complexity Tracking

沒有需要說明的違反。
