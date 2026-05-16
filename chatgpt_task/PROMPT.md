# ChatGPT Task Scheduler Prototype

## System Requirements

Build a job scheduler with an MCP (Model Context Protocol) interface:
- Users schedule tasks for future execution via MCP tool calls
- A background watcher scans for due jobs and pushes them to a queue
- Workers pull jobs from the queue and execute them
- Support task creation, listing, status checking, and cancellation
- Tool naming follows namespace + action verb pattern (e.g., `task.create`)

### Architecture

```
User → MCP Tool Call → Job Scheduler API → DB
                                            ↓
                              Watcher (scans DB) → Queue → Worker (executes)
```

## Design Questions

Answer these before you start coding:

1. **Watcher vs Cron:** Why separate the watcher from the worker? What problems does a single cron job that both scans and executes have?
主要是「責任分離」與「可擴展性」的關係。如果單一 job 遇到執行時間很長的任務時，會嚴重影響到 scan 的效率，導致排程出現嚴重的延遲 (Task Starvation)
如果要做架構分離，Watcher 可以保持極度輕量及單一，只需時間到了把 task 送到 queue 就好；而 Worker 可以專注於非同步執行，且負載增加時 worker 可以輕鬆進行水平擴展。

2. **Queue Layer:** Why put a queue between the watcher and worker instead of having the watcher call the worker directly? What are the benefits?
加入 Queue 主要是帶來了「解耦(Decoupling)」與「削峰填谷(Load Leveling)」兩大效益。假如有瞬間的大量排程任務到期，瞬間觸發的時候，如果沒有 queue，worker 很容易遇到瞬間的高併發而耗盡系統資源。
所以透過 Queue，worker 就可以自己依據設定的 concurrency 逐步提取並消化這些任務，而且通常 Queue 會有支援 Retry 與 Dead Letter Queue 的機制，大幅提升後端系統的容錯能力與穩定性。

3. **Time Bucket Partitioning:** Instead of `SELECT * WHERE scheduled_at <= now()`, why partition jobs by time bucket (e.g., hour)? What happens to query performance at 1M+ jobs without partitioning?
如果直接使用 `scheduled_at <= now()` 查詢的話，會導致 Range Query 的搜尋變得太高而容易造成 index 臃腫與 Slow Query 的問題，甚至引發資料庫 lock 的問題。
如果使用 Time Bucket Partitioning 實作，就可以變成單純的 key-value 查詢問題，例如將 scheduled_at 轉成具體的 hour_bucket 欄位(如 `2026-05-16-06`)，watcher 在查詢時就可以退化成精確的「等值查詢」(WHERE bucket_id = '2026-05-16-06')，這樣即便資料庫規模極大，也能保持極低的延遲(Lantency)。

4. **Tool Naming:** Why `task.create` instead of `createTask`? How does naming convention affect LLM tool selection accuracy?
LLM 依賴語意結構與 Token 分詞來理解可用工具，所以使用「命名空間.動作」(如 task.create) 提供了明確的層級與脈絡，對於管理 RAG 與複雜 Prompt 的上下文時極為友善，相比之下， createTask 在分詞器處理時，可能不如 . 分隔符號來得清晰且具有結構性。
清晰的層級命名能幫助 LLM 減少幻覺（Hallucination），讓模型在推論時能清楚識別這是屬於 task 領域下的操作，顯著提升模型選用正確 MCP 工具的準確率。

5. **Registry vs If-Else:** Why use a dictionary registry to route tool calls instead of if-else chains? What happens when you need to add the 20th tool?
如果使用大量的 If-Else 進行路由，會使程式碼的循環複雜度隨著工具數量的增加呈線性上升，在具備一定規模的專案中，大量的 If-Else 結構會變得極度臃腫且難以維護，然後每次新增一個工具就要加 code，也嚴重違反開閉原則 (Open/Closed Principle)。
以 Python 來說，可以使用字典註冊表，例如 Dict[str, Callable] 或 decorator @tool("task.create")，來達成將路由轉換為時間複雜度 O(1) 的操作，且不需要修改路由系統 (Registry Router) 的程式碼，讓系統更具備可維護性與可擴轉性。


## Verification

Your prototype is a real MCP server. Test it with the MCP inspector — no Claude needed.

### 1. Start the server (sanity check)

```bash
python -m app.mcp_server
```

The process should hang waiting on stdin (it's a stdio MCP server — that's correct). Ctrl+C to stop. If you see an `ImportError` or other crash, fix that first.

### 2. Run the MCP inspector

Requires Node.js (uses `npx`).

```bash
npx @modelcontextprotocol/inspector python -m app.mcp_server
```

This opens a browser GUI (usually `http://localhost:5173`).

Steps in the GUI:

1. Click **Connect** -> should show 4 tools: `task.create`, `task.list`, `task.status`, `task.cancel`
2. **task.create** -> fill `description="Summarize tech news"`, `scheduled_at="2025-01-01T00:00:00"` (past time so watcher picks it up immediately) -> **Run Tool** -> response should include `{"job_id": 1, "status": "pending", ...}`
3. Wait ~10 seconds, then **task.status** -> `job_id: 1` -> status should now be `"completed"`
4. **task.create** with future time `"2099-12-31T00:00:00"` -> get `job_id: 2`
5. **task.cancel** -> `job_id: 2` -> status `"cancelled"`
6. **task.list** -> see all your jobs

### 3. (Optional) Connect to Claude Desktop / Claude Code

Once the inspector tests pass, the server is ready. To talk to it through Claude:

**Claude Desktop**: edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and add (use absolute paths):

```json
{
  "mcpServers": {
    "task-scheduler": {
      "command": "/absolute/path/to/scaffold/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/scaffold"
    }
  }
}
```

Restart Claude Desktop fully. The 🔨 icon in the chat input should show 4 tools.

**Claude Code**: edit `~/.claude.json` (top-level `mcpServers` for user scope) with the same block, or run `claude mcp add` from inside `scaffold/`.

Then chat:
> "Schedule a task to review PR #123 tomorrow at 9am."
> -> Claude calls `task.create` -> returns job_id
> "What's the status of that task?"
> -> Claude calls `task.status`

## Suggested Tech Stack

Python + the official `mcp` SDK is recommended (already in `requirements.txt` for the Guided Track). Challenge Track may use any language with an MCP SDK.
