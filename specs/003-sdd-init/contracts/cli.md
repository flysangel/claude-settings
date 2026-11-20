# Contract: sdd_init.py 的指令介面

## 指令

在專案目錄內執行。`<skill>` 是 skill 的安裝位置（`~/.claude/skills/sdd-init`）。

```text
uv run <skill>/scripts/sdd_init.py init      導入 Spec Kit
uv run <skill>/scripts/sdd_init.py remove    移除 Spec Kit
```

沒有其他參數與選項。沒有子指令或出現未知的參數時，以結束碼 1 結束並顯示用法。

## 結束碼

| 碼 | 意義 | 專案內是否有異動 |
|---|---|---|
| 0 | 成功，包含「已導入」與「沒有可移除的內容」 | 視情況 |
| 1 | 執行失敗（例如權限不足、磁碟已滿、紀錄無法解析、參數錯誤） | 可能已部分寫入；再次執行會補齊 |
| 3 | 缺少必要工具（`uv`、`git`、`bash`） | 否 |
| 4 | 無法取得最新穩定版，或官方工具執行失敗 | 否 |

結束碼 2 保留不用，與 001 部署工具的「衝突」區隔。

## 輸出

輸出到 stdout，以英文撰寫，每行一筆，格式固定；兩個平台的輸出逐字相同（路徑一律用 `/`，各段內依路徑排序）。
錯誤訊息輸出到 stderr，內容包含原因與處理方式（SC-006）。

### init

```text
created   .specify/templates/plan-template.md
created   .specify/.gitattributes
skipped   .claude/skills/speckit-plan/SKILL.md (already exists, left untouched)
staged    .specify/scripts/bash/setup-plan.sh (executable bit recorded in the git index)
warning   .specify/.gitattributes was not created by sdd-init; add this line to it: scripts/bash/*.sh text eol=lf
missing   bash
```

之後是摘要。新導入或補齊時，摘要固定四行，順序如下：

```text
Spec Kit 1.4.3 initialized: 31 created, 0 skipped.
Git: 6 files were added to the index and nothing was committed. 31 paths are uncommitted.
Next: run /sdd-grill to be questioned until the constitution and specs are decided.
Or use Spec Kit directly: run /speckit-constitution, then /speckit-specify.
```

| 行 | 內容 | 是否隨情況改變 |
|---|---|---|
| 1 | 結果 | 是，見下方「各種情況的摘要」 |
| 2 | `Git:` | 是，見下方的三種形式 |
| 3 | 下一步建議：本專案的 skill | 否，逐字固定 |
| 4 | 下一步建議：原生 Spec Kit 指令 | 否，逐字固定 |

第 3、4 行是下一步建議，兩條路都 MUST 列出，文字不含任何變數，兩個平台逐字相同：

```text
Next: run /sdd-grill to be questioned until the constitution and specs are decided.
Or use Spec Kit directly: run /speckit-constitution, then /speckit-specify.
```

下一步建議 MUST NOT 提到這兩條路以外的指令。

各種情況的摘要：

| 情況 | 摘要的第一行 |
|---|---|
| 新導入或補齊 | `Spec Kit <版本> initialized: <n> created, <m> skipped.` |
| 已完整導入 | `Spec Kit <版本> is already initialized. Nothing changed.` |
| 缺少工具 | `Missing required tools. Nothing was created. Install them and run /sdd-init again.` |
| 無法取得版本 | `Could not get the latest stable Spec Kit release: <原因>. Nothing was created. Check the network connection and run /sdd-init again.` |

`Git:` 一行的三種形式：

```text
Git: <n> files were added to the index and nothing was committed. <k> paths are uncommitted.
Git: nothing was added to the index. <k> paths are uncommitted.
Git: not a git repository, and none was created. Executable bits cannot be recorded until the files are added with: git add --chmod=+x .specify/scripts/bash/*.sh
```

已完整導入時只輸出摘要的第一行，不輸出 `Git:` 與下一步建議。

### remove

```text
deleted   .specify/templates/plan-template.md
kept      .specify/memory/constitution.md (modified since init)
unstaged  .specify/scripts/bash/setup-plan.sh
```

摘要：

| 情況 | 摘要 |
|---|---|
| 有刪除 | `Spec Kit removed: <n> deleted, <m> kept because they were modified.` |
| 沒有紀錄 | `Nothing to remove: this project has no sdd-init record, so no file can be proven to be created by sdd-init.` |
| 紀錄無法解析 | `Nothing was removed: .specify/sdd-init.json cannot be read, so no file can be proven to be created by sdd-init.` |

## 不變的保證

- init 不覆蓋、不修改任何既有檔案；remove 只刪除紀錄內且內容未被修改的檔案。
- 兩個指令都不 commit、不建立 repository、不切換分支。
- init 對暫存區唯一的異動是加入自己建立的 `.sh`；remove 對暫存區唯一的異動是取消其中仍未 commit 的項目。
- 不讀寫 `specs/`。
- 不安裝、不升級使用者環境中的任何工具。

## 只為測試存在的入口

測試以函式參數替換「查詢版本」與「執行官方工具」這兩步；不提供環境變數或隱藏選項來改變正式執行的行為。
