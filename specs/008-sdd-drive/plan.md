# Implementation Plan: sdd-drive 由子 session 依序把每份 spec 做到完成

**Branch**: `008-sdd-drive` | **Date**: 2026-11-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-sdd-drive/spec.md`

## Summary

維護者在主 session 輸入 `/sdd-drive`。主 session 的 Claude 依 SKILL.md 協調：每個行動前以腳本重新計算每份 spec 的狀態與下一步，
依編號一次一份、一個階段一個子 session，開子 session 執行 plan、tasks、implement，之後親自（經由腳本）執行測試，再開一個子 session 以 `speckit-converge` 對照檢查有沒有漏做（找到就停止回報），
才往下一個階段或下一份 spec；失敗或中斷時停止並回報。子 session 因有重置時間的用量上限中斷時，在重置後自動從中斷處接續一次，不需要維護者輸入指令；
再次中斷或上限沒有重置時間時停止並回報（FR-021 修訂，2026-11-21）。

做法：**協調式的 skill**。判斷（選模型與理由、轉述結果給維護者）寫在 SKILL.md；可決定的事集中在一支由 uv 執行、輸出 JSON 的腳本
`sdd_drive.py`（`status`、`brief`、`run`、`watch`、`cancel`、`test`、`finalize`、`clear`）。子 session 是腳本以 `claude -p` 啟動的無頭 session
（`--model` 指定模型、`--session-id`／`--resume` 接續、`--json-schema` 結構化回報、`--output-format stream-json` 判讀結束原因與用量上限的重置時間），
由 `run` 以脫離 session 的方式啟動的 **driver** 行程執行；driver 在可等待的用量上限時自己等到重置並以 `--resume` 接續一次，不依賴主 session 的回合
（主 session 與子 session 共用額度，子 session 被擋下時主 session 多半也被擋下）。主 session 以 Bash 背景執行的 `watch` 等待 driver（research D1、D17–D21，依實測 E1–E11）。工作說明完全由腳本產生；進度由檔案判定，
`.specify/sdd-drive/`（不入庫）只補充測試紀錄、失敗次數與可接續的 session。

## Technical Context

**Language/Version**: Python 3.11+（由 uv 依腳本內的 inline metadata 提供）；SKILL.md 與 README.md 為 Markdown

**Primary Dependencies**: 執行期只用 Python 標準函式庫；以 `importlib` 載入相鄰的 `../sdd-grill/scripts/sdd_grill.py`
（Spec Kit 狀態、spec 編號、原子寫入、機密樣式；不修改它）；外部指令 `git`、`claude`（Claude Code 本身，`-p` 無頭模式）、
該 spec 的測試指令；子 session 內以 Skill 工具呼叫 Spec Kit 的 `speckit-plan`、`speckit-tasks`、`speckit-implement`、`speckit-converge`

**Storage**: 檔案。目標專案的 `.specify/sdd-drive/`（`.gitignore`、`state.json`、`lock`，不入庫）、`.specify/feature.json`（只改 `feature_directory`）；
其餘專案檔案只由子 session（經 Spec Kit）修改

**Testing**: pytest，`uv run --with pytest pytest`；GitHub Actions 的 `test` job 在 `ubuntu-latest` 與 `windows-latest` 執行。
腳本的單元測試在暫存目錄以真實的 git、假的 `claude`（`SDD_DRIVE_CLAUDE` 指定的 Python 腳本）覆蓋每一種結果；
SKILL.md 的結構與內容檢查比照 `tests/unit/test_sdd_rebuild_skill.py`；真實子 session 的行為以 [quickstart.md](./quickstart.md) 的人工驗收驗證（D15）。
不新增或修改 CI job

**Target Platform**: Linux 與 Windows 上的 Claude Code（`claude` 2.1.x，實測版本 2.1.319）

**Project Type**: Claude Code skill（一份 SKILL.md、一份 README、一支腳本）

**Performance Goals**: `status`、`brief`、`finalize`、`clear` 在數十份 spec 的專案於 1 秒內完成；`run`、`test` 的時間由子 session 與測試決定

**Constraints**:

- 只需要 Claude Code 本身與 uv（FR-013）；不使用 Orca、Agent 工具以外的協調工具
- 主 session 不親自產生 plan、tasks 與程式碼（FR-002）；工作說明由腳本產生
- 一律不 push；不捨棄、不覆蓋、不替維護者 commit 未提交的變更
- 子 session 的完整輸出不寫入檔案、不進入主 session 的上下文；機密值不出現在輸出與紀錄
- Bash 背景執行最長 2 小時：`watch` 每 110 分鐘結束一次由主 session 重新啟動；子 session 與等待重置在脫離的 driver 中進行，不受此限（D18）；`test` 最長 2 小時
- 自動接續只由 driver 做、每次中斷最多一次；driver 不開始下一個階段（模型由主 session 選）
- 產出只有 skill 文件或 script；Python 一律用 uv 執行

**Scale/Scope**: 一個專案、數份到數十份 spec；同時只有一個流程；單一使用者

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 constitution v1.0.2 逐條檢查（Phase 0 前與 Phase 1 設計後各一次，結果相同）。

| 原則 | 判定 | 說明 |
|---|---|---|
| I. 只包裝、不修改 Spec Kit | 通過 | plan、tasks、implement 與對照檢查只由子 session 以 Skill 工具呼叫 `speckit-*`（含 `speckit-converge`）進行，本 skill 不自行手寫檢查（FR-023）；check 階段只接受 converge 定義的「在 tasks.md 末尾附加」（D22）；工作說明禁止手寫其產物（FR-006）；`run` 事後偵測 Spec Kit 範本、腳本與 `speckit-*` skill 是否被改動（D10）。在 `.specify/` 只新增自己的 `.specify/sdd-drive/`，以資料夾名稱與 `.gitignore` 第一行的註解記錄歸屬（同 005）。`.specify/feature.json` 只改 `feature_directory`（原則 I 明定的例外）。不讀不改另一個工具的 `.specify/sdd-drive-state.json` 與 Spec Kit 的 `.specify/.gitignore` |
| II. Windows 與 Linux 完全對等 | 通過（含一項風險） | 子 session 的啟動、判讀、檢查與用量上限的等待都在腳本內，以 Python subprocess 執行 `claude`（兩個平台都可用）；提示走 stdin，不依賴 shell 的引號；檔案鎖依平台用 `fcntl`／`msvcrt`；測試指令要求兩個平台寫法相同。可測的部分（腳本）有單元測試在兩個平台的 CI 執行；不可測的部分（真實子 session）以內容檢查與 quickstart 的人工驗收（含 Windows）涵蓋（D15）。driver 的脫離啟動依平台用對應的建立旗標，CI 在兩個平台以「終止啟動它的行程樹」驗證存活；Claude Code 在 Windows 終止背景指令的方式無法在 CI 重現，以人工驗收 15 確認，失敗時的結果是 `lost`（停止並回報，不會造成錯誤狀態）（T10） |
| III. 保護既有檔案 | 通過 | 腳本只寫自己的資料夾與 `feature.json`；工作區不乾淨時不開始（D9）；不 stash、reset、checkout、clean、merge；分岔的分支不處理（`branch-diverged`）；受保護檔案被改動時回報不還原；`.specify/sdd-drive/` 有不明檔案時視為衝突。driver 只寫自己的資料夾；自動接續前確認工作區與中斷時相同，不同就不接續（D20）。`status`、`brief`、`watch` 只讀；`finalize`、`clear`、`cancel` 冪等 |
| IV. 先確認再寫入 | 通過（不適用） | 本 skill 不產生或改寫 constitution 與 spec；工作說明禁止子 session 修改它們，`run` 事後偵測（FR-016）。全自動不經核可的是 plan、tasks、實作，屬維護者已接受的取捨（spec Assumptions） |
| V. 個人使用、repo 公開 | 通過 | 紀錄中來自外部的字串（理由、子 session 回報、錯誤文字、測試指令）寫入與讀回都以共同的機密樣式掃描（寫入與讀取對稱），腳本計算的欄位（含 `limit`、`auto_resume`、`driver`）只驗證格式；子 session 的完整輸出（stream-json）不保存，只取結構化的限額資訊與結果物件；輸出中的機密以 `(not shown…)` 取代；紀錄不入庫；SKILL.md、README、腳本、工作說明沒有絕對路徑與信箱（結構測試） |
| VI. 文件語言 | 通過 | SKILL.md、腳本訊息、工作說明為英文；README 為繁體中文；本 spec 的設計文件為繁體中文 |

**Complexity Tracking：沒有例外。**

## Project Structure

### Documentation (this feature)

```text
specs/008-sdd-drive/
├── plan.md              # 本文件
├── research.md          # 實測紀錄 E1–E12、決策 D1–D23、經驗的處理 O1–O8、設計取捨 T1–T15
├── data-model.md        # 本 skill 的檔案、紀錄、spec 狀態、下一步、受保護檔案、子 session 的回報
├── quickstart.md        # 自動測試與人工驗收
├── contracts/
│   ├── cli.md           # sdd_drive.py 的指令介面
│   └── skill.md         # SKILL.md 的必要指示：階段 1–6 與 3B（7 個）、61 種結果的下一步（含 check 階段與既有的基準）；工作說明的必含事項
└── tasks.md             # Phase 2（/speckit-tasks 產生，不在本階段）
```

### Source Code (repository root)

```text
home/skills/sdd-drive/
├── SKILL.md                     # 英文；frontmatter 與 7 個階段（contracts/skill.md）
├── README.md                    # 繁體中文簡述
└── scripts/
    └── sdd_drive.py             # uv inline metadata；載入 ../../sdd-grill/scripts/sdd_grill.py；含工作說明範本與回報的 JSON Schema

tests/unit/
├── test_sdd_drive.py            # 腳本的單元測試（狀態、下一步、run 的每種 outcome、test、鎖、git、機密、brief）
├── test_sdd_drive_skill.py      # SKILL.md 與 README 的結構與內容檢查
└── fixtures/sdd_drive/
    └── fake_claude.py           # 假的 claude：依環境變數指定的情境寫檔案、印出結果物件或不印就結束

README.md                        # repo 的說明：更新「目前狀態」並新增 /sdd-drive 一節（6 個 skill 到齊）
```

**Structure Decision**：與 005、006、007 相同的單一 skill 資料夾。共用程式以執行時載入相鄰的 sdd-grill 腳本達成，不新增共用資料夾、不修改 sdd-grill。

## SKILL.md 與腳本的分工

| 由腳本決定（可測） | 由 SKILL.md 指示主 session（內容檢查＋人工驗收） |
|---|---|
| 前置條件（Spec Kit、三個 `speckit-*`、`claude`、git） | 依 `reason` 向維護者說明並停止 |
| 每份 spec 的狀態、範本判定、下一步、失敗次數、規模提示 | 每個行動前先 `status`，不憑記憶 |
| 鎖（同時只有一個流程）、`finalize` | 看到 `running` 時不啟動、不 `finalize`，改以 `watch` 接手 |
| driver：脫離啟動、用量上限的判讀（`limit`）、等待重置、自動接續一次、取消、等待期間工作區檢查 | 依 `watch` 的 `status` 與 `auto_resume` 回報；不自己等待或排程；維護者要求時 `cancel` |
| 分支的建立與切換、`feature.json` | 不自己操作 git 與 `feature.json` |
| 工作說明、`claude` 的啟動參數（模型、接續、權限、結構化回報） | 選模型並寫理由；接續時加 `--resume` |
| 結果分類（D4）與檢查（產物、任務、受保護檔案、push、未提交） | 依 `outcome` 回報與停止；不改為親自實作 |
| 測試指令的取得與執行、紀錄 | 以背景執行 `test`；不採信子 session |
| 機密掃描與取代 | 不在理由與回報中寫機密 |
| — | 宣告、每階段的一行回報（含模型與理由）、結束報告 |

## 需求與驗證方式

| 需求 | 實現 | 驗證 |
|---|---|---|
| FR-001 只由維護者啟動 | `disable-model-invocation: true` | 內容檢查（frontmatter）；`test_claude_md.py` |
| FR-002、SC-007 主 session 不親自做 | SKILL.md 通則 1、3；子 session 由 `run` 啟動 | 內容檢查；人工驗收 1 |
| FR-003、FR-008 依編號、一次一份、確認完成才往下 | `status` 的 `next` 只看第一份未完成的 spec；`run`／`test` 拒絕 `not-next`；鎖 | 單元測試；人工驗收 1、5 |
| FR-004、SC-001 不等核可 | SKILL.md 通則 5；`succeeded` 直接回到 `status` | 內容檢查；人工驗收 1 |
| FR-005 技術選型依 constitution | 工作說明 | `brief` 的單元測試 |
| FR-006 透過 Spec Kit | 工作說明要求 Skill 工具；產物檢查；受保護檔案偵測 | `brief` 與 `run` 的單元測試；人工驗收 2 |
| FR-007、SC-002 完成＝任務全勾＋測試通過＋對照檢查沒有漏做；範本不算 | data-model「spec 的狀態」；`test` 親自執行；check 以檔案判定（D22） | 單元測試（範本、部分勾選、`tasks_hash` 或 HEAD 改變後需重測、測試失敗、未檢查不算完成） |
| FR-023 以子 session 透過 speckit-converge 檢查；找到漏做即失敗、停止、不修正 | check 階段、`gaps-found`、`findings`；工作說明禁止修正 | 單元測試（各種 check 結果）；`brief` 的單元測試；內容檢查（階段 3 的對應列）；人工驗收 4b |
| FR-025 既有的基準不檢查 | `baseline` 於第一次寫入時凍結；有 `implement` 嘗試即不再是基準；`clear` 後沒有基準（D23） | 單元測試（基準只測試、補做後需檢查、清除後沒有基準、第一次 `status` 與寫入後一致）；人工驗收 4a |
| FR-024 再次啟動先補做、重新測試與檢查；有變動不沿用 | 附加的任務使狀態回到 implement；結果以 `tasks_hash`、HEAD 綁定 | 單元測試（gaps-found 後的下一步、變動後重測重檢、converged 後不重複）；人工驗收 4b |
| FR-009、SC-003 失敗即停止 | `failed` 疊加使 `next` 停在同一份；SKILL.md 階段 3、4 | 單元測試；人工驗收 4 |
| FR-010、SC-005 回報 | SKILL.md 階段 5；`run`、`test` 的輸出 | 內容檢查；人工驗收 4、5 |
| FR-011、SC-004 依檔案判定、不重做 | 狀態每次由檔案計算；工作說明只做未完成的部分 | 單元測試（各狀態與接續）；人工驗收 5 |
| FR-012 單一流程 | 作業系統檔案鎖 | 單元測試（另一個程序持有鎖時 `running`、程序結束後釋放）；人工驗收 6 |
| FR-013、SC-006 只需要 Claude Code | `claude -p` | 內容檢查（不提及 Orca）；人工驗收 |
| FR-014 前置條件 | `status` 的 `reason` | 單元測試；人工驗收 9 |
| FR-015 不捨棄變更 | `dirty`、leftovers 指紋、`uncommitted`、不還原 | 單元測試；人工驗收 7 |
| FR-016 不改 constitution 與 spec | 工作說明；`protected-changed` | 單元測試；人工驗收 4 |
| FR-017 兩平台相同 | D15 | 兩平台 CI；人工驗收 12 |
| FR-018 英文與繁中 README | — | 內容檢查 |
| FR-019、SC-008 逐次選模型 | SKILL.md 通則 8；`run` 必填 `--model`、`--reason`；`hints` | 單元測試（缺少時 `usage`、參數傳給 `claude`）；內容檢查；人工驗收 2 |
| FR-020 回報模型與理由 | `run` 輸出 `model`、`model_used`、`reason`；SKILL.md 階段 3、5 | 單元測試；內容檢查 |
| FR-021、SC-009 用量上限不算失敗、回報原因／種類／重置時間／進度 | D4、D17、D21；`failures` 不計入 | 單元測試（各種 `rate_limit_info`、只有文字、沒有結果、失敗次數不變）；內容檢查（通則 13）；人工驗收 11、12 |
| FR-021、SC-010 有重置時間時自動接續一次；再次中斷或沒有重置時間時停止 | D18、D19；driver 等待後 `--resume`；`auto` 計數 | 單元測試（自動接續一次、再次中斷停止、不可等待停止、手動啟動後重設、取消、工作區改變、driver 消失、存活於行程樹終止）；人工驗收 11、13–15 |
| FR-022 接續 | `--session-id`／`--resume`；leftovers 指紋 | 單元測試（接續參數、leftovers 允許接續）；人工驗收 5、11、14 |
| Edge Cases | contracts/skill.md 階段 1–4 的對應列 | 單元測試＋內容檢查 |

`tests/unit/test_claude_md.py::test_referenced_skills_exist_in_home_skills` 目前因缺少 `home/skills/sdd-drive` 而 skip；
008 建立 `home/skills/sdd-drive/SKILL.md` 後它會生效，並因 6 個被引用的 skill 都有 `SKILL.md` 而通過。tasks MUST 包含執行這項測試並確認它不再 skip。

## 設計取捨（核可時請特別注意）

詳見 [research.md](./research.md)「設計取捨」T1–T15（全部已於 2026-11-21 核可；T5 改為納入、T14 改為既有的基準不檢查）。重點：

1. **T1 每個階段一個子 session**（而不是 spec 字面上的「一個子 session 依序處理」）：為了逐階段選模型、不採信子 session、便宜的接續。
2. **T3 子 session 允許所有 Bash 指令**（只禁止 `git push`，並以 `acceptEdits`、`--permission-prompts none` 執行）。
3. **T5 已納入 `speckit-converge`**（維護者 2026-11-21 決定，FR-023、FR-024）：代價是每份 spec 多一個 check 子 session（預設 `opus`）的用量與時間，找到漏做就停止，需要維護者再次啟動。
   **T14（維護者決定，FR-025）**：導入前已完成的 spec 是既有的基準，只測試、不做對照檢查（research D23；本 repo 的 001–007 即是）；紀錄被 `clear` 後偏向需要檢查。
   **T15（已核可）**：converge 對「多做的工作」（`unrequested`）也會附加任務而停止流程。
4. **T4 一律不 push**：「完成」是本機測試通過，不含兩個平台的 CI。
5. **T2 測試指令取自 plan.md 的 `**Testing**:` 行**；**T7 中斷被發現時先回報、下一次才接續**。
6. **用量上限的實際訊息無法實測**（research E5、E9）：被拒絕時的 `rate_limit_info` 形狀依程式內容推得；判斷不出來一律不自動接續（停止），以人工驗收 11 確認。
7. **自動接續的代價**（2026-11-21 新增，research T9–T13）：
   - T9：driver 是脫離終端機的行程，維護者離開或關閉終端機後仍會在重置時接續一次並消耗用量；結果寫在 `.specify/sdd-drive/state.json`，下一次 `/sdd-drive` 回報。
   - T10：Windows 上 driver 能否撐過 Claude Code 終止背景指令未經實測（Linux 已實測），失敗時退化為停止並回報。
   - T11：driver 只保證被中斷的階段自動接續；之後的階段要主 session 繼續，主 session 若也被擋下則依賴 Claude Code 內建的「Continue automatically at usage limit」（有條件），不適用時流程在該階段完成後停下。
   - T12：重置時間沒有上限（7 天的時間窗也等）。T13：輸出格式改為 stream-json。
   - 連帶影響 T6：長的 implement 不再被 2 小時上限終止。

## 仍待釐清的事項

沒有。只用 Claude Code 能滿足所有 MUST（research E2、E3、E6、E8、E9、E11、E12 與 D1、D17–D23）；上面的取捨（含 T9–T13）由維護者在核可時決定。

## Complexity Tracking

沒有違反 constitution 的設計，不需要例外。
