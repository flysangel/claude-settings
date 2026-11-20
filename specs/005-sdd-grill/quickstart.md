# Quickstart: 驗證 sdd-grill

以下情境都在暫存目錄進行，不會動到真正的專案，也不會動到 `~/.claude`。
哪些 FR 由自動測試涵蓋、哪些只能人工驗收，見 [research.md](./research.md) 的 R3。

## 前置

- 已安裝 `uv`、`git`。
- 在 repo 根目錄；下面以 `<repo>` 代表它的路徑。

## 自動測試

```text
uv run --with pytest pytest tests/unit/test_sdd_grill.py tests/unit/test_sdd_grill_skill.py
uv run --with pytest pytest                      全部
```

預期：全部通過，且不需要網路。`home/skills/sdd-grill/SKILL.md` 存在之後，`tests/unit/test_claude_md.py` 中
「引用的 skill 資料夾存在」一項在 6 個 skill 到齊之前仍會跳過。合併前 CI 的 `test`、`cross-platform-produce`、
`cross-platform` 三個 job 在兩個平台都必須是綠的（本功能只新增 `test` job 執行的測試）。

## 手動情境（腳本）

`<grill>` 代表 `uv run <repo>/home/skills/sdd-grill/scripts/sdd_grill.py`。Windows 在 Git Bash 或 PowerShell 皆可。

先準備一個導入 Spec Kit 的空專案（需要網路）：

```text
git init
uv run <repo>/home/skills/sdd-init/scripts/sdd_init.py init
git add -A && git commit -m "spec kit"
```

1. **前置檢查**：執行 `<grill> check`。預期結束碼 0；`speckit` 為 `"ok"`、`constitution` 為 `"template"`、`specs` 為空、
   `progress` 為 `"none"`。在另一個空目錄執行，預期結束碼 3、`speckit` 為 `"missing"`，目錄仍是空的。
   刪除 `.claude/skills/speckit-specify/SKILL.md` 後執行，預期結束碼 3、`speckit` 為 `"incomplete"`，`missing` 列出該檔。
2. **保存與不入庫**：以 [data-model.md](./data-model.md) 的欄位組一份 `phase: "discussing"` 的最小進度，經 stdin 交給 `<grill> save`。
   預期結束碼 0；`.specify/sdd-grill/progress.json` 與 `.specify/sdd-grill/.gitignore` 存在；
   `git status --porcelain --untracked-files=all` 沒有任何輸出；`git add -A` 之後仍沒有。
3. **機密被拒**：把某個 `decision` 改成含 `password=hunter2` 的字串再 `save`。預期結束碼 1，`error` 指出欄位路徑但不含該值，
   `progress.json` 沒有改變。
4. **變更偵測**：在專案 commit 一個新檔案後執行 `<grill> check`。預期 `progress` 為 `"present"`、`changed` 為 `["head"]`、
   `saved` 是第 2 步的內容。
5. **確認與驗證**：把進度改成 `phase: "confirmed"`、`stage: "summary"`、兩個功能 `a`、`b`（`b` 依賴 `a`）並 `save`；
   預期輸出 `"baseline": true`。手動建立 `specs/001-a/spec.md` 與 `specs/002-b/spec.md`（只為了測試腳本；實際流程由 `speckit-specify` 產生），
   把兩個 `spec_dir` 填入並 `save`，再執行 `<grill> verify`：預期 `ok` 為 `true`。
   把兩個 `spec_dir` 對調後再 `save` 與 `verify`：預期結束碼 1，`failures` 有 `order` 與 `dependency-order`。
6. **指向第一份**：先把 `.specify/feature.json` 寫成 `{"feature_directory": "specs/002-b"}`（模擬 `speckit-specify` 最後寫入的結果），
   執行 `<grill> focus`。預期結束碼 0、輸出 `feature_directory` 為 `specs/001-a`、`previous` 為 `specs/002-b`、`changed` 為 `true`，
   檔案內容是 `{"feature_directory": "specs/001-a"}`，`git status --porcelain` 仍沒有輸出（不入庫）；再執行一次，`changed` 為 `false`。
   刪除該檔案後執行，預期建立並 `previous` 為 `null`；把內容改成 `not json` 後執行，預期改寫並 `previous` 為 `null`。
   把兩個 `spec_dir` 對調後執行，預期結束碼 1、`feature.json` 沒有改變。先在專案放一份 `specs/000-old/spec.md` 並重做第 5 步（讓它在 `baseline` 中），
   預期目標仍是這一批的第一份。
7. **清除**：執行 `<grill> clear`。預期 `.specify/sdd-grill/` 不存在；再執行一次，輸出 `{"cleared": false}`、結束碼 0。
8. **衝突**：建立 `.specify/sdd-grill/notes.txt` 後執行 `save` 與 `clear`。預期兩者都是結束碼 1，`notes.txt` 仍在。

以上情境都由 `tests/unit/test_sdd_grill.py` 自動涵蓋；手動執行是為了在實作完成時確認真實的檔案與 git 行為。

## 人工驗收（真實 session）

對話行為無法在 CI 驗證，以下情境由維護者在真實的 Claude Code session 執行，並在 tasks.md 對應的任務記錄結果。

先把 skill 部署到**測試用的家目錄**，避免與真正的 `~/.claude` 混在一起（這台機器的 `~/.claude/skills/` 可能有同名的其他 skill）：

```text
HOME=<test-home> uv run <repo>/tools/deploy.py             Linux／Git Bash
CLAUDE_CONFIG_DIR=<test-home>/.claude claude                在測試專案中啟動 session
```

Windows 的 PowerShell 以 `$env:USERPROFILE` 與 `$env:CLAUDE_CONFIG_DIR` 達到相同效果。
每個情境開始前，用上面「手動情境」的方式準備一個導入 Spec Kit 的測試專案。

| # | 操作 | 預期（對應） |
|---|---|---|
| 1 | 輸入 `/sdd-grill` 加一段刻意含糊的需求，例如「做一個記帳工具，要簡單好用」 | Claude 先執行 `check` 並讀取專案；每則訊息只有一題，以 AskUserQuestion 呈現，建議排第一且附理由；問題都能對應到需求中的某個未決事項；能從專案查到的事沒有被問；順序是原則 → 功能清單與相依 → 逐一功能（US1-1、2、3、6；FR-001 至 FR-004、FR-007；SC-001、SC-006） |
| 2 | 追問中回答「要快」；之後給一個與先前矛盾的回答；再主動提起「用 SQLite 好不好」 | 對「要快」繼續追問到可判斷；指出矛盾的兩邊並要求取捨；SQLite 只被記為留給 plan，不展開討論（US1-4、5、7；FR-005、FR-006、FR-008） |
| 3 | 回答幾題後說「先到這裡」；開新的 session 再輸入 `/sdd-grill` | 結束時呈現目前摘要並停止；`git status` 乾淨；新 session 先列出已決定的事項並詢問接續或重新開始；接續後沒有重問任何已決定的事項；選擇重新開始時 `.specify/sdd-grill/` 被清除（US3-1、2、3；FR-009、FR-010；SC-004） |
| 4 | 中斷後在專案 commit 一個檔案，再輸入 `/sdd-grill` | Claude 先說明專案在上次討論後有變更（指出改變的項目），由你決定是否沿用（US3-4；FR-010） |
| 5 | 走到摘要；在確認前檢查 `git status` 與 constitution；要求修改摘要中的一項 | 摘要有已決定、已延後與原因、留給 plan、功能順序四部分；確認前 constitution 與 `specs/` 沒有任何變化；修改後再次請你確認，仍未寫入（US2-1、2、3；FR-011、FR-012；SC-002） |
| 6 | 確認摘要（摘要有兩個以上的功能） | Claude 以 Skill 呼叫 `speckit-constitution` 與 `speckit-specify`（不是自己寫檔）；constitution 只有摘要中的原則；每個功能一份 spec，編號依相依順序；延後事項在對應 spec 的 Assumptions；文件語言符合 FR-020；`.specify/feature.json` 指向這一批編號最小的一份（不是最後一份）；結束時列出每份 spec 的位置、相依與建議順序，告訴你 `feature.json` 現在指向哪一份，說明下一步是 `/sdd-drive`（或依序以原生的 `/speckit-plan`），然後停止；`.specify/sdd-grill/` 已不存在（US2-4、5；FR-013 至 FR-018、FR-020；SC-003、SC-005、SC-007） |
| 7 | 重做到確認摘要，在第二份 spec 產生途中中斷 session；開新 session 再輸入 `/sdd-grill` | 進度保留；`feature.json` 沒有被改成第一份（仍是 `speckit-specify` 最後寫入的、存在的資料夾）；Claude 回報已產生與未產生的文件，以一題詢問繼續（建議）、重新開始或停止，不重新討論、不補寫、不刪除已產生的文件；選擇繼續時先把已寫入的 constitution 與摘要逐條比對，再產生未產生的 spec（Edge Cases；FR-010、FR-014、FR-018） |
| 8 | 在已有 constitution 與 3 份 spec 的專案，以新需求輸入 `/sdd-grill`；途中提出與既有原則衝突的需求 | 不重問既有文件已記錄的決定；指出衝突並請你選擇修訂原則或調整需求；產生後既有 spec 未被修改，新 spec 編號接在 003 之後；你沒有同意修訂時 constitution 不變；`feature.json` 指向這一批的第一份（新編號最小的一份），不是 001（US4-1、2、3；FR-016） |
| 9 | 在沒有導入 Spec Kit 的目錄輸入 `/sdd-grill` 加需求 | Claude 請你先執行 `/sdd-init`，沒有開始追問，目錄沒有任何新檔案（Edge Cases；FR-019） |
| 10 | 不輸入指令，只說「我想開一個新專案，但還不確定要做成什麼樣子」；另外問一句「這個專案該用哪個資料庫？」 | 前者 Claude 主動使用 sdd-grill；後者不觸發 sdd-grill（FR-001；R5） |
| 11 | 以 `--disallowedTools AskUserQuestion` 啟動 session 後輸入 `/sdd-grill` 加需求 | 改用文字提問，仍然一次一題並附建議（Edge Cases；FR-003） |
| 12 | 在第 1 步的對話中提供一組假的 API 金鑰 | 進度與產生的文件中都沒有該值，Claude 說明它沒有被記錄（Edge Cases；FR-009） |
| 13 | 在已有 spec 的專案重做到第 7 步的中斷；中斷後手動修改一份既有的 `spec.md`，再輸入 `/sdd-grill` | Claude 回報 `existing-spec-changed`，不繼續產生，詢問停止（還原後再執行）或重新開始。選擇停止：進度保留，以 git 還原該檔後再輸入 `/sdd-grill`，可以繼續產生。另做一次並選擇重新開始：`.specify/sdd-grill/` 被清除，已產生的 constitution 與 spec 都還在，接著開始新的討論（US3-3、4；FR-010、FR-018） |
| 14 | 在已有 constitution 與 spec 的專案，輸入只涉及原則的需求，例如「所有文件改用英文撰寫」 | 沒有功能清單的討論，直接進入摘要；確認後只修訂 constitution，沒有產生 spec；`.specify/feature.json` 不變；結束時說明沒有產生 spec、`feature.json` 未更動，下一步是檢查既有 spec 是否需要依新原則調整，不建議 `/sdd-drive`（FR-017；SC-007） |

情境 1 至 6 在 Linux 與 Windows 各做一次（FR-021）；其餘在任一平台做一次即可，因為平台差異只在腳本，已由兩個平台的 CI 涵蓋。

指令與輸出格式見 [contracts/cli.md](./contracts/cli.md)，skill 的結構與必要指示見 [contracts/skill.md](./contracts/skill.md)，
進度的格式與規則見 [data-model.md](./data-model.md)。
