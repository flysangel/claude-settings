# Quickstart: 驗證 sdd-init

以下情境都在暫存目錄進行，不會動到真正的專案。

## 前置

- 已安裝 `uv`、`git`、`bash`（Windows 的 `bash` 是隨 Git for Windows 安裝的 Git Bash）。
- 可連線到 PyPI。
- 在 repo 根目錄；下面以 `<repo>` 代表它的路徑。

## 自動測試

```text
uv run --with pytest pytest                      全部（需要網路）
uv run --with pytest pytest -m "not network"     只跑不需要網路的測試
```

預期：全部通過。`tests/e2e/test_cross_platform.py` 在本機會跳過，它只在 CI 的跨平台 job 執行。
`tests/unit/test_claude_md.py` 中「引用的 skill 資料夾存在」一項，在 6 個 skill 到齊之前仍會跳過。

合併前 CI 的兩個 job 在兩個平台都必須是綠的：`test`（單元與整合）與 `cross-platform`（互相交換導入後的 repository）。

## 手動情境（腳本）

在新的空目錄執行；Windows 在 Git Bash 或 PowerShell 皆可。`<init>` 代表
`uv run <repo>/home/skills/sdd-init/scripts/sdd_init.py`。

1. **全新導入**：`git init` 後執行 `<init> init`。
   預期結束碼 0；逐筆列出 `created` 與 `staged`；摘要顯示的版本等於 PyPI 上 `specify-cli` 的最新穩定版；
   摘要的最後兩行是下一步建議，先 `/sdd-grill`，再 `/speckit-constitution` 與 `/speckit-specify`；
   `git status` 顯示 6 支 `.sh` 已在暫存區、其餘未追蹤、沒有新的 commit。
2. **重複執行**：再執行一次。
   預期只輸出 `Spec Kit <版本> is already initialized. Nothing changed.`，`git status` 與上一步完全相同。
3. **Spec Kit 腳本可用**：`.specify/scripts/bash/create-new-feature.sh --json --short-name demo "Demo"`，
   再執行 `.specify/scripts/bash/setup-plan.sh --json`。
   預期兩者結束碼 0，產生 `specs/001-demo/plan.md`。
4. **移除並保留修改**：在 `.specify/memory/constitution.md` 末尾加一行，執行 `<init> remove`。
   預期 `constitution.md` 列為 `kept`，其餘列為 `deleted`，6 支 `.sh` 列為 `unstaged`；`specs/001-demo/` 原封不動。
5. **不覆蓋既有檔案**：在另一個空目錄先自行建立內容為 `MINE` 的 `.specify/templates/plan-template.md`，再執行 `<init> init`。
   預期該檔列為 `skipped` 且內容仍是 `MINE`；其餘檔案照常建立。接著執行 `<init> remove`，預期該檔仍在。
6. **導入後立即移除**：在只有一個 `README.md` 且已 commit 的 repository 執行 `init` 再執行 `remove`。
   預期目錄內容與 `git status` 都和導入前完全相同。
7. **不是 git repository**：在沒有 `git init` 的空目錄執行 `<init> init`。
   預期結束碼 0，沒有 `staged`，摘要有 `Git: not a git repository, and none was created.`，目錄內沒有 `.git`。
8. **無法取得版本**：中斷網路後在空目錄執行 `<init> init`。
   預期結束碼 4，訊息說明原因與處理方式，目錄仍是空的。
9. **沒有紀錄時移除**：在空目錄執行 `<init> remove`。
   預期結束碼 0，輸出 `Nothing to remove: …`，沒有任何異動。

## 人工驗收（skill 與跨平台）

先以部署工具安裝，再開新的 Claude Code session。

| # | 操作 | 預期 |
|---|---|---|
| 1 | 在沒有 Spec Kit 的專案輸入 `/sdd-init` | 回報版本、建立的檔案、加入暫存區的檔案與下一步的兩條路（`/sdd-grill`，或 `/speckit-constitution` 再 `/speckit-specify`）；Claude 沒有自行 commit |
| 2 | 要求 Claude「幫這個專案導入 Spec Kit」而不輸入指令 | Claude 請你執行 `/sdd-init`，沒有自行觸發 |
| 3 | 把第 1 步的專案 commit 後，在另一個平台 clone，直接輸入 `/speckit-specify` 加一段需求 | 流程正常完成，不需要重新導入或手動補檔；Windows 與 Linux 兩個方向各做一次 |
| 4 | 輸入 `/sdd-init remove` | 回報刪除與保留的檔案；`specs/` 不變 |
| 5 | 把 `uv` 從 `PATH` 移除後輸入 `/sdd-init` | Claude 回報缺少 `uv` 與處理方式後停止，沒有改用其他方式安裝 |

指令與輸出格式見 [contracts/cli.md](./contracts/cli.md)，skill 的結構見 [contracts/skill.md](./contracts/skill.md)，
紀錄與判定規則見 [data-model.md](./data-model.md)。
