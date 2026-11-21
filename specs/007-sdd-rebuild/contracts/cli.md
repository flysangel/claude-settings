# Contract: sdd_rebuild.py 的指令介面

```text
uv run <skill>/scripts/sdd_rebuild.py check   [--old <dir>]      新專案與舊專案的現況、進度、下一步
uv run <skill>/scripts/sdd_rebuild.py save    [--refresh-source]  從 stdin 讀入完整的進度並保存
uv run <skill>/scripts/sdd_rebuild.py preview                     以已保存的進度組成世代紀錄並檢查，輸出摘要
uv run <skill>/scripts/sdd_rebuild.py claim   <feature-id> [--dir <specs/name>]  記下這個功能剛產生的 spec 資料夾
uv run <skill>/scripts/sdd_rebuild.py verify                      檢查產生的 constitution 與 spec
uv run <skill>/scripts/sdd_rebuild.py lineage                     寫入 .sdd-rebuild/lineage.json
uv run <skill>/scripts/sdd_rebuild.py focus                       把 .specify/feature.json 指向第一份產生的 spec
uv run <skill>/scripts/sdd_rebuild.py clear                       清除進度
```

`<skill>` 是 skill 的資料夾，SKILL.md 以 `${CLAUDE_SKILL_DIR}` 表示。一律在**新專案**的根目錄執行（目前目錄）；
舊專案以 `--old` 指定（第一次）或由進度的 `old_project` 取得（之後）。子指令不認得、缺少或多出參數時，結束碼 1，`reason: "usage"`。

資料格式見 [data-model.md](../data-model.md)；決定與理由見 [research.md](../research.md)。

## 共通

- stdout 只有一份 JSON 物件（UTF-8、LF、縮排 2、`ensure_ascii=False`、結尾換行），鍵的順序固定；新專案的路徑相對於新專案根目錄、
  以 `/` 分隔；舊專案的路徑只有 `old.path` 一處（絕對路徑，給 Claude 用於 US4 的匯出）。
- 失敗時 JSON 有 `"error": "<一句英文>"` 與 `"reason": "<列舉值>"`，同一句 `error` 也寫到 stderr。SKILL.md 依 `reason` 分支。
- **寫入範圍**：`save`、`claim` 只寫 `.specify/sdd-rebuild/`；`lineage` 只寫 `.sdd-rebuild/` 的兩個檔案與 `.specify/sdd-rebuild/progress.json`；
  `focus` 只寫 `.specify/feature.json`；`clear` 只刪除 `.specify/sdd-rebuild/` 的兩個檔案與變空的該資料夾。
  `check`、`preview`、`verify` 不寫入任何檔案。**任何指令都不寫入舊專案**；對舊專案只讀 data-model 列出的三個檔案。
  寫入一律「同資料夾的暫存檔再取代」（005 的 `atomic_write`）。
- 執行時以 `importlib` 載入 `<skill>/../sdd-export/scripts/sdd_export.py` 與 `<skill>/../sdd-grill/scripts/sdd_grill.py`；
  任一個不存在或載入失敗時，所有指令以結束碼 3、`reason: "dependency"` 結束，`missing` 列出缺少的 skill 名稱。
- **機密**（原則 V）：舊專案的養分與世代紀錄、既有的進度都可能在寫入後被手動編輯。007 以 006 的機密樣式掃描它們的每個字串
  （欄位名稱也算），也掃描 `preview`、`lineage` 組好的世代紀錄；命中時只輸出 `check: "secret"` 與欄位路徑（`detail` 不含值），
  不建立快照、不寫入任何檔案。任何指令的輸出（含 `error`、`detail`、差異、轉述的 006 錯誤）都不含命中的值；006 的錯誤的路徑或說明
  含有機密樣式時改以 `{"check": "secret", "path": "(not shown)", ...}` 取代。不新增 `reason`：命中時沿用下表既有的 `reason`。
- 唯一的外部指令是 `git`（經 005 的 `fingerprint` 執行 `rev-parse`，只讀）。
- Windows 與 Linux 的輸出逐位元組相同（`saved_at`、`rebuilt_at`、`head`、`old.path` 這類取決於當下或機器的值除外）。
  `--old` 接受該平台的路徑寫法；比較路徑時以實際路徑（`realpath`）、Windows 上不分大小寫。

## 結束碼與 `reason`

| 結束碼 | `reason` | 指令 | 意義 |
|---|---|---|---|
| 0 | | 全部 | 成功 |
| 1 | `usage` | 全部 | 用法錯誤 |
| 1 | `old-mismatch` | `check` | `--old` 與進度的 `old_project` 不同 |
| 1 | `invalid` | `save`、`preview` | 進度不符合結構，或 `preview` 的檢查不通過（`errors` 列出；含組好的世代紀錄有機密樣式時的 `secret`） |
| 1 | `secret` | `save` | 字串符合機密樣式（只指出欄位路徑；欄位名稱符合時指出所在物件的路徑，最上層為 `(top level)`；名稱含句點時也一樣，路徑不由名稱切割而來） |
| 1 | `frozen` | `save` | 已確認的內容被修改，或已產生文件後要改回 `deciding` |
| 1 | `finished` | `save` | 世代紀錄已寫入，只能 `focus`、`clear` |
| 1 | `source` | `save` | 建立或更新快照時舊專案的養分無法使用（`export_dir` 不是 `ours`，含養分有機密樣式時） |
| 1 | `no-progress` | `preview`、`claim`、`verify`、`lineage`、`focus` | 沒有進度；或需要已確認的進度而它還在 `deciding` |
| 1 | `none`、`ambiguous`、`mismatch` | `claim` | 見 claim |
| 1 | `not-next` | `claim` | 這個功能不是下一個要產生 spec 的功能，或它對應既有 spec、已經有 `spec_dir` |
| 1 | `mismatch-documents` | `verify`、`lineage`、`focus` | `verify` 有失敗的項目 |
| 1 | `lineage-changed` | `lineage` | `.sdd-rebuild/lineage.json` 已存在且內容與組成的結果不同 |
| 1 | `internal` | `lineage` | 007 的檢查通過但 006 的驗證不通過（007 的缺陷） |
| 1 | `not-regular` | `focus` | `.specify/feature.json` 存在但不是一般檔案 |
| 1 | `conflict` | `save`、`claim`、`lineage`、`clear` | `.specify/sdd-rebuild/` 有不是本功能的檔案 |
| 1 | `os-error` | 寫入的指令 | 無法寫入；暫存檔已移除，已存在的檔案不變 |
| 3 | `dependency` | 全部 | 相鄰的 sdd-export 或 sdd-grill 缺少 |
| 3 | `speckit-missing`、`speckit-incomplete` | `check` | 新專案未導入 Spec Kit，或缺少產生文件所需的檔案（005 的判定） |
| 3 | `old-required` | `check` | 沒有進度也沒有 `--old` |
| 3 | `old-missing`、`old-not-folder` | `check` | 舊專案路徑不存在、不是資料夾（沒有進度時才判定） |
| 3 | `same-project`、`old-inside-new`、`new-inside-old` | `check` | 兩個路徑相同或互相包含 |
| 3 | `rebuilt` | `check` | 新專案已有世代紀錄（`rebuild_dir: "ours"`）而沒有進度 |
| 3 | `rebuild-conflict` | `check`、`lineage` | `rebuild_dir` 為 `conflict` 或 `invalid` |
| 3 | `nutrients-conflict`、`nutrients-unreadable`、`nutrients-invalid`、`nutrients-newer` | `check` | 舊專案的 `.sdd-export/` 無法使用（006 的判定，或養分有機密樣式時的 `nutrients-invalid`；沒有進度時才判定） |
| 3 | `progress-unreadable` | `check` | 進度無法解析、不符合結構，或含有機密樣式（可以 `clear`） |

`check` 的 `reason` 依上表由上而下取第一個成立的。`export_dir` 為 `none`、`empty`（需要先匯出）不是錯誤，結束碼 0。

## check

只讀。輸出：

```json
{
  "dependencies": {"sdd-export": "ok", "sdd-grill": "ok"},
  "export_skill": true,
  "speckit": "ok",
  "missing": [],
  "constitution": "written",
  "numbering": "sequential",
  "specs": [{"dir": "specs/001-deploy", "number": "001"}],
  "rebuild_dir": "none",
  "rebuild_conflicts": [],
  "rebuild_errors": [],
  "rebuilt_generation": null,
  "progress": "present",
  "changed": [],
  "saved": { "...": "progress.json 的完整內容，或 null" },
  "old": {"path": "/abs/old-project", "state": "ok"},
  "export_dir": "ours",
  "nutrients_edited": false,
  "nutrients_errors": [],
  "conflicts": [],
  "nutrients": { "...": "養分的完整內容（export_dir 為 ours 時），否則 null" },
  "pending": ["status-report-diff"],
  "old_lineage": "present",
  "old_lineage_errors": [],
  "needs_old_lineage": true,
  "source_state": "available",
  "source_changed": {"nutrients": false, "lineage": false},
  "source_diff": null,
  "next": {"step": "decide", "feature": null, "candidates": []}
}
```

| 欄位 | 值 |
|---|---|
| `dependencies` | 每個相鄰 skill 的腳本：`"ok"` 或 `"missing"` |
| `export_skill` | `<skill>/../sdd-export/SKILL.md` 是否存在（US4 的匯出要讀它） |
| `speckit`、`missing`、`constitution`、`numbering`、`specs` | 同 005 的 `check` |
| `rebuild_dir`、`rebuild_conflicts` | data-model「`.sdd-rebuild/`」；`conflict` 時列出不屬於本功能的路徑 |
| `rebuild_errors` | `rebuild_dir` 為 `invalid` 時，006 `load_lineage` 對新專案 `lineage.json` 的錯誤（同 006 的 `errors` 格式，經同樣的取代：路徑或說明含機密樣式時為 `(not shown)`）；含機密樣式時每個命中一項 `check: "secret"` 與欄位路徑，不含值；其他情況 `[]` |
| `rebuilt_generation` | `rebuild_dir` 為 `ours` 時新專案世代紀錄的 `generation`（整數；SKILL.md 以它說明第幾代，不開啟該檔）；其他情況 `null` |
| `progress` | `"none"`、`"present"`、`"unreadable"`、`"conflict"` |
| `changed` | 進度存在時，新專案指紋中改變的項目（`constitution`、`specs`、`head`） |
| `saved` | 進度的完整內容（`present` 時；含機密樣式的進度是 `unreadable`，不輸出） |
| `old` | `path`：實際路徑（`--old` 或進度的 `old_project`）；`state`：`"ok"`、`"missing"`、`"not-folder"`、`"same"`、`"old-inside-new"`、`"new-inside-old"` |
| `export_dir`、`conflicts` | 006 對舊專案 `.sdd-export/` 的判定與衝突的路徑（相對於舊專案）；舊專案無法存取時 `null`；006 判為 `ours` 但養分有機密樣式時為 `"invalid"` |
| `nutrients_edited` | 006 的 `nutrients` 為 `"edited"` 或 `"unknown"`（匯出後被手動編輯） |
| `nutrients_errors` | `export_dir` 為 `invalid` 或 `unreadable` 時的錯誤（同 006 的 `errors` 格式）；機密樣式時每個命中的欄位一項 `{"check": "secret", "path": <養分中的路徑>, "detail": <不含值>}` |
| `nutrients` | 目前舊專案的養分（`ours` 時）；接續時與快照比對用，Claude 呈現養分時以它（沒有進度時）或 `saved.source.nutrients`（有進度時）為準 |
| `pending` | 養分中 `status: "pending"` 的 `id`，依出現順序 |
| `old_lineage`、`old_lineage_errors` | 006 `load_lineage` 對舊專案世代紀錄的結果（`present` 但世代與養分不同時 `"mismatch"`；有機密樣式時 `"invalid"`，錯誤只列 `check: "secret"` 與路徑）與錯誤 |
| `needs_old_lineage` | 養分的 `generation` ≥ 2 |
| `source_state` | 有進度時：`"available"`（舊專案的養分可讀）或 `"unavailable"`；沒有進度時 `null` |
| `source_changed` | 有進度且 `available` 時：養分、舊世代紀錄的雜湊是否與快照不同；否則 `null` |
| `source_diff` | 養分改變時：006 的 `compute_diff(快照, 目前)`；否則 `null` |
| `next` | 依進度算出的下一步，見下 |

`next.step`（沒有進度時 `"start"`）：

| `step` | 條件 |
|---|---|
| `start` | 沒有進度 |
| `decide` | `phase` 為 `deciding` |
| `constitution` | 已確認，`generation.constitution` 為 `pending` |
| `review-constitution` | `generation.constitution` 為 `written` |
| `claim` | 下一個要產生的功能（`feature`）沒有 `spec_dir`，且已有候選資料夾（`candidates`，同 `claim` 的定義）。候選只是「新的、含 `spec.md`」的資料夾，腳本無法分辨它是否為這次重建產生（維護者自建或另一個視窗產生的也會列入）；SKILL.md 讀取候選的 `spec.md` 並經維護者確認後才 `claim --dir`，確認屬於這個功能時不重新產生 |
| `specify` | 同上但沒有候選 |
| `review` | `feature` 已有 `spec_dir`、`reviewed` 為 `false` |
| `verify` | 全部功能都已 `reviewed`，`lineage_written` 為 `null` |
| `focus` | `lineage_written` 不為 `null`，`feature.json` 尚未指向目標 |
| `clear` | `lineage_written` 不為 `null`，`feature.json` 已指向目標或沒有要指向的 spec |

## save

從 stdin 讀入一份進度（data-model「進度」），依「驗證規則」檢查。`phase` 為 `confirmed` 時另外執行 `preview` 的全部檢查。通過時：

1. 自己的資料夾不存在就建立，並寫入固定內容的 `.gitignore`。
2. 沒有既有進度、或帶 `--refresh-source`（只在 `deciding` 允許；確認後帶它時結束碼 1、`reason: "frozen"`，不寫入）時，以 006 的程式讀取 `old_project` 建立快照；
   舊專案的 `.sdd-export/` 不是 `ours`（含養分有機密樣式）時 `reason: "source"`，不寫入；舊世代紀錄有機密樣式時不納入快照（`lineage_state: "invalid"`）。
   其他時候沿用既有快照。
3. 填入 `saved_at`、`fingerprint`；第一次 `confirmed` 時記下 `baseline` 與 `rebuilt_at`；改回 `deciding` 時兩者設為 `null`。
   `spec_dir`、`lineage_written` 沿用既有值。
4. 原子寫入 `progress.json`。

輸出 `{"saved": ".specify/sdd-rebuild/progress.json", "phase": "...", "baseline": true, "snapshot": "created" | "kept" | "refreshed"}`。
`baseline` 為 `true` 表示這次保存記下了基準（第一次 `confirmed`）。失敗時的輸出另有 `path`（`invalid`、`secret`、`frozen` 時指出欄位路徑；
`adjustments[i].lesson` 不是快照養分的教訓時同樣是 `invalid`）；`phase` 為 `confirmed` 而 `preview` 的檢查不通過時另有 `errors`（格式同 `preview`）。

## preview

以已保存的進度（不讀 stdin）組成世代紀錄並執行 data-model「`preview` 的檢查」。不寫入。輸出：

```json
{
  "ok": true,
  "errors": [],
  "generation": 3,
  "lineage": { "...": "組好的世代紀錄；尚未決定的 spec_dir 為 null" },
  "summary": {
    "kept": [{"section": "features", "id": "deploy", "title": "一行部署"}],
    "modified": [],
    "merged": [{"section": "requirements", "id": "overview-list", "title": "…", "from": ["status-list", "report-diff"]}],
    "split": [],
    "added": [],
    "discarded": [{"section": "requirements", "id": "audit-log", "title": "…", "reason": "…"}],
    "pending_decided": ["status-report-diff"],
    "adjustments": [{"lesson": "atomic-write", "change": "…", "adopted": true}],
    "order": [{"id": "deploy", "title": "一行部署", "depends_on": [], "existing_spec": null}]
  },
  "counts": {"principles": 1, "features": 2, "requirements": 3, "lessons": 2, "discarded": 4}
}
```

`errors` 的格式同 006：`{"check", "path", "detail"}`，`check` 名稱見 data-model。`ok` 為 `false` 時結束碼 1、`reason: "invalid"`，
`error` 為 `the decisions do not yet make a valid lineage`，`summary` 仍輸出能組成的部分；但 `errors` 含 `secret` 時 `lineage` 與 `summary` 為 `null`
（不輸出命中的值）。

## claim

`claim <feature-id> [--dir <specs/name>]`。前提：進度已確認；`feature-id` 是 `target.features` 中 `existing_spec` 為 `null`、
`spec_dir` 為 `null`，而且排在它前面、需要產生的功能都已有 `spec_dir`（否則 `reason: "not-next"`）。

1. 候選：`specs/` 下含 `spec.md`、不在 `baseline.specs`、也不是任何功能的 `spec_dir` 的資料夾。
2. 讀 `.specify/feature.json` 的 `feature_directory`（005 的 `read_feature_directory`）。
3. 不帶 `--dir`：候選恰好一個且等於 `feature_directory` 時記錄（`feature_directory` 可能被另一個視窗的 `speckit-specify` 改寫，
   所以這不證明候選屬於這個功能；SKILL.md 在執行前先確認 `speckit-specify` 回報的資料夾與其 `spec.md` 的內容）。否則不記錄：沒有候選 → `none`（另列 `incomplete`：
   不在 `baseline`、沒有 `spec.md` 的 `specs/` 子資料夾）；兩個以上 → `ambiguous`；一個但不等於 `feature_directory` → `mismatch`。
4. 帶 `--dir`：值 MUST 是候選之一（否則 `usage`）；記錄。只在維護者確認後使用。
5. 記錄 = 把 `spec_dir` 寫入該功能並原子保存進度。

輸出 `{"feature": "...", "spec_dir": "specs/004-overview", "feature_directory": "specs/004-overview", "candidates": [...], "incomplete": [...]}`。

## verify

只讀。前提：進度已確認。以 005 的 `verify_generated` 檢查由這次重建產生的功能（research R2 的組法），另外檢查：

| 失敗的 `check` | 規則 |
|---|---|
| 005 的全部（`existing-spec-changed`、`constitution-changed`、`constitution-not-written`、`spec-missing`、`spec-not-new`、`order`、`dependency-order`） | 同 005 |
| `existing-spec-missing` | 對應既有 spec 的功能，其 `existing_spec/spec.md` 仍存在 |
| `not-reviewed` | `generation.constitution` 為 `reviewed` 或 `not-needed`；每個功能 `reviewed` 為 `true` |

輸出同 005 的 `verify`（`ok`、`failures`、`constitution`、`specs`、`unexpected`），`specs` 的每一項多一個 `existing`（布林）。
`ok` 為 `false` 時結束碼 1、`reason: "mismatch-documents"`。

## lineage

前提：進度已確認。步驟：

1. `rebuild_dir` 為 `conflict` 或 `invalid`：結束碼 3、`rebuild-conflict`，不寫入；輸出 `rebuild_conflicts` 與 `rebuild_errors`（同 `check`）。
2. 執行 `verify`；不通過時 `mismatch-documents`，不寫入。
3. 以快照與進度組成世代紀錄，依序執行三層驗證（research R6）：007 的檢查（含 `secret`）不通過時 `invalid`；
   006 的 `lineage_problems` 或 `generation_problems(L, L, None)` 不通過時 `internal`（輸出 `errors`），都不寫入。
4. `lineage.json` 已存在：換行正規化後與組成的位元組相同時不改寫（`unchanged: true`）；不同時 `lineage-changed`，不寫入。
5. 建立 `.sdd-rebuild/`（需要時），原子寫入 `lineage.json`；`.gitattributes` 不存在時寫入固定內容，存在時不動。
6. 把 `lineage.json` 的內容雜湊記入進度的 `lineage_written` 並原子保存。

步驟 5 與 6 之間中斷時，下一次 `lineage` 走步驟 4 的「相同」並補上步驟 6（冪等）。輸出：

```json
{
  "written": [".sdd-rebuild/lineage.json", ".sdd-rebuild/.gitattributes"],
  "unchanged": false,
  "lineage": ".sdd-rebuild/lineage.json",
  "generation": 3,
  "counts": {"principles": 1, "features": 2, "requirements": 3, "lessons": 2, "discarded": 4}
}
```

## focus

前提：進度已確認且 `lineage_written` 不為 `null`（否則 `no-progress`）。再執行一次 `verify`（不通過時 `mismatch-documents`，不寫入）。
目標是 `target.features` 中第一個 `existing_spec` 為 `null` 的功能的 `spec_dir`；沒有這樣的功能時不寫入，`feature_directory` 為 `null`。
寫入方式與內容同 005 的 `focus`（只有 `feature_directory` 一個鍵；值相同時不寫）。
輸出 `{"feature_directory": "specs/004-overview" | null, "previous": "...", "changed": true}`。

## clear

同 005：刪除 `.specify/sdd-rebuild/progress.json` 與 `.gitignore`，資料夾變空時刪除。輸出 `{"cleared": true | false}`。
衝突時不刪除，`reason: "conflict"`。不碰 `.sdd-rebuild/`、constitution 與 spec。`progress` 為 `unreadable` 時也能清除。

## 以模組方式載入

測試以 `importlib` 載入本檔：載入時 MUST NOT 執行任何動作（也不載入 005、006；第一次需要時才載入）。下列能力 MUST 是獨立、可呼叫的函式：
祖先表的建立、`expand`、世代紀錄的組成、已用過的 `id` 的計算、`preview` 的檢查。
`main(argv, root=None, stdin=None, stdout=None, stderr=None)` 回傳結束碼。
