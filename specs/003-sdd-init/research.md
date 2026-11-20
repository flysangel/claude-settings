# Research: sdd-init 導入 Spec Kit

R1 至 R4 是 spec 留給 plan 的四個決定，R5 之後是設計時衍生的決定。
「實測」指 2026-11-20 在 Linux 以 `uv tool run --from specify-cli==1.4.3 specify …` 於暫存目錄執行的結果，
指令與觀察列在文末的「實測紀錄」。Windows 上的行為無法在這台機器實測，由 R4 的 CI 測試驗證。

## R1 同一專案同時支援 Windows 與 Linux

### 官方工具的行為（實測）

- `specify init --script` 一次只接受一種：`sh`、`ps` 或 `py`；未指定時 Windows 預設 `ps`，其他平台預設 `sh`。
- 產生的 `speckit-*` SKILL.md 把該種腳本的路徑與參數寫死：

  | `--script` | 安裝的目錄 | SKILL.md 內的指令 |
  |---|---|---|
  | `sh` | `.specify/scripts/bash/` | `.specify/scripts/bash/setup-plan.sh --json` |
  | `ps` | `.specify/scripts/powershell/` | `.specify/scripts/powershell/setup-plan.ps1 -Json` |
  | `py` | `.specify/scripts/python/`，外加依**執行平台**決定的 `bash/` 或 `powershell/` | `python3 .specify/scripts/python/setup_plan.py --json` |

- `py` 的直譯器名稱是 init 當下在該主機解析的結果：依序為專案的 `.venv`、`PATH` 上的 `python3`、`python`，
  都沒有時寫入執行 CLI 的直譯器絕對路徑（`specify_cli/integrations/base.py` 的 `resolve_python_interpreter`）。
- 官方工具不產生 `.gitattributes`，也不執行 git 指令；`sh` 腳本的執行權限只以 `chmod` 設在工作目錄。
- `sh` 與 `ps` 兩種導入的檔案集合只差腳本目錄；相同參數導入兩次，檔案內容只差三個檔案內的時間戳。

### 決定

- **Decision**: 兩個平台一律以 `--integration claude --script sh` 導入。Windows 由 Git for Windows 提供的 Git Bash
  執行這些腳本（Claude Code 在裝有 Git for Windows 時，Bash tool 就使用 Git Bash）。為了讓 `sh` 腳本經過 git
  到另一個平台後仍可直接執行，sdd-init 另外做兩件事，都不更動 Spec Kit 產生的檔案內容：

  1. 新增自己的檔案 `.specify/.gitattributes`，內容只有一行 `scripts/bash/*.sh text eol=lf`。
  2. 專案是 git repository 時，對自己建立的 `.sh` 執行 `git add --chmod=+x`，把執行權限記進 index。
     **sdd-init 因此會動到暫存區**：只加入這幾個 `.sh`，不 commit，並在回報中逐一列出。
     不是 repository 時不做，並在回報中說明。

- **Rationale**:
  - `sh` 是唯一一種產出內容不依導入平台而變的選項，兩個平台導入後的檔案集合相同（US2 情境 3）。
  - 實測缺口一（換行）：以 `core.autocrlf=true` clone 後 `.sh` 變成 CRLF，執行得到
    `/usr/bin/env: 'bash\r': No such file or directory`（結束碼 127）。Git for Windows 的預設就是這個設定。
    加上述 `.gitattributes` 規則後，同樣的 clone 中 `.sh` 維持 LF，腳本正常執行。
  - 實測缺口二（執行權限）：SKILL.md 直接以路徑執行腳本；mode 為 100644 時得到 `Permission denied`（結束碼 126）。
    Windows 的檔案系統無法記錄執行權限，git 在 Windows 新增檔案時一律記為 100644，
    只有 `git add --chmod=+x` 能在 Windows 寫入 100755。在 `core.fileMode=false` 的 repository 實測，
    index 內這些檔案成為 100755，clone 後可直接執行。兩個平台都做同一件事，行為才對等（FR-012）。
  - Git Bash 隨 git 安裝，而 `git` 已是 001 部署工具的必要指令，所以 Windows 不需要額外安裝任何東西。
  - 維護者已確認這個方向（Windows 以 Git Bash 執行、`.specify/` 內可放 sdd-init 自己的檔案、可動暫存區）。

- **Alternatives considered**:
  - `--script py`：SKILL.md 內的直譯器名稱取決於導入的主機（Linux 是 `python3`，Windows 常見的是 `python`，
    兩者都沒有時是絕對路徑），額外安裝的 shell 目錄也依平台不同，兩個平台導入的結果不一樣；
    還要求兩個平台都有 uv 以外的系統 Python。
  - 各平台用預設值（Windows `ps`、Linux `sh`）：SKILL.md 只引用導入時那一種，另一個平台必須重新導入，直接違反 FR-006。
  - 導入兩次，同時安裝 `bash/` 與 `powershell/`：SKILL.md 仍只引用其中一種，多出來的目錄用不到。
  - 兩個平台都用 `ps`：Linux 需要另外安裝 PowerShell。
  - 修改 SKILL.md 讓它依平台選腳本：違反原則 I。
  - 把換行規則寫進專案根目錄的 `.gitattributes`：那是維護者的檔案，已存在時依原則 III 不能修改。
  - 不動暫存區，改請維護者自己執行 `git add --chmod=+x`：Windows 導入、Linux 使用時多一個手動步驟，與 FR-006、SC-001 不符。
  - 由 sdd-init 直接 commit：超出導入的職責，維護者已否決。

### `.specify/.gitattributes` 已存在時

依原則 III 不覆蓋、不修改，列為 `skipped`，也不納入導入紀錄。接著以 `git check-attr eol` 檢查 `.sh` 的有效設定：
不是 `lf` 時在回報中加一行警告，寫明要維護者自行加入的那一行規則；導入本身照常完成。不是 git repository 時無法檢查，
同樣以警告說明。

## R2 導入紀錄的格式與位置

- **Decision**: `.specify/sdd-init.json`，JSON，欄位見 [data-model.md](./data-model.md)。重點：
  - 記錄導入的 Spec Kit 版本、傳給官方工具的選項、每個由 sdd-init 建立的檔案（相對路徑、內容雜湊、來源、
    是否由 sdd-init 加入暫存區），以及 sdd-init 建立的目錄。
  - 內容雜湊是「把 CRLF 換成 LF 之後」的 SHA-256。
  - 有 `status` 欄位（`applying`、`complete`），寫入檔案前先落下 `applying` 的紀錄。
  - 不含絕對路徑、時間戳、使用者名稱。
- **Rationale**:
  - 放在 `.specify/` 內，紀錄跟著 Spec Kit 的檔案一起提交、一起到另一個平台；004 sdd-update 與移除都從固定位置讀取。
    官方工具不產生這個檔名（實測的檔案清單中沒有），不會互相覆蓋。
  - 雜湊先正規化換行：專案經 git 到 Windows 後，範本與 SKILL.md 可能被轉成 CRLF（換行規則只涵蓋 `.sh`，
    其他檔案的換行政策屬於專案自己）。不正規化的話，這些檔案在 Windows 會全部被判定為「被修改過」，
    移除與 004 的更新都會失效，違反 FR-012。
  - 逐檔記錄來源（官方工具或 sdd-init 自己）讓 004 知道哪些檔案要跟官方新版比對、哪些是 sdd-init 自己維護的。
  - 先落下 `applying` 的紀錄，中途失敗後再次執行時能分辨「已寫入的是自己的」，補齊其餘檔案（spec 的邊界情況）。
  - 不含時間戳與機器資訊，符合原則 V，兩個平台對同一版本產生的紀錄只差官方檔案內的時間戳所造成的雜湊。
- **Alternatives considered**:
  - 沿用官方的 `.specify/integrations/*.manifest.json`：它由官方工具改寫，內容與格式不受本專案控制；
    不涵蓋 `.claude/skills/` 以外的全部檔案歸屬判斷，雜湊也不處理換行。
  - 放在專案根目錄的獨立資料夾：多一個頂層目錄；維護者已確認可放在 `.specify/` 內。
  - 以 git 歷史判斷檔案是否被修改：專案可能不是 repository，也可能尚未 commit。
  - 未正規化的位元組雜湊（001 的做法）：001 的來源與目標都由本專案的 `.gitattributes` 控制，這裡的目標專案不是。

## R3 取得當下最新的穩定版

- **Decision**: 兩步。
  1. 以 Python 標準函式庫讀取 `https://pypi.org/pypi/specify-cli/json`，從 `releases` 選出最大的穩定版：
     版本字串必須符合 `N(.N)*`（沒有 `a`、`b`、`rc`、`dev`、`post` 等後綴），且該版本至少有一個未被 yank 的檔案。
  2. 以該版本執行官方工具，不安裝到使用者環境：
     `uv tool run --from specify-cli==<版本> specify init --here --non-interactive --ignore-agent-tools --integration claude --script sh`。
     完成後核對產出的 `.specify/init-options.json` 的 `speckit_version` 等於該版本，不符就視為失敗。

  任何一步失敗（無法連線、沒有符合的版本、uv 無法取得套件、官方工具以非零結束）都以結束碼 4 停止，
  不建立任何檔案，不重試，不改用其他來源（FR-010）。
- **Rationale**:
  - 官方文件（v1.4.3 的 `docs/installation.md`）寫明 PyPI 的 `specify-cli` 與 GitHub repository 是兩個官方發行管道，
    README 的安裝指令就是 `uv tool install specify-cli`。
  - 先解析出明確的版本再釘住執行：回報的版本就是實際執行的版本；「排除預覽版」是本專案自己的、可單元測試的邏輯，
    不依賴解析器的預設行為。
  - 實測 `uv tool run --from specify-cli@latest` 在離線且有快取時會成功並使用快取的舊版，
    無法保證是「當下」最新；直接查詢 PyPI 則離線時一定失敗，行為明確。
  - `uv tool run` 不更動使用者已安裝的 `specify`（這台機器上既有的是 1.2.6，與最新版不同），也不要求事先安裝。
    `uvx` 不一定存在（這台機器就沒有），所以用 `uv tool run`。
  - `specify init` 本身不需要網路（它的說明寫明範本內建在套件裡），所以需要網路的只有查詢版本與 uv 下載套件。
  - `--ignore-agent-tools`：略過「`claude` 指令是否存在」的檢查，導入不該因此失敗。
- **Alternatives considered**:
  - `uv tool run --prerelease disallow --from specify-cli@latest`：如上，離線時會悄悄用舊版，且版本事後才知道。
  - GitHub API 的 `releases/latest` 加 `git+https://…@vX.Y.Z`：要從原始碼建置，較慢；未驗證身分的 API 有次數限制。
  - 使用機器上已安裝的 `specify`：版本不可控。`specify self upgrade` 會更動使用者的安裝。
  - 取 PyPI 回應的 `info.version`：通常就是最新穩定版，但規則不在本專案手上，無法測試。

## R4 自動測試的範圍

- **Decision**: 三層，全部由 pytest 執行，CI 兩個平台都要通過。

  | 層 | 位置 | 是否執行官方工具 | 需要網路 | 驗證什麼 |
  |---|---|---|---|---|
  | 單元 | `tests/unit/test_sdd_init.py` | 否。以測試用的假產出取代「執行官方工具」這一步 | 否 | 版本挑選、建立與略過、不覆蓋、紀錄內容、冪等、中途失敗後補齊、失敗時零寫入、移除的各種情況、換行正規化、暫存區的加入與取消、輸出格式 |
  | 單元 | `tests/unit/test_sdd_init_skill.py` | 否 | 否 | skill 資料夾的結構：SKILL.md 的 frontmatter、以英文撰寫、README 為繁體中文、腳本有 inline metadata |
  | 整合 | `tests/integration/test_sdd_init_real.py`（標記 `network`） | 是，實際查詢 PyPI 並執行官方工具 | 是 | 導入的版本等於 PyPI 當下最新穩定版、檔案齊全且是 `sh`、以 bash 實際執行 Spec Kit 腳本成功、導入後立即移除回到原狀（SC-004）、再次執行零異動 |
  | 跨平台 | CI 的第二個 job 加 `tests/e2e/test_cross_platform.py` | 是 | 是 | 一個平台導入並 commit 的 repository，在另一個平台 clone 後不做任何額外步驟就能執行 Spec Kit 腳本（兩個方向）；兩個平台導入的檔案集合相同 |

  - 跨平台 job 的做法：矩陣的每個平台先導入一個新的 repository、commit、以 `git bundle` 打包並連同檔案清單上傳為
    artifact；接著每個平台下載**另一個平台**的 artifact，clone 後執行 `create-new-feature.sh` 與 `setup-plan.sh`，
    並比對兩份檔案清單。Windows 這一側明確設定 `core.autocrlf=true`，重現 R1 的兩個缺口。
  - CI 需要網路（GitHub 的 runner 具備）。網路測試失敗就是失敗，不自動跳過；
    本機離線時可用 `-m "not network"` 只跑單元測試。
  - 「Spec Kit 流程」在自動測試中指 `speckit-*` skill 所呼叫的腳本能執行並產出預期的檔案；
    Claude 依 SKILL.md 走完整個對話流程屬於對話行為，以 quickstart 的人工情境驗收（與 002 的做法相同）。
- **Rationale**:
  - 判斷邏輯都在一支 Python 程式裡，用假產出就能快速、離線、決定性地測完所有分支。
  - R1 與 R3 的結論建立在官方工具的實際行為上，官方改版時要能被發現，所以必須有實際執行官方工具的測試。
  - 這台機器只能實測 Linux；R1 的兩個缺口都只在真正跨平台時出現，只有兩個 runner 互相交換 repository 才驗得到（SC-003）。
  - 最新版會隨時間改變，所以整合測試不比對固定的檔案清單，只比對性質（版本、腳本種類、必要檔案、兩個平台相同）。
- **Alternatives considered**:
  - 只做單元測試：驗不到官方工具的行為與跨平台的缺口。
  - 在 repo 內保存一份官方產出的快照來比對：官方每次發版都會讓測試失敗，而那並不是本專案的錯誤。
  - 在同一個 runner 上以設定模擬另一個平台：這正是本機已做過的實測，無法取代真正的 Windows。

## R5 不覆蓋既有檔案的做法

- **Decision**: 不在專案目錄內執行官方工具。先在專案之外的暫存空目錄執行 `specify init`，
  再把產出逐檔以位元組原樣複製到專案：目標不存在才建立，已存在一律略過並列出。完成後刪除暫存目錄。
- **Rationale**: 實測官方工具在非空目錄且 `--non-interactive` 時直接以結束碼 1 拒絕；加上 `--force` 則會覆蓋既有檔案
  （測試中預先放入的範本與 SKILL.md 都被換成官方內容），兩者都不符合 FR-004。
  暫存目錄的做法同時滿足 FR-010：取得版本或執行官方工具失敗時，專案內還沒有任何寫入。
  檔案仍由官方工具產生，sdd-init 只是原樣複製，符合 FR-003。實測相同參數在不同目錄的產出只差時間戳，與專案路徑無關。
- **Alternatives considered**: 在專案內執行 `--force` 後再還原被覆蓋的檔案（中途失敗就會遺失內容）；
  用 `specify integration install` 補裝（同樣不保證不覆蓋，且不涵蓋共用的範本與腳本）。

## R6 重複執行與中途失敗

- **Decision**:

  | 情況 | 行為 |
  |---|---|
  | 紀錄為 `complete`，且紀錄內的檔案都存在 | 回報已導入的版本，不連線、不寫入、不動暫存區 |
  | 紀錄為 `applying`，或紀錄內有檔案不存在 | 以**紀錄內的版本**重新產生暫存產出，只補上缺少的檔案 |
  | 沒有紀錄 | 取最新穩定版；既有的同名檔案一律視為別人的，略過並列出 |
  | 沒有紀錄，且官方產出的檔案全部已存在 | 全部列為略過；只建立 sdd-init 自己的檔案（若缺少） |
  | 紀錄無法解析，或 `schema` 不認得 | 以結束碼 1 停止並說明，不寫入任何檔案 |

- **Rationale**: 已導入時不連線才能做到零異動（FR-011），也不會因為官方發了新版就把新舊版本的檔案混在一起；
  版本的更新屬於 004。無法辨識的紀錄不能證明檔案歸屬，覆寫它會毀掉另一個工具或未來版本留下的資訊。
- **Alternatives considered**: 補齊時改用最新版（同一個專案內會混用兩個版本的檔案）。

## R7 移除

- **Decision**: `/sdd-init remove` 只依紀錄行事：
  - 紀錄內的檔案，目前內容的雜湊（正規化換行後）等於紀錄 → 刪除；不等於 → 保留並列出；已不存在 → 略過。
  - 被刪除的檔案若是由 sdd-init 加入暫存區、仍在 index 且不在 `HEAD` 內，就以 `git rm --cached` 取消，
    使導入後立即移除時 index 也回到原狀（SC-004）。已 commit 過的檔案不動 index，刪除會顯示為未暫存的變更。
  - 刪除因此變空、且由 sdd-init 建立的目錄；最後刪除紀錄本身。
  - 紀錄內的路徑必須位於 `.specify/` 或 `.claude/skills/speckit-*/` 之下，否則拒絕執行（結束碼 1），
    確保 `specs/` 與專案其他內容不會被刪（FR-009）。
  - 沒有紀錄或紀錄無法解析：不刪除任何檔案，說明原因，結束碼 0。
- **Rationale**: 雜湊比對直接對應 FR-008；維護者寫好的 constitution 是被修改過的檔案，自然被保留。
  之後由 Spec Kit 流程產生、不在紀錄內的檔案（例如 `.specify/feature.json`）不屬於 sdd-init，留在原處。
  移除後保留下來的檔案已是維護者的內容，所以紀錄不再保留。
- **Alternatives considered**: 呼叫官方的 `specify integration uninstall`（只處理 integration 的檔案，不含共用的範本與腳本，
  判定也不經過本專案的紀錄）；刪除整個 `.specify/`（會刪掉維護者的 constitution）。

## R8 skill 的形式

- **Decision**: `home/skills/sdd-init/` 內含 `SKILL.md`（英文）、`README.md`（繁體中文）與 `scripts/sdd_init.py`。
  SKILL.md 很薄：frontmatter 設 `disable-model-invocation: true`，內文指示 Claude 在專案目錄執行
  `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_init.py" init`（參數為 `remove` 時執行移除），
  把腳本的輸出整理後回報，並在非零結束碼時停止、不重試、不改用其他安裝方式。
  所有判斷都在 Python 腳本內，腳本開頭以 inline metadata 宣告 `requires-python = ">=3.11"`、沒有第三方相依。
- **Rationale**: 維護者指定產出只有 skill 文件或 script、Python 一律用 uv 執行。邏輯集中在一支程式，
  兩個平台的行為與回報內容才會相同（FR-012），也才能被自動測試。`disable-model-invocation` 對應
  「由維護者手動執行，不由 Claude 自行觸發」。`${CLAUDE_SKILL_DIR}` 是 Claude Code 提供的 skill 目錄替換變數，
  不必寫死安裝路徑。
- **Alternatives considered**: 把步驟全部寫在 SKILL.md 讓 Claude 逐步執行（每次執行的結果不保證相同，也無法自動測試）。

## R9 必要工具

- **Decision**: 必要工具是 `uv`、`git` 與 `bash`，兩個平台相同。腳本一開始檢查，一次列出全部缺少的工具，
  以結束碼 3 停止（與 001 的結束碼一致）。Windows 上的 `bash` 由 Git for Windows 提供。
  `uv` 不存在時腳本根本無法啟動，這種情況由 SKILL.md 指示 Claude 回報並停止。不檢查 `jq` 與系統 Python。
- **Rationale**: `uv` 用來執行官方工具；`bash` 是 `sh` 腳本的執行環境；`git` 用來記錄執行權限並提供 Windows 的 bash。
  官方的 `sh` 腳本在沒有 `jq`、`python3` 時會退回內建的文字處理（`common.sh` 內的註解與程式如此），所以不列為必要。
- **Alternatives considered**: 只檢查 `uv`（Windows 沒有 Git Bash 時會導入成功但流程無法執行，違反 SC-006 的精神）。

## 實測紀錄

環境：Linux、uv 0.13.6；機器上既有的 `specify` 是 1.2.6（未使用）。以下的 `S` 代表
`uv tool run --from specify-cli==1.4.3 specify`。

| # | 指令 | 觀察 |
|---|---|---|
| 1 | `git ls-remote --tags --refs https://github.com/github/spec-kit.git`；`curl https://api.github.com/repos/github/spec-kit/releases/latest`；`curl https://pypi.org/pypi/specify-cli/json` | 最新的 tag、GitHub 最新 release、PyPI 最新版都是 1.4.3；PyPI 沒有預覽版，檔案的 `yanked` 為 false |
| 2 | 讀取 v1.4.3 的 `README.md` 與 `docs/installation.md` | PyPI 的 `specify-cli` 與 GitHub repository 是兩個官方管道；安裝指令為 `uv tool install specify-cli` |
| 3 | `S init --help` | `--script` 為 `sh`、`ps` 或 `py`；init 不需要網路；`--non-interactive`、`--force`、`--ignore-agent-tools`、`--integration` |
| 4 | 在三個空目錄分別執行 `S init --here --force --non-interactive --integration claude --script {sh,ps,py} --ignore-agent-tools` | 結束碼都是 0。`sh` 與 `ps` 各 30 個檔案，只差腳本目錄；`py` 37 個檔案（`python/` 加 `bash/`）。都沒有建立 `.git` 與 `.gitattributes` |
| 5 | `grep -rn "scripts/" .claude/skills` | SKILL.md 寫死腳本路徑，如 R1 的表 |
| 6 | 閱讀套件內的 `integrations/base.py`、`shared_infra.py` | `py` 的直譯器與額外 shell 目錄依執行主機決定；未指定 `--script` 時依 `os.name` 選預設 |
| 7 | 同參數在另一個空目錄再導入一次後 `diff -r` | 只有 `integrations/*.manifest.json` 與 `workflows/workflow-registry.json` 內的時間戳不同 |
| 8 | 在已有 3 個檔案的目錄執行 `S init --here --non-interactive …`（無 `--force`） | 結束碼 1：`Current directory is not empty and --non-interactive was set` |
| 9 | 同上加 `--force` | 結束碼 0；預先放入的 `plan-template.md` 與 `speckit-plan/SKILL.md` 被官方內容覆蓋 |
| 10 | 在空目錄執行不加 `--force` 的 init | 結束碼 0，30 個檔案 |
| 11 | 導入後 commit，執行 `create-new-feature.sh --json --short-name demo "Demo feature"` 與 `setup-plan.sh --json` | 都是結束碼 0，產生 `specs/001-demo/` 與 `plan.md` |
| 12 | `chmod -x` 後直接執行腳本 | `Permission denied`，結束碼 126 |
| 13 | `git clone -c core.autocrlf=true -c core.eol=crlf` 後執行腳本 | `.sh` 為 CRLF；`/usr/bin/env: 'bash\r': No such file or directory`，結束碼 127 |
| 14 | 新增 `.specify/.gitattributes`（`scripts/bash/*.sh text eol=lf`），在 `core.fileMode=false` 的 repository 對沒有執行權限的 `.sh` 執行 `git add --chmod=+x`，commit 後以 `core.autocrlf=true` clone | `git check-attr eol` 對 `.sh` 回報 `lf`；index 內為 100755；clone 後 `.sh` 是 LF 且可執行，第 11 項的兩支腳本都成功 |
| 15 | 對已加入 index 的 `.sh` 執行 `git rm --cached` | 該檔案回到未追蹤，工作目錄的檔案不受影響 |
| 16 | `uv tool run --prerelease disallow --from specify-cli@latest specify --version` | 輸出 `specify 1.4.3`；設定 `UV_OFFLINE=1` 時仍以快取成功 |
| 17 | 同上但指定無法連線的套件來源與 `--no-cache` | 連線被拒，結束碼 2 |
| 18 | `which uvx` | 不存在；`uv tool run` 可用 |
