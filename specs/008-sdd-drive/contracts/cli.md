# Contract: sdd_drive.py 的指令介面

```text
uv run <skill>/scripts/sdd_drive.py status                                   前置條件、每份 spec 的狀態、下一步（只讀）
uv run <skill>/scripts/sdd_drive.py brief    --spec <dir> --phase <phase>    印出交給子 session 的工作說明（只讀）
uv run <skill>/scripts/sdd_drive.py run      --spec <dir> --phase <phase> --model <model> --reason <text> [--resume] [--fresh]
                                                                             準備後啟動 driver（子 session 在其中執行、檢查、記錄），再如 watch 等待
uv run <skill>/scripts/sdd_drive.py watch    [--minutes <n>]                 等待 driver 結束、進入等待重置或時間到（只讀）
uv run <skill>/scripts/sdd_drive.py cancel                                   要求取消等待中的自動接續
uv run <skill>/scripts/sdd_drive.py test     --spec <dir>                    親自執行該 spec 的測試指令並記錄
uv run <skill>/scripts/sdd_drive.py finalize                                 把沒有結果的嘗試記為 interrupted
uv run <skill>/scripts/sdd_drive.py clear                                    刪除本 skill 的紀錄
```

另有內部指令 `_drive --token <uuid>`：只由 `run` 以脫離的方式啟動，SKILL.md 不提及（D18）。

`<skill>` 是 skill 的資料夾，SKILL.md 以 `${CLAUDE_SKILL_DIR}` 表示。一律在目標專案的根目錄執行（目前目錄）。`<dir>` 是 `specs/` 下的資料夾名稱
（例如 `008-sdd-drive`），`<phase>` 是 `plan`、`tasks`、`implement`。子指令不認得、缺少或多出參數時，結束碼 1，`reason: "usage"`。

資料格式見 [data-model.md](../data-model.md)；決定與理由見 [research.md](../research.md)。

## 共通

- stdout 只有一份 JSON 物件（UTF-8、LF、縮排 2、`ensure_ascii=False`、結尾換行），鍵的順序固定；路徑相對於專案根目錄、以 `/` 分隔。
  例外：`brief` 印出純文字的工作說明。
- 失敗時 JSON 有 `"error": "<一句英文>"` 與 `"reason": "<列舉值>"`，同一句 `error` 也寫到 stderr。SKILL.md 依 `reason` 分支。
- **寫入範圍**：`status`、`brief`、`watch` 不寫入任何檔案。`run` 寫 `.specify/sdd-drive/`、`.specify/feature.json`，並在需要時建立或切換 git 分支（D11）；driver 只寫 `.specify/sdd-drive/`（刪除 `cancel` 也是）；`cancel` 只建立 `.specify/sdd-drive/cancel`；
  其餘的專案檔案只由子 session 修改。`test` 只寫 `.specify/sdd-drive/`（測試指令本身可能寫入專案自己的暫存檔，不在本 skill 的控制內）。
  `finalize` 只寫 `.specify/sdd-drive/state.json`。`clear` 只刪除本 skill 的四個檔案與變空的資料夾。寫入一律「同資料夾的暫存檔再取代」。
- **不做的事**：任何指令都不 commit、不 push、不 stash、不 reset、不 checkout 檔案、不 merge、不刪除分支，不讀取也不修改
  `.specify/sdd-drive-state.json` 與 `.specify/.gitignore`。
- 執行時以 `importlib` 載入 `<skill>/../sdd-grill/scripts/sdd_grill.py`（Spec Kit 狀態、spec 編號、原子寫入、機密樣式）；不存在或載入失敗時，
  所有指令以結束碼 3、`reason: "dependency"` 結束。
- 外部指令：`git`（`rev-parse`、`status`、`for-each-ref`、`merge-base --is-ancestor`、`switch`、`switch -c`）、`claude`（只在 `run`）、
  測試指令（只在 `test`）。`claude` 的位置以 `shutil.which("claude")` 解析；環境變數 `SDD_DRIVE_CLAUDE` 若存在，必須是 JSON 字串陣列，
  以它取代 `claude`（供測試使用，SKILL.md 不提及）。
- **機密**（原則 V）：見 data-model「紀錄」。任何輸出（含 `error`、`detail`、`summary`、測試輸出的末段、`dirty` 的路徑）都不含符合機密樣式的值：
  字串以 `(not shown: looks like a secret)` 取代，路徑以 `(not shown)` 取代。
- Windows 與 Linux 的輸出逐位元組相同（時間、雜湊、session ID、測試輸出這類取決於當下的值除外）。

## 結束碼與 `reason`

| 結束碼 | `reason` | 指令 | 意義 |
|---|---|---|---|
| 0 | | 全部 | 成功（`run` 的子 session 本身失敗時仍是 0，結果在 `outcome`） |
| 1 | `usage` | 全部 | 用法錯誤 |
| 1 | `secret` | `run` | `--reason` 符合機密樣式 |
| 1 | `running` | `run`、`test`、`finalize`、`clear` | 鎖被另一個程序持有（含 driver 等待重置期間），或 `launch` 在 60 秒內 |
| 1 | `not-waiting` | `cancel` | 沒有正在等待重置的 driver |
| 1 | `no-driver` | `watch` | 沒有 driver 在執行，也沒有剛結束而尚未回報的結果（應先 `status`） |
| 1 | `pending-finalize` | `run`、`test` | 有沒有結果的嘗試，需要先 `finalize` |
| 1 | `not-next` | `run`、`test` | 指定的 spec 與階段不是 `status` 的下一步；或 `--resume` 但下一步不是 `resume`；或 `--fresh` 沒有與 `--resume` 的情境對應 |
| 1 | `dirty` | `run`、`test` | 工作區有未提交的變更且不是被中斷的子 session 留下的（`dirty` 列出路徑） |
| 1 | `branch-diverged` | `run` | spec 的分支存在但與目前 HEAD 分岔 |
| 1 | `no-test-command` | `test` | plan.md 沒有可用的測試指令 |
| 1 | `nothing-to-finalize` | `finalize` | 沒有需要 `finalize` 的嘗試 |
| 1 | `conflict` | 讀寫紀錄的指令 | `.specify/sdd-drive/` 有不是本 skill 的檔案 |
| 1 | `os-error` | 寫入的指令 | 無法寫入或無法執行 git 指令；暫存檔已移除，已存在的檔案不變 |
| 3 | `dependency` | 全部 | 相鄰的 sdd-grill 缺少 |
| 3 | `speckit-missing`、`speckit-incomplete` | `status`、`run` | 未導入 Spec Kit，或缺少 `speckit-plan`、`speckit-tasks`、`speckit-implement` 任何一個（`missing` 列出） |
| 3 | `no-specs` | `status` | `specs/` 下沒有任何 spec |
| 3 | `claude-missing` | `status`、`run` | 找不到 `claude` |
| 3 | `state-unreadable` | 讀紀錄的指令（`clear` 除外） | `state.json` 無法解析、不符合結構或機密掃描命中（`detail` 指出欄位路徑；可 `clear`） |

`status` 的 `reason` 依上表由上而下取第一個成立的。`running`、`pending-finalize`、`dirty` 對 `status` 不是錯誤，而是輸出中的欄位。

## status

只讀。輸出：

```json
{
  "speckit": "ok",
  "missing": [],
  "claude": "ok",
  "git": true,
  "branch": "007-sdd-rebuild",
  "own_dir": "ours",
  "running": false,
  "running_attempt": null,
  "driver": null,
  "last_attempt": {"spec": "008-sdd-drive", "phase": "plan", "outcome": "succeeded", "auto": false, "limit": null, "auto_resume": null, "ended_at": "2026-11-21T10:31:12Z"},
  "pending_finalize": false,
  "dirty": [],
  "leftovers": false,
  "specs": [
    {"spec": "007-sdd-rebuild", "state": "done", "next_phase": null, "tasks_total": 77, "tasks_open": 0, "failures": {}},
    {"spec": "008-sdd-drive", "state": "planned", "next_phase": "tasks", "tasks_total": 0, "tasks_open": 0, "failures": {"plan": 1}}
  ],
  "next": {
    "action": "run",
    "spec": "008-sdd-drive",
    "phase": "tasks",
    "branch": "008-sdd-drive",
    "session_id": null,
    "model": null,
    "failures": {"plan": 1},
    "last_outcome": null,
    "test_command": null,
    "hints": {"requirements": 22, "user_stories": 4, "plan_bytes": 15234, "contracts": 2, "tasks_total": 0, "tasks_open": 0,
              "phase_failures": 0, "models_used_this_run": ["opus"]}
  }
}
```

- `running_attempt`：鎖被持有時，紀錄中最後一筆 `outcome: null` 的嘗試（driver 等待重置時則是被中斷的那一筆）的 `spec`、`phase`、`model`、`started_at`、`limit`、`auto_resume`；`next.action` 為 `wait`。
- `driver`：data-model 的 `driver`（`phase`、`waiting_until` 等）；沒有 driver 時 `null`。
- `last_attempt`：最近一筆有結果的嘗試（data-model）；沒有時 `null`。
- `pending_finalize: true` 時 `next.action` 為 `finalize`，`next` 附上該嘗試的 `spec`、`phase`。
- `next.action` 為 `none` 時其餘 `next` 欄位為 `null`。
- `next.action` 為 `resume` 時 `session_id`、`model`、`last_outcome`（`usage-limit`、`api-error`、`interrupted`）有值，另附 `limit`、`auto_resume`。
- `next.action` 為 `test` 時 `test_command` 有值（無法取得時為 `null`，`test` 會回報 `no-test-command`）；另附 `covers`：同一次測試會一併記錄的 spec 清單（D5）。
- `dirty` 不為空且 `leftovers: false` 時，SKILL.md 依 `dirty` 停止（D9）。

## brief

只讀。依 data-model「工作說明」印出純文字的工作說明；不檢查是否為下一步（供人與測試檢視）。`--spec` 不存在時 `usage`。

## run

`run` 是「準備＋啟動 driver＋watch」。準備階段（在鎖內）：

1. 驗證參數與 `--reason`（`secret`）；檢查前置條件（`speckit-*`、`claude-missing`、`conflict`、`state-unreadable`）。
2. 取得鎖（`running`）。
3. 以 `status` 的規則確認下一步：`pending-finalize`；指定的 `--spec`、`--phase` 必須等於 `next`，`next.action` 為 `resume` 時必須帶 `--resume`
   （帶 `--resume --fresh` 表示放棄接續、開新的 session，用於上一次 `resume_failed`），否則 `not-next`。
4. 工作區：有 `dirty` 且不是 `leftovers` → `dirty`。
5. git：依 D11 建立或切換到 spec 的分支（`branch-diverged`）。
6. 把 `.specify/feature.json` 的 `feature_directory` 設為 `specs/<dir>`（保留其他鍵；檔案存在但不是 JSON 物件時改寫為只有這個鍵的物件）。
7. 刪除殘留的 `cancel` 檔案；寫入一筆 `outcome: null` 的嘗試（`auto: false`；新的 `session_id`，或 `--resume` 時沿用）與 `launch` 記號。
8. 以兩層啟動、脫離 session 的方式啟動 `_drive --token <token>`（Linux：中間程序以 `start_new_session=True` 啟動後立即結束；Windows：
   `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`，可用時加 `CREATE_BREAKAWAY_FROM_JOB`；stdin、stdout、stderr 皆接到空裝置），然後釋放鎖。
   無法啟動時清除 `launch`、把嘗試記為 `launch-failed`，輸出結果後結束。

之後與 `watch` 相同（`--minutes` 預設 110），輸出格式見 watch。步驟 1–7 的錯誤以表中的 `reason` 結束（結束碼 1 或 3），不寫入嘗試。

### driver（`_drive`，內部）

1. 以阻塞方式取得鎖（最多 60 秒）並確認 `launch.token` 相符；不符或逾時時直接結束（不寫入）。清除 `launch`、寫入 `driver`（`phase: running`）。
2. 記下受保護檔案的雜湊與 remote-tracking refs。
3. 以 stdin 傳入工作說明，啟動 `claude -p --output-format stream-json --verbose --model <model> (--session-id <id> | --resume <id>) --json-schema <schema>
   --permission-mode acceptEdits --permission-prompts none --allowedTools Bash Skill --disallowedTools AskUserQuestion "Bash(git push*)"`。
   stdout 逐行解析，只保留：`status: "rejected"` 的 `rate_limit_event.rate_limit_info`、assistant 訊息的 `api_error` 與 `api_error_params.rate_limit_info`、
   最後一行 `type: "result"` 的物件；stderr 丟棄。
4. 依 D4 分類；`succeeded` 候選再檢查：該階段的產物、任務編號沒有減少（implement）、受保護檔案未變、remote-tracking refs 未變、git 工作區乾淨；
   第一個不符合的項目成為 `verify-failed` 的 `detail.code`。`usage-limit` 依 D17 計算 `limit`。
5. 寫入結果、`model_used`、`worktree`、（tasks 成功時）`task_ids`、`limit`。
6. 自動接續（D18–D20）：`outcome` 為 `usage-limit` 時——
   - `limit.waitable: false` → `auto_resume: not-waitable`；這筆嘗試 `auto: true` → `already-auto`；兩者都到步驟 7。
   - 否則 `auto_resume: waiting`、`driver.phase: waiting`、`driver.waiting_until = resets_at + 120 秒`；每 30 秒以牆上時鐘檢查一次，
     看到 `cancel` 檔案 → `cancelled`（刪除該檔案）並到步驟 7。
   - 到時：工作區指紋與這筆嘗試的 `worktree` 不同 → `skipped-changed` 並到步驟 7；再檢查一次 `cancel`；否則 `auto_resume: started`、`driver.phase: resuming`，
     寫入新嘗試（`auto: true`、`resume: true`、同一個 `session_id` 與 `model`、`reason: "Automatic resume after the usage limit reset."`），回到步驟 2。
7. 清除 `driver`，釋放鎖，結束。driver 不寫 stdout，不開始其他階段。

## watch

只讀。等待直到下列任一成立，輸出當時的結果後結束（結束碼 0）：driver 結束（`driver` 清除且鎖釋放）；driver 進入 `waiting`（每個等待中的嘗試只回報一次：
啟動 `watch` 時已在等待者，立即回報）；`--minutes` 到時（預設 110，範圍 1–115）；`launch` 超過 60 秒仍未被 driver 取得（`launch-failed`）。
沒有 driver、沒有 `launch`，且最後一筆嘗試已有結果時，回報該筆結果（讓剛結束的 driver 的結果不會遺失）；連嘗試都沒有時 `no-driver`。

輸出：

```json
{
  "status": "finished",
  "attempts": [
    {
      "spec": "008-sdd-drive",
      "phase": "tasks",
      "outcome": "usage-limit",
      "auto": false,
      "counts_as_failure": false,
      "model": "sonnet",
      "model_used": ["claude-sonnet-5-5"],
      "reason": "Breaking an existing design into tasks is mechanical.",
      "session_id": "…",
      "resume": false,
      "resume_failed": false,
      "duration_seconds": 412,
      "summary": "…",
      "failure": null,
      "detail": {"code": "usage-limit", "paths": [], "text": "…"},
      "limit": {"waitable": true, "types": ["five_hour"], "resets_at": "2026-11-21T07:10:00Z", "overage_status": "rejected"},
      "auto_resume": "started",
      "permission_denials": []
    },
    {"spec": "008-sdd-drive", "phase": "tasks", "outcome": "succeeded", "auto": true, "…": "…"}
  ],
  "waiting_until": null,
  "state_after": {"state": "tasked", "next_phase": "implement", "tasks_total": 41, "tasks_open": 41},
  "failures": {"plan": 1}
}
```

- `status`：`finished`（driver 已結束）、`waiting`（driver 正在等待重置；`waiting_until` 有值）、`running`（時間到時子 session 仍在執行）、`launch-failed`。
- `attempts`：這次 driver 的所有嘗試（被中斷的嘗試與自動接續的嘗試），依時間順序；欄位同 data-model，字串已做機密取代。
- `failure` 是子 session 回報的 `{kind, step, reason, tasks}`（`failed` 時）；`permission_denials`：被拒絕的工具名稱（去重，不含參數）。

## cancel

`driver.phase` 不是 `waiting` → `not-waiting`。否則建立 `.specify/sdd-drive/cancel`（已存在視為成功），輸出 `{"cancel_requested": true, "waiting_until": "…"}`。
不取得鎖、不寫 `state.json`；driver 在 30 秒內處理（之後 `watch` 會回報 `auto_resume: cancelled`）。

## test

1. 前置條件與鎖同 `run` 的準備階段（`test` 在自己的程序內執行，不使用 driver）；`--spec` 必須是 `next.action: test` 的 spec（`not-next`）；`pending-finalize`、`dirty` 同 `run`。
2. 從 `specs/<dir>/plan.md` 的 `**Testing**:` 行取第一個反引號區段（D6）。沒有、空白、或內容是 `N/A`、`none`、`TBD`（不分大小寫）→ `no-test-command`。
   指令符合機密樣式 → 不執行，`no-test-command`，`detail` 說明原因而不含值。
3. 以 shell 在專案根目錄執行，stdin 為空；不設逾時（由主 session 的 Bash 背景執行上限決定）。
4. 結束碼 0 → 為 `covers` 中的每一份 spec 寫入一筆 `exit_code: 0` 的測試紀錄；非 0 → 只為 `--spec` 寫入一筆。

輸出：

```json
{"spec": "007-sdd-rebuild", "command": "uv run --with pytest pytest", "exit_code": 0, "passed": true,
 "covers": ["001-deploy-tool", "002-global-claude-md"], "duration_seconds": 95, "output_tail": ["…"]}
```

`output_tail`：合併的 stdout 與 stderr 最後 40 行，每行先做機密掃描。

## finalize

前提：鎖未被持有，且最後一筆嘗試 `outcome: null`、`driver` 不為 `null`，或 `launch` 已超過 60 秒（否則 `running` 或 `nothing-to-finalize`）。
`outcome: null` 的嘗試記為 `interrupted`（`detail.code: "no-result"`），寫入目前的工作區指紋；`auto_resume: waiting` 的嘗試改為 `lost`；`launch` 與 `driver` 清除。輸出該嘗試的 `spec`、`phase`、`model`、`started_at` 與 `state_after`（依檔案重新計算）。

## clear

鎖未被持有且沒有 `driver`、`launch` 時，刪除本 skill 的四個檔案與變空的資料夾；`own_dir` 為 `conflict` 時不刪除任何檔案（`conflict`）。不存在的檔案視為已刪除。
輸出 `{"cleared": true}`。
