# Contract: sdd-drive skill 的結構與必要指示

部署來源是 `home/skills/sdd-drive/`，安裝後位於 `~/.claude/skills/sdd-drive/`。`tests/unit/test_sdd_drive_skill.py` 依此檢查。
SKILL.md 與腳本的分工見 [research.md](../research.md) 的 D1、D16；腳本介面見 [cli.md](./cli.md)。

本文件依階段列出 SKILL.md 必須包含的指示，並且**每個階段都列出每一種結果的下一步**。沒有任何一個結果的下一步是「未定義」；
實作 SKILL.md 時 MUST 逐一涵蓋。腳本回傳本文件沒有提到的結束碼或 `reason`、或輸出無法解析時，SKILL.md MUST 指示：告訴維護者發生了什麼、
再執行一次 `status` 並依它說明目前的進度，然後停止（通則 10）。

## 檔案

| 檔案 | 語言 | 內容 |
|---|---|---|
| `SKILL.md` | 英文 | 給主 session 的 Claude 的指示 |
| `README.md` | 繁體中文 | 給維護者的簡述：做什麼、怎麼啟動、何時停止、如何接續、不 push、紀錄放在哪裡、不使用的機制 |
| `scripts/sdd_drive.py` | 英文（訊息與註解） | 介面見 [cli.md](./cli.md)，包含工作說明的範本 |

資料夾內沒有其他檔案。

## SKILL.md 的 frontmatter

| 欄位 | 值 |
|---|---|
| `name` | `sdd-drive` |
| `description` | 英文；在 spec 確認後，由子 session 依編號把每份 spec 依序做完 plan、tasks、implement、測試與對照檢查，不等核可，只在失敗或中斷時停止並回報；需要 Spec Kit；只由維護者以 `/sdd-drive` 啟動 |
| `disable-model-invocation` | `true`（FR-001：只由維護者手動啟動；sdd-grill、sdd-rebuild 不會自動觸發） |

沒有其他欄位（不設 `argument-hint`：本 spec 不提供指定範圍的參數）。

## SKILL.md 的內文

每一項都 MUST 出現；結構測試以關鍵字或關鍵句檢查（括號內「字樣」），並檢查標示「順序」的段落先後。腳本一律以
`uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_drive.py" <command>` 在專案根目錄（目前目錄）執行。

### 通則（任何階段都適用）

1. **主 session 只協調**：主 session MUST NOT 親自執行 plan、tasks、implement 或對照檢查，MUST NOT 呼叫 `speckit-plan`、`speckit-tasks`、`speckit-implement`、`speckit-converge`，
   MUST NOT 撰寫或修改 plan、tasks、程式碼或測試；唯一的工作是執行 `sdd_drive.py`、等待、回報（FR-002、SC-007；字樣：`never run`、`speckit-implement`）。
   子 session 無法啟動或一再失敗時也一樣，絕不改為親自做（Edge Case；字樣：`do not take over`）。
2. **每個行動前先 `status`**：決定下一步只依 `status` 的輸出，不憑記憶或先前的輸出；上下文被壓縮或對話重新開始後也一樣（FR-011、D8；字樣：`status`、`memory`）。
3. **只經由腳本**：MUST NOT 自己寫 `.specify/sdd-drive/`、`.specify/feature.json`，MUST NOT 自己組 `claude` 指令、建立或切換分支、改寫工作說明；
   MUST NOT 讀取或修改 `.specify/sdd-drive-state.json`（不是本 skill 的檔案）（原則 I、III、D12、T8；字樣：`sdd-drive-state.json`）。
4. **背景執行與等待**：`run`、`watch`、`test` 以 Bash 工具的 `run_in_background: true`、`timeout: 7200000` 執行；之後結束這一回合等待完成通知，
   不輪詢、不 sleep、不同時做其他工作；通知到達後讀取該指令的輸出（D1、D18；字樣：`run_in_background`、`7200000`、`watch`）。
   子 session 在脫離的 driver 中執行，`run` 或 `watch` 結束不代表子 session 結束；依輸出的 `status` 決定是否再 `watch`。
5. **不提問、不等核可**：流程中不向維護者提問、不請維護者核可 plan 或 tasks；只有在停止時回報（FR-004、SC-001；字樣：`do not ask`）。
6. **git**：主 session 自己 MUST NOT commit、push、stash、reset、checkout 檔案、merge 或刪除分支；一律不 push，結束報告提醒維護者自行 push 並確認 CI（D11、T4；字樣：`never push`）。
7. **不捨棄變更**：MUST NOT 為了讓流程繼續而捨棄、還原、stash 或替維護者 commit 任何未提交的變更；受保護的檔案被改動時也不還原（FR-015、D9、D10；字樣：`uncommitted`）。
8. **模型**：每次 `run` 前依 `next.hints` 與階段評估模型並寫一句英文理由（準則見 D3、D22：plan 預設 `opus`、tasks 預設 `sonnet`、implement 依性質、check（對照檢查）預設 `opus`；
   不預設 `fable`，使用時理由要說明為何較便宜的模型不夠；同一次流程不得每個子 session 都用最強的模型；接續時沿用 `next.model`）（FR-019、SC-008；字樣：`model`、`reason`、`sonnet`、`opus`）。
9. **機密**：理由與回報中不寫機密值；腳本以 `(not shown...)` 取代的內容不要嘗試找出原值（原則 V；字樣：`secret`）。
10. **未預期的結果**：見本文件開頭（字樣：`unexpected`）。
11. **回報的語言**：與維護者對話的語言依全域設定；腳本輸出中的英文訊息可轉述（字樣：`language`）。
12. **用量上限的自動接續只由 driver 做**：主 session MUST NOT 自己等待重置、排程喚醒（例如 CronCreate）、或為了用量上限自行再 `run --resume`；
   自動接續最多一次，由 driver 依紀錄判斷（D18、D19；字樣：`automatic resume`、`once`）。主 session 自己被用量上限擋下而稍後繼續時（Claude Code 的自動繼續或維護者的訊息），
   一律從階段 1 的 `status` 重新開始（通則 2）。
13. **用量上限的回報**：每一則都包含原因（用量上限，不是失敗、未計入重試）、上限的種類（`limit.types`）、重置時間（`limit.resets_at` 轉成維護者的當地時間，
   沒有時說「沒有重置時間或無法得知」）、目前進度（`state_after`），以及接下來會自動接續（何時）還是需要維護者再輸入 `/sdd-drive`（FR-021、D21；字樣：`resets_at`）。

### 階段 1：開始（`status`）

順序：`status` → 依下表 → 宣告 → 階段 3 或 4。

| `status` 的結果 | 下一步 |
|---|---|
| 結束碼 3、`dependency` | 說明 sdd-grill 未安裝（以部署工具重新部署），停止 |
| `speckit-missing` | 說明先執行 `/sdd-init`，再以 `/sdd-grill` 或 `/sdd-rebuild` 產生 spec；不開子 session，停止（Edge Case、FR-014） |
| `speckit-incomplete` | 列出缺少的 `speckit-*`，說明可能是 Spec Kit 不相容的變更或需要 `/sdd-update`，停止（Edge Case） |
| `no-specs` | 說明先以 `/sdd-grill` 或 `/sdd-rebuild` 產生 spec，停止 |
| `claude-missing` | 說明找不到 `claude` 指令、無法開子 session，停止；不親自實作 |
| `conflict` | 說明 `.specify/sdd-drive/` 有不是本 skill 的檔案，請維護者確認；不刪除，停止 |
| `state-unreadable` | 指出欄位路徑（不含值），說明紀錄影響失敗次數、測試與檢查紀錄，以及哪些 spec 是既有的基準；可請維護者同意後 `clear`，並說明清除後沒有任何 spec 是基準、已完成的 spec 會各再測試與對照檢查一次；未同意前停止；MUST NOT 建議手動刪除 `.specify/sdd-drive/`（D23） |
| `running: true`、`driver.phase` 為 `running` 或 `resuming` | 回報已有執行中的流程、它正在處理的 spec 與階段、開始時間、是否為自動接續；不開第二個子 session、不 `finalize`；以背景執行 `watch` 接手（階段 3B）（FR-012、Edge Case） |
| `running: true`、`driver.phase: waiting` | 依通則 13 回報正在等待用量重置：哪一份 spec 的哪個階段、上限種類、預計自動接續的時間、目前進度；說明維護者若要取消自動接續可以直接說；以背景執行 `watch` 接手（階段 3B）（D20） |
| `running: true`、只有 `launch`（driver 正在取得鎖） | 以背景執行 `watch`（階段 3B） |
| `last_attempt.auto` 為 `true` 或 `last_attempt.auto_resume` 不為 `null` | 在下面的宣告之前先回報這筆嘗試：曾因用量上限中斷、是否已自動接續與其結果（維護者不在場時發生的事，D20）；再依其他列繼續 |
| `next.action: finalize` | 進入階段 2 |
| `dirty` 不為空且 `leftovers: false` | 列出路徑，說明子 session 會 commit，請維護者先自行提交或處理這些變更；不捨棄、不開子 session，停止（Edge Case、FR-015） |
| `next.action: none` | 回報每份 spec 都已完成、沒有待處理的 spec；不開子 session，停止（US4-4） |
| `git: false` | 說明不是 git repository，無法依版本紀錄判斷變更、子 session 不會 commit；繼續（Edge Case） |
| `next.action` 為 `run`、`resume`、`test` | 宣告：要處理哪些 spec（`state` 不是 `done` 的，依編號）、從哪一份的哪個階段開始、已完成的有哪些、哪些是既有的基準（`baseline: true`，只測試、不做對照檢查）、各 spec 的失敗次數；然後進入階段 3 或 4（US1-1） |

### 階段 2：處理被中斷的嘗試（`finalize`）

| 結果 | 下一步 |
|---|---|
| 成功、且被清除的嘗試 `auto_resume` 為 `lost` | 依通則 13 回報：子 session 曾因用量上限中斷、等待重置的行程已不存在（例如重新開機），自動接續沒有發生；說明再次 `/sdd-drive` 會接續同一個子 session、不計入失敗，停止（D20） |
| 成功（其他） | 回報流程曾經中斷（沒有回報就結束）：哪一份 spec、哪個階段、使用的模型、開始時間，以及依 `state_after` 與 `status` 的目前進度；說明再次 `/sdd-drive` 會接續同一個子 session、不計入失敗，停止（US3-3、T7） |
| `running` | 回報另一個流程剛開始執行，停止 |
| `nothing-to-finalize` | 回到階段 1 |
| 其他 | 依通則 10 |

### 階段 3：開子 session（`run`）

順序：`status`（通則 2）→ 決定模型與理由（通則 8）→ 以背景執行 `run --spec <next.spec> --phase <next.phase> --model <m> --reason "<r>"`
（`next.action: resume` 時加 `--resume`，模型用 `next.model`）→ 等待通知 → 讀取輸出 → 對 `attempts` 的每一筆以一兩行回報：spec、階段、`outcome`、
是否為自動接續（`auto`）、要求的模型與 `model_used`、理由（FR-020、SC-008；字樣：`model_used`）→ 依下表（以最後一筆嘗試與 `status` 判斷）。
`watch`（階段 3B）的輸出格式相同，也依本表處理。

| `run` 的結果 | 下一步 |
|---|---|
| `outcome: succeeded` | 回到階段 3 或 4 的開頭（先 `status`）；不等核可（FR-004、FR-008） |
| `outcome: failed` | 停止整個流程，不開始後面的 spec；回報 spec、階段、`failure.kind`、`failure.step`、`failure.reason`、該階段累計失敗次數；`requirements` 時說明需要維護者修正 spec 或 constitution（FR-016）；`blocked-task` 時列出任務編號，說明這些任務需要維護者或 push 才能完成；提醒子 session 若留下未提交的變更由維護者決定如何處理；說明修正後再次 `/sdd-drive` 會從這個階段重試（FR-009、FR-010、US3、US4-3） |
| `outcome: verify-failed` | 同 `failed`，原因依 `detail.code` 說明：`plan-missing`／`tasks-missing`（子 session 宣稱完成但產物不存在或仍是範本）、`tasks-unfinished`（仍有未勾選任務）、`tasks-removed`（任務被刪除）、`protected-changed`（列出被改的 constitution、spec 或 Spec Kit 檔案；未還原，請維護者檢查）、`pushed`（remote-tracking refs 改變，請維護者確認遠端）、`uncommitted`（留下未提交的變更；未捨棄）；check 階段另有 `check-no-tasks`（子 session 說找到漏做但 tasks.md 沒有變化，不當成完成也不當成漏做）、`check-rewrote-tasks`（tasks.md 被改寫、勾選或刪除任務，而不是只在末尾附加）、`check-touched-files`（動到 tasks.md 以外的檔案，列出路徑；未還原）；修正後再次 `/sdd-drive` 會重新檢查（FR-007、FR-015、FR-016、D22） |
| `outcome: succeeded`（`phase: check`、`convergence: converged`） | 回報對照檢查沒有找到漏做，這份 spec 判定完成（任務全勾、測試通過、檢查通過）；回到階段 3 或 4 的開頭，開始下一份 spec（FR-007、FR-008） |
| `outcome: gaps-found` | 停止整個流程，不自動修正，不開始後面的 spec；以 `findings` 逐項列出（編號、描述、`source_ref`、`gap_type`；超過 50 項時註明總數），說明這些已作為未勾選任務附加到 tasks.md 並已 commit、該 spec 的對照檢查失敗次數；說明再次 `/sdd-drive` 會先補做這些任務，再重新測試與對照檢查；維護者認為某項不必做時可以自己在 tasks.md 處理；`detail.code: report-mismatch` 時另說明子 session 的說法與檔案不符、以檔案為準（FR-023、FR-024、D22） |
| `status: waiting`（`auto_resume: waiting`） | 依通則 13 回報，說明 driver 會在 `waiting_until` 自動接續一次、維護者不必輸入指令、要取消可以直接說；以背景執行 `watch`（階段 3B）（FR-021、SC-010） |
| `status: running`（時間到，子 session 仍在執行） | 不回報細節，以背景執行 `watch`（階段 3B） |
| `status: launch-failed` | 回報 driver 無法啟動；不親自實作，停止（FR-014） |
| 最後一筆 `outcome: usage-limit`、`auto_resume: not-waitable` | 依通則 13 回報：這個上限沒有重置時間（例如每月的花費上限）或無法判斷，不會自動接續；進度與未提交的檔案都保留；說明處理後（例如提高上限或等額度恢復）再次 `/sdd-drive` 會接續同一個子 session；停止（FR-021、FR-022） |
| 最後一筆 `outcome: usage-limit`、`auto_resume: already-auto` | 依通則 13 回報：自動接續之後再次因用量上限中斷，不再自動重試；說明再次 `/sdd-drive` 會接續；停止（FR-021） |
| 最後一筆 `outcome: usage-limit`、`auto_resume: cancelled` | 回報自動接續已依要求取消、進度保留；再次 `/sdd-drive` 會接續；停止（D20） |
| 最後一筆 `outcome: usage-limit`、`auto_resume: skipped-changed` | 回報等待期間工作區有了變更，為了不把它們混進子 session 的 commit 而沒有自動接續；以 `status` 的 `dirty` 列出路徑；請維護者處理後再次 `/sdd-drive`；停止（D9、D20） |
| 有 `auto: true` 的嘗試且最後一筆 `outcome: succeeded` | 回報已在重置後自動接續並完成該階段（時間、模型）；回到階段 3 或 4 的開頭（先 `status`）（SC-010） |
| 有 `auto: true` 的嘗試且最後一筆是其他 `outcome` | 依下面同名的列處理，並在回報中說明這是自動接續的結果 |
| `outcome: api-error` | 回報 API 錯誤與 `detail.text`（例如未登入、模型不可用），不計入失敗、進度保留；不親自實作、不自動重試，停止；說明處理後再次 `/sdd-drive` 會接續 |
| `outcome: interrupted` | 回報子 session 沒有回報就結束（`detail.code`），依 `state_after` 說明進度，不計入失敗；停止，再次 `/sdd-drive` 會接續（US3-3） |
| `outcome: launch-failed` | 回報子 session 無法啟動與原因；不親自實作，停止（Edge Case、FR-014） |
| `resume_failed: true` | 回報無法接續原本的子 session（例如紀錄不在這台機器），改以 `--resume --fresh` 開新的子 session 執行同一階段一次；新的 session 仍依檔案狀態從未完成處繼續；若再次失敗依其 `outcome` 處理 |
| `permission_denials` 不為空 | 在階段回報中列出被拒絕的工具；不改變上面的分支 |
| `reason: secret` | 改寫理由（不含機密）後重新執行一次 |
| `reason: running` | 回報有另一個流程在執行（可能是另一個主 session 已接手），停止；不再 `watch`，避免兩個主 session 同時推進 |
| `reason: pending-finalize`、`not-next` | 回到階段 1（狀態在 `status` 之後改變了） |
| `reason: dirty` | 同階段 1 的 `dirty` |
| `reason: branch-diverged` | 說明 spec 的分支已存在且與目前分支分岔，請維護者決定如何合併或改名；不合併、不重設，停止 |
| `speckit-*`、`claude-missing`、`conflict`、`state-unreadable` | 同階段 1 |
| `os-error` | 回報無法寫入或 git 指令失敗的原因，停止 |
| 背景指令沒有輸出 JSON（被終止、逾時、主 session 中斷後恢復） | 回到階段 1；`status` 會顯示 `running` 或 `finalize`，依其處理 |
| 主 session 自己曾被用量上限擋下，稍後才繼續（重置時間可能已過） | 回到階段 1；driver 若已自動接續或已結束，依 `status` 與 `watch` 的結果處理（通則 12） |

### 階段 3B：等待 driver（`watch`）

順序：以背景執行 `watch` → 等待通知 → 依階段 3 的表處理輸出。另外：

| 結果 | 下一步 |
|---|---|
| `no-driver` | 回到階段 1 |
| 等待期間維護者要求取消自動接續 | 進入階段 6 |
| 等待期間維護者輸入其他訊息 | 回應後，若 `status` 仍顯示 driver 在執行，再以背景執行 `watch` |

### 階段 6：取消自動接續（`cancel`）

只在維護者明確要求時執行（字樣：`cancel`）。

| 結果 | 下一步 |
|---|---|
| `cancel_requested: true` | 告知 driver 會在 30 秒內停止；以背景執行 `watch`，收到 `auto_resume: cancelled` 後依階段 3 的對應列回報並停止 |
| `not-waiting` | 依 `status` 說明目前沒有等待中的自動接續（可能已開始接續或已結束），依階段 1 處理 |
| 其他 | 依通則 10 |

### 階段 4：確認測試通過（`test`）

順序：`status` → `next.action: test` → 以背景執行 `test --spec <next.spec>` → 等待通知 → 依下表。主 session 親自（經由腳本）執行測試，
不採信子 session 的說法（FR-007、O2；字樣：`do not trust`）。

| 結果 | 下一步 |
|---|---|
| `passed: true`，spec 是既有的基準（`baseline: true`） | 回報這些既有的基準測試通過、判定完成，不做對照檢查（維護者要驗證時可自行執行 Spec Kit 的對照檢查）；回到階段 3 或 4 的開頭（FR-025） |
| `passed: true`，其他 spec | 回報這些 spec（`covers`）測試通過；尚未判定完成，下一步是對照檢查（`next.phase: check`）；回到階段 3 或 4 的開頭（FR-007、FR-023） |
| `passed: false` | 停止，不開始後面的 spec；回報 spec、測試指令、結束碼、`output_tail` 的重點，以及失敗次數；說明修正後再次 `/sdd-drive` 會重新測試（FR-009、FR-010） |
| `no-test-command` | 回報無法以測試確認完成（plan.md 沒有可執行的測試指令），不判定為完成，停止（Edge Case） |
| `running`、`pending-finalize`、`not-next`、`dirty` 等 | 同階段 3 的對應列 |
| 背景指令沒有輸出 JSON | 回到階段 1 |

### 階段 5：結束報告

流程結束或停止時（任何停止的分支都適用），報告 MUST 包含（FR-010、SC-005；字樣：`final report`）：

1. 每份 spec 的狀態（依最後一次 `status`）：已完成、目前的 spec 與階段、尚未開始。
2. 停止的原因：失敗時 spec、步驟、原因與累計失敗次數；中斷時中斷的種類並明說「不是失敗」；用量上限依通則 13，並說明是否已自動接續過（D19）。
3. 本次每個子 session 的 spec、階段、`outcome`、要求的模型與實際模型、理由（FR-020）；對照檢查找到漏做時列出每一項（`findings`）。
4. 下一步：再次 `/sdd-drive` 會做什麼；全部完成時提醒維護者自行 push 並確認兩個平台的 CI，以及 tasks.md 的 Notes 中需要維護者親自做的項目（T4、O1）。

維護者只讀這份報告就要知道是哪一份、哪個步驟與原因，不需要開啟子 session 的紀錄（SC-005）。

## 子 session 的工作說明（腳本範本必含事項）

由 `sdd_drive.py` 的固定範本產生（D12），`tests/unit/test_sdd_drive.py` 以 `brief` 的輸出檢查每個階段都包含下列事項：

| 事項 | plan | tasks | implement | check |
|---|---|---|---|---|
| 目標：只做這一份 spec 的這一個階段；spec 目錄與分支 | ✓ | ✓ | ✓ | ✓ |
| 以 Skill 工具呼叫的 skill：`speckit-plan`／`speckit-tasks`／`speckit-implement`／`speckit-converge`；MUST NOT 手寫這些 skill 的產物 | ✓ | ✓ | ✓ | ✓ |
| 不提問、不等核可；技術決定依 constitution、spec 與既有設計自行決定並記下理由 | ✓ | ✓ | ✓ | ✓ |
| 需求有矛盾或不足：以 `failed`、`kind: requirements` 回報，MUST NOT 修改 spec.md 或 constitution | ✓ | ✓ | ✓ | ✓ |
| MUST NOT 修改 Spec Kit 的範本、腳本與 `speckit-*` skill，MUST NOT 修改其他 spec 的資料夾、`.specify/sdd-drive/` | ✓ | ✓ | ✓ | ✓ |
| `**Testing**:` 行以反引號寫出可直接執行、兩個平台寫法相同的測試指令，放在該行第一個反引號區段 | ✓ | | | |
| 需要維護者或 push 才能完成的項目寫在 Notes，不寫成勾選任務；任務行格式 `- [ ] T001 …` | | ✓ | | |
| 只做未勾選的任務；做完一項就勾選；MUST NOT 刪除、改寫或合併任務；做不到的以 `blocked-task` 回報並列出編號 | | | ✓ | |
| 完成前執行測試指令（腳本填入）並使其通過；新測試不得依賴執行順序 | | | ✓ | |
| 唯一的寫入是 `speckit-converge` 在 tasks.md 末尾附加的 Convergence 段落；MUST NOT 修改程式碼、測試、plan.md、spec.md 或其他檔案，MUST NOT 勾選、改寫、刪除或重新編號既有任務，MUST NOT 自行修正找到的問題 | | | | ✓ |
| check 的 git：有附加時以一個 commit 提交 tasks.md（只含這個檔案）；沒有發現時 MUST NOT 產生任何 commit 或檔案變更 | | | | ✓ |
| git：每完成一份文件或一組任務就 commit 到目前分支，訊息遵循專案與使用者的 CLAUDE.md；結束時不得留下未提交的變更；MUST NOT push、切換或建立分支、amend、rebase、reset、merge、stash、clean | ✓ | ✓ | ✓ | ✓（commit 的時機依上一列） |
| 不是 git repository 時：不 commit（取代上一列） | ✓ | ✓ | ✓ | ✓ |
| 接續時（`--resume` 或 `--fresh`）：先重新檢查檔案狀態，從未完成的部分繼續，不重做已完成的部分 | ✓ | ✓ | ✓ | ✓ |
| 機密值不得寫入檔案、commit 或回報 | ✓ | ✓ | ✓ | ✓ |
| 回報：以結構化輸出回報 `status`、`summary`（做了什麼、commit 了哪些）、失敗時的 `failure`；check 另回報 `convergence` | ✓ | ✓ | ✓ | ✓ |

## README.md

繁體中文，涵蓋：用途（spec 確認後一次做完）、啟動方式（只能由維護者輸入 `/sdd-drive`）、會在什麼情況停止、如何接續、
不 push 與分支的做法、紀錄放在 `.specify/sdd-drive/`（不入庫）、子 session 使用 `claude -p`（只需要 Claude Code）、模型的選擇原則。
