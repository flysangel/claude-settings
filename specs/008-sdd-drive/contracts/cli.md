# Contract: sdd_drive.py 的指令介面

```text
uv run <skill>/scripts/sdd_drive.py status                                   前置條件、每份 spec 的狀態、下一步（只讀）
uv run <skill>/scripts/sdd_drive.py brief    --spec <dir> --phase <phase>    印出交給子 session 的工作說明（只讀）
uv run <skill>/scripts/sdd_drive.py run      --spec <dir> --phase <phase> --model <model> --reason <text> [--resume] [--fresh]
                                                                             啟動一個子 session 執行該階段，等它結束、檢查、記錄
uv run <skill>/scripts/sdd_drive.py test     --spec <dir>                    親自執行該 spec 的測試指令並記錄
uv run <skill>/scripts/sdd_drive.py finalize                                 把沒有結果的嘗試記為 interrupted
uv run <skill>/scripts/sdd_drive.py clear                                    刪除本 skill 的紀錄
```

`<skill>` 是 skill 的資料夾，SKILL.md 以 `${CLAUDE_SKILL_DIR}` 表示。一律在目標專案的根目錄執行（目前目錄）。`<dir>` 是 `specs/` 下的資料夾名稱
（例如 `008-sdd-drive`），`<phase>` 是 `plan`、`tasks`、`implement`。子指令不認得、缺少或多出參數時，結束碼 1，`reason: "usage"`。

資料格式見 [data-model.md](../data-model.md)；決定與理由見 [research.md](../research.md)。

## 共通

- stdout 只有一份 JSON 物件（UTF-8、LF、縮排 2、`ensure_ascii=False`、結尾換行），鍵的順序固定；路徑相對於專案根目錄、以 `/` 分隔。
  例外：`brief` 印出純文字的工作說明。
- 失敗時 JSON 有 `"error": "<一句英文>"` 與 `"reason": "<列舉值>"`，同一句 `error` 也寫到 stderr。SKILL.md 依 `reason` 分支。
- **寫入範圍**：`status`、`brief` 不寫入任何檔案。`run` 寫 `.specify/sdd-drive/`、`.specify/feature.json`，並在需要時建立或切換 git 分支（D11）；
  其餘的專案檔案只由子 session 修改。`test` 只寫 `.specify/sdd-drive/`（測試指令本身可能寫入專案自己的暫存檔，不在本 skill 的控制內）。
  `finalize` 只寫 `.specify/sdd-drive/state.json`。`clear` 只刪除本 skill 的三個檔案與變空的資料夾。寫入一律「同資料夾的暫存檔再取代」。
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
| 1 | `running` | `run`、`test`、`finalize`、`clear` | 鎖被另一個程序持有 |
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

- `running_attempt`：鎖被持有時，紀錄中最後一筆 `outcome: null` 的嘗試的 `spec`、`phase`、`model`、`started_at`；`next.action` 為 `wait`。
- `pending_finalize: true` 時 `next.action` 為 `finalize`，`next` 附上該嘗試的 `spec`、`phase`。
- `next.action` 為 `none` 時其餘 `next` 欄位為 `null`。
- `next.action` 為 `resume` 時 `session_id`、`model`、`last_outcome`（`usage-limit`、`api-error`、`interrupted`）有值。
- `next.action` 為 `test` 時 `test_command` 有值（無法取得時為 `null`，`test` 會回報 `no-test-command`）；另附 `covers`：同一次測試會一併記錄的 spec 清單（D5）。
- `dirty` 不為空且 `leftovers: false` 時，SKILL.md 依 `dirty` 停止（D9）。

## brief

只讀。依 data-model「工作說明」印出純文字的工作說明；不檢查是否為下一步（供人與測試檢視）。`--spec` 不存在時 `usage`。

## run

依序：

1. 驗證參數與 `--reason`（`secret`）；檢查前置條件（`speckit-*`、`claude-missing`、`conflict`、`state-unreadable`）。
2. 取得鎖（`running`）；之後任何結束都釋放鎖。
3. 以 `status` 的規則確認下一步：`pending-finalize`；指定的 `--spec`、`--phase` 必須等於 `next`，`next.action` 為 `resume` 時必須帶 `--resume`
   （帶 `--resume --fresh` 表示放棄接續、開新的 session，用於上一次 `resume_failed`），否則 `not-next`。
4. 工作區：有 `dirty` 且不是 `leftovers` → `dirty`。
5. git：依 D11 建立或切換到 spec 的分支（`branch-diverged`）。
6. 把 `.specify/feature.json` 的 `feature_directory` 設為 `specs/<dir>`（保留其他鍵；檔案存在但不是 JSON 物件時改寫為只有這個鍵的物件）。
7. 記下受保護檔案的雜湊與 remote-tracking refs；寫入一筆 `outcome: null` 的嘗試（新的 `session_id`，或 `--resume` 時沿用）。
8. 以 stdin 傳入工作說明，啟動 `claude -p --output-format json --model <model> (--session-id <id> | --resume <id>) --json-schema <schema>
   --permission-mode acceptEdits --permission-prompts none --allowedTools Bash Skill --disallowedTools AskUserQuestion "Bash(git push*)"`，
   等待結束；stdout 只解析結果物件，stderr 丟棄。
9. 依 D4 分類；`succeeded` 候選再檢查：該階段的產物（plan 已產生、tasks 已產生、implement 的任務全部勾選）、任務編號沒有減少（implement）、
   受保護檔案未變、remote-tracking refs 未變、git 工作區乾淨。第一個不符合的項目成為 `verify-failed` 的 `detail.code`。
10. 寫入結果、`model_used`、`worktree`、（tasks 成功時）`task_ids`；印出輸出。

輸出（結束碼 0）：

```json
{
  "spec": "008-sdd-drive",
  "phase": "tasks",
  "outcome": "succeeded",
  "counts_as_failure": false,
  "model": "sonnet",
  "model_used": ["claude-sonnet-5-5"],
  "reason": "Breaking an existing design into tasks is mechanical.",
  "session_id": "…",
  "resume": false,
  "resume_failed": false,
  "duration_seconds": 412,
  "summary": "Generated tasks.md with 41 tasks.",
  "failure": null,
  "detail": null,
  "permission_denials": [],
  "state_after": {"state": "tasked", "next_phase": "implement", "tasks_total": 41, "tasks_open": 41},
  "failures": {"plan": 1}
}
```

- `failure` 是子 session 回報的 `{kind, step, reason, tasks}`（`failed` 時）。
- `permission_denials`：被拒絕的工具名稱（去重，不含參數）。
- 步驟 2–7 之前的錯誤以表中的 `reason` 結束（結束碼 1 或 3），不寫入嘗試。

## test

1. 前置條件與鎖同 `run`；`--spec` 必須是 `next.action: test` 的 spec（`not-next`）；`pending-finalize`、`dirty` 同 `run`。
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

前提：鎖未被持有、最後一筆嘗試 `outcome: null`（否則 `running` 或 `nothing-to-finalize`）。把它記為 `interrupted`（`detail.code: "no-result"`），
寫入目前的工作區指紋。輸出該嘗試的 `spec`、`phase`、`model`、`started_at` 與 `state_after`（依檔案重新計算）。

## clear

鎖未被持有時，刪除本 skill 的三個檔案與變空的資料夾；`own_dir` 為 `conflict` 時不刪除任何檔案（`conflict`）。不存在的檔案視為已刪除。
輸出 `{"cleared": true}`。
