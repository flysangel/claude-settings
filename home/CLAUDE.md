# 個人工作偏好

## 溝通

- 以繁體中文回覆；指令、程式碼識別字與專有名詞保留原文。
  預期：我用英文提問時，回覆仍是繁體中文。
- 需要我做決定時，使用互動式提問工具 AskUserQuestion，不要用純文字提問。
  預期：每個待決定事項都以選項呈現，並標出你建議的選項。
- Skill 要求用文字或表格提問時，同樣改用 AskUserQuestion；只有工具不能用時才用文字。
  預期：執行 `/speckit-clarify` 這類 skill 時，問題也以選項呈現。

## Git

- 每完成一項異動就 commit，不等我要求。
  預期：回合結束時，你改過的檔案沒有未提交的內容。
- 不直接 commit 到 `main`；目前在 `main` 上時先開分支。
  預期：`git log main` 不會多出你直接提交的 commit。
- 只在我明確要求時才 push。
  預期：commit 後遠端沒有變化。

## 規格驅動開發

新功能以 Spec Kit 依序進行 spec、plan、tasks、implement；修正錯字這類不改變行為的小改動除外。

- 專案還沒有 `.specify/` 時，請我執行 `/sdd-init`。
  預期：你不會手動建立 Spec Kit 的檔案。
- 全新專案、有新需求或方向未定時，使用 `sdd-grill`。
  預期：一次只問一題，並附上你的建議。
- 要從舊專案重生時，請我在舊專案執行 `/sdd-export`，在新專案執行 `/sdd-rebuild`。
  預期：你會說明兩個指令各自在哪個專案執行。
- spec 已確認、要開始實作時，請我在主 session 輸入 `/sdd-drive`。
  預期：你不會自行開始實作。
- Spec Kit 有新版時，請我執行 `/sdd-update`。
  預期：你不會手動修改 `.specify/` 與 `speckit-*` skill 的檔案。
