# Data Model: sdd-init 導入 Spec Kit

所有路徑都相對於專案根目錄，一律以 `/` 分隔，兩個平台相同。
專案根目錄：目前目錄位於 git 工作目錄內時是它的最上層，否則是目前目錄。

## 導入紀錄（Record）

位置：`.specify/sdd-init.json`。由 sdd-init 建立與刪除，004 sdd-update 會讀取並更新它。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schema` | integer | 格式版本，目前為 1 |
| `status` | `"applying"` \| `"complete"` | 上一次導入是否完整結束 |
| `speckit_version` | string | 導入的 Spec Kit 版本，例如 `1.4.3` |
| `init_options` | object | 傳給官方工具的選項：`{"integration": "claude", "script": "sh"}` |
| `entries` | array | 每個由 sdd-init 建立的檔案一筆，依 `path` 排序 |
| `entries[].path` | string | 檔案的相對路徑 |
| `entries[].sha256` | string | 建立時的內容雜湊（見「內容識別資訊」） |
| `entries[].origin` | `"speckit"` \| `"sdd-init"` \| `"sdd-update"` | 內容來自官方工具的產出、sdd-init 自己的檔案，或是 004 sdd-update 建立的比對副本 |
| `entries[].staged_executable` | boolean | sdd-init 是否曾以 `git add --chmod=+x` 成功把它加入暫存區；false 的 `.sh` 在之後的導入可能被補登（見「導入的動作」） |
| `created_dirs` | array of string | 由 sdd-init 建立的目錄，移除時若為空就刪除 |

規則：

- 紀錄本身不列在 `entries` 內；它存在就代表由 sdd-init 建立。
- MUST NOT 含有絕對路徑、時間戳、使用者名稱、信箱或任何機密。
- `entries[].path` MUST 位於 `.specify/` 或 `.claude/skills/speckit-*/` 之下；不符合的紀錄視為無效。
- 被略過的既有檔案 MUST NOT 出現在 `entries`。
- `status` 為 `applying` 時，`entries` 是本次要達成的目標；再次執行時據此補齊。
- `origin` 為 `sdd-update` 的項目（004 的比對副本），`path` MUST 位於 `.specify/sdd-update/` 之下且以 `.new` 結尾，
  `staged_executable` MUST 為 false；其他 `origin` 的項目 MUST NOT 位於 `.specify/sdd-update/` 之下。不符合的紀錄視為無效
  （與 `schema` 不認得相同）。見 [004 的 data-model.md](../004-sdd-update/data-model.md) 的「對 003 格式的變更」。
- 檔案無法解析、`schema` 不是認得的值，或違反上面的路徑規則：導入時停止（結束碼 1），移除時不刪除任何檔案。
- 以 UTF-8、LF 換行、鍵值順序固定的格式寫入，使兩個平台產生的檔案位元組相同。

## 內容識別資訊

檔案內容把每個 CRLF 換成 LF 之後的 SHA-256（十六進位小寫）。

- 判斷「未被修改」：目前檔案以同樣方式計算的雜湊等於紀錄內的值。
- 換行被 git 轉換不算修改；其他任何位元組的差異都算。

## Spec Kit 檔案

官方工具以 `--integration claude --script sh` 產生的全部檔案，`origin` 為 `speckit`。以 1.4.3 為例共 30 個：

| 位置 | 內容 |
|---|---|
| `.claude/skills/speckit-*/SKILL.md` | 9 個 skill |
| `.specify/scripts/bash/` | 6 支 `.sh` 與 1 支輔助用的 `.py` |
| `.specify/templates/` | 5 份範本 |
| `.specify/memory/` | `constitution.md` 與它的範本資訊 |
| `.specify/integrations/`、`.specify/workflows/` | 官方的安裝清單與 workflow |
| `.specify/init-options.json`、`.specify/integration.json`、`.specify/.gitignore` | 官方的設定 |

實際清單以執行當下的官方產出為準，sdd-init 不內建這份清單。內容以位元組原樣複製，不做任何轉換。

## sdd-init 自己的檔案

| 路徑 | 內容 | 是否列在 `entries` |
|---|---|---|
| `.specify/sdd-init.json` | 導入紀錄 | 否 |
| `.specify/.gitattributes` | 固定一行：`scripts/bash/*.sh text eol=lf`（LF 結尾） | 是，`origin` 為 `sdd-init` |

`.specify/.gitattributes` 已存在且不在紀錄內時，視為別人的檔案：不覆蓋、不修改、不列入 `entries`。

## 暫存產出（Staging）

官方工具在專案之外的暫存空目錄產生的檔案樹。只存在於一次執行期間，結束時（包含失敗）刪除。

## 導入的動作

規劃階段的輸出，只存在於記憶體。暫存產出的每個檔案，加上 `.specify/.gitattributes`，各一個動作：

| 動作 | 條件 | 處理 |
|---|---|---|
| `create` | 目標不存在 | 複製到專案，列入 `entries` |
| `keep` | 目標存在，且在紀錄內 | 不寫入，保留紀錄內原有的那一筆 |
| `skip` | 目標存在，且不在紀錄內 | 不寫入，不列入 `entries`，在回報中列出 |

動作為 `create` 且副檔名是 `.sh` 的檔案，在專案是 git repository 時再執行 `git add --chmod=+x`，
並把 `staged_executable` 設為 true。

補登執行權限：動作為 `keep` 且副檔名是 `.sh` 的檔案，若 `origin` 為 `speckit`、`staged_executable` 為 false、
檔案存在，且不在 index 也不在 `HEAD`，在專案是 git repository 時同樣執行 `git add --chmod=+x`，並把 `staged_executable` 設為 true。
這涵蓋上一次複製途中失敗、上一次 `git add --chmod=+x` 失敗，以及導入時還不是 git repository 的專案。
已在 index 或 `HEAD` 的檔案不動。`git add --chmod=+x` 失敗時 `staged_executable` 維持 false，下一次導入再重試。
輸出與摘要見 [contracts/cli.md](./contracts/cli.md) 的「補登執行權限」。

狀態轉移：

```text
（沒有紀錄）──規劃──▶ 寫入 status=applying 的紀錄 ──複製檔案、加入暫存區──▶ status=complete
status=applying 或缺少檔案 ──以紀錄內的版本重新規劃──▶ 補齊 ──▶ status=complete
status=complete 且檔案齊全，沒有待補登的 .sh ──▶ 不做任何事
status=complete 且檔案齊全，有待補登的 .sh ──▶ 只補登執行權限（不連線、不執行官方工具、不複製檔案）──▶ status=complete
```

「檔案齊全」指紀錄內 `origin` 不是 `sdd-update` 的檔案都存在：比對副本可以隨時被維護者刪除，
不存在時不算缺少，也不會為它們重新執行官方工具。

「待補登的 `.sh`」就是上面「補登執行權限」所列條件的檔案；專案不是 git repository 時沒有這種檔案。
只補登時沒有規劃階段的動作：直接由紀錄判定，寫入的只有 index 與紀錄內的 `staged_executable`。

取得版本、執行官方工具與規劃都在第一次寫入之前；這些步驟失敗時專案內沒有任何異動。

## 移除的動作

紀錄內的每一筆各一個動作：

| 動作 | 條件 | 處理 |
|---|---|---|
| `delete` | 檔案存在，雜湊等於紀錄 | 刪除；若 `staged_executable` 為 true、仍在 index 且不在 `HEAD`，再從 index 取消 |
| `keep-modified` | 檔案存在，雜湊不等於紀錄 | 保留，在回報中列出 |
| `gone` | 檔案已不存在 | 不處理 |

之後由深到淺刪除 `created_dirs` 中已經變空的目錄，最後刪除紀錄。
不在紀錄內的檔案（包含 `specs/`、之後由 Spec Kit 流程產生的檔案、導入時被略過的檔案）一律不碰。
