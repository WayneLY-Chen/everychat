# everychat

[English](README.md) | 繁體中文

**搜尋你跟 AI 聊過的每一句話。** ChatGPT、Claude、Gemini、Claude Code、Codex 全部進同一個本地索引。免費、離線，而且你的 coding agent 可以透過 MCP 查詢它。

[![PyPI](https://img.shields.io/pypi/v/everychat?color=3fb950)](https://pypi.org/project/everychat/)
[![CI](https://github.com/WayneLY-Chen/everychat/actions/workflows/ci.yml/badge.svg)](https://github.com/WayneLY-Chen/everychat/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/everychat)](https://pypi.org/project/everychat/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

<p align="center">
  <img src="docs/demo.svg" alt="終端機示範：everychat sync 索引本機 session，everychat search 在 ChatGPT、Claude Code、Claude 三處找到同一個 timezone bug，最後 Claude Code 透過 MCP 從歷史回答問題" width="760">
</p>

同一個問題你可能在三個 AI 產品裡問過三次。everychat 讓第一次的答案找得回來，也讓你的 agent 找得到。

```bash
uv tool install everychat
everychat sync                                   # 索引本機的 Claude Code 與 Codex 對話
everychat import ~/Downloads/chatgpt-export.zip  # 匯入 ChatGPT / Claude.ai / Gemini 匯出檔
everychat search "timezone bug"
claude mcp add everychat -- everychat mcp        # 讓 Claude Code 能查這一切
```

## 為什麼需要它

- 對話散在各家廠商，每一家內建的搜尋不是很弱就是根本沒有。
- Coding agent（Claude Code、Codex）把 session 存在硬碟上，但格式沒人讀得懂。
- 如果模型看得到你上個月做過的決定，下一場對話會好很多。

## 你會得到什麼

- **一行指令索引本機 agent 對話。** `everychat sync` 自動找到 Claude Code 與 Codex 的紀錄。
- **匯入廠商匯出檔。** 把 ChatGPT、Claude.ai 或 Google Takeout（Gemini）給你的 zip 或 JSON 丟進來。
- **任何語言都能快速子字串搜尋。** SQLite FTS5 搭配 trigram 分詞，中文、日文、程式識別字都不需要斷詞器。
- **MCP server。** 加進 Claude Code、Codex、Cursor 或任何 MCP client。問一句「這個我是不是已經解過了？」，agent 自己去翻。
- **可選的語意搜尋**，完全在本機跑，不需要 API key。
- **沒有雲端。** 一個 SQLite 檔放在 `~/.everychat`，什麼都不會上傳。

## 安裝

```bash
uv tool install everychat          # 或 pipx install everychat / pip install everychat
```

需要 Python 3.10 以上，其他什麼都不用。

## 使用

```bash
everychat sync                                  # 索引本機的 Claude Code 與 Codex session
everychat import ~/Downloads/chatgpt-export.zip # ChatGPT 資料匯出（zip 或 conversations.json）
everychat import ~/Downloads/claude-export.zip  # Claude.ai 資料匯出
everychat import ~/Takeout/My\ Activity/Gemini\ Apps/MyActivity.json

everychat search "rate limiter"                 # 搜尋全部
everychat search "寫一個" --source claude-code  # 限定來源
everychat show 412                              # 印出整段對話
everychat recent --limit 10
everychat stats
```

`everychat sync` 可以隨時重跑，沒變動的檔案會自動跳過。

### 讓你的 coding agent 有記憶

```bash
claude mcp add everychat -- everychat mcp        # Claude Code
```

Codex、Cursor 或其他 MCP client，註冊一個 stdio server，指令是 `everychat mcp`。這個 server 提供四個工具：`search_chats`、`get_chat`、`recent_chats`、`list_sources`。

之後在新的對話裡：

> 「我幾週前幫這個專案設定過 Postgres 連線池，找出我當時怎麼設的。」

agent 會呼叫 `search_chats`，用 `get_chat` 讀舊對話，然後接著做。

### 語意搜尋（可選）

```bash
uv tool install "everychat[semantic]"
everychat embed                      # 跑一次即可，在 CPU 上執行一個小型多語模型
everychat search --semantic "那次因為時區導致部署壞掉的事"
```

模型是透過 fastembed 載入的 `paraphrase-multilingual-MiniLM-L12-v2`，只下載一次（約 120 MB），之後不連網。

## 匯出檔去哪裡拿

| 來源 | 方法 |
|---|---|
| ChatGPT | 設定 → 資料控制 → 匯出資料。會收到含 `conversations.json` 的 zip。 |
| Claude.ai | 設定 → 隱私 → 匯出資料。會收到含 `conversations.json` 的 zip。 |
| Gemini | [Google Takeout](https://takeout.google.com) → 我的活動 → 格式選 **JSON** → Gemini Apps → `MyActivity.json`。 |
| Claude Code | 不用做任何事。`everychat sync` 會讀 `~/.claude/projects`。 |
| Codex | 不用做任何事。`everychat sync` 會讀 `~/.codex/sessions`。 |

Gemini 的 Takeout 不會把對話分組，所以每一個提問和它的回覆會變成一段兩則訊息的對話。

## 運作方式

```
匯出檔 / session 紀錄  →  匯入器  →  SQLite（conversations、messages、FTS5 trigram 索引）
                                            ↑                      ↓
                                   everychat embed          everychat search / mcp
```

- 匯入器把每種格式都正規化成 `Conversation(source, external_id, title, messages[])`。重複匯入同一段對話會直接覆蓋，不會重複。
- ChatGPT 只保留你最後瀏覽的那條分支（匯出檔裡存了每一次重新生成的分支）。
- Claude Code 與 Codex 只索引人類與助理的文字。工具呼叫、工具輸出、思考區塊、子 agent 執行緒，以及注入的系統內容（`<system-reminder>`、`<app-context>`、AGENTS.md 指示）全部過濾掉。
- 搜尋結果每段對話只留最佳的一筆。三個字以下的查詢改走 `LIKE`，因為 trigram 分詞至少需要三個字元。

想搬資料庫可以設 `EVERYCHAT_HOME`。`CLAUDE_CONFIG_DIR` 與 `CODEX_HOME` 也會被尊重。

## 規劃中

- [ ] Cursor、Gemini CLI、OpenCode、Aider 的 session 匯入器
- [ ] 監看模式：session 檔一變動就重新索引
- [ ] 極簡的本機網頁介面
- [ ] 把搜尋結果匯出成 Markdown，方便貼進新對話

非常歡迎貢獻新的匯入器。一個匯入器就是一個檔案，實作 `detect()` 和 `parse()` 即可；最短的範例在 [`src/everychat/importers/claude_web.py`](src/everychat/importers/claude_web.py)。

## 隱私

所有東西都留在你的電腦上。資料庫是一個普通的 SQLite 檔，刪掉就沒了。MCP server 只回應你接上的那個 client。

## 授權

MIT
