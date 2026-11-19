# Data Model: 部署工具

## 部署內容（Source）

repo 內 `home/` 底下的所有檔案。每個檔案以相對於 `home/` 的路徑識別，並對應到 `~/.claude/<相同路徑>`。

- 路徑一律以 `/` 分隔，兩個平台相同。
- 內容以位元組原樣複製，不做任何轉換。

## 安裝紀錄（Manifest）

位置：`~/.claude/.claude-settings/manifest.json`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schema` | integer | 格式版本，目前為 1 |
| `status` | `"applying"` \| `"complete"` | 上一次執行是否完整結束 |
| `repo_commit` | string | 部署來源的 commit；取不到時為空字串 |
| `entries` | array | 每個由本工具安裝的檔案一筆 |
| `entries[].path` | string | 相對於 `~/.claude` 的路徑，以 `/` 分隔 |
| `entries[].sha256` | string | 部署當下的內容雜湊 |
| `entries[].backup` | boolean | 是否有被取代的原檔備份 |
| `entries[].previous` | string（選填） | 只在 `status` 為 `applying` 時出現：寫入前該路徑的內容雜湊，供中斷後判斷歸屬 |
| `created_dirs` | array of string | 由本工具建立的目錄（相對路徑），移除時若為空就刪除 |

規則：

- MUST NOT 含有絕對路徑、使用者名稱、信箱或任何機密（FR-013）。
- `status` 為 `applying` 時，`entries` 是本次要達成的目標狀態；再次執行時據此完成。
- 檔案無法解析時視為不存在，所有既有檔案都當成不是自己安裝的。

## 備份（Backup）

位置：`~/.claude/.claude-settings/backups/<path>`

- 內容是被 `--replace` 取代、且不屬於本工具的原檔。
- 每個路徑只保留第一次的備份；之後的更新不覆寫它。
- 移除時搬回 `~/.claude/<path>`。

## 捨棄的修改（Discarded）

位置：`~/.claude/.claude-settings/discarded/<UTC 時間戳>/<path>`

- 內容是使用者手動改過、之後被 `--replace` 覆蓋或移除的本工具檔案。
- 不參與還原；移除後若仍有內容，保留這個目錄並回報。

## 動作計畫（Plan）

規劃階段的輸出，只存在於記憶體。每個路徑一個動作：

| 動作 | 條件 |
|---|---|
| `create` | 目標不存在 |
| `adopt` | 目標存在、內容與來源相同、不在 manifest |
| `keep` | 在 manifest 且內容與來源相同 |
| `update` | 在 manifest、目標雜湊等於紀錄、來源已改變 |
| `delete` | 在 manifest、目標雜湊等於紀錄、來源已不提供 |
| `conflict-foreign` | 不在 manifest 且內容與來源不同 |
| `conflict-modified` | 在 manifest 但目標雜湊不等於紀錄，且也不等於來源 |

狀態轉移：

- 計畫中沒有 `conflict-*`：直接執行。
- 有 `conflict-*` 且沒有 `--replace`：結束碼 2，零寫入。
- 有 `conflict-*` 且有 `--replace`：`conflict-foreign` 先備份到 backups 再寫入；
  `conflict-modified` 先搬到 discarded 再寫入（或在移除時刪除）。

移除時，在 manifest 內但目標已不存在的檔案視為已移除，不算衝突。
