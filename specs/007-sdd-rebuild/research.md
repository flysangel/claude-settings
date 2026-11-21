# Research: sdd-rebuild 在新專案以養分重建

R1 是 SKILL.md 與腳本的分工總表；R2 至 R13 對應任務說明列出的重點與設計時衍生的決定。
「實測」指 2026-11-20 在 Linux（Python 3.12、uv 0.13.6）於 `/tmp` 的暫存目錄以 importlib 載入
`home/skills/sdd-export/scripts/sdd_export.py` 執行的結果，列在文末的「實測紀錄」。
世代紀錄的格式與「007 寫入時 MUST 遵守的規則」由 006 定義（`specs/006-sdd-export/data-model.md`）；
本功能是實作它的一方，除了 R5 經維護者核可的一處規則修改之外，不重新設計它。

## 與 005、006 的相同與不同

相同：都是**對話式的 skill**。逐項決定、追問新需求、比對產生的文件與摘要，只能由 Claude 依 SKILL.md 執行；
可以決定性完成的事集中在一支由 uv 執行、輸出 JSON 的 Python 腳本 `sdd_rebuild.py`。

| | 005 sdd-grill | 006 sdd-export | 007 sdd-rebuild |
|---|---|---|---|
| 執行的地方 | 目標專案 | 舊專案 | 新專案，另外**唯讀**舊專案 |
| 需要 Spec Kit | 是 | 否 | 是（FR-002） |
| 進度 | `.specify/sdd-grill/`，不入庫 | 沒有 | `.specify/sdd-rebuild/`，不入庫（R8） |
| 寫入的內容 | 透過 Spec Kit 產生 constitution 與 spec；`focus` | `.sdd-export/` | 透過 Spec Kit 產生 constitution 與 spec；`.sdd-rebuild/` 的世代紀錄；`focus` |
| 確認之後 | 產生多份文件，可能中斷 | 一次 `write` | 產生多份文件再寫世代紀錄，可能中斷（R9） |

007 的流程最長：讀養分（或先匯出）→ 逐項決定 → 新需求 → 教訓引發的調整 → 最終摘要確認 → 產生 constitution →
逐份產生 spec → 寫世代紀錄 → 收尾。005 與 006 的經驗是正常流程以外的分支最容易出錯，所以每一種結果的下一步都在
[contracts/skill.md](./contracts/skill.md) 依階段寫出，本文件只記錄決定與理由。

## R1 SKILL.md 與腳本的分工

- **Decision**：

  | 行為 | 放哪裡 | 理由 |
  |---|---|---|
  | 新專案是否導入 Spec Kit、產生文件所需的檔案是否齊全（FR-002、FR-019） | 腳本 `check`（載入 005 的 `speckit_state`） | 只看檔案，可決定；與 005 同一份判斷 |
  | 舊專案的路徑：不存在、不是目錄、與新專案相同或互相包含（FR-019、Edge Cases） | 腳本 `check` | 以實際路徑比對可決定；判斷錯了會在舊專案寫入 |
  | 養分的讀取與驗證、格式較新或無法讀取（FR-003、Edge Cases） | 腳本 `check`（載入 006 的 `export_folder`） | 格式只能有一份實作（R2） |
  | 舊專案世代紀錄的讀取與驗證（R4） | 腳本 `check`（載入 006 的 `load_lineage`） | 同上 |
  | 新專案的 constitution、既有 spec、編號方式、自己的進度、`.sdd-rebuild/` 的狀態 | 腳本 `check` | 可決定 |
  | 沒有養分時對舊專案匯出（US4） | SKILL.md 指示讀取已部署的 `../sdd-export/SKILL.md` 並照做；腳本只是 006 的腳本加上 `--project` | 匯出的規則只有一份（R3） |
  | 呈現養分、逐項決定保留、修改、合併、拆分、捨棄（FR-005、FR-008） | SKILL.md | 對話 |
  | 待確認的項目逐項決定（FR-018） | SKILL.md 詢問；腳本 `preview` 拒絕尚未決定的待確認項目 | 結構保證沒有遺漏 |
  | 新需求的追問（FR-006） | SKILL.md 指示讀取 `../sdd-grill/SKILL.md` 的「Rules for questioning」並套用 | 追問規則只有一份（R11） |
  | 教訓引發的調整、矛盾的指出（FR-007、US2-4） | SKILL.md；進度記錄每項調整的來源教訓與是否採用 | 語意判斷；記錄讓摘要能逐項列出 |
  | 世代紀錄每個項目的 `id`、`origin`、`revised`、`derived_from`、`source`、`spec`，捨棄紀錄的組成（FR-016） | 腳本 `preview`、`lineage` | 006 的寫入規則表每一列都可決定；由 Claude 手寫最容易斷鏈 |
  | 祖先表的建立、遞移補入、去重與排序（R5） | 腳本 | 決定性；維護者要求以單元測試鎖定 |
  | 「新取」的 `id` 不得與任何已用過的 `id` 相同（R6） | 腳本 `preview`、`lineage` | 可決定；006 察覺不到其中一種 |
  | 來源養分的每個有效項目都有去處（006 世代規則 2 的前提） | 腳本 `preview` | 可決定 |
  | 最終摘要的呈現與確認（FR-009、FR-010） | SKILL.md 呈現；腳本 `preview` 輸出分類清單與數量 | 呈現是對話；分類由腳本算出避免漏列 |
  | 進度的保存、快照、變更偵測（R8） | 腳本 `save`、`check`（載入 005 的指紋與原子寫入） | 與 005 相同 |
  | 呼叫 `speckit-constitution`、`speckit-specify`，比對產生的內容與摘要（FR-011、FR-013） | SKILL.md | 呼叫 skill 與語意比對 |
  | 每份 spec 對應到哪個功能（`spec_dir`）（R7） | 腳本 `claim` | 可決定；寫錯會讓功能沿用到另一份 spec，而 006 察覺不到 |
  | 產生結果的驗證：既有文件未被改動、編號依相依順序、沒有多出或缺少（FR-012、FR-015） | 腳本 `verify`（載入 005 的 `verify_generated`） | 與 005 同一份判斷 |
  | 世代紀錄的寫入與驗證（FR-016） | 腳本 `lineage`（以 006 的程式驗證） | 必須能被 006 讀取；由 006 的程式證明 |
  | 切換目前的功能 | 腳本 `focus` | 同 005 |
  | 結束報告與下一步 `/sdd-drive`（FR-017） | SKILL.md；`verify` 與 `lineage` 輸出位置 | 報告是對話 |
  | 不帶入舊專案的 plan、tasks 與程式碼（FR-014） | 兩邊：SKILL.md 禁止讀取舊專案（除 US4 的匯出）；腳本只輸出養分與世代紀錄的內容 | 007 對舊專案的唯一來源就是腳本的輸出 |
  | 不修改舊專案（FR-004） | 兩邊：SKILL.md；腳本對舊專案只讀（測試以檔案樹快照證明） | 同 006 R5 |
  | 機密（原則 V） | 兩邊：SKILL.md；`save` 以 006 的機密樣式攔截 | 同 005 R8 |

- **Rationale**：與 005 R1、006 R1 相同的兩個問題：「錯了會不會在檔案上留下難以發現的後果」與「判斷是否需要理解語意」。
  本功能最不能錯的是世代紀錄：它被下一代讀取，錯誤要等到一兩代之後才會被發現，而且無法回頭修補。
  所以**世代紀錄的每個欄位都由腳本從「來源養分 + 維護者的決定」組成**，Claude 只送出決定與內容，不送出 `origin`、`revised`、
  `derived_from` 的值。
- **Alternatives considered**：由 Claude 組好整份世代紀錄、腳本只驗證：006 的規則表每一列都是機械性的轉換，交給 Claude
  只會多出出錯的機會；而且 006 的驗證本來就察覺不到其中幾種錯誤（R6），驗證不能取代正確的組成。

## R2 與 005、006 的程式共用

- **Decision**：`sdd_rebuild.py` 比照 004 的 `sdd_update.py` 載入 `sdd_init.py` 的方式，在執行時以 `importlib` 載入相鄰的
  `../sdd-export/scripts/sdd_export.py` 與 `../sdd-grill/scripts/sdd_grill.py`（路徑以本檔位置計算：`<本檔>/../../../sdd-export/...`；
  repo 中與部署後都成立）。**不修改 005 與 006 的腳本。**

  | 能力 | 來源 | 用到的函式（已存在，名稱以實作時為準） |
  |---|---|---|
  | 讀取並驗證養分、專用目錄的狀態 | 006 | `export_folder`、`load_nutrients` |
  | 讀取並驗證世代紀錄（舊專案的與自己剛組好的） | 006 | `load_lineage`、`lineage_problems` |
  | 世代紀錄的序列化 | 006 | `serialize(data, "lineage")`、`content_hash` |
  | 下一次匯出的模擬（R6 第三層） | 006 | `generation_problems` |
  | 項目的走訪與索引 | 006 | `walk_items`、`active_items`、`discarded_items`、`derived_sources` |
  | 差異（養分在接續時被改過） | 006 | `compute_diff` |
  | 機密樣式 | 006 | `looks_like_secret`（與 005 相同的樣式） |
  | id 的格式 | 006 | `valid_id` |
  | Spec Kit 的狀態、constitution 是否仍是範本、編號方式、既有 spec | 005 | `speckit_state`、`constitution_state`、`numbering`、`spec_number`、`existing_specs`、`spec_folders` |
  | 指紋、原子寫入、讀取 `feature.json` | 005 | `fingerprint`、`file_hash`、`atomic_write`、`read_feature_directory` |
  | 產生結果的驗證 | 005 | `verify_generated(root, progress)` |

  007 自己實作的：自己的進度資料夾（`.specify/sdd-rebuild/` 的衝突判定、`.gitignore` 的固定內容與清除；005 的
  `own_folder_state` 等函式把 sdd-grill 的檔名與 `.gitignore` 內容寫成模組常數，不能用參數換成 007 的）、進度的結構驗證、
  祖先表與遞移補入（R5）、世代紀錄的組成與 007 自己的寫入規則檢查（R6）、`claim`（R7）、`.sdd-rebuild/` 的寫入、`focus`、`clear`。
- **`verify_generated` 的共用方式**：它只讀進度中的 `baseline`、`constitution.action`，以及 `features[]` 的 `id`、`spec_dir`、
  `depends_on`。007 在呼叫前組一份同形的物件：只放「由這次重建產生 spec」的功能（對應既有 spec 的功能不放，見 R10），
  它們的 `depends_on` 中指向「對應既有 spec 的功能」的換成該 spec 資料夾路徑（005 的 `depends_on` 本來就接受既有 spec 的路徑）。
  這是使用 005 已公開的函式邊界，不需要修改 005。
- **載入失敗**：相鄰的檔案不存在或載入時拋出例外（例如只部署了 sdd-rebuild），`check` 以結束碼 3、`reason: "dependency"` 回報缺少哪一個，
  不做任何事。其餘指令同樣先載入，失敗時同樣回報。
- **世代規則只有一份實作**：006 的驗證（`lineage_problems` 與 `generation_problems`）在 007 寫入之前對組好的世代紀錄執行，
  不在 007 另寫一份；007 自己的檢查只涵蓋 006 定義為「007 寫入時 MUST 遵守、但 006 讀取時無法檢查」的部分（R6）。
- **需要修改的 005、006 檔案**：腳本與測試都不改。只有 006 的 `data-model.md` 依維護者核可的決定修改「007 寫入時 MUST 遵守的規則」表
  與表後的說明（逐字內容見 [plan.md](./plan.md) 的「對 006 文件的修改」），在 007 的實作階段進行，並以 007 的測試鎖定（R12）。
- **Rationale**：006 的 cli.md「以模組方式載入」與 R12、005 的 R6 都已為 007 保證「載入時不執行任何動作」與函式邊界；
  直接使用就是「格式只有一份實作」最可靠的做法。
- **Alternatives considered**：
  - 複製 006 的驗證到 007：兩份會漂移，正是任務說明要避免的。
  - 抽出共用的第三個資料夾：部署、測試與既有兩個 skill 的結構都要改，而載入相鄰檔案已能達到同樣的效果。
  - 修改 005 的 `own_folder_state` 讓資料夾名稱與 `.gitignore` 內容成為參數：可行，但 005 有完整的測試，007 需要的只是約 40 行，
    改動既有腳本的風險大於重複這段簡單的程式。
  - 007 以子程序呼叫 006 的 CLI（`uv run sdd_export.py validate --project <新專案>`）驗證世代紀錄：006 的 `validate` 驗證的是「養分草稿」，
    不是世代紀錄；要模擬下一次匯出也需要直接呼叫 `generation_problems`。

## R3 舊專案沒有養分時（US4、FR-003）

- **Decision**：
  1. `check --old <路徑>` 回報 `export_dir`（006 的定義）。`"none"` 或 `"empty"` 時，SKILL.md 先說明將對舊專案進行匯出、
     需要在舊專案寫入 `.sdd-export/`，以 AskUserQuestion 詢問「先匯出（建議）」或「停止」。停止：兩個專案都不寫入（US4-3）。
  2. 匯出的做法：**SKILL.md 不複製匯出規則**。它指示 Claude 用 Read 讀取已部署的 `${CLAUDE_SKILL_DIR}/../sdd-export/SKILL.md`
     （`check` 回報這個檔案是否存在），從頭到尾照它的九個階段與「Rules for the whole run」執行，只做下列固定的替換：
     - 腳本：`${CLAUDE_SKILL_DIR}/scripts/sdd_export.py` 換成 `${CLAUDE_SKILL_DIR}/../sdd-export/scripts/sdd_export.py`，
       每一個指令都加上 `--project "<舊專案>"`（006 R11 為此提供）。
     - 路徑：`files` 與 `check` 輸出的路徑相對於舊專案；Read、Grep 一次一個 `<舊專案>/<路徑>`；Glob 只在階段 2 協助選範圍時用於
       `<舊專案>` 之下的資料夾名稱。006 的「只讀 `files` 列出的檔案、不對資料夾執行 Grep」原樣適用。
     - git：006 允許清單中的四種形式，各自在 `git` 之後加上 `-C "<舊專案>"`，**其他部分完全相同**；允許清單以外的 git 指令與選項一律不用。
     - 「專案」一詞指舊專案；006 的「不建立任何檔案」同時適用於新專案：匯出期間不在新專案寫入任何東西，包括 007 自己的進度。
     - 006 的階段 9（結束報告）改為：回報 `.sdd-export/` 的位置與各類數量，說明養分可以在舊專案提交，然後回到 007 的流程；
       不建議執行 `/sdd-rebuild`（已經在執行）。
     - 006 的通則 7（確認前結束）適用時，重建一併結束：兩個專案都沒有寫入（US4-3）。
  3. 匯出完成後重新執行 `check --old`，`export_dir` 為 `"ours"` 才進入重建；否則依 `check` 的結果處理（contracts/skill.md 階段 1）。
- **一致性的保證**：匯出的規則只存在於 006 的 SKILL.md；007 的 SKILL.md 只寫替換表。007 的結構測試檢查替換表引用的 006 段落標題
  （`Rules for the whole run`、`Stage 9: Final report`）與四種 git 形式仍存在於 `home/skills/sdd-export/SKILL.md`，
  006 改寫這些段落而忘了 007 時，CI 會失敗。
- **機密與只讀的延續**：006 的機密與只讀保證來自三處：允許清單（只換成 `-C`，不放寬）、讀取範圍（只換成加上舊專案的前綴）、
  腳本（同一支腳本，`--project` 只改變根目錄）。三者在 007 觸發的匯出中都原樣成立。
- **Rationale**：006 是 `disable-model-invocation: true`，不能以 Skill 工具呼叫；006 R9 與 R11 已預期 007 以「腳本 + `--project` +
  依 006 SKILL.md 的規則」完成。讀取已部署的檔案而不是複製，是讓兩邊日後不會不一致的唯一方式。
- **Alternatives considered**：
  - 在 007 的 SKILL.md 複製一份匯出規則：006 修正規則時（006 已因 git 指令的機密外露修過一次）007 不會跟著修。
  - 請維護者切到舊專案執行 `/sdd-export` 再回來：可行（SKILL.md 也提供這個選項給不想在這個 session 匯出的維護者），
    但 US4 要求可以不切換。
  - 以 `cd <舊專案>` 後照 006 原文執行：Claude Code 的工作目錄與工具權限都以新專案為準，切換目錄在 Windows 也容易出錯（006 R11）。

## R4 讀取養分與舊專案的世代紀錄

- **Decision**：`check --old` 以 006 的程式讀取兩個檔案，並把讀到的內容放進輸出，**Claude 不以 Read 讀取舊專案的任何檔案**（US4 的匯出除外）。

  養分（`export_dir`，006 的定義）：

  | 值 | 下一步 |
  |---|---|
  | `ours` | 讀取；`nutrients` 為 `"edited"` 或 `"unknown"` 時告知維護者養分在匯出後被手動編輯過（內容仍通過 006 的驗證），繼續 |
  | `none`、`empty` | R3 的匯出 |
  | `conflict` | 停止；列出 `conflicts`，請維護者在舊專案處理後再執行（006 也會拒絕在這個狀態匯出） |
  | `unreadable`、`invalid` | 停止；列出原因或欄位路徑，請維護者修正，或在舊專案再執行 `/sdd-export`（006 也會因結構錯誤拒絕，需先修正） |
  | `newer` | 停止；說明養分來自較新的 sdd-export，請更新 skill 後再執行（Edge Cases「格式較新」）|

  格式「較舊」：schema 1 是第一個版本，沒有較舊的格式；`schema` 小於 1 或不是整數由 006 判為 `invalid`，處理同上（說明無法安全讀取，不猜測）。

  舊專案的世代紀錄（`old_lineage`，006 `load_lineage` 的值；只讀 `.sdd-rebuild/lineage.json` 這一個檔案）：

  | 值 | 判定 | 下一步 |
  |---|---|---|
  | `present`，且 `generation` 等於養分的 `generation` | 正常 | 祖先表納入它（R5） |
  | `present`，但 `generation` 與養分不同 | 世代紀錄在匯出後被換過 | 視為 `mismatch`，同下列「無法使用」 |
  | `none`，養分的 `generation` 為 1 | 正常（第一代沒有世代紀錄） | 祖先表只來自養分 |
  | `none`，養分的 `generation` ≥ 2 | 世代紀錄在匯出後被移除 | 同下列「無法使用」 |
  | `unreadable`、`invalid`、`conflict`、`newer` | 無法使用 | 見下 |

  「無法使用」時，SKILL.md 說明原因與影響（**只存在於舊世代紀錄的祖先會遺失**，之後那些 `id` 可能被重用、追溯會斷在這一代），
  以一題詢問：
  1. **停止，先處理舊專案的世代紀錄（建議）**：`newer` 時更新 skill；`unreadable`、`invalid` 時修正（列出 `errors` 的欄位路徑）；
     `none` 時從 git 歷史還原；`mismatch` 時確認養分與世代紀錄是否屬於同一個專案。處理後再執行 `/sdd-rebuild`，已保存的進度會接續。
  2. **只以養分建立祖先表並繼續**：進度記下 `old_lineage: "skipped"`（R8），最終摘要與結束報告都列出這個選擇；之後不再詢問。

  兩個選項都不會讓重建卡死，也不會在維護者不知情時略過。
- **Rationale**：006 對舊專案的世代紀錄無效時會拒絕匯出（結束碼 3），所以「養分有效但世代紀錄無效」只會發生在匯出之後有人動了世代紀錄；
  這種情況應該先修，但維護者可能已無法還原（例如舊專案已刪除歷史），所以保留明確的出路。
- **Alternatives considered**：
  - 世代紀錄無效時一律停止：維護者無法還原時重建就卡死，違反維護者的補充要求。
  - 無效時自動略過：祖先默默遺失，違反同一要求。
  - 以 Read 讀取舊專案的世代紀錄：多一條 Claude 讀舊專案的路徑；由腳本讀並經 006 驗證才可靠。

## R5 遞移帶入 `derived_from`（維護者 2026-11-20 的決定）

### 問題

006 的檢查發現：項目經過「合併再拆分」後，更早的來源 `id` 會從養分與世代紀錄中消失。第 2 代的 `status-list` 在第 3 代被合併進
`overview-list`，第 4 代重建時 `overview-list` 又被拆掉；拆出的新項目 `derived_from` 只有 `overview-list`，`status-list` 從此看不到，
之後可以被重用，追溯也斷在上一代。實測重現了這個問題（實測紀錄 1：不遞移時，第 4 代匯出的新需求取名 `status-list` 通過 006 的檢查）。

### 規則

- **Decision**（維護者核可，不改格式、不加欄位，`schema` 維持 1）：
  1. **祖先表**：`id → derived_from`，由下列有效項目（原則、功能、需求、教訓）的 `derived_from` 組成：
     來源養分的全部有效項目，以及舊專案的世代紀錄（`old_lineage` 為 `present` 且世代相符時）的全部有效項目。
     同一個 `id` 兩邊都有時，取兩者的聯集，養分的在前。
  2. **補入祖先**：給定一串「直接來源」，結果是：直接來源依給定的順序在前；接著依直接來源的順序，逐一把每個直接來源在祖先表中的
     `derived_from` 依記錄的順序展開，展開出的每個 `id` 再遞迴展開它自己的（深度優先、前序）；去重，保留第一次出現的位置。
     遇到已展開過的 `id` 不再展開（祖先表不可能有循環，但這一條保證即使手動編輯造成循環也會結束）。
  3. **適用到世代紀錄的每個有效項目**：
     - 原樣保留、修改後保留：直接來源是祖先表中該項目自己的清單（來源養分與舊世代紀錄的聯集，養分的在前），結果寫回（「沿用並補入祖先」）。
     - 合併、拆分：直接來源是維護者指定的來源 `id`（合併時是被合併的項目，拆分時是被拆分的項目），結果寫入。
     - 重建時新增：`derived_from` 為空，不補入。
  4. **捨棄**：捨棄紀錄沒有 `derived_from` 欄位，被捨棄項目的來源只保留到這次捨棄為止；被捨棄的項目本身仍在 `discarded`，
     它的 `id` 不能被重用（維護者接受的限制，見「取捨」）。
  5. **拆出且保留原項**：原項依「原樣保留」或「修改後保留」；拆出的項目依「拆分」：新取 `id`、`origin` 為這一代、
     `derived_from` 為原項 `id` 加上它的祖先。實測 006 接受這種寫法（實測紀錄 4）。

- **為什麼可行**（實測紀錄 1 至 5）：
  - 006 的 `lineage_problems` 不檢查 `derived_from` 的內容，補入後的世代紀錄 `load_lineage` 為 `present`。
  - 006 的規則 8（`derived-unknown`）允許「已出現在 L、N 中同一項目的 `derived_from`」的 `id`：下一代匯出時沿用世代紀錄中補齊的清單即通過。
  - 006 的規則 9（`id-reused`）把 L、N 中所有 `derived_from` 出現過的 `id` 視為已用過：補入後，歷史 `id` 留在世代紀錄裡，
    下一代以它們取名的新項目被擋下。
  - 006 的規則 5（`revision-unmarked`）只比較 `title`、`text`、`summary`：原樣保留的項目 `derived_from` 因補齊而變長，不會被當成修改。
- **去重、排序與增長**：清單只在合併或拆分時增長，每個 `id` 至多出現一次；長度上限是這個項目的全部歷史來源數，與世代數無關。
  對已經補齊的清單再套用一次，結果不變（冪等），所以原樣保留的項目在之後的重建中不會再變動。不刪減：刪掉任何一個都會讓它可被重用。
- **舊專案世代紀錄的作用**：匯出時的合併或拆分（006 的 SKILL.md 允許）只記下直接來源，006 的規則 8 也不允許在匯出時補入祖先
  （實測紀錄 3：`derived-unknown`）。被合併的項目若是上一次重建時記在世代紀錄中的項目，它的祖先仍在舊專案的世代紀錄裡；
  所以 007 除了養分，也讀取舊專案的世代紀錄建立祖先表，補上這一段（實測紀錄 5）。這是維護者選擇的做法（Q1 的 (a)），
  不改 006 的腳本與 SKILL.md。
- **006 寫入規則表的修改**：「原樣保留」「修改後保留」的 `derived_from` 由「沿用」改為「沿用並補入祖先」，「合併」「拆分」補上「並補入祖先」，
  並在表後說明祖先表、順序、捨棄與剩餘缺口。這是維護者核可的規則含義修改，逐字內容見 [plan.md](./plan.md)「對 006 文件的修改」。

### 取捨（維護者知悉並接受）

1. **同一代內的第二次匯出**：舊專案在同一代匯出兩次，第二次合併了第一次匯出才建立的項目時，第一次匯出記下的來源只在第一次的養分裡
   （第二次匯出取代了它），世代紀錄中也沒有，所以那些來源會遺失。單元測試以一個案例寫明這個行為（R12）。
2. **捨棄**：被捨棄項目的 `derived_from` 不會被保留；只靠它才在視野內的歷史 `id`，捨棄之後可能被重用。被捨棄的項目本身仍在 `discarded`。
   單元測試同樣寫明（R12）。
3. 兩項都寫進 007 的 README 與 006 data-model.md 的寫入規則註記。

- **Alternatives considered**：
  - 放寬 006 的規則 8，讓匯出時也補入祖先：完全補上第 1 項，但要改 006 的腳本、測試與 SKILL.md（維護者的 Q1 選項 (b)，未採用）。
  - 捨棄紀錄加上 `derived_from`：要改格式並把 `schema` 升為 2（維護者的 Q2 選項 (b)，未採用）。
  - 為歷史 `id` 另造捨棄紀錄：歷史 `id` 的 `origin` 與內容不在任何檔案中，寫進去就是猜測（違反原則 IV）。
  - 只記直接來源，靠舊專案追溯：舊專案不一定還在這台機器上（spec 的 Assumptions），追溯不能依賴它。

## R6 世代紀錄的組成、新取的 `id` 與三層驗證

### 組成

- **Decision**：進度中的「目標」（[data-model.md](./data-model.md)「目標」）是維護者決定後的原則、功能（含需求）、教訓清單，
  每個項目帶 `basis`：`inherit`（沿用來源養分中同 `id` 的項目，內容可以修改）、`derived`（合併或拆分，`from` 列出直接來源）、
  `new`（重建時新增）；另有 `discards`（來源養分中被捨棄的項目）。腳本依 006 的寫入規則表組成世代紀錄：

  | `basis` | `id` | `origin` | `revised` | `derived_from` | `source` | 功能的 `spec` |
  |---|---|---|---|---|---|---|
  | `inherit` | 來源的 | 來源的 | 來源的；`title`、`text`、`summary` 任一與來源不同時加上這一代（**由腳本比較決定**，Claude 不指定「修改」） | 來源的，補入祖先 | 來源的 | 來源的 |
  | `derived` | 新取 | 這一代 | 空 | `from`，補入祖先 | 第一個直接來源的 `source`（教訓沒有） | 第一個 `spec` 不為 `null` 的直接來源的；都沒有時 `null` |
  | `new` | 新取 | 這一代 | 空 | 空 | `"rebuild"` | `null` |

  - `discards` 的每一項成為捨棄紀錄：`kind` 依來源項目的種類、`origin` 為來源的、`discarded_in` 為這一代、`text` 為來源項目的
    `title`（需求取 `text` 的第一行，最多 80 字），可由維護者給的摘要取代、`reason` 為維護者的理由（沒有時「維護者決定捨棄」）。
  - 來源養分的 `discarded` 全部原樣帶入，依原順序排在前面，這一代的捨棄接在後面。
  - `merged` 與 `split` 不另設 `basis`：`from` 有兩個以上的直接來源是合併；一個直接來源而該來源也出現在其他目標的 `from`，
    或該來源仍被保留，是拆分。摘要中的分類由腳本依此算出（`preview` 的 `summary`）。
  - `generation` = 來源養分的 `generation` + 1；`source` 為 `{"project": 養分的 project, "generation": 養分的 generation,
    "nutrients_schema": 養分的 schema}`；`rebuilt_at` 為維護者確認摘要當天的 UTC 日期（記在進度，接續時不變，R9）。
  - 功能的 `spec_dir` 來自 `claim`（R7）或對應的既有 spec（R10）；`depends_on` 由目標給定（指向排在前面的功能）。
  - 待確認的項目（`status: "pending"`）：`pending_decided` MUST 包含每一個來源養分中待確認的 `id`；寫入時一律去掉 `status` 與 `evidence`
    （FR-018，006 寫入規則表的最後一列）。

### 新取的 `id`

- **Decision**：`derived` 與 `new` 的 `id` MUST NOT 是下列任何一個（集合由腳本計算）：
  1. 來源養分的有效項目 `id`、`discarded` 的 `id`、所有 `derived_from` 中的 `id`；
  2. 舊專案世代紀錄（使用時）的同三類；
  3. 祖先表展開後出現的所有 `id`；
  4. 這份世代紀錄中其他項目的 `id`，以及這份世代紀錄**所有項目補齊後的 `derived_from` 中的 `id`**——
     「重用同一份紀錄裡其他項目 `derived_from` 中的 `id`」006 察覺不到（006 的規則 9 只看前代的 L、N），由 007 檢查。
- `inherit` 的 `id` MUST 是來源養分的有效項目，且種類相同；同一個來源 `id` 至多被 `inherit` 一次。

### 每個來源項目都有去處

- **Decision**：來源養分的每個有效項目 MUST 至少屬於下列之一：被某個目標 `inherit`、出現在某個目標的 `from`、在 `discards` 中。
  `discards` 中的 `id` MUST NOT 同時被 `inherit` 或出現在 `from`（被捨棄的項目不會以來源的身分延續）。
  這是 006 的寫入規則表最後一段「每一個有效項目 MUST 對應到上表其中一列」，不滿足時 006 下一次匯出會以規則 2 拒絕。

### 三層驗證

`preview`（確認前）與 `lineage`（寫入前）都執行：

1. **007 的寫入規則**：上述三節，加上結構（欄位、`depends_on` 指向前面的功能、`id` 格式）與機密樣式。
2. **006 的結構驗證**：組好的世代紀錄以 006 的 `lineage_problems` 檢查，MUST 沒有任何問題（等同於 006 `check` 讀到 `lineage: "present"`）。
3. **006 的下一次匯出模擬**：以組好的世代紀錄 L 本身當作下一次匯出的草稿（世代相同、內容完全沿用），以 006 的
   `generation_problems(L, L, None)` 檢查，MUST 沒有任何問題。這證明重建後不做任何手動補充，新專案即可匯出（SC-006），
   也涵蓋「補齊後變長的 `derived_from` 不會被規則 5、8 當成問題」（維護者的補充要求 3）。

任何一層有問題就不寫入。第 1 層的問題在 `preview` 回報給 Claude 修正目標；第 2、3 層若在第 1 層通過後仍有問題，代表 007 的組成與
006 的契約不一致，是 007 的缺陷：`lineage` 以結束碼 1、`reason: "internal"` 回報，SKILL.md 依 contracts/skill.md 停止並請維護者回報。

- **Rationale**：第 1 層是 006 規則表中 006 自己無法檢查的部分；第 2、3 層直接用 006 的程式，世代規則只有一份實作。
- **Alternatives considered**：把來源養分當成 L、新世代紀錄當成草稿，直接套用 006 的 `generation_problems`：規則 2 至 7、9 的語意相近，
  但規則 8 不允許補入的祖先（祖先不是 L、N 的有效項目，也不是新項目「已記錄」的來源），會誤判；而且把養分當成世代紀錄是借用，
  006 改版時容易無聲地失效。

## R7 spec 資料夾的對應（`claim`）

- **Decision**：每次 `speckit-specify` 完成後執行 `claim <功能 id>`，由腳本決定 `spec_dir`：
  1. 候選 = `specs/` 下含 `spec.md`、不在 `baseline`、也還沒有被任何功能記錄的資料夾。
  2. 讀 `.specify/feature.json` 的 `feature_directory`（`speckit-specify` 剛寫入它建立的資料夾，005 R4 查到的事實）。
  3. 候選恰好一個且等於 `feature_directory`：記入該功能的 `spec_dir` 並保存進度，輸出資料夾。
  4. 其他情況不記錄，以結束碼 1 回報 `reason`：`none`（沒有新的 spec：產生失敗；另列出不在 `baseline`、沒有 `spec.md` 的資料夾
    `incomplete`）、`ambiguous`（候選不止一個，例如維護者在途中自己建了 spec）、`mismatch`（候選一個但與 `feature_directory` 不同）。
  5. `ambiguous` 或 `mismatch` 時，SKILL.md 列出候選並詢問維護者哪一份屬於這個功能（建議：`feature_directory` 指向的那份，
    並說明比對內容後的判斷）；維護者選定後以 `claim <功能 id> --dir <資料夾>` 記錄（`--dir` 必須是候選之一）。
  6. 前提：進度已確認；該功能不是對應既有 spec 的功能；依目標順序排在它前面、需要產生的功能都已有 `spec_dir`（一次一個，順序即編號）。
- **Rationale**：005 由 Claude 抄寫 `speckit-specify` 回報的路徑，依賴 Claude 不抄錯。007 的世代紀錄把 `spec_dir` 寫進入庫的檔案，
  寫錯會讓下一代把功能沿用到另一份 spec，而 006 只檢查 `spec_dir` 是 `specs/` 下的一層資料夾，察覺不到。
  以「新出現的資料夾」與「Spec Kit 自己記下的目前功能」兩個獨立的事實交叉確認，才可靠。`verify` 之後仍檢查編號與相依順序。
- **Alternatives considered**：
  - 由 007 先計算編號並以 `SPECIFY_FEATURE_DIRECTORY` 指定：多一份 Spec Kit 的編號邏輯（005 R4 已否決）。
  - 比對 spec 的內容與功能的標題：`speckit-specify` 會改寫標題，無法可靠比對；內容比對由 Claude 在產生後進行（FR-013 的比對）。

## R8 進度的位置、格式、快照與變更偵測

- **Decision**：
  - 位置：新專案的 `.specify/sdd-rebuild/progress.json`，同資料夾有固定內容的 `.gitignore`（`# Created by sdd-rebuild. Local rebuild progress; never committed.`
    與 `*`），與 005 R2 相同的自我忽略方式；資料夾只屬於 sdd-rebuild，有其他檔案時視為衝突。這符合原則 I（在 `.specify/` 新增自己的檔案，
    以資料夾名稱與 `.gitignore` 的註解記錄歸屬）。
  - 第一次保存的時機：養分讀取成功、維護者開始決定之後。匯出（R3）期間與之前不保存（US4-3：拒絕匯出時兩個專案都沒有寫入）。
  - **快照**：第一次 `save` 時，腳本把讀到的養分完整內容、舊專案世代紀錄的內容（使用時）與兩者的雜湊記入進度的 `source`，之後只有
    `save --refresh-source` 會換成目前的內容（只在確認之前允許）。之後的 `preview`、`lineage` 一律以快照組成。
    Claude 不轉抄養分，腳本取得的就是 006 驗證過的內容。
  - **舊專案的路徑**記為絕對路徑：進度不入庫，原則 V 的「不提交機器專屬路徑」不受影響；世代紀錄中只有養分的 `project` 名稱。
  - **變更偵測**：
    - 舊專案：`check` 重新讀取並比較雜湊，輸出 `source_changed`（`nutrients`、`lineage`）與 `source_diff`（006 的 `compute_diff`，快照 → 目前）。
      舊專案不存在或無法讀取時 `source_state` 為 `"unavailable"`：快照已足以完成重建，不影響接續。
    - 新專案：同 005 的指紋（constitution、每份 spec.md、HEAD），`check` 輸出 `changed`；確認後另有 `baseline`，由 `verify` 檢查。
  - 機密：`save` 以 006 的機密樣式掃描 Claude 送來的所有字串；快照是 006 驗證過、已經過機密攔截的養分。
- **Rationale**：任務說明要求比照 005；R5 需要的祖先表也必須在接續時與當初一致，所以以快照固定來源，而不是每次重讀舊專案。
- **Alternatives considered**：
  - 放在 `.sdd-rebuild/`（世代紀錄的資料夾）：那個資料夾入庫，要在裡面放一份只忽略進度的 `.gitignore`，006 也規定該資料夾只有 007 的檔案、
    006 只讀 `lineage.json`；混放入庫與不入庫的檔案容易被 `git add -A` 誤加。
  - 不存快照、每次重讀舊專案：接續時舊專案已變或已不存在，決定與來源對不上。

## R9 產生文件的做法、中斷與接續

- **Decision**：確認後依下列步驟，每一步完成就保存；任何一步失敗都停在原地，進度保留，再執行 `/sdd-rebuild` 從停下的地方繼續。

  | 步驟 | 進度記錄 | 腳本 |
  |---|---|---|
  | 1. 確認 | `phase: "confirmed"`；腳本記下 `baseline`（同 005）與 `rebuilt_at` | `save` |
  | 2. constitution（`action` 為 `create` 或 `amend`） | `generation.constitution`：`pending` → `written`（呼叫完成）→ `reviewed`（比對完成） | `save` |
  | 3. 逐份 spec | 每個功能：`spec_dir`（`claim`）→ `reviewed: true`（比對完成） | `claim`、`save` |
  | 4. 驗證 | | `verify` |
  | 5. 世代紀錄 | 腳本記下寫入內容的雜湊 `lineage_written` | `lineage` |
  | 6. 目前的功能 | | `focus` |
  | 7. 清除進度 | | `clear` |

  接續時依進度判斷下一步（contracts/skill.md 的「接續」列出每一種）：
  - constitution 為 `written` 尚未 `reviewed`：先做比對，不重新呼叫 `speckit-constitution`。
  - 有功能已 `claim` 尚未 `reviewed`：先比對那一份。
  - 下一個功能尚未 `claim`，但 `specs/` 已有符合條件的新資料夾（呼叫後中斷）：先 `claim`，不重新產生（Edge Cases「不重複產生已存在的 spec」）。
  - 世代紀錄已寫入但進度沒有記下（寫入後、保存前中斷）：`lineage` 重新組成，內容與檔案相同時視為已寫入（冪等）。
  - 新專案的文件在中途被手動改過：`verify` 的 `existing-spec-changed`、`constitution-changed`、`spec-missing` 等；
    依 005 的兩條出路（還原或重新開始），另外對「已產生的 spec 被刪除或改動」與「編號與預期不同」列出各自的下一步。
  - 舊專案的養分已變：確認後一律以快照繼續，只告知差異（確認的是快照的內容）。
- **確認後改變主意**：constitution 與 spec 都尚未產生時，可以改回 `deciding`（同 005，腳本只在沒有任何 `spec_dir`、
  `generation.constitution` 為 `pending` 時允許）；已產生任何文件時，選項是「依確認的內容產生完（建議）」「停止，保留已產生的文件」
  「重新開始」；世代紀錄已寫入後不能重新開始（見 R10 的「已重建過的專案」）。
- **重新開始**：`clear` 清除進度；已產生的 constitution 與 spec 不刪除（原則 III：它們由 Spec Kit 產生），下一次重建把它們當成既有內容（R10）。
  世代紀錄尚未寫入，所以不會留下不完整的世代紀錄（Edge Cases）。
- **Rationale**：005 的四個問題都在「確認之後、完成之前」：比對步驟沒有狀態、`spec_dir` 與實際資料夾不一致、改回討論後基準失效、
  失敗後的出路不明。007 把每一步的完成都記進進度、以 `claim` 取代抄寫、世代紀錄寫入冪等，讓每一個中斷點都有可判斷的下一步。
- **Alternatives considered**：世代紀錄在產生 spec 之前就寫入（`spec_dir` 預留）：中斷時留下指向不存在資料夾的世代紀錄，
  違反 Edge Cases「不留下不完整的世代紀錄」。

## R10 新專案已有內容（FR-015）

- **Decision**：
  - **constitution**：同 005 的 `action`：沒有或仍是範本時 `create`；已寫入時預設 `keep`，維護者同意修訂時 `amend`，只傳入要新增或修改的部分。
    養分的原則逐項與既有 constitution 比對，呈現差異；已涵蓋的原則仍以 `inherit` 記入世代紀錄（它在這一代仍然有效）。
  - **spec**：既有 spec 不覆蓋、不修改。養分的每個功能逐項比對既有 spec，維護者決定：
    1. **對應到既有 spec**：功能以 `inherit` 或 `derived` 記入目標，`existing_spec` 指向該資料夾，不再產生；世代紀錄的 `spec_dir` 就是它。
       這些功能 MUST 排在需要產生的功能之前（它們的編號較小），腳本檢查。
    2. **產生新的 spec**：編號接在既有之後（Spec Kit 的行為）。
    3. **捨棄**。
  - 與養分無關的既有 spec 不記入世代紀錄；下一次匯出時 006 把它們當成那一代新增的功能（006 的 `check` 會列為 `in_lineage: false`）。
  - **已重建過的專案**：新專案已有 `.sdd-rebuild/`（有世代紀錄）而沒有進度時，`check` 回報 `rebuild_dir: "present"`，SKILL.md 停止：
    一個專案只會被重建一次；要加入新需求用 `/sdd-grill`，要再生下一代就在這個專案執行 `/sdd-export`、另開新專案。
    `.sdd-rebuild/` 有世代紀錄以外的不明檔案，或世代紀錄不是 007 寫的：`conflict`，停止並列出。
- **Rationale**：FR-015 只要求不覆蓋、提出差異；對應既有 spec 讓追溯不因「新專案先建了部分 spec」而斷掉。
- **Alternatives considered**：既有 spec 一律視為無關：同一個需求在世代紀錄中消失（只能捨棄），追溯斷掉。

## R11 新需求與教訓引發的調整

- **Decision**：
  - 新需求：SKILL.md 指示讀取 `${CLAUDE_SKILL_DIR}/../sdd-grill/SKILL.md` 的「Rules for questioning」段落，對每個新需求套用
    （一次一題、附建議、追問含糊的回答、指出矛盾、技術選型只記錄不討論、機密只記需要什麼）；不使用其中關於 sdd-grill 自己的進度與指令的部分。
    釐清後成為 `basis: "new"` 的功能或需求，並排入相依順序。技術選型與延後事項記在 `for_plan` 與 `deferred`（同 005），產生 spec 時寫入 Assumptions。
  - 教訓引發的調整：每一項記在進度的 `adjustments`（來源教訓的 `id`、調整內容、是否採用），一題一項詢問；採用時以對應的修改或新增反映在目標中。
    教訓本身是否仍然適用另外決定（適用的 `inherit`，不適用的 `discards`）。
  - 矛盾：調整之間、或調整與保留的原則衝突時，指出兩邊並詢問取捨（US2-4）。
- **Rationale**：spec 寫明新需求「像追問新需求一樣釐清」；追問規則只存在於 005 的 SKILL.md，讀取已部署的檔案與 R3 同樣避免兩份規則不一致。
  結構測試檢查該段落標題仍存在。
- **Alternatives considered**：以 Skill 工具呼叫 `sdd-grill`：它會自己產生 spec、清除自己的進度，與 007 的流程衝突。

## R12 自動測試的範圍

constitution 原則 II 要求每個功能 MUST 有自動測試並在兩個平台的 CI 通過。與 005 R3、006 R8 相同，**對話行為不在 CI 驗證**；
CI 證明腳本的行為與「必要的指示存在於 SKILL.md」。

- **Decision**：

  | 類別 | 測試檔 | 涵蓋內容 |
  |---|---|---|
  | 腳本的單元測試 | `tests/unit/test_sdd_rebuild.py` | 載入相鄰的 005、006 與載入失敗；`check` 的每一種狀態（Spec Kit、舊專案路徑、養分、舊世代紀錄、`.sdd-rebuild/`、進度、變更）；`save` 的驗證、快照、`--refresh-source`、衝突、機密；祖先表與補入（順序、去重、冪等、遞迴、循環保護）；`preview` 的組成與每一條 007 寫入規則；`claim` 的每一種結果；`verify`（含對應既有 spec）；`lineage` 的三層驗證、冪等、原子寫入、衝突；`focus`；`clear`；對舊專案只讀（執行前後檔案樹相同）；序列化與固定測試資料逐位元組相同 |
  | 多代來回 | `tests/unit/test_sdd_rebuild_generations.py` | 以真實的 006 腳本與 007 腳本在暫存目錄交替執行（Spec Kit 的 spec 產生以建立資料夾與 `feature.json` 模擬）：第 1 代匯出 → 重建 → 匯出 → … 到第 5 代，見下 |
  | skill 的結構與內容檢查 | `tests/unit/test_sdd_rebuild_skill.py` | 資料夾只有三個檔案、frontmatter、英文、沒有絕對路徑與信箱、必要指示的關鍵句與順序（contracts/skill.md）、README 是繁體中文且涵蓋必要內容（含兩項取捨）、腳本只用標準函式庫且訊息是英文；**跨 skill 的一致性**：引用的 006 段落標題與 git 允許清單、005 的「Rules for questioning」仍存在；006 data-model.md 的寫入規則表含有「沿用並補入祖先」等文字（鎖定 R5 的契約修改） |
  | 人工驗收 | [quickstart.md](./quickstart.md) | 實際對話：逐項決定、新需求、教訓、確認前不寫入、中斷與接續、US4 的匯出 |

- **多代來回的情境**（每一代都斷言：007 寫出的世代紀錄 006 `check` 為 `present`、`generation` 加一；下一次 006 匯出的 `validate` 通過）：

  | 代 | 舊專案的操作 | 重建的決定 |
  |---|---|---|
  | 1 → 2 | 第 1 代匯出（含一個待確認的需求） | 保留、修改、捨棄、新增；待確認的需求決定保留 |
  | 2 → 3 | 第 2 代匯出 | 合併（兩個功能與兩個需求）；拆出且保留原項 |
  | 3 → 4 | 第 3 代匯出 | 把第 3 代合併出的項目拆開（合併後再拆分）：斷言拆出項目的 `derived_from` 含第 2 代的 `status-list`；以 `status-list` 取名的新項目在第 4 代的匯出被 006 擋下 |
  | 4 → 5 | 第 4 代匯出時合併兩個項目（匯出時的合併） | 保留匯出時合併出的項目：斷言補入的祖先來自舊專案的世代紀錄（Q1 的 (a)），且原樣保留的項目 `derived_from` 變長後，下一代匯出不被規則 5 或其他規則拒絕（補充要求 3） |

  另外三個獨立案例：
  - **SC-006 的追溯**：第 5 代世代紀錄中每個有效項目，以 `derived_from` 加上 `origin` 都能追到第 1 代養分中的 `id`（或本身就是那一代建立的）。
  - **已知限制 1**：同一代匯出兩次，第二次合併第一次匯出才建立的項目；斷言重建後第一次匯出的來源不在世代紀錄中（測試名稱與註解寫明這是接受的限制）。
  - **已知限制 2**：捨棄帶有 `derived_from` 的項目；斷言它的來源不再出現，且那些 `id` 在下一代可被 006 接受為新項目（同樣寫明是接受的限制）。
  - 對照：同樣的「合併後再拆分」在**不補入**祖先時，`status-list` 可被重用（證明補入是必要的；以直接組出的世代紀錄執行，不經 007 的組成）。

- **FR 與驗證方式的對照**：

  | FR | 單元測試 | 結構／內容檢查 | 人工驗收 |
  |---|---|---|---|
  | FR-001 以路徑啟動 | `check --old` | `argument-hint`；沒有路徑時詢問、不搜尋 | 情境 1 |
  | FR-002 需要 Spec Kit | `check` 結束碼 3 | 指示：請先 `/sdd-init` | 情境 7 |
  | FR-003 讀養分或先匯出 | 養分各狀態；`export_skill` | 指示：讀 `../sdd-export/SKILL.md` 與替換表；006 段落仍存在 | 情境 5 |
  | FR-004 不修改舊專案 | 只讀的檔案樹快照 | 指示：不讀不寫舊專案，匯出除外 | 情境 1、5 |
  | FR-005 逐項決定 | `preview` 的去處規則 | 指示：原樣或逐項；五種處置 | 情境 2 |
  | FR-006 新需求 | `basis: "new"` 的組成 | 指示：讀 005 的追問規則 | 情境 2 |
  | FR-007 教訓的調整 | `adjustments` 的結構 | 指示：單獨呈現、標示來源 | 情境 2 |
  | FR-008 一次一題、矛盾 | | 指示存在 | 情境 2 |
  | FR-009 最終摘要 | `preview` 的 `summary` | 指示：五類、教訓、順序 | 情境 1、2 |
  | FR-010 確認前不寫入 | 除 `save` 外確認前的指令不寫入；`lineage` 要求已確認 | 指示順序：確認在產生之前 | 情境 1 |
  | FR-011 透過 Spec Kit | | 指示：`speckit-constitution`、`speckit-specify`，不手寫 | 情境 1 |
  | FR-012 依相依順序重新編號 | `verify` 的 `order`、`dependency-order`；`preview` 的相依順序 | 指示：一次一個、依順序 | 情境 1 |
  | FR-013 constitution 只含確認的原則 | | 指示：雙向比對 | 情境 1 |
  | FR-014 不帶入 plan、tasks、程式碼 | 世代紀錄沒有多出的欄位（006 驗證） | 指示：不讀舊專案、只傳確認內容 | 情境 1 |
  | FR-015 不覆蓋既有 | `verify` 的 `existing-spec-changed`；對應既有 spec；已重建過的專案 | 指示：只提差異 | 情境 6 |
  | FR-016 世代紀錄 | 組成、三層驗證、多代來回 | 指示：`lineage` | 情境 3 |
  | FR-017 結束報告 | `verify`、`lineage`、`focus` 的輸出 | 指示：位置、順序、`/sdd-drive`、停止 | 情境 1 |
  | FR-018 待確認逐項決定 | `pending_decided`；不以 `pending` 寫入 | 指示：一題一項 | 情境 2 |
  | FR-019 無效時停止 | 路徑、養分、Spec Kit 的錯誤狀態 | 指示存在 | 情境 7 |
  | FR-020 跨平台 | 見下 | | |
  | FR-021 文件語言 | 進度的 `language` | 指示：繁體中文，除非既有文件是其他語言 | 情境 1 |
  | FR-022 英文與 README | | 英文、無 CJK；README 繁體中文 | |

- **FR-020 與 CI**：**不新增** CI job，也不修改 cross-platform 系列 job；以 `test` job 在兩個平台執行的單元測試驗證：
  1. 006 的固定測試資料 `tests/unit/fixtures/sdd_export/nutrients.json` 是兩個平台的 006 都會逐位元組寫出的內容（006 的測試已保證）；
     007 以它重建，寫出的 `lineage.json` 在兩個平台都逐位元組等於 `tests/unit/fixtures/sdd_rebuild/` 中的一份固定資料。
     「一個平台匯出、另一個平台重建」因此等價於「兩個平台都從同一份位元組重建出同一份位元組」。
  2. 把養分與舊世代紀錄換成 CRLF 的版本，重建結果與 LF 版本逐位元組相同（Windows 的 checkout 可能改成 CRLF）。
  3. `--old` 接受該平台的路徑寫法（Windows 的反斜線與磁碟代號，以 `tmp_path` 測試）；相同目錄、互相包含的判定在 Windows 不分大小寫。
  4. `.sdd-rebuild/.gitattributes` 讓世代紀錄在 `core.autocrlf=true` 的 clone 中維持 LF（同 006 R8 第 3 點）。
  理由同 006 R8：世代紀錄是腳本以固定規則寫出的純文字，「兩個平台的輸出都等於同一份固定的位元組」比交換 artifact 更直接。

- **Alternatives considered**：在 CI 以非互動模式執行 Claude Code：同 005 R3 與 006 R8，不採用。新增 cross-platform job 交換世代紀錄：
  驗證內容與第 1 點相同，代價是兩個 job 與 artifact。

## R13 frontmatter、結束碼、不提交

- **frontmatter**：`name: sdd-rebuild`；`description` 為英文，說明在新專案以舊專案的養分重建 constitution 與 spec、留下世代紀錄、
  需要 Spec Kit、確認前不寫入；`argument-hint: "<old project path>"`；`disable-model-invocation: true`。
  理由同 006 R9：`home/CLAUDE.md` 寫「請我在新專案執行 `/sdd-rebuild`」，由維護者明確啟動；誤觸發的代價是讀取另一個專案並可能在其中匯出。
- **結束碼**：0 成功；1 用法錯誤、輸入無效或含機密、規則不符、`claim` 或 `verify` 失敗、衝突、`internal`；
  3 前置條件不成立（Spec Kit、相鄰的 skill、舊專案路徑、養分無法讀取、已重建過）。2 保留、4 不使用（同 003 至 006）。
- **不提交**：同 005：SKILL.md 只在維護者自己的指示要求時才提交產生的文件與世代紀錄，MUST NOT push；結束報告 MUST 提醒
  `.sdd-rebuild/lineage.json` 要入庫（006 規定；不入庫的話換一台機器匯出就變成第一代）。舊專案一律不提交（006 R13）。

## 實測紀錄

實驗腳本在 `/tmp/exp007/`，以 importlib 載入本 repo 的 `sdd_export.py`，以 `tests/unit/fixtures/sdd_export/gen3-draft.json`
（第 3 代的養分：`overview` 由 `status`、`report` 合併，`overview-list` 由 `status-list`、`report-diff` 合併）為來源組出第 4 代的世代紀錄，
寫進暫存的假專案後以 `load_lineage` 讀取；下一代的匯出以 `validate_draft(draft, L, N, None)` 檢查（`root` 為 `None` 只略過看檔案的檢查，
世代規則完整執行）。

1. **合併後再拆分**（第 4 代把 `overview` 拆成 `overview-files`、`overview-diff`，需求 `overview-list` 拆成 `files-list`、`diff-mark`）：

   ```text
   遞移帶入：files-list derived_from = ['overview-list', 'status-list', 'report-diff']
     load_lineage → present
     第 4 代匯出、全部保留 → OK
     第 4 代匯出、新需求取名 status-list / overview-list / report-diff → id-reused（三個都被擋）
   不遞移（對照）：files-list derived_from = ['overview-list']
     load_lineage → present；全部保留 → OK
     新需求取名 status-list → OK（問題重現）；report-diff → OK；overview-list → id-reused
   ```

2. **再下一代**（第 5 代把 `files-list`、`diff-mark` 合併成 `deploy-view`）：
   `derived_from = ['files-list', 'overview-list', 'status-list', 'report-diff', 'diff-mark']`（此實驗的展開順序為逐一交錯；
   設計採「直接來源在前」，見 R5）；`load_lineage` → present；第 5 代匯出全部保留 → OK；新需求取名 `status-list`、`overview-list`、
   `files-list`、`overview`、`status` → 全部 `id-reused`。
3. **匯出時的合併**：第 4 代匯出時把 `files-list`、`diff-mark` 合併成 `files-all`：只列直接來源 → OK；遞移帶入 →
   `derived-unknown`（三個祖先）。所以匯出時無法補入，由 007 下一次重建時補（R5）。
4. **拆出且保留原項**：保留 `overview`（含 `overview-list`），另拆出 `overview-diff`（`derived_from: ['overview', 'status', 'report']`），
   需求 `diff-mark`（`derived_from: ['overview-list', 'status-list', 'report-diff']`）：`load_lineage` → present；第 4 代匯出全部保留 → OK。
5. **以舊專案的世代紀錄補入**（實測 3 的養分，第 5 代原樣保留 `files-all`）：以「第 4 代養分 + 第 4 代世代紀錄」建立祖先表，
   `files-all` 的 `derived_from` 由 `['files-list', 'diff-mark']` 補成 `['files-list', 'overview-list', 'status-list', 'report-diff', 'diff-mark']`：
   `load_lineage` → present；第 5 代匯出全部保留 → OK（變長的 `derived_from` 沒有被規則 5 或其他規則拒絕）；新需求取名 `status-list` → `id-reused`。
6. **捨棄**：第 4 代捨棄兩個拆出的項目（其他項目都沒有記下 `status-list`）：`load_lineage` → present；匯出 → OK；新需求取名 `status-list` → OK
   （已知限制 2 的行為，維護者接受）。
