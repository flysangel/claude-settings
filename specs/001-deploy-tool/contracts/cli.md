# Contract: 指令介面

## 一行指令

```text
Linux:   curl -fsSL <RAW>/tools/setup.sh | bash [-s -- <參數>]
Windows: irm <RAW>/tools/setup.ps1 | iex
         & ([scriptblock]::Create((irm <RAW>/tools/setup.ps1))) <參數>
```

開機腳本依序：檢查 `git`、`uv` → 取得或更新 `~/.claude-settings` → 執行 `uv run ~/.claude-settings/tools/deploy.py <參數>`。
結束碼就是 `deploy.py` 的結束碼；檢查指令失敗時為 3。

## deploy.py

```text
uv run tools/deploy.py                 安裝或更新（預設）
uv run tools/deploy.py --replace       安裝或更新，並取代衝突的檔案（先備份）
uv run tools/deploy.py remove          移除
uv run tools/deploy.py remove --replace  移除，被手動改過的檔案先搬到 discarded
```

沒有其他參數。未知的參數以結束碼 1 結束並顯示用法。

## 結束碼

| 碼 | 意義 | 是否寫入檔案 |
|---|---|---|
| 0 | 成功，包含「已是最新」與「沒有可移除的內容」 | 視情況 |
| 1 | 執行失敗（例如權限不足、磁碟已滿、無法取得 repo、參數錯誤） | 可能已部分寫入；再次執行會收斂 |
| 2 | 有衝突或手動修改，未指定 `--replace` | 否 |
| 3 | 缺少必要指令 | 否 |

## 輸出

輸出到 stdout，每行一筆，格式固定，兩個平台相同（路徑一律用 `/`）：

```text
created   skills/sdd-init/SKILL.md
updated   CLAUDE.md
adopted   skills/sdd-grill/README.md
deleted   skills/sdd-old/SKILL.md
restored  CLAUDE.md
conflict  CLAUDE.md (not installed by this tool)
conflict  skills/sdd-init/SKILL.md (modified since install)
backup    CLAUDE.md -> .claude-settings/backups/CLAUDE.md
discarded CLAUDE.md -> .claude-settings/discarded/20261120T010203Z/CLAUDE.md
missing   uv
```

最後是摘要，例如 `Installed: 12 created.`、`Installed: 1 updated, 1 deleted.`、`Already up to date.`、
`Removed 12 files.`、`Nothing to remove.`、
`2 conflicts. Nothing was written. Re-run with --replace to overwrite (originals are backed up).`

錯誤訊息輸出到 stderr。
