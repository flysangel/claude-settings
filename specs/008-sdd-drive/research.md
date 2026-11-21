# Research: sdd-drive

**Feature**: `008-sdd-drive` | **Date**: 2026-11-21

（本檔先寫入實測紀錄以免中斷遺失；決策各節隨後補上。）

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
- **用量上限無法在實測中觸發**（需要真的用完額度）。依 E3 的欄位，用量上限屬於 API 錯誤，預期 `terminal_reason: "api_error"` 且
  `api_error_status: 429`；`result` 的文字會提到 limit 與重設時間。這一點列為人工驗收項目，判讀規則的設計見決策 D4：
  即使判讀錯誤，也只會落在「中斷」而不是「失敗」，FR-021 的行為不變。
- stdout 沒有可解析的結果物件（程序被終止、當機、Bash 工具逾時）視為「沒有回報就結束」。
