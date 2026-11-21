# sdd-update

把目前專案中由 `/sdd-init` 導入的 [Spec Kit](https://github.com/github/spec-kit) 更新到當下最新的穩定版，
並保留你改過的檔案。只由維護者手動執行，Claude 不會自行觸發。

## 用法

| 指令 | 作用 |
|---|---|
| `/sdd-update` | 更新到當下最新的穩定版 Spec Kit |

沒有任何參數：一律更新到執行當下的最新穩定版，不能指定版本，也不能降版。
已是最新穩定版時只回報版本，不產生任何異動；專案的版本比最新穩定版還新時也不會降版。

完成後會回報版本變化，以及每一個被更新（`updated`）、建立（`created`）、移除（`removed`）與保留（`kept`）的檔案。

## 前置需求

- 專案已由 `/sdd-init` 導入，也就是有導入紀錄 `.specify/sdd-init.json`。沒有紀錄時會停止並請你先執行 `/sdd-init`。
- `uv`、`git`、`bash` 都在 `PATH` 上；判定方式與 `/sdd-init` 相同。Windows 的 `bash` 是隨 Git for Windows 安裝的 Git Bash。
- 需要網路：向 PyPI 查詢最新穩定版，並由 `uv` 下載官方工具 `specify-cli`。
- 這個 skill 與 `sdd-init` 一起部署，執行時使用相鄰的 `sdd-init` 資料夾內的程式（紀錄的讀寫、雜湊、版本挑選與官方工具的執行）。
  只部署 `sdd-update` 時會停止並說明。

缺少工具、無法取得版本或官方工具執行失敗時，指令會說明原因並停止，專案內不產生任何異動，也不會重試或改用其他方式取得 Spec Kit。

## 會做的事

新版的檔案全部由官方工具在專案之外的暫存目錄產生，再原樣複製到專案。逐檔的處理：

| 情況 | 處理 |
|---|---|
| 由 `/sdd-init` 或上一次更新建立、內容沒有被修改，新版內容不同 | 換成新版（`updated`） |
| 新版才有的檔案，或你刪掉的 Spec Kit 檔案 | 建立（`created`） |
| 新版不再提供、內容沒有被修改 | 刪除（`removed`），因此變空的目錄一併刪除 |
| 內容被你修改過 | 保留不動，附上新版內容的比對副本（`kept`） |
| 不是由 `/sdd-init` 建立的同名檔案 | 保留不動，附上比對副本（`kept`） |
| 新版不再提供、但內容被你修改過 | 保留不動，從紀錄移除，之後由你自行處理（`kept`） |
| 與新版內容相同 | 不寫入，也不列出 |

更新完成後，導入紀錄會改寫為新版本與新版內容的雜湊，之後的 `/sdd-update` 與 `/sdd-init remove` 都依它判斷。

## 永遠不動的內容

- `.specify/memory/`：constitution 與它的範本資訊，不論內容是否改過、新版是否不同。
- `specs/` 與專案的其他內容。

## 比對副本

- 被保留、且新版仍提供的檔案 `<原路徑>`，新版內容會寫到 `.specify/sdd-update/<原路徑>.new`，
  例如 `.specify/sdd-update/.specify/templates/plan-template.md.new`。`kept` 那一行會寫出這個路徑。
- 是否入庫由你決定：它們在 `git status` 中是未追蹤的檔案，sdd-update 不會把它們加入暫存區，也不會寫任何忽略規則。
- 合併完成後可以直接刪除比對副本或整個 `.specify/sdd-update/`。已是最新穩定版時再次執行，
  只會列出仍與比對副本不同的檔案，不會清掉比對副本。
- 下一次實際更新到新版本時，上一次的比對副本會先被自動刪除，再寫入這一次的。所以 SHOULD NOT 把自己的內容寫在比對副本裡。

## Git

- 專案是 git repository 時，新建立的 `.sh` 會以 `git add --chmod=+x` 加入暫存區，讓執行權限記進 index；
  **不會 commit**。被換成新版的檔案與其他異動都留在工作目錄，由你以 `git status` 檢視後提交。
- 已在 index 的項目不會被改寫，所以既有 `.sh` 的執行權限維持不變。
- 不是 repository 時不會建立 repository。
