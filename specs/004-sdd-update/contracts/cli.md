# Contract: sdd_update.py 的指令介面

## 指令

在專案目錄內執行。`<skill>` 是 skill 的安裝位置（`~/.claude/skills/sdd-update`）。

```text
uv run <skill>/scripts/sdd_update.py      把專案的 Spec Kit 更新到最新穩定版
```

沒有子指令、參數與選項（spec：不提供指定版本或降版的選項）。出現任何參數時，以結束碼 1 結束並在 stderr 顯示用法
`usage: sdd_update.py`。

## 結束碼

數字與意義沿用 [003 的 contracts/cli.md](../003-sdd-init/contracts/cli.md)，不新增。

| 碼 | 意義 | 專案內是否有異動 |
|---|---|---|
| 0 | 成功：已更新、已是最新穩定版，或專案比最新穩定版還新 | 只有「已更新」時有 |
| 1 | 執行失敗：沒有導入紀錄、紀錄無法使用、被中斷的導入尚未完成、比對副本的路徑有衝突、寫入失敗、參數錯誤、找不到相鄰的 sdd-init | 只有「寫入失敗」可能已部分寫入；再次執行會完成 |
| 3 | 缺少必要工具（`uv`、`git`、`bash`；判定方式與 003 的「必要工具的判定」完全相同） | 否 |
| 4 | 無法取得最新穩定版，或官方工具執行失敗 | 否 |

結束碼 2 保留不用，理由與 003 相同。

## 執行順序

每一步失敗就停止，不執行後面的步驟。第 6 步之前專案內沒有任何寫入。

| # | 步驟 | 失敗時的結束碼 | 是否連線 |
|---|---|---|---|
| 1 | 檢查參數 | 1 | 否 |
| 2 | 檢查必要工具 | 3 | 否 |
| 3 | 讀取導入紀錄 | 1 | 否 |
| 4 | 查詢最新穩定版，與專案的版本比較 | 4 | 是 |
| 5 | 在專案外的暫存目錄以最新穩定版執行官方工具，並規劃每個檔案的動作 | 4（官方工具）或 1（衝突） | 是（uv 下載套件） |
| 6 | 寫入：紀錄、比對副本、建立、取代、刪除、加入暫存區、紀錄 | 1 | 否 |
| 7 | 輸出回報 | | 否 |

第 4 步判定為「已是最新穩定版」或「比最新穩定版還新」時，不執行第 5、6 步。

## 輸出

輸出到 stdout，以英文撰寫，每行一筆，格式固定；兩個平台的輸出逐字相同（路徑一律用 `/`）。
逐行格式與 003 相同：動作名稱靠左補滿 10 個字元，後面接內容。錯誤訊息輸出到 stderr，內容包含原因與處理方式。

### 已更新

依下列順序分段，各段內依路徑排序；沒有項目的段落不輸出。

```text
updated   .claude/skills/speckit-plan/SKILL.md
created   .specify/scripts/bash/markdown_sections.py
removed   .claude/skills/speckit-taskstoissues/SKILL.md
kept      .specify/templates/plan-template.md (modified; new version: .specify/sdd-update/.specify/templates/plan-template.md.new)
kept      .specify/templates/spec-template.md (not created by sdd-init; new version: .specify/sdd-update/.specify/templates/spec-template.md.new)
kept      .claude/skills/speckit-legacy/SKILL.md (modified; no longer part of Spec Kit 1.4.3)
staged    .specify/scripts/bash/setup-tasks.sh (executable bit recorded in the git index)
warning   .specify/scripts/bash/setup-tasks.sh has no eol=lf rule in git; it will not run after a checkout that converts line endings
```

| 動作 | 意義 | 對應 [data-model.md](../data-model.md) 的動作 |
|---|---|---|
| `updated` | 內容未被修改，已取代為新版 | `update` |
| `created` | 新建立的檔案，包含不存在時建立的 `.specify/.gitattributes` | `create` |
| `removed` | 新版不再提供、內容未被修改，已刪除 | `remove` |
| `kept` | 保留不動；括號內是原因與比對副本的路徑 | `keep`、`keep-orphan` |
| `staged` | 以 `git add --chmod=+x` 加入暫存區的 `.sh`（新建與補登） | |
| `warning` | 新版的 `.sh` 在 git 的有效 `eol` 設定不是 `lf`；只在專案是 git repository 時檢查 | |

`kept` 一行括號內的三種形式，文字固定：

```text
(modified; new version: <比對副本的路徑>)
(not created by sdd-init; new version: <比對副本的路徑>)
(modified; no longer part of Spec Kit <新版本>)
```

不輸出的項目：與新版相同而沒有寫入的檔案、`.specify/memory/` 下的檔案、紀錄 `.specify/sdd-init.json`、
比對副本本身（它的路徑已在 `kept` 那一行）、被刪除的舊比對副本與空目錄。

之後是摘要，兩行或三行：

```text
Spec Kit updated from 1.2.6 to 1.4.3: 17 updated, 1 created, 1 removed, 2 kept.
Git: 1 files were added to the index and nothing was committed. Review the update with git status, then commit it.
Next: compare each kept file with its .new copy under .specify/sdd-update/, merge what you want, then delete the copies.
```

| 行 | 內容 | 規則 |
|---|---|---|
| 1 | `Spec Kit updated from <原版本> to <新版本>: <u> updated, <c> created, <r> removed, <k> kept.` | `<原版本>` 是紀錄的版本；四個數字分別等於上面 `updated`、`created`、`removed`、`kept` 的行數 |
| 2 | `Git:` | 三種形式，見下 |
| 3 | `Next:` | 文字固定；只在這次寫入了至少一份比對副本時輸出 |

`Git:` 一行的三種形式：

```text
Git: <n> files were added to the index and nothing was committed. Review the update with git status, then commit it.
Git: nothing was added to the index and nothing was committed. Review the update with git status, then commit it.
Git: not a git repository, and none was created. Executable bits cannot be recorded until the files are added with: git add --chmod=+x .specify/scripts/bash/*.sh
```

`<n>` 是這次實際加入暫存區的檔案數，等於 `staged` 的行數。第三種形式與 003 逐字相同。

### 不需要更新

只輸出下列內容，不輸出 `Git:` 一行。結束碼 0，專案內沒有任何異動，也不執行官方工具。

| 情況 | 輸出 |
|---|---|
| 已是最新穩定版，沒有仍待合併的檔案 | `Spec Kit <版本> is already the latest stable release. Nothing changed.` |
| 已是最新穩定版，有仍待合併的檔案 | 每個檔案一行 `kept`（形式見下），再加上面那一行，最後一行 `Next:`（與「已更新」的第 3 行逐字相同） |
| 專案比最新穩定版還新 | `Spec Kit <專案的版本> is newer than the latest stable release <最新穩定版>. Nothing changed.` |

仍待合併的檔案（定義見 [data-model.md](../data-model.md) 的「比對副本」）的 `kept` 行：

```text
kept      .specify/templates/plan-template.md (still differs from Spec Kit 1.4.3; new version: .specify/sdd-update/.specify/templates/plan-template.md.new)
```

`<專案的版本>` 是紀錄的版本與 `.specify/init-options.json` 的版本中較新的一個，原樣輸出（例如 `1.5.0rc1`）。

### 停止

stdout 只有一行摘要（缺少工具時前面另有 `missing` 行）；原因與處理方式的細節輸出到 stderr。專案內沒有任何異動。

| 情況 | 結束碼 | stdout 的摘要 |
|---|---|---|
| 缺少工具 | 3 | `missing` 行（格式與 003 逐字相同），再加 `Missing required tools. Nothing was changed. Install them and run /sdd-update again.` |
| 沒有導入紀錄 | 1 | `Spec Kit was not updated: this project has no sdd-init record. Run /sdd-init first, then run /sdd-update again.` |
| 紀錄無法使用 | 1 | `Spec Kit was not updated: .specify/sdd-init.json cannot be used. Nothing was changed.` |
| 被中斷的導入 | 1 | `Spec Kit was not updated: the setup by /sdd-init was interrupted. Run /sdd-init to finish it, then run /sdd-update again.` |
| 無法取得版本或官方工具失敗 | 4 | `Could not get the latest stable Spec Kit release: <原因>. Nothing was changed. Check the network connection and run /sdd-update again.` |
| 比對副本的路徑有衝突 | 1 | `Spec Kit was not updated: <路徑> is in the way. Nothing was changed. Move it away and run /sdd-update again.` |
| 找不到相鄰的 sdd-init | 1 | `Spec Kit was not updated: the sdd-init skill is not installed next to sdd-update. Nothing was changed.` |

「紀錄無法使用」涵蓋無法解析、`schema` 不認得、欄位不合規則與路徑違反規則；stderr 的第一行寫出具體原因，
文字沿用 003 的 init，名稱寫 `sdd-update`（實作時定案）：
`error: .specify/sdd-init.json is not a record this version of sdd-update can use: <原因>.`

「比對副本的路徑有衝突」的 `<路徑>` 是第一個（依路徑排序）擋住寫入的路徑：要寫入比對副本的位置上有不在紀錄內的檔案，
或要建立的檔案的某個上層路徑存在但不是目錄。

### 寫入失敗

結束碼 1。stdout 不輸出摘要；stderr：

```text
error: writing into the project failed: <原因>
Some files may already have been updated. Fix the cause, then run /sdd-update again; it finishes the update and never overwrites a file you changed.
```

再次執行時從紀錄與專案目前的狀態重新判定（[data-model.md](../data-model.md) 的「狀態轉移」）。
那一次的回報只包含它自己做的事：上一次已經取代完成的檔案不會再列為 `updated`。

`git add --chmod=+x` 失敗不算寫入失敗，處理方式與 003 相同：stderr 一行
`note: <路徑> was not added to the git index: <原因>`，不輸出該檔案的 `staged` 行，結束碼不受影響。

## 不變的保證

- 只取代、刪除紀錄內且內容未被修改的 Spec Kit 檔案；被修改過的檔案、不在紀錄內的檔案一律不寫入、不刪除。
- `.specify/memory/` 與 `specs/` 不讀寫；寫入的範圍只有 Spec Kit 檔案的路徑、`.specify/sdd-update/`、
  `.specify/.gitattributes`（不存在時）與紀錄。
- 已是最新穩定版、專案比最新穩定版還新，以及所有「停止」的情況，專案內的檔案與 index 都沒有任何異動。
- 不 commit、不建立 repository、不切換分支。對暫存區的異動只有兩種：以 `git add --chmod=+x` 加入這次新建的 `.sh`
  與 003 定義的待補登的 `.sh`；以 `git rm --cached` 取消被刪除、先前由本工具加入且尚未 commit 的 `.sh`。
  已在 index 的項目不改寫。
- 新版的檔案內容只來自官方工具的產出，位元組原樣寫入。
- 不安裝、不升級使用者環境中的任何工具；不重試，不改用其他來源取得 Spec Kit。
- 不提供降版：目標永遠是執行當下的最新穩定版。

## 只為測試存在的入口

與 003 相同：`main()` 以關鍵字參數接受「查詢版本」與「執行官方工具」兩個可替換的函式，
測試以假的版本與假的官方產出取代它們；必要工具判定的兩個可替換函式沿用 `sdd_init.py` 內的那一份。
不提供環境變數或隱藏選項來改變正式執行的行為。
