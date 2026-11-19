# Research: 部署工具

## R1 實作語言與執行方式

- **Decision**: 部署邏輯寫成單一 Python 腳本 `tools/deploy.py`，以 `uv run` 執行，腳本開頭用 inline metadata 宣告
  `requires-python = ">=3.11"` 且沒有第三方相依。
- **Rationale**: 維護者指定 Python script 一律用 uv 執行。單一程式在兩個平台跑同一份邏輯，是達成「完全對等」
  成本最低的方式；uv 會自行準備 Python，所以機器不需要預先安裝 Python。
- **Alternatives considered**: 各寫一份 bash 與 PowerShell（兩份邏輯必然漂移，違反原則 II）；
  打包成可安裝的套件（對數十個檔案的複製過度設計）。

## R2 一行指令與開機腳本

- **Decision**: 兩支薄的開機腳本，只做三件事：(1) 檢查 `git` 與 `uv`，一次列出全部缺少的指令後以結束碼 3 停止；
  (2) 把 repo clone 到 `~/.claude-settings`，已存在就 `git pull --ff-only`；(3) 執行
  `uv run <clone>/tools/deploy.py`，並把參數原樣轉交。

  ```text
  Linux:   curl -fsSL <RAW>/tools/setup.sh | bash
  Windows: irm <RAW>/tools/setup.ps1 | iex
  ```

  需要參數時（`--replace`、`remove`）：

  ```text
  Linux:   curl -fsSL <RAW>/tools/setup.sh | bash -s -- --replace
  Windows: & ([scriptblock]::Create((irm <RAW>/tools/setup.ps1))) --replace
  ```

- **Rationale**: 開機腳本無法共用語言，所以盡量薄，把可測的邏輯都放進 Python。clone 位置固定，符合「不提供可調選項」。
- **Alternatives considered**: 下載壓縮檔而不 clone（少了更新時的版本資訊，也要自己處理解壓）；
  開機腳本自動安裝缺少的工具（維護者明確要求不代為安裝）。
- **Open item**: `<RAW>` 與 clone 的 URL 取決於 repo 公開後的位址，目前還沒有 remote。兩支腳本各以一個常數保存，
  建立 remote 時填入。測試以環境變數 `CLAUDE_SETTINGS_REPO` 覆寫為本機路徑；這個變數只為測試存在，不寫進使用說明。

## R3 必要指令的範圍

- **Decision**: 必要指令是 `git` 與 `uv`。`curl`/`irm` 是執行一行指令本身的前提，不另外檢查。不檢查 Claude Code。
- **Rationale**: 規格要求檢查「需要用到的指令」；部署只用到這兩個。沒有 Claude Code 也能部署，裝了之後設定就生效。
- **Alternatives considered**: 連 Claude Code 一起檢查（會讓「先放好設定再裝 Claude Code」的順序失敗，沒有必要）。

## R4 分辨檔案歸屬

- **Decision**: 安裝紀錄 manifest 記錄每個已部署檔案的相對路徑與部署當下的 SHA-256。目標路徑上每個檔案分成四類：

  | 狀態 | 判定 | 處理 |
  |---|---|---|
  | 不存在 | 目標沒有檔案 | 寫入 |
  | 相同 | 目標雜湊等於要部署的內容 | 不寫入；納入 manifest |
  | 自己的、未改 | 在 manifest 內且目標雜湊等於紀錄 | 可更新或移除 |
  | 自己的、被改過 | 在 manifest 內但目標雜湊不同 | 衝突 |
  | 別人的 | 不在 manifest 內且內容不同 | 衝突 |

- **Rationale**: 以內容雜湊而不是修改時間判斷，兩個平台結果一致，也不受 clone 或複製影響。
  manifest 遺失時所有檔案都落入「相同」或「別人的」，自然滿足規格的邊界情況。
- **Alternatives considered**: 在檔案內加標記（會改動 skill 內容，且使用者刪掉標記就失效）；用 symlink 指向 clone
  （Windows 需要額外權限，且手動修改會直接改到 clone）。

## R5 整批不寫入與中途失敗

- **Decision**: 兩階段。規劃階段只讀取，算出每個檔案的動作與全部衝突；有任何衝突且沒有 `--replace` 就以結束碼 2 結束，
  完全不寫入。執行階段的順序是：先寫入狀態為 `applying` 的 manifest（含本次的完整計畫與備份對應）→ 備份 →
  以暫存檔加 `os.replace` 逐一寫入 → 刪除新版不再提供的檔案 → 把 manifest 改為 `complete`。
- **Rationale**: 規劃與執行分離讓「零寫入」可以被測試直接驗證。先落下 `applying` 的 manifest，
  中途失敗後再次執行時，已寫入的檔案雜湊等於新內容（視為相同）、未寫入的等於舊紀錄（視為未改），都能繼續完成，
  不會出現歸屬不明的檔案。
- **Alternatives considered**: 先複製到暫存目錄再整個目錄替換（`~/.claude` 內有大量不屬於本工具的內容，不能整個替換）。

## R6 備份與移除

- **Decision**: 備份放在 `~/.claude/.claude-settings/backups/<相對路徑>`，manifest 的該筆紀錄標記 `backup: true`。
  移除時：刪除自己的檔案 → 把備份搬回原位 → 刪除因此變空且由本工具建立的目錄 → 刪除狀態目錄。
  以 `--replace` 覆蓋「自己的、被改過」的檔案時，被改過的版本放到
  `~/.claude/.claude-settings/discarded/<UTC 時間>/<相對路徑>`，不參與還原；移除後若這個目錄有內容就保留並回報位置。
- **Rationale**: 「別人的原檔」與「使用者對本工具檔案的修改」是兩種東西：前者移除時要還原，後者只是避免遺失。
  分開存放讓移除的行為明確。同一路徑的原檔備份只保留第一次的，才能還原到安裝前的狀態。
- **Alternatives considered**: 使用 `~/.claude/backups/`（Claude Code 自己已在使用這個目錄，避免混在一起）。

## R7 兩個平台的內容一致

- **Decision**: repo 加上 `.gitattributes`（`* text=auto eol=lf`），部署時以位元組原樣複製，manifest 路徑一律用 `/`。
- **Rationale**: Windows 上 git 預設可能把換行轉成 CRLF，雜湊就會與 Linux 不同，違反 SC-002。
- **Alternatives considered**: 計算雜湊前正規化換行（部署出去的檔案仍然不同，只是把差異藏起來）。

## R8 測試與 CI

- **Decision**: pytest。單元測試直接呼叫 `deploy.py` 的函式，以暫存目錄當家目錄（設定 `HOME` 與 `USERPROFILE`）
  與暫存的部署來源。E2E 測試以本機的 bare repo 當來源，實際執行 `setup.sh`（Linux）與 `setup.ps1`（Windows）。
  CI 用 GitHub Actions，矩陣為 `ubuntu-latest` 與 `windows-latest`，兩者都通過才能合併。
- **Rationale**: 原則 II 要求每個功能有自動測試且兩個平台都通過。E2E 用本機 repo 就不需要網路與公開位址。
- **Alternatives considered**: 只做單元測試（開機腳本是兩個平台唯一不同的部分，最需要實跑）。
