# Data Model: 全域 CLAUDE.md

## 文件（Document）

`home/CLAUDE.md`，部署為 `~/.claude/CLAUDE.md`。

| 欄位 | 說明 |
|---|---|
| 標題 | 一個一級標題 |
| 段落 | 恰好三個二級標題，依序為「溝通」「Git」「規格驅動開發」 |
| 編碼 | UTF-8，換行 LF，結尾有換行 |

## 段落（Section）

| 欄位 | 說明 |
|---|---|
| 名稱 | 二級標題文字 |
| 前言 | 選填的一段說明；「規格驅動開發」用它說明適用範圍與例外 |
| 規則 | 一條以上的規則 |

## 規則（Rule）

| 欄位 | 說明 |
|---|---|
| 要求 | 一個頂層清單項目，描述 Claude 該怎麼做 |
| 預期 | 緊接在後的縮排行，以「預期：」開頭，描述維護者可以觀察到的行為 |

驗證規則：

- 每條規則 MUST 恰好有一個預期。
- 規則引用的 skill 名稱 MUST 屬於：`sdd-init`、`sdd-update`、`sdd-grill`、`sdd-export`、`sdd-rebuild`、`sdd-drive`。
- 文件 MUST NOT 出現電子信箱、家目錄的絕對路徑或其他機器專屬路徑。
