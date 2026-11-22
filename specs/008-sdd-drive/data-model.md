# Data Model: sdd-drive

決定與理由見 [research.md](./research.md)（以 D 編號引用）；指令介面見 [contracts/cli.md](./contracts/cli.md)。

## 本 skill 的檔案（目標專案內）

| 路徑 | 寫入者 | 內容 |
|---|---|---|
| `.specify/sdd-drive/.gitignore` | 第一次需要寫入時（`run`、`test`、`finalize`） | 固定兩行：`# Created by sdd-drive. Local run records; never committed.` 與 `*` |
| `.specify/sdd-drive/state.json` | `run`、`test`、`finalize` | 嘗試與測試紀錄，見下 |
| `.specify/sdd-drive/lock` | `run`（準備期間）、driver（整個生命期間，含等待重置）、`test`（持有作業系統檔案鎖） | 空檔案；內容沒有意義 |
| `.specify/sdd-drive/cancel` | `cancel` 建立；driver 看到後刪除 | 空檔案；存在代表「取消等待中的自動接續」（D20） |
| `.specify/feature.json` | `run`（只改 `feature_directory`，保留其他鍵） | Spec Kit 的本機狀態檔（原則 I 允許） |

- **資料夾狀態**（`own_dir`）：`none`（不存在）、`ours`（只有上表的檔案與寫入用的暫存檔，且 `.gitignore` 內容與上面完全相同）、`conflict`（其他情況）。
  `conflict` 時所有會讀寫紀錄的指令以 `reason: "conflict"` 停止；`clear` 也不刪除。
- 不讀取、不修改 `.specify/sdd-drive-state.json` 與 `.specify/.gitignore`（D14、T8）。
- `clear` 把 `state.json` 重寫為空的紀錄並設 `baseline: []`、`baseline_reset: true`，刪除 `cancel` 與暫存檔（driver 執行中時拒絕）；只在維護者要求或 `state-unreadable` 時由 SKILL.md 提議（D23：紀錄被清除後偏向需要檢查）。

## 紀錄（`state.json`）

```json
{
  "tool": "sdd-drive",
  "schema": 1,
  "attempts": [
    {
      "id": 1,
      "spec": "008-sdd-drive",
      "phase": "plan",
      "session_id": "5f1c…-uuid",
      "resume": false,
      "model": "opus",
      "model_used": ["claude-opus-5-5"],
      "reason": "Design work with new mechanisms to research.",
      "started_at": "2026-11-21T10:00:00Z",
      "ended_at": "2026-11-21T10:31:12Z",
      "outcome": "succeeded",
      "detail": null,
      "report": {"status": "completed", "summary": "…", "failure": null},
      "worktree": "sha256:…",
      "task_ids": null,
      "auto": false,
      "limit": null,
      "auto_resume": null
    }
  ],
  "baseline": ["001-deploy-tool", "002-global-claude-md"],
  "baseline_reset": false,
  "launch": null,
  "driver": null,
  "tests": [
    {"spec": "007-sdd-rebuild", "tasks_hash": "sha256:…", "command": "uv run --with pytest pytest", "exit_code": 0, "head": "3f2a…", "at": "2026-11-21T09:58:00Z"}
  ]
}
```

| 欄位 | 來源 | 驗證（讀回時） |
|---|---|---|
| `tool`、`schema` | 腳本 | 等於 `"sdd-drive"`、`1` |
| `attempts[].id` | 腳本，由 1 遞增 | 正整數、嚴格遞增 |
| `spec` | 腳本（spec 資料夾名稱） | 格式驗證：符合 Spec Kit 的編號前綴（005 的 `spec_number`），不含 `/`、`\` |
| `phase` | 腳本 | `plan`、`tasks`、`implement`、`check` |
| `session_id` | 腳本（啟動前以 `uuid4` 產生；`resume` 時沿用） | UUID 格式 |
| `resume` | 腳本 | 布林 |
| `model` | 主 session 的 `--model` | 格式驗證 `^[A-Za-z0-9._\[\]-]{1,64}$` |
| `model_used` | `claude` 結果的 `modelUsage` 鍵 | 每個符合上面的格式；沒有結果時為 `[]` |
| `reason` | 主 session 的 `--reason` | **機密掃描**；1–300 字元、單行 |
| `started_at`、`ended_at` | 腳本（UTC） | `YYYY-MM-DDTHH:MM:SSZ`；`ended_at` 在 `outcome` 為 `null` 時為 `null` |
| `outcome` | 腳本（D4） | `null`、`launch-failed`、`usage-limit`、`api-error`、`interrupted`、`failed`、`verify-failed`、`succeeded` |
| `detail` | 腳本 | `null` 或物件：`code`（列舉，見下）、`paths`（字串陣列，**機密掃描**）、`text`（**機密掃描**，≤ 500 字元，取自 `claude` 的錯誤文字） |
| `report` | 子 session 的 `structured_output` | `null` 或符合「子 session 的回報」；字串欄位**機密掃描** |
| `worktree` | 腳本：嘗試結束時工作區的指紋（D8） | `null` 或 `sha256:` 加 64 個十六進位字元 |
| `task_ids` | 腳本：tasks 階段 `succeeded` 時的任務編號（如 `T001`）；check 階段 `gaps-found` 時為原有編號加上附加的編號 | `null` 或符合 `^T\d{3,}$` 的字串陣列 |
| `convergence` | 腳本：只出現在 `check` 的嘗試（D22） | `null`、`converged`、`tasks-appended` |
| `tasks_hash` | 腳本：嘗試結束時這個 spec 的 `tasks.md` 雜湊 | `null` 或同 `worktree` 的格式 |
| `appended` | 腳本：check 附加的任務編號 | `null` 或符合 `^T\d{3,}$` 的字串陣列 |
| `attempts[].auto` | 腳本：這筆嘗試是否為 driver 的自動接續（D19） | 布林 |
| `attempts[].limit` | 腳本：`outcome` 為 `usage-limit` 時依 D17 從 `rate_limit_info` 計算 | `null` 或物件：`waitable`（布林）、`types`（字串陣列，元素屬於 `five_hour`、`seven_day`、`seven_day_opus`、`seven_day_sonnet`、`seven_day_overage_included`、`overage`、`unknown`）、`resets_at`（`waitable` 時為 `YYYY-MM-DDTHH:MM:SSZ`，否則 `null`）、`overage_status`（`null` 或 `allowed`、`allowed_warning`、`rejected`） |
| `attempts[].auto_resume` | 腳本（D18–D20），只出現在 `usage-limit` 的嘗試 | `null`、`waiting`、`started`、`cancelled`、`skipped-changed`、`lost`、`not-waitable`、`already-auto` |
| `launch` | `run`：啟動 driver 前寫入，driver 取得鎖後清除 | `null` 或 `{"token": UUID, "at": 時間}` |
| `driver` | driver：取得鎖後寫入、結束前清除 | `null` 或 `{"token": UUID, "pid": 正整數, "phase": "running"\|"waiting"\|"resuming", "attempt": 嘗試 id, "waiting_until": 時間或 null, "started_at": 時間}` |
| `baseline` | 腳本：第一次寫入紀錄時凍結（D23） | spec 資料夾名稱的陣列（格式同 `spec`），不重複 |
| `baseline_reset` | 腳本：`clear` 寫入時為 `true` | 布林 |
| `tests[].spec` | 腳本 | 同 `spec` |
| `tests[].tasks_hash` | 腳本 | 同 `worktree` 的格式 |
| `tests[].head` | 腳本：執行測試時的 HEAD（非 git 時為 `null`） | `null` 或 40／64 個十六進位字元 |
| `tests[].command` | 腳本，取自 plan.md | **機密掃描**（來自專案檔案的內容，寫入時已掃描；命中時不執行、不寫入，見 cli.md `test`） |
| `tests[].exit_code` | 腳本 | 整數 |

- 寫入時掃描的欄位與讀回時掃描的欄位相同（標為**機密掃描**者）；其餘欄位只做格式驗證（寫入與讀取對稱，D14）。
  `reason` 命中時 `run` 拒絕（不寫入）；`detail.text`、`detail.paths`、`report` 的字串命中時，在寫入前把該字串換成 `(not shown: looks like a secret)`。
- 任何欄位不符合時：`reason: "state-unreadable"`，指出欄位路徑而不含值。
- `limit`、`auto_resume`、`launch`、`driver` 都是腳本計算的欄位，只做格式驗證（不掃描機密）；`rate_limit_info` 的其他欄位與子 session 的其他輸出不保存。
- `launch` 存在且 `at` 在 60 秒內：其他指令視同 `running`（driver 正在取得鎖）；超過 60 秒且鎖未被持有：視為啟動失敗，`run` 的 `watch` 回報 `launch-failed`，`finalize` 清除它。
- `detail.code` 列舉：`launch`、`usage-limit`、`api-error`、`no-result`、`no-report`、`child-failed`、`plan-missing`、`tasks-missing`、`tasks-unfinished`、
  `tasks-removed`、`protected-changed`、`pushed`、`uncommitted`、`resume-failed`、`check-no-tasks`、`check-rewrote-tasks`、`check-touched-files`、`report-mismatch`。
- `outcome` 另有 `gaps-found`（只在 `check`）：對照檢查在 `tasks.md` 附加了任務（D22），計入失敗。

## spec 的狀態（每次由檔案重新計算，D5）

依 spec 編號由小到大，只看 `specs/` 下符合 Spec Kit 編號的資料夾（缺號依實際存在的處理）。

| 條件（由上而下取第一個成立的） | `state` | `next_phase` |
|---|---|---|
| plan 未產生 | `not-started` | `plan` |
| plan 已產生、tasks 未產生 | `planned` | `tasks` |
| tasks 已產生、勾選數為 0 | `tasked` | `implement` |
| 有未勾選的任務 | `implementing` | `implement` |
| 全部勾選、是**既有的基準**（在 `baseline` 且沒有任何 `implement` 嘗試）、`tests` 中有它在目前 `tasks_hash` 下 `exit_code: 0` 的紀錄 | `done` | `null` |
| 全部勾選、是既有的基準、沒有上述紀錄 | `implementing` | `test` |
| 全部勾選、有該 spec 的 `check` 嘗試 `outcome: succeeded`、`convergence: converged`，且其 `tasks_hash` 等於目前的雜湊 | `done` | `null` |
| 全部勾選、`tests` 中有該 spec 在目前 `tasks_hash` 與目前 HEAD（非 git 時只比 `tasks_hash`）下 `exit_code: 0` 的紀錄 | `implementing` | `check` |
| 全部勾選、沒有上述紀錄 | `implementing` | `test` |

- 既有的基準（D23）：在 `baseline` 中且紀錄裡沒有它的 `implement` 嘗試。紀錄尚不存在時，`baseline` 以「tasks 已產生且全部勾選」即時計算；第一次寫入時凍結。
  基準不執行 check（FR-025）；一旦有 `implement` 嘗試（例如維護者加了新任務後由本 skill 補做），就改依其餘各列（測試＋check）。`status` 的每份 spec 附 `baseline: true|false`。
- 「plan 已產生」「tasks 已產生」的判定與「未填寫的範本」見 D5：與範本內容相同、或第一個 `# ` 標題仍含範本佔位字串（plan 為 `[FEATURE]`，tasks 為 `[FEATURE NAME]`）、
  或（tasks）沒有任何任務行，都視為未產生。
- 任務行：`^\s*- \[( |x|X)\] (T\d{3,})\b`；勾選為 `x` 或 `X`。
- **失敗的疊加**：若該 spec 在 `next_phase` 上的最後一筆嘗試是 `failed` 或 `verify-failed`，或（`next_phase` 為 `test`）最後一筆測試紀錄的
  `exit_code` 非 0，`state` 改為 `failed`，`next_phase` 不變（維護者處理後再次執行就從失敗的步驟重試，US4-3）。
- 對照檢查找到漏做（`gaps-found`）後，附加的任務未勾選，依上表回到 `implementing`／`implement`；不套用失敗的疊加（下一步本來就是補做），`failures.check` 加一。
  `tasks.md` 之後的任何改變（補做時勾選、維護者手動處理）都使先前的測試與檢查紀錄失效（以 `tasks_hash` 比對，FR-024）。
- `failures`：該 spec 每個階段的失敗次數 = `outcome` 為 `failed`、`verify-failed` 或 `gaps-found` 的嘗試數，加上（test）`exit_code` 非 0 的測試數。
  `usage-limit`、`api-error`、`interrupted`、`launch-failed` 不計入（FR-021、SC-009）。

## 下一步（`status` 的 `next`）

第一份 `state` 不是 `done` 的 spec 決定下一步；後面的 spec 一律不處理（FR-008、FR-009）。

| 情況 | `next.action` |
|---|---|
| 鎖被持有，或 `launch` 在 60 秒內 | `wait`（`running: true`；附 `driver` 的 `phase`、`waiting_until` 與等待中嘗試的 `limit`） |
| 鎖未被持有，且（最後一筆嘗試 `outcome: null`、`driver` 不為 `null`，或 `launch` 已超過 60 秒） | `finalize` |
| 沒有任何未完成的 spec | `none` |
| `next_phase` 為 `test` | `test` |
| 該 spec 在 `next_phase` 上的最後一筆嘗試是 `usage-limit`、`api-error` 或 `interrupted`，且有 `session_id` | `resume`（附 `session_id`、該嘗試的 `model`、`last_outcome`、`limit`、`auto_resume`）；這是維護者啟動的手動接續（`auto: false`） |
| 其他 | `run`（附 `phase`） |

`next` 另附 `spec`、`phase`、`branch`（等於 spec 資料夾名稱，非 git 時為 `null`）、`failures`、`hints`（D3）：

```json
{"requirements": 22, "user_stories": 4, "plan_bytes": 0, "contracts": 0, "tasks_total": 0, "tasks_open": 0,
 "phase_failures": 0, "models_used_this_run": ["opus", "sonnet"]}
```

`models_used_this_run`：紀錄中所有嘗試（自紀錄開頭或上一次 `clear` 起）依出現順序去重的 `model`。它不區分批次：`status` 是唯讀的，紀錄也不記下何時回報過 `none`，因此無法從檔案分出「這一次流程」；先前批次用過的模型也會列入（對照檢查發現、維護者核可的修訂 A1）。

`status` 另輸出 `last_attempt`：最近一筆有結果的嘗試的 `spec`、`phase`、`outcome`、`auto`、`limit`、`auto_resume`、`ended_at`，供主 session 回報「你不在時發生了什麼」（D20）。

## 自動接續的狀態轉移（D18–D20）

```text
（plan、tasks、implement、check 四個階段都適用）
run（auto:false）── usage-limit ──┬─ limit.waitable=false ─────────────→ auto_resume=not-waitable，driver 結束 → 停止
                                 ├─ 被中斷的嘗試 auto=true ───────────→ auto_resume=already-auto，driver 結束 → 停止
                                 └─ 可等待且 auto=false → auto_resume=waiting（driver.phase=waiting）
                                        ├─ 看到 cancel 檔案 ───────────→ cancelled，driver 結束 → 停止
                                        ├─ 重置後工作區指紋不同 ───────→ skipped-changed，driver 結束 → 停止
                                        ├─ driver 消失（finalize）────→ lost → 停止
                                        └─ 到達 resets_at+120s → started；新嘗試（auto:true，--resume）
                                               └─ 其 outcome 依 D4；若再次 usage-limit → already-auto → 停止
```

## 工作區（git）

- `git`：`true`／`false`（`git rev-parse --is-inside-work-tree`）。
- `dirty`：`git status --porcelain=v1 -z --untracked-files=all` 的路徑，排除 `.specify/feature.json` 與 `.specify/sdd-drive/`；被 ignore 的檔案本來就不列出。
- 工作區指紋：上述輸出加上每個路徑目前內容的 SHA-256，整體再取 SHA-256（不記路徑本身）。
- `leftovers`：`dirty` 不為空、下一步是 `resume`（或 `finalize`），且最後一筆嘗試的 `worktree` 等於目前指紋 → 這些變更屬於被中斷的子 session。
  `finalize` 會在記錄 `interrupted` 時一併寫入目前的指紋。其他有 `dirty` 的情況 → `reason: "dirty"`（D9）。
- remote-tracking refs 的快照：`git for-each-ref --format=%(refname) %(objectname) refs/remotes` 的輸出，只在 `run` 的記憶體中比較，不寫入。

## 受保護的檔案（D10）

`.specify/memory/constitution.md`、`specs/*/spec.md`、`.specify/templates/**`、`.specify/scripts/**`、`.claude/skills/speckit-*/**`。
`run` 在啟動子 session 前與結束後各計算一次 `{路徑: SHA-256 或 null}`，只在記憶體中比較；不同的路徑寫入 `detail.paths`。

## 子 session 的回報（`--json-schema`，D12）

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["status", "summary"],
  "properties": {
    "status": {"enum": ["completed", "failed"]},
    "convergence": {"enum": ["converged", "tasks-appended"]},
    "summary": {"type": "string", "maxLength": 1000},
    "failure": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind", "step", "reason"],
      "properties": {
        "kind": {"enum": ["requirements", "blocked-task", "tests", "tooling", "other"]},
        "step": {"type": "string", "maxLength": 200},
        "reason": {"type": "string", "maxLength": 1000}
      }
    },
    "tasks": {"type": "array", "items": {"type": "string", "pattern": "^T\\d{3,}$"}}
  }
}
```

- `convergence` 只在 check 階段填寫（子 session 的說法，僅供比對；判定以檔案為準，D22）。
- `status: failed` 時 MUST 有 `failure`；`tasks` 列出做不到的任務編號（`blocked-task`）。
- 腳本讀取 `structured_output` 後再以同一份結構驗證；不符合時視為沒有回報（`interrupted`、`detail.code: "no-report"`）。

## 工作說明（提示）的組成

由 `brief` 與 `run` 共用的固定英文範本產生，可計算的值由腳本填入：專案根目錄（以 `.` 表示，不寫絕對路徑）、spec 目錄、分支、階段、
要呼叫的 skill、測試指令（implement）、是否為 git、是否為接續。範本的段落與必含事項見 [contracts/skill.md](./contracts/skill.md)「子 session 的工作說明」。
