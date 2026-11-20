# Contract: sdd-export skill 的結構與必要指示

部署來源是 `home/skills/sdd-export/`，安裝後位於 `~/.claude/skills/sdd-export/`。
`tests/unit/test_sdd_export_skill.py` 依此檢查。SKILL.md 與腳本的分工見 [research.md](../research.md) 的 R1。

本文件依階段列出 SKILL.md 必須包含的指示，並且**每個階段都列出每一種結果的下一步**（成功、各種失敗、維護者改變主意）。
沒有任何一個結果的下一步是「未定義」；實作 SKILL.md 時 MUST 逐一涵蓋。

## 檔案

| 檔案 | 語言 | 內容 |
|---|---|---|
| `SKILL.md` | 英文 | 給 Claude 的指示：對話的進行方式與何時呼叫腳本 |
| `README.md` | 繁體中文 | 給維護者的簡述 |
| `scripts/sdd_export.py` | 英文（訊息與註解） | 專案現況、讀取範圍、驗證與寫入，介面見 [cli.md](./cli.md) |

資料夾內沒有其他檔案。

## SKILL.md 的 frontmatter

| 欄位 | 值 |
|---|---|
| `name` | `sdd-export` |
| `description` | 英文；說明用途（在舊專案把原則、各功能的需求與相依、經驗教訓與世代資訊匯出成 `.sdd-export/` 中的養分，供新專案以 `/sdd-rebuild` 重生）、在舊專案執行、不需要 Spec Kit、確認前不寫入（R9） |
| `disable-model-invocation` | `true` |
| `argument-hint` | `"[scope path ...]"` |

沒有其他欄位。

## SKILL.md 的內文

以下每一項都 MUST 出現；結構測試以每一項的關鍵字或關鍵句檢查（括號內是至少要出現的字樣），並檢查標示「順序」的段落先後。
措辭在實作時決定，測試不比對完整文字。腳本一律以 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_export.py" <command>` 執行，
在目前目錄（維護者啟動 skill 的舊專案），不使用 `--project`。

### 通則（任何階段都適用）

1. **只讀**：讀取只用讀取工具（Read、Grep、Glob），範圍限於 `files` 的清單與 `check` 輸出的內容；Read 與 Grep 一次指定 `files`
   中的一個路徑，MUST NOT 對專案根目錄或資料夾執行 Grep（搜尋結果會帶出機密檔案與排除範圍中相符的行）。允許的指令只有本 skill 的腳本
   與下列確切形式的只讀 git 指令（允許清單，不會輸出任何檔案的內容）：`git --no-pager log --oneline -n <n> [-- <path>]`、
   `git --no-pager log --stat -n <n> [<commit>] [-- <path>]`、`git --no-pager ls-files`、`git --no-pager blame -- <path>`
   （`<path>` 為 `files` 列出的路徑）；MUST NOT 加上其他選項或使用其他 git 指令，明確禁止 `git show` 的任何形式（對 blob 的 hash
   或 `<commit>:<path>` 即使加 `--stat` 也會印出整個檔案）、`git diff`、`git grep`、`git cat-file`、`git format-patch`、
   `git stash show`、`git whatchanged`、`git reflog`，以及 `git log` 輸出變更內容的選項（`-p`、`--patch`、`-u`、`--patch-with-stat`、
   `--cc`、`-L`）；MUST NOT 對 `files` 未列出的檔案執行 `git blame`（FR-015、FR-017、原則 V）。MUST NOT 執行建置、測試、安裝套件、格式化、產生程式碼
   或專案自己的任何腳本；MUST NOT 以 Write、Edit 或其他方式在專案內建立或修改檔案，**包括暫存檔**；草稿只經 stdin 交給腳本
   （FR-008、US2-5；字樣：`read-only`、`build`、`test`、`stdin`）。
2. **寫入只有一次**：唯一的寫入是確認後的 `write`；MUST NOT 以其他方式建立或修改 `.sdd-export/` 的檔案，
   也 MUST NOT 修改 `.sdd-export/` 以外的任何檔案（FR-010、FR-011；字樣：`.sdd-export/`）。
3. **不需要 Spec Kit**：MUST NOT 呼叫任何 `speckit-*` skill，MUST NOT 要求或建議先執行 `/sdd-init`；
   專案有 `.specify/memory/constitution.md` 與 `specs/` 時只是讀取它們（FR-001；字樣：`speckit-`、`/sdd-init`）。
4. **機密**：MUST NOT 讀取 `secret_files` 中的檔案；`secret_hits` 指出的行 MUST NOT 在對話、草稿與養分中引用其值；
   需要時只記錄位置（例如寫成改進建議的疑點）。任何機密值都 MUST NOT 出現在對話中。commit 訊息看起來含有機密值時，MUST NOT 引用、重複或改寫該部分，只以 `commit:<hash>` 指出位置，需要時記為只指出該 commit 的疑點（FR-015；字樣：`secret_files`、`secret_hits`）。
5. **提問**：需要維護者決定時使用 AskUserQuestion，建議的選項排第一並附理由；一次一個決定。性質相同的是非題（例如「哪些前代教訓
   已不適用」）MAY 以一題複選呈現；疑點 MUST 一題一項。工具不能用時改用文字，仍一次一題並附建議（字樣：`AskUserQuestion`）。
6. **語言**：與維護者對話的語言依全域設定；草稿與養分的字串內容使用繁體中文，MUST、SHOULD 等規範詞保留英文，
   檔名、識別字與專有名詞保留原文；來源文件是其他語言時翻譯，由維護者確認草稿時一併確認（R2；字樣：`Traditional Chinese`）。
7. **維護者在確認前要求結束**（任何階段）：不寫入任何內容；說明沒有保存任何東西，再執行 `/sdd-export` 會重新開始；
   停止（Edge Cases；字樣：`nothing is saved`）。
8. **維護者在確認前改變先前的決定**：直接修改草稿中對應的項目，最終確認時一併呈現；不需要重新討論其他項目。
9. **不提交**：MUST NOT 對專案執行 `git add`、`git commit`、`git push` 或任何改變 `.git/` 的指令（R13；字樣：`commit`）。
10. **不編造**：沒有依據的內容 MUST 標為待確認（`pending`），MUST NOT 寫成事實（原則 IV、FR-006、FR-009）。

### 階段 1：開始

11. 第一個動作是執行 `check`（字樣：該指令）。順序：在讀取任何專案檔案之前。

| 結果 | 下一步 |
|---|---|
| `uv` 不存在或腳本無法執行 | 回報原因（需要安裝 `uv`），停止 |
| 結束碼 3，`reason: "conflict"` | 列出 `.sdd-export/` 中不是本功能產生的內容，說明不會覆蓋；請維護者移走或改名後再執行；停止（Edge Cases、原則 III） |
| 結束碼 3，`nutrients-unreadable` 或 `nutrients-invalid` | 說明既有養分無法讀取，列出 `errors` 的欄位路徑；請維護者修正（或自行刪除 `.sdd-export/`）後再執行；停止。MUST NOT 覆蓋 |
| 結束碼 3，`nutrients-newer` 或 `lineage-newer` | 說明養分或世代紀錄來自較新版本的 skill，請維護者更新 skill 後再執行；停止 |
| 結束碼 3，`lineage-unreadable`、`lineage-invalid`、`lineage-conflict` | 說明世代紀錄無法讀取，列出原因；MUST NOT 把專案當成第一代；請維護者修正後再執行；停止 |
| 結束碼 0，`writable: false` | 告訴維護者專案看起來無法寫入：可以照常整理草稿，但最後可能無法寫入；以一題詢問繼續（建議）或停止 |
| 結束碼 0，`existing_generation` 不是 `null` 且不等於 `generation` | 列出兩者與可能的原因（世代紀錄被移除、專案是從其他專案複製而來）；以一題詢問：停止並檢查（建議）、或以 `generation` 繼續 |
| 結束碼 0，`nutrients: "edited"` 或 `"unknown"` | 告訴維護者既有養分在上次匯出後被修改過（或無法判斷）；之後把其中的內容當成維護者的決定（見階段 4），繼續 |
| 結束碼 0，`inventory.files` 為 0 | 說明專案沒有可讀取的內容（列出 `skipped` 的數量），停止，不寫入（FR-016） |
| 結束碼 0，其他 | 告訴維護者這一代的世代（`generation`；`lineage` 為 `none` 時說明視為第一代）、是否已有養分（再次匯出）、是否有 constitution 與 spec；進入階段 2 |

### 階段 2：範圍（FR-016、Edge Cases）

12. 維護者在啟動時附了範圍路徑，就以 `files --scope <路徑>...` 使用它們。
13. 沒有附範圍且 `inventory.too_large` 為 `true` 時，MUST 先列出 `areas`（檔案數、大小、套件描述檔），以 AskUserQuestion（可複選）
    請維護者選擇範圍，再以 `files --scope` 取得清單；MUST NOT 在選定範圍前讀取專案檔案（字樣：`too_large`、`--scope`）。
    順序：在階段 3 之前。
14. 範圍不是整個專案時，草稿的 `scope` 為 `partial` 並列出 `included`；說明之後可以再執行 `/sdd-export` 選擇其他範圍，
    範圍外的既有項目會原樣保留（R7 的分批匯出）。

| 結果 | 下一步 |
|---|---|
| 不過大、沒有範圍 | 以 `files`（不帶 `--scope`）取得清單；進入階段 3 |
| `files` 結束碼 1、`reason: "usage"`（範圍路徑不存在、在專案外或被排除） | 說明哪個路徑無效，重新請維護者選擇範圍 |
| `files` 的 `too_large` 仍為 `true` | 說明範圍仍太大，請維護者再縮小 |
| 維護者不願縮小範圍 | 說明一次讀不完整個專案，建議分批匯出；維護者仍拒絕時停止，不寫入 |
| 維護者選擇停止 | 依通則第 7 項 |

### 階段 3：讀取（US2、FR-005、FR-017）

15. 只讀取 `files` 列出的檔案；`constitution` 與 `specs` 列出的文件一定要讀（字樣：`files`）。
16. 有 spec 的功能以 spec 為來源；沒有 spec 或 spec 只涵蓋部分的功能，從文件、設定、測試與程式結構導出；
    部分涵蓋時功能的 `source` 為 `mixed`，各需求標明自己的來源（FR-005、US2-4；字樣：`mixed`）。
17. 從程式碼導出的需求只描述程式碼**目前實際**的行為，每項附上依據的檔案；無法確定的標為待確認（FR-006）。
18. 需求只描述使用者需求與可驗收的行為，MUST NOT 描述現行的實作方式（FR-004）。
19. 經驗教訓從專案的文件、spec 與 plan 類文件、git 歷史（只用通則第 1 項允許清單中的 git 指令，不看 diff）整理，分為重要決定與理由、踩過的坑、被推翻的做法；
    每項附依據（檔案或 `commit:<hash>`），沒有依據的標為待確認（FR-009、US3-1；字樣：`decision`、`pitfall`、`reversed`）。
20. 讀取時發現的疑似 bug、文件與程式碼的矛盾、spec 與程式碼的矛盾、改進建議記為**疑點**，不混入需求；
    spec 與程式碼矛盾時兩邊的說法都要記下，不自行選擇（FR-007、Edge Cases）。
21. 養分 MUST NOT 包含 plan、tasks 與程式碼；plan 類文件只作為教訓的依據，內容不抄進養分（FR-003）。

| 結果 | 下一步 |
|---|---|
| 讀完後能提出至少一個有依據的功能 | 進入階段 4 |
| 讀完後內容不足以提出任何有依據的需求 | 說明原因（例如只有設定檔、沒有可辨認的功能），停止，不寫入（FR-016、Edge Cases） |
| 某個檔案無法讀取（權限、編碼） | 略過並記下，在草稿的說明中列出；不改用其他指令讀取 |
| 範圍內的內容讀不完（context 不足） | 停止讀取，說明情況並建議縮小範圍，回到階段 2 |

### 階段 4：組草稿（FR-002、FR-012、FR-013、FR-014）

22. 草稿的 `generation` 使用 `check` 的 `generation`，不自行計算（字樣：`generation`）。
23. `lineage` 為 `present` 時：世代紀錄中 `in_lineage` 的 spec 對應的功能沿用紀錄的 `id` 與 `origin`；內容與紀錄不同時在 `revised`
    加上這一代；不在紀錄中的 spec 成為 `origin` 為這一代的新功能；`lineage_missing_specs` 中的每個功能，以一題詢問保留（依紀錄的內容）
    或捨棄；紀錄中的教訓詢問是否仍然適用（可複選），仍適用的沿用 `id` 與 `origin`，不適用的移到 `discarded`；
    紀錄中的 `discarded` 全部原樣保留（FR-012、FR-013、US4；字樣：`lineage`、`origin`、`discarded`）。
24. `export_dir` 為 `ours` 時（再次匯出）：以 `existing` 為起點；既有項目沿用 `id`；依據沒有改變的項目不改寫文字；
    範圍外的既有項目原樣保留；`nutrients` 為 `edited` 或 `unknown` 時，要改動既有內容 MUST 逐項詢問（R4；字樣：`existing`）。
25. 新項目的 `id` 不與世代紀錄或既有養分中的任何 `id`（含 `discarded`）重複。

| 結果 | 下一步 |
|---|---|
| 草稿組好 | 進入階段 5 |
| 世代紀錄中的項目無法對應到目前的任何內容 | 依第 23 項詢問保留或捨棄；不讓它無聲消失（世代規則 2） |

### 階段 5：呈現與逐項決定（FR-007、FR-010、US1、US3）

26. 依區段逐段呈現：世代資訊（世代、繼承與新增的數量）→ 原則 → 功能、需求與相依關係（依相依順序）→ 疑點 → 經驗教訓。
    每項標出來源（spec、程式碼、文件、維護者）、來源世代與依據；待確認的標為待確認（字樣：`pending`）。順序：各區段的先後。
27. 每段呈現後請維護者決定：全部接受、修改某些項目、或刪除某些項目；被刪除的項目，若是前代的或維護者希望記錄，移到 `discarded` 並記下理由。
28. 疑點 MUST 一題一項：納入（成為需求或教訓，可修改文字）、標為待確認、或捨棄（以 `doubt` 記入 `discarded`）（FR-007；字樣：`doubt`）。
29. 找不到任何可作為教訓的依據時，說明沒有找到，並詢問維護者是否口頭補充；口頭補充的依據記為 `maintainer`；MUST NOT 自行編造（US3-3；字樣：`maintainer`）。
30. 每段決定之後，在對話中以簡短清單留下該段的結論（讓 context 壓縮後仍能接續）。
31. 確認之前 MUST NOT 寫入任何檔案。順序：在階段 8 之前。

| 結果 | 下一步 |
|---|---|
| 維護者接受、修改或刪除 | 更新草稿；繼續下一段 |
| 維護者要補充需求或教訓 | 加入草稿，依據為 `maintainer`（或維護者指出的檔案），繼續 |
| 維護者要回頭修改已決定的段落 | 依通則第 8 項 |
| 全部區段都決定了 | 進入階段 6 |
| 維護者要求結束 | 依通則第 7 項 |

### 階段 6：驗證

32. 以 stdin 把完整草稿交給 `validate`（字樣：該指令）。順序：在最終確認之前。

| 結果 | 下一步 |
|---|---|
| `ok: true` | 進入階段 7 |
| `reason: "secret"` | 把 `errors` 指出的欄位改寫成不含該值的描述；MUST NOT 在對話中重複該值；再 `validate` |
| `reason: "invalid"`，結構或格式的錯誤（`field`、`id`、`range`、`code-block`、`dependency`、`scope`） | 修正草稿後再 `validate`；不涉及內容意義的修正不必詢問維護者 |
| `unsupported` 或 `evidence` | 補上正確的依據，或把該項改為待確認；改為待確認時告訴維護者 |
| 世代規則的錯誤（`lineage-item-missing`、`origin-changed`、`revision-unmarked`、`discard-lost` 等） | 依錯誤修正；需要維護者決定的（前代項目要保留還是捨棄）以一題詢問 |
| 結束碼 3 | 依階段 1 的同名結果處理（專案狀態在對話途中改變） |

### 階段 7：最終確認（FR-010、FR-014、US4-4）

33. 呈現整體摘要（`counts`、待確認的項目、捨棄的項目）；`diff.base` 為 `nutrients` 時呈現差異：新增、移除、修改（新舊值），
    沒有差異時明說（字樣：`diff`）。
34. `view` 為 `edited` 時，告訴維護者寫入會重新產生 `.sdd-export/README.md` 而蓋掉其中的手動修改，請他決定把那些修改併入草稿或放棄。
35. 以一題詢問：確認寫入（建議）、修改、或停止。

| 結果 | 下一步 |
|---|---|
| 確認 | 進入階段 8 |
| 要修改 | 回到階段 5 的對應區段；修改後重新經過階段 6、7 |
| 停止 | 依通則第 7 項 |

### 階段 8：寫入（FR-011、FR-014）

36. 以 stdin 把確認後的草稿交給 `write --expect <check 的 state>`（字樣：`write`、`--expect`）。

| 結果 | 下一步 |
|---|---|
| 結束碼 0 | 進入階段 9 |
| `reason: "changed"` | 說明養分在對話途中被修改；重新 `check`，以新的 `existing` 重新組差異並 `validate`，回到階段 7 再次確認 |
| `reason: "conflict"`（結束碼 3） | 停止，回報衝突的路徑；把確認後的草稿完整呈現在對話中，讓維護者自行保存；不寫到其他地方 |
| 其他結束碼 3 | 依階段 1 的同名結果處理；把確認後的草稿完整呈現在對話中 |
| `reason: "os-error"` | 回報原因（例如唯讀、權限）；把確認後的草稿完整呈現在對話中（Edge Cases）；說明 `.sdd-export/` 沒有留下半份檔案；以一題詢問：維護者處理後重試、或停止（建議） |
| 維護者處理後要求重試 | 重新 `check`：`state` 與先前相同時以同一份確認後的草稿再次 `write`；不同時依 `changed` 處理 |
| `reason: "invalid"` 或 `"secret"`（不應發生，階段 6 已通過） | 回到階段 6 |

### 階段 9：結束報告（FR-018、US1-5）

37. 依 `write` 的輸出回報：養分的位置（`.sdd-export/nutrients.json`，可讀版本 `.sdd-export/README.md`）、世代、
    納入的項目（各類數量、繼承與新增）、待確認的項目、捨棄的項目；說明養分可以提交到 repo（由維護者決定，本 skill 不提交）；
    下一步是在**新專案**執行 `/sdd-rebuild` 並指定這個舊專案的路徑；然後停止（字樣：`/sdd-rebuild`）。
38. `scope` 為 `partial` 時，另外說明可以再執行 `/sdd-export` 匯出其他範圍。
39. 寫入後維護者改變主意：說明可以再執行 `/sdd-export` 修改（以這份養分為起點），或自行編輯、刪除 `.sdd-export/`。

內文 MUST NOT 含有中日韓文字、絕對路徑、信箱。

## README.md

MUST 以繁體中文撰寫，並包含：

- 用途與用法：在舊專案執行 `/sdd-export [範圍路徑...]`；不需要 Spec Kit；只能由維護者啟動。
- 前置需求：`uv`；`git` 非必要（有的話用來尊重 `.gitignore` 與引用 commit）。
- 流程：讀取（只讀）→ 草稿 → 逐項決定 → 確認 → 寫入；確認之前不寫入任何檔案，中途結束不會留下任何東西。
- 產出：`.sdd-export/` 的三個檔案、`nutrients.json` 是唯一的資料來源、`README.md` 是產生的可讀版本、可以提交到 repo；
  下一步在新專案執行 `/sdd-rebuild`。
- 世代：沒有 `.sdd-rebuild/lineage.json` 時是第一代；有時沿用它的世代，繼承的項目保留來源世代。
- 再次匯出：更新同一份養分、呈現差異；手動編輯過的內容會先詢問。
- 大型專案：先選範圍、可分批匯出。
- 機密：不開啟的檔案類型、寫入前的樣式攔截，以及它的限制（無法涵蓋所有機密）。
- 不做的事：不修改 `.sdd-export/` 以外的任何檔案、不執行建置或測試、不呼叫 Spec Kit、不提交、不刪除。

## scripts/sdd_export.py

- 開頭有 uv 的 inline metadata：`requires-python = ">=3.11"`，`dependencies` 為空。
- 只使用 Python 標準函式庫；外部指令只有 `git`。
- 不載入其他 skill 的程式。
- 可被測試以模組方式載入，載入時不執行任何動作（[cli.md](./cli.md) 的「以模組方式載入」）。
- 訊息與註解為英文，沒有絕對路徑與信箱。
