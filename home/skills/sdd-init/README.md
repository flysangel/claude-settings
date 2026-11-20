# sdd-init

在目前的專案導入最新穩定版的 [Spec Kit](https://github.com/github/spec-kit)，或把它移除。
只由維護者手動執行，Claude 不會自行觸發。

## 用法

| 指令 | 作用 |
|---|---|
| `/sdd-init` | 導入當下最新的穩定版 Spec Kit |
| `/sdd-init remove` | 移除 `/sdd-init` 建立、且之後沒有被修改過的檔案 |

導入完成後會回報版本、建立與略過的檔案，以及下一步的兩條路：
`/sdd-grill`，或 `/speckit-constitution` 再 `/speckit-specify`。

## 前置需求

- `uv`、`git`、`bash` 都在 `PATH` 上。Windows 的 `bash` 是隨 Git for Windows 安裝的 Git Bash。
- 需要網路：向 PyPI 查詢最新穩定版，並由 `uv` 下載官方工具 `specify-cli`。
  已完整導入的專案再次執行時不會連線。

缺少工具或無法取得版本時，指令會說明原因並停止，不建立任何檔案，也不會改用其他方式安裝。

## 會做的事

- Spec Kit 的檔案全部由官方工具產生，再原樣複製到專案中**還不存在**的位置。
  已存在的檔案 MUST NOT 被覆蓋或修改，被略過的檔案會逐一列出。
- 兩個平台一律使用 `sh` 腳本（Windows 由 Git Bash 執行），所以在任一平台導入並提交的專案，
  在另一個平台 clone 後不需要重新導入。
- 導入後會多出兩個不屬於 Spec Kit 的檔案：

  | 檔案 | 用途 |
  |---|---|
  | `.specify/sdd-init.json` | 導入紀錄：版本、建立了哪些檔案與當時的內容雜湊，供移除與更新判斷 |
  | `.specify/.gitattributes` | 一行規則，讓 `.specify/scripts/bash/*.sh` 在 Windows 也維持 LF 換行 |

- 專案是 git repository 時，會把新建的 `.sh` 以 `git add --chmod=+x` 加入暫存區，
  讓執行權限記進 index；**不會 commit**，其餘檔案也不會被加入。不是 repository 時不會建立 repository。

## 不會碰的東西

- `specs/` 與專案的其他內容。
- 既有的同名檔案，包含以其他方式導入的 Spec Kit 檔案。
- 移除時，被你修改過的檔案（例如寫好的 `.specify/memory/constitution.md`）會保留並列出。
- 沒有導入紀錄，或紀錄無法辨識時，移除不會刪除任何檔案。
