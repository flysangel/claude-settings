# Research: sdd-drive

**Feature**: `008-sdd-drive` | **Date**: 2026-11-21

本檔前半是實測紀錄（E1–E8），後半是決策（D1–D16）、對既有經驗的處理（O1–O8）與需要維護者核可的設計取捨（T1–T8）。

## 實測紀錄：只用 Claude Code 開子 session 的機制

環境：Linux，`claude --version` 為 `2.1.319 (Claude Code)`。實驗一律在 `mktemp -d` 建立的假專案（`git init` 後只放一個
示範 skill）進行，使用 `--model haiku` 與最小提示；沒有在本 repo 啟動任何會修改檔案的子 session。

### E1. `claude --help` 中與子 session 相關的選項（實際輸出摘錄）

| 選項／子指令 | 說明（摘自 help） | 與本 spec 的關係 |
|---|---|---|
| `-p, --print` | 非互動，印出回應後結束；非互動時略過 workspace trust 對話框 | 無頭子 session 的基礎 |
| `--model <model>` | 別名（`fable`、`opus`、`sonnet`）或完整名稱 | FR-019 指定模型 |
| `--output-format json` | 只在 `--print` 時有效，輸出單一結果物件 | 主 session 以腳本判讀結果 |
| `--json-schema <schema>` | `--print` 時以 JSON Schema 驗證結構化輸出 | 可要求子 session 依格式回報（未採用，見決策） |
| `-r, --resume [value]` | 以 session ID 或名稱接續對話 | FR-022 從中斷處接續 |
| `--session-id <uuid>` | 指定 session ID | 可預先決定 ID，啟動前就能記錄 |
| `--no-session-persistence` | 不存檔、無法 resume（只在 `--print`） | 本 skill MUST NOT 使用，否則不能接續 |
| `--permission-mode <mode>` | `acceptEdits`、`auto`、`bypassPermissions`、`manual`、`dontAsk`、`plan` | 子 session 的權限 |
| `--permission-prompts <target>` | `--print` 時由 `host` 或 `none` 回答權限提示；`none` 代表會提示的一律拒絕 | 無頭時不會卡在提示 |
| `--allowedTools` / `--disallowedTools` | 允許／拒絕的工具與樣式，例如 `Bash(git *)` | 禁止 `git push` 等 |
| `--max-budget-usd <amount>` | `--print` 時的花費上限 | 未採用（個人訂閱用量不是以金額計） |
| `--effort <level>` | `low` 到 `max` | 可與模型一起依工作性質調整 |
| `--bg, --background` 與 `claude agents`、`attach`、`logs`、`stop`、`rm` | 背景 session 與管理指令 | 互動式背景 session，輸出是終端畫面而非結構化結果（未採用） |
| `-w, --worktree` | 為 session 建立 git worktree | 未採用（見決策） |

`claude agents --help` 另有 `--json`（列出執行中的 session，供腳本使用）、`--model`、`--permission-mode` 等，作用對象是
agent view 派出的互動式背景 session。

### E2. 無頭子 session 能以 Skill 工具呼叫專案內的 skill，並寫入檔案

假專案的 `.claude/skills/hello/SKILL.md` 要求建立內容為 `PONG` 的 `pong.txt`。

```text
claude -p "Use the Skill tool to invoke the hello skill." --model haiku --output-format json \
  --permission-mode acceptEdits --max-budget-usd 0.2 --no-session-persistence
```

觀察：結束碼 0；`pong.txt` 內容為 `PONG`；結果物件的重要欄位：

- `type: "result"`、`subtype: "success"`、`is_error: false`、`terminal_reason: "completed"`、`stop_reason: "end_turn"`
- `api_error_status: null`、`permission_denials: []`、`num_turns: 4`、`result: "DONE"`（子 session 最後一則回覆的文字）
- `session_id`（UUID，可供 `--resume`）
- `modelUsage` 以實際模型為鍵：`{"claude-haiku-5-5": {...}}`，可據此確認子 session 真的使用了指定的模型（FR-020）
- `subagent_stats`、`total_cost_usd`、`duration_ms` 等統計
- stderr 有一行 `Warning: no stdin data received in 3s, proceeding without it...`：以程式啟動時 stdin MUST 接到空輸入（`< /dev/null`
  或 subprocess 的 `stdin=DEVNULL`），否則每次多等 3 秒並產生雜訊。

結論：子 session 能使用 Skill 工具，`speckit-plan`、`speckit-tasks`、`speckit-implement` 與示範 skill 一樣位於專案的
`.claude/skills/`，以相同方式呼叫（FR-006 可滿足）。

### E3. API 錯誤時的結果物件（以不存在的模型觸發）

```text
claude -p "hi" --model not-a-model --output-format json --no-session-persistence </dev/null
```

觀察：結束碼 1；stdout 仍是一個完整的結果物件：`is_error: true`、`subtype: "success"`（注意：錯誤時 `subtype` 仍可能是
`success`，不能只看它）、`terminal_reason: "api_error"`、`api_error_status: 404`、`result` 為錯誤說明文字、`modelUsage: {}`；
stderr 有 `[claude-code:unrecognized_model] ...`。

### E4. 預算用盡時的結果物件

```text
claude -p "Reply OK" --model haiku --output-format json --max-budget-usd 0.0001 --no-session-persistence </dev/null
```

觀察：結束碼 1；`subtype: "error_max_budget_usd"`、`is_error: true`、`terminal_reason: "budget_exhausted"`、
`api_error_status: null`、`result: null`。

### E5. 由實測推得的判讀規則與未能實測的部分

- 結果物件一律在 stdout，與結束碼一起足以分辨：正常結束（`is_error: false`）、API 錯誤（`terminal_reason: "api_error"` 與 HTTP 狀態碼
  `api_error_status`）、其他非正常結束（`subtype` 以 `error_` 開頭或 `terminal_reason` 不是 `completed`）。
- **用量上限無法在實測中觸發**（需要真的用完額度；重置時間的取得見 E9、E10，2026-11-21 補查）。依 E3 的欄位，用量上限屬於 API 錯誤，預期 `terminal_reason: "api_error"` 且
  `api_error_status: 429`；`result` 的文字會提到 limit 與重設時間。這一點列為人工驗收項目，判讀規則的設計見決策 D4：
  即使判讀錯誤，也只會落在「中斷」而不是「失敗」，FR-021 的行為不變。
- stdout 沒有可解析的結果物件（程序被終止、當機、Bash 工具逾時）視為「沒有回報就結束」。

### E6. 以 session ID 接續（`--session-id` 與 `--resume`）

```text
claude -p "Remember the word KIWI. Reply OK." --model haiku --output-format json --session-id <uuid> </dev/null
claude -p "What word did I ask you to remember? Reply with the word only." --model haiku --output-format json --resume <uuid> </dev/null
```

觀察：兩次結束碼皆為 0；兩次的 `session_id` 都等於預先指定的 UUID；第二次回答 `KIWI`，證明 `--resume` 帶回了第一次的對話內容，
且可以與 `--model` 一起使用。因此腳本可以在啟動前產生 UUID 並寫入紀錄，即使子 session 中途被終止、沒有輸出結果物件，
下一次也能以同一個 ID 接續（FR-022）。

### E7. 其他機制（未實際啟動，依本 session 可見的工具定義與 help）

- **Agent 工具（subagent）**：參數有 `model`（`sonnet`、`opus`、`haiku`、`fable`）、`run_in_background`（完成時通知主 session）、
  `subagent_type`；完成後只把最終回報放進主 session 的上下文；同一個主 session 內可用 SendMessage 接續。它沒有結構化的結束狀態欄位，
  主 session 重新開始（新的對話）後無法接續先前的 subagent。
- **`claude --bg` 與 `claude agents`**：互動式的背景 session，`logs` 取得的是終端畫面文字，不是結構化結果；適合人操作，不適合腳本判讀。
- **skill frontmatter 指定在 subagent 執行或指定模型**：本專案 `speckit-*` 的 frontmatter 只有 `name`、`description`、
  `user-invocable`、`disable-model-invocation` 等欄位；是否支援其他欄位未查證，且 sdd-drive 不能修改 `speckit-*`（constitution 原則 I），
  所以不採用這條路。

### E8. 結構化回報（`--json-schema`）與以 stdin 傳入提示

```text
echo "Report status completed with summary 'nothing to do'." | claude -p --model haiku --output-format json \
  --no-session-persistence --json-schema '{"type":"object","properties":{"status":{"type":"string","enum":["completed","failed"]},"summary":{"type":"string"}},"required":["status","summary"]}' \
  --disallowedTools AskUserQuestion "Bash(git push*)"
```

觀察：結束碼 0；結果物件多了 `structured_output: {"status": "completed", "summary": "nothing to do"}`，`result` 是同一份 JSON 的字串。
提示可以從 stdin 傳入（不受 Windows 命令列長度限制、不必處理引號）。另一個觀察：`--disallowedTools`、`--allowedTools` 是可變長度參數，
第一次把提示放在它們後面時被當成工具名稱吃掉，`claude` 回報 `Input must be provided either through stdin or as a prompt argument`；
因此提示一律走 stdin，參數順序由腳本固定。

### E9. 用量上限的結構化資訊與重置時間（2026-11-21 為 FR-021 修訂補查）

標示：**實測**＝在本機實際執行觀察到；**程式內容**＝以 `strings` 讀取已安裝的 `claude` 2.1.319 執行檔（`~/.local/share/claude/versions/2.1.319`）
中的程式文字，是這個版本實際會執行的邏輯，但不是公開文件、可能隨版本改變；**推測**＝由前兩者推論、未能直接觀察。
公開文件與 `claude --help` 都沒有提到重置時間的欄位（**實測**：help 中沒有相關選項）。

1. **實測**：`echo "Reply OK" | claude -p --model haiku --output-format stream-json --verbose --no-session-persistence` 的輸出中有一行
   `type: "rate_limit_event"`：

   ```json
   {"rate_limit_info": {"status": "allowed", "resetsAt": 1795264800, "rateLimitType": "five_hour",
     "overageStatus": "rejected", "overageDisabledReason": "org_level_disabled_until", "isUsingOverage": false,
     "unifiedWindows": {"five_hour": {"utilization": 0.6, "resetsAt": 1795264800, "status": "allowed"},
                        "seven_day": {"utilization": 0.41, "resetsAt": 1795741200, "status": "allowed"}}}}
   ```

   `resetsAt` 是 Unix 時間（秒），每個時間窗各有 `status` 與 `resetsAt`。`--output-format json`（單一結果物件）沒有這個資訊；最後一行仍是與 E2 相同的 `result` 物件。
2. **程式內容**：請求被用量上限拒絕時，該則 assistant 訊息帶 `api_error: "usage_limit_reached"` 與
   `api_error_params.rate_limit_info`，說明為「what the refused request's own response said about the limit, in the shape rate_limit_event carries
   … its status, limit and reset are the text's: status is rejected」。資訊來自 API 回應標頭 `anthropic-ratelimit-unified-status`、
   `anthropic-ratelimit-unified-reset`、`anthropic-ratelimit-unified-overage-status` 等。`rateLimitType` 的值有 `five_hour`、`seven_day`、
   `seven_day_opus`、`seven_day_sonnet`、`seven_day_overage_included`、`overage`；另有 `dailyCapPaused`、`overageResetsAt`。
3. **程式內容**：訊息文字由這些欄位組成，例如 `You've hit your ${名稱}`、`You've hit your monthly spend limit · raise it at …`，
   有時間窗資訊時再接 ` · your ${limitName} resets ${resetTime}`；`resetTime` 是只有時刻與時區名稱的可讀文字（例如 `3:10pm (Asia/Taipei)`），
   沒有日期。維護者看過的訊息 `You've hit your monthly spend limit · raise it at … · your 5-hour limit resets 3:10pm (Asia/Taipei)`
   就是「額外用量（overage）被拒絕＋5 小時時間窗用完」的組合：時間窗重置後就回到方案內的額度，不再需要額外用量。
4. **推測**：無頭的 `claude -p` 被用量上限拒絕時，stream-json 會有 `status: "rejected"` 的 `rate_limit_event`，以及帶
   `api_error_params.rate_limit_info` 的 assistant 訊息（第 2 點的程式文字明說兩者形狀相同）；最後的 `result` 為 `is_error: true`、
   `api_error_status: 429`。無法在不耗盡額度的情況下實測，列為人工驗收。
5. **程式內容**：互動式的 Claude Code 內建「Continue automatically at usage limit」（設定 `autoContinueAtUsageLimit`，預設 `true`）：
   主 session 自己被用量上限擋下時，於重置後自動送出「You can continue now. Continue the task you were working on when the usage limit was reached;
   do not repeat work that is already complete.」繼續原本的工作。條件包括：以 claude.ai 帳號登入、計費方式不是 `usage_based`、遠端功能開關未關閉、
   重置時間在 24 小時內（否則顯示 `the usage limit now resets more than 24 hours out, so this task will not resume on its own`）、
   連續自動繼續有次數上限（更新紀錄：修正了「continuing more than three times without a prompt from you」）；Claude Code 在等待期間結束或重新啟動時
   不會繼續（`Claude Code exited during the wait, so the task will not resume on its own`）。這是主 session 的機制，不作用在 `claude -p` 子 session。
6. **程式內容**：`CronCreate` 這類排程工具的說明寫明「Jobs live only in this Claude session — nothing is written to disk」「Jobs only fire while the REPL is idle」；
   本 session（Orca 內的 Claude Code）可見，但在一般的 Claude Code 是否預設提供未查證。`ScheduleWakeup` 只在 `/loop` 的動態模式可用。
   Bash 工具的背景執行上限 7200000 ms（2 小時），`Monitor` 上限 1 小時（**實測**：本 session 的工具定義）。

### E10. 由 E9 推得的判斷：「等到重置就能繼續」或「等也沒用」

- 有用的資訊只有結構化的 `rate_limit_info`；訊息文字沒有日期與可靠的格式，**不解析文字**。
- 等待有用：`status` 為 `rejected`，且被拒絕的原因是時間窗：`unifiedWindows` 中 `status: "rejected"` 的時間窗至少一個、每一個都有 `resetsAt`
  → 重置時間取它們的最大值；沒有 `unifiedWindows` 時，`rateLimitType` 屬於 `five_hour`、`seven_day`、`seven_day_opus`、`seven_day_sonnet`
  且有 `resetsAt` → 取 `resetsAt`。
- 等也沒用（停止）：`rateLimitType` 為 `overage`、`seven_day_overage_included` 或沒有；`dailyCapPaused: true`；被拒絕的時間窗缺 `resetsAt`；
  沒有任何 `rate_limit_info`（只有文字或只有 429）；欄位不合格式；重置時間早於子 session 開始的時間（資訊自相矛盾）。
  也就是說，判斷不出來一律歸為「等也沒用」。
- 維護者的例子（花費上限＋5 小時時間窗）：被拒絕的時間窗是 `five_hour`、有 `resetsAt` → 等待有用；花費上限本身沒有重置時間，但時間窗重置後就不需要它。

### E11. 等待的行程能否在 Bash 背景指令被終止後存活（Linux 實測）

以 Bash 工具的 `run_in_background: true`、很短的 `timeout`（6–8 秒）執行一支 Python，讓它啟動子程序後自己睡 300 秒，等 Claude Code 在時限到時終止它：

| 啟動方式 | 結果（**實測**） |
|---|---|
| 一般子程序（同一個行程群組） | 被終止 |
| `start_new_session=True`（新的 session／行程群組，父程序仍在） | **也被終止**：Claude Code 終止的是整個子孫行程樹，不只行程群組 |
| 兩層啟動：中間程序以 `start_new_session=True` 啟動孫程序後立刻結束，孫程序被系統收養 | **存活**，25 秒後如期寫入檔案 |

結論：等待的行程要用「兩層啟動並脫離 session」才能撐過 Bash 背景執行的 2 小時上限；這樣啟動的行程也會在維護者關閉終端機或結束 Claude Code 後繼續存在（**推測**：已脫離終端機的 session，不會收到 SIGHUP）。
Windows 上對應的做法是 `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`（必要時加 `CREATE_BREAKAWAY_FROM_JOB`）的兩層啟動；**Claude Code 在 Windows 如何終止背景指令未查證**
（若以不允許脫離的 job object 管理，孫程序仍可能被終止），列為人工驗收與風險（T10）。電腦休眠時行程暫停，醒來後以牆上時鐘判斷是否已過重置時間（**推測**，屬一般作業系統行為）。

### E12. `speckit-converge` 的實際行為（2026-11-21 為 FR-023、FR-024 補查；讀取 `.claude/skills/speckit-converge/SKILL.md`，Spec Kit 1.4.2）

- 前置：以 `check-prerequisites.sh --json --require-spec --require-tasks --include-tasks` 取得目前的功能（依 `.specify/feature.json`）；`spec.md`、`plan.md`、`tasks.md`
  任一缺少就停止並指出要先執行的指令。只應在 `speckit-implement` 對目前的 `tasks.md` 執行過之後使用。
- 依據：只以 spec、plan、tasks（與 constitution）為意圖來源；「completion claims are not evidence」，已勾選的任務也重新對照程式；不看 git 歷史。
- **唯一的寫入**：在 `tasks.md` **末尾**附加一個 `## Phase N: Convergence` 段落（N 為最大階段編號＋1），每個發現一行
  `- [ ] T{M+1:03d} <imperative description> per <source-ref> (<gap-type>)`，`M` 為既有最大任務編號，`<gap-type>` 為 `missing`、`partial`、`contradicts`、`unrequested`，
  constitution 違反排第一並標 `CRITICAL`。先前的 Convergence 段落不動，另起新的段落。
- MUST NOT 修改 `spec.md`、`plan.md`；MUST NOT 改寫、重新編號、重排或刪除既有任務；MUST NOT 建立、修改或刪除程式碼。
- **沒有發現**：`tasks.md` **逐位元組不變**（不留空的段落標題），回報「Converged」。
- 會在對話中輸出發現的摘要表；不會 commit（skill 本身沒有提到 git）。`unrequested`（多做的工作）也會成為附加的任務。
- 結論：「有沒有漏做」可以完全由檔案判定（`tasks.md` 是否在原內容之後多了 Convergence 段落），不需要採信子 session；FR-023、FR-024 都能可靠達成。

## 決策

### D1. 開子 session 的機制：腳本以 `claude -p` 啟動無頭 session，主 session 以 Bash 背景執行該腳本

> 2026-11-21 修訂（FR-021 自動接續）：輸出格式改為 `--output-format stream-json --verbose`（取得 `rate_limit_info`，D17）；子 session 改由脫離的 driver 行程啟動、主 session 以 `watch` 等待（D18）。下文其餘理由不變。

- **Decision**：腳本 `sdd_drive.py run` 以 subprocess 啟動 `claude -p`（`--output-format json`、`--model`、`--session-id` 或 `--resume`、
  `--json-schema`、權限參數，提示由 stdin 傳入），等它結束後判讀結果物件、檢查檔案狀態、寫入紀錄，最後在 stdout 印出一份精簡的 JSON。
  主 session 依 SKILL.md 以 Bash 工具的 `run_in_background: true`（`timeout` 設為上限 7200000 ms）執行這個指令，結束時由 Claude Code
  通知主 session，主 session 只讀這份精簡的 JSON。
- **Rationale**：
  - FR-019：`--model` 可指定模型，結果的 `modelUsage` 可確認實際使用的模型（E2）。
  - FR-006：無頭 session 能以 Skill 工具呼叫專案 `.claude/skills/` 的 skill（E2）。
  - FR-021：結果物件有 `is_error`、`terminal_reason`、`api_error_status`，可由腳本決定性地分類（E3、E4、D4）；沒有結果物件也能判定（E5）。
  - FR-022：`--session-id` 讓腳本在啟動前就把 ID 記下，中斷後以 `--resume` 接續同一段對話（E6），即使主 session 已經是新的對話。
  - 上下文：子 session 的完整輸出不進入主 session，主 session 只看到腳本整理後的數行 JSON；結構化回報（E8）不必從自然語言猜測結果。
  - FR-013、SC-006：只用 `claude` 本身與 uv；原則 II：`claude` 與 Python subprocess 在兩個平台都可用，啟動指令由腳本組成，
    主 session 不必依平台寫不同的 shell 指令。
  - 可測性：啟動、判讀、檢查與紀錄全在腳本內，CI 以假的 `claude`（環境變數 `SDD_DRIVE_CLAUDE` 指定的指令）覆蓋每一種結果。
- **Alternatives considered**：
  - **Agent 工具的 subagent**：能指定模型、能背景執行，但結束狀態不是結構化的（用量上限只能從文字猜）、主 session 換成新的對話後無法接續，
    且啟動與判讀都在 Claude 的判斷裡，無法以單元測試覆蓋。不採用。
  - **`claude --bg` 與 `claude agents`**：互動式背景 session，結果是終端畫面文字；不採用。
  - **由主 session 直接在 Bash 寫 `claude -p ...`**：命令列冗長、兩個平台的引號與重新導向寫法不同、結果判讀落在 Claude 身上；不採用。

### D2. 每個階段一個子 session

- **Decision**：每份 spec 的 plan、tasks、implement 各由一個子 session 執行；主 session（依 SKILL.md）在它們之間以腳本重新判定狀態再決定下一個。
- **Rationale**：FR-019 要求每次開子 session 前依「該階段」的工作性質選模型，一個 session 跑三個階段就只能用一個模型；
  失敗定位到單一階段；每個子 session 的上下文從乾淨開始，長的 implement 不會被前面的 plan 對話佔用；中斷後以該階段的 session ID 接續，範圍明確；
  FR-008 的「確認完成才往下」在每個階段之後都由主 session 以腳本檢查，而不是讓子 session 自己決定繼續。
- **Alternatives considered**：一個子 session 依序處理全部 spec（spec 的 User Story 1 的字面描述）：模型無法逐階段選擇、子 session 自己判定完成
  違反 FR-007 的精神、中斷時要接續的對話過長；一個子 session 跑完一份 spec 的三個階段：同樣無法逐階段選模型。spec 的「子 session 依編號一次處理一份」
  在本設計中由「同時只有一個子 session、依編號與階段順序啟動」滿足（FR-003）。見設計取捨 T1。

### D3. 模型的選擇：主 session 逐次判斷，腳本提供規模資訊並記錄

- **Decision**：
  - `run` 必須帶 `--model <alias 或完整名稱>` 與 `--reason <一句英文理由>`；缺少時以 `usage` 拒絕。腳本不內建對應表（spec 的 Assumptions）。
  - `status` 的 `next` 附上 `hints`：該 spec 的 FR 數、User Story 數、plan 與 contracts 的大小、任務總數與未完成數、該階段先前的失敗次數、
    本次流程已使用過的模型。主 session 依 SKILL.md 的準則判斷：
    - plan：需要調查與設計判斷，預設較強的模型（`opus`）；規模很小、無新技術決定時可降為 `sonnet`。
    - tasks：把既有設計拆成任務，偏機械性，預設 `sonnet`。
    - implement：依任務數與性質，以機械性的修改為主時 `sonnet`，需要新設計或先前失敗時 `opus`。
    - 不預設使用最強的別名（`fable`）；要用時理由必須說明為何較便宜的模型不夠。整批流程中 MUST NOT 每一個子 session 都用最強的模型（SC-008）。
    - 接續（`--resume`）時沿用該 session 的模型，理由寫明「resuming the interrupted session」。
  - 腳本把要求的模型、結果的 `modelUsage` 鍵（實際模型）與理由寫進紀錄並在 `run` 的輸出列出；主 session 的每個階段回報都寫出這兩項（FR-020）。
- **Rationale**：模型可用性隨帳號與時間變化，把選擇留給讀得到最新情況的主 session；腳本負責可計算的部分與證據（實際模型）。
- **Alternatives considered**：腳本依規模自動選模型：等於固定對應表，spec 明言不規定；一律 `opus`：違反 FR-019。

### D4. 結果的分類（`run` 的 `outcome`）

> 2026-11-21 修訂：`usage-limit` 的下一步改為「可等待時由 driver 在重置後自動接續一次」，見 D17–D21。分類規則本身不變；`usage-limit` 另依 `rate_limit_info` 判斷是否可等待。

| `outcome` | 判定（依序取第一個成立的） | 計入失敗 | 下一次 `/sdd-drive` |
|---|---|---|---|
| `launch-failed` | 找不到 `claude` 或無法啟動程序 | 否 | 重新檢查前置條件 |
| `usage-limit` | 有結果物件、`is_error: true`，且 `api_error_status` 為 429，或 `result` 文字符合用量上限樣式（`usage limit`、`hit your limit`、`rate limit`，不分大小寫） | 否 | 以 `--resume` 接續同一 session |
| `api-error` | 有結果物件、`is_error: true`，其餘情況（例如 401、404、5xx、`error_max_turns`） | 否 | 以 `--resume` 接續；`resume_failed` 時開新的 |
| `interrupted` | 沒有可解析的結果物件（程序被終止、Bash 逾時、當機），或結果沒有 `structured_output` | 否 | 先 `finalize` 回報，再下一次以 `--resume` 接續 |
| `failed` | `structured_output.status` 為 `failed` | 是 | 從同一階段重試（US4-3） |
| `verify-failed` | 子 session 回報完成，但檔案狀態不符（D7、D9、D10） | 是 | 從同一階段重試 |
| `succeeded` | 回報完成且檔案狀態相符 | — | 下一個階段 |

- 用量上限的樣式無法實測（E5）。分類錯誤時最壞的結果是落在 `api-error` 或 `interrupted`：三者都不計入失敗、都保留進度、都停止且不自動重試，
  差別只在回報的文字，FR-021 的行為不變。
- `--resume` 本身失敗（session 不存在，例如換了機器）時，`run` 的輸出 `resume_failed: true`（結果 `is_error` 且 `num_turns` 為 0 或結束碼非零且沒有結果）；
  SKILL.md 指示以新的 session 重跑該階段，不計入失敗。

### D5. 進度的判定（FR-011）與「未填寫的範本」（FR-007）

每份 spec 的狀態每次都由檔案重新計算，紀錄檔只補充檔案表達不了的事實（測試是否通過、失敗次數、可接續的 session）：

- plan 已產生：`plan.md` 存在、正規化換行後不等於 `.specify/templates/plan-template.md`，且第一個 `# ` 標題不含範本的佔位字串 `[FEATURE]`
  （`setup-plan.sh` 會先複製範本，只有被填寫後才算）。
- tasks 已產生：`tasks.md` 存在、不等於 `tasks-template.md`、第一個標題不含 `[FEATURE NAME]`，且至少有一行任務（`- [ ] T001` 或 `- [x] T001` 形式）。
- 實作進度：任務行中勾選與未勾選的數量。
- 完成：任務全部勾選，**且**紀錄中有這份 spec 在目前 `tasks.md` 內容（雜湊）下的測試通過紀錄（D6）。`tasks.md` 之後被改動時需要重新測試。
- 狀態值與下一步見 data-model。之前的 spec 已完成（例如本 repo 的 001–007）但沒有測試紀錄時，下一步是 `test`；同一次測試可替連續、
  測試指令相同的多份 spec 記錄通過，避免重複執行整套測試。

### D6. 測試指令的來源與執行者

- **Decision**：測試指令取自該 spec 的 `plan.md` 中 `**Testing**:` 那一行的第一個反引號區段（本專案 001–007 的 plan 都符合，例如 `uv run --with pytest pytest`）。
  plan 階段的工作說明要求子 session 把可直接執行、兩個平台寫法相同的指令放在那裡。主 session 執行 `sdd_drive.py test --spec <dir>`，
  由腳本以 shell 執行該指令（Linux 為 `/bin/sh`、Windows 為 `cmd.exe`），只依結束碼判定，紀錄只存結束碼與 `tasks.md` 的雜湊。
- 沒有 `**Testing**:` 行、該行沒有反引號區段，或區段內容是 `N/A` 之類的佔位：`reason: "no-test-command"`，主 session 回報並停止（Edge Case「沒有可執行的測試」），
  不判定為完成，不計入失敗。
- 子 session 的說法不採信：implement 的子 session 被要求自己跑測試，但完成與否只看腳本親自執行的結果（FR-007）。
- 輸出：`test` 只在 stdout 回傳最後 40 行輸出供主 session 回報原因；每一行先以機密樣式掃描，命中的行以 `(line not shown: looks like a secret)` 取代；不寫入檔案。
- **Alternatives**：由主 session 依專案自行找出測試指令（每次可能不同，不可測）；由子 session 回報指令（等於採信子 session）；
  在 `.specify/` 放設定檔（多一個要維護者填的東西，且 spec 沒有要求）。

### D7. 同一專案同時只有一個流程（FR-012）

> 2026-11-21 修訂：鎖改由 driver 持有，涵蓋子 session 執行與等待重置的整段期間（D18）。

- **Decision**：`.specify/sdd-drive/lock` 以作業系統的檔案鎖保護（Linux `fcntl.flock`、Windows `msvcrt.locking`，非阻塞）。`run` 與 `test`
  在整個執行期間持有它，程序結束（含被終止）時由作業系統釋放。`status` 以嘗試取得鎖的方式判斷是否有流程在執行（`running`），並立即釋放。
- **Rationale**：不依賴 PID（PID 會被重用；Windows 上 `os.kill(pid, 0)` 會終止程序，不能用來探測）；不會因當機留下永久的鎖。
- 第二個主 session 輸入 `/sdd-drive` 時看到 `running`：回報已有執行中的流程與它正在處理的 spec 與階段（紀錄中最後一筆未結束的嘗試），不啟動、不 `finalize`。
- 只能靠 SKILL.md 的部分：主 session 在等待背景執行時不另外啟動第二個 `run`（腳本也會以 `running` 拒絕）。

### D8. 用量上限與中斷後的接續（FR-021、FR-022、SC-009）

> 2026-11-21 修訂：「回報後停止、不自動重試」改為 D17–D21 的「有重置時間時自動接續一次」；以下關於紀錄、指紋、`--resume`、`finalize` 的設計仍適用。

- `run` 在啟動子 session 前先寫入一筆嘗試（`outcome: null`、`session_id`、模型、理由），結束時補上結果。程序被終止時這筆嘗試留著 `outcome: null`。
- 下一次 `status` 發現「最後一筆嘗試沒有結果且鎖沒有被持有」：`pending_finalize: true`。主 session 執行 `finalize`（記為 `interrupted`），
  依檔案狀態回報中斷與進度後停止（US3-3），不自動接續；再下一次 `/sdd-drive` 才接續。
- 用量上限、`api-error`、`interrupted` 不改變失敗次數；子 session 留下的未提交檔案不被觸碰（不 stash、不 reset、不 checkout）。腳本在嘗試結束時
  記下工作區的指紋（`git status --porcelain=v1 -z` 與各檔案內容雜湊的雜湊，不記路徑），接續時若工作區指紋相同，判定這些變更屬於被中斷的子 session，
  允許接續；不同時視為維護者的變更（D9）。
- 接續的下一步是 `run --resume`：腳本以同一個 `session_id` 傳 `--resume`，提示要求子 session 先重新檢查檔案狀態，從未完成的部分繼續。
  即使改成開新的 session，各階段也不重做已完成的部分：plan 已填寫就不再進 plan（D5）；implement 只做未勾選的任務（工作說明要求，且已勾選的任務是檔案事實）。
- 主 session 自己也會被用量上限中斷：背景的 `run` 可能還在執行或一起停止；下一次 `/sdd-drive` 的 `status` 會看到 `running` 或 `pending_finalize`，
  依上面處理。主 session 的上下文被壓縮或換成新的對話時，同樣以 `status` 重新取得一切進度，不憑記憶（SKILL.md 規定每個行動前先 `status`）。

### D9. 不捨棄或覆蓋未提交的變更（FR-015）

- `status` 與 `run` 檢查 git 工作區（排除被 ignore 的檔案與 `.specify/feature.json`）。有未提交的變更且不是 D8 所述被中斷的子 session 留下的：
  `reason: "dirty"`，列出路徑（像機密的路徑以 `(not shown)` 取代），主 session 告知維護者並停止，不啟動子 session。
  理由：子 session 會 commit，若在髒的工作區執行，維護者的變更會被混進子 session 的 commit。
- 腳本與工作說明都不使用 `git stash`、`reset`、`checkout -- <path>`、`clean`、`restore`；切換分支只在工作區乾淨（或只有被中斷的子 session 的變更、
  且目標分支就是目前分支）時進行，git 本身也會拒絕會覆蓋檔案的切換。
- 子 session 成功結束卻留下未提交的變更：`verify-failed`（`uncommitted`），不替它 commit 也不捨棄，回報後停止。

### D10. 不修改 constitution 與 spec（FR-016）、不手寫 Spec Kit 產物（FR-006）、主 session 不親自實作（FR-002）

- 腳本強制（事後偵測）：`run` 在啟動前後各計算一次「受保護檔案」的雜湊：`.specify/memory/constitution.md`、所有 `specs/*/spec.md`、
  Spec Kit 的範本與腳本（`.specify/templates/`、`.specify/scripts/`）與 `speckit-*` skill。任何一個改變：`verify-failed`（`protected-changed`，列出路徑），
  不還原（還原會覆蓋，違反 FR-015），由維護者處理。
- 工作說明強制（事前）：需求有矛盾或不足以做決定時，以 `failed`、`failure_kind: "requirements"` 回報並停止，不改 spec。
- FR-006：工作說明要求以 Skill 工具呼叫 `speckit-plan`、`speckit-tasks`、`speckit-implement`；腳本無法證明子 session 真的呼叫了 skill，
  只能檢查產物存在且不是範本。主 session 依 SKILL.md 只執行 `sdd_drive.py`，不寫 plan、tasks 或程式碼（FR-002、SC-007），以 SKILL.md 的內容檢查與人工驗收涵蓋。
- 子 session 無法啟動（`launch-failed`、`api-error`）時，SKILL.md 明令回報後停止，不改為親自實作（Edge Case）。

### D11. git：每份 spec 一個分支、子 session commit、一律不 push

- **分支**：每份 spec 在名稱等於其資料夾名稱的分支上進行（Spec Kit 的慣例，例如 `008-sdd-drive`）。`run` 在啟動子 session 前：
  目前分支就是它 → 不動；分支不存在 → 從目前的 HEAD 建立並切換（因此後一份 spec 疊在前一份之上）；分支存在且目前 HEAD 是它的祖先 → 切換；
  分支存在但與目前 HEAD 分岔 → `reason: "branch-diverged"`，回報並停止，不合併、不重設。結果永遠不會直接 commit 到預設分支。
- **commit**：子 session 每完成一份文件或一組任務就 commit 到目前分支（`home/CLAUDE.md` 的偏好），訊息遵循專案與使用者的 CLAUDE.md；
  MUST NOT 切換、建立、刪除分支，MUST NOT amend、rebase、reset、merge。
- **push**：一律不 push（`home/CLAUDE.md`：只在明確要求時才 push；全自動流程中沒有人能明確要求）。三層保護：工作說明禁止、
  `--disallowedTools "Bash(git push*)"`、`run` 前後比對 remote-tracking refs（`git for-each-ref refs/remotes`），有變化時 `verify-failed`（`pushed`）。
- 不是 git repository：跳過分支、未提交變更與 push 的檢查，工作說明告訴子 session 不要 commit；`status` 的 `git: false` 讓主 session 說明
  「無法依版本紀錄判斷變更」（Edge Case）。

### D12. 子 session 的工作說明由腳本產生

- **Decision**：工作說明（提示）完全由腳本依固定的英文範本產生：目標、spec 目錄、分支、階段、要呼叫的 skill、可以修改與不可以修改的檔案、
  禁止事項、commit 規則、遇到文件沒寫明的決定時怎麼做、回報格式與要附的證據、測試指令（implement）。`brief` 指令可單獨印出供檢查與測試；
  `run` 內部使用同一份。主 session 不手寫、不改寫工作說明。
- 對文件沒寫明的決定：技術決定依 constitution、spec、plan 自行決定並寫進 research.md 或 plan 的理由（FR-005）；需求層級的缺口或矛盾以失敗回報（FR-016）；
  任何情況都不提問（`--disallowedTools AskUserQuestion`）。
- 回報格式以 `--json-schema` 強制（E8），欄位見 data-model「子 session 的回報」。

### D13. 子 session 的權限

- **Decision**：`--permission-mode acceptEdits --permission-prompts none --allowedTools Bash Skill`，並 `--disallowedTools AskUserQuestion "Bash(git push*)"`。
  無頭時沒有人回答權限提示；`none` 讓會提示的動作直接被拒絕而不是卡住，被拒絕的動作列在結果的 `permission_denials`，`run` 轉述其數量與工具名稱。
- 使用者與專案的 settings 仍然生效（例如維護者設定的 deny 規則）。見設計取捨 T3（允許 Bash 的範圍）。

### D14. 狀態檔、歸屬與機密（原則 I、V）

- 本 skill 只在 `.specify/sdd-drive/` 內放自己的檔案：`.gitignore`（第一行 `# Created by sdd-drive. ...`，第二行 `*`，與 005 相同的歸屬標記，
  因此整個資料夾不入庫）、`state.json`（嘗試與測試紀錄）、`lock`。資料夾內出現其他檔案、或 `.gitignore` 不是本 skill 寫的：`reason: "conflict"`，
  不讀不寫。寫入一律「同資料夾的暫存檔再取代」。
- 不讀取、不修改、不刪除 `.specify/sdd-drive-state.json`（另一個工具的檔案）與 `.specify/.gitignore`。
- 機密：紀錄中來自外部的字串只有三種：主 session 給的 `reason`、子 session 回報的 `summary`／`failure.reason`／`failure.step`、`claude` 結果的錯誤文字摘要。
  寫入時以專案共同的機密樣式（005 的 `SECRET_PATTERNS`，以 `importlib` 載入相鄰的 `sdd-grill/scripts/sdd_grill.py`）掃描：`reason` 命中時拒絕（`secret`），
  子 session 與錯誤文字命中時以 `(not shown: looks like a secret)` 取代後才寫入與輸出。讀回時只掃描同一組欄位（寫入與讀取對稱），
  腳本自己算出的欄位（spec 資料夾名稱、雜湊、session ID、模型名稱、時間）改以格式驗證；不符合時 `reason: "state-unreadable"`（可 `clear`）。
  子 session 的完整輸出與 stderr 不寫入任何檔案。

### D15. 可測與不可測的分界（原則 II）

- 單元測試（兩個平台的 CI）：狀態判定與下一步、範本判定、測試指令擷取、`test` 的執行與紀錄、檔案鎖（以子程序持有鎖驗證 `running`）、
  `run` 的每一種 `outcome`（以假的 `claude`：一支 Python 腳本，經 `SDD_DRIVE_CLAUDE` 以 JSON 陣列 `[python, fake.py]` 指定，依情境寫檔案並印出結果物件）、
  啟動參數（模型、`--resume`、權限、stdin 傳入的提示）、分支處理、受保護檔案、push 偵測（暫存目錄的 bare remote）、未提交變更與接續的指紋、
  機密的寫入與讀回、`brief` 的內容、`finalize`、`clear`。
- 內容檢查（`tests/unit/test_sdd_drive_skill.py`）：SKILL.md 包含 contracts/skill.md 要求的每一條指示（依階段、每一種結果的分支）、英文、README 為繁體中文、
  不含機器路徑與信箱；`tests/unit/test_claude_md.py` 的 `test_referenced_skills_exist_in_home_skills` 在 `home/skills/sdd-drive/SKILL.md` 出現後不再 skip 並通過。
- 人工驗收（quickstart.md）：在暫存的假專案以真實的 `claude` 跑兩份小 spec、製造失敗、中止後接續、同時執行兩次；用量上限的實際訊息。

### D16. 腳本的組成

一支 `home/skills/sdd-drive/scripts/sdd_drive.py`（uv inline metadata、只用標準函式庫），以 `importlib` 載入相鄰的 `sdd_grill.py` 取得 Spec Kit 狀態判定、
spec 編號、原子寫入、機密樣式（004、007 的做法）；載入失敗時結束碼 3、`reason: "dependency"`。指令：`status`、`brief`、`run`、`test`、`finalize`、`clear`（見 contracts/cli.md）。

### D17. 用量上限的判讀與重置時間（FR-021）

- **Decision**：driver 以 stream-json 逐行讀取子 session 的輸出，只保留三種結構化資訊：`status: "rejected"` 的 `rate_limit_event.rate_limit_info`、
  assistant 訊息的 `api_error` 與 `api_error_params.rate_limit_info`、最後的 `result` 物件；其餘內容不保存。`outcome` 為 `usage-limit` 時，依 E10 判斷
  `limit.waitable`：`true` 時 `limit.resets_at` 是被拒絕的時間窗重置時間的最大值；`false` 涵蓋沒有重置時間（花費上限、額外用量）與判斷不出來的所有情況。
  訊息文字不解析（沒有日期，格式不保證）。
- **Rationale**：結構化欄位是 Claude Code 自己用來組訊息與決定自動繼續的同一份資料（E9 第 2、5 點）；判斷不出來歸為不可等待，符合修訂後的 FR-021。
- **Alternatives**：解析 `resets 3:10pm (Asia/Taipei)` 文字（沒有日期、跨日與時區名稱的換算不可靠、格式可能改變）；只看 `api_error_status: 429`（無法分辨有沒有重置時間）。

### D18. 由脫離的 driver 行程等待並自動接續，主 session 以 `watch` 等待

- **Decision**：
  - `run`（主 session 以 Bash 背景執行）在鎖內完成所有檢查與準備（D9–D11），寫入一筆 `launch` 記號後以兩層啟動、脫離 session 的方式啟動 **driver**
    （同一支腳本的內部指令），釋放鎖；driver 立刻以阻塞方式取得鎖並確認記號，之後在整個生命期間持有鎖。
  - driver 啟動子 session、判讀與檢查（D4、D9、D10）、寫入結果。結果是可等待的 `usage-limit` 且符合 D19 的次數規則時，driver 記下
    `auto_resume: "waiting"` 與重置時間，**自己**等待到 `resets_at` 再加 120 秒（以牆上時鐘每 30 秒檢查一次，可處理休眠；每次檢查取消要求，D20），
    重新確認工作區指紋與等待前相同，以 `--resume` 啟動同一個子 session（`auto: true` 的新嘗試），照常判讀、檢查、寫入，然後結束。
    driver 不會開始下一個階段或下一份 spec（下一步的模型要由主 session 判斷，FR-019）。
  - `run` 在啟動 driver 後轉為 `watch`：等到 driver 結束、driver 進入等待（每個等待只回報一次），或 110 分鐘到時，輸出目前的結果後結束。
    主 session 收到通知、依輸出回報後再執行 `watch`（仍以 Bash 背景執行），直到 driver 結束。
- **Rationale**：
  - 主 session 與子 session 用同一個帳號的額度，子 session 被擋下時主 session 的下一個回合很可能也被擋下（任務說明的前提）；
    把「等待並接續」放在不需要 Claude 回合的行程裡，接續不依賴主 session 能不能動。
  - Bash 背景執行最長 2 小時、Monitor 1 小時，五小時的時間窗等不完；Linux 實測兩層脫離的行程能撐過 Bash 指令被終止（E11）。
  - 主 session 只在 driver 結束後需要動作；若主 session 當時被擋下，互動式 Claude Code 內建的「Continue automatically at usage limit」
    會在重置後讓主 session 繼續（E9 第 5 點），主 session 依 SKILL.md 先 `status`，driver 已在接續或已結束，主 session 接著 `watch` 或往下一步。
  - 順帶解決 T6：長的 implement 不再被 2 小時上限終止。
- **Alternatives considered**：
  - **主 session 的 Claude 記得時間到了再繼續**（CronCreate 一次性排程或 Bash `sleep` 到重置）：需要主 session 在被擋下的當下還能呼叫工具，不可靠；
    CronCreate 只存在於該 session 的記憶體、只在閒置時觸發，且在一般 Claude Code 是否提供未查證（E9 第 6 點）。不採用為主要機制。
  - **只依賴 Claude Code 內建的自動繼續**：條件多（claude.ai 帳號、非 usage-based 計費、24 小時內、等待期間 Claude Code 不能結束、可被設定關閉），
    且只繼續主 session、不會叫醒子 session；主 session 被喚醒後再開子 session 雖然可行，但不滿足的情況下就完全不會接續。保留為「讓主 session 在 driver 之後繼續整個流程」的輔助。
  - **Bash 背景指令鏈式等待（每 110 分鐘由主 session 重新啟動）**：每一段都需要主 session 的回合，等待期間主 session 被擋下就斷了。
  - **`claude --bg` 背景 session**：本身是消耗額度的 Claude session，同樣會被擋下。
  - **作業系統排程（cron、systemd timer、Windows 工作排程器）**：兩個平台做法不同，會在專案外留下設定，且不屬於「只用 Claude Code」。

### D19. 自動接續「一次」的計數與持久化（FR-021、SC-010）

- 每筆嘗試記 `auto`（是否為自動接續）。driver 只在被中斷的嘗試 `auto: false` 時自動接續；自動接續的嘗試再次 `usage-limit` → 不再等待，停止（`auto_resume: "already-auto"`）。
- 計數存在 `state.json`（跨行程、跨主 session）；維護者再次輸入 `/sdd-drive` 啟動的 `run` 是 `auto: false`，因此之後若再遇到可等待的上限，可以再自動接續一次（計數隨維護者的手動啟動重設）。
- 不計入失敗次數（`failures` 只算 `failed`、`verify-failed`），SC-009 不受影響。

### D20. 等待期間的鎖、維護者介入與取消

- **鎖**：driver 在等待期間持有鎖；`status` 顯示 `running: true` 與 `driver.phase: "waiting"`、`waiting_until`、上限的種類。第二個 `run` 或 `test` 以 `running` 拒絕（FR-012）。
- **維護者在等待期間輸入 `/sdd-drive`**（同一個或新的主 session）：回報正在等待哪一份 spec 的哪個階段、上限的種類、預計接續的時間與目前進度，
  說明要取消可以直接告訴 Claude；然後以背景執行 `watch`，讓這個主 session 在 driver 結束後接手流程。兩個主 session 同時 `watch` 時，
  driver 結束後第一個 `run` 取得鎖，另一個得到 `running` 或 `not-next` 而回到 `status`（不會重複執行）。
- **取消**：維護者要求取消時，主 session 執行 `cancel`：在 `.specify/sdd-drive/` 建立 `cancel` 檔案（不需要鎖，不寫 `state.json`）。driver 每 30 秒與接續前各檢查一次，
  看到時記 `auto_resume: "cancelled"`、刪除該檔案、結束；主 session 回報已取消並停止，下一次 `/sdd-drive` 手動接續。driver 不在等待時 `cancel` 回報 `not-waiting`
  （子 session 執行中不提供中止；維護者可以在 driver 結束後再處理）。
- **等待期間工作區被改動**：接續前的指紋與等待前不同 → 不接續（`auto_resume: "skipped-changed"`），結束；理由同 D9（不把維護者的變更混進子 session 的 commit）。
- **主 session 的對話已關閉**：driver 仍會在重置後接續一次並把結果寫進 `state.json`，之後結束，不會再啟動其他行程。下一次 `/sdd-drive` 的 `status` 以 `last_attempt`
  呈現最近一筆嘗試，SKILL.md 先回報「你不在時發生了什麼」（自動接續的結果）再往下。這是 spec 要求「不需要維護者再輸入指令」的直接結果，代價見 T9。
- **driver 意外消失**（重新開機、被手動終止）：鎖被釋放、`driver` 仍有記錄 → `status` 的 `pending_finalize`，`finalize` 把等待中的自動接續記為 `auto_resume: "lost"`
  （未接續的嘗試仍是 `usage-limit`），回報後停止；下一次 `/sdd-drive` 手動接續。主 session 不代替 driver 做自動接續（腳本分辨不出某次 `/sdd-drive` 是維護者還是自動繼續觸發的）。
- **得知時重置時間已過**：driver 計算出的 `resets_at` 已過（例如子 session 很晚才結束），只等 120 秒的緩衝就接續；主 session 很晚才醒來時，driver 已經接續或結束，依其結果處理。

### D21. 回報（FR-021）

`watch` 與 `status` 輸出 `limit`：`waitable`、被拒絕的上限種類（`types`，例如 `["five_hour"]`、`["overage"]`）、`resets_at`（UTC 的 ISO 8601，
主 session 轉成維護者的當地時間說明）、`overage_status`，以及 `auto_resume` 的狀態與 `state_after`（目前進度）。主 session 的每一則用量上限回報 MUST 包含：
原因（用量上限，不是失敗、未計入重試）、哪一種上限、何時重置（或「沒有重置時間／無法得知」）、目前進度、接下來會自動接續還是需要維護者再輸入 `/sdd-drive`。

### D22. 對照檢查（check 階段，FR-007、FR-023、FR-024）

- **位置**：每份 spec 的第四個子 session 階段 `check`，在「任務全部勾選＋測試通過」之後；以 Skill 工具呼叫 `speckit-converge`（Spec Kit，FR-023「MUST NOT 自行手寫」）。
- **判定只看檔案**（E12）。driver 在啟動前記下 `tasks.md` 的內容、HEAD、受保護檔案與 remote refs，結束後比對：
  - `tasks.md` 不變、HEAD 不變、工作區乾淨、沒有其他檔案改變 → `succeeded`，`convergence: converged`。
  - `tasks.md` = 原內容＋合格的附加段落（只含空行、一行 `## Phase N: Convergence`、未勾選的 `- [ ] Tnnn …` 任務行與縮排的續行；新任務編號都大於原最大編號），
    且從原 HEAD 起的 commit 與工作區只動到這個 spec 的 `tasks.md` → `gaps-found`，把附加的任務編號併入 `task_ids`（之後 implement 不得刪除它們，D9 的 `tasks-removed`）。
  - 子 session 說 converged 但檔案有合格的附加段落 → 以檔案為準記 `gaps-found`，`detail.code: report-mismatch` 一併回報。
  - 子 session 說找到漏做但 `tasks.md` 沒有變 → `verify-failed`（`check-no-tasks`）：沒有證據，不當成 converged，也不當成漏做。
  - `tasks.md` 不是「原內容＋附加」（改寫、勾選、刪除任務、格式不合）→ `verify-failed`（`check-rewrote-tasks`）；動到 `tasks.md` 以外的檔案（程式碼、plan.md 等）→
    `verify-failed`（`check-touched-files`，列出路徑）；受保護檔案（spec.md、constitution）→ `protected-changed`；未提交 → `uncommitted`；push → `pushed`。都不還原。
- **commit**：由 check 子 session commit 附加的 `tasks.md`（與其他階段一致：子 session 結束時工作區必須乾淨）；converged 時 MUST NOT 產生任何 commit。
- **失敗的計算**：`gaps-found` 是該 spec 的失敗（FR-023）：計入 `failures.check`，停止整個流程，不自動修正，不開始後續的 spec。本設計沒有重試上限——每一次失敗都停止，
  只有維護者再次輸入 `/sdd-drive` 才會繼續，所以「implement → test → check → 又找到漏做」不會自行循環；每一圈都是維護者的決定（FR-024、SC-003）。
- **接續**：維護者再次啟動時，附加的未勾選任務讓狀態回到 `implementing`、下一步 `implement`（只做未勾選的任務，即補做檢查指出的工作）→ `test` → `check`。
  維護者若認為某一項不必做，可以自己在 tasks.md 處理（勾選或刪除）；`tasks.md` 因此改變，同樣需要重新測試與檢查。
- **與工作區綁定、不沿用過期結果也不重複檢查**：
  - 「完成」＝存在 `check` 的 `succeeded`／`converged` 嘗試，其 `tasks_hash` 等於目前 `tasks.md` 的雜湊。converged 不改變任何檔案，所以紀錄之後立即成立、不會再跑一次。
  - 測試紀錄另記 HEAD；要進入 `check` 時，必須有「目前 `tasks_hash` 且目前 HEAD」的通過紀錄（工作區乾淨由 D9 保證）。測試之後有 commit（實作改變）→ 先重新測試，再檢查。
  - 找到漏做之後，附加與補做都會改變 `tasks.md`，所以之前的結果自然失效（FR-024）。converged 之後該 spec 即為完成；之後由後續 spec 造成的變更屬於後續 spec，由它們的測試與檢查涵蓋，
    不重新打開已完成的 spec（否則每份新 spec 的 commit 都會讓所有已完成的 spec 重跑檢查）。
- **模型**：對照與推演需要仔細判斷，預設建議較強的模型（`opus`）；理由仍逐次撰寫（FR-019）。
- **回報**：`watch` 從 `tasks.md` 的附加段落解析每一項（編號、描述、`source-ref`、`gap-type`，各自做機密取代、每項最多 300 字元、最多列 50 項並註明總數）給主 session 列出；
  子 session 的輸出（包括 converge 在對話中的摘要表）不進入主 session。
- **用量上限**：check 子 session 適用 D17–D21（不算失敗、可等待時自動接續一次）。
- **Alternatives**：主 session 或腳本自己對照（違反 FR-023、也無法以腳本做語意判斷）；以子 session 的回報判定（不可靠）；找到漏做時自動補做（違反 FR-023）。

### D23. 既有的基準（FR-025、SC-002）

- **判定依據（只看檔案）**：`state.json` 的 `baseline`：本 skill **第一次**在這個專案寫入紀錄時（`.specify/sdd-drive/` 不存在、第一個寫入的指令 `run`、`test`、`finalize`），
  腳本依當時的檔案算出「tasks 已產生、任務全部勾選」的 spec 清單，寫入 `baseline` 後**凍結**，之後不再新增（之後才完成的 spec 永遠不在其中）。
  在第一次寫入之前，`status` 以同一規則即時計算同一份清單（因此第一次的 `status` 與寫入後的結果一致）。
- **「本 skill 實作或補做過」**＝該 spec 不在 `baseline`，**或**紀錄中有它的任何一筆 `implement` 嘗試（不論結果，含中斷）。兩者都來自檔案，不依賴主 session 的記憶。
- **狀態判定**：任務全部勾選的 spec，若在 `baseline` 且沒有 `implement` 嘗試 → 只需要「目前 `tasks_hash` 下測試通過」（D5 原本的規則，不綁 HEAD）就是 `done`，
  不執行 check、也不因缺少檢查紀錄而停止；其他 spec 依 D22（測試＋check）。
- **既有的基準被補做**：維護者在 baseline 的 spec 的 tasks.md 加了未勾選的任務 → 下一步 `implement` → 產生 `implement` 嘗試 → 之後它屬於「本 skill 補做過」，
  需要 test 與 check（FR-024、FR-025 一致）。維護者自己勾選而沒有經過 sdd-drive 的 implement 時，仍是基準，只重新測試。
- **既有的基準仍然要求測試通過才往下一份**：與修改前對「導入前已完成的 spec」的設計相同（D5：同一次測試可為連續、指令相同的多份 spec 記錄通過）；
  這次修改只拿掉它們的 check，不改變測試的行為。
- **紀錄遺失或無法讀取時偏向「需要檢查」（較安全）**：
  - `state.json` 無法讀取 → 照舊 `state-unreadable` 停止，不猜測。
  - 維護者同意 `clear` → `clear` 不再刪除整個資料夾，而是把 `state.json` 重寫為 `{"tool", "schema", "attempts": [], "tests": [], "baseline": [], "baseline_reset": true, ...}`：
    之後沒有任何 spec 是基準，所有任務已勾選的 spec 都要測試與檢查。這樣不會把本 skill 實作過、但紀錄已被清除的 spec 誤當成基準。代價是清除後第一次執行要為已完成的 spec 各跑一次檢查（只在清除後發生）。
  - 維護者手動刪除整個 `.specify/sdd-drive/` 資料夾：無法與「第一次處理」區分，會重新建立基準（README 與 SKILL.md 提醒改用 `clear`，不要手動刪除）。這是本設計唯一無法以檔案防範的情況。
- **Alternatives**：以 commit 訊息的 trailer 作為實作證據（能撐過紀錄遺失，但會改變維護者 git 紀錄的格式、需要子 session 配合）；以 tasks.md 是否有 Convergence 段落判斷（不可靠）。

## 對實際執行同類流程的觀察的處理

- **O1. 子 session 做不到的勾選任務（push 後確認 CI、人工驗收）**：tasks 的工作說明要求「需要維護者或 push 才能完成的項目寫在 Notes，不寫成勾選任務」。
  implement 遇到仍做不到的任務：以 `failed`、`failure_kind: "blocked-task"` 回報並列出任務編號，不刪除也不改寫任務；腳本在 tasks 階段通過時記下任務編號集合，
  之後檢查不得減少（`tasks-removed`），防止以刪除任務達成「全部勾選」。push 後的 CI 驗證留給維護者（結束報告提醒），見 T4。
- **O2. 子 session 的回報不能直接採信**：完成只看檔案狀態（D5）與腳本親自執行的測試（D6）。測試依賴執行順序屬於測試本身的品質；腳本只執行整套指令一次，
  無法偵測。implement 的工作說明要求新測試不得依賴執行順序，並列出 tests/conftest.py 這類專案慣例由子 session 自行遵循（屬子 session 的實作品質，不另設關卡）。
- **O3. 用量上限中斷**：D4、D8；以 `--resume` 接續同一個子 session，不計入失敗；2026-11-21 起有重置時間時由 driver 自動接續一次（D17–D21），處理「額度重置後沒有東西叫醒主 session」。
- **O4. 文件沒寫明的決定**：D12。
- **O5. 工作說明的品質**：D12，全部由腳本產生，沒有手寫或沿用舊說明的空間；路徑、分支、階段、測試指令都是計算出來的。
- **O6. 完成後的 `speckit-converge` 檢查**：2026-11-21 維護者決定納入（FR-023、FR-024），見 D22。
- **O7. 測試環境的陷阱**：屬於被驅動的專案自己的測試品質。本 skill 自己的測試沿用 tests/conftest.py（停用 git 背景維護），
  測試中的資料夾名稱不含 Windows 不允許的字元，測試之間不共用狀態。
- **O8. 主 session 上下文被壓縮**：D8，每個行動前重新 `status`。

## 設計取捨（請維護者在核可時決定）

- **T1. 每個階段一個子 session，而不是「一個子 session 處理全部」**：spec 的 User Story 1 字面上是「開一個子 session，由它依序處理」，
  但 FR-019（逐階段選模型）、FR-007（不採信子 session）與接續的成本都指向每個階段一個。若維護者要求字面的單一子 session，需要放寬 FR-019 為「每次流程選一次」。
- **T2. 測試指令取自 plan.md 的 `**Testing**:` 行**：簡單且可決定，但依賴 plan 的寫法；不符合時停止並回報。替代方案是在專案放一份設定檔。
- **T3. 子 session 允許所有 Bash 指令**（只禁止 `git push`）：implement 需要執行建置、測試與 git；逐一列出允許的指令會隨專案不同而失效。
  代價是子 session 能執行任何 shell 指令（例如刪除檔案）；保護靠工作說明、使用者 settings 的 deny 規則、受保護檔案的事後偵測與「工作區乾淨才開始」。
- **T4. 一律不 push**：CI 的兩平台驗證只在維護者 push 後發生；sdd-drive 判定的「完成」是本機測試通過，不含 CI。結束報告提醒維護者 push 並確認 CI。
- **T5. 納入 `speckit-converge`（2026-11-21 維護者決定，取代原本的「不納入」）**：每份 spec 多一個 check 子 session（預設較強的模型）的用量與時間；找到漏做就停止，需要維護者再次啟動。見 D22。
- **T6. 2 小時上限**（2026-11-21：受 D18 影響，子 session 改由脫離的 driver 執行，不再被 2 小時上限終止；主 session 每 110 分鐘重新 `watch` 一次。下列原文保留供對照）：Bash 背景執行的上限是 7200000 ms；更長的 implement 會被終止並落在 `interrupted`，下一次以 `--resume` 接續（不計入失敗）。
  可接受，但一份 spec 若常超過 2 小時，代表應該拆小。
- **T7. 中斷被發現時先回報、下一次才接續**：符合 US3-3 與 FR-021「不自動重試」；代價是維護者要多輸入一次 `/sdd-drive`。
- **T8. 既有的 `.specify/sdd-drive-state.json`**（2026-11-21 補註：001–007 依 D23 是既有的基準，只測試、不做對照檢查）：本 skill 使用 `.specify/sdd-drive/` 資料夾，完全忽略那個檔案與 `.specify/.gitignore` 中對應的一行，
  不讀、不改、不刪、不回報；維護者可自行刪除它們。已有的 001–007 沒有本 skill 的測試紀錄，第一次執行時會先執行一次測試（D5）再處理 008 之後的 spec。
- **T9. 自動接續會在維護者不在場時消耗用量，且需要一個脫離終端機的等待行程**（2026-11-21，FR-021 修訂的代價）：driver 在維護者關閉終端機或離開後仍會等待並接續一次；
  它只做一次、只接續被中斷的那個子 session、結束後不留行程，結果寫在 `.specify/sdd-drive/state.json`，下一次 `/sdd-drive` 回報。想避免時在等待期間取消。
- **T10. Windows 上的脫離行程未經實測**：Linux 實測兩層脫離能撐過 Claude Code 終止背景指令（E11）；Windows 以對應的建立旗標實作，CI 以「終止啟動它的行程樹」驗證，
  但 Claude Code 在 Windows 的終止方式無法在 CI 重現，列為人工驗收。若實際上會被終止，結果是 `auto_resume: "lost"`、回報後停止（等同沒有自動接續，不會造成錯誤的狀態）。
- **T11. 主 session 在 driver 之後繼續整個流程依賴 Claude Code 內建的自動繼續**：driver 保證被中斷的階段自動接續一次（SC-010 的範圍）；之後的階段需要主 session 選模型。
  主 session 若在等待期間被用量上限擋下，而內建的自動繼續不適用（設定關閉、usage-based 計費、重置超過 24 小時、Claude Code 已結束），流程在 driver 完成該階段後停下，
  維護者回來後輸入任何訊息或 `/sdd-drive` 才繼續。替代方案是請主 session 在流程開始時以 CronCreate 設定週期性的喚醒（session 限定、每次喚醒消耗少量用量、可用性未查證），未採用。
- **T12. 重置時間沒有上限**：spec 只要求「有重置時間就等待」，因此 7 天的時間窗也會等待（Claude Code 內建的自動繼續則以 24 小時為限）。等待期間可取消。
- **T13. 輸出格式改為 stream-json**：每行都要解析、不保存；只取結構化的限額資訊與最後的結果物件，與 D2 的 `json` 結果欄位相同。
- **T14. 既有的基準不做對照檢查**（2026-11-21 維護者決定，FR-025；取代原本「已經做完的 spec 也要檢查」）：見 D23。
- **T15. `unrequested`（多做的工作）也會停止流程**（2026-11-21 維護者核可，照此設計）：converge 對多做的工作也附加任務（「審視或移除」），依 FR-023 任何附加都是漏做而停止。代價是可能因為合理的額外實作而停下，
  由維護者在 tasks.md 處理後再啟動。
