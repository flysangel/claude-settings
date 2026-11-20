# Contract: sdd-grill skill 的結構與必要指示

部署來源是 `home/skills/sdd-grill/`，安裝後位於 `~/.claude/skills/sdd-grill/`。
`tests/unit/test_sdd_grill_skill.py` 依此檢查。SKILL.md 與腳本的分工見 [research.md](../research.md) 的 R1。

## 檔案

| 檔案 | 語言 | 內容 |
|---|---|---|
| `SKILL.md` | 英文 | 給 Claude 的指示：對話的進行方式與何時呼叫腳本 |
| `README.md` | 繁體中文 | 給維護者的簡述 |
| `scripts/sdd_grill.py` | 英文（訊息與註解） | 進度與檢查，介面見 [cli.md](./cli.md) |

資料夾內沒有其他檔案。

## SKILL.md 的 frontmatter

| 欄位 | 值 |
|---|---|
| `name` | `sdd-grill` |
| `description` | 英文；說明用途（一次一題追問到 constitution 與 spec 的決定都有結論，確認後由 Spec Kit 產生）、使用時機（新專案、新需求、方向未定）與不使用的時機（單純詢問意見、技術選型、實作既有 spec）（R5） |
| `argument-hint` | `"<requirement description>"` |

MUST NOT 有 `disable-model-invocation`（FR-001：Claude MAY 主動使用）。沒有其他欄位。

## SKILL.md 的內文

以下每一項都 MUST 出現；結構測試以每一項的關鍵字或關鍵句檢查（括號內是至少要出現的字樣），
並檢查標示「順序」的段落先後。措辭在實作時決定，測試不比對完整文字。

### 開始

1. 維護者沒有附需求描述時，先請他說明需求，不做其他事（Edge Cases）。
2. 執行 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" check`（字樣：該指令）。順序：在任何提問之前。
3. 結束碼 3 時：`speckit` 為 `"missing"` 時請維護者執行 `/sdd-init`，`"incomplete"` 時回報可能有不相容的變更並列出缺少的檔案；
   然後停止。MUST NOT 自己執行 `/sdd-init`，MUST NOT 建立或修改 `.specify/` 與 `speckit-*` 的檔案（FR-019；字樣：`/sdd-init`、`.specify/`）。
   `uv` 不存在時同樣回報並停止。
4. `progress` 為 `"conflict"` 或 `"unreadable"` 時回報原因；`unreadable` 時詢問維護者是否以 `clear` 清除後重新開始。

### 接續（FR-010、US3）

5. `progress` 為 `"present"` 時，先列出已決定的事項；`changed` 不是空的時先說明哪些改變了；
   再以一題詢問接續或重新開始。重新開始時執行 `clear`（字樣：`changed`、`clear`）。
6. 接續時從 `stage` 與 `current_feature` 繼續，MUST NOT 重問已決定的事項（SC-004）。
   `phase` 為 `"confirmed"` 時不重新討論（不在這份進度上修改已確認的決定），先以 `verify` 判斷產生到哪裡，
   再以一題詢問：從尚未產生的文件繼續（建議）、重新開始、或停止（FR-010、US3-3）。
   `verify` 回報重跑也不會消失的失敗（例如 `existing-spec-changed`、`constitution-changed`）時不繼續產生，
   改為詢問停止（讓維護者還原 `detail` 指出的檔案後再執行）或重新開始。
   重新開始時執行 `clear`，只清除進度；已產生的 constitution 與 spec MUST NOT 被刪除或還原，交給維護者處理，
   之後的新討論把它們視為既有文件（字樣：`start over`、`clear`、`do not delete`）。
   繼續時若 constitution 已寫入（`create` 或 `amend`），先依第 23 項與摘要逐條比對一次再繼續（FR-014）。

### 追問的規則（集中在一個段落，R6）

7. 先讀取專案現有內容（constitution、spec、README 與程式碼），能查到的事自己查出並採用，不提問（FR-004）。
8. 問題從需求描述與專案內容中未決定的事項推導；MUST NOT 使用與需求無關的固定題庫（FR-002）。
9. 每則訊息只問一個問題，附建議與理由，建議排在第一個選項；使用 AskUserQuestion；工具不能用時改用文字，
   仍然一次一題並附建議（FR-003；字樣：`AskUserQuestion`、`one question`）。
10. 回答含糊時繼續追問到能判斷做法是否符合為止（FR-005）。
11. 回答與先前的決定矛盾時，指出兩邊並請維護者取捨；與既有 constitution 衝突時，請維護者決定修訂原則或調整需求（FR-006、US4-2）。
12. 語言、框架、資料庫等技術選型只記錄在 `for_plan`，不討論（FR-008；字樣：`for_plan`）。
13. 機密值不記錄，只記下需要什麼，並告知維護者（FR-009）。
14. 維護者要求結束時：呈現目前的摘要、確認進度已保存，然後停止（US3-2）。

### 追問的順序（FR-007）

15. 依序：constitution 的原則 → 功能清單與相依關係 → 逐一討論每個功能的使用情境、範圍與邊界情況。順序：三段的先後。
    專案已有 constitution 時，原則這一段只處理新需求與既有原則的衝突或新增；`action` 依維護者的決定設為 `keep` 或 `amend`。
    需求只涉及原則、拆不出功能時，`features` 可以是空的，跳過逐一討論直接進入摘要；constitution 也維持不變時沒有東西可產生，
    告知維護者並詢問要新增功能或結束。
16. 對話時使用的語言依維護者的全域設定；產生的文件依專案既有文件的語言，無法判斷時使用繁體中文，規範詞保留英文（FR-020）。

### 保存（FR-009）

17. 每個決定之後，以 stdin 把完整的進度交給 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" save`（字樣：該指令）。
    `save` 失敗時修正後重試；因機密被拒時改寫成不含該值的描述。
18. 進度只透過 `save` 寫入；MUST NOT 以其他方式建立或修改 `.specify/sdd-grill/` 的檔案。

### 摘要與確認（FR-011、FR-012）

19. 全部有結論或已延後時，呈現摘要：已決定的事項、已延後的事項與原因、留給 plan 的事項、依相依關係排列的功能順序。
20. 以一題詢問確認；維護者要求修改時修改並再次確認。
21. 確認之前 MUST NOT 寫入或修改 constitution 與任何 spec。順序：在產生文件的段落之前。

### 產生文件（FR-013 至 FR-016、R4）

22. 確認後以 `phase: "confirmed"` 保存。確認後維護者要改決定時，只有 constitution 與 spec 都尚未產生才可改回
    `"discussing"`（改回會重設 `baseline`，見 data-model.md 的「狀態轉移」）；已產生任何文件時，詢問依確認內容產生完、
    停止或重新開始（FR-012、FR-014）。
23. `constitution.action` 為 `create` 或 `amend` 時，以 Skill 工具呼叫 `speckit-constitution`，只傳入確認過的原則與治理規則，
    並要求不要推斷其他原則；完成後移除未確認的規則，想保留的先詢問維護者（FR-014；字樣：`speckit-constitution`）。
    `keep` 時不呼叫。
24. 依功能順序，一次一個以 Skill 工具呼叫 `speckit-specify`，傳入該功能確認過的內容，延後事項要求寫在 Assumptions；
    每完成一個就把回報的資料夾寫入 `spec_dir` 並保存（字樣：`speckit-specify`、`spec_dir`、`Assumptions`）。
    `speckit-specify` 要澄清時，依摘要回答；摘要沒有答案時以一題詢問維護者並補進進度。
25. MUST NOT 自己手寫 constitution 或 spec；MUST NOT 自行指定編號，也 MUST NOT 自己修改 `.specify/feature.json`（它只由腳本的 `focus` 寫入，見第 28 項）。

### 失敗（Edge Cases、FR-018）

26. 任何一步失敗時，回報已產生與未產生的文件，保留進度，停止；MUST NOT 補寫、MUST NOT 刪除已產生的文件。
    區分兩種失敗：重跑後會自行消失的（中斷、Spec Kit skill 暫時失敗），告訴維護者再執行 `/sdd-grill` 就會接續；
    不會自行消失的（`existing-spec-changed`、`constitution-changed`、`spec-not-new`、`order`、`dependency-order`、
    已記錄的 `spec_dir` 失去 `spec.md` 的 `spec-missing`），告訴維護者兩條出路：還原 `detail` 指出的檔案後再執行，
    或再執行並選擇重新開始（FR-010、FR-018；字樣：`restore`、`start over`）。

### 收尾（FR-017、FR-018）

27. 執行 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_grill.py" verify`；失敗時依第 26 項處理。
28. `verify` 通過後執行 `focus`，把 `.specify/feature.json` 指向這一批新 spec 中編號最小的一份（字樣：`focus`、`feature.json`）；
    失敗時依第 26 項處理。順序：`verify` 在 `focus` 之前。
29. `focus` 成功後執行 `clear`。順序：`focus` 在 `clear` 之前。
30. 依 `verify` 的輸出列出每份 spec 的位置、相依關係與建議順序，並告訴維護者 `.specify/feature.json` 現在指向哪一份
    （`focus` 輸出的 `feature_directory`）；說明下一步是由維護者輸入 `/sdd-drive`，也可依序以原生的 `/speckit-plan` 處理，
    因為目前的功能已指向第一份；然後停止，MUST NOT 開始 plan、tasks 或實作（字樣：`/sdd-drive`）。
    只修訂 constitution、沒有任何功能的一批（`focus` 的 `feature_directory` 為 `null`）時，改為回報沒有產生 spec、
    `.specify/feature.json` 沒有更動、constitution 是建立或修訂；下一步是檢查既有 spec 是否需要依新原則調整，
    有新需求時再執行 `/sdd-grill`，MUST NOT 建議 `/sdd-drive`（FR-017、SC-007；字樣：`null`）。
31. MUST NOT push。

內文 MUST NOT 含有中日韓文字、絕對路徑、信箱。

## README.md

MUST 以繁體中文撰寫，並包含：

- 用途與用法：`/sdd-grill <需求描述>`；Claude 也可能在方向未定時主動使用。
- 前置需求：專案已導入 Spec Kit（未導入時先執行 `/sdd-init`）；`uv`；`git` 非必要。
- 流程：先原則、再功能清單、再逐一功能；確認摘要之前不寫入任何文件；確認後由 Spec Kit 產生；結束後下一步是 `/sdd-drive`。
- 進度：位置 `.specify/sdd-grill/`、不入庫的方式（資料夾內自己的 `.gitignore`）、成功後清除、中途結束或失敗時保留、
  不記錄機密、「專案有變更」的偵測範圍與限制（未 commit 的程式碼變更不會被偵測）。
- 收尾：產生完畢後把 `.specify/feature.json` 指向這一批新 spec 中編號最小的一份（這是它對 Spec Kit 檔案唯一的寫入）。
- 不做的事：不覆蓋既有 spec、constitution 只在同意修訂時更動、不修改 `.specify/feature.json` 以外的 Spec Kit 檔案、不開始 plan 或實作。

## scripts/sdd_grill.py

- 開頭有 uv 的 inline metadata：`requires-python = ">=3.11"`，`dependencies` 為空。
- 只使用 Python 標準函式庫；外部指令只有 `git`。
- 不載入其他 skill 的程式。
- 可被測試以模組方式載入，載入時不執行任何動作（[cli.md](./cli.md) 的「以模組方式載入」）。
- 訊息與註解為英文，沒有絕對路徑與信箱。
