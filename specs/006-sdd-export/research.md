# Research: sdd-export 從舊專案匯出養分

R1 是 SKILL.md 與腳本的分工總表；R2 至 R9 對應任務說明列出的八個決定（養分的格式與目錄、世代、再次匯出、
從程式碼導出需求、機密、中斷與失敗、自動測試、frontmatter）；R10 至 R13 是設計時衍生的決定。
「實測」指 2026-11-20 在 Linux（git 2.43.0、uv 0.13.6）於暫存目錄執行的結果，列在文末的「實測紀錄」。
本功能的寫法、分工與指令介面比照 005 sdd-grill（`specs/005-sdd-grill/`、`home/skills/sdd-grill/`）。

## 與 005 的相同與不同

相同：都是**對話式的 skill**。讀程式碼導出需求、整理經驗教訓、判斷疑點、呈現草稿、逐項請維護者決定，
這些只能由 Claude 依 SKILL.md 的文字執行；可以決定性完成的事集中在一支由 uv 執行、輸出 JSON 的 Python 腳本。

不同：

- **執行的地方是任意的舊專案**：可能沒有 Spec Kit、不是 git repository、是別的語言。所以不依賴 `.specify/`，
  不呼叫任何 `speckit-*` skill，自己的檔案放在獨立的頂層目錄（R2）。
- **沒有進度**：spec 的 Edge Cases 規定中途結束不寫入任何內容。草稿只存在於對話中，經 stdin 交給腳本；
  寫入只有一次，就是維護者確認之後（R7）。
- **產出要被另一個 skill 讀取**：養分是 007 sdd-rebuild 的輸入，世代紀錄是 007 的輸出、006 的輸入。
  兩份檔案的格式是本 plan 最重要的契約（R2、R3、[data-model.md](./data-model.md)）。
- **腳本可以寫入的範圍只有養分的專用目錄**，沒有 `focus` 那類例外；也沒有刪除指令。

設計原則與 005 相同：對話與語意判斷寫在 SKILL.md；檔案狀態、格式、可決定的檢查寫在腳本並以單元測試驗證；
不為了可測而把判斷塞進腳本，也不把可決定的事留給文字指示。

## R1 SKILL.md 與腳本的分工

- **Decision**：逐項如下表。腳本是 `scripts/sdd_export.py`，指令只有 `check`、`files`、`validate`、`write` 四個，
  介面見 [contracts/cli.md](./contracts/cli.md)；SKILL.md 的必要指示見 [contracts/skill.md](./contracts/skill.md)。

  | 行為 | 放哪裡 | 理由 |
  |---|---|---|
  | 專用目錄的狀態：不存在、本功能的、衝突、無法讀取、版本較新（Edge Cases、FR-011） | 腳本 `check` | 看檔名、標記與版本即可決定；判斷錯了會覆蓋維護者的檔案 |
  | 世代紀錄的讀取與驗證、這一代的世代編號（FR-012、US4-1、US4-2） | 腳本 `check` | 「有沒有紀錄、是第幾代」可決定；算錯會讓整條世代鏈斷掉 |
  | 既有養分的讀取、驗證、是否被手動編輯過（FR-014） | 腳本 `check` | 以雜湊與標記比對可決定（R4） |
  | 專案是否有 constitution、哪些功能有 spec（FR-005） | 腳本 `check` | 只看檔案是否存在；不依賴 `.specify/` 的其他部分 |
  | 可讀取的檔案清單：排除相依套件、建置產物、被 git 忽略的檔案、二進位檔、鎖定檔、機密檔案（FR-008、FR-015、FR-017） | 腳本 `check`、`files` | 排除規則是固定的清單，可決定、可測試；交給 Claude 每次自行判斷會漂移 |
  | 專案是否過大、主要區塊有哪些（FR-016、Edge Cases） | 腳本 `check` 判定；SKILL.md 請維護者選擇範圍 | 門檻可決定；選哪些區塊是維護者的決定 |
  | 可讀檔案中疑似機密值的位置（FR-015） | 腳本 `files` 標出路徑與行號 | 樣式比對可決定；讓 Claude 讀之前就知道哪幾行不能引用 |
  | 讀取 spec、文件、設定、測試與程式結構，導出功能與需求（FR-005、FR-006、US2） | SKILL.md | 需要理解語意 |
  | 需求只描述使用者需求與可驗收的行為、不描述實作（FR-004） | SKILL.md | 「這句話是不是實作描述」是語意判斷 |
  | 疑點（疑似 bug、矛盾、改進建議）另外列出、逐項請維護者決定（FR-007、Edge Cases） | SKILL.md；養分的結構沒有「未決疑點」的位置，只能成為項目或被捨棄 | 辨認疑點是語意判斷；結構保證沒有被遺漏的未決疑點寫入養分 |
  | 經驗教訓的整理與分類（FR-009、US3） | SKILL.md；`kind` 只接受三種值 | 整理是語意工作；分類的值可驗證 |
  | 草稿的呈現、逐項修改與刪除、最終確認（FR-010、US1-2、US1-3） | SKILL.md | 對話行為 |
  | 養分的格式、結構驗證、版本、正規化的序列化（FR-002、FR-019） | 腳本 `validate`、`write` | 可決定；這是 007 的輸入契約，必須由同一段程式寫出 |
  | 沒有依據的項目必須是待確認（FR-006、SC-003、原則 IV） | 腳本 `validate`：`confirmed` 的項目 MUST 有依據；依據的檔案 MUST 存在 | 可決定；這是 SC-003 唯一能自動驗證的方式 |
  | 繼承項目保留來源世代、前代項目不能無聲消失、被捨棄的項目保留紀錄（FR-012、FR-013、SC-006） | 腳本 `validate` 對照世代紀錄 | 可決定；三代追溯能否成立取決於這幾條 |
  | 新舊養分的差異（FR-014、US4-4） | 腳本 `validate` 輸出差異；SKILL.md 呈現並請維護者確認 | 逐項比對可決定；呈現是對話 |
  | 不含 plan、tasks、程式碼（FR-003、SC-004） | 兩邊：SKILL.md 指示；腳本拒絕程式碼區塊與未定義的欄位 | 語意上的「程式碼」只能由 Claude 判斷；程式碼區塊與多餘欄位可決定性地擋下 |
  | 機密值不出現在草稿與養分（FR-015、SC-004） | 兩邊：SKILL.md 指示；腳本拒絕符合機密樣式的字串與指向機密檔案的依據 | 同 005 R8 |
  | 寫入只發生在專用目錄、原子寫入、不覆蓋（FR-011、SC-001、原則 III） | 腳本 `write` | 可證明、可測試 |
  | 確認前不寫入（FR-010、SC-002） | SKILL.md 決定何時呼叫 `write`；腳本除 `write` 外全部只讀 | Claude 的時機只能靠指示；腳本可證明只有一個指令會寫入 |
  | 全程只讀（FR-008） | 兩邊：SKILL.md 列出允許的動作；腳本的只讀指令不寫入任何檔案 | 見 R5 |
  | 結束報告與下一步 `/sdd-rebuild`（FR-018） | SKILL.md；`write` 輸出位置與各類數量 | 報告是對話；位置與數量由腳本給出避免漏列 |

- **Rationale**：與 005 R1 相同的兩個問題：「錯了會不會在檔案上留下難以發現的後果」與「判斷是否需要理解語意」。
  前者是、後者否的放腳本；需要語意的放 SKILL.md；兩者都有的由 SKILL.md 執行、腳本檢查結果。
  本功能的養分會被 007 解析，格式錯誤的代價特別高，所以格式的一切（欄位、版本、序列化、世代規則）都由腳本負責。
- **Alternatives considered**：
  - 不寫腳本，由 Claude 以 Write 工具直接寫出養分：格式與欄位會隨每次對話漂移，007 無法可靠解析；
    「只寫專用目錄」「不覆蓋」只能靠指示；除了結構檢查之外沒有任何行為能在 CI 驗證，難以滿足原則 II。
  - 由腳本做需求導出（例如以靜態分析列出路由、指令、設定鍵當成需求）：只能得到實作的清單，
    違反 FR-004（需求要描述使用者需求，不是實作），而且只適用於特定語言。
  - 加入 `clear` 或刪除指令：本功能沒有需要清除的進度，養分要刪除時由維護者自己刪；少一個會刪檔的指令就少一個風險。

## R2 養分的檔案格式與專用目錄

### 目錄

- **Decision**：養分寫在舊專案根目錄的 **`.sdd-export/`**。這個目錄只屬於 sdd-export，裡面只會有三個檔案：

  | 檔案 | 角色 |
  |---|---|
  | `nutrients.json` | 養分本體，**唯一的資料來源**；007 只讀這個檔案 |
  | `README.md` | 由腳本從 `nutrients.json` 產生的可讀版本，第一行是標記（含兩個雜湊，見 R4），供維護者在 GitHub 或編輯器閱讀 |
  | `.gitattributes` | `* text eol=lf`，讓三個檔案在任何平台 checkout 時都維持 LF |

- **Rationale**：
  - 不放 `.specify/` 底下：舊專案不一定有 Spec Kit（FR-001），而且 `.specify/` 由 sdd-init／sdd-update 管理，
    `/sdd-init remove` 會整理它；原則 I 也讓那裡的歸屬變複雜。頂層的獨立目錄與 Spec Kit 完全無關。
  - 以 skill 的名稱為目錄名，歸屬一目瞭然：看到 `.sdd-export/` 就知道是哪個工具產生的、要用哪個工具更新。
    007 寫世代紀錄的 `.sdd-rebuild/` 採同一個慣例（R3），兩者對稱。
  - 點開頭表示工具的中繼資料（與 `.github/`、`.specify/` 相同）：不會與任何語言的原始碼目錄撞名，
    多數建置工具與 linter 預設不掃描點開頭的目錄，所以不會被舊專案的建置流程當成原始碼。
  - 它會被提交到 repo（FR-011「可以隨 repo 提交」、Assumptions「跨機器搬運的方式是取得舊專案的 repo」），
    所以不加自我忽略的 `.gitignore`（與 005 的進度相反）。
- **Alternatives considered**：
  - `.specify/sdd-export/`：見上，舊專案可能沒有 `.specify/`，有時又要處理原則 I 的歸屬。
  - 不帶點的 `sdd-export/` 或 `nutrients/`：在檔案總管與 IDE 中和原始碼並列，像是專案的一部分；
    `nutrients/` 這類通用名稱也可能與既有目錄撞名。
  - 共用的 `.sdd/`（006、007 的檔案放在一起）：FR-011 要求「專用」目錄，007 若在 006 的目錄裡寫檔，
    「目錄內有不是本功能產生的內容就停止」這條衝突規則就無法成立。

### 格式

- **Decision**：
  - **單一 JSON 檔案** `nutrients.json`，`schema` 為 1。所有內容（原則、功能、需求、相依、教訓、世代、捨棄紀錄）
    都在這個檔案裡；結構化的部分是欄位（`id`、`origin`、`status`、`depends_on`、`evidence` 等），
    給人與 Claude 讀的部分是字串欄位（`title`、`text`、`reason` 等）。欄位定義見 [data-model.md](./data-model.md)。
  - 序列化由腳本固定：UTF-8（無 BOM）、LF、縮排 2、`ensure_ascii=False`（中文直接可讀）、
    鍵的順序依 data-model 固定、陣列保留 Claude 給的順序（功能依相依順序）、結尾換行。
    同樣的內容在兩個平台寫出的位元組完全相同。
  - `README.md` 是可讀版本：標題、世代資訊、原則、每個功能的需求與相依、教訓、捨棄紀錄，
    以固定的英文標籤與 Markdown 結構從 `nutrients.json` 產生。它不是資料來源；第一行標記寫明「由 sdd-export 產生、請勿編輯」。
  - 版本規則：讀取者（本 skill 與 007）遇到 `schema` 大於自己認得的版本時 MUST 停止並說明需要更新 skill，
    MUST NOT 猜測內容；遇到較舊的版本時由讀取者負責轉換（v1 沒有較舊的版本）。新增欄位或改變意義都 MUST 加版本。
- **Rationale**：
  - **007 要能可靠解析**：JSON 有標準函式庫的解析器，兩邊都不需要第三方套件（Python 標準庫沒有 YAML），
    也能用同一段驗證程式（007 可以載入本腳本的驗證函式，R12）。Markdown 的結構靠標題與清單，
    維護者手動編輯時很容易破壞，解析器要處理的情況太多。
  - **維護者能直接閱讀與編輯**：縮排的 JSON、非 ASCII 字元不跳脫，中文可以直接讀與改；
    另外產生的 `README.md` 讓不想看 JSON 的時候也能讀。手動編輯 JSON 後，`check` 會驗證並指出錯在哪個欄位。
  - **git 差異好讀**：每個欄位一行、鍵順序固定、陣列順序穩定，改一條需求只會改一行；
    `exported_at` 只記日期，同一天重複匯出不會產生差異。
  - **跨平台原樣互通**：固定的編碼、換行與 `/` 分隔的相對路徑；`.gitattributes` 防止 Windows 的 `core.autocrlf`
    在 checkout 時改成 CRLF（實測）。讀取時另外先正規化換行再計算雜湊，即使 `.gitattributes` 被拿掉也不會誤判為手動編輯。
  - **單一檔案**：寫入可以用「寫暫存檔再取代」一次完成，不會出現「一半的功能是新的、一半是舊的」；
    007 只需要讀一個檔案；數十個功能約數百 KB，JSON 解析沒有負擔。數十個功能時維護者閱讀用的是 `README.md`，
    差異以功能的 `id` 為單位呈現（R4），不需要靠檔案切分。
- **Alternatives considered**：
  - **每個功能一個檔案**（`features/<id>.json` 加一份索引）：差異與手動編輯更局部，但寫入跨多個檔案，
    中途失敗會留下新舊混合的養分（目錄的取代在 Windows 不是原子操作）；007 要處理檔案缺漏與索引不一致；
    刪除功能時腳本要刪檔，與「不刪除」的保證衝突。
  - **Markdown 加 YAML front matter**：最好讀，但需要第三方 YAML 套件或自寫解析器；Markdown 本文的結構無法可靠解析。
  - **只有 JSON、不產生 `README.md`**：少一個檔案，但數十個功能時 JSON 不便閱讀；產生的成本低，且它的標記
    同時讓 `check` 能偵測 JSON 是否被手動編輯過（R4），所以保留。
  - **TOML**：Python 3.11 有讀取器但沒有寫入器，多行中文字串的編輯體驗也不比 JSON 好。

### 養分內容的語言

- **Decision**：欄位名稱與列舉值（`kind`、`status` 等）是英文；**字串內容（原則、需求、教訓、理由）一律使用繁體中文**，
  MUST、SHOULD 等規範詞保留英文，檔名、識別字與專有名詞保留原文。`language` 欄位固定為 `"zh-Hant"`。
  舊專案的 spec 或文件是其他語言時，Claude 在草稿中翻譯，由維護者確認草稿時一併確認。
- **Rationale**：養分會被 007 用來產生新專案的 constitution 與 spec；本專案 constitution 原則 VI 要求 constitution 與 spec
  使用繁體中文，007 的 FR-021 也以繁體中文為預設。在匯出時就統一語言，翻譯發生在有原文可對照、維護者會逐項確認的時候，
  007 不必再翻譯一次；與維護者對話的語言（全域 CLAUDE.md 的繁體中文）也與草稿一致，確認時不必在兩種語言間切換。
  欄位名稱維持英文，因為它們是給腳本與 007 解析的。
- **Alternatives considered**：
  - 沿用舊專案文件的語言：同一份養分可能混合多種語言，007 要在產生 spec 時才翻譯，那時沒有原文可對照，也沒有逐項確認。
  - 英文：與 skill 的語言一致，但 007 產生的文件是繁體中文，等於翻譯兩次。

## R3 世代的表示方式與世代紀錄（007 的寫入契約）

### 世代編號

- **Decision**：
  - **專案的世代**：專案有世代紀錄時是紀錄中的 `generation`；沒有時是 1（FR-012、US4-2）。
  - **養分的 `generation`** 等於匯出它的專案的世代。第一代專案匯出的養分是 1；由它重建的專案，
    007 在世代紀錄寫下 `generation: 2`；那個專案日後匯出的養分就是 2，比上一代的養分大一（US4-1）。
  - 同一個專案再次匯出時世代不變（同一代的養分只是更新）。
  - 世代編號由腳本 `check` 計算並輸出；`validate` 要求草稿的 `generation` 等於它。Claude 不自己計算。
- **Rationale**：「世代」是專案的屬性，不是匯出次數。把它定在世代紀錄上，由 007 在重建時加一，006 只讀取，
  兩個 skill 各負責一次轉換，不會重複加一，也不會因為重複匯出而跳號。

### 項目的身分與來源

- **Decision**：養分中的每個項目（原則、功能、需求、教訓、捨棄紀錄）都有：
  - `id`：小寫英數與連字號，**在整份養分中唯一，且跨世代不變**。繼承的項目沿用原本的 `id`；這一代新增的項目由 Claude
    取新的 `id`，MUST NOT 與世代紀錄或既有養分中任何項目（含捨棄紀錄）的 `id` 重複。
  - `origin`：首次出現的世代（整數，1 ≤ `origin` ≤ `generation`）。**繼承**的項目 `origin` 小於 `generation`；
    **這一代新增**的項目 `origin` 等於 `generation`。這就是區分繼承與新增的方式，不另設欄位。
  - `revised`：內容在哪些世代被修改過（遞增的整數陣列，每個值大於 `origin`、不大於 `generation`）。
  - `derived_from`：由前代的哪些項目合併或拆分而來（`id` 的陣列）。007 合併兩個需求時，新項目的 `origin` 是重建後的世代，
    `derived_from` 列出被合併的前代 `id`，追溯就此延續（007 US3-3）。
  - 捨棄的項目移到 `discarded`，保留 `id`、`kind`、`origin`、內容與理由，加上 `discarded_in`（在哪一代被捨棄）。
- **腳本的世代規則**（`validate` 對照世代紀錄與既有養分，決定性地檢查；違反時列出項目 `id`）：
  1. 草稿的 `generation` 等於 `check` 算出的世代。
  2. 世代紀錄中的每個項目，在草稿中 MUST 仍是有效項目（`id` 相同）或出現在 `discarded`；不能無聲消失（SC-006）。
  3. 繼承的項目 MUST 保留世代紀錄中的 `origin`；`origin` 小於 `generation` 的項目 MUST 能在世代紀錄或既有養分中找到同一個 `id`。
  4. 繼承項目的內容（`text` 或 `title`）與世代紀錄不同時，`revised` MUST 包含這一代。
  5. 世代紀錄與既有養分中 `discarded_in` 小於這一代的捨棄紀錄 MUST 原樣保留；`discarded` 中的 `id` MUST NOT 同時是有效項目
    （被捨棄的需求不會重新出現為有效需求，007 US3-4）。
  6. `derived_from` 中的每個 `id` MUST 出現在世代紀錄或既有養分中。
- **Rationale**：只要 `id` 跨世代不變、`origin` 不被重設、前代項目不能無聲消失，第一代的需求在第三代的養分中
  就一定仍以同一個 `id` 與 `origin: 1` 出現，或以 `discarded` 記錄它在哪一代被捨棄（SC-006）。
  這幾條都可決定，放在腳本就能在 CI 以三代的測試資料驗證，而不是靠 Claude 每次記得。
- **Alternatives considered**：
  - 每個項目記一份完整的世代歷史（每一代的文字）：檔案隨世代增長，對 007 的用途（知道來源與是否修改過）沒有幫助。
  - 以內容雜湊當身分：修改一個字就變成另一個項目，追溯中斷。
  - 只記「繼承／新增」的布林值：無法追溯到第幾代，SC-006 不成立。

### 世代紀錄（**這是 007 sdd-rebuild 要實作寫入的契約**）

- **Decision**：
  - **位置**：新專案根目錄的 **`.sdd-rebuild/lineage.json`**。`.sdd-rebuild/` 只屬於 sdd-rebuild；006 只讀其中的
    `lineage.json`，不讀也不寫目錄中的其他檔案。它 MUST 被提交到 repo（不入庫的話換一台機器匯出就變成第一代）。
  - **格式**：與養分相同的序列化規則；`"tool": "sdd-rebuild"`、`schema` 為 1。內容是重建時**確認後**的原則、功能、
    需求、教訓與捨棄紀錄，項目結構與養分相同，差別是：沒有 `evidence` 與 `status`（重建時待確認的項目已由維護者逐項決定，
    007 FR-018），功能多一個 `spec_dir`（產生的 spec 資料夾），另有 `source`（來源養分的世代與專案名稱）。
    完整欄位見 [data-model.md](./data-model.md) 的「世代紀錄」。
  - **007 寫入時的規則**（006 的 `check` 依此驗證，不符合時停止）：`generation` = 來源養分的 `generation` + 1；
    原樣保留的項目沿用 `id`、`origin`；修改的項目在 `revised` 加上新的世代；合併的項目取新 `id`、`origin` 為新的世代、
    `derived_from` 列出被合併的 `id`；重建時新增的需求 `origin` 為新的世代；被捨棄的項目移到 `discarded`
    並設 `discarded_in` 為新的世代；來源養分中的 `discarded` 全部原樣帶入。
    這一組規則就是 006 的世代規則（上一節）以 `generation` 加一的方式套在重建上。
- **為什麼不放 `.specify/`**：重建後的新專案通常已導入 Spec Kit，放在 `.specify/` 內本來是允許的（原則 I 讓本專案的工具新增
  自己的檔案並記錄歸屬）。但 (1) 006 在任何專案都要能讀它，而 006 不依賴 `.specify/`；(2) 世代紀錄必須入庫並長期保留，
  `.specify/` 會被 `/sdd-init remove` 與 `/sdd-update` 整理，歸屬要另外登記；(3) 與 `.sdd-export/` 對稱，兩個目錄各屬一個工具，
  歸屬由名稱表明，不需要另外的登記檔。
- **006 如何使用它**：`check` 輸出整份世代紀錄與兩份對照清單：世代紀錄中 `spec_dir` 已不存在的功能，
  以及 `specs/` 中不在世代紀錄的 spec（這一代新增的功能）。Claude 據此組草稿：對應到世代紀錄的功能沿用 `id` 與 `origin`，
  比對目前的 spec 與紀錄中的內容決定是否列為修改；新的 spec 成為 `origin` 為這一代的功能；
  `spec_dir` 已不存在的功能請維護者決定保留（依紀錄的內容）或捨棄；紀錄中的教訓逐項請維護者決定是否仍然適用（FR-013、US4-3）。
- **Alternatives considered**：
  - `.specify/sdd-rebuild/lineage.json`：見上。
  - 寫進新專案的 constitution 或 spec（例如在 spec 開頭加註來源世代）：那些檔案由 Spec Kit 產生，007 不能手寫（原則 I），
    而且資訊分散在數十個檔案。
  - 由 007 直接在新專案寫一份 `.sdd-export/nutrients.json` 當作世代紀錄：會讓新專案「看起來已經匯出過」，
    違反 `.sdd-export/` 只屬於 006 的約定，也混淆「已匯出的養分」與「重建時的紀錄」。
  - 世代紀錄只記 `id` 與 `origin`，內容到舊專案的養分去找：舊專案不一定在這台機器上，006 也不讀其他專案。

## R4 再次匯出

- **Decision**：
  1. **同一份**：養分永遠是 `.sdd-export/nutrients.json`，`write` 取代它，不產生第二份（FR-014）。
  2. **手動編輯的偵測**：`write` 在 `README.md` 的第一行標記記下兩個雜湊：`source-sha256`（寫入時 `nutrients.json`
    換行正規化後的雜湊）與 `view-sha256`（`README.md` 其餘內容的雜湊）。`check` 據此回報：
     - `nutrients: "edited"`：`nutrients.json` 與上次匯出寫入的內容不同（維護者手動編輯，或上次寫入在兩個檔案之間中斷）。
     - `view: "edited"`：`README.md` 本文被手動改過；`"stale"`：本文沒被改，但對應的是舊的 `nutrients.json`；`"missing"`：不存在。
     手動編輯過的 `nutrients.json` 仍要通過驗證；無法解析或不符合結構時 `check` 停止並指出欄位，由維護者修正（不覆蓋）。
  3. **草稿的起點**：Claude 以既有養分（含手動編輯）為起點，加上專案目前的狀態組成新草稿。既有項目沿用 `id`；
     依據沒有改變的項目不改寫文字。`nutrients` 為 `"edited"` 時，Claude 先告訴維護者，並把手動編輯的內容當成維護者的決定：
     要改動它們時 MUST 逐項詢問。
  4. **差異**：`validate` 對照既有養分輸出逐項差異：新增、移除、修改（列出改變的欄位與新舊值），以 `id` 為單位，
     各區段分開。Claude 在最終確認前呈現差異（沒有差異時明說）；移除的項目與修改的既有內容是維護者要特別確認的部分。
  5. **寫入時的並行保護**：`check` 輸出 `state`（專用目錄中兩個檔案目前內容的雜湊）；`write` MUST 帶 `--expect <state>`，
     目前的內容不同時拒絕寫入（`reason: "changed"`）。維護者在對話途中又手動改了養分時，Claude 重新 `check`、
     重新呈現差異並再次確認，不會蓋掉剛改的內容。
  6. **`README.md`**：`view` 為 `"edited"` 時，寫入會重新產生它而蓋掉手動修改；Claude MUST 先告訴維護者，
     請他決定把那些修改併入草稿或放棄。它是本功能產生、標明不要編輯的檔案，重新產生不違反原則 III。
- **Rationale**：差異由腳本計算，維護者看到的「會改變什麼」是決定性的；手動編輯以雜湊偵測，不依賴 git
  （舊專案不一定是 git repository）；`--expect` 讓「確認的差異」與「實際寫入」之間沒有空窗。
- **Alternatives considered**：
  - 每個項目各存一個雜湊來偵測哪一項被改過：養分裡會出現對維護者沒有意義的欄位，手動編輯時還要求他別動它。
    檔案層級的偵測加上逐項差異已足夠讓 Claude 指出改了什麼。
  - 每次都從零重新導出、忽略既有養分：會丟掉維護者在上次匯出時的修改與手動編輯。
  - 以 git 的差異判斷：舊專案不一定是 git repository，養分也可能還沒提交。

## R5 從程式碼導出需求的流程與只讀保證

### 讀取範圍與排除規則

- **Decision**：Claude 只讀取 `files` 列出的檔案（加上 `check` 輸出的世代紀錄與既有養分）。`files` 的清單如下決定：
  1. 專案是 git repository 時以 `git ls-files -z --cached --others --exclude-standard` 取得清單（尊重 `.gitignore`）；
     不是時走訪目錄樹。兩種情況都再套用以下的固定排除，並且不跟隨指向專案外的符號連結。
  2. **相依套件**（`dependency`）：`node_modules/`、`bower_components/`、`vendor/`、`.venv/`、`venv/`、`Pods/`、`.terraform/` 等。
  3. **建置產物與快取**（`build`）：`dist/`、`build/`、`target/`、`bin/`、`obj/`、`out/`、`.next/`、`.nuxt/`、`coverage/`、
     `__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.tox/`、`.gradle/`、`.cache/` 等。
  4. **工具與編輯器**（`tooling`）：`.git/`、`.idea/`、`.vscode/`、`.claude/`、`.sdd-export/`、`.sdd-rebuild/`（後兩者由 `check` 讀取）、
     `.specify/`（但 `.specify/memory/constitution.md` 列入可讀）。
  5. **鎖定檔與產生的檔案**（`generated`）：`package-lock.json`、`yarn.lock`、`pnpm-lock.yaml`、`uv.lock`、`poetry.lock`、
     `Cargo.lock`、`go.sum`、`composer.lock`、`*.min.js`、`*.map` 等。
  6. **二進位檔**（`binary`）：依副檔名（圖片、影音、字型、壓縮檔、執行檔、資料庫檔等），以及開頭 8 KiB 含 NUL 位元組的檔案。
  7. **過大的單一檔案**（`large`）：超過 1 MiB。
  8. **機密檔案**（`secret`）：見 R6；腳本**也不開啟**它們，只列出路徑。
  完整清單與比對方式在 [data-model.md](./data-model.md) 的「讀取範圍」，以常數集中在腳本內。
- **Rationale**：FR-017 的「相依套件與建置產物」在不同語言有不同的目錄名；集中成固定清單，兩個平台、每次執行都一樣，
  也能逐項測試。git 的忽略規則是專案自己對「什麼不是原始碼」的宣告，能用時優先採用。
  spec 與 plan 文件（`specs/**`）仍可讀：plan、research 中的決定與理由是經驗教訓的重要來源，只是內容不能被抄進養分（FR-003）。

### 專案過大

- **Decision**：`check` 依可讀檔案計算 `too_large`：檔案數超過 1500、總大小超過 10 MiB，或有兩個以上的頂層區塊各自帶有
  套件描述檔（`package.json`、`pyproject.toml`、`go.mod`、`Cargo.toml`、`pom.xml`、`*.csproj` 等，視為 monorepo）。
  並輸出主要區塊（頂層目錄）的檔案數、大小與描述檔。`too_large` 時 Claude MUST 先列出區塊、以 AskUserQuestion（可複選）
  請維護者選擇範圍，再以 `files --scope <路徑>` 取得該範圍的清單；`too_large` 時不帶範圍的 `files` 不列出檔案（FR-016）。
  選定的範圍寫入養分的 `scope`（`coverage: "partial"` 與 `included`），讓 007 知道養分只涵蓋部分專案。
- **Rationale**：門檻是可調的常數，目的不是精準，而是「一次讀不完時一定先問」。範圍記在養分裡，
  也讓大型專案可以分批匯出（R7）。

### 依據的引用

- **Decision**：每個項目的 `evidence` 是字串陣列，每一筆是下列三種之一：
  - 專案內的相對路徑（`/` 分隔，檔案或目錄），寫入時 MUST 存在、MUST NOT 是機密檔案或被排除的路徑；
  - `commit:<7 至 40 位十六進位>`：git 歷史中的 commit（教訓常以此為依據），寫入時 MUST 存在於 repository；
  - `maintainer`：維護者在這次對話中口頭提供（US3-3）。
  `status` 為 `"confirmed"` 的項目 MUST 至少有一筆依據；沒有依據的 MUST 是 `"pending"`（待確認）。
  不記行號：行號隨程式碼變動很快失效，路徑的粒度已足夠讓維護者與 007 追溯。
- **Rationale**：依據能被腳本驗證存在，SC-003 才能自動檢查；`maintainer` 讓口頭補充有合法的位置，
  而不是被迫寫成沒有依據的事實（原則 IV）。

### 待確認與疑點

- **Decision**：
  - **待確認**：項目的 `status: "pending"`，可以寫入養分（007 FR-018 會逐項請維護者決定）。草稿中以「待確認」標示。
  - **疑點**（疑似 bug、文件與程式碼矛盾、spec 與程式碼矛盾、改進建議）：只存在於草稿，草稿中與需求分開列成一節。
    每一項 MUST 由維護者決定：納入（成為需求或教訓，必要時修改文字）、標為待確認（成為 `pending` 的項目）、或捨棄。
    捨棄的疑點以 `kind: "doubt"` 記入 `discarded`，下次匯出時 Claude 不再重提。養分的結構**沒有**「未決疑點」的位置。
  - spec 與程式碼矛盾時，兩邊的說法都列在疑點中，由維護者選擇，Claude 不自行選擇（Edge Cases）。
- **Rationale**：FR-007 要求疑點與需求分開且逐項決定；讓結構中不存在未決疑點，就保證沒有疑點未經決定就進入養分。

### 只讀的保證

- **Decision**：
  - **SKILL.md 能保證的（指示）**：讀取只用 Read、Grep、Glob 這類讀取工具，範圍限於 `files` 的清單；
    允許的指令只有本 skill 的腳本與只讀的 git 指令（`git log`、`git show`、`git ls-files`、`git blame`，都加 `--no-pager`）；
    MUST NOT 執行建置、測試、安裝套件、格式化、產生程式碼或任何專案自己的腳本；MUST NOT 以 Write、Edit 或其他方式
    在專案內建立檔案，包括暫存檔（草稿經 stdin 交給腳本）。
  - **腳本能保證的（可測試）**：`check`、`files`、`validate` 不在任何地方寫入檔案；`write` 只寫 `.sdd-export/` 內的三個檔案
    與同目錄的暫存檔；唯一的外部指令是只讀的 `git`（`rev-parse`、`ls-files`、`cat-file -e`），以 `--no-optional-locks`
    執行，避免 git 為了更新 index 的快取而寫入 `.git/`；腳本不接受從檔案讀入草稿，所以不需要在專案內放暫存檔。
  - **uv**：以 `uv run <腳本>` 執行帶 inline metadata 的腳本時，uv 使用自己的快取環境，不會在專案內建立 `.venv` 或 `uv.lock`，
    即使專案有 `pyproject.toml`（實測）。
- **Rationale**：Claude 的工具使用無法由程式攔截，只能以明確的允許清單約束；腳本這一側則可以在測試中以
  「執行前後的檔案樹快照相同」證明不寫入。
- **Alternatives considered**：由腳本代讀檔案再交給 Claude（Claude 不直接讀專案）：等於把整個專案經 stdout 傳遞，
  大型專案不可行，也無法比 Read 工具更安全。

## R6 機密的處理

- **Decision**：
  - **不開啟的檔案**（`secret`）：檔名或路徑符合 `.env`、`.env.*`（含 `.env.example` 等範例檔，寧可漏讀不可誤讀）、`*.pem`、
    `*.key`、`*.p12`、`*.pfx`、`*.jks`、`*.keystore`、`*.kdbx`、`id_rsa*`、`id_dsa*`、`id_ecdsa*`、`id_ed25519*`、`.netrc`、
    `.npmrc`、`.pypirc`、`*.tfvars`、`*.tfstate*`、`credentials*`、`secrets.*`、`*secret*.json`、`service-account*.json`，
    以及 `.ssh/`、`.aws/`、`.gnupg/` 底下的所有檔案。`check` 與 `files` 只列出路徑（Edge Cases「只記錄位置」），
    腳本自己也不開啟它們；SKILL.md 指示 Claude MUST NOT 讀取，需要時只在草稿提到「某處有一份機密檔案」。
  - **可讀檔案中的機密值**：`files` 以 005 R8 的樣式（私鑰標頭、常見權杖前綴、URL 中的 `user:password@`、
    `password`／`secret`／`token`／`api_key` 後接 `=` 或 `:` 與值）掃描清單中的檔案，輸出命中的路徑與行號（不輸出內容）。
    Claude 讀到這些行時 MUST NOT 在對話或草稿中引用其值；需要時寫成「`<路徑>` 第 N 行有寫死的憑證」這類疑點（改進建議）。
  - **寫入前的攔截**：`validate` 與 `write` 掃描草稿的每個字串值，符合同一組樣式時拒絕（`reason: "secret"`，
    指出欄位路徑但不重複印出該值）；`evidence` 指向機密檔案時同樣拒絕。Claude 改寫成不含值的描述後重試。
- **Rationale**：辨認機密主要是語意判斷，只能靠 Claude；但「哪些檔案不開」「寫入前擋下常見樣式」是決定性的安全網，
  可在 CI 測試。範例檔（`.env.example`）常被填入真實值，一律不開啟；它的用途（需要哪些設定）通常能從讀取設定的程式碼得知。
- **限制**：樣式無法涵蓋所有機密；Claude 讀取可讀檔案時一定會看到其中的值，只能靠指示不引用。這兩點寫入 README。
- **Alternatives considered**：以熵值偵測：誤判太多。開啟範例檔：多數專案確實是假值，但只要有一次是真值就違反 FR-015。

## R7 中途結束與失敗

### 沒有進度是否可行

- **Decision**：維持 spec 的規定：**確認前不寫入任何內容，也不保存進度**。大型專案以三個方式讓它可行：
  1. **縮小範圍**（R5）：專案過大時一定先選範圍，一次只討論一個或幾個區塊。
  2. **分批匯出**：每一次確認並寫入的養分都是一個完整、有效的檢查點。第一次只匯出部分範圍（`coverage: "partial"`），
     之後再執行 `/sdd-export` 選擇其他範圍；再次匯出以既有養分為起點（R4），範圍外的既有項目原樣保留，
     最後一次涵蓋全部時改為 `"full"`。
  3. **分段確認**：草稿依區段（世代資訊、原則、功能與需求、疑點、教訓）逐段呈現與決定；決定後的內容留在對話中，
     最終確認只需要看整體與差異，不重新逐項討論。
- **Rationale**：保存進度需要在確認前寫檔，與 spec 的 Edge Cases、FR-010「確認前 MUST NOT 寫入任何檔案」直接衝突。
  分批匯出讓「確認」成為天然的保存點，代價只是大型專案要執行多次，而這本來就是 FR-016「先縮小範圍」的意圖。
- **風險**：單一批次的對話中斷（session 結束、context 被壓縮）時，該批次尚未確認的決定會遺失。
  SKILL.md 要求在每段決定後把那一段的結論以簡短清單留在對話中，壓縮後仍能接續；真的遺失時重新執行即可，
  不會留下任何檔案。這是本設計明確接受的代價（列入 plan 的取捨）。
- **Alternatives considered**：
  - 比照 005 把進度存在 `.sdd-export/` 或 `.specify/` 並自我忽略：違反 spec 的 Edge Cases 與 FR-010；
    需要修改 spec，不在本 plan 的權限內。
  - 把進度存在專案外（使用者層級的目錄）：同樣是「確認前寫入」，只是換了地方；也引入機器專屬路徑。

### 每一種中斷與失敗

- **Decision**：每一種情況的行為與下一步，都在 [contracts/skill.md](./contracts/skill.md) 依階段逐一寫出。摘要：

  | 情況 | 行為 |
  |---|---|
  | 維護者在確認前結束（任何階段） | 不寫入任何內容；告訴維護者沒有保存任何東西，再執行 `/sdd-export` 會重新開始 |
  | `.sdd-export/` 已存在但不是本功能產生的（含同名檔案、目錄內有其他檔案） | `check` 結束碼 3、`reason: "conflict"`；不讀取專案、不組草稿，列出衝突的路徑並停止；請維護者移走或改名後再執行 |
  | 既有養分無法解析、不符合結構、版本較新 | `check` 結束碼 3；列出原因（欄位路徑或版本），停止；不覆蓋。版本較新時請維護者更新 skill |
  | 世代紀錄無法解析、不符合結構、版本較新、`tool` 不符 | 同上；不把專案當成第一代（那會切斷世代鏈） |
  | 既有養分的世代與算出的世代不同 | 列出兩者與可能原因（世代紀錄被移除、專案是從舊專案複製而來），以一題詢問：停止並檢查（建議）或以算出的世代繼續 |
  | 專案沒有任何可讀檔案，或讀完後內容不足以提出有依據的需求 | 說明原因並停止，不寫入（FR-016） |
  | `check` 回報專案不可寫入 | 先告知，以一題詢問繼續（建議，草稿仍有價值）或停止；繼續時寫入失敗就依「寫入中途失敗」處理 |
  | 確認後 `validate` 不通過（例如機密、依據不存在） | 不寫入；修正草稿，涉及內容改變時讓維護者再確認那一項 |
  | `write` 回報 `changed`（對話途中養分被改） | 重新 `check`、重新組差異，呈現新的差異並再次確認 |
  | `write` 回報 `conflict`（對話途中目錄被別的內容占用） | 停止，回報衝突的路徑；把確認後的草稿完整呈現在對話中 |
  | `write` 中途失敗（權限、唯讀、磁碟） | 腳本以「暫存檔再取代」寫入，`nutrients.json` 不是舊的就是新的，不會是一半；本次建立的空目錄與暫存檔由腳本移除。回報原因，把確認後的草稿完整呈現在對話中（Edge Cases），停止 |
  | 寫入 `nutrients.json` 之後、`README.md` 之前中斷 | 下一次 `check` 回報 `nutrients: "edited"`、`view: "stale"`；內容就是確認過的養分，再次匯出時一併重新產生 `README.md` |
  | 寫入後維護者改變主意 | 再執行 `/sdd-export`（以既有養分為起點修改），或由維護者自己編輯或刪除 `.sdd-export/` |

- **Rationale**：005 的經驗是「確認之後、完成之前」的分支沒想清楚；本功能把寫入縮成單一的 `write`、
  寫入本身原子化、沒有接續狀態，所以確認後只剩「寫入成功」與幾種寫入失敗，每一種都有明確的下一步，而且都不需要接續。

## R8 自動測試的範圍

constitution 原則 II 要求每個功能 MUST 有自動測試並在兩個平台的 CI 通過。與 005 R3 相同，**對話行為不在 CI 驗證**；
CI 證明腳本的行為與「必要的指示存在於 SKILL.md」。

- **Decision**：

  | 類別 | 測試檔 | 涵蓋內容 |
  |---|---|---|
  | 腳本的單元測試 | `tests/unit/test_sdd_export.py` | 專用目錄的各種狀態與衝突、世代的計算與世代紀錄的驗證、既有養分的驗證與手動編輯偵測、讀取範圍的排除（以真實的 `git` 與不是 git 的目錄各測一次）、過大的判定、機密檔案不被開啟、可讀檔案中機密值的定位、草稿驗證（結構、依據、待確認、程式碼區塊、機密、世代規則）、差異、`write` 的原子寫入與 `--expect`、只讀指令執行前後檔案樹相同、`write` 只寫專用目錄、序列化的位元組與固定的測試資料相同、CRLF 版本仍能讀取且不被判為編輯、三代的世代追溯 |
  | skill 的結構與內容檢查 | `tests/unit/test_sdd_export_skill.py` | 資料夾只有三個檔案、frontmatter、SKILL.md 是英文且沒有絕對路徑與信箱、必要指示的關鍵句（逐條對應 FR，見 [contracts/skill.md](./contracts/skill.md)）、指示的順序（`check` 在讀取之前、範圍選擇在讀取之前、確認在 `write` 之前）、README 是繁體中文且涵蓋必要內容、腳本只用標準函式庫且訊息是英文 |
  | 人工驗收 | [quickstart.md](./quickstart.md) 的「人工驗收」 | 實際對話：導出需求的品質、疑點與待確認的呈現、教訓、確認前不寫入、再次匯出的差異、世代延續 |

  FR 與驗證方式的對照：

  | FR | 單元測試 | 結構／內容檢查 | 人工驗收 |
  |---|---|---|---|
  | FR-001 不需要 Spec Kit | `check` 在沒有 `.specify/`、不是 git repository 的目錄正常完成 | 指示：不呼叫 `speckit-*`、不要求 `/sdd-init` | 情境 2 |
  | FR-002 養分的內容 | `validate` 要求各區段與世代欄位 | 指示：草稿的各區段 | 情境 1 |
  | FR-003 不含 plan、tasks、程式碼 | 拒絕程式碼區塊與未定義的欄位 | 指示存在 | 情境 1 |
  | FR-004 只描述需求 | | 指示存在 | 情境 1、2 |
  | FR-005 spec 為先、其餘從程式碼 | `check` 列出 constitution 與 spec；`source` 只接受定義的值 | 指示存在 | 情境 1、3 |
  | FR-006 依據與待確認 | `confirmed` 必須有依據、依據必須存在 | 指示存在 | 情境 2 |
  | FR-007 疑點分開、逐項決定 | 捨棄的疑點以 `doubt` 記錄；結構沒有未決疑點 | 指示：疑點獨立一節、一題一項 | 情境 2 |
  | FR-008 全程只讀 | 只讀指令前後檔案樹相同；git 以 `--no-optional-locks` 執行 | 指示：允許的動作清單、禁止建置與測試 | 情境 2 |
  | FR-009 教訓 | `kind` 只接受三種值；沒有依據必須是 `pending` | 指示：三類、不編造、找不到時說明並請維護者決定 | 情境 4 |
  | FR-010 確認前不寫入 | 只有 `write` 會寫入 | 指示存在，且在 `write` 之前 | 情境 1 |
  | FR-011 專用目錄、不動其他檔案 | `write` 只寫 `.sdd-export/`；衝突時不寫入 | 指示存在 | 情境 1、7 |
  | FR-012 繼承與新增、世代加一 | 世代規則 1 至 4、三代追溯 | 指示：以 `check` 的世代與世代紀錄組草稿 | 情境 5 |
  | FR-013 前代教訓 | 世代規則 2、3 也適用於教訓 | 指示：逐項詢問是否仍然適用 | 情境 5 |
  | FR-014 更新同一份 | `write` 取代同一個檔案；差異；`--expect` | 指示：呈現差異、手動編輯逐項詢問 | 情境 6 |
  | FR-015 機密 | 機密檔案不被開啟、樣式攔截、依據不得指向機密檔案 | 指示：不讀取、不引用、只記位置 | 情境 2 |
  | FR-016 過大先縮小、內容不足就停止 | `too_large` 的判定；不帶範圍時不列檔案 | 指示：先選範圍；內容不足時停止 | 情境 3 |
  | FR-017 排除相依與建置產物 | 排除規則逐項 | 指示：只讀 `files` 的清單 | 情境 3 |
  | FR-018 結束報告 | `write` 輸出位置與數量 | 指示：位置、納入與捨棄、可以提交、`/sdd-rebuild` | 情境 1 |
  | FR-019 跨平台互通 | 序列化的位元組與固定測試資料相同（兩個平台）；CRLF 版本可讀；`.gitattributes` 在 `core.autocrlf=true` 的 clone 中維持 LF | | |
  | FR-020 英文與 README | | 英文、無 CJK；README 繁體中文 | |

- **FR-019 與 cross-platform job**：**不新增**跨平台的 CI job，以 `test` job 在兩個平台執行的單元測試驗證：
  1. 同一份草稿在兩個平台寫出的 `nutrients.json` 與 `README.md`，逐位元組等於 repo 中一份固定的測試資料
     （兩個平台都等於同一份，就等於彼此相同）；
  2. 換成 CRLF 的版本仍能被讀取、驗證，且不被判為手動編輯；
  3. 以真實的 git、`core.autocrlf=true` clone 後，`.sdd-export/` 的檔案仍是 LF。
  理由：003 的 cross-platform job 交換的是「一個平台執行 Spec Kit 腳本後產生的整個 repository」，
  其中有檔案模式與 shell 腳本的行為只能實際交換才驗證得到。養分是腳本以固定規則寫出的純文字，
  「兩個平台的輸出都等於同一份固定的位元組」比交換 artifact 更直接，也不增加 CI 的時間與複雜度。
  固定的測試資料放在 `tests/unit/fixtures/sdd_export/`；repo 根目錄既有的 `.gitattributes`（`* text=auto eol=lf`）已讓它在 Windows runner 上 checkout 為 LF，
  測試另外以位元組比對前先確認檔案不含 CR，避免 checkout 設定改變時誤判。
- **Alternatives considered**：
  - 加入 cross-platform job：一個平台匯出、另一個平台讀取。驗證的內容與上面的第 1 點相同，代價是兩個 job 與 artifact。
  - 在 CI 以非互動模式執行 Claude Code 跑對話：同 005 R3，需要付費呼叫、結果不穩定、沒有 AskUserQuestion，不採用。

## R9 SKILL.md 的 frontmatter

- **Decision**：

  | 欄位 | 值 |
  |---|---|
  | `name` | `sdd-export` |
  | `description` | 一段英文：在舊專案把原則、各功能的需求與相依、經驗教訓與世代資訊匯出成 `.sdd-export/` 中的養分，供新專案以 `/sdd-rebuild` 重生；不需要 Spec Kit；確認前不寫入 |
  | `argument-hint` | `"[scope path ...]"` |
  | `disable-model-invocation` | `true` |

- **Rationale**：這個 skill 會讀取整個專案、可能花很長的對話，並在專案內寫入一個要提交的目錄；
  spec 的 FR-001 與 `home/CLAUDE.md` 都寫「請我在舊專案執行 `/sdd-export`」，也就是由維護者明確啟動，Claude 只負責提醒。
  與 sdd-init、sdd-update 相同，禁止 Claude 主動使用。description 仍要寫清楚用途與執行的地方，
  因為它會出現在 `/` 選單與說明中。`argument-hint` 讓維護者可以一開始就指定範圍（例如大型專案的某個目錄）。
- **與 007 的關係**：禁止模型呼叫代表 007 的 US4（舊專案沒有養分時先匯出）不能以 Skill 工具呼叫 sdd-export；
  007 可以依本 skill 的腳本（`--project <舊專案路徑>`，R11）與 SKILL.md 的規則完成匯出。如何做由 007 的 plan 決定。
- **Alternatives considered**：允許主動使用（與 005 相同）：005 是全域 CLAUDE.md 要求在方向未定時使用的對話；
  本 skill 沒有這種「Claude 判斷時機」的需求，誤觸發的代價卻是在使用者的專案中進行一次長時間的全面讀取。

## R10 Claude 與腳本之間的資料傳遞

- **Decision**：與 005 R7 相同：stdout 上一份 JSON（UTF-8、LF、縮排 2），錯誤時有 `error`（一句英文）與 `reason`
  （固定的列舉值，讓 SKILL.md 依值分支），同一句寫到 stderr；`validate` 與 `write` 從 stdin 讀入完整的草稿 JSON。
  草稿的格式就是養分的格式減去腳本填入的欄位（`tool`、`schema`、`exported_at`）。
- **Rationale**：草稿可能很長、含引號與換行，經 stdin 傳遞在 Windows 與 Linux 相同，也不需要在專案內放暫存檔（R5）。
  `reason` 比解析 `error` 的文字可靠。

## R11 指定專案的位置

- **Decision**：每個指令接受可選的 `--project <目錄>`，預設是目前目錄。輸出中的路徑一律相對於該目錄、以 `/` 分隔。
- **Rationale**：005 只在目前目錄執行，因為它只處理目前的專案。本功能是 007 的前半，007 的 US4 要在新專案的 session
  中對舊專案完成匯出；提供 `--project` 讓 007 不必切換工作目錄就能呼叫，成本只是一個參數。
  本 skill 自己的 SKILL.md 一律在目前目錄執行（維護者在舊專案啟動它），不使用這個參數。
- **Alternatives considered**：只支援目前目錄，由 007 先 `cd`：可行，但在 Windows 的 Git Bash 與 PowerShell 中切換目錄後
  再交由 uv 執行，路徑轉換容易出錯；參數更明確。

## R12 腳本可被載入

- **Decision**：`sdd_export.py` 以模組方式載入時不執行任何動作；讀取與驗證養分、讀取與驗證世代紀錄、序列化、
  機密掃描、排除規則都是獨立的函式。測試以 `importlib` 載入；007 可以比照 004 載入 `sdd_init.py` 的方式，
  從相鄰的 skill 資料夾載入這些函式來讀取養分，確保兩邊用同一份驗證邏輯。
- **Rationale**：格式只有一份實作，就不會出現「006 寫得出、007 讀不懂」。是否真的載入由 007 的 plan 決定；
  006 只保證函式邊界與「載入時無副作用」，並在 [contracts/cli.md](./contracts/cli.md) 列出這些函式。

## R13 結束碼與不提交

- **結束碼**：0 成功；1 用法錯誤、草稿無效或含機密、`write` 的 `changed` 或寫入失敗；3 專案目前的狀態不能匯出
  （專用目錄衝突、既有養分或世代紀錄無法讀取、不符合結構或版本較新、`--project` 不是目錄）。
  2 保留不用、不使用 4（沒有網路操作），與 003 至 005 相同。
- **不提交**：SKILL.md MUST NOT 對舊專案執行 `git add`、`git commit` 或 `git push`；結束時告訴維護者養分可以提交。
  理由：spec 的 Assumptions 寫明「是否把養分提交到 repo 由維護者決定」，FR-011 也要求不修改專用目錄以外的檔案，
  而 commit 會改變 `.git/`。這與全域 CLAUDE.md「每完成一項異動就 commit」不同：那條規則適用於維護者請 Claude 修改的專案，
  本 skill 在舊專案只負責留下養分，提交與否由 spec 明訂交給維護者。

## 實測紀錄

uv 不會在帶有 `pyproject.toml` 的專案內建立檔案（uv 0.13.6）：

```text
mkdir t && cd t && 寫入一份含 dependencies 的 pyproject.toml
uv run /tmp/s.py            # s.py 帶 inline metadata，dependencies = []
→ 輸出 hi；目錄中仍只有 pyproject.toml（沒有 .venv、uv.lock）
```

`.gitattributes` 在 `core.autocrlf=true` 時維持 LF（git 2.43.0）：

```text
git init a; 在 a/.sdd-export/ 放 .gitattributes（* text eol=lf）與 nutrients.json；另放 other.txt；commit
git -c core.autocrlf=true clone a b; 在 b 設定 core.autocrlf=true，刪除兩個檔案後 git checkout -- .
→ b/.sdd-export/nutrients.json 為 LF；b/other.txt 為 CRLF
```
