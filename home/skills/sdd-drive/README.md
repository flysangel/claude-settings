# sdd-drive

spec 確認之後，由子 session 依編號一份一份地把每份 spec 做完：plan、tasks、implement，接著由腳本親自執行測試，
最後再開一個子 session 以 Spec Kit 的對照檢查（`speckit-converge`）確認沒有漏做，才開始下一份。過程不等你核可，
只在失敗或中斷時停止並回報。

## 用法

| 指令 | 作用 |
|---|---|
| `/sdd-drive` | 從第一份未完成的 spec 的下一個步驟開始，依序做到全部完成或停止 |

- 只能由維護者在主 session 輸入 `/sdd-drive` 啟動（`disable-model-invocation: true`），Claude 不會主動使用；沒有參數。
- 主 session 只執行腳本、等待與回報，不親自做 plan、tasks、實作或對照檢查；子 session 無法啟動時也不會改為親自做。
- 每個步驟結束時回報一兩行：spec、步驟、結果、要求的模型與實際使用的模型、選擇的理由。

## 前置需求

- 專案已導入 Spec Kit（`/sdd-init`），且有 `speckit-plan`、`speckit-tasks`、`speckit-implement` 這幾個 skill；已有 spec
  （`/sdd-grill` 或 `/sdd-rebuild` 產生）。
- 同時部署 `sdd-grill`：腳本載入它的 Spec Kit 狀態判定與機密樣式。
- 只需要 Claude Code 本身與 `uv`：子 session 是腳本以 `claude -p` 啟動的無頭 session，腳本 `scripts/sdd_drive.py`
  以 `uv run` 執行、只用 Python 標準函式庫。不使用 Orca 或其他協調工具。

## 什麼算「完成」

- 任務全部勾選、測試通過（測試指令取自該 spec 的 plan.md 的 `**Testing**:` 行，由腳本親自執行，不採信子 session 的說法），
  而且對照檢查沒有找到漏做。plan 或 tasks 若只是未填寫的範本，不算已產生。
- **既有的基準**：本 skill 第一次在這個專案寫入紀錄時，任務已經全部勾選的 spec 是既有的基準，只需要測試通過，
  不做對照檢查（你想驗證時可以自己執行 Spec Kit 的對照檢查）。之後若在它的 tasks.md 加了新任務並由本 skill 補做，
  就改為需要測試與對照檢查。

## 會在什麼情況停止

- 任何步驟失敗（子 session 回報失敗、檔案狀態不符合它的說法、測試失敗）：停止整個流程，不跳過、不開始後面的 spec；
  回報是哪一份、哪個步驟與原因。需求有矛盾時，子 session 不修改 spec 或 constitution，而是以失敗回報，由你修正。
- 對照檢查找到漏做：漏做的項目已作為未勾選任務附加到 tasks.md 並 commit，流程停止並逐項列出；不自動修正。
  多做的工作（`unrequested`）也會被列出而停止。
- 子 session 沒有回報就結束、API 錯誤（例如未登入）：回報後停止，不算失敗。
- 用量上限沒有重置時間（例如每月的花費上限）、或自動接續之後又遇到用量上限：回報後停止，不算失敗。
- 工作區有你尚未提交的變更：請你先提交或處理，本 skill 不捨棄、不 stash、也不替你 commit。

## 如何接續

再輸入一次 `/sdd-drive`。進度每次都依專案內檔案的實際狀態重新判定，已完成的 spec 與步驟不重做：
失敗的步驟在你修正後重試；被中斷的子 session 以同一個 session 接續（不計入失敗）；對照檢查找到的漏做會先補做，
再重新測試與檢查。同一個專案同時只會有一個流程在執行。

## 用量上限的自動接續

子 session 因**有重置時間**的用量上限中斷時，不算失敗、不計入重試次數。負責等待的 driver 行程（由腳本以脫離終端機的方式啟動）
會等到重置時間再加 2 分鐘，以同一個 session 自動接續一次，你不需要輸入任何指令；你也可以在等待期間要求取消。
代價：driver 在你關閉終端機或離開後仍會在重置時接續一次並消耗用量；它只接續被中斷的那個步驟、結束後不留行程，
結果寫在紀錄裡，下一次 `/sdd-drive` 會先告訴你你不在時發生了什麼。等待期間若工作區有了變更，driver 不會接續。

## git 與 push

- 每份 spec 在名稱等於其資料夾名稱的分支上進行；分支不存在時從目前的 HEAD 建立，所以後一份疊在前一份之上。
  分支已存在且分岔時停止，不合併、不重設。
- commit 由子 session 進行；本 skill 與主 session 都不 commit、不 push。全部完成後請你自己 push，並確認兩個平台的 CI
  與 tasks.md 的 Notes 中需要你親自做的項目。
- 不是 git repository 時仍可執行，但無法依版本紀錄判斷變更，子 session 也不會 commit。

## 模型的選擇

每次開子 session 前，主 session 依該步驟與該 spec 的規模選模型，並寫一句理由：plan 預設 `opus`、tasks 預設 `sonnet`、
implement 依工作性質（機械性的修改用 `sonnet`，需要新設計或先前失敗時用 `opus`）、對照檢查預設 `opus`；
不預設使用最強的模型，同一次流程也不會每個子 session 都用最強的模型。接續時沿用原本的模型。

## 紀錄

- 位置：專案的 `.specify/sdd-drive/`（`state.json`、`lock`，以及一份固定內容的 `.gitignore`），不入庫。
  內容是每次嘗試的結果、測試紀錄、失敗次數、可接續的 session 與既有的基準清單；子 session 的完整輸出不保存，機密值會被取代。
- 要重設紀錄時請說「清除紀錄」，由腳本的 `clear` 處理；**不要手動刪除這個資料夾**：手動刪除會讓下一次執行重新認定既有的基準，
  可能把本 skill 做過的 spec 誤當成不需要檢查。`clear` 之後沒有任何 spec 是既有的基準，已完成的 spec 會各再測試與對照檢查一次。
- 本 skill 不讀取、不修改 `.specify/sdd-drive-state.json`（另一個工具的檔案）與 `.specify/.gitignore`。
