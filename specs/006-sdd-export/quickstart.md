# Quickstart: 驗證 sdd-export

以下情境都在暫存目錄進行，不會動到真正的專案，也不會動到 `~/.claude`；**不要拿本 repo 當成舊專案**。
哪些 FR 由自動測試涵蓋、哪些只能人工驗收，見 [research.md](./research.md) 的 R8。
格式與規則見 [data-model.md](./data-model.md)，指令介面見 [contracts/cli.md](./contracts/cli.md)。

## 前置

- 已安裝 `uv`、`git`。
- 在 repo 根目錄；下面以 `<repo>` 代表它的路徑，`<export>` 代表 `uv run <repo>/home/skills/sdd-export/scripts/sdd_export.py`。
  Windows 在 Git Bash 或 PowerShell 皆可。

## 自動測試

```text
uv run --with pytest pytest tests/unit/test_sdd_export.py tests/unit/test_sdd_export_skill.py
uv run --with pytest pytest                      全部
```

預期：全部通過，且不需要網路。`home/skills/sdd-export/SKILL.md` 存在之後，`tests/unit/test_claude_md.py` 中
「引用的 skill 資料夾存在」一項在 6 個 skill 到齊之前仍會跳過。合併前 CI 的 `test`、`cross-platform-produce`、
`cross-platform` 三個 job 在兩個平台都必須是綠的（本功能只新增 `test` job 執行的測試，不新增 job；FR-019 的驗證方式見 R8）。

## 手動情境（腳本）

準備一個不是 git repository、沒有 Spec Kit 的小專案：`src/app.py`、`README.md`、`node_modules/x/index.js`、`dist/app.js`、
`.env`（內容 `API_KEY=dummy`）、`src/settings.py`（含一行 `password = "hunter2"`）。

1. **只讀的現況**：記下目錄樹（含內容雜湊），執行 `<export> check`。預期結束碼 0；`export_dir` 為 `"none"`、`lineage` 為 `"none"`、
   `generation` 為 1、`constitution` 為 `null`、`specs` 為空；`inventory.skipped` 的 `dependency`、`build`、`secret` 各為 1，
   `secret_files` 為 `[".env"]`。目錄樹與執行前完全相同（沒有 `.venv`、`uv.lock`、`.sdd-export/`）。
2. **讀取範圍與機密位置**：`<export> files`。預期 `files` 只有 `README.md`、`src/app.py`、`src/settings.py`；
   `secret_hits` 為 `[{"path": "src/settings.py", "line": <行號>}]`，輸出中沒有 `hunter2` 與 `dummy`。目錄樹不變。
3. **草稿驗證**：依 data-model 的「最小範例」改成 `generation: 1`、一個功能、一條 `confirmed` 但 `evidence` 為空的需求，
   經 stdin 交給 `<export> validate`。預期結束碼 1、`reason: "invalid"`、`errors` 含 `unsupported`。
   把依據改成 `src/app.py` 後預期 `ok: true`、`diff.base` 為 `"none"`。把某條 `text` 改成含 `password=abc` 再驗證，
   預期 `reason: "secret"`，輸出中沒有 `abc`。把依據改成 `.env`，預期 `evidence` 錯誤。目錄樹始終不變。
4. **寫入**：以 `check` 的 `state`（`"none"`）執行 `<export> write --expect none`。預期結束碼 0；只多出 `.sdd-export/` 的三個檔案，
   其他檔案的內容雜湊不變；`nutrients.json` 為 LF、無 BOM；`README.md` 第一行是標記。再執行 `check`：`export_dir` 為 `"ours"`、
   `nutrients` 為 `"unchanged"`、`view` 為 `"current"`。
5. **並行保護與手動編輯**：再以 `--expect none` 執行 `write`，預期 `reason: "changed"`、不寫入。手動修改 `nutrients.json` 某條需求的文字，
   `check` 預期 `nutrients: "edited"`、`view: "stale"`；以新的 `state` 與原本的草稿 `validate`，`diff.changed` 列出那一條。
   把 `nutrients.json` 改成無效 JSON，`check` 預期結束碼 3、`reason: "nutrients-unreadable"`。復原後手動修改 `README.md` 本文，
   預期 `view: "edited"`、`view_secret_lines: []`；再在 `README.md` 加一行 `token: <自編的假權杖>`，預期 `view_secret_lines` 列出該行號，
   輸出中沒有該權杖。在 `nutrients.json` 某條需求的文字加上同一個假權杖，`check`、`files`、`validate`、`write` 都預期結束碼 3、
   `reason: "nutrients-invalid"`、`errors` 只有 `check: "secret"` 與該欄位路徑，`existing` 為 `null`，輸出中沒有該權杖；
   在 `.sdd-rebuild/lineage.json` 加入時同樣預期 `lineage-invalid`。
6. **衝突**：在另一個專案建立 `.sdd-export/notes.txt`，執行 `check` 與 `write`。預期結束碼 3、`reason: "conflict"`，`notes.txt` 不變。
7. **世代**：在另一個專案放一份依 data-model「世代紀錄」寫成的 `.sdd-rebuild/lineage.json`（`generation: 2`，一個功能指向存在的
   `specs/001-x/spec.md`、一條教訓、一筆捨棄紀錄）。`check` 預期 `generation` 為 2、該 spec 的 `in_lineage` 為 `true`。
   草稿漏掉那條教訓時 `validate` 預期 `lineage-item-missing`；把繼承項目的 `origin` 改成 2 預期 `origin-changed`；
   改了繼承需求的文字但 `revised` 沒有 2 預期 `revision-unmarked`；刪掉那筆捨棄紀錄預期 `discard-lost`。
   在世代紀錄的功能加上 `derived_from: ["old-x"]`（重建時合併而來），草稿新增一條 `id` 為 `old-x`、`origin` 為 2 的需求，
   預期 `id-reused`；改用新的 `id` 並以 `derived_from` 指向該功能則通過。
8. **唯讀**：把專案設為唯讀（Linux `chmod -w`；Windows 以檔案屬性設定）後執行 `write`。預期結束碼 1、`reason: "os-error"`，
   沒有留下 `.sdd-export/` 或暫存檔。
9. **過大**：以腳本產生 1600 個小檔案的專案，`check` 預期 `too_large: true`；`files` 不帶範圍時 `files` 為空陣列；
   `files --scope <一個子目錄>` 列出該目錄的檔案。

## 人工驗收（真實 session）

以 `uv run <repo>/tools/deploy.py` 部署到**暫存的家目錄**（Linux 先 `export HOME="$(mktemp -d)"`，Windows 設定 `$env:USERPROFILE`，同 001 的 quickstart），或在測試機上部署；
在暫存目錄準備舊專案，於該目錄啟動 Claude Code 並輸入 `/sdd-export`。每個情境記錄結果與日期。
核心情境（1、2、5）在 Windows 與 Linux 各做一次。

1. **有 spec 的專案**（US1、FR-002 至 FR-004、FR-010、FR-011、FR-018）：專案有 constitution 與 3 份 spec（以 sdd-init 導入）。
   預期：草稿含全部原則、3 個功能的需求與相依、教訓與世代資訊（第 1 代）；確認前 `git status` 沒有變化；
   確認後只多出 `.sdd-export/`；養分不含 plan、tasks、程式碼；需求不描述實作；結束報告說明位置、可以提交、
   下一步在新專案執行 `/sdd-rebuild`。Claude 沒有呼叫任何 `speckit-*` skill，也沒有 commit。
2. **只有程式碼的專案**（US2、FR-001、FR-005 至 FR-008、FR-015）：一個沒有 Spec Kit、不是 git repository、含 `.env` 與一處寫死密碼的小專案。
   預期：不要求 `/sdd-init`；每項需求附依據檔案或標為待確認；疑點獨立一節、一題一項；沒有開啟 `.env`；
   密碼沒有出現在對話與養分中（只提到位置）；全程沒有執行建置、測試或套件安裝；只多出 `.sdd-export/`。
3. **大型專案與部分 spec**（FR-016、FR-017、US2-4）：monorepo（兩個子目錄各有 `package.json`、含 `node_modules/`），其中一個子目錄有 spec。
   預期：Claude 先列出區塊並請維護者選擇範圍，選定前沒有讀取原始碼；`node_modules/` 沒有被讀取；有 spec 的功能以 spec 為準、
   其餘從程式碼導出並標明來源；養分的 `scope` 為 `partial`。再次執行並選擇另一個範圍，前一次的項目原樣保留。
4. **經驗教訓**（US3、FR-009）：有修訂紀錄（commit 歷史與 research 類文件）的專案。預期：教訓分三類、各附依據；
   刪除一項後寫入的養分不含它。在一個沒有任何歷史與文件的專案，Claude 說明沒有找到並詢問是否口頭補充，不自行編造。
5. **世代延續**（US4、FR-012、FR-013、SC-006）：在情境 7 的專案（帶世代紀錄、之後又新增 2 份 spec）執行。
   預期：養分的世代為 2；繼承的需求保留 `origin: 1`；新增的 2 個功能 `origin: 2`；前代教訓逐項詢問是否仍適用；捨棄紀錄保留。
   以同一份養分手寫一份第 3 代的世代紀錄再匯出一次，第 1 代的需求仍以 `origin: 1` 出現。
   在第 3 代的世代紀錄放一個重建時合併而成的功能（`origin: 3`、`spec` 為舊專案的路徑、需求的 `source` 為 `"rebuild"`）：
   預期沿用時功能的 `spec` 取自 `check` 的 `specs`、`source` 依目前的來源重新決定；維護者刪除它時 Claude 把它與它的需求
   移到 `discarded`，不直接刪除，也不在 `validate` 之後再問一次。
6. **再次匯出**（FR-014、US4-4）：在情境 1 的專案修改一份 spec、手動編輯 `nutrients.json` 一條需求後再次執行。
   預期：Claude 說明養分被手動編輯過；改動那條需求前先詢問；最終確認前呈現差異；寫入後仍只有一份 `nutrients.json`。
   在最終確認之後、寫入之前從另一個終端機修改 `nutrients.json`：預期 Claude 回報養分被修改、重新呈現差異並再次確認。
7. **中斷與失敗**（Edge Cases）：(a) 草稿呈現途中要求結束：沒有任何檔案被寫入，Claude 說明沒有保存；
   (b) `.sdd-export/` 已有別的檔案：Claude 在讀取前就停止並回報；(c) 專案唯讀：草稿照常整理，寫入失敗時回報原因並完整呈現確認後的草稿；
   (d) 只有一個設定檔的專案：Claude 說明內容不足並停止。
