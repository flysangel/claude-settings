# claude-settings

個人化的 Claude Code 設定：一份全域 `CLAUDE.md`，加上以 [Spec Kit](https://github.com/github/spec-kit)
進行規格驅動開發的 skill。支援 Linux 與 Windows。

> **目前狀態**：部署工具（spec 001）已實作，Linux 上的測試通過；Windows 尚未經 CI 驗證。
> `home/` 的實際內容（`CLAUDE.md` 與各個 skill）由後續的 spec 002 至 008 提供。
> 在部署工具合併進 `main` 之前，下方的指令還無法使用。

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

```text
curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash -s -- --replace
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.ps1))) --replace
```

| 被取代的內容 | 存放位置 | 移除時 |
|---|---|---|
| 不是這個工具安裝的原檔 | `~/.claude/.claude-settings/backups/` | 還原到原位 |
| 你對已安裝檔案的手動修改 | `~/.claude/.claude-settings/discarded/<時間>/` | 保留，不還原 |

## 移除

```text
curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash -s -- remove
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.ps1))) remove
```

只刪除這個工具安裝的檔案，並還原備份的原檔；`~/.claude` 的其他內容不受影響。
`~/.claude-settings` 這份 clone 不會被刪除，需要時請自行刪除。

## 結束碼

| 碼 | 意義 |
|---|---|
| 0 | 成功 |
| 1 | 執行失敗，例如無法取得 repo 或沒有寫入權限 |
| 2 | 有衝突或手動修改，沒有寫入任何檔案 |
| 3 | 缺少必要指令 |

## 開發

```text
uv run --with pytest pytest
```

規格與設計文件在 `specs/`，專案原則在 `.specify/memory/constitution.md`。
