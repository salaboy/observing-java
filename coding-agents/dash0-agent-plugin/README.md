# Claude Chat Stream Proxy — dash0-agent-plugin variant

Same Go server as `../claude/` (a long-lived `claude` process per session, exposed over a streaming HTTP API), but instead of relying on Claude Code's built-in OpenTelemetry env vars (`CLAUDE_CODE_ENABLE_TELEMETRY`, `OTEL_*`) it ships with the [dash0-agent-plugin](https://github.com/dash0hq/dash0-agent-plugin) installed and pointed at every spawned `claude` session.

The plugin captures tool calls, LLM invocations, token usage, and errors as OTel traces to Dash0.

## Prerequisites

- Go 1.21+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- The dash0-agent-plugin repo cloned somewhere locally (the Dockerfile clones it for you)

## Build

```bash
go build -o claude-proxy .
```

## Run

```bash
./claude-proxy
```

By default the server listens on port `8080`. Override with the `PORT` environment variable.

## API

Identical to the `claude/` proxy:

- `POST /api/chat/stream` — send a prompt; SSE response. `X-Session-ID` header on the response identifies the session for follow-up requests; pass it as `session_id` in the body to continue.
- `DELETE /api/sessions/{sessionID}` — terminate a session.

See `../claude/README.md` for the full request/response shape — it has not changed.

## How it works

The proxy spawns:

```
claude --print --verbose --output-format stream-json --input-format stream-json [--plugin-dir <path>]...
```

When `CLAUDE_PLUGIN_DIR` is set, the proxy appends one `--plugin-dir <path>` argument per comma-separated entry. That tells the Claude CLI to load that directory as a local plugin for the duration of the session, which causes Claude Code to register every hook declared in the plugin's `hooks/hooks.json` (`SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `PermissionRequest`, …). Each event runs the plugin's `on-event.sh`, which downloads (on first run) and invokes the `on-event` binary that ships traces to Dash0 via OTLP.

## dash0-agent-plugin configuration

The plugin reads its configuration from environment variables (or from a `.claude/dash0-agent-plugin.local.md` frontmatter file in the working directory).

| Variable | Required | Description |
|---|---|---|
| `DASH0_OTLP_URL` | yes | Dash0 OTLP endpoint, e.g. `https://ingress.us1.dash0.com` |
| `DASH0_AUTH_TOKEN` | yes | Dash0 auth token |
| `DASH0_DATASET` | no | Dash0 dataset |
| `DASH0_AGENT_NAME` | no | service identifier (default `claude-code`) |
| `DASH0_OMIT_USER_INFO` | no | redact user info |
| `DASH0_OMIT_IO` | no | omit tool input/output payloads |
| `DASH0_DEBUG` | no | log telemetry payloads to stderr |
| `DASH0_DEBUG_FILE` | no | route debug output to a file |

There are no `OTEL_*` or `CLAUDE_CODE_ENABLE_TELEMETRY` env vars to set — the plugin handles OTLP export itself.

## Run locally with Dash0

You first need the plugin cloned somewhere local:

```bash
git clone --depth 1 --branch v0.1.2 \
  https://github.com/dash0hq/dash0-agent-plugin.git /tmp/dash0-agent-plugin
```

Then:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export CLAUDE_PLUGIN_DIR=/tmp/dash0-agent-plugin
export DASH0_OTLP_URL=https://ingress.us1.dash0.com
export DASH0_AUTH_TOKEN=<your-dash0-token>
export DASH0_DATASET=claude

./claude-proxy
```

## Docker

### Build the image

```bash
docker build -t claude-proxy-dash0-plugin .
```

The Dockerfile:

- Clones `dash0hq/dash0-agent-plugin` (pinned via the `DASH0_PLUGIN_REF` build arg, default `v0.1.2`) into `/opt/dash0-agent-plugin`.
- Sets `CLAUDE_PLUGIN_DIR=/opt/dash0-agent-plugin` so every spawned `claude` session loads the plugin.

Override the pinned plugin version at build time:

```bash
docker build --build-arg DASH0_PLUGIN_REF=v0.1.2 -t claude-proxy-dash0-plugin .
```

### Run the container

```bash
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e DASH0_OTLP_URL=https://ingress.us1.dash0.com \
  -e DASH0_AUTH_TOKEN=<your-dash0-token> \
  -e DASH0_DATASET=claude \
  claude-proxy-dash0-plugin
```

## Examples

```bash
# Start a new conversation
curl -N -X POST http://localhost:8080/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Hello, what can you do?"}'

# Continue (use X-Session-ID from the previous response header)
curl -N -X POST http://localhost:8080/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Tell me more", "session_id":"<id>"}'

# End a session
curl -X DELETE http://localhost:8080/api/sessions/<id>
```
