# Data Model: sdd-grill

本功能只有一份持久的資料：目標專案中的進度檔。其餘的實體（需求描述、決定、決策摘要、功能清單）
都是進度檔的一部分，或由它推導。決定與理由見 [research.md](./research.md) 的 R2、R4、R8。

## 自己的資料夾：`.specify/sdd-grill/`

| 檔案 | 建立者 | 內容 |
|---|---|---|
| `.specify/sdd-grill/.gitignore` | `sdd_grill.py save`（第一次寫入時） | 固定的兩行：`# Created by sdd-grill. Local discussion progress; never committed.` 與 `*` |
| `.specify/sdd-grill/progress.json` | `sdd_grill.py save` | 進度，見下 |

規則：

- sdd-grill 只在這個資料夾寫檔，這個資料夾也只放上表兩個檔案。唯一的例外是 `focus`：它另外寫入 Spec Kit 的
  `.specify/feature.json`（見下「目前的功能目錄」），那個檔案不是 sdd-grill 建立的，也不放進這個資料夾。
- **衝突**：資料夾存在，且 (a) `.gitignore` 存在但內容（換行正規化後）不是上面的固定內容，或
  (b) 有上表以外的檔案或子資料夾。此時 `save` 與 `clear` 都不寫入、不刪除，以結束碼 1 回報；
  `check` 回報 `progress: "conflict"`。
- `clear` 刪除 `progress.json` 與 `.gitignore`，資料夾變空時一併刪除；不存在的檔案視為已刪除。
  衝突時什麼都不刪。
- 不登記在 `.specify/sdd-init.json`（R2）。

## 進度（`progress.json`）

UTF-8、LF、縮排 2、結尾換行的 JSON 物件。由 Claude 組成、經 stdin 交給 `save`；標示「腳本」的欄位由腳本寫入，
Claude 送來的值會被忽略。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schema` | 整數 | 固定為 `1` |
| `tool` | 字串 | 固定為 `"sdd-grill"` |
| `requirement` | 字串 | 維護者的需求描述（原文），非空 |
| `language` | 字串或 `null` | 產生文件的語言，例如 `"zh-TW"`；尚未判斷時為 `null`（FR-020） |
| `phase` | 字串 | `"discussing"` 或 `"confirmed"`（維護者已確認摘要） |
| `stage` | 字串 | 目前進行到哪一段：`"principles"`、`"features"`（列出功能與相依）、`"feature"`（逐一討論功能）、`"summary"`（FR-007） |
| `current_feature` | 字串或 `null` | `stage` 為 `"feature"` 時是正在討論的功能 `id`，其他時候是 `null` |
| `constitution` | 物件 | 見「constitution」 |
| `features` | 陣列 | 依施工順序排列的功能，見「功能」 |
| `deferred` | 陣列 | 已延後的事項：`{ "item": 字串, "reason": 字串, "feature": 功能 id 或 null }` |
| `for_plan` | 陣列 | 留給 plan 的技術選型：`{ "item": 字串, "feature": 功能 id 或 null }`（FR-008） |
| `saved_at` | 字串 | 腳本：最後一次保存的 UTC 時間，ISO 8601，到秒 |
| `fingerprint` | 物件 | 腳本：保存當下的專案指紋，見「指紋」 |
| `baseline` | 物件或 `null` | 腳本：第一次以 `phase: "confirmed"` 保存時記下，之後不變；`discussing` 時為 `null` |

`feature` 為 `null` 的延後事項與留給 plan 的事項屬於整個專案（例如 constitution 層級）。

### constitution

| 欄位 | 型別 | 說明 |
|---|---|---|
| `action` | 字串 | `"create"`（沒有 constitution 或仍是空白範本）、`"amend"`（維護者同意修訂既有的）、`"keep"`（不動） |
| `principles` | 陣列 | 已決定的原則：`{ "title": 字串, "rules": [字串, …], "rationale": 字串或 null }` |
| `governance` | 陣列 | 已決定的治理規則，字串 |

`action` 為 `"keep"` 時 `principles` 與 `governance` 可以是空陣列（既有原則留在 constitution 本身，不複製到進度）。
`"amend"` 時 `principles` 與 `governance` 只列出要新增或修改的部分。

### 功能

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | 字串 | 功能的短名，符合 `^[a-z0-9]+(-[a-z0-9]+)*$`，在 `features` 中唯一 |
| `title` | 字串 | 一句話的名稱 |
| `depends_on` | 陣列 | 依賴的功能：`features` 中**排在它前面**的 `id`，或既有 spec 的資料夾路徑（例如 `"specs/003-sdd-init"`） |
| `status` | 字串 | `"pending"`、`"discussing"`、`"decided"` |
| `decisions` | 陣列 | 已決定的事項：`{ "topic": 字串, "decision": 字串 }`（使用情境、範圍、邊界情況等） |
| `spec_dir` | 字串或 `null` | 產生後由 Claude 填入 `speckit-specify` 回報的資料夾（`specs/<名稱>`），之前為 `null` |

`features` 的順序就是施工順序與 spec 的產生順序；「`depends_on` 只能指向前面的功能」同時保證沒有循環，
也保證依序產生時被依賴的功能編號較小（FR-015）。

### 驗證規則（`save`）

違反任何一條時不寫入，以結束碼 1 回報第一個錯誤的欄位路徑：

1. 是 JSON 物件，只有上表列出的欄位，型別正確；字串欄位非空（可為 `null` 的除外）。
2. `schema` 是 `1`、`tool` 是 `"sdd-grill"`。
3. `stage` 為 `"feature"` 時 `current_feature` 是存在的 `id`；其他時候是 `null`。
4. 功能的 `id` 唯一且符合樣式；`depends_on` 只指向前面的 `id`，或 `specs/` 之下實際存在且含 `spec.md` 的資料夾。
5. `deferred`、`for_plan` 的 `feature` 是 `null` 或存在的 `id`。
6. `phase` 為 `"confirmed"` 時：`stage` 是 `"summary"`，每個功能的 `status` 都是 `"decided"`，`language` 不是 `null`。
7. `spec_dir` 只有在 `phase` 為 `"confirmed"` 時可以不是 `null`；值必須是 `specs/` 之下的一層資料夾的相對路徑（`/` 分隔）。
8. 已經 `confirmed` 且有任何 `spec_dir` 的進度，不能再改回 `"discussing"`（產生途中不能改決定，要先處理已產生的文件）。
9. 沒有任何字串值符合機密樣式（R8）；錯誤訊息只指出欄位路徑，不印出值。

## 指紋（`fingerprint`）

| 欄位 | 值 |
|---|---|
| `constitution` | `.specify/memory/constitution.md` 換行正規化（CRLF、CR 轉 LF）後的 SHA-256 十六進位；不存在為 `null` |
| `specs` | 物件：`specs/` 下每個含 `spec.md` 的一層資料夾，鍵為 `specs/<名稱>/spec.md`，值為同樣方式的 SHA-256 |
| `head` | 專案是 git repository 且有 commit 時為 `git rev-parse HEAD` 的結果；不是、沒有 commit 或沒有 `git` 時為 `null` |

`check` 重新計算並與 `progress.json` 的 `fingerprint` 逐項比較，`changed` 依固定順序列出不同的項目名稱
（`constitution`、`specs`、`head`）。

## 基準（`baseline`）

第一次以 `phase: "confirmed"` 保存時，從當下的專案記下：

| 欄位 | 值 |
|---|---|
| `constitution` | 同指紋的 `constitution` |
| `specs` | 同指紋的 `specs` |

之後的 `save` 保留原值，不論 Claude 送來什麼。`verify` 以它判斷既有文件有沒有被動到。

## 專案現況（`check` 輸出的一部分）

| 項目 | 判定 |
|---|---|
| Spec Kit | `"missing"`：沒有 `.specify/` 資料夾；`"incomplete"`：有 `.specify/`，但 [research.md](./research.md) R4 列出的必要檔案有缺；其餘為 `"ok"` |
| constitution | `"missing"`：不存在；`"template"`：與 `.specify/templates/constitution-template.md` 換行正規化後相同，或含有 `[PROJECT_NAME]` 或 `[PRINCIPLE_1_NAME]`；其餘為 `"written"` |
| 既有 spec | `specs/` 下每個含 `spec.md` 的一層資料夾，依名稱排序；附編號：名稱以 `\d{3,}-` 開頭時為該數字，以 `\d{8}-\d{6}-` 開頭時為該時間戳記字串，其他為 `null` |
| 編號方式 | `.specify/init-options.json` 的 `feature_numbering`，其次 `branch_numbering`；都沒有或無法讀取時為 `"sequential"` |

## 驗證產生的結果（`verify`）

前提：進度存在、`phase` 為 `"confirmed"`。逐項檢查，全部列出（不在第一個失敗時停止）：

| 檢查 | 失敗的項目名稱 |
|---|---|
| `baseline.specs` 的每一份 spec.md 仍存在，雜湊相同 | `existing-spec-changed` |
| `constitution.action` 為 `"keep"` 時，constitution 的雜湊等於 `baseline.constitution` | `constitution-changed` |
| `constitution.action` 為 `"create"` 時，constitution 存在且不再是空白範本；為 `"amend"` 時，constitution 存在且雜湊不等於 `baseline.constitution` | `constitution-not-written` |
| 每個功能都有 `spec_dir`，其 `spec.md` 存在 | `spec-missing` |
| 每個 `spec_dir` 都不在 `baseline.specs` 中，且彼此不同 | `spec-not-new` |
| 依 `features` 的順序，`spec_dir` 的編號嚴格遞增，且全部大於 `baseline` 中最大的編號 | `order` |
| 每個功能的 `depends_on` 所指的 spec 編號都比它小 | `dependency-order` |

另外列出 `unexpected`：`specs/` 下含 `spec.md`、不在 `baseline` 中、也不是任何功能的 `spec_dir` 的資料夾。
它不算失敗（可能是維護者自己加的），但會被回報。

編號比較：`sequential` 取整數比較，`timestamp` 取字串比較；無法取得編號的 `spec_dir` 記為 `order` 失敗。

## 目前的功能目錄（`focus`）

不是 sdd-grill 的資料，而是 Spec Kit 的本機狀態 `.specify/feature.json`（Spec Kit 的 `.specify/.gitignore` 已列為不入庫）。
格式是 Spec Kit 定義的：`{"feature_directory": "<相對於專案根目錄、以 / 分隔的 spec 資料夾>"}`，只有這一個鍵。

| 項目 | 規則 |
|---|---|
| 目標 | `features` 第一個功能的 `spec_dir`；`verify` 的 `order` 檢查保證它是這一批新 spec 中編號最小的，且大於 `baseline` 中最大的編號 |
| 有效值 | 檔案是 JSON 物件、有字串型的 `feature_directory`；其他情況（不存在、無法解析、型別不符）都是「沒有有效值」 |
| 寫入條件 | `verify` 的全部檢查通過，且有效值不等於目標；內容整份取代，原子寫入 |
| 不寫入 | 任何 `verify` 檢查失敗、進度不是 `confirmed`、檔案存在但不是一般檔案 |

## 狀態轉移

```text
（沒有進度）
   │ save（phase: discussing）
   ▼
discussing ──save──▶ discussing          每個決定之後
   │  │
   │  └─clear──▶（沒有進度）              維護者選擇重新開始
   │ save（phase: confirmed）             維護者確認摘要；記下 baseline
   ▼
confirmed ──save──▶ confirmed            每產生一份文件就填入 spec_dir
   │  │
   │  └─save（phase: discussing）         只在還沒有任何 spec_dir 時允許（確認後又要改摘要）
   │ verify 通過
   ▼
focus（寫 .specify/feature.json；失敗時停在 confirmed）
   │
   ▼
clear ──▶（沒有進度）
```

中途結束、產生失敗、`verify` 或 `focus` 不通過：停在目前的狀態，進度保留（FR-018）。
