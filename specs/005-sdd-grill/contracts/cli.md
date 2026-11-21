# Contract: sdd_grill.py 的指令介面

```text
uv run <skill>/scripts/sdd_grill.py check     前置檢查、專案現況、既有進度與變更
uv run <skill>/scripts/sdd_grill.py save      從 stdin 讀入完整的進度並保存
uv run <skill>/scripts/sdd_grill.py verify    檢查產生的 constitution 與 spec
uv run <skill>/scripts/sdd_grill.py focus     把 .specify/feature.json 指向這一批新 spec 中編號最小的一份
uv run <skill>/scripts/sdd_grill.py clear     清除進度
```

`<skill>` 是 skill 的資料夾，SKILL.md 以 `${CLAUDE_SKILL_DIR}` 表示。一律在目標專案的根目錄執行，
專案根目錄就是目前目錄。沒有其他參數與選項；沒有子指令、子指令不認得或多出參數時，以結束碼 1 結束並在 stderr 顯示用法。

資料格式與判定規則見 [data-model.md](../data-model.md)；決定與理由見 [research.md](../research.md) 的 R2、R4（含「目前的功能目錄」）、R7 至 R9。

## 共通

- stdout 只有一份 JSON 物件（UTF-8、LF、縮排 2、結尾換行），鍵的順序固定；所有路徑都是相對於專案根目錄、以 `/` 分隔。
- 失敗時 JSON 有 `"error": "<一句英文>"`，同一句也寫到 stderr。
- 只讀寫目前目錄之下的檔案；**寫入與刪除只發生在 `.specify/sdd-grill/` 之內，唯一的例外是 `focus` 另外寫入 `.specify/feature.json`**。唯一的外部指令是 `git`
  （`rev-parse`，只讀），`git` 不存在時視為不是 git repository。
- Windows 與 Linux 的輸出逐位元組相同（`saved_at` 與 `head` 這類取決於當下的值除外）。

## 結束碼

| 結束碼 | 意義 |
|---|---|
| 0 | 成功（`check` 能完成檢查、`save` 已寫入、`verify` 全部通過、`focus` 已指向或本來就指向目標、`clear` 已清除或本來就沒有） |
| 1 | 用法錯誤；`save` 的輸入無效或含機密；`verify` 或 `focus` 有失敗的項目；`.specify/feature.json` 不是一般檔案；自己的資料夾有衝突 |
| 3 | Spec Kit 未導入或缺少產生文件所需的檔案（只有 `check` 會回傳） |

2 保留不用（與 001 部署工具的「衝突」區隔）；4 不使用（沒有網路操作）。

## check

只讀，不寫入任何檔案。輸出：

```json
{
  "speckit": "ok",
  "missing": [],
  "constitution": "written",
  "numbering": "sequential",
  "specs": [
    {"dir": "specs/001-deploy", "number": "001"}
  ],
  "progress": "present",
  "changed": ["head"],
  "saved": { "...": "progress.json 的完整內容" }
}
```

| 欄位 | 值 |
|---|---|
| `speckit` | `"ok"`、`"missing"`、`"incomplete"` |
| `missing` | `speckit` 為 `"incomplete"` 時缺少的必要檔案，依路徑排序；其他時候是空陣列 |
| `constitution` | `"missing"`、`"template"`、`"written"` |
| `numbering` | `"sequential"` 或 `"timestamp"` |
| `specs` | 既有 spec 的清單（`number` 可能是 `null`） |
| `progress` | `"none"`、`"present"`、`"unreadable"`（不是有效的 JSON、`schema` 或 `tool` 不符、或不符合驗證規則）、`"conflict"` |
| `changed` | `progress` 為 `"present"` 時，指紋中改變的項目；其他時候是空陣列 |
| `saved` | `progress` 為 `"present"` 時是進度的完整內容；其他時候是 `null` |

`speckit` 不是 `"ok"` 時：結束碼 3，`error` 是 `"Spec Kit is not set up in this project; run /sdd-init first."`
（`missing`）或 `"Spec Kit in this project lacks files needed to generate a constitution and specs; it may have changed incompatibly."`
（`incomplete`）。其餘欄位照常輸出。

## save

從 stdin 讀入一份進度 JSON，依 [data-model.md](../data-model.md) 的驗證規則檢查，通過時：

1. 自己的資料夾不存在就建立，並寫入固定內容的 `.gitignore`；
2. 填入 `saved_at`、`fingerprint`；`phase` 為 `"confirmed"` 而既有進度沒有 `baseline` 時記下 `baseline`，
   已有時沿用；`phase` 為 `"discussing"` 時 `baseline` 為 `null`；
3. 寫到同資料夾的暫存檔，再取代 `progress.json`。

輸出 `{"saved": ".specify/sdd-grill/progress.json", "phase": "...", "baseline": true|false}`，結束碼 0。

失敗（結束碼 1，不寫入任何檔案）：

| 情況 | `error` |
|---|---|
| stdin 不是 JSON | `progress is not valid JSON: <原因>` |
| 不符合驗證規則 | `progress is invalid at <欄位路徑>: <原因>` |
| 含機密樣式 | `progress at <欄位路徑> looks like a secret; describe what is needed instead of recording the value`（欄位名稱本身像機密時，`<欄位路徑>` 是含有該欄位的物件路徑，最上層為 `(top level)`，不重複欄位名稱） |
| 產生途中改回 `discussing` | `specs were already generated from the confirmed summary; it can no longer go back to discussing` |
| 資料夾衝突 | `.specify/sdd-grill/ holds files sdd-grill did not create; nothing was written` |

`save` 不檢查 Spec Kit 是否存在；呼叫順序由 SKILL.md 保證（先 `check`）。

## verify

只讀。前提是進度存在且 `phase` 為 `"confirmed"`，否則結束碼 1，`error` 為
`there is no confirmed summary to verify`。輸出：

```json
{
  "ok": true,
  "failures": [],
  "constitution": "written",
  "specs": [
    {"feature": "deploy", "dir": "specs/004-deploy", "depends_on": ["specs/003-sdd-init"]}
  ],
  "unexpected": []
}
```

| 欄位 | 值 |
|---|---|
| `ok` | `failures` 為空時 `true` |
| `failures` | `{"check": "<項目名稱>", "detail": "<一句英文，含相關路徑>"}`，項目名稱見 data-model 的「驗證產生的結果」 |
| `constitution` | 同 `check` |
| `specs` | 依 `features` 的順序；`depends_on` 中的功能 `id` 換成該功能的 `spec_dir`（還沒有時保留 `id`） |
| `unexpected` | 不在基準、也不屬於任何功能的新 spec 資料夾 |

`ok` 為 `false` 時結束碼 1，`error` 為 `the generated documents do not match the confirmed summary`。

## focus

把 `.specify/feature.json` 的 `feature_directory` 指向這一批新 spec 中編號最小的一份，讓維護者用原生的 `/speckit-plan`
時從第一份開始（理由與對原則 I 的判斷見 [research.md](../research.md) R4「目前的功能目錄」）。在 `verify` 通過之後、`clear` 之前執行。
前提是進度存在且 `phase` 為 `"confirmed"`，否則結束碼 1，`error` 為 `there is no confirmed summary to point at`。

步驟：

1. 執行與 `verify` 相同的全部檢查；任何一項失敗就結束碼 1、不寫入，`error` 為
   `the generated documents do not match the confirmed summary; .specify/feature.json was not changed`，`failures` 同 `verify`。
2. 目標是 `features` 第一個功能的 `spec_dir`（`verify` 的 `order` 檢查保證它是這一批編號最小的一份，也大於專案原有的所有 spec）。
3. 讀取 `.specify/feature.json` 的 `feature_directory`：檔案不存在、不是 JSON、不是物件、或沒有字串型的 `feature_directory`
   都視為沒有有效值（`previous` 為 `null`）。路徑存在但不是一般檔案時，結束碼 1、不寫入，`error` 為
   `.specify/feature.json is not a regular file; nothing was written`。
4. 值等於目標時不寫入（`changed` 為 `false`）；否則寫入 `{"feature_directory": "<目標>"}`（UTF-8、LF、縮排 2、結尾換行，
   只有這一個鍵，與 `speckit-specify` 寫的內容相同），先寫到同資料夾的暫存檔再取代。

輸出：

```json
{
  "feature_directory": "specs/004-deploy",
  "previous": "specs/006-status",
  "changed": true
}
```

| 欄位 | 值 |
|---|---|
| `feature_directory` | 目標 |
| `previous` | 執行前的有效值；沒有有效值時是 `null` |
| `changed` | 是否寫入 |

情況：

| 情況 | 結果 |
|---|---|
| 只產生一份 spec | 目標就是那一份；原本就指向它時 `changed` 為 `false` |
| 產生多份 spec | 指向編號最小的一份；執行前通常指向最後一份（`speckit-specify` 最後寫入的） |
| `feature.json` 不存在 | 建立；`previous` 為 `null` |
| 內容無法解析 | 改寫；`previous` 為 `null`（該檔案只有這一個鍵，Spec Kit 自己的寫入也是整份取代） |
| 產生文件中途失敗 | `verify` 不通過，`focus` 不寫入；檔案保持 `speckit-specify` 最後寫入的值，指向它建立的、存在的資料夾 |
| 專案已有先前的 spec | 目標是這一批的第一份，不是整個專案的第一份 |
| `verify` 不通過、進度不是 `confirmed` | 結束碼 1，不寫入 |

`focus` 不讀也不寫 `.specify/` 內的其他 Spec Kit 檔案；重複執行的結果相同（第二次起 `changed` 為 `false`）。

## clear

刪除 `.specify/sdd-grill/progress.json` 與 `.specify/sdd-grill/.gitignore`，資料夾變空時刪除資料夾。
輸出 `{"cleared": true}`（有刪除）或 `{"cleared": false}`（本來就沒有），結束碼 0。
資料夾衝突時不刪除任何檔案，結束碼 1，`error` 同 `save`。`clear` 不看進度的內容，`unreadable` 的進度也能清除。

## 以模組方式載入

測試（與日後可能的 007）以 `importlib` 載入本檔：載入時 MUST NOT 執行任何動作。下列能力 MUST 是獨立、可呼叫的函式，
資料夾名稱以參數傳入：讀寫自我忽略的資料夾、原子寫入、計算指紋、機密掃描。`main(argv)` 回傳結束碼，
可指定專案根目錄與 stdin 以便測試。
