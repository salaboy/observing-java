# --- Build stage ---
FROM golang:1.24-bookworm AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o claude-proxy .

# --- Runtime stage ---
FROM node:22-bookworm-slim

# Tools needed to fetch the dash0-agent-plugin and the on-event binary it
# downloads on first run.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code globally via npm
RUN npm install -g @anthropic-ai/claude-code@2.1.119

# Pin the dash0-agent-plugin version so image builds are reproducible.
ARG DASH0_PLUGIN_REF=v0.1.2
RUN git clone --depth 1 --branch ${DASH0_PLUGIN_REF} \
    https://github.com/dash0hq/dash0-agent-plugin.git \
    /opt/dash0-agent-plugin

# Copy the Go binary from the build stage
COPY --from=builder /app/claude-proxy /usr/local/bin/claude-proxy

# Tell the proxy to load the plugin into every claude CLI session via
# `--plugin-dir`. Hooks declared in the plugin's hooks/hooks.json are picked
# up automatically when the plugin directory is registered.
ENV CLAUDE_PLUGIN_DIR=/opt/dash0-agent-plugin

# Pass ANTHROPIC_API_KEY at runtime via: docker run -e ANTHROPIC_API_KEY=sk-ant-...
#
# Configure the dash0-agent-plugin via these env vars (read by the plugin's
# on-event hook script — see https://github.com/dash0hq/dash0-agent-plugin):
#   DASH0_OTLP_URL    (required) e.g. https://ingress.us1.dash0.com
#   DASH0_AUTH_TOKEN  (required) Dash0 auth token
#   DASH0_DATASET     (optional) Dash0 dataset
#   DASH0_AGENT_NAME  (optional) defaults to "claude-code"

EXPOSE 8080

ENTRYPOINT ["claude-proxy"]
