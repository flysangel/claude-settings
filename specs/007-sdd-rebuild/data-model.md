# Data Model: sdd-rebuild

本功能讀取兩份由他人定義的資料：舊專案的養分（`.sdd-export/nutrients.json`）與舊專案的世代紀錄（`.sdd-rebuild/lineage.json`），
寫出一份由他人定義的資料：新專案的世代紀錄。三者的格式都由 006 定義（`specs/006-sdd-export/data-model.md`，以下稱「006 契約」），
本文件不重複，只定義 007 自己的資料（進度、目標、祖先表）與 007 如何把它們轉成世代紀錄。決定與理由見 [research.md](./research.md)；
指令的輸入與輸出見 [contracts/cli.md](./contracts/cli.md)。

## 新專案中屬於 sdd-rebuild 的檔案

| 檔案 | 建立者 | 入庫 | 內容 |
|---|---|---|---|
| `.specify/sdd-rebuild/.gitignore` | `save`（第一次） | 否（忽略自己） | 固定兩行：`# Created by sdd-rebuild. Local rebuild progress; never committed.` 與 `*` |
| `.specify/sdd-rebuild/progress.json` | `save`、`claim`、`lineage` | 否 | 進度，見下 |
| `.sdd-rebuild/lineage.json` | `lineage` | **是** | 世代紀錄，格式見 006 契約「世代紀錄」 |
| `.sdd-rebuild/.gitattributes` | `lineage` | 是 | 固定兩行：`# Created by sdd-rebuild; keeps the lineage LF on every platform.` 與 `* text eol=lf` |

規則：

- `.specify/sdd-rebuild/` 只放上表的兩個檔案；有其他項目、`.gitignore` 的內容（換行正規化後）不是固定內容、或路徑不是一般資料夾時，
  視為衝突（`progress: "conflict"`），`save`、`claim`、`lineage`、`clear` 都不寫入、不刪除。同 005 的自己的資料夾。
- `.sdd-rebuild/` 只放上表的兩個檔案。狀態（`check` 的 `rebuild_dir`）：

  | 值 | 判定 |
  |---|---|
  | `"none"` | 不存在 |
  | `"empty"` | 空的資料夾 |
  | `"ours"` | 只有上表的檔案（`.gitattributes` 可缺），`lineage.json` 存在且 006 的 `load_lineage` 為 `present` |
  | `"conflict"` | 路徑是檔案；有上表以外的項目；沒有 `lineage.json` 卻有其他檔案；`lineage.json` 的 `tool` 不是 `sdd-rebuild` |
  | `"invalid"` | `lineage.json` 存在但 `load_lineage` 為 `unreadable`、`invalid` 或 `newer` |

- `.specify/feature.json` 不是本功能的檔案；只有 `focus` 改寫它的 `feature_directory`（原則 I 的例外，同 005）。
- 舊專案：本功能的腳本只讀 `.sdd-export/nutrients.json`、`.sdd-export/README.md`（006 判斷手動編輯所需）與 `.sdd-rebuild/lineage.json`，
  不寫入。US4 的匯出由 006 的腳本寫入（只寫 `.sdd-export/`）。

## 進度（`progress.json`）

UTF-8、LF、縮排 2、結尾換行的 JSON 物件。由 Claude 組成、經 stdin 交給 `save`；標示「腳本」的欄位由腳本寫入，
Claude 送來的值被忽略（以既有值或腳本算出的值取代）。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schema` | `1` | |
| `tool` | `"sdd-rebuild"` | |
| `old_project` | 字串 | 舊專案的絕對路徑（進度不入庫）；第一次 `save` 後不可變更 |
| `language` | 字串或 `null` | 產生文件的語言，例如 `"zh-TW"`；確認時不得為 `null`（FR-021） |
| `phase` | `"deciding"` 或 `"confirmed"` | |
| `stage` | `"items"`、`"new"`、`"lessons"`、`"summary"` | 逐項決定 → 新需求 → 教訓引發的調整 → 最終摘要；`confirmed` 時必為 `"summary"` |
| `source` | 物件 | 腳本：快照，見「快照」 |
| `old_lineage` | `"used"`、`"not-needed"`、`"skipped"` | 祖先表是否納入舊專案的世代紀錄，見「快照」 |
| `constitution` | 物件 | `{"action": "create" \| "amend" \| "keep", "governance": [字串]}`；原則的內容來自 `target.principles` |
| `target` | 物件 | 決定後的結果，見「目標」 |
| `discards` | 陣列 | 這次重建捨棄的來源項目，見「目標」 |
| `pending_decided` | 識別字陣列 | 維護者已逐項決定的待確認項目（來源養分中 `status: "pending"` 的 `id`） |
| `adjustments` | 陣列 | 教訓引發的調整：`{"lesson": 教訓 id, "change": 字串, "adopted": true \| false \| null}`；`null` 表示尚未決定 |
| `deferred` | 陣列 | `{"item": 字串, "reason": 字串, "feature": 功能 id 或 null}`（同 005） |
| `for_plan` | 陣列 | `{"item": 字串, "feature": 功能 id 或 null}`（同 005） |
| `generation` | 物件 | `{"constitution": "pending" \| "written" \| "reviewed" \| "not-needed"}`；`deciding` 時 MUST 為 `"pending"`（`keep` 時為 `"not-needed"`） |
| `rebuilt_at` | 字串或 `null` | 腳本：第一次以 `confirmed` 保存當天的 UTC 日期；`deciding` 時 `null` |
| `saved_at` | 字串 | 腳本：最後一次保存的 UTC 時間（ISO 8601，到秒） |
| `fingerprint` | 物件 | 腳本：新專案的指紋（同 005：constitution、每份 spec.md、HEAD） |
| `baseline` | 物件或 `null` | 腳本：第一次以 `confirmed` 保存時記下（同 005），之後不變；`deciding` 時 `null` |
| `lineage_written` | 字串或 `null` | 腳本：`lineage` 寫入的 `lineage.json` 內容雜湊；寫入前 `null` |

### 快照（`source`）

第一次 `save` 時，腳本讀取 `old_project` 並記下；之後只有 `save --refresh-source`（只在 `deciding` 允許）會重新讀取。

| 欄位 | 說明 |
|---|---|
| `nutrients` | 養分的完整內容（006 驗證為 `ours` 的內容） |
| `nutrients_sha256` | `nutrients.json` 換行正規化後的 SHA-256 |
| `lineage_state` | 006 `load_lineage` 對舊專案世代紀錄的結果；`present` 但 `generation` 與養分不同時記為 `"mismatch"` |
| `lineage` | `lineage_state` 為 `present` 時是舊世代紀錄的完整內容，否則 `null` |
| `lineage_sha256` | 舊世代紀錄存在時是它的雜湊，否則 `null` |

`old_lineage` 與快照的關係（`save` 檢查）：

| `lineage_state` | 養分的 `generation` | 允許的 `old_lineage` |
|---|---|---|
| `present` | 任何 | `"used"` |
| `none` | 1 | `"not-needed"` |
| `none` | ≥ 2 | `"skipped"`（維護者已同意，research R4） |
| `mismatch`、`unreadable`、`invalid`、`newer`、`conflict` | 任何 | `"skipped"` |

快照無法建立（舊專案的養分不是 `ours`）時 `save` 失敗，不寫入。

### 目標（`target`、`discards`）

`target` 有 `principles`、`features`、`lessons` 三個陣列；`features` 的順序就是 spec 的順序（施工順序）。每個項目：

| 欄位 | 適用 | 說明 |
|---|---|---|
| `id` | 全部 | 識別字（006 契約的格式） |
| `basis` | 全部 | `"inherit"`（沿用來源養分中同 `id` 的項目）、`"derived"`（合併或拆分）、`"new"`（重建時新增） |
| `from` | 全部 | `derived` 時是直接來源的 `id`（至少一個，維護者指定的順序）；其他時候是空陣列 |
| `title` | 原則、功能、教訓 | 字串；`inherit` 時可為 `null`，表示沿用來源的內容 |
| `text` | 原則、需求、教訓 | 同上 |
| `summary` | 功能 | 同上 |
| `kind` | 需求、教訓 | 006 契約的列舉值；`inherit` 時可為 `null`（沿用） |
| `depends_on` | 功能 | `target.features` 中排在它前面的功能 `id` |
| `existing_spec` | 功能 | `null`（由這次重建產生 spec），或新專案中既有的 spec 資料夾 `specs/<名稱>`（對應既有 spec，research R10） |
| `spec_dir` | 功能 | 腳本（`claim`）：產生的 spec 資料夾；`existing_spec` 不為 `null` 時等於它；確認前 `null` |
| `reviewed` | 功能 | 產生的 spec 已與摘要比對；`existing_spec` 不為 `null` 時固定 `true`；確認前 `false` |
| `requirements` | 功能 | 需求陣列，每個需求有 `id`、`basis`、`from`、`kind`、`text` |

`discards`：`{"id": 來源項目的 id, "text": 字串或 null, "reason": 字串或 null}`；`text` 為 `null` 時取來源項目的 `title`
（需求取 `text` 的第一行，最多 80 字），`reason` 為 `null` 時寫「維護者決定捨棄」。

### 驗證規則

`save` 只檢查結構與不變的條件（任何時候都必須成立），違反時不寫入，以結束碼 1 回報欄位路徑：

1. 欄位齊全、沒有多出的欄位、型別與列舉值正確；字串非空（可為 `null` 的除外）。
2. `schema`、`tool` 正確；`old_project` 與既有進度相同。
3. `old_lineage` 與快照相符（上表）。
4. 識別字格式正確；`target` 中所有項目（含需求）的 `id` 唯一；`depends_on` 只指向前面的功能。
5. `stage` 與 `phase` 一致；`generation.constitution` 與 `constitution.action`、`phase` 一致；
   `spec_dir` 只能由腳本寫入（Claude 送來的值與既有值不同時拒絕）。
6. `phase` 為 `"confirmed"` 時：`language` 不為 `null`；`adjustments` 都已決定；**`preview` 的全部檢查通過**（下一節）。
7. 已確認且有任何 `spec_dir`（不含對應既有 spec 的）或 `generation.constitution` 不是 `pending`、`not-needed` 的進度，不能改回 `deciding`；
   已確認的進度，`target`、`discards`、`constitution`、`language` 不能再改（只有 `generation` 與各功能的 `reviewed` 可以前進）。
8. `lineage_written` 不為 `null` 後，只接受 `clear`（`save` 拒絕）。
9. 字串值不符合 006 的機密樣式；錯誤只指出欄位路徑。

### `preview` 的檢查（007 的寫入規則，research R6）

以快照與 `target`、`discards` 組成世代紀錄，並檢查（全部列出，不在第一個停止）：

| `check` 名稱 | 規則 |
|---|---|
| `inherit-unknown` | `inherit` 的 `id` 是來源養分中同種類的有效項目 |
| `inherit-twice` | 同一個來源 `id` 至多被 `inherit` 一次 |
| `from-unknown` | `from` 的每個 `id` 是來源養分中同種類的有效項目（需求的 `from` 只能是需求，以此類推） |
| `id-taken` | `derived`、`new` 的 `id` 不在「已用過的 `id`」中（下一節） |
| `unaccounted` | 來源養分的每個有效項目被 `inherit`、出現在某個 `from`，或在 `discards` 中 |
| `discard-conflict` | `discards` 的 `id` 是來源養分的有效項目，且沒有被 `inherit` 或出現在 `from` |
| `pending-undecided` | 來源養分中每個 `pending` 的 `id` 都在 `pending_decided` 中 |
| `existing-spec` | `existing_spec` 是新專案中存在、含 `spec.md` 的資料夾，彼此不同；有 `existing_spec` 的功能全部排在沒有的之前 |
| `lineage-format` | 組好的世代紀錄通過 006 的 `lineage_problems`（`spec_dir` 尚未決定的功能以預留值 `specs/pending` 代入檢查） |
| `next-export` | 組好的世代紀錄通過 006 的 `generation_problems(L, L, None)`（research R6 第三層） |

### 已用過的 `id`

集合 U 為下列 `id` 的聯集：

1. 來源養分：有效項目、`discarded`、所有 `derived_from` 中的 `id`；
2. 舊專案的世代紀錄（`old_lineage` 為 `"used"` 時）：同三類；
3. 祖先表展開後出現的所有 `id`；
4. 組好的世代紀錄中：`inherit` 項目的 `id`，以及所有項目補齊後的 `derived_from` 中的 `id`。

`derived`、`new` 的 `id` MUST NOT 在 U 中，也 MUST NOT 與其他 `derived`、`new` 的 `id` 相同（規則 4 已保證）。

## 祖先表與補入（research R5）

```text
ancestors: id → [id]
  對來源養分的每個有效項目 x：ancestors[x.id] = x.derived_from
  old_lineage 為 "used" 時，對舊世代紀錄的每個有效項目 y：
    ancestors[y.id] = ancestors[y.id] 之後接上 y.derived_from 中尚未出現的 id

expand(direct):
  result = direct 去重（保留第一次出現）
  seen = set(result)
  for d in direct（依順序）:
    visit(d)
  visit(x):
    for a in ancestors[x]（依順序；沒有時為空）:
      if a not in seen: result.append(a); seen.add(a); visit(a)
  return result
```

| 世代紀錄中的項目 | `derived_from` |
|---|---|
| `inherit` | `expand(ancestors[id])` |
| `derived` | `expand(from)` |
| `new` | `[]` |

性質（單元測試逐條驗證）：結果沒有重複；直接來源依給定順序在最前面；`expand(expand(x)) == expand(x)`（冪等，已補齊的項目在之後的重建中不再改變）；
祖先表有循環時仍會結束；結果只含祖先表與 `direct` 中出現過的 `id`。

## 世代紀錄的組成

依 006 契約「007 寫入時 MUST 遵守的規則」，由 `preview` 與 `lineage` 決定性地產生；欄位的順序、序列化由 006 的 `serialize(data, "lineage")` 決定。

| 頂層欄位 | 值 |
|---|---|
| `tool`、`schema` | `"sdd-rebuild"`、`1` |
| `generation` | 快照養分的 `generation` + 1 |
| `rebuilt_at` | 進度的 `rebuilt_at` |
| `source` | `{"project": 養分的 project, "generation": 養分的 generation, "nutrients_schema": 養分的 schema}` |
| `principles`、`features`、`lessons` | `target` 依序轉換（下表） |
| `discarded` | 養分的 `discarded` 原樣、依原順序，接著 `discards` 依序轉換 |

| `basis` | `id` | `origin` | `revised` | `derived_from` | `source` | 功能的 `spec` | 內容欄位 |
|---|---|---|---|---|---|---|---|
| `inherit` | 來源的 | 來源的 | 來源的；`title`、`text`、`summary` 任一與來源不同時接上這一代 | 見上表 | 來源的 | 來源的 | 目標的值；`null` 時來源的 |
| `derived` | 目標的 | 這一代 | `[]` | 見上表 | 第一個直接來源的（教訓沒有此欄位） | 第一個 `spec` 不為 `null` 的直接來源的，否則 `null` | 目標的值 |
| `new` | 目標的 | 這一代 | `[]` | `[]` | `"rebuild"` | `null` | 目標的值 |

功能另有 `spec_dir`（進度的值）與 `depends_on`（目標的值）；`status`、`evidence` 一律不寫。
捨棄紀錄：`{"id", "kind": 來源項目的種類, "origin": 來源的, "discarded_in": 這一代, "text", "reason"}`。

`preview` 依組成結果輸出摘要分類（[contracts/cli.md](./contracts/cli.md)）：`kept`（`inherit` 且內容未變）、`modified`（`inherit` 且內容改變）、
`merged`（`derived` 且 `from` 有兩個以上）、`split`（`derived` 且只有一個直接來源）、`added`（`new`）、`discarded`（`discards`），
以及 `pending_decided`、`adjustments` 的採用與否、功能的順序與相依。

## 狀態轉移

```text
（沒有進度）
   │ save（deciding；腳本建立快照）
   ▼
deciding ──save──▶ deciding              每個決定之後；save --refresh-source 換快照
   │  │
   │  └─clear──▶（沒有進度）              重新開始
   │ save（confirmed；preview 全部通過；記下 baseline、rebuilt_at）
   ▼
confirmed ──save──▶ confirmed            generation.constitution 前進；reviewed 前進
   │  │  │
   │  │  └─claim──▶ confirmed            記下一個功能的 spec_dir
   │  ├─save（deciding）                 只在沒有任何產生的 spec_dir 且 constitution 為 pending 或 not-needed 時
   │  └─clear──▶（沒有進度）              重新開始；已產生的文件保留
   │ verify 通過
   ▼
lineage（寫 .sdd-rebuild/；記下 lineage_written）
   │
   ▼
focus（寫 .specify/feature.json）
   │
   ▼
clear ──▶（沒有進度）
```

中途結束、產生失敗、`verify` 不通過：停在目前的狀態，進度保留。`lineage_written` 之後只能前進到 `focus`、`clear`。
