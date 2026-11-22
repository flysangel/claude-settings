# claude-settings

個人化的 Claude Code 設定：一份全域 `CLAUDE.md`，加上以 [Spec Kit](https://github.com/github/spec-kit)
進行規格驅動開發的 skill。支援 Linux 與 Windows。

> **目前狀態**：部署工具（spec 001）已合併進 `main`，Linux 與 Windows 的 CI 都通過，下方的指令已可使用。
> `home/` 目前有全域 `CLAUDE.md`（spec 002）、`sdd-init` skill（spec 003）、`sdd-update` skill（spec 004）、`sdd-grill` skill（spec 005）、
> `sdd-export` skill（spec 006）、`sdd-rebuild` skill（spec 007）與 `sdd-drive` skill（spec 008）；`CLAUDE.md` 引用的
> 6 個 SDD skill 都已提供。

## 安裝與更新

需要先安裝 `git` 與 `uv`。缺少時指令會列出缺少的項目並停止，不會代為安裝。

Linux：

```text
curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash
```

Windows PowerShell：

```text
irm https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.ps1 | iex
```

指令會把 repo 取得到 `~/.claude-settings`，再把 `home/` 的內容安裝到 `~/.claude`。
再執行一次同一行指令就是更新；沒有變更時不會產生任何異動。

## 遇到既有檔案

`~/.claude` 內有不是這個工具安裝的同名檔案，或這個工具安裝的檔案被你手動改過時，
指令會列出所有衝突並停止，**不寫入任何檔案**。

確定要取代時加上 `--replace`，原檔會先備份：

Linux：

```text
curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash -s -- --replace
```

Windows PowerShell：

```text
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.ps1))) --replace
```

| 被取代的內容 | 存放位置 | 移除時 |
|---|---|---|
| 不是這個工具安裝的原檔 | `~/.claude/.claude-settings/backups/` | 還原到原位 |
| 你對已安裝檔案的手動修改 | `~/.claude/.claude-settings/discarded/<時間>/` | 保留，不還原 |

## 移除

Linux：

```text
curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash -s -- remove
```

Windows PowerShell：

```text
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.ps1))) remove
```

只刪除這個工具安裝的檔案，並還原備份的原檔；`~/.claude` 的其他內容不受影響。
`~/.claude-settings` 這份 clone 不會被刪除，需要時請自行刪除。

## 在專案導入 Spec Kit

安裝後，在要使用 Spec Kit 的專案開啟 Claude Code：

| 指令 | 作用 |
|---|---|
| `/sdd-init` | 導入當下最新穩定版的 Spec Kit；既有檔案不會被覆蓋，重複執行不產生異動 |
| `/sdd-init remove` | 移除 `/sdd-init` 建立且之後沒有被修改過的檔案；`specs/` 與你改過的檔案都會保留 |

前置需求是 `uv`、`git`、`bash` 都在 `PATH` 上，並且可以連線到 PyPI。Windows 的 `bash` 是隨 Git for Windows 安裝的 Git Bash。
在任一平台導入並提交的專案，在另一個平台 clone 後不需要重新導入。細節見
[home/skills/sdd-init/README.md](home/skills/sdd-init/README.md)。

## 更新專案的 Spec Kit

| 指令 | 作用 |
|---|---|
| `/sdd-update` | 把 `/sdd-init` 導入的 Spec Kit 更新到當下最新的穩定版；沒有參數，不能指定版本或降版 |

沒有被修改的 Spec Kit 檔案會換成新版，新版新增的檔案會被建立，不再提供的會被移除；
你改過的檔案保留不動，新版內容另存在 `.specify/sdd-update/<原路徑>.new` 供比對。
`.specify/memory/`（constitution）與 `specs/` 永遠不動。已是最新穩定版時不產生任何異動。

前置需求：專案已由 `/sdd-init` 導入；`uv`、`git`、`bash` 都在 `PATH` 上（Windows 的 `bash` 是 Git Bash）；
可以連線到 PyPI。細節見 [home/skills/sdd-update/README.md](home/skills/sdd-update/README.md)。

## 從需求追問出 constitution 與 spec

| 指令 | 作用 |
|---|---|
| `/sdd-grill <需求描述>` | 一次一題追問到 constitution 的原則與每個功能都有結論；你確認摘要後由 Spec Kit 產生 constitution 與 spec，然後停止 |

確認摘要之前不寫入 constitution 與 `specs/`；進度存在不入庫的 `.specify/sdd-grill/`，中斷後再執行會接續。
產生完畢後 `.specify/feature.json` 指向這一批編號最小的 spec，下一步是 `/sdd-drive`。
前置需求：專案已導入 Spec Kit（`/sdd-init`）、`uv`。細節見 [home/skills/sdd-grill/README.md](home/skills/sdd-grill/README.md)。

## 從舊專案匯出養分

| 指令 | 作用 |
|---|---|
| `/sdd-export [範圍路徑...]` | 在舊專案把原則、各功能的需求與相依、經驗教訓與世代資訊整理成草稿，你逐項決定並確認後寫入 `.sdd-export/` |

只讀取專案、不需要 Spec Kit；確認之前不寫入任何檔案，也只寫 `.sdd-export/`。下一步是在新專案執行 `/sdd-rebuild`。
前置需求：`uv`；`git` 非必要。細節見 [home/skills/sdd-export/README.md](home/skills/sdd-export/README.md)。

## 在新專案以養分重建

| 指令 | 作用 |
|---|---|
| `/sdd-rebuild <舊專案路徑>` | 在新專案讀取舊專案的養分，你逐項保留、修改、合併、捨棄並加入新需求，確認後由 Spec Kit 產生 constitution 與 spec，並留下世代紀錄 |

確認最終摘要之前不寫入 constitution、`specs/` 與世代紀錄；不修改舊專案（舊專案還沒有養分而你同意代為匯出時，只寫它的 `.sdd-export/`）。
進度存在不入庫的 `.specify/sdd-rebuild/`，中斷後再執行會接續。世代紀錄 `.sdd-rebuild/lineage.json` MUST 提交，下一次 `/sdd-export` 需要它。
完成後下一步是 `/sdd-drive`。前置需求：新專案已導入 Spec Kit（`/sdd-init`）、同時部署 `sdd-export` 與 `sdd-grill`、`uv`。
細節見 [home/skills/sdd-rebuild/README.md](home/skills/sdd-rebuild/README.md)。

## 由子 session 依序把每份 spec 做到完成

| 指令 | 作用 |
|---|---|
| `/sdd-drive` | spec 確認後，由子 session 依編號一份一份做完 plan、tasks、implement，腳本親自執行測試，再以 Spec Kit 的對照檢查確認沒有漏做，才開始下一份 |

只能由維護者在主 session 輸入；主 session 只執行腳本、等待與回報，不親自做。過程不等核可，只在失敗、對照檢查找到漏做、
中斷或用量上限（沒有重置時間或再次中斷）時停止並回報；再輸入一次 `/sdd-drive` 會依檔案狀態從未完成處接續。
有重置時間的用量上限會在重置後自動接續一次（維護者不在場時也會）。導入前已全部勾選的 spec 是既有的基準，只測試、不做對照檢查。
每份 spec 一個分支、後一份疊在前一份之上；子 session 會 commit，但一律不 push。紀錄存在不入庫的 `.specify/sdd-drive/`，
要重設請用 `clear`，不要手動刪除。前置需求：已導入 Spec Kit（`/sdd-init`）、同時部署 `sdd-grill`、Claude Code（`claude -p`）與 `uv`。
細節見 [home/skills/sdd-drive/README.md](home/skills/sdd-drive/README.md)。

## 部署工具的結束碼

| 碼 | 意義 |
|---|---|
| 0 | 成功 |
| 1 | 執行失敗，例如無法取得 repo 或沒有寫入權限 |
| 2 | 有衝突或手動修改，沒有寫入任何檔案 |
| 3 | 缺少必要指令 |

## 開發

```text
uv run --with pytest pytest                      全部（整合測試需要網路）
uv run --with pytest pytest -m "not network"     只跑不需要網路的測試
```

規格與設計文件在 `specs/`，專案原則在 `.specify/memory/constitution.md`。
