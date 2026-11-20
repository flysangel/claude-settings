# Quickstart: sdd-rebuild 的驗證

指令介面見 [contracts/cli.md](./contracts/cli.md)，SKILL.md 的必要指示見 [contracts/skill.md](./contracts/skill.md)，
測試範圍見 [research.md](./research.md) R12。

## 前置

- repo 根目錄，`uv` 可用；`home/skills/` 下有 `sdd-export`、`sdd-grill`、`sdd-rebuild`。
- 人工驗收只在暫存目錄建立的假專案進行；**不要**拿這個 repo 或機器上其他真實的專案當成舊專案或新專案，也不要動到真正的 `~/.claude`
  （以 `tools/deploy.py` 部署到暫存的家目錄，或在暫存的新專案中以 `.claude/skills/` 放置副本）。

## 自動測試

```text
uv run --with pytest pytest tests/unit/test_sdd_rebuild.py tests/unit/test_sdd_rebuild_generations.py tests/unit/test_sdd_rebuild_skill.py -v
uv run --with pytest pytest -v          # 全部（含 005、006 的既有測試，確認行為沒有改變）
```

預期：全部通過；CI 的 `test` job 在 `ubuntu-latest` 與 `windows-latest` 都通過。`tests/unit/test_claude_md.py` 中等待 skill 資料夾齊全的檢查
在 007 之後仍只缺 `sdd-drive`。

重點案例（名稱於實作時決定）：

| 案例 | 預期 |
|---|---|
| 多代來回 1 → 5 | 每一代的世代紀錄被 006 `check` 讀為 `present`、世代加一；每一代的匯出 `validate` 通過 |
| 合併後再拆分 | 拆出項目的 `derived_from` 含 `status-list`；以 `status-list` 取名的新項目被 006 以 `id-reused` 擋下 |
| 匯出時合併再重建 | 補入的祖先來自舊專案的世代紀錄；保留項目的 `derived_from` 變長，下一代匯出通過 |
| 已知限制 1、2 | 行為如 research R5「取捨」所述，測試名稱標明是接受的限制 |
| 不補入的對照 | `status-list` 可被重用（證明補入必要） |
| 跨平台 | 以 006 的固定養分重建出的 `lineage.json` 等於 `tests/unit/fixtures/sdd_rebuild/` 的固定資料；CRLF 輸入結果相同 |
| 舊專案只讀 | 每個指令執行前後，舊專案的檔案樹（名稱、大小、內容雜湊）相同 |

## 腳本的手動檢查

在暫存目錄建立舊專案（放入 006 的 `tests/unit/fixtures/sdd_export/nutrients.json` 為 `.sdd-export/nutrients.json`，以 006 的 `write` 寫入以取得
`README.md`）與已導入 Spec Kit 的新專案（以 `/sdd-init` 或複製本 repo 的 `.specify/` 與 `.claude/skills/speckit-*` 到暫存目錄），在新專案執行：

```text
uv run <repo>/home/skills/sdd-rebuild/scripts/sdd_rebuild.py check --old <舊專案>
```

預期：結束碼 0、`export_dir: "ours"`、`old_lineage: "none"`、`needs_old_lineage: true`（fixture 是第 2 代）、`next.step: "start"`。
以舊專案自己當新專案執行（`--old .`）→ 結束碼 3、`same-project`。

## 人工驗收（真實 session）

每個情境都在新的暫存舊專案與新專案進行，結束後確認舊專案的 `git status` 乾淨（除了情境 5 的 `.sdd-export/`）。

1. **原樣重建（US1、SC-002 至 SC-004）**：舊專案有含 3 個功能的養分。`/sdd-rebuild <舊專案>` → 摘要列出原則、功能與相依、教訓、建議順序；
   確認前 constitution 與 `specs/` 沒有變化（SC-001）；全部保留並確認 → 1 份 constitution 與 3 份 spec 依相依順序編號；
   新專案沒有舊專案的 plan、tasks 與程式碼；`.sdd-rebuild/lineage.json` 為第 2 代；報告列出位置與順序、提醒提交世代紀錄、下一步 `/sdd-drive`，然後停止。
2. **逐項調整（US2）**：含 4 個功能、1 個待確認需求的養分：捨棄 1 個、合併 2 個、修改 1 個、新增 1 個；待確認的需求被單獨詢問；
   教訓引發的調整逐項標示來源；故意給出矛盾的決定 → 被指出；最終摘要列出五類與採用的教訓。產生的 spec 數量與內容符合決定。
3. **世代延續（US3、SC-006）**：情境 2 的新專案新增 1 份 spec 後執行 `/sdd-export` → 006 不需任何手動補充；養分的世代為 3；
   合併的項目可追溯到前代來源，捨棄的項目在 `discarded`，新增的需求 `origin` 正確。
4. **中斷與接續**：分別在 (a) 逐項決定途中、(b) constitution 產生後比對前、(c) 第 2 份 spec 產生後 `claim` 前、(d) `lineage` 之前結束 session，
   再執行 `/sdd-rebuild` → 每次都從 `check` 的 `next` 繼續，不重複產生；(e) 在 (a) 之後修改舊專案的養分 → 呈現差異並詢問；
   (f) 在 (c) 之後刪除第 1 份 spec → `verify` 回報 `spec-missing`，提示還原或重新開始。
5. **沒有養分（US4）**：舊專案沒有 `.sdd-export/` → 說明將先匯出；依 sdd-export 的流程（`--project`、`git -C`）完成並確認 →
   舊專案只多出 `.sdd-export/`；接著進入重建。另一次在匯出確認前拒絕 → 兩個專案都沒有任何寫入（US4-3）。
6. **新專案已有內容（FR-015）**：新專案已有 constitution 與 1 份 spec → 只提出差異；選擇修訂 constitution、把一個功能對應到既有 spec →
   既有 spec 未被改動，新 spec 編號接在後面，世代紀錄中該功能的 `spec_dir` 指向既有的資料夾。
7. **錯誤**：新專案未導入 Spec Kit → 請先 `/sdd-init`；路徑不存在 → 回報並停止；舊專案就是新專案 → 回報並停止；
   新專案已重建過 → 回報並停止；舊專案的世代紀錄被刪除（養分為第 2 代以上）→ 說明影響並詢問停止或略過。
