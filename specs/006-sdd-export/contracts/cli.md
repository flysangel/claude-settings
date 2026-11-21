# Contract: sdd_export.py 的指令介面

```text
uv run <skill>/scripts/sdd_export.py check    [--project <dir>]                 專案現況、專用目錄、世代、讀取範圍摘要
uv run <skill>/scripts/sdd_export.py files    [--project <dir>] [--scope <path>]...  可讀取的檔案清單與機密位置
uv run <skill>/scripts/sdd_export.py validate [--project <dir>]                 從 stdin 讀入草稿，驗證並輸出差異
uv run <skill>/scripts/sdd_export.py write    [--project <dir>] --expect <state>  從 stdin 讀入確認後的草稿並寫入養分
```

`<skill>` 是 skill 的資料夾，SKILL.md 以 `${CLAUDE_SKILL_DIR}` 表示。`--project` 預設為目前目錄（SKILL.md 不使用它；
它讓 007 可以對另一個專案呼叫，見 [research.md](../research.md) R11）。子指令不認得、缺少必要選項或多出參數時，
結束碼 1，stderr 顯示用法。

資料格式與判定規則見 [data-model.md](../data-model.md)；決定與理由見 [research.md](../research.md)。

## 共通

- stdout 只有一份 JSON 物件（UTF-8、LF、縮排 2、`ensure_ascii=False`、結尾換行），鍵的順序固定；
  所有路徑都相對於專案根目錄、以 `/` 分隔。
- 失敗時 JSON 有 `"error": "<一句英文>"` 與 `"reason": "<列舉值>"`，同一句 `error` 也寫到 stderr。
- **`check`、`files`、`validate` 不寫入任何檔案**（專案內外皆然）。**`write` 只寫 `.sdd-export/` 內的
  `nutrients.json`、`README.md`、`.gitattributes` 與同目錄的暫存檔**，從不刪除專案的任何檔案。
- 唯一的外部指令是 `git`，只用 `rev-parse`、`ls-files`、`cat-file -e`，一律帶 `--no-optional-locks`；
  `git` 不存在或專案不是 git repository 時照常運作（以走訪目錄樹取代 `ls-files`，`commit:` 依據視為不存在）。
- 腳本不開啟機密檔案（[data-model.md](../data-model.md)「機密檔案」），只以路徑判斷。
- 不接受從檔案讀入草稿；草稿只從 stdin 讀入。
- Windows 與 Linux 的輸出逐位元組相同（`exported_at` 這類取決於當下的值除外）。

## 結束碼與 `reason`

| 結束碼 | 意義 | `reason` |
|---|---|---|
| 0 | 成功（`validate` 為 `ok: true`） | 沒有 |
| 1 | 用法錯誤 | `usage` |
| 1 | 草稿無效（含世代規則） | `invalid` |
| 1 | 草稿含機密樣式或依據指向機密檔案 | `secret`（同時也有其他錯誤時仍是 `secret`，讓 Claude 優先處理） |
| 1 | `write` 時專用目錄的內容與 `--expect` 不同 | `changed` |
| 1 | `write` 時無法寫入（權限、唯讀、磁碟） | `os-error` |
| 3 | 專用目錄衝突 | `conflict` |
| 3 | 既有養分無法讀取、不符合結構、版本較新 | `nutrients-unreadable`、`nutrients-invalid`、`nutrients-newer` |
| 3 | 世代紀錄無法讀取、不符合結構、版本較新、`tool` 不符 | `lineage-unreadable`、`lineage-invalid`、`lineage-newer`、`lineage-conflict` |
| 3 | `--project` 不存在或不是目錄 | `project` |

2 保留不用（與 001 部署工具的「衝突」區隔）；4 不使用（沒有網路操作）。
結束碼 3 由 `check`、`files`、`validate`、`write` 共同使用：四個指令都先做同樣的專案狀態檢查。

## check

只讀。輸出：

```json
{
  "project": "my-tool",
  "git": true,
  "writable": true,
  "export_dir": "ours",
  "nutrients": "unchanged",
  "view": "current",
  "gitattributes": "ok",
  "state": "<64 hex>",
  "lineage": "present",
  "generation": 2,
  "existing_generation": 2,
  "constitution": ".specify/memory/constitution.md",
  "specs": [
    {"dir": "specs/001-deploy", "spec": "specs/001-deploy/spec.md", "in_lineage": true}
  ],
  "lineage_missing_specs": [],
  "inventory": {
    "files": 214,
    "bytes": 1830211,
    "too_large": false,
    "ignore_source": "git",
    "areas": [
      {"path": "src", "files": 120, "bytes": 1200000, "manifests": []},
      {"path": ".", "files": 6, "bytes": 20000, "manifests": ["pyproject.toml"]}
    ],
    "skipped": {"ignored": 3, "dependency": 0, "build": 12, "tooling": 40, "generated": 1, "secret": 1, "binary": 4, "large": 0},
    "secret_files": [".env"]
  },
  "existing": { "...": "nutrients.json 的完整內容（export_dir 為 ours 時），否則 null" },
  "lineage_content": { "...": "lineage.json 的完整內容（lineage 為 present 時），否則 null" }
}
```

| 欄位 | 值 |
|---|---|
| `project` | 專案根目錄的名稱（建議的 `project` 值） |
| `git` | 是否為 git repository |
| `writable` | 依 `os.access` 推測能否在專案根目錄（或既有的 `.sdd-export/`）寫入；只是提示，實際以 `write` 為準 |
| `export_dir` | `"none"`、`"empty"`、`"ours"`、`"conflict"`、`"unreadable"`、`"newer"`、`"invalid"` |
| `nutrients`、`view` | 見 data-model「手動編輯的偵測」 |
| `gitattributes` | `"ok"`、`"missing"`、`"edited"`；目錄不存在時 `"missing"` |
| `state` | 見 data-model「`state`」 |
| `lineage` | `"none"`、`"present"`、`"unreadable"`、`"newer"`、`"invalid"`、`"conflict"` |
| `generation` | 這一代的世代：`lineage` 為 `present` 時是紀錄的 `generation`，`none` 時是 1；其他時候 `null` |
| `existing_generation` | 既有養分的 `generation`；沒有時 `null` |
| `constitution` | `.specify/memory/constitution.md` 存在時是該路徑，否則 `null`（不檢查其他 Spec Kit 檔案） |
| `specs` | `specs/*/spec.md` 存在的資料夾，依名稱排序；`in_lineage` 表示世代紀錄中有功能的 `spec_dir` 指向它 |
| `lineage_missing_specs` | 世代紀錄中 `spec_dir` 已不存在的功能：`[{"id": ..., "spec_dir": ...}]` |
| `inventory` | 見 data-model「讀取範圍」；不列出個別的可讀檔案。`ignore_source` 是 `"git"`（以 `git ls-files` 取得清單）或 `"none"`（不是 git repository 或沒有 `git`，走訪目錄樹） |
| `existing`、`lineage_content` | 見上 |

狀態不能匯出時（結束碼 3），仍輸出上述欄位中已能判定的部分，不能判定的為 `null`；另外有 `error`、`reason`，
`export_dir` 為 `"invalid"` 或 `lineage` 為 `"invalid"` 時另有 `errors`（同 `validate` 的格式）。
`error` 的例子：`.sdd-export/ holds files sdd-export did not create; nothing was read or written`。

`reason` 為 `conflict` 時另有 `conflicts`：不是本功能產生的路徑（相對於專案根目錄），讓 SKILL.md 能列給維護者看——
路徑本身是檔案時是 `[".sdd-export"]`；目錄內有表外的項目時是那些項目；沒有 `nutrients.json` 卻有其他檔案時是那些檔案；
`nutrients.json` 的 `tool` 不符時是 `[".sdd-export/nutrients.json"]`。衝突時不讀取專案，`lineage` 以後的欄位都是 `null`；
既有養分無法使用（`nutrients-*`）或世代紀錄無法使用（`lineage-*`）時 `inventory` 為 `null`（不掃描專案）。
`files`、`validate`、`write` 在結束碼 3 時輸出 `error`、`reason`，以及同樣條件下的 `conflicts` 或 `errors`。

既有養分（`export_dir`）的驗證只看內容本身（欄位、`id`、範圍、程式碼區塊、相依、`confirmed` 要有依據、依據與路徑的格式），
不檢查依據的檔案是否仍存在、也不做機密掃描：匯出之後專案的檔案本來就會變動，這些在下一次 `validate` 時才對照目前的專案檢查。

## files

只讀。不帶 `--scope` 時範圍是整個專案；帶 `--scope` 時只包含這些路徑（目錄或檔案，可重複）之下的可讀檔案，
另外**一律**包含 `.specify/memory/constitution.md` 與 `specs/*/spec.md`（存在時），因為它們是 FR-005 的來源。
`--scope` 的路徑不存在、在專案外或屬於排除範圍時，結束碼 1，`reason` 為 `usage`。

輸出：

```json
{
  "scope": ["src/api"],
  "too_large": false,
  "files": [
    {"path": "src/api/routes.py", "bytes": 4210}
  ],
  "secret_hits": [
    {"path": "src/api/settings.py", "line": 12}
  ],
  "skipped": {"ignored": 0, "dependency": 0, "build": 2, "tooling": 0, "generated": 0, "secret": 1, "binary": 0, "large": 0},
  "secret_files": ["src/api/.env"]
}
```

| 欄位 | 值 |
|---|---|
| `scope` | 依路徑排序；沒有範圍時是空陣列 |
| `too_large` | 這個範圍是否仍過大（門檻同 `check`） |
| `files` | 可讀檔案，依路徑排序；`too_large` 為 `true` 時是空陣列（必須先縮小範圍） |
| `secret_hits` | `files` 中符合機密樣式的行（只有路徑與行號，不含內容）；`too_large` 時是空陣列 |
| `skipped`、`secret_files` | 這個範圍內被排除的數量與機密檔案的路徑 |

## validate

只讀。從 stdin 讀入草稿（[data-model.md](../data-model.md)「草稿」），依「驗證規則」與「世代規則」檢查，並對照既有養分計算差異。

```json
{
  "ok": false,
  "errors": [
    {"check": "unsupported", "path": "features[1].requirements[0]", "detail": "a confirmed item needs at least one piece of evidence; mark it pending or add evidence"},
    {"check": "lineage-item-missing", "path": "lessons", "detail": "lesson 'atomic-write' from the lineage is neither kept, derived from, nor discarded"}
  ],
  "counts": {"principles": 1, "features": 2, "requirements": 2, "lessons": 1, "discarded": 1, "pending": 1, "inherited": 3, "new": 2},
  "diff": {
    "base": "nutrients",
    "generation": null,
    "scope": null,
    "added": [{"section": "features", "id": "status-report", "title": "部署狀態報告"}],
    "removed": [],
    "changed": [{"section": "requirements", "id": "deploy-no-overwrite", "fields": [{"field": "text", "from": "…", "to": "…"}]}],
    "order_changed": false
  }
}
```

| 欄位 | 值 |
|---|---|
| `ok` | `errors` 為空時 `true` |
| `errors` | `check` 名稱見 data-model；`path` 是欄位路徑；`detail` 是一句英文，**不含**被判為機密的值 |
| `counts` | 各區段的數量；`pending` 是待確認的項目數；`inherited` 是 `origin` 小於 `generation` 的有效項目數，`new` 是等於的 |
| `diff` | 見 data-model「差異」；草稿無法解析、有 `field` 錯誤，或有 `secret` 錯誤（差異會重複草稿的文字）時為 `null` |

`ok` 為 `false` 時結束碼 1，`reason` 為 `invalid` 或 `secret`，`error` 為 `the draft is not valid nutrients`
（或 `the draft looks like it contains a secret; describe what is needed instead of recording the value`）。

## write

從 stdin 讀入確認後的草稿。步驟：

1. 專案狀態檢查（同 `check`）；結束碼 3 的情況照樣回報，不寫入。
2. 目前的 `state` 不等於 `--expect` 時，結束碼 1、`reason: "changed"`，不寫入。
   `error`：`.sdd-export/ changed since it was checked; check again and confirm the differences before writing`。
3. 執行 `validate` 的全部檢查；不通過時同 `validate` 的失敗，不寫入。
4. 填入 `tool`、`schema`、`exported_at`，依 data-model 的順序序列化成 `nutrients.json`，並從它產生 `README.md`（含標記）。
5. `.sdd-export/` 不存在時建立（記下「本次建立」）。
6. 兩個檔案各自先寫到同目錄的暫存檔（`.nutrients.json.tmp-<隨機>`、`.README.md.tmp-<隨機>`），全部寫好後依序以
   `os.replace` 取代 `nutrients.json`，再取代 `README.md`。最後，`.gitattributes` 不存在時同樣以暫存檔寫入固定內容，存在時不動。
   `.gitattributes` 放在最後，是為了讓前面任何一步失敗時，本次建立的目錄裡不會留下檔案而能被移除（腳本不刪除自己以外的檔案，
   也不刪除已寫好的 `.gitattributes`）。
7. 任何一步發生 OS 錯誤：刪除自己建立的暫存檔；`.sdd-export/` 是本次建立且仍是空的時移除它；結束碼 1、`reason: "os-error"`，
   `error` 為 `could not write .sdd-export/: <原因>`。已完成的 `os.replace` 不回復（`nutrients.json` 是完整的新內容，
   `check` 之後會回報 `view: "stale"`）。

成功時輸出，結束碼 0：

```json
{
  "written": [".sdd-export/nutrients.json", ".sdd-export/README.md", ".sdd-export/.gitattributes"],
  "created": true,
  "state": "<64 hex>",
  "generation": 2,
  "counts": {"principles": 1, "features": 2, "requirements": 2, "lessons": 1, "discarded": 1, "pending": 1, "inherited": 3, "new": 2},
  "diff": { "...": "同 validate" }
}
```

`written` 只列出這次實際寫入的檔案；`created` 表示 `.sdd-export/` 是否為本次建立。
以相同草稿、相同日期重複執行，第二次的檔案內容與第一次逐位元組相同（`--expect` 要用第一次輸出的 `state`）。

## README.md 的產生

由 `nutrients.json` 決定性地產生（相同輸入、相同位元組）。第一行是標記（data-model「手動編輯的偵測」），之後依序：

1. `# Nutrients: <project>`，以及世代、匯出日期、範圍、各類數量。
2. `## Principles`：每條原則一個小節，標出 `origin`、`revised`、`status`、依據。
3. `## Features`：依順序每個功能一個小節（標題、摘要、來源、spec、相依），其下依 `kind` 分組列出需求，每條需求標出 `id`、
   `origin`、`status` 與依據；待確認的標為 `(pending)`。
4. `## Lessons`：依 `kind` 分為 Decisions、Pitfalls、Reversed approaches。
5. `## Discarded`：表格列出 `id`、`kind`、`origin`、`discarded_in`、理由。

標籤是英文（與腳本的其他輸出一致），內容是 `nutrients.json` 的字串原文。

## 以模組方式載入

測試與 007 以 `importlib` 載入本檔：載入時 MUST NOT 執行任何動作。下列能力 MUST 是獨立、可呼叫的函式，不依賴目前目錄：

| 函式（名稱於實作時決定） | 用途 |
|---|---|
| 讀取並驗證養分 | 給定路徑，回傳狀態（同 `export_dir`）與內容或錯誤清單 |
| 讀取並驗證世代紀錄 | 給定路徑，回傳狀態（同 `lineage`）與內容或錯誤清單 |
| 驗證草稿 | 給定草稿、世代紀錄、既有養分與專案根目錄，回傳錯誤清單 |
| 序列化 | 養分或世代紀錄 → 位元組（共通的序列化規則） |
| 計算差異 | 兩份養分 → `diff` |
| 機密掃描 | 字串或檔案 → 命中的位置 |
| 讀取範圍 | 專案根目錄與範圍 → 可讀檔案、排除的數量與機密檔案 |

`main(argv, root=None, stdin=None, stdout=None, stderr=None)` 回傳結束碼，可指定專案根目錄與 stdin 以便測試。
