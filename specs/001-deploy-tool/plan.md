# Implementation Plan: 部署工具

**Branch**: `001-deploy-tool` | **Date**: 2026-11-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-deploy-tool/spec.md`

## Summary

以一行指令把 repo 的 `home/`（全域 CLAUDE.md 與 6 個 SDD skill）安裝到 `~/.claude`，可更新與移除，
且未經明確要求不覆蓋任何不是自己安裝的檔案。

做法分兩層：每個平台一支很薄的開機腳本（`tools/setup.sh`、`tools/setup.ps1`）只負責檢查必要指令、
取得 repo、呼叫部署程式；所有判斷邏輯集中在一支跨平台的 Python 程式 `tools/deploy.py`，由 uv 執行。
兩個平台共用同一份邏輯，行為對等由同一套測試在兩個平台的 CI 驗證。部署程式先完整計算要做的事，
有任何衝突就整批不寫入；以安裝紀錄（manifest）裡的內容雜湊分辨「自己安裝的」「被手動改過的」與「別人的」檔案。

## Technical Context

**Language/Version**: Python 3.11+（由 uv 依腳本內的 inline metadata 自動提供）；開機腳本為 POSIX sh 與 PowerShell 5.1+

**Primary Dependencies**: 執行期只用 Python 標準函式庫；外部指令為 `git` 與 `uv`

**Storage**: 檔案。安裝紀錄與備份放在 `~/.claude/.claude-settings/`

**Testing**: pytest，以 `uv run --with pytest pytest` 執行；GitHub Actions 矩陣 `ubuntu-latest` 與 `windows-latest`

**Target Platform**: Linux 與 Windows；macOS 不在支援範圍

**Project Type**: CLI 工具（單一腳本加兩支開機腳本）

**Performance Goals**: 具備必要指令的新機器上，從貼上指令到完成不超過 2 分鐘（SC-001）

**Constraints**: 衝突時零寫入；重複執行零異動；紀錄不含絕對路徑與個人資訊；產出只有 skill 文件或 script，Python 一律用 uv 執行

**Scale/Scope**: 約數十個檔案（1 份 CLAUDE.md 與 6 個 skill 資料夾）；單一使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | 本功能不接觸 `.specify/` 與 `speckit-*`；只部署 `home/` 下的內容。 |
| II. Windows 與 Linux 完全對等 | 通過 | 邏輯集中在同一支 Python 程式；開機腳本只做相同的三件事。單元與 E2E 測試在兩個平台的 CI 都要通過才能合併。 |
| III. 保護既有檔案 | 通過 | 先規劃後執行；任何衝突或手動修改都整批不寫入；`--replace` 才覆蓋且先備份；無變更時零異動。 |
| IV. 先確認再寫入 | 不適用 | 本功能不產生或改寫 constitution、spec。 |
| V. 個人使用、repo 公開 | 通過 | 只有安裝、`--replace`、`remove` 三種用法；manifest 只存相對路徑與雜湊。 |
| VI. 文件語言 | 通過 | 本功能不是 skill；spec 與 plan 文件為繁體中文。程式內的訊息與註解用英文。 |

Phase 1 設計後重新檢查：結果相同，沒有需要記錄在 Complexity Tracking 的違反。

## Project Structure

### Documentation (this feature)

```text
specs/001-deploy-tool/
├── plan.md              # 本檔
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── cli.md           # 指令、結束碼與輸出的約定
└── tasks.md             # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
home/                        # 會被部署到 ~/.claude 的內容（部署內容）
├── CLAUDE.md                # 由 002 提供
└── skills/                  # 由 003–008 提供
    └── sdd-*/

tools/
├── setup.sh                 # Linux 開機腳本：檢查指令、取得 repo、呼叫 deploy.py
├── setup.ps1                # Windows 開機腳本：同上
└── deploy.py                # 部署邏輯（uv run，標準函式庫）

tests/
├── unit/
│   └── test_deploy.py       # 規劃、衝突判定、備份、移除、冪等
├── e2e/
│   ├── test_setup_sh.py     # 只在 Linux 執行
│   └── test_setup_ps1.py    # 只在 Windows 執行
└── conftest.py              # 暫存家目錄與暫存 repo 的 fixture

.github/workflows/ci.yml     # ubuntu-latest 與 windows-latest 矩陣
.gitattributes               # * text=auto eol=lf，確保兩個平台的檔案內容相同
```

**Structure Decision**: 單一專案。`home/` 是唯一的部署來源，目錄結構與 `~/.claude` 下的目標一一對應，
新增 skill 不需要改部署程式。本功能建立 `tools/`、`tests/`、CI 與空的 `home/` 骨架；
`home/` 的實際內容由 002 至 008 填入，測試以 fixture 內容驗證。

## Complexity Tracking

沒有需要說明的違反。
