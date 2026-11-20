# Quickstart: 驗證 sdd-update

以下情境都在暫存目錄進行，不會動到真正的專案，也不會動到 `~/.claude`。

## 前置

- 已安裝 `uv`、`git`、`bash`（Windows 的 `bash` 是隨 Git for Windows 安裝的 Git Bash）。
- 可連線到 PyPI。
- 在 repo 根目錄；下面以 `<repo>` 代表它的路徑。

## 自動測試

```text
uv run --with pytest pytest                      全部（需要網路）
uv run --with pytest pytest -m "not network"     只跑不需要網路的測試
```

預期：全部通過。`tests/e2e/test_cross_platform.py` 與 `tests/e2e/test_cross_platform_update.py` 在本機會跳過，
它們只在 CI 的跨平台 job 執行。`tests/unit/test_claude_md.py` 中「引用的 skill 資料夾存在」一項，
在 6 個 skill 到齊之前仍會跳過。

合併前 CI 的三個 job 在兩個平台都必須是綠的：`test`、`cross-platform-produce`、`cross-platform`。

## 手動情境（腳本）

`<update>` 代表 `uv run <repo>/home/skills/sdd-update/scripts/sdd_update.py`。Windows 在 Git Bash 或 PowerShell 皆可。

手動情境需要一個「以舊版導入」的專案。sdd-init 只會導入最新穩定版，所以先在新的空目錄準備：

```text
git init
uv run --with pytest python -c "import sys; sys.path.insert(0, r'<repo>/tests'); import conftest; raise SystemExit(conftest._load_sdd_init().main(['init'], resolve_version=lambda: '1.2.6'))"
git add -A && git commit -m "spec kit 1.2.6"
```

這與整合測試使用的是同一個入口（只替換「查詢版本」），官方工具仍實際執行。

1. **更新未修改的專案**（US1 情境 1、3）：執行 `<update>`。
   預期結束碼 0；摘要第一行是 `Spec Kit updated from 1.2.6 to <最新穩定版>: …`；
   `removed` 列出 `.claude/skills/speckit-taskstoissues/SKILL.md`，`created` 列出 `.specify/scripts/bash/markdown_sections.py`
   （以當下最新版的實際差異為準）；沒有 `kept`；`git status` 顯示這些異動都未提交。
2. **已是最新版**（US1 情境 2、SC-005）：`git add -A && git commit -m update` 後連續執行 `<update>` 5 次。
   預期每次都只輸出 `Spec Kit <版本> is already the latest stable release. Nothing changed.`，`git status` 始終是乾淨的。
3. **Spec Kit 腳本可用**：`.specify/scripts/bash/create-new-feature.sh --json --short-name demo "Demo"`，
   再執行 `.specify/scripts/bash/setup-plan.sh --json`。預期兩者結束碼 0。
4. **保留修改與專案內容**（US2 情境 1、2）：重新準備一個以舊版導入的專案，改寫 `.specify/memory/constitution.md`、
   新增 `specs/001-demo/spec.md`、在 `.claude/skills/speckit-plan/SKILL.md` 末尾加一行，commit 後執行 `<update>`。
   預期 `speckit-plan/SKILL.md` 列為 `kept … (modified; new version: .specify/sdd-update/.claude/skills/speckit-plan/SKILL.md.new)`，
   該比對副本存在且內容是新版；constitution 與 `specs/` 的 `git diff` 是空的；其餘檔案照常列為 `updated`；
   摘要最後一行是 `Next: …`。
5. **合併後不重複列出**（US2 情境 3）：接續上一步，先再執行一次 `<update>`，預期 `speckit-plan/SKILL.md` 以
   `still differs from …` 列出。把比對副本的內容複製到 `.claude/skills/speckit-plan/SKILL.md` 後再執行一次，
   預期不再列出它，只有 `… is already the latest stable release. Nothing changed.`，且這兩次執行都沒有改變任何檔案。
6. **不是由 sdd-init 導入**：在空目錄先執行
   `uv tool run --from specify-cli==1.2.6 specify init --here --non-interactive --ignore-agent-tools --integration claude --script sh`，
   再執行 `<update>`。預期結束碼 1，訊息請維護者先執行 `/sdd-init`，目錄沒有任何異動。
   接著執行 `uv run <repo>/home/skills/sdd-init/scripts/sdd_init.py init`（既有檔案全部被略過），再執行 `<update>`：
   預期已是最新穩定版，沒有檔案被更動（紀錄的版本是 `/sdd-init` 執行當下的最新穩定版；這些既有檔案要到下一個穩定版發布後
   才會被比對並附上比對副本，見 [research.md](./research.md) 的 R2。這條路徑的逐檔行為由單元測試驗證）。
7. **沒有導入**：在空目錄執行 `<update>`。預期結束碼 1，訊息請維護者先執行 `/sdd-init`，目錄仍是空的。
8. **無法取得版本**：中斷網路後在第 1 步準備好的專案執行 `<update>`。
   預期結束碼 4，訊息說明原因與處理方式，`git status` 是乾淨的。
9. **不是 git repository**：以舊版導入時不做 `git init`，執行 `<update>`。
   預期結束碼 0，沒有 `staged`，摘要有 `Git: not a git repository, and none was created.`，目錄內沒有 `.git`。

「專案比最新穩定版還新」與「更新中途失敗」不容易手動重現，由單元測試驗證
（把紀錄或 `init-options.json` 的版本改成較大的數字、讓寫入在中途失敗）。

## 人工驗收（skill 與跨平台）

先以部署工具安裝到**測試用的家目錄**（不是真正的 `~/.claude`），再開新的 Claude Code session。

| # | 操作 | 預期 |
|---|---|---|
| 1 | 在以舊版導入的專案輸入 `/sdd-update` | 回報版本變化與每一筆更新、建立、移除、保留的檔案；Claude 沒有自行 commit |
| 2 | 要求 Claude「幫我更新 Spec Kit」而不輸入指令 | Claude 請你執行 `/sdd-update`，沒有自行觸發，也沒有手動修改 `.specify/` |
| 3 | 修改一份範本後輸入 `/sdd-update`（需要有新版可更新） | 範本列為保留並附比對副本的路徑；Claude 沒有自行合併 |
| 4 | 把第 1 步的專案 commit 後，在另一個平台 clone，直接輸入 `/speckit-specify` 加一段需求 | 流程正常完成，不需要再次更新或導入；Windows 與 Linux 兩個方向各做一次 |
| 5 | 在沒有導入 Spec Kit 的專案輸入 `/sdd-update` | Claude 回報原因並請你執行 `/sdd-init`，沒有自行執行它 |

指令與輸出格式見 [contracts/cli.md](./contracts/cli.md)，skill 的結構見 [contracts/skill.md](./contracts/skill.md)，
紀錄與判定規則見 [data-model.md](./data-model.md)。
