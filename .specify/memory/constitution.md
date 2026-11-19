# claude-settings Constitution

claude-settings 是個人化的 Claude Code 設定：全域 CLAUDE.md、一行部署指令，以及以 Spec Kit
為主的 6 個 SDD skill。

## Core Principles

### I. 只包裝、不修改 Spec Kit

`.specify/` 與 `speckit-*` skill 一律由 Spec Kit 官方工具產生與更新。本專案的 skill 只呼叫它們，
MUST NOT 手寫或修改這些檔案。

理由：專案要能持續更新 Spec Kit，不修改上游檔案才不會在更新時產生衝突或遺失修改。

### II. Windows 與 Linux 完全對等

- 每個功能在 Windows 與 Linux MUST 有相同的行為。
- 每個功能 MUST 有自動測試，且在 Windows 與 Linux 的 CI 上都通過才能合併。
- 只在其中一個平台能用的功能 MUST NOT 合併。

理由：沒有明確的驗收門檻時，較少日常使用的平台最容易悄悄壞掉。

### III. 保護既有檔案

- MUST NOT 覆蓋或刪除不是本專案工具自己建立的檔案。
- 遇到衝突 MUST 停止並回報；只有使用者明確要求取代時，才先備份再寫入。
- 所有操作重複執行 MUST 得到相同結果。

理由：工具會寫入使用者的 `~/.claude` 與各個目標專案，這些地方有使用者自己的內容。

### IV. 先確認再寫入

- 會產生或改寫 constitution、spec 的 skill MUST 先呈現摘要或草稿，維護者確認後才寫入。
- 無法從專案或對話取得依據的內容 MUST 標為待確認，MUST NOT 寫成事實。

理由：spec 是後續 plan 與實作的依據，錯誤內容一旦寫入會一路放大。

### V. 個人使用、repo 公開

- 內容只為維護者自己的偏好設計，不為其他使用者提供可調選項。
- repo 是公開的，MUST NOT 提交機密、憑證、機器專屬路徑與個人信箱。

### VI. 文件語言

- constitution 與 spec MUST 使用繁體中文，MUST、SHOULD 等規範詞保留英文。
- Skill MUST 以英文撰寫，且每個 skill 的資料夾 MUST 有一份繁體中文的 README 簡述。

## Governance

- 本 constitution 優先於其他開發慣例。
- 修訂 MUST 經維護者確認，並更新版本號。

**Version**: 1.0.0 | **Ratified**: 2026-11-19 | **Last Amended**: 2026-11-19
