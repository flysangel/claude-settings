# Research: sdd-grill 依需求追問出 constitution 與 spec

R1 是 SKILL.md 與腳本的分工總表；R2 至 R6 是 spec 與任務說明留給 plan 的五個決定（進度保存、自動測試的範圍、
產生文件的做法、frontmatter、與 007 的關係）；R7 至 R9 是設計時衍生的決定。
「實測」指 2026-11-20 在 Linux（git 2.43.0）於暫存目錄執行的結果，列在文末的「實測紀錄」。
Spec Kit 的行為以本 repo 由官方工具產生的 `.claude/skills/speckit-specify/SKILL.md`、
`.claude/skills/speckit-constitution/SKILL.md` 與 `.specify/scripts/bash/`（1.4.2）為準，只讀不改。

## 與 003、004 的根本差異

003、004 是「薄 SKILL.md 加一支做完所有判斷的腳本」：Claude 只負責執行一次腳本並回報。
sdd-grill 的主要產出是**對話**：找出未決事項、一次一題、追問含糊的回答、指出矛盾、整理摘要。
這些只能由 Claude 依 SKILL.md 的文字指示執行，沒有任何程式能替它判斷「這個回答夠不夠明確」。

所以本功能的設計原則是：

- **對話與語意判斷寫在 SKILL.md**，由 Claude 執行；以結構與內容檢查確認必要的指示都在，以人工驗收確認實際行為。
- **檔案狀態與可決定的判斷寫在腳本**：進度檔放哪裡、怎麼寫、怎麼不入庫、專案有沒有變、Spec Kit 能不能用、
  產生的 spec 編號是否符合順序、既有文件有沒有被動到。這些都能在 CI 的兩個平台以單元測試驗證。
- 不為了可測而把對話塞進腳本（例如由腳本出題或判斷回答），也不把可決定的事留給文字指示（例如由 Claude 自己決定
  進度檔路徑或自行判斷「專案有沒有變」）。

## R1 SKILL.md 與腳本的分工

- **Decision**：逐項如下表。腳本是 `scripts/sdd_grill.py`，介面見 [contracts/cli.md](./contracts/cli.md)；
  SKILL.md 的必要指示見 [contracts/skill.md](./contracts/skill.md)。

  | 行為 | 放哪裡 | 理由 |
  |---|---|---|
  | 前置檢查：專案是否導入 Spec Kit、產生文件所需的能力是否齊全（FR-019、Edge Cases） | 腳本 `check` | 只看檔案是否存在，可決定；結果決定要不要開始追問，錯了會在沒有 Spec Kit 的專案亂寫檔案 |
  | 專案現況：constitution 是空白範本、已填寫或不存在；既有 spec 的清單與編號；編號方式 | 腳本 `check` | 讀檔與比對即可決定；Claude 讀錯會導致重問已決定的事或編號衝突 |
  | 讀取專案內容並推導問題、自行查出可查到的事（FR-002、FR-004） | SKILL.md | 需要理解需求與專案內容的語意 |
  | 一次一題、附建議與理由、建議排第一、使用 AskUserQuestion、工具不能用時改用文字（FR-003） | SKILL.md | 提問的形式是對話行為 |
  | 追問含糊的回答、指出矛盾、與既有原則衝突時要求取捨（FR-005、FR-006、US4-2） | SKILL.md | 判斷「夠不夠明確」「是否矛盾」是語意判斷 |
  | 追問的順序：原則 → 功能清單與相依 → 逐一功能（FR-007） | SKILL.md；進度的結構支援 | 順序是對話的進行方式；進度檔記錄目前在哪一段，讓接續時知道從哪裡繼續 |
  | 技術選型只記錄為「留給 plan」（FR-008） | SKILL.md；進度的結構有專用欄位 | 辨認哪些話題屬於技術選型是語意判斷 |
  | 進度檔的位置、格式、寫入、不入庫（FR-009） | 腳本 `save` | 可決定；位置與不入庫做錯會把私人討論提交到公開 repo |
  | 每個決定之後保存（FR-009 的時機） | SKILL.md | 「做出一個決定」的時點只有 Claude 知道；腳本負責每次都寫對 |
  | 不把機密值寫入進度（FR-009） | 兩邊：SKILL.md 指示不記錄；腳本拒絕寫入看起來像機密的值（R8） | 辨認機密主要是語意判斷，腳本是決定性的安全網 |
  | 偵測「專案在上次討論後有變更」（FR-010） | 腳本 `check` | 以指紋比對可決定（R2） |
  | 列出已決定事項、讓維護者選擇接續或重新開始（FR-010） | SKILL.md；重新開始時呼叫腳本 `clear` | 呈現與詢問是對話；清除是檔案操作 |
  | 呈現決策摘要、依修改再次確認（FR-011、US2-3） | SKILL.md | 摘要的內容來自對話 |
  | 確認前不寫入 constitution 與 spec（FR-012） | SKILL.md；腳本除 `focus` 之外的每個指令都只寫 `.specify/sdd-grill/`；`focus` 只在確認後的收尾執行，且只多寫 `.specify/feature.json` | Claude 的寫入只能靠指示約束；腳本本身可證明不寫其他地方 |
  | 確認時記下既有文件的基準（constitution 與每份 spec.md 的雜湊） | 腳本 `save`（`phase` 變為 `confirmed` 時） | 可決定；是 `verify` 的依據 |
  | 呼叫 `speckit-constitution` 與 `speckit-specify` 產生文件（FR-013） | SKILL.md | 只有 Claude 能呼叫 skill |
  | constitution 不多出未確認的規則（FR-014） | SKILL.md | 判斷某條規則是否「確認過」是語意比對 |
  | spec 依相依順序產生（FR-015） | SKILL.md 決定呼叫順序；腳本 `verify` 檢查結果 | 呼叫順序由 Claude 執行；「編號是否遞增、是否接在既有之後」可決定 |
  | 不覆蓋既有文件（FR-016） | SKILL.md；腳本 `verify` 以基準比對 | 同上 |
  | 結束時的報告與下一步 `/sdd-drive`、停止（FR-017） | SKILL.md；`verify` 輸出每份新 spec 的位置與相依 | 報告是對話；清單由腳本給出可避免漏列 |
  | 成功後清除、失敗或中途結束時保留（FR-018） | SKILL.md 決定時機；腳本 `clear` 只刪自己的檔案 | 「是否成功」由 `verify` 決定；刪除範圍必須可證明 |
  | 產生文件的語言（FR-020） | SKILL.md | 判斷既有文件的語言是語意判斷 |
  | 把目前的功能目錄（`.specify/feature.json`）指向這一批新 spec 中編號最小的一份 | 腳本 `focus`（R4） | 「哪一份最小」與「檔案內容」都可決定，能被單元測試；`verify` 通過才執行，所以不會指向不存在的目錄 |

- **Rationale**：每一項都問兩件事：「錯了會不會在檔案上留下難以發現的後果」與「判斷是否需要理解語意」。
  前者是、後者否的放腳本；需要語意的放 SKILL.md。兩者都有的（機密、順序、不覆蓋）由 SKILL.md 執行、腳本檢查結果。
- **Alternatives considered**：
  - 完全不寫腳本，進度與檢查都由 Claude 依文字指示處理：進度檔的位置與格式會隨每次對話漂移，
    「專案有沒有變」由 Claude 憑印象判斷不可靠，而且除了結構檢查之外沒有任何行為能在 CI 驗證，難以滿足原則 II。
  - 由腳本主導對話（例如腳本維護一份題目清單、決定下一題）：等於固定題庫，違反 FR-002；
    「回答是否足夠」也不是腳本能判斷的。

## R2 進度保存的位置、格式、不入庫與變更偵測

### 位置與不入庫

- **Decision**：
  - 進度存在目標專案的 `.specify/sdd-grill/progress.json`。
  - 同一個資料夾內有一份由 sdd-grill 建立的 `.specify/sdd-grill/.gitignore`，內容是一行說明註解加上 `*`。
    它忽略整個資料夾（包含它自己），所以進度永遠不會出現在 `git status`、也不會被 `git add -A` 加入。
  - 這個資料夾**只屬於 sdd-grill**：sdd-grill 只在這裡寫檔，這裡也只有 sdd-grill 的檔案。
    這是原則 I 要求的「記錄哪些檔案是自己建立的」的做法：資料夾名稱與 `.gitignore` 的註解標明來源，
    README 與 contracts 寫明這個約定；`progress.json` 本身也帶 `"tool": "sdd-grill"`。
  - 腳本第一次寫入時建立資料夾與 `.gitignore`；資料夾已存在、但 `.gitignore` 的內容不是 sdd-grill 寫的，
    或資料夾內有 sdd-grill 不認得的檔案時，視為衝突：不寫入、不刪除，回報並停止（原則 III）。
- **Rationale**：
  - `.specify/.gitignore` 是 Spec Kit 產生的檔案，依原則 I 不能加規則；目標專案根目錄的 `.gitignore` 是維護者的檔案，
    也不該由工具改寫。在自己的資料夾放一份「忽略自己」的 `.gitignore`，不碰任何別人的檔案就能不入庫。
    實測（文末）確認 `*` 同時忽略同資料夾的進度與 `.gitignore` 本身，`git add -A` 不會加入任何一個。
  - 不需要專案是 git repository；專案之後才 `git init` 也一樣有效。
  - 進度跟著專案走：換目錄、改名都不會遺失；刪除專案時一併消失。
  - 與既有做法一致：sdd-init 在 `.specify/` 有自己的 `.gitattributes` 與紀錄，sdd-update 有自己的 `.specify/sdd-update/`。
- **為什麼不登記在 sdd-init 的導入紀錄**：004 把比對副本列入 `.specify/sdd-init.json`，因為比對副本可能入庫、
  需要被 `/sdd-init remove` 與下一次更新清理。進度則相反：它不入庫、隨時會被清除，而導入紀錄是入庫的檔案；
  登記進去會讓入庫的紀錄指向別台機器上不存在的檔案，sdd-grill 也會因此依賴 sdd-init 的紀錄格式與腳本。
  專用資料夾已足以讓它與 Spec Kit 的檔案分得清楚。
- **Alternatives considered**：
  - 在 `.specify/.gitignore` 加一行：違反原則 I（本 repo 自己的 `.specify/.gitignore` 有一行 `sdd-grill-progress.md`，
    是 constitution v1.0.1 之前為了另一個工具手動加的歷史內容，與本設計無關，本功能不依賴也不處理它）。
  - 寫入 `.git/info/exclude`：不入庫，但只在已是 git repository 時有效，要處理 worktree 的路徑，
    而且改的是維護者的 git 設定，之後 `git init` 的專案也不會生效。
  - 放在專案外（例如使用者層級的資料夾，依專案路徑分開）：不會弄髒專案，但專案搬移或改名就找不到進度，
    刪除專案後留下孤兒檔案，路徑也依機器而異。
  - 放在專案根目錄的 `.sdd-grill/`：根目錄多一個工具資料夾，與 Spec Kit 的檔案分散兩處；`.specify/` 已是本專案工具放自己檔案的地方。

### 格式

- **Decision**：UTF-8、LF、縮排 2 的 JSON，`schema` 為 1。欄位見 [data-model.md](./data-model.md)。
  內容由 Claude 組好、以 stdin 交給 `save`；腳本驗證結構、加上 `fingerprint`（與確認時的 `baseline`）後以
  「寫暫存檔再取代」的方式寫入，中途中斷不會留下半份檔案。
- **Rationale**：JSON 讓腳本能驗證結構與欄位（可在 CI 測試），也讓 `check` 能決定性地輸出「已決定的事項」清單；
  Claude 讀寫 JSON 沒有困難。每次都寫入完整文件，不做增量修改，接續時讀到的就是最後一次保存的完整狀態。
- **Alternatives considered**：
  - Markdown：方便人閱讀，但腳本無法可靠地驗證與擷取欄位；`check` 要列出已決定事項時只能整份交給 Claude 解讀。
    維護者想看進度時，`check` 的輸出與 Claude 呈現的摘要已足夠。
  - 每個決定 append 一筆：要處理修改與撤回已決定事項，讀取時要重播，複雜度不值得。

### 變更偵測

- **Decision**：每次 `save` 時記錄專案的指紋；`check` 重新計算並逐項比較，輸出哪幾項改變。指紋包含：
  1. `constitution`：`.specify/memory/constitution.md` 換行正規化後的 SHA-256，不存在為 `null`。
  2. `specs`：`specs/` 下每個資料夾的 `spec.md` 換行正規化後的 SHA-256（以相對路徑為鍵）。
  3. `head`：專案是 git repository 且有 commit 時為 `git rev-parse HEAD` 的結果，否則為 `null`。
- **Rationale**：sdd-grill 的決定建立在三類事實上：既有原則、既有 spec、專案內容。前兩者直接比對內容；
  專案內容以 HEAD 代表，任何 commit 都會讓它改變。換行正規化與 003 相同，讓 CRLF 與 LF 不被當成變更。
  只有改變的項目會被提示，維護者能據此判斷是否沿用舊進度。
- **限制**：未 commit 的程式碼變更不會被偵測（constitution 與 spec 的未 commit 變更會）。
  對全部工作檔案計算雜湊在大型專案很慢，且多數變更與需求討論無關；這個限制寫入 README。
- **Alternatives considered**：
  - 檔案修改時間：在 clone、checkout 後全部改變，誤報太多。
  - 全部工作檔案的雜湊：最完整，但成本與專案大小成正比，且 build 產物會不斷誤報。
  - 只看 HEAD：抓不到未 commit 的 constitution 或 spec 修改，而這兩者正是最直接影響決定的內容。

## R3 自動測試能涵蓋的範圍

constitution 原則 II 要求每個功能 MUST 有自動測試並在兩個平台的 CI 通過。本功能的自動測試分兩類，
另有一類只能人工驗收；**對話行為不在 CI 驗證**，CI 只能證明「必要的指示存在」，不能證明 Claude 會照做。

- **Decision**：

  | 類別 | 測試檔 | 涵蓋內容 |
  |---|---|---|
  | 腳本的單元測試 | `tests/unit/test_sdd_grill.py` | 前置檢查、專案現況、進度的驗證與寫入、不入庫（以真實的 `git` 驗證 `git status` 與 `git add -A`）、機密攔截、變更偵測、基準、`verify`、`clear` 的刪除範圍、衝突、除 `focus` 之外的指令都不寫入 `.specify/sdd-grill/` 以外的地方、`focus` 只寫 `.specify/feature.json`（含檔案不存在、無法解析、已指向目標、`verify` 不通過時不寫入）、換行與路徑在兩個平台一致 |
  | skill 的結構與內容檢查 | `tests/unit/test_sdd_grill_skill.py` | 資料夾只有三個檔案、frontmatter、SKILL.md 是英文且沒有絕對路徑與信箱、必要指示的關鍵句都存在（逐條對應 FR，見 [contracts/skill.md](./contracts/skill.md)）、指示的順序（前置檢查在提問之前、摘要確認在產生文件之前、`verify` 在 `clear` 之前）、README 是繁體中文且涵蓋必要內容、腳本只用標準函式庫且訊息是英文 |
  | 人工驗收 | [quickstart.md](./quickstart.md) 的「人工驗收」 | 實際對話：提問形式、追問、矛盾、技術選型、摘要、確認前不寫入、產生文件的內容與編號、中斷接續、既有專案加需求 |

  FR 與驗證方式的對照：

  | FR | 單元測試 | 結構／內容檢查 | 人工驗收 |
  |---|---|---|---|
  | FR-001 啟動方式 | | frontmatter 有 `argument-hint`、沒有 `disable-model-invocation`；description 說明使用時機 | 情境 1、10 |
  | FR-002 問題源自需求 | | 指示：從需求與專案內容推導、不用固定題庫 | 情境 1 |
  | FR-003 一次一題附建議 | | 指示：一題、建議排第一、附理由、AskUserQuestion、工具不能用時改用文字 | 情境 1、2 |
  | FR-004 可查到的自己查 | | 指示存在 | 情境 1 |
  | FR-005 追問含糊回答 | | 指示存在 | 情境 2 |
  | FR-006 指出矛盾 | | 指示存在 | 情境 2 |
  | FR-007 追問順序 | 進度的 `stage` 只接受定義的值 | 指示存在，且三段的順序正確 | 情境 1 |
  | FR-008 技術選型留給 plan | 進度有 `for_plan` 欄位 | 指示存在 | 情境 2 |
  | FR-009 保存、不入庫、無機密 | 位置、原子寫入、`.gitignore`、`git status` 乾淨、機密被拒 | 指示：每個決定後保存、不記錄機密 | 情境 3 |
  | FR-010 接續與變更提示 | `check` 回報進度與改變的項目 | 指示：先列出、選擇接續或重新開始、有變更先提示 | 情境 3、4 |
  | FR-011 決策摘要 | 進度有四類欄位 | 指示：摘要的四個部分 | 情境 5 |
  | FR-012 確認前不寫入 | 確認前腳本只寫自己的資料夾（`focus` 在確認、產生與 `verify` 之後才會執行） | 指示存在，且在產生文件的步驟之前 | 情境 5 |
  | FR-013 透過 Spec Kit 產生 | | 指示：以 Skill 呼叫兩個 `speckit-*` skill、不手寫 | 情境 6 |
  | FR-014 constitution 不多出規則 | | 指示存在 | 情境 6 |
  | FR-015 依相依順序編號 | `verify` 檢查編號遞增、相依在前 | 指示：依順序逐一呼叫 | 情境 6 |
  | FR-016 不覆蓋、接續編號 | `verify` 檢查基準未變、新編號大於既有 | 指示存在 | 情境 8 |
  | FR-017 結束報告與停止 | `verify` 輸出清單 | 指示：列出、`/sdd-drive`、停止 | 情境 6 |
  | FR-018 清除或保留進度 | `clear` 只刪自己的檔案；`verify` 失敗不清除 | 指示：`verify` 通過後才 `clear` | 情境 3、7 |
  | FR-019 Spec Kit 不可用 | `check` 的結束碼 3 與缺少的項目 | 指示：停止、請維護者執行 `/sdd-init`、不建立檔案 | 情境 9 |
  | FR-020 文件語言 | | 指示存在 | 情境 6、8 |
  | FR-021 兩平台相同 | CI 的 `test` job 在兩個平台跑全部單元測試 | | |
  | FR-022 英文與 README | | 英文、無 CJK；README 繁體中文 | |

- **Rationale**：
  - 腳本負責的事全部可以在暫存目錄以真實的檔案與 `git` 測試，不需要網路，也不需要 Claude。
  - 結構與內容檢查能防止「改 SKILL.md 時不小心刪掉一條規則」這類回歸，是對話式 skill 唯一能在 CI 做的防線。
    檢查以關鍵句與段落順序為準，不檢查完整文字，避免每次潤飾措辭都要改測試。
  - 人工驗收的每個情境都對應 spec 的 Independent Test 或 Acceptance Scenario，由維護者在真實 session 進行並記錄結果。
- **CI**：沿用既有的 `test` job（兩個平台執行全部測試）。進度不入庫、不在平台之間交換，所以不需要新的跨平台 job；
  `cross-platform-produce` 與 `cross-platform` 不變。
- **Alternatives considered**：
  - 在 CI 以 Claude Code 的非互動模式跑一段腳本化的對話並檢查結果：需要 API 金鑰與付費呼叫、結果不穩定，
    而且非互動模式下沒有 AskUserQuestion，測的不是真正的行為。不採用。
  - 只做結構檢查、不寫腳本：見 R1 的替代方案。

## R4 產生文件的做法

- **Decision**：維護者確認摘要後，依下列步驟進行；每一步完成就以 `save` 保存，失敗時停在原地。
  1. **記下基準**：以 `phase: "confirmed"` 保存。腳本在第一次進入 `confirmed` 時記下 `baseline`：
     constitution 與每份既有 spec.md 的雜湊、既有 spec 資料夾清單。之後的 `save` 不再改動 `baseline`。
  2. **constitution**（只在摘要的 `constitution.action` 是 `create` 或 `amend` 時）：以 Skill 工具呼叫
     `speckit-constitution`，參數是摘要中確認過的原則與治理規則的完整文字，並說明不要從專案內容推斷其他原則。
     完成後 Claude 逐條比對 constitution 與摘要：多出的規則移除；Claude 認為值得保留的，先以一題詢問維護者（FR-014）。
     `action` 是 `keep`（既有專案、維護者沒有同意修訂）時不呼叫，constitution 不動（FR-016、US4-3）。
  3. **spec**：依摘要的功能順序（被依賴的在前）逐一以 Skill 工具呼叫 `speckit-specify`，一次一個功能。
     參數是該功能確認過的使用情境、範圍、邊界情況、相依的功能，以及延後事項與原因（明確要求寫在 Assumptions）。
     每完成一個，把 `speckit-specify` 回報的 `SPECIFY_FEATURE_DIRECTORY` 寫入該功能的 `spec_dir` 並保存。
     `speckit-specify` 若因 `[NEEDS CLARIFICATION]` 要提問，答案能從摘要得出就由 Claude 依摘要回答；
     不能時以一題詢問維護者（附建議），並把答案補進進度，視為對已確認摘要的修訂。
     產生後 Claude 比對 spec 與摘要：沒有依據的規則移除，或依原則 IV 標為待確認。
  4. **驗證**：執行 `verify`。它檢查 `baseline` 中的每份 spec.md 仍存在且內容未變；`action` 為 `keep` 時 constitution 未變；
     每個功能都有 `spec_dir` 且其 `spec.md` 存在、不在 `baseline` 中；`spec_dir` 的編號依功能順序遞增，
     且全部大於 `baseline` 中最大的編號；每個功能依賴的功能編號都比它小。通過時輸出每份新 spec 的位置與相依。
  5. **指向第一份**：`verify` 通過後執行 `focus`，把 `.specify/feature.json` 指向這一批新 spec 中編號最小的一份（見下「目前的功能目錄」）。
  6. **收尾**：`focus` 成功才執行 `clear`，然後依 `verify` 的輸出報告每份 spec 的位置、相依與建議順序，
     並說明 `.specify/feature.json` 現在指向哪一份；下一步是由維護者輸入 `/sdd-drive`（或依序以原生的 `/speckit-plan` 處理），並停止（FR-017、FR-018）。
- **編號（FR-015、FR-016）**：`speckit-specify` 自己決定編號：`sequential`（預設）時取 `specs/` 中下一個可用的三位數，
  `timestamp` 時取當下時間。所以「依相依順序、一次一個地呼叫」就同時保證兩件事：編號等於施工順序，且接在既有之後、
  不覆蓋既有資料夾。sdd-grill 不自行計算或指定編號，也不建立資料夾；`verify` 事後確認結果（時間戳記同樣依呼叫順序遞增）。
- **目前的功能目錄**（維護者決定，取代原本「不修改 `feature.json`」的決定）：`speckit-specify` 每次都把
  `.specify/feature.json` 改成它剛建立的資料夾，所以一批 spec 產生完畢時它會指向最後一份。維護者決定 sdd-grill 在
  產生多份 spec 之後，把 `feature_directory` 指向**這一批新 spec 中編號最小的一份**，讓維護者改用原生的
  `/speckit-plan` 時依施工順序從第一份開始（導入後可以用 sdd-grill，也可以用原生 Spec Kit 指令，原生這條路要順）。
  - **查到的事實**（Spec Kit 1.4.2，讀取本 repo 的檔案）：(a) `speckit-specify` 建立資料夾與 `spec.md` 後把
    `{"feature_directory": "<資料夾>"}` 寫入 `.specify/feature.json`，目的是讓 `/speckit-plan`、`/speckit-tasks` 等後續指令
    不靠 git 分支名稱就能找到功能目錄；`create-new-feature.sh` 與 `common.sh` 的 `_persist_feature_json` 也以同樣內容寫入
    （只有檔案不存在或值不同時才寫）。(b) Spec Kit 自己產生的 `.specify/.gitignore` 把 `feature.json` 列為不入庫的本機狀態，
    註解寫明「每次切換功能就改寫，是每個 checkout 自己的狀態，不是要分享的東西」。(c) `common.sh` 的
    `read_feature_json_feature_directory` 讀它的 `feature_directory`（依序用 `jq`、`python3`、`grep`／`sed`；無法解析時不是有效值），
    `check-prerequisites.sh` 等腳本由此取得功能目錄；環境變數 `SPECIFY_FEATURE_DIRECTORY` 的優先順序比它高。
  - **與原則 I 的關係**：原則 I 禁止的是「手寫或修改 Spec Kit 產生的檔案的內容」，理由是專案要能持續更新 Spec Kit、
    不修改上游檔案才不會在更新時衝突或遺失修改。`feature.json` 是 Spec Kit 用來記錄「目前處理哪個功能」的本機狀態：
    不入庫（所以不會有更新衝突，也不會有 git 內容被改）、Spec Kit 每次切換功能都自己改寫它、切換功能的方式就是改這個值。
    `focus` 寫入的內容與格式與 `speckit-specify` 寫的相同，改的是它設計成會被改的那個值，所以屬於使用 Spec Kit 提供的切換機制，
    不是修改它的產出。這個判斷的範圍僅限這個檔案的這個鍵；其他 Spec Kit 檔案（含 `.specify/.gitignore`）仍一律不改。
    （原則 I 的條文沒有為這類狀態檔另列例外；這個判斷建立在上述理由上，維護者若希望條文寫明可另行修訂 constitution，不在本功能範圍。）
  - **由誰寫入**：腳本新增第五個指令 `focus`，不放在 SKILL.md 讓 Claude 修改。理由：「找出最小編號的一份」與「寫出固定格式的檔案」
    都是可決定的事，錯了會在檔案上留下難以發現的後果（指到不存在或錯的目錄），符合 R1 的分工準則，也能單元測試。
    不併入 `verify` 是因為 `verify` 的契約是只讀；不併入 `clear` 是因為 `clear` 的契約是只刪自己的檔案。
    因此「腳本只寫 `.specify/sdd-grill/`」這條保證改為「除 `focus` 之外的指令只寫 `.specify/sdd-grill/`；`focus` 只多寫
    `.specify/feature.json`，不寫其他地方」。
  - **`focus` 的行為**：先執行與 `verify` 相同的全部檢查，任何一項失敗就不寫入；通過後目標是 `features` 第一個功能的 `spec_dir`
    （`verify` 的 `order` 檢查保證它就是這一批編號最小的一份，也大於專案原有的所有 spec，所以不是整個專案的第一份）。
    只產生一份 spec：目標就是那一份，已指向時不寫入。`feature.json` 不存在：建立。內容無法解析（不是 JSON、不是物件、
    沒有字串型的 `feature_directory`）：視為沒有有效值，改寫成 `{"feature_directory": "<目標>"}`；這與 Spec Kit 自己的寫入相同，
    該檔案只有這一個鍵且可由 Spec Kit 隨時重建。若 `.specify/feature.json` 存在但不是一般檔案，不寫入並回報失敗。
    產生中途失敗時 `verify` 不通過，`focus` 不會執行，檔案保持 `speckit-specify` 最後寫入的值（指向它建立的、存在的資料夾），
    補完之後再執行 `/sdd-grill` 繼續時才會被指向第一份。
  - **Alternatives considered**：
    - 不修改，只在結束報告說明（原決定）：維護者跳過 `/sdd-drive` 直接 `/speckit-plan` 時會先處理最後一份，
      這與「原生指令這條路要順」的決定衝突，只能靠維護者看報告自己切換。
    - 指向最後一份（保持 `speckit-specify` 的結果）：同上，順序倒過來。
    - 由 SKILL.md 指示 Claude 修改該檔案：Claude 手寫 JSON 的格式與路徑可能出錯，也無法單元測試；
      且與原則 I 的「手寫」字樣更接近。
    - 指向專案中編號最小的 spec：專案已有先前的 spec 時，會指向與這一批無關的舊功能。
    - 用環境變數 `SPECIFY_FEATURE_DIRECTORY`：只在單一 process 內有效，維護者之後開的 session 不會帶著它。
- **中途失敗**（Edge Cases）：任何一步失敗（Skill 呼叫失敗、產生的檔案不存在、`verify` 不通過）時，
  Claude 依進度與 `verify` 的輸出回報已產生與未產生的文件，保留進度，不執行 `focus`，停止；MUST NOT 自行手寫或補寫文件，
  也 MUST NOT 刪除已產生的文件。再次執行 `/sdd-grill` 時，`check` 回報 `phase: "confirmed"` 與尚未產生的功能，
  Claude 詢問維護者是否從尚未產生的功能繼續（不重新討論）。`verify` 若發現 `baseline` 之外、又沒有記在任何功能的
  新 spec 資料夾（例如 `speckit-specify` 中途失敗留下的），列為 `unexpected` 由維護者處理，sdd-grill 不刪除。
- **Spec Kit 缺少能力**（Edge Cases、FR-019）：`check` 要求以下檔案都存在：`.specify/`、
  `.claude/skills/speckit-constitution/SKILL.md`、`.claude/skills/speckit-specify/SKILL.md`、
  `.specify/scripts/bash/resolve-template.sh`、`.specify/templates/spec-template.md`、
  `.specify/templates/constitution-template.md`。沒有 `.specify/` 時回報「未導入」，其餘缺少時回報「可能有不相容的變更」並列出缺少的項目。
  兩者都在開始追問之前停止。
- **Rationale**：完全依賴 Spec Kit 自己的編號與寫檔，sdd-grill 不必知道 Spec Kit 內部的規則，Spec Kit 改版時也不必跟著改；
  結果再由 `verify` 決定性地檢查，錯了也不會靜悄悄地留下。
- **Alternatives considered**：
  - 由 sdd-grill 先計算編號並以 `SPECIFY_FEATURE_DIRECTORY` 指定給 `speckit-specify`：多一份與 Spec Kit 重複的編號邏輯，
    `timestamp` 模式也要另外處理；依序呼叫已能得到相同結果。
  - 一次把所有功能交給 `speckit-specify`：它明確規定一次只建立一個功能。
  - 產生完畢後不動 `feature.json`（原決定）：已被維護者的決定取代，見上「目前的功能目錄」。
  - 失敗時自動刪除已產生的文件再重來：違反原則 III（那些檔案由 Spec Kit 產生，不是 sdd-grill 自己建立的），
    也會丟掉可用的結果。

## R5 SKILL.md 的 frontmatter

- **Decision**：

  | 欄位 | 值 |
  |---|---|
  | `name` | `sdd-grill` |
  | `description` | 一段英文：做什麼（一次一題追問到 constitution 與 spec 的每個決定都有結論，確認後交給 Spec Kit 產生）；何時使用（全新專案、加入新需求、方向未定、要討論該有什麼 constitution 或 spec）；何時不用（單純的意見詢問、技術選型、實作已有的 spec） |
  | `argument-hint` | `"<requirement description>"` |

  沒有 `disable-model-invocation`（預設允許 Claude 自行使用）。
- **Rationale**：FR-001 允許 Claude 在方向未定時主動使用，`home/CLAUDE.md` 也要求「全新專案、有新需求或方向未定時使用
  `sdd-grill`」；禁止模型呼叫會讓這條全域偏好無法執行。description 是 Claude 決定是否選用的唯一依據，所以要寫出
  觸發的情境與不該觸發的情境（否則任何「幫我想想」都可能誤觸發一場長追問）。
  主動使用時同樣先經過前置檢查，而且確認摘要之前不寫入任何文件，所以誤觸發的代價只是一段對話，維護者可以隨時要求結束。
- **Alternatives considered**：
  - `disable-model-invocation: true`（與 sdd-init、sdd-update 相同）：與 FR-001 與 `home/CLAUDE.md` 抵觸。
  - description 只寫用途不寫時機：選用時機不明確，容易漏用或誤用。

## R6 與 007 sdd-rebuild 的關係

- **Decision**：005 不為 007 實作任何功能，只保留以下餘地：
  1. **腳本可被載入**：`sdd_grill.py` 以模組方式載入時不執行任何動作，進度的讀寫、指紋、自我忽略的資料夾、
     機密攔截都是獨立的函式，資料夾名稱是參數。007 若要「比照 sdd-grill 的進度保存」，可以像 004 載入 `sdd_init.py`
     那樣從相鄰的 skill 資料夾載入這些函式，存在它自己的 `.specify/sdd-rebuild/`。
  2. **進度有 `schema` 與 `tool` 欄位**：007 若沿用同一格式，可以分辨檔案屬於誰，格式演進時也能辨認版本。
  3. **追問規則集中在 SKILL.md 的一個段落**：007 處理新需求時，可以請維護者以 `/sdd-grill` 加上新需求進入，
     或在它自己的 SKILL.md 引用同一套規則；US4（既有專案加需求）已涵蓋「在既有決定的基礎上追問」。
- **Rationale**：spec 只說 007 的接續「比照」sdd-grill，沒有決定 007 的範圍；預先抽出共用模組或擴充欄位都是在猜。
  保持函式邊界清楚、載入時無副作用，成本幾乎為零，007 需要時再決定要不要共用。
- **Alternatives considered**：
  - 現在就把進度處理抽成共用的第三個資料夾：部署與測試結構都要改，而 007 是否需要還不確定。
  - 進度格式預留 007 專用的欄位：沒有需求依據。

## R7 Claude 與腳本之間的資料傳遞

- **Decision**：腳本的輸出一律是 stdout 上的一份 JSON（UTF-8、LF），錯誤原因同時寫在 JSON 的 `error` 與 stderr；
  `save` 從 stdin 讀入完整的進度 JSON。不以命令列參數傳遞進度內容。
- **Rationale**：讀取的一方是 Claude，不是維護者；JSON 讓 SKILL.md 可以指名欄位（例如「列出 `progress.decided`」），
  也讓測試直接比對結構。進度內容可能很長且含引號與換行，經 stdin 傳遞避免 shell 的跳脫問題，在 Windows 與 Linux 相同。
  003、004 的輸出是給維護者看的文字；本功能由 Claude 再整理後才呈現給維護者，所以選擇不同。
- **Alternatives considered**：
  - 人類可讀的文字輸出：Claude 要自行解析，欄位改名時沒有測試會失敗。
  - 由 Claude 直接以 Write 工具寫進度檔：路徑、格式與不入庫都要靠 Claude 每次記得，無法測試。

## R8 機密值

- **Decision**：SKILL.md 指示 Claude 不把機密值（密碼、金鑰、權杖、連線字串中的憑證）寫入進度與產生的文件，
  只記錄「需要一個 X」，並告知維護者它沒有被記錄。腳本的 `save` 另外以一組固定的樣式掃描所有字串值，
  符合時拒絕寫入（結束碼 1，指出欄位路徑但不重複印出該值）：私鑰標頭（`-----BEGIN … PRIVATE KEY-----`）、
  常見的權杖前綴（例如 `ghp_`、`github_pat_`、`sk-`、`xox[abpr]-`、`AKIA`）、URL 中的 `user:password@`、
  以及 `password`／`secret`／`token`／`api_key` 後接 `=` 或 `:` 與一段非空白值。
- **Rationale**：辨認機密主要靠語意，只能由 Claude 執行；但寫入的唯一入口是 `save`，在那裡加一道決定性的檢查，
  能擋下最常見的失誤，且可以在 CI 測試。樣式刻意保守，誤判時 Claude 改寫描述即可。
- **限制**：樣式無法涵蓋所有機密，這道檢查是安全網，不取代 SKILL.md 的指示。產生的 constitution 與 spec 由
  Spec Kit 寫入，不經過腳本，只能靠指示與維護者確認摘要時把關。
- **Alternatives considered**：只靠指示：沒有可測試的部分。以熵值偵測：誤判太多，討論內容常有長識別字。

## R9 結束碼

- **Decision**：0 成功；1 用法錯誤、輸入的進度無效、機密被拒、`verify` 或 `focus` 的檢查不通過、`feature.json` 不是一般檔案、自己的資料夾有衝突；
  3 Spec Kit 未導入或缺少產生文件所需的檔案。2 保留不用（與 001 的「衝突」區隔，與 003 相同）；
  不使用 4（本功能沒有網路操作）。
- **Rationale**：沿用 003、004 的編號意義，讓 SKILL.md 的處理方式一致：3 表示「前置條件不成立，請維護者處理」。

## 實測紀錄

自我忽略的資料夾（git 2.43.0，暫存目錄）：

```text
git init
mkdir -p .specify/sdd-grill
printf '# Created by sdd-grill\n*\n' > .specify/sdd-grill/.gitignore
echo '{}' > .specify/sdd-grill/progress.json
echo x > a
git status --porcelain --untracked-files=all   → 只有 "?? a"
git check-ignore -v .specify/sdd-grill/progress.json .specify/sdd-grill/.gitignore
                                               → 兩者都由 .specify/sdd-grill/.gitignore:2:* 忽略
git add -A; git status --porcelain             → 只有 "A  a"
```

Spec Kit 1.4.2 的行為（讀取本 repo 由官方工具產生的檔案）：

- `speckit-specify`：一次只建立一個功能；未指定 `SPECIFY_FEATURE_DIRECTORY` 時依 `.specify/init-options.json`
  的 `feature_numbering`（`sequential` 或不存在時取 `specs/` 中下一個可用的三位數，`timestamp` 時取當下時間）；
  每次把 `.specify/feature.json` 改寫為剛建立的資料夾；最多 3 個 `[NEEDS CLARIFICATION]` 並會向使用者提問；
  在 `checklists/requirements.md` 產生品質檢查清單；依賴 `.specify/scripts/bash/resolve-template.sh` 取得範本。
- `speckit-constitution`：以 `resolve-template.sh constitution-template` 取得範本，會從 repo 內容推斷未提供的值，
  在檔案開頭加上 Sync Impact Report 的 HTML 註解，只寫 `.specify/memory/constitution.md`。
- `before_specify`／`before_constitution` 等 hook 只在 `.specify/extensions.yml` 存在時執行；sdd-init 導入的專案沒有這個檔案。
  專案自行加了 hook（例如建立分支）時，sdd-grill 不干涉，由 Spec Kit 照它的規則執行。
