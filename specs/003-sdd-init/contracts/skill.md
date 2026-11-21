# Contract: sdd-init skill 的結構

部署來源是 `home/skills/sdd-init/`，安裝後位於 `~/.claude/skills/sdd-init/`。`tests/unit/test_sdd_init_skill.py` 依此檢查。

## 檔案

| 檔案 | 語言 | 內容 |
|---|---|---|
| `SKILL.md` | 英文 | 給 Claude 的指示 |
| `README.md` | 繁體中文 | 給維護者的簡述：用途、用法、前置需求、會建立與不會碰的東西 |
| `scripts/sdd_init.py` | 英文（訊息與註解） | 全部的判斷邏輯，介面見 [cli.md](./cli.md) |

資料夾內沒有其他檔案。

## SKILL.md

frontmatter：

| 欄位 | 值 |
|---|---|
| `name` | `sdd-init` |
| `description` | 一句英文，說明用途是在目前專案導入或移除 Spec Kit |
| `disable-model-invocation` | `true`（只由維護者以 `/sdd-init` 執行） |
| `argument-hint` | `[remove]` |

內文 MUST 指示 Claude：

1. 沒有參數時執行 `uv run "${CLAUDE_SKILL_DIR}/scripts/sdd_init.py" init`；參數是 `remove` 時執行 `remove`；
   其他參數時說明用法，不執行任何指令。
2. 在目前專案的目錄執行，只執行一次。
3. 把腳本輸出的版本、建立、略過、加入暫存區、警告與下一步完整回報給維護者，不省略任何一筆路徑；
   下一步建議的兩條路（`/sdd-grill`，或 `/speckit-constitution` 再 `/speckit-specify`）都要回報，不只挑其中一條。
4. 結束碼不是 0 時回報原因與處理方式後停止：MUST NOT 重試、MUST NOT 改用其他方式安裝 Spec Kit、
   MUST NOT 手動建立或修改 `.specify/` 與 `speckit-*` 的檔案。`uv` 指令不存在時同樣處理。
5. MUST NOT commit、push 或修改腳本沒有建立的檔案。

內文 MUST NOT 含有中日韓文字、絕對路徑、信箱。

## README.md

MUST 以繁體中文撰寫，並包含：

- 用法：`/sdd-init` 與 `/sdd-init remove`。
- 前置需求：`uv`、`git`、`bash`；Windows 的 `bash` 是隨 Git for Windows 安裝的 Git Bash。
- 導入後會出現的兩個不屬於 Spec Kit 的檔案（`.specify/sdd-init.json`、`.specify/.gitattributes`）與它們的用途。
- 專案是 git repository 時，導入會把 `.sh` 加入暫存區但不 commit。
- 需要網路（查詢版本與下載官方工具）。

## scripts/sdd_init.py

- 開頭有 uv 的 inline metadata：`requires-python = ">=3.11"`，`dependencies` 為空。
- 只使用 Python 標準函式庫；外部指令只有 `uv`、`git`。
- 可被測試以模組方式載入，載入時不執行任何動作。
