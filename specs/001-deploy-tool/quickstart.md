# Quickstart: 驗證部署工具

以下情境都在暫存的家目錄進行，不會動到真正的 `~/.claude`。

## 前置

- 已安裝 `git` 與 `uv`。
- 在 repo 根目錄。

## 自動測試

```text
uv run --with pytest pytest
```

預期：全部通過。Linux 會跳過 `test_setup_ps1.py`，Windows 會跳過 `test_setup_sh.py`。
合併前兩個平台的 CI 都必須是綠的。

## 手動情境（Linux 示範；Windows 把 `HOME=` 改成設定 `$env:USERPROFILE`）

```text
export HOME="$(mktemp -d)"
```

1. **全新安裝**：`uv run tools/deploy.py`
   預期結束碼 0；`$HOME/.claude` 內出現 `home/` 的全部檔案；輸出逐筆列出 `created`。
2. **重複執行**：再執行一次。
   預期結束碼 0，輸出 `Already up to date.`，沒有任何檔案的修改時間改變。
3. **別人的檔案**：刪除 `$HOME/.claude` 後，先自行建立內容不同的 `$HOME/.claude/CLAUDE.md`，再執行安裝。
   預期結束碼 2；輸出列出 `conflict CLAUDE.md`；`$HOME/.claude` 內除了你建立的檔案之外什麼都沒有。
4. **明確取代**：`uv run tools/deploy.py --replace`
   預期結束碼 0；原檔出現在 `.claude-settings/backups/CLAUDE.md`。
5. **手動修改**：在 `$HOME/.claude/CLAUDE.md` 末尾加一行，再執行安裝。
   預期結束碼 2，列出 `conflict CLAUDE.md (modified since install)`，沒有任何寫入。
6. **移除**：先把第 5 步的修改還原，再執行 `uv run tools/deploy.py remove`
   預期結束碼 0；本工具安裝的檔案都消失；`CLAUDE.md` 變回第 3 步你建立的內容；`.claude-settings/` 不存在。
7. **缺少指令**：在 `PATH` 找不到 `uv` 的環境執行 `bash tools/setup.sh`
   預期結束碼 3，列出 `missing uv`，沒有 clone 也沒有寫入。

介面細節見 [contracts/cli.md](./contracts/cli.md)，檔案判定規則見 [data-model.md](./data-model.md)。
