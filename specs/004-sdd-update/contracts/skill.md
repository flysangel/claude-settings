# Contract: sdd-update skill 的結構

部署來源是 `home/skills/sdd-update/`，安裝後位於 `~/.claude/skills/sdd-update/`。
`tests/unit/test_sdd_update_skill.py` 依此檢查。

## 檔案

| 檔案 | 語言 | 內容 |
|---|---|---|
| `SKILL.md` | 英文 | 給 Claude 的指示 |
| `README.md` | 繁體中文 | 給維護者的簡述 |
| `scripts/sdd_update.py` | 英文（訊息與註解） | 更新的判斷邏輯，介面見 [cli.md](./cli.md) |

資料夾內沒有其他檔案。

## SKILL.md

frontmatter：

| 欄位 | 值 |
|---|---|
| `name` | `sdd-update` |
| `description` | 一句英文，說明用途是把目前專案的 Spec Kit 更新到最新穩定版 |
| `disable-model-invocation` | `true`（只由維護者以 `/sdd-update` 執行） |

沒有 `argument-hint`：這個 skill 不接受參數。

內文 MUST 指示 Claude：

1. 執行 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_update.py"`，不加任何參數；維護者輸入了參數時說明這個 skill 不接受參數
   （不能指定版本或降版），不執行任何指令。
2. 在目前專案的目錄執行，只執行一次。
3. 把腳本的輸出完整回報給維護者，不省略任何一筆路徑：版本變化、每一行 `updated`、`created`、`removed`、`kept`、
   `staged`、`warning`、`Git:` 一行與 `Next:` 一行；`kept` 的檔案要連同比對副本的路徑一起回報。
4. 結束碼不是 0 時回報原因與處理方式後停止：MUST NOT 重試、MUST NOT 改用其他方式更新 Spec Kit
   （包含自行執行 `specify`）、MUST NOT 手動建立或修改 `.specify/` 與 `speckit-*` 的檔案。`uv` 指令不存在時同樣處理。
   腳本要求先執行 `/sdd-init` 時，請維護者執行它，MUST NOT 自行執行。
5. MUST NOT 自行合併被保留的檔案，MUST NOT 修改或刪除 `.specify/sdd-update/` 下的比對副本；
   只有維護者之後明確要求時才協助比對或合併。
6. MUST NOT commit、push 或修改腳本沒有更動的檔案。

內文 MUST NOT 含有中日韓文字、絕對路徑、信箱。

## README.md

MUST 以繁體中文撰寫，並包含：

- 用法：`/sdd-update`，沒有參數；一律更新到最新穩定版，不能指定版本或降版。
- 前置需求：專案已由 `/sdd-init` 導入；`uv`、`git`、`bash`（Windows 的 `bash` 是隨 Git for Windows 安裝的 Git Bash）；
  需要網路。這個 skill 與 `sdd-init` 一起部署，執行時使用 `sdd-init` 資料夾內的程式。
- 哪些檔案會被更新、建立、移除，哪些會被保留（被修改過的、不是由 sdd-init 建立的）。
- 永遠不動的內容：`.specify/memory/`（constitution）與 `specs/`。
- 比對副本：位置 `.specify/sdd-update/<原路徑>.new`、是否入庫由維護者決定、合併後可以直接刪除、
  下一次更新時會被自動清掉、不要把自己的內容寫在裡面。
- 專案是 git repository 時，新建立的 `.sh` 會被加入暫存區但不 commit；其餘的異動留在工作目錄，由維護者檢視後提交。

## scripts/sdd_update.py

- 開頭有 uv 的 inline metadata：`requires-python = ">=3.11"`，`dependencies` 為空。
- 只使用 Python 標準函式庫；外部指令只有 `uv`、`git`。
- 共用的程式從相鄰的 skill 載入：`<本檔>/../../../sdd-init/scripts/sdd_init.py`
  （在 repo 內是 `home/skills/sdd-init/scripts/sdd_init.py`，安裝後是 `~/.claude/skills/sdd-init/scripts/sdd_init.py`）。
  MUST NOT 複製 `sdd_init.py` 的內容；MUST NOT 自行實作紀錄的讀寫、雜湊、版本挑選與必要工具的判定。
- 可被測試以模組方式載入，載入時不執行任何動作（包含不載入 `sdd_init.py` 以外的任何東西、不連線）。

## 對 sdd-init skill 的變更

本功能為了共用而修改 `home/skills/sdd-init/scripts/sdd_init.py`，範圍限於
[data-model.md](../data-model.md) 的「對 003 格式的變更」與 [research.md](../research.md) 的 R6 所列的三項。
sdd-init 的 SKILL.md、README.md、指令介面、結束碼與既有情境的輸出都不變；
[003 的 contracts/skill.md](../../003-sdd-init/contracts/skill.md) 的「資料夾內沒有其他檔案」仍然成立。
003 的設計文件中受影響的敘述（`origin` 的值、「已完整導入」的條件）在實作時一併更新。
