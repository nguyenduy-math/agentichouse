# Utility Tools MCP Client (Java, multi-provider)

A console chat client that drives the
[`utility-tools-mcp`](../utility-tools-mcp) server using an LLM. It supports **two
providers — Google Gemini and SiliconFlow** — and lets you choose one at startup and switch between
them mid-session. Built with **Spring AI**: it launches the server over stdio, discovers its tools,
and runs an interactive chat loop where the LLM decides which tools to call.

```
[gemini] you> What's the weather in Hanoi and how much is 100 USD in VND?
bot> It's currently 33°C and partly cloudy in Hanoi. 100 USD is about 2,540,000 VND.
[gemini] you> /use siliconflow
Switched to 'siliconflow'.
[siliconflow] you> ...
```

## How it works

- `spring-ai-starter-mcp-client` connects to the server (stdio) and exposes its tools as Spring AI
  `ToolCallback`s.
- Both providers expose an **OpenAI-compatible API**, so each is built as an `OpenAiChatModel` with
  its own base URL / key / model
  ([`ChatClientConfig`](src/main/java/com/dshouse/mcp/client/config/ChatClientConfig.java)). Only
  providers that have an API key are activated.
- [`ChatRunner`](src/main/java/com/dshouse/mcp/client/ChatRunner.java) runs the REPL, routing each
  message to the active provider's `ChatClient`. Spring AI handles the tool-calling loop.

## Requirements

- Java 21+, Maven 3.6.3+
- The server jar built first: from `../utility-tools-mcp` run `mvn clean package`
- An API key for at least one provider:
  - `GEMINI_API_KEY` — Google Gemini
  - `SILICONFLOW_API_KEY` — SiliconFlow (from <https://cloud.siliconflow.cn>)

  If only one is set, only that provider is available (the other is skipped).

## Build

```bash
mvn clean package
```

Produces `target/utility-tools-mcp-client-0.0.1.jar`.

## Run

Set the key(s), then run from this project directory (the server-jar path in
`application.properties` is relative):

```powershell
# PowerShell
$env:GEMINI_API_KEY = "your-gemini-key"
$env:SILICONFLOW_API_KEY = "your-siliconflow-key"
java -jar target/utility-tools-mcp-client-0.0.1.jar
```

```bash
# bash
export GEMINI_API_KEY="your-gemini-key"
export SILICONFLOW_API_KEY="your-siliconflow-key"
java -jar target/utility-tools-mcp-client-0.0.1.jar
```

### Choosing the provider

- **At startup:** set the default with the `app.llm.default-provider` property, e.g.
  `APP_LLM_DEFAULT_PROVIDER=siliconflow` (env) or `-Dapp.llm.default-provider=siliconflow` (flag).
  Defaults to `gemini`.
- **At runtime:** use the in-chat commands.

### REPL commands

| Command | Description |
|---|---|
| `/use <provider>` | Switch the active provider (`gemini` or `siliconflow`) |
| `/providers` | List configured providers and which are available |
| `/provider` | Show the active provider |
| `/help` | Show command help |
| `exit` | Quit |

## Configuration

All settings live in
[`application.properties`](src/main/resources/application.properties), under `app.llm.*`:

```properties
app.llm.default-provider=gemini

app.llm.providers.gemini.base-url=https://generativelanguage.googleapis.com/v1beta/openai
app.llm.providers.gemini.completions-path=/chat/completions
app.llm.providers.gemini.api-key=${GEMINI_API_KEY:}
app.llm.providers.gemini.model=gemini-2.5-flash

app.llm.providers.siliconflow.base-url=https://api.siliconflow.cn
app.llm.providers.siliconflow.completions-path=/v1/chat/completions
app.llm.providers.siliconflow.api-key=${SILICONFLOW_API_KEY:}
app.llm.providers.siliconflow.model=deepseek-ai/DeepSeek-V3
```

- **Tool calling depends on the model.** MCP tools only fire if the selected model supports
  function/tool calling. `deepseek-ai/DeepSeek-V3` and `Qwen/Qwen2.5-*-Instruct` on SiliconFlow do.
- **Add another provider** by adding a `app.llm.providers.<name>.*` block (any OpenAI-compatible
  endpoint works); it appears automatically in `/providers`.
