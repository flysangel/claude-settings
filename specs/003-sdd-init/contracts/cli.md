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
| 3 | 缺少必要工具（`uv`、`git`、`bash`；Windows 上的 `bash` 只承認 Git Bash，見「必要工具的判定」） | 否 |
| 4 | 無法取得最新穩定版，或官方工具執行失敗 | 否 |

結束碼 2 保留不用，與 001 部署工具的「衝突」區隔。

## 必要工具的判定

維護者在 T041 之後追加的決定：Windows 上 MUST 分辨 Git Bash 與 WSL 的啟動器，只承認 Git Bash。

| 工具 | Linux | Windows |
|---|---|---|
| `uv` | `PATH` 上有 `uv` | 同左 |
| `git` | `PATH` 上有 `git` | 同左 |
| `bash` | `PATH` 上有 `bash` | 找得到 Git for Windows 附的 Git Bash，方法見下 |

### Windows 上判定 Git Bash 的方法

Git Bash 的定義是「Git for Windows 這套安裝內附的 `bash.exe`」，所以判定從 `git` 出發，不看 `PATH` 上的 `bash`：

1. 依 `PATH` 的順序列出每一個 `git`（不只第一個）。
2. 對每一個 `git` 執行 `git --version`。輸出含有 `.windows.`（例如 `git version 2.47.1.windows.2`）才是 Git for Windows；
   不是的就略過，看下一個。
3. 對 Git for Windows 的 `git` 執行 `git --exec-path`（執行時移除環境變數 `GIT_EXEC_PATH`，避免被它改寫），
   取得這套安裝內的目錄，再由近到遠檢查它的每一層上層目錄 `<上層>` 是否有 `<上層>/bin/bash.exe` 或 `<上層>/usr/bin/bash.exe`。
   第一個存在的檔案就是 Git Bash。
4. 所有 `git` 都試過仍找不到時，`bash` 視為缺少的工具。

這個方法的性質：

- 不依賴固定的安裝路徑：位置由 `git` 自己回報，安裝程式、winget、scoop、可攜版裝在任何位置都相同。
- 不受 `PATH` 上 `bash` 的順序影響：`PATH` 上的 `bash.exe` 完全不參與判定，所以 WSL 的啟動器
  （例如 `System32` 內的 `bash.exe`）排在前面、排在後面或是唯一的 `bash.exe`，結果都只取決於有沒有 Git Bash。
- 只執行 `git`，MUST NOT 執行任何 `bash.exe`（執行 WSL 的啟動器會啟動 WSL）。

### 這項檢查保證與不保證的事

sdd-init 自己不執行 Spec Kit 的 `.sh`；執行它們的是 Claude Code 的 Bash tool。這項檢查只在導入前確認
**這台機器具備 Git Bash**，讓缺少它的機器在寫入任何檔案之前就得到明確的說明。

- 保證：結束碼不是 3 時，這台機器上有一套 Git for Windows，其中有 `bash.exe`，而且它的 `git` 在 `PATH` 上。
- 不保證：Claude Code 的 Bash tool 之後實際使用的是這個 Git Bash。那由 Claude Code 自己的設定決定，sdd-init 不讀取也不改變它。
- 不保證：這個 `bash.exe` 能正常執行。檢查只確認檔案存在，不執行它。
- sdd-init MUST NOT 因為這項檢查而改變 `PATH`、寫入設定，或記錄找到的路徑。

### 判定不出來的情況

以下情況會被列為缺少 `bash`（結束碼 3），即使機器上可能有能用的 bash：

| 情況 | 處理方式 |
|---|---|
| 裝了 Git for Windows，但它的 `git` 不在執行 sdd-init 的 `PATH` 上（例如安裝時選了只在 Git Bash 內使用 git，或可攜版沒有加入 `PATH`） | 把 Git for Windows 的 `git` 加入 `PATH` |
| `git` 不是 Git for Windows（MSYS2、Cygwin 等自己的 git 與 bash） | 安裝 Git for Windows |
| Git for Windows 的安裝內沒有 `bash.exe`（例如 MinGit） | 安裝完整的 Git for Windows |
| `PATH` 上的 `git` 只是轉呼叫 WSL 內 git 的包裝 | 安裝 Git for Windows |

### 缺少工具時的輸出

每個缺少的工具一行 `missing`，依工具名稱排序，一次列出全部；之後是摘要的第一行（見「各種情況的摘要」）。格式兩個平台相同：

```text
missing   <工具>
missing   <工具> (<說明>)
```

只有 Windows 上的 `bash` 帶說明，文字固定：

| 平台 | 缺少 `bash` 時的 `missing` 行 |
|---|---|
| Linux | `missing   bash` |
| Windows | `missing   bash (Git Bash, included with Git for Windows)` |

`uv` 與 `git` 在兩個平台都是 `missing   uv`、`missing   git`。

stderr：第一行 `error: required tools are missing: <以逗號分隔的工具名稱>`（只有名稱，不帶說明），第二行是處理方式。
Windows 上缺少 `bash` 時再多一行，說明需要的是 Git for Windows 附的 Git Bash、它的 `git` 必須在 `PATH` 上，
以及 WSL 的 `bash.exe` 不被承認。Linux 的 stdout 與 stderr 和追加這個決定之前逐字相同。

表中結束碼 1 的「紀錄無法解析」只適用於 init（包含 `schema` 不認得與路徑違反規則的紀錄）。remove 遇到無效紀錄時：

| 紀錄的狀況 | remove 的結束碼 | stdout | 是否刪除檔案 |
|---|---|---|---|
| 無法解析，或 `schema` 不認得 | 0 | `Nothing was removed: …` 一行 | 否 |
| 有路徑不在 `.specify/` 或 `.claude/skills/speckit-*/` 之下 | 1 | `Nothing was removed: …` 一行；原因輸出到 stderr | 否 |

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

`missing` 行的完整格式（包含 Windows 上缺少 Git Bash 時的文字）見「必要工具的判定」的「缺少工具時的輸出」。

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

補充（維護者核可 plan 時確認）：

- (a) 「缺少工具」（結束碼 3）與「無法取得最新穩定版或官方工具執行失敗」（結束碼 4）這兩種失敗情況下，
  摘要只輸出第一行，不輸出 `Git:` 一行與兩行下一步建議。
- (b) `Git:` 一行的 `<k> paths are uncommitted` 中，k 是本次執行後導入紀錄 `entries` 內的路徑中尚未在 `HEAD` 的數量，
  不含紀錄 `.specify/sdd-init.json` 本身，也不含專案其他未提交的內容。
- (c) 紀錄 `.specify/sdd-init.json` 不輸出 `created` 行，也不計入摘要的 `<n> created`。

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

「紀錄無法解析」這一列也用於 `schema` 不認得的紀錄（結束碼 0），以及有路徑違反規則的紀錄（結束碼 1，原因另外輸出到 stderr）。

## 不變的保證

- init 不覆蓋、不修改任何既有檔案；remove 只刪除紀錄內且內容未被修改的檔案。
- 兩個指令都不 commit、不建立 repository、不切換分支。
- init 對暫存區唯一的異動是加入自己建立的 `.sh`；remove 對暫存區唯一的異動是取消其中仍未 commit 的項目。
- 不讀寫 `specs/`。
- 不安裝、不升級使用者環境中的任何工具。

## 只為測試存在的入口

測試以函式參數替換「查詢版本」與「執行官方工具」這兩步；不提供環境變數或隱藏選項來改變正式執行的行為。

必要工具的判定另有兩個可由測試替換的模組層級函式：「目前是否為 Windows」與「以指定的 `git` 執行一個查詢並取得輸出」。
替換它們加上暫存目錄內的假安裝目錄，就能在 Linux 上驗證 Windows 的各種情況；同樣不提供環境變數或隱藏選項。
