# Quickstart: 驗證全域 CLAUDE.md

## 自動測試（結構）

```text
uv run --with pytest pytest tests/unit/test_claude_md.py
```

預期：全部通過。在 6 個 skill 資料夾到齊之前，「引用的 skill 資料夾存在」這一項會跳過並列出缺少的 skill。

## 人工驗收（行為）

先以部署工具安裝（會遇到既有的 `~/.claude/CLAUDE.md`，需要 `--replace`，原檔會備份），
然後在一個沒有專案層級 CLAUDE.md 的目錄開新的 Claude Code session，逐項確認：

| # | 操作 | 預期 |
|---|---|---|
| 1 | 用英文問一個問題 | 回覆是繁體中文，指令與識別字保留原文 |
| 2 | 提出一個有兩種做法的需求 | 以互動式選項提問，並標出建議的選項 |
| 3 | 在 git repo 的 `main` 上要求修改一個檔案 | 先開分支再 commit；回合結束沒有未提交的內容；`main` 沒有新 commit |
| 4 | 接續第 3 步，不要求 push | 遠端沒有變化 |
| 5 | 在沒有 `.specify/` 的專案要求開發新功能 | 請你執行 `/sdd-init`，沒有手動建立 Spec Kit 的檔案 |
| 6 | 在已導入的專案提出方向未定的新需求 | 使用 `sdd-grill`，一次只問一題並附建議 |
| 7 | 詢問如何把舊專案重做一次 | 指引舊專案 `/sdd-export`、新專案 `/sdd-rebuild` |
| 8 | spec 確認後說「開始實作」 | 說明由你在主 session 輸入 `/sdd-drive`，沒有自行開始實作 |
| 9 | 要求修正一個錯字 | 直接修改，沒有要求走 Spec Kit |
| 10 | 詢問 Spec Kit 怎麼更新 | 指引 `/sdd-update` |

第 6 至 8、10 項提到的 skill 在 003 至 008 完成前還沒安裝；此時預期 Claude 回報該 skill 不存在，而不是自行模擬流程。

文件結構見 [contracts/claude-md-structure.md](./contracts/claude-md-structure.md)。
