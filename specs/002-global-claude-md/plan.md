# Implementation Plan: 全域 CLAUDE.md

**Branch**: `002-global-claude-md` | **Date**: 2026-11-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-global-claude-md/spec.md`

## Summary

提供一份對所有專案生效的偏好文件 `home/CLAUDE.md`，由 001 部署工具安裝為 `~/.claude/CLAUDE.md`。
內容沿用維護者目前生效的溝通、Git、規格驅動開發三段，只把規格驅動開發一段改成本專案的 6 個 skill 與流程。

這個功能的產出是一份 Markdown 文件，沒有程式邏輯。自動測試驗證文件的結構：三段都存在、每條規則都附「預期」、
引用的 skill 名稱都在本專案的清單內、沒有個人資訊。Claude 是否實際遵守規則屬於對話行為，以 quickstart 的情境人工驗收。

## Technical Context

**Language/Version**: Markdown（文件本身）；測試為 Python 3.11+，由 uv 執行

**Primary Dependencies**: 無。測試只用 Python 標準函式庫與 pytest

**Storage**: 單一檔案 `home/CLAUDE.md`

**Testing**: pytest，`uv run --with pytest pytest`；沿用 001 建立的 CI 矩陣（`ubuntu-latest`、`windows-latest`）

**Target Platform**: Linux 與 Windows 上的 Claude Code

**Project Type**: 設定文件

**Performance Goals**: 不適用

**Constraints**: 文件每個 session 都會載入，內容要精簡；不含機密、機器專屬路徑與個人信箱；兩個平台安裝後位元組相同

**Scale/Scope**: 一份文件，三段，約十條規則

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | 文件只指引何時使用哪個 skill，不接觸 `.specify/` 與 `speckit-*`。 |
| II. Windows 與 Linux 完全對等 | 通過 | 同一份檔案，`.gitattributes` 保證兩邊位元組相同；結構測試在兩個平台的 CI 執行。 |
| III. 保護既有檔案 | 通過 | 安裝由 001 負責，既有的 `~/.claude/CLAUDE.md` 依 001 的衝突規則處理。 |
| IV. 先確認再寫入 | 不適用 | 本功能不是產生 constitution 或 spec 的 skill。文件中引導使用的 skill 各自遵守這條原則。 |
| V. 個人使用、repo 公開 | 通過 | 只寫維護者的偏好，沒有可調選項；測試檢查沒有信箱與絕對路徑。 |
| VI. 文件語言 | 通過 | CLAUDE.md 是偏好文件，不是 skill，以繁體中文撰寫（spec 的 Assumptions）。 |

Phase 1 設計後重新檢查：結果相同，沒有需要記錄的違反。

## Project Structure

### Documentation (this feature)

```text
specs/002-global-claude-md/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── claude-md-structure.md   # 文件結構的約定，測試依此檢查
└── tasks.md                     # 由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
home/
└── CLAUDE.md                    # 本功能的產出

tests/
└── unit/
    └── test_claude_md.py        # 結構測試
```

**Structure Decision**: 沿用 001 建立的結構。`home/CLAUDE.md` 會被部署工具自動納入，不需要修改部署程式。

## Complexity Tracking

沒有需要說明的違反。
