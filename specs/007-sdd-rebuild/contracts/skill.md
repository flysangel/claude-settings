# Contract: sdd-rebuild skill 的結構與必要指示

部署來源是 `home/skills/sdd-rebuild/`，安裝後位於 `~/.claude/skills/sdd-rebuild/`。
`tests/unit/test_sdd_rebuild_skill.py` 依此檢查。SKILL.md 與腳本的分工見 [research.md](../research.md) 的 R1。

本文件依階段列出 SKILL.md 必須包含的指示，並且**每個階段都列出每一種結果的下一步**：成功、每一種失敗、維護者改變主意、
中途結束後接續。沒有任何一個結果的下一步是「未定義」；實作 SKILL.md 時 MUST 逐一涵蓋。腳本回傳本文件沒有提到的結束碼或 `reason` 時，
SKILL.md MUST 指示：告訴維護者發生了什麼、哪些已寫入（依進度）、然後停止（通則 12）。

## 檔案

| 檔案 | 語言 | 內容 |
|---|---|---|
| `SKILL.md` | 英文 | 給 Claude 的指示 |
| `README.md` | 繁體中文 | 給維護者的簡述 |
| `scripts/sdd_rebuild.py` | 英文（訊息與註解） | 介面見 [cli.md](./cli.md) |

資料夾內沒有其他檔案。

## SKILL.md 的 frontmatter

| 欄位 | 值 |
|---|---|
| `name` | `sdd-rebuild` |
| `description` | 英文；在新專案以舊專案的養分（`/sdd-export` 的產出）重建 constitution 與 spec：逐項保留、修改、合併、捨棄並加入新需求，確認後由 Spec Kit 產生，並留下世代紀錄；在新專案執行、需要 Spec Kit、確認前不寫入（R13） |
| `argument-hint` | `"<old project path>"` |
| `disable-model-invocation` | `true` |

沒有其他欄位。

## SKILL.md 的內文

每一項都 MUST 出現；結構測試以關鍵字或關鍵句檢查（括號內「字樣」），並檢查標示「順序」的段落先後。腳本一律以
`uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_rebuild.py" <command>` 在新專案（目前目錄）執行。

### 通則（任何階段都適用）

1. **兩個專案**：目前目錄是新專案；舊專案只經由腳本讀取。MUST NOT 以 Read、Grep、Glob 或任何指令讀取舊專案的檔案（plan、tasks、程式碼、
   spec 都不讀），唯一的例外是階段 2 的匯出（FR-004、FR-014；字樣：`old project`、`plan`、`tasks`）。新專案只讀 constitution 與 `specs/`
   下的 `spec.md`；MUST NOT 開啟新專案的 `.sdd-rebuild/lineage.json`（世代編號由 `check` 的 `rebuilt_generation` 提供）。
2. **不修改舊專案**：除了階段 2 經維護者確認的匯出，MUST NOT 在舊專案建立、修改或刪除任何檔案，MUST NOT 在舊專案執行任何 git 指令以外的指令
   （FR-004；字樣：`never write`）。
3. **確認前不寫入**：最終摘要確認之前，MUST NOT 呼叫 `speckit-*`、`claim`、`lineage`、`focus`，MUST NOT 以任何方式修改 constitution、spec、
   `.sdd-rebuild/`；唯一的寫入是 `save` 的進度（FR-010、原則 IV；字樣：`confirm`）。
4. **不手寫 Spec Kit 的檔案**：constitution 與 spec 只透過 `speckit-constitution`、`speckit-specify` 產生；MUST NOT 手寫、補寫或刪除它們；
   比對時對 spec 的修改只限 `claim` 為該功能記錄的那一份，`specs/` 下其他資料夾屬於維護者（原則 III）；
   MUST NOT 自己修改 `.specify/feature.json`、`.sdd-rebuild/` 或進度檔（只經由腳本）（FR-011、原則 I、III；字樣：`speckit-constitution`、`speckit-specify`）。
5. **不自己算世代紀錄**：`origin`、`revised`、`derived_from`、`spec_dir` 由腳本決定；Claude 只在進度中寫決定（`basis`、`from`）與內容
   （R1、R5；字樣：`derived_from`）。
6. **提問**：需要維護者決定時使用 AskUserQuestion，建議的選項排第一並附理由；一次一個決定；性質相同的是非題 MAY 一題複選；
   工具不能用時改用文字，仍一次一題並附建議（FR-008；字樣：`AskUserQuestion`）。
7. **語言**：對話依全域設定；產生的文件依 FR-021（繁體中文，規範詞保留英文，除非新專案既有文件使用其他語言）；進度與世代紀錄的文字
   維持養分的繁體中文（006 schema 1 固定）（字樣：`Traditional Chinese`）。
8. **機密**：機密值 MUST NOT 出現在對話、進度、產生的文件與世代紀錄中；只記錄「需要什麼」（原則 V；字樣：`secret`）。
   腳本也掃描從舊專案與進度讀到的內容，命中時只給 `check: "secret"` 與欄位路徑；向維護者說明是哪個檔案、哪個路徑，
   MUST NOT 為了找出值而開啟該檔案（舊專案的 `nutrients.json`、`lineage.json`、新專案的進度檔與 `.sdd-rebuild/lineage.json` 只經由腳本的輸出取得）。
9. **保存**：每一個決定之後以 `save` 保存完整進度（stdin，quoted heredoc），讓中斷後能接續（字樣：`save`、`heredoc`）。
10. **維護者在確認前要求結束**：確認進度已保存，告訴維護者再執行 `/sdd-rebuild` 會接續、或在接續時選擇重新開始；
    不產生任何文件，停止（Edge Cases「維護者中途結束」）。
11. **不提交、不 push**：只在維護者自己的指示要求時才提交新專案中產生的文件與世代紀錄；MUST NOT 對舊專案執行任何改變 `.git/` 的指令；
    MUST NOT push（R13；字樣：`push`）。
12. **未預期的結果**：腳本回傳本文件沒有列出的結束碼或 `reason` 時，告訴維護者發生了什麼與目前已寫入的內容，停止。

### 階段 1：開始（`check`）

13. 沒有給舊專案路徑、也沒有進度時，詢問路徑；MUST NOT 自行搜尋（Edge Cases；字樣：`do not search`）。
14. 執行 `check [--old <路徑>]`。順序：`check` 在任何其他動作之前。

| 結果 | 下一步 |
|---|---|
| 結束碼 0，`progress: "present"` | 進入「接續」 |
| 結束碼 0，沒有進度，`export_dir` 為 `ours` | 階段 3 |
| 結束碼 0，沒有進度，`export_dir` 為 `none` 或 `empty` | 階段 2 |
| `progress: "conflict"` | 列出 `.specify/sdd-rebuild/` 中不明的檔案，請維護者移走後再執行；停止 |
| `progress-unreadable` | 說明進度無法讀取（可能被手動編輯，或含有機密樣式）；詢問：清除進度並重新開始（建議）或停止讓維護者自己檢查（MUST NOT 自己開啟進度檔）；清除時執行 `clear` 後重新執行 `check` |
| `old-mismatch` | 說明進度屬於另一個舊專案（列出兩個路徑）；詢問：沿用進度的舊專案繼續（建議）或清除進度、以新的路徑重新開始 |
| `dependency` | 列出缺少的 skill，請維護者重新部署（`tools/deploy.py`）；停止 |
| `speckit-missing` | 請維護者先執行 `/sdd-init`；停止（FR-002） |
| `speckit-incomplete` | 列出 `missing`，說明 Spec Kit 可能有不相容的變更，建議 `/sdd-update`；停止 |
| `old-required` | 詢問路徑（第 13 項） |
| `old-missing`、`old-not-folder` | 回報路徑無效；請維護者確認路徑後再執行；停止（FR-019） |
| `same-project`、`old-inside-new`、`new-inside-old` | 回報兩個路徑的關係（互相包含時在新專案寫入就會改到舊專案，或反之）；停止（Edge Cases） |
| `rebuilt` | 說明這個專案已經重建過（第幾代，取自 `rebuilt_generation`；MUST NOT 為此開啟 `.sdd-rebuild/lineage.json`）；一個專案只重建一次：要加需求用 `/sdd-grill`，要再生下一代就在這個專案 `/sdd-export` 後另開新專案；停止 |
| `rebuild-conflict` | `rebuild_conflicts` 不為空時列出那些不是本功能寫入的檔案，請維護者移走或改名；為空時是本功能的 `lineage.json` 無法使用，列出 `rebuild_errors` 的 `check` 與路徑（`secret` 時說明新專案的 `.sdd-rebuild/lineage.json` 在該路徑看起來含機密值，請維護者自行移除，MUST NOT 開啟該檔），其他原因請維護者還原該檔；MUST NOT 建議刪除 `.sdd-rebuild/` 或世代紀錄；停止 |
| `nutrients-conflict` | 列出 `conflicts`（舊專案的 `.sdd-export/` 有不是 sdd-export 的檔案）；請維護者在舊專案處理；停止 |
| `nutrients-unreadable`、`nutrients-invalid` | 列出 `nutrients_errors` 的欄位路徑；請維護者修正養分，或在舊專案再執行 `/sdd-export`；`check` 為 `secret` 時說明舊專案的 `.sdd-export/nutrients.json` 在該路徑看起來含機密值，請維護者在舊專案移除後重跑，MUST NOT 開啟該檔案；停止（FR-019） |
| `nutrients-newer` | 說明養分來自較新的 sdd-export，請維護者更新 skill（重新部署本 repo 的 `home/`）；停止（Edge Cases） |

### 階段 2：舊專案沒有養分時的匯出（US4、FR-003、R3）

15. 說明舊專案還沒有養分，將依 sdd-export 的規則對舊專案匯出，會在舊專案寫入 `.sdd-export/`（只有這個資料夾），匯出前後都需要維護者確認；
    以一題詢問：先匯出（建議）、我自己到舊專案執行 `/sdd-export` 後再回來、停止。
16. `export_skill` 為 `false` 時不能匯出：說明需要部署 sdd-export，停止。`old_lineage_errors` 有 `check: "secret"` 時也不從這裡匯出
    （006 讀取同一份世代紀錄時會判為 `lineage-invalid`，匯出在第一步就會停下）：說明舊專案的 `.sdd-rebuild/lineage.json` 在該路徑看起來含機密值，請維護者移除後重跑，停止。
17. 匯出的指示：以 Read 讀取 `${CLAUDE_SKILL_DIR}/../sdd-export/SKILL.md`，依它的「Rules for the whole run」與 Stage 1 至 Stage 9 執行，
    **只做下列替換**，其他規則（含機密、只讀、git 允許清單、一題一項）原樣遵守（字樣：`../sdd-export/SKILL.md`、`--project`、`-C`）：
    - 腳本是 `${CLAUDE_SKILL_DIR}/../sdd-export/scripts/sdd_export.py`，每個指令加上 `--project "<old.path>"`；
    - `files` 與 `check` 的路徑相對於舊專案：Read、Grep 一次一個 `<old.path>/<路徑>`；Glob 只在 Stage 2 用於舊專案的資料夾名稱；
    - git 指令只用 sdd-export 允許清單中的四種形式，各自在 `git` 後加上 `-C "<old.path>"`，不加其他任何東西；
    - 「the project」指舊專案；匯出期間 MUST NOT 在新專案寫入任何東西，包括 `save`；
    - Stage 9 改為：回報 `.sdd-export/` 的位置與數量、說明養分可在舊專案提交，然後回到階段 1 重新執行 `check`；不建議 `/sdd-rebuild`。

| 結果 | 下一步 |
|---|---|
| 維護者選擇停止（第 15 項或匯出途中確認前） | 兩個專案都沒有寫入；說明沒有保存任何東西；停止（US4-3） |
| 維護者選擇自己去舊專案匯出 | 說明在舊專案執行 `/sdd-export`、完成後在新專案再執行 `/sdd-rebuild <路徑>`；停止 |
| 匯出依 sdd-export 的某個結果停止（衝突、專案過大且未選範圍、內容不足等） | 依 sdd-export 對該結果的指示回報；新專案沒有寫入；停止 |
| 匯出的 `write` 成功 | 執行 `check --old`：`export_dir` 為 `ours` → 階段 3；其他 → 依階段 1 的表 |
| 匯出中途 session 中斷 | 006 沒有進度；新專案也沒有進度（匯出期間不 `save`）；再執行 `/sdd-rebuild` 會從階段 1 開始，`.sdd-export/` 若已寫入就直接讀取 |

### 階段 3：讀取養分與舊專案的世代紀錄（R4）

18. 只使用 `check` 輸出的 `nutrients`，不讀舊專案的檔案。`nutrients_edited` 為 `true` 時告知養分在匯出後被手動編輯過。
19. 養分的 `scope.coverage` 為 `partial` 時，說明養分只涵蓋舊專案的一部分（列出 `included`），以一題詢問：先在舊專案補完匯出（建議）、只以這部分繼續。
20. 依 `old_lineage` 與 `needs_old_lineage` 處理（字樣：`old_lineage`、`skipped`）：

| 結果 | 下一步 |
|---|---|
| `present` | 祖先表納入舊世代紀錄；`old_lineage` 記為 `"used"`；階段 4 |
| `none` 且 `needs_old_lineage` 為 `false` | 第一代；記為 `"not-needed"`；階段 4 |
| `none` 且 `needs_old_lineage` 為 `true` | 說明世代紀錄在匯出後被移除、只存在於它的祖先會遺失；詢問：停止並從 git 歷史還原（建議）或只以養分繼續（記為 `"skipped"`） |
| `mismatch` | 說明世代紀錄與養分的世代不同；詢問：停止並確認兩者屬於同一個專案（建議）或只以養分繼續 |
| `unreadable`、`invalid` | 列出 `old_lineage_errors`；詢問：停止並修正（建議）或只以養分繼續；`check` 為 `secret` 時說明舊專案的 `.sdd-rebuild/lineage.json` 在該路徑看起來含機密值、建議移除後重跑，MUST NOT 開啟該檔案 |
| `newer` | 說明它來自較新的 sdd-rebuild；詢問：停止並更新 skill（建議）或只以養分繼續 |
| `conflict` | 說明它不是 sdd-rebuild 寫的；詢問：停止並檢查（建議）或只以養分繼續 |
| 選擇停止 | 沒有寫入（尚未 `save`）；說明處理後再執行 `/sdd-rebuild`；停止 |
| 選擇只以養分繼續 | 記為 `"skipped"`，最終摘要與結束報告列出這個選擇；階段 4 |
| `partial` 時選擇先補完匯出 | 說明在舊專案再執行 `/sdd-export`（或回到階段 2 的匯出流程，以既有養分為起點）；停止或進入階段 2 |

21. 呈現養分摘要：原則、功能清單與相依關係、經驗教訓、待確認的項目（`pending`），以及建議的 spec 順序（US1-1）。
    第一次 `save`（`phase: "deciding"`、`stage: "items"`）在這之後，腳本建立快照。

| `save` 的結果 | 下一步 |
|---|---|
| 成功 | 階段 4 |
| `source`（養分在這之間變了或消失） | 重新執行 `check`，回到階段 1 |
| `conflict` | 同階段 1 的 `progress: "conflict"` |
| `os-error` | 說明新專案無法寫入，進度無法保存；詢問：不保存繼續（中斷就遺失）或停止（建議） |

### 階段 4：新專案已有的內容（FR-015、R10）

22. `constitution` 為 `written` 時：逐條比對養分的原則與既有 constitution，呈現差異；預設 `action: "keep"`，維護者同意修訂時 `"amend"`；
    `missing` 或 `template` 時 `"create"`（字樣：`keep`、`amend`）。
23. `specs` 不是空的時：逐項比對養分的功能與既有 spec，每個功能一題：對應到既有 spec（`existing_spec`）、產生新的 spec、捨棄；
    MUST NOT 修改或覆蓋既有 spec（字樣：`existing_spec`）。對應既有 spec 的功能排在最前面。
24. 都沒有時跳過此階段。

| 結果 | 下一步 |
|---|---|
| 決定完成 | `save`；階段 5 |
| `save` 在某功能的 `existing_spec` 回 `secret` | 那份既有 spec 的資料夾名稱格式符合機密樣式，不是有人輸入的機密，但進度無法記錄；告訴維護者，詢問：維護者把資料夾改成不符合樣式的名稱後對應到改名後的資料夾、改為產生新的 spec，或捨棄 |
| 維護者想修改既有 spec | 說明本 skill 不修改既有 spec；建議重建完成後以 `/sdd-grill` 或手動處理；記為對應既有 spec 或產生新的 spec 由維護者選 |

### 階段 5：逐項決定（FR-005、FR-008、FR-018、US2-1）

25. 先問一題：全部原樣保留（養分中有 `pending` 時不提供此選項，或提供但仍逐一處理待確認的項目）或逐項檢視。
26. 逐項檢視時，依原則 → 功能（含需求）→ 教訓的順序，一次一個項目、附建議：保留、修改、合併、拆分（可保留原項）、捨棄（字樣：`merge`、`split`、`discard`）。
    合併與拆分以 `basis: "derived"` 與 `from` 記錄；拆出且保留原項時原項記為 `inherit`。新取的 `id` 由 Claude 擬定，被拒時改名。
27. 待確認的項目 MUST 一題一項請維護者決定（保留為事實、修改、捨棄），決定後加入 `pending_decided`；MUST NOT 當成事實寫入（FR-018；字樣：`pending`）。
28. 每個決定後 `save`（`stage: "items"`）。

| 結果 | 下一步 |
|---|---|
| 所有項目都有結論 | 階段 6 |
| 維護者改變先前的決定 | 修改目標中對應的項目並 `save`；不重新討論其他項目 |
| 決定彼此矛盾，或與保留的原則衝突 | 指出兩邊，一題請維護者取捨（US2-4） |
| 維護者要求結束 | 通則 10 |
| `save` 回 `invalid` 或 `secret` | 修正進度（機密改寫成「需要什麼」），涉及內容時請維護者確認該項；再 `save` |

### 階段 6：新需求（FR-006、US2-3、R11）

29. 詢問這一代是否有新需求。有時以 Read 讀取 `${CLAUDE_SKILL_DIR}/../sdd-grill/SKILL.md` 的「Rules for questioning」段落並套用到新需求
    （不使用該檔關於 sdd-grill 自己的進度、指令與產生文件的部分）；釐清到有結論後以 `basis: "new"` 加入目標，排入相依順序；
    技術選型記在 `for_plan`，延後事項記在 `deferred`（字樣：`Rules for questioning`、`for_plan`）。
30. 每個決定後 `save`（`stage: "new"`）。

| 結果 | 下一步 |
|---|---|
| 沒有或已全部釐清 | 階段 7 |
| 新需求與既有功能重疊 | 指出重疊，詢問：併入既有功能（修改）或成為新功能 |
| 維護者要求結束 | 通則 10 |

### 階段 7：教訓引發的調整（FR-007、US2-2、SC-005）

31. 依養分的教訓提出調整（新增原則、修改需求等），每一項記在 `adjustments` 並標示來源教訓，一題一項請維護者決定是否採用；
    採用時把變更反映在目標中；MUST NOT 未經同意改變原則或需求（字樣：`adjustments`、`lesson`）。
32. 教訓本身是否仍然適用：適用的 `inherit`、不適用的加入 `discards`；可以一題複選。

| 結果 | 下一步 |
|---|---|
| 全部決定 | `save`（`stage: "lessons"`）；階段 8 |
| 調整與保留的原則或其他決定矛盾 | 指出兩邊，請維護者取捨 |
| 沒有可提的調整 | 明說沒有；階段 8 |

### 階段 8：最終摘要與確認（FR-009、FR-010、US2-5）

33. `save`（`stage: "summary"`）後執行 `preview`。順序：`preview` 在確認之前。
34. 依 `preview` 的 `summary` 呈現：保留、修改、合併、拆分、捨棄、新增的項目，待確認項目的決定，採用與不採用的教訓調整，
    constitution 的 `action`，spec 的順序與相依，以及 `old_lineage` 為 `"skipped"` 時的影響（字樣：`preview`、`summary`）。
35. 以一題請維護者確認：確認並產生（建議）、修改某一項、結束。

| 結果 | 下一步 |
|---|---|
| `preview` 的 `ok` 為 `false` | 依 `errors` 修正目標（`unaccounted` 表示有來源項目沒有去處、`id-taken` 表示 `id` 已用過要改名、`pending-undecided` 表示還有待確認項目等）；需要決定的一題一項詢問；回到第 33 項 |
| `preview` 的 `errors` 含 `secret` | 組好的世代紀錄看起來含機密值（只有路徑）；`save` 與腳本讀取舊專案、進度時都會擋下，所以代表進度在途中被手動修改或 sdd-rebuild 的缺陷；詢問：清除並重新開始（建議）或停止；MUST NOT 開啟進度檔 |
| `preview` 回 `next-export` 或 `lineage-format` 錯誤 | 這代表 007 的組成與 006 不一致；回報錯誤內容，請維護者回報問題；停止（不確認） |
| 維護者確認 | `save`（`phase: "confirmed"`）；成功 → 階段 9 |
| 確認時 `save` 回 `invalid` | `preview` 之後進度又被改；重新執行第 33 項 |
| 維護者要修改 | 回到對應的階段處理該項，再回到第 33 項 |
| 維護者要求結束 | 通則 10 |

### 階段 9：constitution（FR-011、FR-013）

36. `action` 為 `create` 或 `amend` 時，以 Skill 工具呼叫 `speckit-constitution`，只傳入確認過的原則與治理規則，要求不推斷其他原則；
    返回後 `save`（`generation.constitution: "written"`）。順序：constitution 在任何 spec 之前。
37. 比對：雙向逐條；缺少的再呼叫一次只套用缺少的部分；多出的規則移除，想保留的先詢問維護者（同意保留的記進 `constitution.governance`，
    確認後只新增，用途只是讓之後的比對不再重複詢問；不改目標，不進世代紀錄）；完成後 `save`（`"reviewed"`）（FR-013；字樣：`reviewed`）。
    `keep` 時跳過（`"not-needed"`）。

| 結果 | 下一步 |
|---|---|
| 比對完成 | 階段 10 |
| `speckit-constitution` 失敗或中斷 | 進度保留 `pending` 或 `written`；回報；再執行 `/sdd-rebuild` 時依 `next` 繼續；停止 |
| 再呼叫一次仍缺少 | 回報缺少的部分；MUST NOT 手寫；停止，進度保留（再執行時從比對繼續） |

### 階段 10：逐份產生 spec（FR-011、FR-012、R7）

38. 依目標順序，對每個 `existing_spec` 為 `null` 的功能：以 Skill 工具呼叫 `speckit-specify`，傳入該功能確認過的內容（摘要、需求、相依、
    延後事項與 `for_plan` 寫在 Assumptions）；一次一個；MUST NOT 自行指定編號（字樣：`speckit-specify`、`Assumptions`）。
39. 返回後立即以 `claim <功能 id>` 記錄它建立的資料夾。順序：`claim` 在下一個 `speckit-specify` 之前。只能記錄這次執行中 `speckit-specify`
    為這個功能建立的資料夾：腳本無法分辨它與維護者自建、另一個視窗產生、或 `.specify/feature.json` 剛好指向的資料夾，而第 40 項會修改
    記錄的 spec。因此執行 `claim` 前先讀取 `speckit-specify` 回報建立的資料夾的 `spec.md`，確認標題與內容對應確認過的這個功能（標題、摘要）；
    沒有回報資料夾時依 `none` 處理；內容不對應時不執行 `claim`，告訴維護者該資料夾的內容並詢問（確認是這個功能的 → `claim --dir`；
    不是 → 「沒有吻合的候選」；或停止）。
40. 比對 spec 與摘要（`spec.md` 不存在或明顯不是這個功能的 spec 時不做任何修改，依下表）：沒有依據的規則移除或標為待確認；`speckit-specify` 的澄清問題能從摘要回答就依摘要，不能時一題詢問維護者，
    答案經 `speckit-specify` 的流程寫進該份 spec，需要記錄時加入 `deferred` 或 `for_plan`（確認後只新增）；不改目標；完成後 `save`（該功能 `reviewed: true`）。
    第 37 項與本項在確認後加入的內容不在世代紀錄中：結束報告（第 44 項）列出它們，並說明下一次 `/sdd-export` 時它們被當成這一代新增的項目。

| 結果 | 下一步 |
|---|---|
| `claim` 成功 | 確認 `spec_dir` 是第 39 項確認過（或維護者確認）的資料夾；第 40 項，然後下一個功能；全部完成 → 階段 11；不是時同「明顯不是這個功能的 spec」 |
| `claim` 回 `none` | `speckit-specify` 沒有產生 spec：列出 `incomplete`（有的話，說明不會刪除它）；詢問：再呼叫一次（建議）或停止；再呼叫一次仍失敗 → 停止，進度保留 |
| `claim` 回 `secret` | 資料夾名稱的格式符合機密樣式（例如 `sk-` 後接 20 個以上英數字或連字號），不是有人輸入的機密，但進度與世代紀錄無法記錄；沒有寫入。告訴維護者，詢問：把資料夾改成不符合樣式、保留編號的名稱（例如 `sklearn` 取代 `sk-learn`；建議），或停止；改名後 `claim <id> --dir <改名後的資料夾>`，接第 40 項；`feature.json` 仍指向舊名稱時不處理，下一次 `speckit-specify` 或 `focus` 會改寫。接續時的 `claim --dir` 回 `secret` 也同樣處理 |
| `claim` 回 `ambiguous` 或 `mismatch` | 列出 `candidates` 與 `feature_directory`；建議這次 `speckit-specify` 回報、且 `spec.md` 對應這個功能的那份（其他候選的 `spec.md` 只用於說明它們是什麼），一題請維護者確認；確認後 `claim --dir`；沒有吻合時見下一列；其餘候選列為維護者要處理的多出的資料夾 |
| 沒有吻合的候選（沒有候選的 `spec.md` 對應這個功能、`speckit-specify` 回報的資料夾不在其中，或維護者說都不是） | 說明那些資料夾不是這個功能的 spec、屬於維護者：本 skill 不修改、不刪除，`verify` 列為 `unexpected`；把這個功能視為尚未產生，依第 38 項呼叫 `speckit-specify`；之後 `claim` 回 `ambiguous`，依該列以 `--dir` 記錄剛產生的資料夾；再失敗 → 停止，進度保留 |
| 比對時記錄的 `spec.md` 明顯不是這個功能的 spec | MUST NOT 修改它（連移除一句都不做）；停止並告訴維護者哪個資料夾被記錄給哪個功能；詢問：其實就是這個功能的 spec（例如維護者改寫過，繼續比對），或重新開始（記錄的資料夾無法更改，已產生的文件保留） |
| 比對時 `<spec_dir>/spec.md` 不存在（`claim` 後被刪除） | 執行 `verify`，依階段 11 的 `spec-missing` 處理（還原或重新開始）；MUST NOT 重新產生（plan 設計取捨 6） |
| `claim` 回 `not-next` | 代表順序錯了；重新執行 `check`，依 `next` 處理 |
| `speckit-specify` 中斷（session 結束） | 再執行時 `next` 為 `claim`（有新的資料夾，可能已產生）或 `specify`（未產生）；依「接續」繼續：不重複產生，也不記錄無法確認屬於這個功能的資料夾 |
| 產生的編號與預期不同（例如中間有維護者自己的資料夾） | `claim` 仍記錄；`verify` 的 `order` 決定是否可接受（階段 11） |

### 階段 11：驗證（`verify`）

41. 全部功能完成後執行 `verify`。順序：`verify` 在 `lineage` 之前。

| 結果 | 下一步 |
|---|---|
| `ok` | 階段 12 |
| `existing-spec-changed`、`constitution-changed` | 既有文件在產生期間被改動：列出 `detail`；兩條出路：還原後再執行 `/sdd-rebuild`（建議），或重新開始（`clear`；已產生的文件保留，之後被當成既有內容）；停止 |
| `spec-missing`（已記錄的 `spec_dir` 失去 `spec.md`，例如被維護者刪除） | 列出；出路：還原該檔案後再執行（建議）；或重新開始；MUST NOT 重新產生該功能（新編號會排到後面，破壞順序）；停止 |
| `spec-not-new`、`order`、`dependency-order` | 編號與相依順序不符（例如中間被插入其他 spec）：列出；出路：還原或移走 `detail` 指出的資料夾後再執行，或重新開始；停止 |
| `existing-spec-missing` | 對應的既有 spec 被移除：出路：還原後再執行，或重新開始；停止 |
| `not-reviewed` | 依 `check` 的 `next` 回到對應的比對步驟 |
| `unexpected` 不是空的 | 不算失敗；在結束報告列出這些不屬於任何功能的資料夾，由維護者處理，本 skill 不刪除 |

### 階段 12：世代紀錄（`lineage`，FR-016、US3）

42. 執行 `lineage`（字樣：`lineage`、`.sdd-rebuild/lineage.json`）。

| 結果 | 下一步 |
|---|---|
| 成功（含 `unchanged: true`） | 階段 13 |
| `mismatch-documents` | 同階段 11 |
| `lineage-changed` | `.sdd-rebuild/lineage.json` 在途中被寫入不同的內容：只指出路徑，MUST NOT 開啟或引用其內容（它可能是手動放入的）；不覆蓋；請維護者檢查；停止 |
| `rebuild-conflict` | 同階段 1 的 `rebuild-conflict`（依 `rebuild_conflicts` 與 `rebuild_errors` 區分；不開啟該檔、不建議刪除）；停止 |
| `invalid` | 確認後進度不可能再變，出現代表進度檔被手動修改；回報 `errors`；停止 |
| `internal` | 回報 `errors`，說明這是 sdd-rebuild 的缺陷、世代紀錄沒有寫入、已產生的文件保留；請維護者回報；停止 |
| `os-error` | 回報；世代紀錄沒有寫入（或與之前相同）；修正後再執行 `/sdd-rebuild` 會從這一步繼續；停止 |

### 階段 13：收尾（FR-017）

43. 執行 `focus`，然後 `clear`。順序：`lineage` 在 `focus` 之前，`focus` 在 `clear` 之前。
44. 結束報告：每份 spec 的位置與順序、相依、對應既有 spec 的功能、`.specify/feature.json` 指向哪一份、世代紀錄的位置與世代、
    `.sdd-rebuild/lineage.json` MUST 提交到 repo（下一次 `/sdd-export` 需要它）、`old_lineage` 為 `"skipped"` 時的影響、
    `unexpected`；下一步是由維護者在主 session 輸入 `/sdd-drive`；然後停止，MUST NOT 開始 plan、tasks 或實作（FR-017；字樣：`/sdd-drive`）。
    沒有產生任何 spec（全部對應既有 spec）時，說明 `feature.json` 沒有更動，下一步依既有 spec 的狀態由維護者決定，不建議 `/sdd-drive`。

| 結果 | 下一步 |
|---|---|
| `focus` 成功 | `clear`；報告 |
| `focus` 回 `mismatch-documents` | 世代紀錄已寫入之後文件又被改動：同階段 11 的出路，但 MUST NOT 選重新開始（專案已重建），只能還原後再執行 |
| `focus` 回 `not-regular` | 回報；請維護者處理 `.specify/feature.json`；再執行時從 `focus` 繼續 |
| `clear` 回 `conflict` | 報告照常；另說明 `.specify/sdd-rebuild/` 有不明檔案，請維護者處理 |

### 接續（進度存在時，FR-010 的延伸、Edge Cases）

45. 依 `check` 呈現進度：階段、已決定的項目數、`next`。
46. 舊專案的變化：`source_state` 為 `unavailable` 時說明以快照繼續、不影響；`nutrients_errors` 有 `check: "secret"` 時說明舊專案的
    `.sdd-export/nutrients.json` 在該路徑看起來含機密值、快照不含它而繼續以快照為準，請維護者移除（MUST NOT 開啟該檔案）；
    `source_changed` 為真時呈現 `source_diff`（字樣：`source_diff`）：
    - `phase` 為 `deciding`：詢問：改用新的養分（建議；`save --refresh-source`，之後 `preview` 會指出需要重新決定的項目，逐項處理）、沿用快照繼續、重新開始。
    - `phase` 為 `confirmed`：說明已確認的內容以快照為準，繼續（不再詢問）。
47. 新專案的變化（`changed`）：`deciding` 時，constitution 或 spec 有變就重新執行階段 4 的比對；`confirmed` 時交給 `verify` 判斷。
48. 依 `next.step`：

| `next.step` | 下一步 |
|---|---|
| `decide` | 詢問：繼續（建議）、重新開始（`clear`）；繼續時回到 `stage` 對應的階段 |
| `constitution` | 詢問：繼續產生（建議）、改回討論（只有這時與沒有任何 spec 時允許；`save` 為 `deciding`）、重新開始；繼續 → 階段 9 |
| `review-constitution` | 從第 37 項的比對繼續，不重新呼叫 `speckit-constitution` |
| `claim` | 候選（`next.candidates`）可能是中斷前產生的，也可能是維護者自建或另一個視窗產生的，這次對話中沒有 `speckit-specify` 的回報能分辨：讀取每個候選的 `spec.md`，判斷是否對應 `next.feature`；吻合時詢問維護者是否為這次重建產生的（建議），確認後 `claim --dir`、從第 40 項繼續、不重新產生；都不吻合或維護者說不是 → 同階段 10「沒有吻合的候選」 |
| `specify` | 從第 38 項的這個功能繼續 |
| `review` | 從第 40 項的比對繼續（記錄的 `spec_dir`）；`spec.md` 不存在時執行 `verify`，依 `spec-missing` 處理，MUST NOT 重新產生 |
| `verify` | 階段 11 |
| `focus`、`clear` | 階段 13（世代紀錄已寫入；不能重新開始） |

49. 已產生任何文件後維護者要重新開始：說明已產生的 constitution 與 spec 會保留、下一次重建把它們當成既有內容（可對應到既有 spec），
    世代紀錄尚未寫入；確認後 `clear`。世代紀錄已寫入後不提供重新開始。
50. 已產生任何文件後維護者要改決定：選項：依確認的內容完成（建議，之後以 `/sdd-grill` 或手動調整）、停止保留進度、重新開始。

內文 MUST NOT 含有中日韓文字、絕對路徑、信箱。

## 階段與結果的數量

| 階段 | 結果（表列與指示中的分支） |
|---|---|
| 1 開始 | 17 |
| 2 匯出 | 5（另含第 15、16 項的選擇） |
| 3 讀取 | 10 + `save` 4 |
| 4 既有內容 | 2 |
| 5 逐項決定 | 5 |
| 6 新需求 | 3 |
| 7 教訓 | 3 |
| 8 摘要與確認 | 7 |
| 9 constitution | 3 |
| 10 spec | 9 |
| 11 驗證 | 7 |
| 12 世代紀錄 | 7 |
| 13 收尾 | 4 |
| 接續 | 8 種 `next.step`，加上舊專案變化 3 種、重新開始與改決定 2 種（共 13） |

合計 99 種結果，每一種都有下一步。

## README.md

MUST 以繁體中文撰寫，並包含：

- 用途與用法：在新專案執行 `/sdd-rebuild <舊專案路徑>`；舊專案先執行 `/sdd-export`，沒有時本 skill 可代為匯出（只寫舊專案的 `.sdd-export/`）。
- 前置需求：新專案已導入 Spec Kit；同時部署 sdd-export 與 sdd-grill（本 skill 載入它們的腳本與規則）；`uv`。
- 流程：讀養分 → 逐項決定 → 新需求 → 教訓 → 確認 → constitution → 逐份 spec → 世代紀錄 → `/sdd-drive`；確認前不寫入。
- 進度：位置 `.specify/sdd-rebuild/`、不入庫、快照（舊專案之後改變或消失不影響接續）、成功後清除。
- 世代紀錄：位置 `.sdd-rebuild/lineage.json`、MUST 提交、`derived_from` 補入祖先的規則。
- **已知限制**（維護者接受的取捨）：同一代內第二次匯出合併了第一次匯出才建立的項目時，第一次的來源會遺失；
  被捨棄項目的來源只保留到捨棄為止（被捨棄的項目本身不能重用）；舊專案的世代紀錄無法使用而選擇略過時，只存在其中的祖先會遺失。
- 不做的事：不修改舊專案（匯出除外）、不讀舊專案的 plan、tasks 與程式碼、不覆蓋既有 constitution 與 spec、不開始 plan 或實作、不 push。

## scripts/sdd_rebuild.py

- 開頭有 uv 的 inline metadata：`requires-python = ">=3.11"`，`dependencies` 為空。
- 只使用 Python 標準函式庫；外部指令只有 `git`（經 005 的函式）。
- 執行時載入相鄰的 `sdd_export.py` 與 `sdd_grill.py`（[cli.md](./cli.md)「共通」）；模組載入時不執行任何動作。
- 訊息與註解為英文，沒有絕對路徑與信箱。
