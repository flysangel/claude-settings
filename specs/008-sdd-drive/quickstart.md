# Quickstart: 驗證 sdd-drive

介面與資料見 [contracts/cli.md](./contracts/cli.md)、[contracts/skill.md](./contracts/skill.md)、[data-model.md](./data-model.md)。

## 前置

- 已安裝 uv、git 與 Claude Code（`claude --version`），並已登入。
- 以 `tools/deploy.py` 把 `home/` 部署到 `~/.claude`（sdd-drive 依賴相鄰的 sdd-grill）。

## 自動測試（兩個平台的 CI 都執行）

```text
uv run --with pytest pytest tests/unit/test_sdd_drive.py tests/unit/test_sdd_drive_skill.py tests/unit/test_claude_md.py
uv run --with pytest pytest
```

預期：全部通過；`test_claude_md.py::test_referenced_skills_exist_in_home_skills` 不再 skip（6 個 skill 都有 `SKILL.md`）。
腳本的每一種 `outcome` 與 `reason` 由假的 `claude`（`SDD_DRIVE_CLAUDE`）覆蓋，不會啟動真的子 session。用量上限的部分：
假的 `claude` 依情境輸出 stream-json，包括 `status: "rejected"` 的 `rate_limit_event`（時間窗有 `resetsAt`、只有 `overage`、缺 `resetsAt`、只有文字、
花費上限＋5 小時時間窗的組合），測試以環境變數把「現在時間」與等待間隔縮短，驗證：可等待與不可等待的判斷、driver 等待後以 `--resume` 自動接續一次、
自動接續後再次中斷時停止、`cancel`、等待期間工作區改變時不接續、`finalize` 把消失的 driver 記為 `lost`、失敗次數不變、手動啟動後計數重設、
等待期間第二個 `run` 得到 `running`。對照檢查的部分：假的 `claude` 分別讓 `tasks.md` 不變、附加合格的 Convergence 段落並 commit、說 converged 卻附加、
說找到卻沒附加、改寫或勾選既有任務、改動程式碼或 plan.md、附加後不 commit，驗證 `converged`、`gaps-found`（含 `findings` 與 `report-mismatch`）與各個 `verify-failed`；
並驗證 converged 後立即判定完成、不重複檢查；既有的基準（第一次寫入時已全部勾選且沒有 `implement` 嘗試）只測試、不檢查，加了新任務並經本 skill 補做後改為需要檢查，
`clear` 之後沒有基準；`tasks.md` 或 HEAD 改變後先重新測試再檢查，找到漏做後下一步回到 `implement`。另以「終止啟動 driver 的行程樹」（Linux：`killpg` 加 `kill`；Windows：`taskkill /T /F`）驗證 driver 仍存活並完成（兩個平台的 CI）。

## 人工驗收（真實的子 session；在暫存目錄的假專案進行，不在本 repo）

準備：在暫存目錄建立 git repository，以 `/sdd-init` 導入 Spec Kit，寫一份簡短的 constitution，並以 `speckit-specify` 建立兩份很小的 spec
（例如 `001-hello`：一支印出 hello 的 Python 腳本與它的 pytest；`002-bye`：同樣規模）。constitution 寫明測試指令為 `uv run --with pytest pytest`。
先提交，工作區保持乾淨。

| # | 操作 | 預期 | 對應 |
|---|---|---|---|
| 1 | 在主 session 輸入 `/sdd-drive` | 宣告依序處理 001、002；每個階段結束有一行回報含模型與理由；主 session 沒有呼叫 `speckit-*`、沒有寫檔案（只執行 `sdd_drive.py`）；最後兩份都完成，提醒自行 push；沒有被問任何問題 | US1、SC-001、SC-007、FR-020 |
| 2 | 檢查 1 的結果 | 分支 `001-hello`、`002-bye` 存在且後者疊在前者之上；每份都有 plan、tasks（全部勾選）與實作的 commit；遠端沒有變化；不是每個子 session 都用同一個最強的模型 | D11、SC-008 |
| 3 | 再輸入一次 `/sdd-drive` | 回報沒有待處理的 spec，不開子 session | US4-4 |
| 4 | 新增 `003-x`，其 spec 要求一個不可能的條件（例如與 constitution 矛盾），`/sdd-drive` | 003 的 plan 以 `requirements` 失敗；回報 spec、步驟、原因；spec.md 與 constitution 未被修改 | US3、FR-016 |
| 4a | 在一個已有兩份完成的 spec（任務全部勾選、測試通過）但從未執行過 sdd-drive 的專案輸入 `/sdd-drive` | 宣告這兩份是既有的基準；執行一次測試後判定完成，沒有開 check 子 session；接著處理下一份 | FR-025 |
| 4b | 新增 `003-w`：spec 有兩條需求，實作 1 的子 session 完成後，在它的 commit 之上手動刪除第二條需求的實作與對應測試、保持任務全部勾選與測試通過，再 `/sdd-drive` | 測試通過後對照檢查找到漏做：流程停止，回報逐項列出附加的任務（含 `FR-002` 這類來源與 `missing`），tasks.md 末尾多了 Convergence 段落且已 commit，程式碼未被修改；再次 `/sdd-drive` 依序補做、測試、再檢查，通過後才判定完成 | US2-4–6、FR-023、FR-024 |
| 5 | 新增 `003-y` 與 `004-z`，在 003 的 implement 執行中於主 session 按 Esc 並結束 Claude Code；重新開啟後 `/sdd-drive` | 第一次回報「流程中斷」與依檔案的進度、不計入失敗；第二次 `/sdd-drive` 接續 003 的 implement（不重做 plan、tasks、已勾選的任務），完成後才開始 004 | US3-3、US4、SC-004、T7 |
| 6 | 在 5 的子 session 執行中，從另一個終端機在同一專案啟動 Claude Code 並輸入 `/sdd-drive` | 回報已有執行中的流程，不開第二個子 session | FR-012 |
| 7 | 修改一個已提交的檔案但不提交，`/sdd-drive` | 列出該檔案並停止，檔案內容不變 | FR-015 |
| 8 | 在 plan.md 的 `**Testing**:` 行移除指令、勾選全部任務後 `/sdd-drive` | 回報無法以測試確認完成並停止 | Edge Case |
| 9 | 在沒有 `.specify/` 的資料夾輸入 `/sdd-drive` | 說明先執行 `/sdd-init` 等，不開子 session | Edge Case、FR-014 |
| 10 | 不是 git repository 的專案（Spec Kit 已導入、有一份小 spec） | 說明無法依版本紀錄判斷變更；仍完成該 spec | Edge Case |
| 11 | 實際遇到有重置時間的用量上限時（無法刻意製造；例如 5 小時時間窗用完） | 回報原因、上限種類、重置的當地時間與進度，並說明會自動接續；不輸入任何指令，重置後子 session 以同一 session 自動接續一次並完成該階段；若主 session 也被擋下，Claude Code 的自動繼續讓主 session 在重置後繼續流程（或維護者回來後輸入任何訊息繼續）；失敗次數不變。記下 driver 保存的 `limit`（`types`、`resets_at`），確認與 Claude Code 顯示的訊息一致 | FR-021、FR-022、SC-009、SC-010、research E9、E10 |
| 12 | 遇到沒有重置時間的上限（例如每月花費上限用完、方案的時間窗仍有額度） | 回報為沒有重置時間、不自動接續、停止；之後 `/sdd-drive` 手動接續 | FR-021 |
| 13 | 在 11 的等待期間輸入 `/sdd-drive`，再要求取消 | 第一次回報正在等待與接續時間；要求取消後回報已取消並停止；重置後沒有子 session 被啟動 | D20、FR-012 |
| 14 | 在 11 的等待期間關閉終端機（結束 Claude Code），重置後再開啟並輸入 `/sdd-drive` | 子 session 已在重置後自動接續一次；`/sdd-drive` 先回報「你不在時」的結果，再繼續下一步 | D20、T9 |
| 15 | 在 Windows 上重複 11（或以假的 `claude` 讓真實的 driver 在 Claude Code 的背景指令中等待超過其 `timeout`） | driver 撐過背景指令被終止，仍在時間到後接續；若被終止，`/sdd-drive` 回報 `lost` 並停止（記錄結果以決定 T10） | 原則 II、T10、research E11 |
| 16 | 在 Windows 上重複 1–3 | 結果相同 | 原則 II、FR-017 |

驗收結束後刪除暫存專案；`claude purge <暫存目錄>` 可清除該目錄的 Claude Code 紀錄。
