# Research: sdd-update 更新 Spec Kit

R1 至 R5 是 spec 留給 plan 的五個決定，R6 至 R9 是設計時衍生的決定。
「實測」指 2026-11-20 在 Linux（uv 0.13.6、git 2.43.0）於暫存目錄執行的結果，指令與觀察列在文末的「實測紀錄」。
Windows 上的行為無法在這台機器實測，由 R5 的 CI 測試驗證。003 已定案且本功能沿用的事項（取得最新穩定版、
在專案外產生官方產出、一律 `--script sh`、換行正規化後的 SHA-256、Git Bash 的判定）不在這裡重述，
見 [003 的 research.md](../003-sdd-init/research.md)。

## 官方工具兩個版本之間的差異（實測）

以 `specify init --here --non-interactive --ignore-agent-tools --integration claude --script sh` 分別產生
1.2.6、1.3.3、1.4.2、1.4.3 四個版本的產出後比對：

| 比對 | 檔案數 | 新增的檔案 | 不再提供的檔案 | 內容改變的檔案 |
|---|---|---|---|---|
| 1.4.2 → 1.4.3（相鄰） | 29 → 30 | `.specify/scripts/bash/markdown_sections.py` | 無 | 9 個 `speckit-*/SKILL.md`（frontmatter 內的版本）、`common.sh`、`init-options.json`、`integration.json`、2 個 manifest、`workflow-registry.json` |
| 1.3.3 → 1.4.3 | 29 → 30 | 同上 | 無 | 上列之外再加 `create-new-feature.sh`、`workflows/speckit/workflow.yml` |
| 1.2.6 → 1.4.3 | 30 → 30 | 同上 | `.claude/skills/speckit-taskstoissues/SKILL.md` | 與 1.3.3 → 1.4.3 相同 |

由此得到的設計依據：

- 「新增檔案」與「不再提供檔案」都真的會發生，連相鄰的修訂版之間也有新增；US1 的驗收情境 3 不是假設。
- 每一版的 `speckit-*/SKILL.md` 都會變（frontmatter 寫著版本），所以每次更新至少有十幾個檔案要換；
  維護者只要改過任何一個 SKILL.md，每次更新都會遇到「保留並附新版」。
- 四個版本的 `.specify/memory/constitution.md` 與 5 份範本內容完全相同；這幾版之間範本沒有變。
- 新增的 `markdown_sections.py` 的模式是 0644；可執行的只有 `scripts/bash/*.sh`。新檔案的執行權限只需要處理 `.sh`。
- 官方工具自己的兩種就地更新方式都不符合本功能的需求：
  - `specify init --here --force`：保留既有的 `constitution.md`，但把維護者改過的範本、SKILL.md 與 `.sh` 全部覆蓋
    （違反 FR-005），也不移除不再提供的檔案。
  - `specify integration upgrade`：有被修改的檔案時以結束碼 1 拒絕，不做任何更新；它只管 integration 的檔案，
    不含共用的範本與腳本，也不更新 `init-options.json` 的版本。

所以更新沿用 003 的做法：在專案之外的暫存空目錄以新版執行 `specify init`，再由本功能逐檔比對與處理。

## R1 新版內容以何種形式提供給維護者比對

- **Decision**:
  - 每個被保留、且新版仍提供的檔案 `<P>`，把它的新版內容原樣寫到 `.specify/sdd-update/<P>.new`
    （例如 `.specify/sdd-update/.specify/templates/plan-template.md.new`、
    `.specify/sdd-update/.claude/skills/speckit-plan/SKILL.md.new`），並在 `kept` 那一行寫出這個路徑。
    以下稱它為「比對副本」。
  - 比對副本是本功能自己的檔案：列入導入紀錄的 `entries`，`origin` 為新的值 `sdd-update`（R6）。
  - **是否入庫由維護者決定**。sdd-update 不 commit、不把它加入暫存區，也不寫任何 ignore 規則；它在 `git status`
    中是一般的未追蹤檔案。入庫後可以帶到另一台機器再合併；不想留就直接刪除。
  - **清理**：
    1. 下一次實際更新（版本有變）開始時，刪除紀錄內全部的比對副本，再為這一次被保留的檔案寫入新的。
    2. 維護者可以隨時自行刪除比對副本或整個 `.specify/sdd-update/`；sdd-update 把不存在的比對副本視為已處理完。
    3. `/sdd-init remove` 依紀錄刪除內容未變的比對副本。
  - **不重複列出**（US2 驗收情境 3）：已是最新穩定版時再次執行，只讀取、不寫入。對紀錄內每一份仍存在的比對副本，
    比較專案檔案與比對副本的內容（換行正規化後的雜湊）：相同（維護者已合併）或專案檔案已不存在就不列出；
    不同才列出一行 `kept`。比對副本已被刪除的也不列出。
  - 被保留、但新版**不再提供**的檔案沒有新版內容可附，只列出並說明（R2）。
- **Rationale**:
  - 固定的專用目錄讓「哪些是本工具建立的」一目了然（原則 I），維護者可以用任何工具逐檔比對，
    也能一次刪掉整個目錄。路徑與原檔一一對應，不需要另外查表。
  - 加上 `.new` 後綴，比對副本不會被當成生效的檔案：`SKILL.md.new` 不是 `SKILL.md`，不會被當成 skill 載入；
    `.gitignore.new` 不是 `.gitignore`，不會成為生效的忽略規則；`*.sh.new` 不會被誤執行。
  - 「專案檔案是否已與新版一致」直接由專案檔案與比對副本算出，不需要額外的狀態；雜湊先正規化換行，
    所以比對副本經 git 到 Windows 變成 CRLF 也不影響判定（FR-012）。
  - 已是最新版時完全不寫入，才同時滿足 FR-008（不產生任何檔案異動）、SC-005（連續 5 次零異動）
    與 US2 驗收情境 3（不重複列出）。**代價**：維護者合併之後，比對副本會留到下一次實際更新或維護者自行刪除；
    摘要的 `Next:` 一行會明說可以刪除。
  - 不替維護者決定入庫與否：寫入 `.gitignore` 等於修改 Spec Kit 的檔案（`.specify/.gitignore` 是官方產生的）
    或維護者的檔案，兩者都不該做。
- **Alternatives considered**:
  - 放在原檔旁邊（`plan-template.md.new`）：散落在 `.claude/skills/` 與 `.specify/` 各處，難以一次清理，
    也讓 Spec Kit 的目錄混進本工具的檔案。
  - 放在專案外的暫存目錄：不會弄髒專案，但路徑依機器而異、重開機就消失、無法帶到另一個平台，
    再次執行時也無從判斷「是否已合併」。
  - 在輸出中直接印出 diff：檔案大時輸出過長，且不留存，維護者無法之後再看。
  - 不加後綴、完整鏡射路徑：`.specify/sdd-update/.claude/skills/speckit-plan/SKILL.md` 可能被 Claude Code
    當成巢狀目錄的 skill 載入；副本的 `.gitignore` 會成為生效的規則。
  - 已是最新版時順手刪除「已合併」的比對副本：使用上較省事，但與 FR-008 的字面抵觸（那一次執行產生了檔案異動）。
    這是維護者核可時可以推翻的取捨，見 plan.md 的「需要維護者注意的取捨」。
  - 把新版雜湊另存一個狀態檔：比對副本本身就是完整的資訊，多一個檔案只多一個會不一致的地方。

## R2 新增的檔案、不再提供的檔案與導入紀錄的改寫

### 逐檔的判定

對「新版官方產出」與「紀錄內 `origin` 為 `speckit` 的項目」的聯集中每一個路徑判定一次。
`cur` 是專案檔案目前的雜湊，`rec` 是紀錄內的雜湊，`new` 是新版官方內容的雜湊（都先正規化換行）。

| # | 新版提供 | 專案內 | 紀錄內 | 條件 | 動作 | 回報 |
|---|---|---|---|---|---|---|
| 1 | 是 | 不存在 | 不論 | | `create`：建立 | `created` |
| 2 | 是 | 存在 | 不論 | `cur == new` | `same`：不寫入 | 不列出 |
| 3 | 是 | 存在 | 是 | `cur == rec` | `update`：以新版取代 | `updated` |
| 4 | 是 | 存在 | 是 | `cur != rec` | `keep`：不動，寫比對副本 | `kept … (modified; …)` |
| 5 | 是 | 存在 | 否 | | `keep`：不動，寫比對副本 | `kept … (not created by sdd-init; …)` |
| 6 | 否 | 存在 | 是 | `cur == rec` | `remove`：刪除 | `removed` |
| 7 | 否 | 存在 | 是 | `cur != rec` | `keep-orphan`：不動，沒有比對副本 | `kept … (modified; no longer part of Spec Kit <版本>)` |
| 8 | 否 | 不存在 | 是 | | `forget`：只從紀錄移除 | 不列出 |

例外：`.specify/memory/` 之下的路徑不進入這張表（R7）。

- **Decision（新增的檔案）**：第 1 列。新版有、專案沒有就建立，並列入紀錄。維護者先前刪掉的 Spec Kit 檔案也會被重新建立，
  與 003「缺少的檔案會被補齊」一致。
- **Decision（不再提供的檔案）**：第 6 至 8 列。內容未被修改的才刪除；被修改過的保留，並從紀錄移除，
  它從此是維護者的檔案（與 003 移除時「保留下來的檔案已是維護者的內容」相同）。因刪除而變空、且在 `created_dirs`
  內的目錄一併刪除（例如 `.claude/skills/speckit-taskstoissues/`）。不在紀錄內、新版也不提供的檔案完全不看、不碰。
- **Decision（不是由 sdd-init 導入）**：第 5 列。003 對「導入前就存在的 Spec Kit 檔案」的處理是略過且不列入紀錄，
  所以這種專案**有紀錄、但紀錄內沒有這些檔案**；本功能無法證明它們未被修改，一律保留並附比對副本。
  第 2 列讓其中已經與新版相同的檔案不被列出。完全沒有紀錄的專案屬於 R4 的「沒有導入紀錄」。
  **限制**：`/sdd-init` 在這種專案寫入的紀錄版本是它執行當下的最新穩定版（003 的行為），不是既有檔案實際的版本；
  所以緊接著執行 `/sdd-update` 會得到「已是最新穩定版」，要等官方發布下一個穩定版，這些檔案才會被比對並附上比對副本。
  本功能不以 `init-options.json` 的版本推翻紀錄來強制比對：那個檔案在這種專案裡是被保留的別人的檔案，版本永遠不會變，
  每次執行都會重做一次完整的更新，違反 FR-008。
- **Decision（紀錄的改寫，FR-009）**：更新完成後的紀錄：
  - `speckit_version` 改為新版本，`status` 為 `complete`。
  - 第 1、2（原本就在紀錄內者）、3、4 列的項目，`sha256` 一律改為 `new`。
    第 4 列因此仍是「被修改」（`cur != sha256`），直到維護者把它合併成與新版完全相同，之後的更新才會自動取代它。
  - 第 2 列中不在紀錄內的檔案、第 5 列的檔案都**不**列入紀錄：它們不是本工具建立的，
    列入就會讓 `/sdd-init remove` 在內容相符時刪掉別人的檔案。
  - 第 6、7、8 列的項目從紀錄移除。
  - 比對副本各一筆，`origin` 為 `sdd-update`，`sha256` 是副本內容的雜湊；上一次更新留下的比對副本項目全部移除。
  - 新建立的目錄加入 `created_dirs`。
- **Rationale**: `sha256` 的意義統一為「紀錄的版本在這個路徑提供的官方內容」，下一次更新與移除用同一條規則
  （`cur == sha256` 才是未修改）就能正確判斷，不需要新的欄位。已與新版相同的檔案不寫入、不列出，
  讓「維護者先自行合併」與「上次更新中途失敗後重跑」都自然收斂。
- **Alternatives considered**:
  - 被保留的檔案沿用舊的 `sha256`：維護者合併成新版後雜湊仍不符，會永遠被當成被修改。
  - 把第 5 列的檔案在與新版相同時納入紀錄（「收編」）：之後能自動更新，但移除時會刪掉不是本工具建立的檔案，違反原則 III。
  - 不再提供的檔案一律保留：專案會累積已失效的 skill（例如 `speckit-taskstoissues` 仍可被呼叫），違反 US1 驗收情境 3。
  - 維護者刪掉的檔案不重建：需要在紀錄內多記一種狀態；而 `/sdd-init` 本來就會把它補回來，兩個 skill 的行為會不一致。

## R3 更新後的 `.sh`：執行權限與換行

- **Decision**:
  - 內容：一律把官方產出的位元組原樣寫入（官方的 `.sh` 是 LF），不做任何轉換。
  - 取代既有的 `.sh`（`update`）：只寫入工作目錄，**不動 index**。寫入後把工作目錄的檔案模式設成與官方產出相同
    （Linux 上維持可執行；Windows 上沒有作用）。
  - 新建立的 `.sh`（`create`）：專案是 git repository 時執行 `git add --chmod=+x`，並把 `staged_executable` 設為 true，
    與 003 完全相同，直接呼叫同一個函式。
  - 紀錄內先前建立、`staged_executable` 為 false、還不在 index 也不在 `HEAD` 的 `.sh`（003 的「待補登」）一併補登，
    條件與 003 相同。
  - `.specify/.gitattributes`：不存在時以 003 的同一段程式建立（一行 `scripts/bash/*.sh text eol=lf`）；
    已存在就不動。之後對新版產出的每一支 `.sh` 以 `git check-attr eol` 檢查，結果不是 `lf` 的各輸出一行 `warning`。
  - 被刪除（`remove`）的 `.sh` 若 `staged_executable` 為 true、仍在 index 且不在 `HEAD`，以 `git rm --cached` 取消，
    與 003 移除時的規則相同。
- **Rationale**:
  - 實測：在 `core.fileMode=false`（Windows 的情況）的 repository，已以 100755 提交的 `.sh` 被取代內容後再 `git add`，
    index 內仍是 100755；新檔案以 `git add --chmod=+x` 加入後是 100755；新增的 `.py` 是 100644，與 Linux 相同。
    以 `core.autocrlf=true` clone 後 `.sh` 仍是 LF 且可執行，`create-new-feature.sh`、`setup-plan.sh`、`setup-tasks.sh`
    都以結束碼 0 完成。也就是說，既有的 `.sh` 靠 index 已記錄的模式與 `.gitattributes` 既有的規則就能維持，
    需要額外動作的只有新的 `.sh`。
  - 不改寫已在 index 的項目，是 003 已公開的保證；更新沿用它，暫存區的異動仍然只有「加入自己新建的 `.sh`」。
  - 逐檔檢查 `eol`：新版若把腳本放到 `.gitattributes` 既有規則涵蓋不到的位置，或該檔是別人的、缺少規則，
    維護者會在更新當下就知道，而不是到另一個平台才發現。
- **003 的已知限制**：已在 index 或 `HEAD`、但模式不可執行的 `.sh` 不會被修正。本功能不解決它，也不讓它惡化：
  更新不會把任何既有的 index 項目從 100755 改成 100644（實測如上），也不新增這種狀態（新的 `.sh` 一律以 `--chmod=+x` 加入）。
- **Alternatives considered**:
  - 把取代後的 `.sh` 也 `git add`：會把內容的變更一起放進暫存區，超出 003 對暫存區的保證，也讓維護者難以檢視差異。
  - 以 `git update-index --chmod=+x` 修正所有 `.sh`：會改寫既有的 index 項目，屬於 003 已知限制的範圍，維護者未要求。
  - 更新時改寫 `.specify/.gitattributes`：它可能已被維護者修改；需要的規則在 003 導入時就已存在。

## R4 邊界情況的行為、結束碼與輸出

結束碼沿用 [003 的 contracts/cli.md](../003-sdd-init/contracts/cli.md)，不新增也不改變數字的意義。
完整的輸出格式見 [contracts/cli.md](./contracts/cli.md)。

| 情況 | 行為 | 結束碼 | 專案內的異動 |
|---|---|---|---|
| 缺少 `uv`、`git` 或 `bash`（判定與 003 相同） | 列出缺少的工具後停止 | 3 | 無 |
| 沒有導入紀錄（包含完全沒有 `.specify/`，以及有 Spec Kit 檔案但沒有紀錄） | 停止，請維護者先執行 `/sdd-init`；不連線 | 1 | 無 |
| 紀錄無法解析、`schema` 不認得，或路徑違反規則 | 停止並說明，與 003 的 init 相同；不連線 | 1 | 無 |
| 紀錄為 `applying`，且紀錄的版本等於最新穩定版 | 這是被中斷的導入；停止，請維護者先執行 `/sdd-init` 完成它 | 1 | 無 |
| 無法取得最新穩定版，或官方工具執行失敗 | 停止並說明原因；不重試、不改用其他來源 | 4 | 無 |
| 專案的版本比最新穩定版還新 | 不降版，回報兩個版本 | 0 | 無 |
| 已是最新穩定版（紀錄為 `complete`） | 回報已是最新版，列出仍與新版不同的保留檔案（R1） | 0 | 無 |
| Spec Kit 不是由 sdd-init 導入（有紀錄，但檔案不在紀錄內） | 照常更新；這些檔案全部保留並附比對副本（R2 第 5 列） | 0 | 有 |
| 比對副本要寫入的路徑已有不在紀錄內的檔案，或某個上層路徑不是目錄 | 規劃階段就停止並指出路徑 | 1 | 無 |
| 更新中途失敗（寫入錯誤） | 回報失敗的步驟與原因，請維護者排除後再執行一次 | 1 | 可能已部分寫入 |

- **Decision（專案的版本）**：「專案的版本」取兩個來源中較新的一個：紀錄的 `speckit_version`，以及專案內
  `.specify/init-options.json` 的 `speckit_version`（官方工具寫入；讀不到就只看紀錄）。
  比較時只取版本字串開頭的數字段（`1.5.0rc1` 取 `1.5.0`）；數字段大於最新穩定版才算「比最新穩定版還新」。
- **Rationale**: 紀錄只會寫入穩定版，所以「曾手動安裝預覽版」只能從官方工具自己寫的 `init-options.json` 看出來；
  另一種會發生的情況是紀錄的版本後來被 PyPI 撤回（yank）。兩者都不該被降版。數字段相同而帶有預覽後綴的版本
  （例如 `1.4.3rc1` 對 `1.4.3`）視為較舊，照常更新到正式版。
- **Decision（中途失敗）**：寫入任何檔案之前，先把紀錄改寫為 `status: applying`、**版本仍是原版本**、
  `entries` 為「原有項目加上這次要新建的檔案與比對副本」；全部完成後才寫入新版本與 `complete`。
  每個被取代的檔案先寫到同目錄的暫存檔再以 `os.replace` 換上，不會留下寫到一半的檔案。
  再次執行時不需要特別的復原流程，直接重新判定：已取代的檔案是 `same`、還沒取代的仍是 `update`、
  已建立的檔案在紀錄內且是 `same`、被保留的檔案仍是 `keep`（比對副本是自己的，重寫）。
  被保留的檔案從頭到尾不會被寫入，所以不會遺失。
- **Rationale**: 版本在最後才改，確保「紀錄寫著新版本」就代表全部檔案已處理過；否則下一次執行會誤判為已是最新版，
  留下沒更新的檔案。失敗後若改為執行 `/sdd-init`，它會依紀錄的原版本補齊並標為 `complete`，
  下一次 `/sdd-update` 仍能從那個狀態正確更新。
- **已知的窄縫**：更新中途失敗後、再次執行之前，如果官方又發布了更新的版本，上一次已取代的檔案
  （內容是中間那一版）會被判定為「被修改」而保留。結果仍然安全（不覆蓋、不遺失），只是多出需要人工比對的檔案。
- **Alternatives considered**:
  - 沒有紀錄時把全部既有檔案當成被修改、照常更新：spec 的邊界情況明寫要停止並請維護者先執行 `/sdd-init`；
    而且沒有紀錄就沒有地方記錄本工具建立的檔案。
  - 沒有紀錄時以結束碼 0 結束（比照 003 的 remove）：FR-011 要求「停止並說明原因與處理方式」，
    SKILL.md 以非零結束碼作為停止的依據；1 在 003 的定義是「執行失敗」，涵蓋前置條件不成立。
  - 為更新新增一個 `status` 值或 `updating_to` 欄位：重新判定已經能從任何中斷點收斂，多一個欄位只多一種要處理的狀態。
  - 以 `packaging` 套件比較版本：腳本就得宣告第三方相依；這裡只需要判斷「是否比某個穩定版新」。

## R5 自動測試的範圍

- **Decision**: 沿用 003 的三層，全部由 pytest 執行，CI 兩個平台都要通過。

  | 層 | 位置 | 官方工具 | 網路 | 驗證什麼 |
  |---|---|---|---|---|
  | 單元 | `tests/unit/test_sdd_update.py` | 否：以兩個假版本的假產出取代「查詢版本」與「執行官方工具」 | 否 | R2 的 8 列判定、比對副本的寫入與清理、已是最新版時零寫入與不重複列出、紀錄的改寫、`.specify/memory/` 與 `specs/` 不變、`.sh` 的暫存區處理、R4 每一種情況的結束碼與輸出、中途失敗後重跑、CRLF 的專案檔案不被誤判、輸出逐字固定 |
  | 單元 | `tests/unit/test_sdd_update_skill.py` | 否 | 否 | skill 資料夾的結構（[contracts/skill.md](./contracts/skill.md)），包含能從相鄰的 `sdd-init` 載入共用程式 |
  | 單元 | 既有的 `tests/unit/test_sdd_init.py` 增補 | 否 | 否 | 003 的程式為共用而做的變更（R6）：接受 `origin: sdd-update`、比對副本被刪除時仍是「已完整導入」、remove 會刪除未修改的比對副本 |
  | 整合 | `tests/integration/test_sdd_update_real.py`（標記 `network`） | 是：以固定的舊版 1.2.6 導入，再實際查詢 PyPI 並更新到當下最新穩定版 | 是 | 版本變成最新穩定版；更新後的檔案集合等於直接以最新版導入的檔案集合（涵蓋新增與移除）；紀錄內每個檔案的雜湊相符；改過的範本、constitution 與 `specs/` 內容不變且範本附有比對副本；以 bash 執行 Spec Kit 腳本成功；再執行 5 次零異動（SC-005） |
  | 跨平台 | 既有的兩個 CI job 加 `tests/e2e/test_cross_platform_update.py` | 是 | 是 | 一個平台更新並 commit 的 repository，在另一個平台 clone 後不做任何額外步驟就能執行 Spec Kit 腳本（兩個方向，SC-006）；兩個平台更新後的檔案清單（含模式）與 sdd-update 的輸出相同（US3 驗收情境 2） |

  - 以舊版導入的方法：測試在行程內呼叫 `sdd_init.main(["init"], resolve_version=lambda: "1.2.6")`，
    只替換「查詢版本」這一步，官方工具仍實際執行。這是 003 已有的測試入口，不新增環境變數或隱藏選項。
  - **CI 的 cross-platform job 要擴充，但不新增 job**：`cross-platform-produce` 與 `cross-platform` 兩個 job 的指令
    多執行一個測試檔，bundle 與檔案清單放進同一個 artifact。必要的檢查仍是 `test`、`cross-platform-produce`、
    `cross-platform` 三個，各兩個平台。
  - 跨平台的 produce 步驟：以 1.2.6 導入並 commit；刪除一支 `.sh` 並 commit；修改一份範本並 commit；執行 sdd-update；
    `git add -A` 後 commit；打包。刪掉一支 `.sh` 是為了讓更新在真正的 Windows 上走一次「新建 `.sh` 並以
    `git add --chmod=+x` 加入」（實測的幾組版本之間沒有新增 `.sh`）；1.2.6 到最新版之間 `common.sh` 與
    `create-new-feature.sh` 內容有變，涵蓋「取代既有的 `.sh` 後模式仍是 100755」。
- **Rationale**:
  - 判定都在 Python 內，以假產出就能離線、快速、決定性地測完每一列與每一種邊界情況。
  - R2 與 R3 的結論建立在官方工具的實際產出與 git 在 Windows 上的行為，只有實際執行兩個版本、
    並讓兩個 runner 交換 repository 才驗得到。
  - 固定以 1.2.6 為起點：實測它到 1.4.3 之間同時有新增、移除與內容改變的檔案。斷言只比對性質
    （與直接導入最新版的結果相同），不比對固定的檔案清單，所以官方發新版不會讓測試失敗。
    1.2.6 若被 PyPI 撤回，測試會失敗，屆時換一個起點版本；這是測試該被注意到的訊號，不自動跳過。
- **Alternatives considered**:
  - 以「次新的穩定版」為起點（動態決定）：永遠存在，但相鄰版本之間可能沒有移除的檔案，涵蓋不到 R2 第 6 列。
  - 只做單元測試：驗不到官方產出的實際差異，也驗不到 Windows 上的模式與換行。
  - 為更新新增第四個 CI job：多一組必要檢查要維護，而兩個既有 job 的步驟完全相同。

## R6 與 sdd-init 共用程式碼

- **Decision**: `sdd_init.py` 是共用程式的唯一來源；`home/skills/sdd-update/scripts/sdd_update.py` 在執行時
  以 `importlib` 從相鄰的 skill 資料夾載入它：`<本檔所在的 skill 資料夾>/../sdd-init/scripts/sdd_init.py`。
  共用的部分：結束碼常數、必要工具與 Git Bash 的判定、專案根目錄與 git 查詢、`content_hash`、紀錄的讀寫與路徑規則、
  取得最新穩定版、執行官方工具與核對版本、`.sh` 的補登與 `git add --chmod=+x`、`.specify/.gitattributes` 的建立。
  找不到 `sdd_init.py` 時以結束碼 1 停止，說明 sdd-update 需要與 sdd-init 一起部署。

  為了共用，`sdd_init.py`（003 的產出）需要以下變更，行為對 003 既有的情境不變：

  1. 紀錄的 `entries[].origin` 多接受一個值 `sdd-update`；這種項目的路徑 MUST 位於 `.specify/sdd-update/` 之下且以 `.new` 結尾。
     `schema` 維持 1。
  2. init 判斷「已完整導入」時不要求 `origin` 為 `sdd-update` 的檔案存在（維護者可以隨時刪除比對副本）。
  3. 把 init 內「建立 `.specify/.gitattributes`」與少數寫死 `/sdd-init` 的訊息整理成可由 sdd-update 呼叫的函式，輸出逐字不變。

  remove 不需要改：比對副本是紀錄內的一般項目，內容未變就刪除。
- **Rationale**:
  - 兩個 skill 的資料夾各自被原樣部署，但部署工具一次安裝整個 `home/`，兩者在 repo（`home/skills/`）與安裝後
    （`~/.claude/skills/`）都是相鄰的資料夾，相對路徑在兩處都成立。
  - sdd-update 在功能上本來就依賴 sdd-init：它更新的是 sdd-init 的紀錄，沒有紀錄時請維護者執行的也是 `/sdd-init`。
  - 紀錄格式、雜湊規則與版本挑選只有一份實作，兩個 skill 不可能對同一份紀錄有不同的解讀；003 的測試繼續保護它。
  - `schema` 不升版：舊版的 sdd-init 讀到 `origin: sdd-update` 會以「unknown origin」判定紀錄無法使用並停止，
    與讀到不認得的 `schema` 的結果完全相同（init 結束碼 1、remove 不刪除任何檔案），所以升版得不到更多保護，
    卻會改變每一次新導入產生的紀錄。
- **Alternatives considered**:
  - 在兩個 skill 資料夾各放一份共用模組，以測試確保位元組相同：沒有執行期的相依，但同一段程式有兩份，
    而且 003 的 skill 結構契約是「資料夾內只有三個檔案」。
  - 把更新做成 `sdd_init.py update`，sdd-update 只有 SKILL.md 與 README：程式集中，但 sdd-update 的資料夾沒有自己的腳本，
    003 的指令介面也要改（它寫明只有 `init` 與 `remove`），單一檔案會超過一千行。
  - 在 `home/` 下另設共用目錄：部署工具把 `home/skills/` 下的每個資料夾都當成 skill，放不進去；放在別處又要改 001 的部署範圍。
  - 比對副本以 `origin: speckit` 記錄（內容確實來自官方工具），完全不改格式：sdd-init 會把它當成 Spec Kit 的檔案
    （缺少時重新執行官方工具、副本是 `.sh` 時補登執行權限），也與原則 I「分得清楚」的要求不符。

## R7 constitution 與 `specs/` 永遠不動

- **Decision**: `.specify/memory/` 之下的路徑完全排除在更新之外：不建立、不取代、不刪除、不寫比對副本、不輸出任何一行，
  紀錄內原有的項目原樣保留。`specs/` 與其他專案內容本來就不在處理範圍：sdd-update 寫入的路徑只有
  新版官方產出的路徑（沿用 003 的檢查，MUST 位於 `.specify/` 或 `.claude/skills/speckit-*/` 之下）、
  `.specify/sdd-update/` 與紀錄本身。官方產出若含有 `.specify/sdd-update/` 之下的路徑或紀錄的路徑，視為官方工具執行失敗（結束碼 4）。
- **Rationale**: FR-006 與 SC-002 要求 constitution 被更動的數量為 0，不分它是否仍是空白範本。
  官方工具自己的 `init --force` 也保留既有的 `constitution.md`（實測）。同目錄的 `.constitution-template.json`
  是官方用來記錄 constitution 來源範本的資訊，與 constitution 成對，一起不動才一致。
  不為它寫比對副本：對已寫好的 constitution 附上一份空白範本只是雜訊。
- **Alternatives considered**: 只在 constitution 被修改過時保留（一般規則）：仍是空白範本時會被新版範本取代，
  與「永遠不動」的字面不符；實測四個版本的這個檔案完全相同，排除它沒有實際損失。

## R8 skill 的形式與必要工具

- **Decision**: `home/skills/sdd-update/` 內含 `SKILL.md`（英文）、`README.md`（繁體中文）與 `scripts/sdd_update.py`。
  SKILL.md 與 003 一樣薄：`disable-model-invocation: true`，沒有參數，指示 Claude 在專案目錄執行一次
  `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_update.py"`、完整回報輸出、非零結束碼時停止。
  SKILL.md 另外寫明 Claude MUST NOT 自行合併被保留的檔案、MUST NOT 修改或刪除比對副本，除非維護者之後明確要求。
  必要工具與判定方式與 003 完全相同（`uv`、`git`、`bash`，Windows 只承認 Git Bash），呼叫同一個函式。
- **Rationale**: 與 003 的 R8、R9 相同。sdd-update 自己不執行 bash，但檢查它才能保證更新後的專案在這台機器上可用，
  也讓兩個 skill 對「缺少工具」有完全相同的輸出。合併被保留的檔案是維護者的決定（spec 的 US2：「以便自行合併」）。

## R9 回報的內容

- **Decision**: 逐行格式沿用 003（動作名稱補到 10 個字元後接路徑），依序輸出 `updated`、`created`、`removed`、`kept`、
  `staged`、`warning`，各段內依路徑排序；之後是摘要：版本變化與四個數字一行、`Git:` 一行，
  有比對副本時再加一行固定文字的 `Next:`。完整格式見 [contracts/cli.md](./contracts/cli.md)。
  `same` 的檔案不列出也不計數。
- **Rationale**: FR-003 要求的五項（版本變化、更新、新建、移除、保留）各有固定的位置，測試可以逐行逐字比對，
  兩個平台的輸出相同（FR-012）。

## 實測紀錄

以下的 `S<版本>` 代表 `uv tool run --from specify-cli==<版本> specify`，執行時設定 `PYTHONUTF8=1`。
`INIT` 代表 `init --here --non-interactive --ignore-agent-tools --integration claude --script sh`。

| # | 指令 | 觀察 |
|---|---|---|
| 1 | `curl https://pypi.org/pypi/specify-cli/json`，列出 `releases` | 最新穩定版是 1.4.3（2026-11-19 上傳）；最近的版本依序為 1.2.6、1.3.0 至 1.3.3、1.4.0 至 1.4.3；沒有預覽版，沒有被 yank 的檔案 |
| 2 | 在四個空目錄分別執行 `S1.2.6 INIT`、`S1.3.3 INIT`、`S1.4.2 INIT`、`S1.4.3 INIT` | 結束碼都是 0；檔案數依序為 30、29、29、30 |
| 3 | 兩兩 `diff` 檔案清單並 `diff -rq` 內容（1.4.2↔1.4.3、1.3.3↔1.4.3、1.2.6↔1.4.3） | 如本文開頭的表：1.4.3 新增 `markdown_sections.py`；1.2.6 之後不再提供 `speckit-taskstoissues/SKILL.md`；每一版的 9 個 SKILL.md、`common.sh`、設定檔與 manifest 都不同 |
| 4 | `diff` 1.4.2 與 1.4.3 的 `speckit-plan/SKILL.md`、`init-options.json`、`integration.json`、`workflow-registry.json` | SKILL.md 的 frontmatter 內 `version` 不同；`init-options.json` 只差 `speckit_version`；`integration.json` 只差 `version`；registry 只差時間戳 |
| 5 | `sha256sum` 四個版本的 `.specify/memory/constitution.md` 與 `templates/plan-template.md` | 四個版本各自完全相同 |
| 6 | `find out-1.4.3 -type f -perm -u+x` | 只有 `scripts/bash/` 下的 6 支 `.sh`；`markdown_sections.py` 與其他檔案都不可執行 |
| 7 | 讀取 1.4.3 的 `.specify/.gitignore` 與 `integrations/claude.manifest.json` | `.gitignore` 只忽略 `feature.json` 等機器專屬狀態，沒有規則會涵蓋 `.specify/sdd-update/`；manifest 內有版本、時間戳與各檔案的雜湊 |
| 8 | `S1.4.3 --help`、`S1.4.3 integration --help`、`S1.4.3 integration upgrade --help` | 沒有更新整個專案的指令；`integration upgrade` 是「diff-aware」的重新安裝，`--force` 才覆蓋被修改的檔案 |
| 9 | 複製 1.4.2 的產出，改寫 `constitution.md`，在 `plan-template.md`、`speckit-plan/SKILL.md`、`common.sh` 末尾各加一行，新增 `specs/001-x/spec.md`，再執行 `S1.4.3 init --here --force --non-interactive --ignore-agent-tools --integration claude --script sh` | 結束碼 0；`constitution.md` 與 `specs/` 保留；範本、SKILL.md、`common.sh` 的修改全部被覆蓋；`speckit_version` 變成 1.4.3 |
| 10 | 複製 1.4.2 的產出，在 `speckit-plan/SKILL.md` 與 `plan-template.md` 末尾各加一行，執行 `S1.4.3 integration upgrade claude` | 結束碼 1：`1 file(s) have been modified since installation … Use --force to overwrite modified files, or resolve manually.`；沒有任何檔案被更新，`speckit_version` 仍是 1.4.2，也沒有新增 `markdown_sections.py` |
| 11 | 以 1.2.6 的產出建立 repository：`git config core.fileMode false`、`chmod -x` 全部 `.sh`、加入 `.specify/.gitattributes`、`git add --chmod=+x` 後 commit；`git rm` 一支 `.sh` 並 commit；以 1.4.3 的內容逐檔覆寫（不帶執行權限）、刪除 `speckit-taskstoissues/`；對重新出現的那支 `.sh` 執行 `git add --chmod=+x`；`git add -A` 後 commit | `git status` 顯示既有檔案為已修改、移除的 skill 為已刪除、那支 `.sh` 為已加入、`markdown_sections.py` 為未追蹤；commit 後 `git ls-files -s`：6 支 `.sh` 都是 100755（包含內容被取代的 `common.sh`、`create-new-feature.sh` 與新加入的那一支），`markdown_sections.py` 是 100644 |
| 12 | `git clone -c core.autocrlf=true -c core.eol=crlf` 第 11 項的 repository，執行 `create-new-feature.sh --json --short-name demo "Demo feature"`、`setup-plan.sh --json`、`setup-tasks.sh --json` | `.sh` 都是 LF 且可執行，範本是 CRLF；三支腳本都是結束碼 0，產生 `specs/001-demo/` 與 `plan.md` |
