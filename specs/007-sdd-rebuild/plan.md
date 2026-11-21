# Implementation Plan: sdd-rebuild 在新專案以養分重建

**Branch**: `007-sdd-rebuild` | **Date**: 2026-11-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-sdd-rebuild/spec.md`

## Summary

維護者在已導入 Spec Kit 的新專案輸入 `/sdd-rebuild <舊專案路徑>`。Claude 經由腳本讀取舊專案的養分（沒有時先依 006 的規則對舊專案匯出），
逐項請維護者保留、修改、合併、拆分或捨棄原則、功能與教訓，釐清這一代的新需求、決定教訓引發的調整，呈現最終摘要；
確認後透過 `speckit-constitution` 與 `speckit-specify` 依相依順序產生 constitution 與 spec，再把世代紀錄寫到新專案的
`.sdd-rebuild/lineage.json`，供這個專案日後 `/sdd-export` 時使用；最後說明下一步是 `/sdd-drive` 並停止。

做法：與 005、006 相同，**對話式的 skill**。對話與語意判斷寫在 SKILL.md；可決定的事集中在一支由 uv 執行、輸出 JSON 的腳本
`sdd_rebuild.py`（`check`、`save`、`preview`、`claim`、`verify`、`lineage`、`focus`、`clear`），它在執行時載入相鄰的 006 `sdd_export.py`
（養分與世代紀錄的讀取、驗證、序列化）與 005 `sdd_grill.py`（Spec Kit 的狀態、指紋、原子寫入、產生結果的驗證），
**不修改這兩支腳本**。世代紀錄的每個欄位由腳本從「養分快照 + 維護者的決定」組成，`derived_from` 依維護者 2026-11-20 的決定補入祖先，
寫入前以 006 的程式驗證，並模擬下一次匯出。

## Technical Context

**Language/Version**: Python 3.11+（由 uv 依腳本內的 inline metadata 提供）；SKILL.md 與 README.md 為 Markdown

**Primary Dependencies**: 執行期只用 Python 標準函式庫；以 `importlib` 載入相鄰的 `../sdd-export/scripts/sdd_export.py` 與
`../sdd-grill/scripts/sdd_grill.py`（004 載入 `sdd_init.py` 的做法）；外部指令只有只讀的 `git`；
對話中呼叫 Spec Kit 的 `speckit-constitution`、`speckit-specify`，並依 006 的 SKILL.md 與 005 的「Rules for questioning」進行匯出與追問

**Storage**: 檔案。新專案：`.specify/sdd-rebuild/`（進度，不入庫）、`.sdd-rebuild/lineage.json` 與 `.gitattributes`（入庫）、
Spec Kit 產生的 constitution 與 spec、`.specify/feature.json`（只改 `feature_directory`）。舊專案：只讀 `.sdd-export/` 與 `.sdd-rebuild/lineage.json`

**Testing**: pytest，`uv run --with pytest pytest`；GitHub Actions 的 `test` job 在 `ubuntu-latest` 與 `windows-latest` 執行。
腳本的單元測試與多代來回測試在暫存目錄以真實的 006、005 腳本進行（Spec Kit 產生 spec 的部分以建立資料夾與 `feature.json` 模擬）；
skill 的結構／內容檢查比照 `tests/unit/test_sdd_export_skill.py`；對話行為以 [quickstart.md](./quickstart.md) 的人工驗收驗證。
不新增或修改 CI job（[research.md](./research.md) R12）

**Target Platform**: Linux 與 Windows 上的 Claude Code

**Project Type**: Claude Code skill（一份 SKILL.md、一份 README、一支腳本）

**Performance Goals**: 每個腳本指令在數十個功能、數百條需求的養分上於 1 秒內完成；對話本身沒有效能目標

**Constraints**:

- 維護者確認摘要之前，新專案的 constitution、spec 與世代紀錄零異動（進度除外）；舊專案除了經確認的匯出之外零異動
- 世代紀錄只能由腳本組成與寫入，寫入前通過 006 的 `lineage_problems` 與下一次匯出的模擬
- 世代規則只有一份實作（006）；007 只實作 006 定義為「007 寫入時 MUST 遵守、006 無法檢查」的部分
- 匯出的規則只有一份（006 的 SKILL.md）；追問的規則只有一份（005 的 SKILL.md）；007 讀取已部署的檔案並照做
- 產出只有 skill 文件或 script；Python 一律用 uv 執行；不 push

**Scale/Scope**: 一次重建一個舊專案（spec 的 Assumptions）；數個到數十個功能；單一使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 constitution v1.0.2 逐條檢查（Phase 0 前與 Phase 1 設計後各一次，結果相同）。

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | constitution 與 spec 只經由 `speckit-constitution`、`speckit-specify` 產生，MUST NOT 手寫或修改（contracts/skill.md 通則 4）。在 `.specify/` 只新增自己的 `.specify/sdd-rebuild/`，以資料夾名稱與 `.gitignore` 的註解記錄歸屬（同 005）。`.specify/feature.json` 只由 `focus` 改寫 `feature_directory`（原則 I 明定的例外）。`claim` 只讀 `feature.json`。世代紀錄在 `.specify/` 之外（006 定的位置） |
| II. Windows 與 Linux 完全對等 | 通過 | 腳本只用標準函式庫，路徑以實際路徑比較、Windows 上不分大小寫；輸出逐位元組相同；固定測試資料證明兩個平台以同一份養分重建出同一份世代紀錄、CRLF 輸入結果相同（R12）。`test` job 在兩個平台執行 |
| III. 保護既有檔案 | 通過 | 不覆蓋既有 constitution（`keep` 為預設，`amend` 經同意）與既有 spec（只對應、不改）；`lineage` 遇到內容不同的既有世代紀錄時拒絕；`.sdd-rebuild/`、`.specify/sdd-rebuild/` 有不明檔案時視為衝突；`clear` 只刪自己的兩個檔案；中途失敗不刪除 Spec Kit 已產生的文件；舊專案只讀。所有指令重複執行結果相同（`lineage` 冪等、`claim` 與 `focus` 已完成時不再寫入） |
| IV. 先確認再寫入 | 通過 | 確認前唯一的寫入是進度（原則 IV 允許的例外，任務說明明定）；`claim`、`lineage`、`focus` 要求已確認的進度；待確認的項目逐項決定後才寫入（`pending-undecided`）；比對時沒有依據的規則移除或標為待確認 |
| V. 個人使用、repo 公開 | 通過 | 機密值不進入進度（`save` 的樣式攔截）、世代紀錄（來自已通過 006 機密攔截的養分與經攔截的進度）與產生的文件（指示）；世代紀錄只記舊專案的名稱，不記路徑；進度記舊專案的絕對路徑但不入庫。SKILL.md 與腳本沒有絕對路徑與信箱（結構測試） |
| VI. 文件語言 | 通過 | SKILL.md 與腳本訊息為英文，README 為繁體中文；產生的 constitution 與 spec 為繁體中文、規範詞保留英文（FR-021 的例外：新專案既有文件為其他語言時依該語言） |

**Complexity Tracking：沒有例外。**

## Project Structure

### Documentation (this feature)

```text
specs/007-sdd-rebuild/
├── plan.md              # 本文件
├── research.md          # Phase 0：R1 至 R13 與實測紀錄
├── data-model.md        # Phase 1：進度、目標、祖先表、世代紀錄的組成
├── quickstart.md        # Phase 1：自動測試與人工驗收
├── contracts/
│   ├── cli.md           # sdd_rebuild.py 的指令介面
│   └── skill.md         # SKILL.md 的必要指示：13 個階段與接續，每一種結果的下一步
└── tasks.md             # Phase 2（/speckit-tasks 產生，不在本階段）
```

### Source Code (repository root)

```text
home/skills/sdd-rebuild/
├── SKILL.md                     # 英文；frontmatter 與 13 個階段（contracts/skill.md）
├── README.md                    # 繁體中文簡述，含已知限制
└── scripts/
    └── sdd_rebuild.py           # uv inline metadata；載入 ../../sdd-export、../../sdd-grill 的腳本

tests/unit/
├── test_sdd_rebuild.py          # 腳本的單元測試
├── test_sdd_rebuild_generations.py  # 多代來回（真實的 006 與 007 腳本交替執行）
├── test_sdd_rebuild_skill.py    # 結構與內容檢查，含跨 skill 的一致性與 006 data-model 的契約文字
└── fixtures/sdd_rebuild/        # 固定測試資料（以 006 的 nutrients.json 重建出的 lineage.json 等）

specs/006-sdd-export/data-model.md   # 依維護者核可修改「007 寫入時 MUST 遵守的規則」（見下）
```

**Structure Decision**：與 005、006 相同的單一 skill 資料夾。共用程式以執行時載入相鄰 skill 的腳本達成（R2），不新增共用資料夾。

## 與 005、006 的程式共用（R2）

- **以載入共用**：006 的養分與世代紀錄的讀取、驗證、序列化、走訪、差異、機密樣式、`generation_problems`；
  005 的 Spec Kit 狀態、constitution 狀態、編號、指紋、原子寫入、`read_feature_directory`、`verify_generated`。
- **007 自己實作**：自己的進度資料夾（005 的函式把 sdd-grill 的檔名與 `.gitignore` 內容寫成常數）、進度的驗證與快照、祖先表與補入、
  世代紀錄的組成與 007 的寫入規則、`claim`、`.sdd-rebuild/` 的寫入、`focus`、`clear`。
- **005、006 的腳本與測試：不修改。** 已確認需要的函式都存在且載入時無副作用（006 cli.md「以模組方式載入」、005 cli.md 同節）。
- **相鄰檔案缺少時**：所有指令以結束碼 3、`reason: "dependency"` 停止（contracts/cli.md）。

## 遞移帶入 `derived_from`（R5，維護者 2026-11-20 的決定）

- 祖先表由來源養分與舊專案的世代紀錄（可用時）組成；保留、修改的項目「沿用並補入祖先」，合併、拆分的項目以直接來源補入祖先；
  直接來源在前、祖先依記錄順序深度優先展開、去重保留第一次出現；冪等。
- 實測（research「實測紀錄」1 至 6）：照此寫出的世代紀錄 006 讀為 `present`；之後各種匯出都通過；`status-list` 等歷史 `id` 被規則 9 擋下；
  規則 8 允許沿用世代紀錄記下的祖先；規則 5 不把變長的 `derived_from` 當成修改。
- 舊專案的世代紀錄無法使用時（無法讀取、格式較新、不符合規則、世代不符、匯出後被移除）：一題詢問停止處理（建議）或只以養分繼續，
  選擇記入進度並在摘要與報告列出（R4、contracts/skill.md 階段 3）。

## 對 006 文件的修改（留給 007 的實作階段）

維護者核可的規則含義修改。只改 `specs/006-sdd-export/data-model.md`，不改 006 的腳本、SKILL.md 與測試；`schema` 維持 1。
由 `tests/unit/test_sdd_rebuild_skill.py` 檢查修改後的文字存在（鎖定契約），行為由 `test_sdd_rebuild_generations.py` 鎖定。

**修改一**：「007 寫入時 MUST 遵守的規則」表的四列。

修改前：

```text
| 原樣保留 | 沿用 | 沿用 | 沿用 | 沿用 | |
| 修改後保留 | 沿用 | 沿用 | 沿用並加上 `generation` | 沿用 | |
| 合併多個項目 | 新取（見表後） | `generation` | 空 | 被合併的 `id` | 被合併的項目不必另記為捨棄 |
| 拆分一個項目 | 新取（見表後） | `generation` | 空 | 被拆分的 `id` | |
```

修改後：

```text
| 原樣保留 | 沿用 | 沿用 | 沿用 | 沿用並補入祖先（見表後） | |
| 修改後保留 | 沿用 | 沿用 | 沿用並加上 `generation` | 沿用並補入祖先（見表後） | |
| 合併多個項目 | 新取（見表後） | `generation` | 空 | 被合併的 `id`，並補入祖先（見表後） | 被合併的項目不必另記為捨棄 |
| 拆分一個項目 | 新取（見表後） | `generation` | 空 | 被拆分的 `id`，並補入祖先（見表後） | 原項目可以同時依「原樣保留」或「修改後保留」保留 |
```

**修改二**：在「「新取」的 `id` MUST NOT …（世代規則 9）。」一段之後、「來源養分中的每一個有效項目 MUST 對應到上表其中一列 …」一段之前，
插入下列兩段：

```text
「補入祖先」：007 以來源養分的所有有效項目，以及舊專案的 `.sdd-rebuild/lineage.json`（存在、通過驗證且世代與養分相同時）的所有有效項目，
建立「`id` → `derived_from`」的祖先表（同一個 `id` 兩邊都有時取聯集，養分的在前）。寫入的 `derived_from` 是：直接來源依序在前
（保留與修改的項目是祖先表中它自己的清單，合併與拆分的項目是被合併或被拆分的 `id`），接著依直接來源的順序，把每個直接來源在祖先表中的
`derived_from` 依記錄的順序深度優先展開；去重，保留第一次出現的位置。如此一來，經過合併再拆分的項目仍記得最早的來源，
那些 `id` 留在世代紀錄中而被世代規則 9 擋下重用；世代規則 8 允許沿用世代紀錄已記下的來源，世代規則 5 只比較內容欄位，
所以補入後變長的 `derived_from` 不影響下一次匯出。

已知限制（維護者接受，2026-11-20）：捨棄紀錄沒有 `derived_from`，被捨棄項目的來源只保留到該次捨棄為止（被捨棄的項目本身仍在
`discarded`，不能重用）；匯出時的合併或拆分只記下直接來源（世代規則 8 不允許在匯出時補入），下一次重建由舊專案的世代紀錄補上，
但同一代內第二次匯出合併了第一次匯出才建立的項目時，第一次匯出記下的來源會遺失。
```

## 設計取捨（核可時請特別注意）

1. **已知限制兩項**（維護者已接受）：同一代第二次匯出的來源遺失；捨棄項目的來源只保留到捨棄為止。以測試寫明，README 與 006 data-model 註記。
2. **舊專案的世代紀錄可以被略過**：無法使用時提供「只以養分繼續」，祖先可能遺失；以一題詢問、建議停止，選擇記入進度並在摘要與報告列出。
3. **一個專案只重建一次**：新專案已有世代紀錄時停止（006 的契約只有一份世代紀錄，第二次重建會覆蓋它）。要再生下一代就匯出後另開新專案。
4. **確認後以快照為準**：確認後舊專案的養分改變只告知、不重新決定；確認前則詢問是否改用新的養分。
5. **`claim` 取代 Claude 抄寫 `spec_dir`**：多一個指令與一步，但 `spec_dir` 寫錯是 006 察覺不到、會讓下一代沿用到錯的 spec 的錯誤。
6. **已產生的 spec 被刪除時不重新產生**：重新產生的編號會排到最後、破壞相依順序；出路是還原或重新開始（已產生的文件保留）。
7. **對應既有 spec**：新專案已有的 spec 可以對應到養分的功能，世代紀錄的 `spec_dir` 指向既有資料夾、不產生新 spec；這些功能排在最前面。
8. **匯出與追問的規則以讀取已部署的 006、005 SKILL.md 共用**：不複製規則，以結構測試檢查被引用的段落仍存在；代價是 007 的行為依賴兩個 skill 都已部署（`check` 檢查）。
9. **新取 `id` 的禁用範圍比 006 的寫入規則表更廣**（另含舊專案世代紀錄、祖先、同一份世代紀錄中補齊後的 `derived_from`）：只限制 007 自己，
   寫在 007 的 data-model，不修改 006 的文字。
10. **世代紀錄中的文字維持繁體中文**：006 schema 1 的養分語言固定為 `zh-Hant`；新專案的文件依 FR-021 使用其他語言時，世代紀錄的文字仍是繁體中文。

## 仍待釐清的事項

沒有。遞移帶入的兩個缺口已由維護者決定（Q1 選 (a)、Q2 選 (a)），拆出且保留原項的表示方式與 `derived_from` 的順序已獲同意。

## Complexity Tracking

沒有違反 constitution 的設計，不需要例外。
