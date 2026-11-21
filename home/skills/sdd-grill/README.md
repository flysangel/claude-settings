# sdd-grill

以一段需求描述為起點，一次一題地追問，直到 constitution 的原則與每個功能都有結論；
維護者確認決策摘要後，交給 [Spec Kit](https://github.com/github/spec-kit) 產生 constitution 與 spec，然後停止。

## 用法

| 指令 | 作用 |
|---|---|
| `/sdd-grill <需求描述>` | 以這段需求開始追問；有先前的進度時，先列出已決定的事項並詢問接續或重新開始 |
| `/sdd-grill` | 沒有附需求時：有先前的進度就接續，沒有就先請你說明需求 |

全新專案、有新需求或方向未定時，Claude 也可能主動使用它（`disable-model-invocation` 沒有設定）。
單純的意見詢問、技術選型或實作既有的 spec 不會使用它。

## 前置需求

- 專案已導入 Spec Kit。沒有 `.specify/` 時會請你先執行 `/sdd-init`，不開始追問，也不建立任何檔案；
  Spec Kit 缺少產生 constitution 或 spec 所需的檔案時，會列出缺少的項目並停止。
- `uv`：腳本 `scripts/sdd_grill.py` 一律以 `uv run` 執行，只用 Python 標準函式庫。
- `git` 非必要：有的話用來偵測「上次討論之後有沒有新的 commit」。

## 流程

1. 先執行 `check`（只讀），確認 Spec Kit 可用並取得專案現況，再讀取既有的 constitution、spec、README 與程式碼；
   能查到的事自己查，不問你。
2. 依序追問：先 constitution 的**原則**，再**功能清單**與相依關係，然後**逐一**討論每個功能的使用情境、範圍與邊界情況。
   每則訊息只有一題，以 `AskUserQuestion` 呈現，建議排第一並附理由；含糊的回答會繼續追問，矛盾會被指出；
   語言、框架、資料庫等技術選型只記為「留給 plan」。
3. 全部有結論或已延後時，呈現摘要：已決定、已延後與原因、留給 plan、依相依排列的功能順序。
   **你確認之前，constitution 與 `specs/` 不會有任何寫入。**
4. 確認後依序以 Skill 工具呼叫 `speckit-constitution`（只在需要新建或你同意修訂時）與 `speckit-specify`（一次一個功能，
   被依賴的在前），所以 spec 的編號就是建議的施工順序，並接在既有 spec 之後。產生後逐條比對摘要，
   多出的規則移除或先問你。
5. 執行 `verify` 檢查結果、`focus` 指向第一份新 spec、`clear` 清除進度，列出每份 spec 的位置、相依與建議順序。
   下一步是由你輸入 `/sdd-drive`，也可以依序用原生的 `/speckit-plan`。sdd-grill 在這裡停止。
   需求只涉及原則、沒有任何功能時，只建立或修訂 constitution，不產生 spec，`.specify/feature.json` 不變；
   下一步是檢查既有 spec 是否需要依新原則調整。

## 進度

- 每個決定之後，進度存到 `.specify/sdd-grill/progress.json`。這個資料夾只屬於 sdd-grill，
  裡面有一份它自己寫的 `.gitignore`（內容是 `*`），所以進度不會出現在 `git status`，也不會被提交；
  不修改 Spec Kit 的 `.specify/.gitignore` 與專案的 `.gitignore`，也不登記在 `.specify/sdd-init.json`。
- 中途結束、產生失敗或檢查不通過時保留進度，再次執行 `/sdd-grill` 會從上次的地方接續；文件成功產生後清除。
  確認摘要之後接續時，同樣可以選擇重新開始：只清除進度，已產生的 constitution 與 spec 原樣保留給你處理。
  檢查不通過的原因若是既有 spec 或 constitution 在期間被修改，重跑也會停在同一處：把它還原後再執行，或選擇重新開始。
- 不記錄機密：Claude 只記下「需要什麼」，腳本也會拒絕寫入看起來像密碼、金鑰、權杖的值（樣式比對，無法涵蓋所有情況）。
  進度檔被手動加入這類內容時，腳本把它當成無法讀取、不顯示內容；請自行移除後重新執行，或選擇重新開始（會刪除該檔）。
- 「專案在上次討論之後有變更」只看三件事：constitution、每份 `spec.md` 的內容，以及 git 的 `HEAD`。
  未 commit 的程式碼變更不會被偵測（constitution 與 spec 的未 commit 修改會）。
- `.specify/sdd-grill/` 內出現 sdd-grill 不認得的檔案時，不寫入也不刪除，回報後停止。

## 收尾：`.specify/feature.json`

`speckit-specify` 每產生一份 spec 就把 `.specify/feature.json` 指向它，所以產生完畢時會指向最後一份。
`verify` 全部通過後，sdd-grill 以 `focus` 把它改為指向這一批新 spec 中編號最小的一份，
讓你直接用 `/speckit-plan` 時從第一份開始。這是 sdd-grill 對 Spec Kit 檔案唯一的寫入；
這個檔案是 Spec Kit 不入庫的本機狀態，寫入的格式與 Spec Kit 相同。檢查不通過時不會改它。

## 不做的事

- 不覆蓋或修改既有的 spec；新需求一律產生新的 spec，編號接在既有之後。
- constitution 只在你同意修訂時更動；不手寫 constitution 或 spec，也不自行指定編號。
- 不修改 `.specify/feature.json` 以外的 Spec Kit 檔案，不自行執行 `/sdd-init`。
- 不開始 plan、tasks 或實作，不 push。

## 腳本

`scripts/sdd_grill.py` 有五個指令：`check`、`save`、`verify`、`focus`、`clear`，輸出一律是 stdout 上的一份 JSON。
結束碼：0 成功；1 輸入無效、檢查不通過或資料夾衝突；3 Spec Kit 未導入或不完整（只有 `check`）。
介面細節見 `specs/005-sdd-grill/contracts/cli.md`。
