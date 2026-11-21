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
腳本的每一種 `outcome` 與 `reason` 由假的 `claude`（`SDD_DRIVE_CLAUDE`）覆蓋，不會啟動真的子 session。

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
| 5 | 新增 `003-y` 與 `004-z`，在 003 的 implement 執行中於主 session 按 Esc 並結束 Claude Code；重新開啟後 `/sdd-drive` | 第一次回報「流程中斷」與依檔案的進度、不計入失敗；第二次 `/sdd-drive` 接續 003 的 implement（不重做 plan、tasks、已勾選的任務），完成後才開始 004 | US3-3、US4、SC-004、T7 |
| 6 | 在 5 的子 session 執行中，從另一個終端機在同一專案啟動 Claude Code 並輸入 `/sdd-drive` | 回報已有執行中的流程，不開第二個子 session | FR-012 |
| 7 | 修改一個已提交的檔案但不提交，`/sdd-drive` | 列出該檔案並停止，檔案內容不變 | FR-015 |
| 8 | 在 plan.md 的 `**Testing**:` 行移除指令、勾選全部任務後 `/sdd-drive` | 回報無法以測試確認完成並停止 | Edge Case |
| 9 | 在沒有 `.specify/` 的資料夾輸入 `/sdd-drive` | 說明先執行 `/sdd-init` 等，不開子 session | Edge Case、FR-014 |
| 10 | 不是 git repository 的專案（Spec Kit 已導入、有一份小 spec） | 說明無法依版本紀錄判斷變更；仍完成該 spec | Edge Case |
| 11 | 實際遇到用量上限時（無法刻意製造） | 回報為用量上限、不是失敗、未計入重試；恢復後 `/sdd-drive` 以同一 session 接續；記下實際的 `api_error_status` 與訊息，若分類為 `api-error` 或 `interrupted` 而不是 `usage-limit`，回報以調整樣式（行為不變） | FR-021、FR-022、SC-009、research E5 |
| 12 | 在 Windows 上重複 1–3 | 結果相同 | 原則 II、FR-017 |

驗收結束後刪除暫存專案；`claude purge <暫存目錄>` 可清除該目錄的 Claude Code 紀錄。
