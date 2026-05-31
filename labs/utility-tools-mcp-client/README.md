# Utility Tools MCP Client (Java + Gemini)

A console chat client that drives the
[`utility-tools-mcp`](../utility-tools-mcp) server using **Google Gemini**. Built with
**Spring AI**: it launches the server over stdio, discovers its tools, and runs an interactive chat
loop where Gemini decides which tools to call to answer your questions.

```
you> What's the weather in Hanoi and how much is 100 USD in VND?
bot> It's currently 33°C and partly cloudy in Hanoi. 100 USD is about 2,540,000 VND.
```

## How it works

- `spring-ai-starter-mcp-client` connects to the server (stdio) and exposes its tools as Spring AI
  `ToolCallback`s.
- Gemini is used via its **OpenAI-compatible endpoint**
  (`https://generativelanguage.googleapis.com/v1beta/openai`), so only an API key is needed — no
  GCP project.
- [`ChatRunner`](src/main/java/com/dshouse/mcp/client/ChatRunner.java) attaches the tools to a
  `ChatClient` and runs the REPL. Spring AI handles the tool-calling loop automatically.

## Requirements

- Java 21+, Maven 3.6.3+
- A Google Gemini API key in the `GEMINI_API_KEY` environment variable
- The server jar built first: from `../utility-tools-mcp` run `mvn clean package`

## Build

```bash
mvn clean package
```

Produces `target/utility-tools-mcp-client-0.0.1.jar`.

## Run

Set your key, then run from this project directory (the server-jar path in
`application.properties` is relative: `../utility-tools-mcp/target/utility-tools-mcp-0.0.1.jar`):

```bash
# PowerShell
$env:GEMINI_API_KEY = "your-key"
java -jar target/utility-tools-mcp-client-0.0.1.jar

# bash
export GEMINI_API_KEY="your-key"
java -jar target/utility-tools-mcp-client-0.0.1.jar
```

Type questions at the `you>` prompt; type `exit` to quit.

## Configuration

All settings live in
[`application.properties`](src/main/resources/application.properties):

- `spring.ai.mcp.client.stdio.connections.utils.args` — path to the server jar to launch
- `spring.ai.openai.chat.options.model` — defaults to `gemini-2.5-flash`
- `spring.ai.openai.base-url` / `completions-path` — Gemini's OpenAI-compatible endpoint

To point at a different MCP server, add more `spring.ai.mcp.client.stdio.connections.<name>.*`
entries — all discovered tools are made available to the model.
