# Observing Spring AI Applications with OpenTelemetry

AI applications behave differently from traditional REST services. When a user sends a message, the application may call a language model, retrieve memory from a previous conversation turn, invoke one or more tools, and stream a response back — all as part of a single HTTP request. A latency metric that says "this request took 2.8 seconds" tells you almost nothing useful. Knowing *which* LLM call caused the slowness, how many tokens were consumed, and which tool was invoked — that is actionable information.

This guide walks through a Spring Boot 4 application built with Spring AI, explains how to configure OpenTelemetry for logs, metrics, and traces, and highlights the specific patterns that matter for AI workloads: reactor context propagation, promoting prompts and completions to span attributes, and reading the span hierarchy that emerges from a single chat request.

---

## What is Spring AI?

[Spring AI](https://spring.io/projects/spring-ai) is the Spring project for building AI-powered applications in Java. It provides a unified `ChatClient` abstraction over multiple LLM providers (Anthropic, OpenAI, Vertex AI, and others), along with advisors for memory management, tool/function calling support, and built-in Micrometer instrumentation that follows the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

A Spring AI application introduces execution patterns that have no equivalent in a conventional REST service:

- **Multi-step LLM calls** — a single user request can trigger several model calls if the model decides to invoke a tool
- **Advisor chains** — cross-cutting behaviors (memory, logging, guardrails) wrap every call in a pipeline
- **Streaming responses** — completions arrive as a `Flux<String>`, which crosses thread boundaries
- **Token consumption** — every LLM call has a cost measured in tokens that grows with conversation length

Each of these patterns requires specific observability configuration to be visible in your traces.

---

## The Application: Spring Merch Store

The sample application is an AI-powered store assistant backed by Anthropic's Claude Haiku model. Users interact with it through a streaming chat endpoint. The assistant can look up inventory, display product images, and place orders.

```
POST /api/chat/stream   ← user sends a message, response streams back
POST /api/chat          ← non-streaming variant
```

The core is a `ChatClient` wired with a system prompt, tool definitions, and a per-conversation memory advisor:

```java
@RestController
@RequestMapping("/api/chat")
public class ChatRestController {

    private final ChatClient chatClient;
    private final InMemoryChatMemoryRepository memoryRepository = new InMemoryChatMemoryRepository();

    public ChatRestController(ChatClient.Builder chatClientBuilder, ChatController inventoryTools) {
        this.chatClient = chatClientBuilder
                .defaultSystem(SYSTEM_PROMPT)
                .defaultTools(inventoryTools)
                .build();
    }

    @PostMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> chatStream(@RequestBody ChatRequest request) {
        MessageChatMemoryAdvisor advisor = MessageChatMemoryAdvisor.builder(
                        MessageWindowChatMemory.builder()
                                .chatMemoryRepository(memoryRepository)
                                .build())
                .conversationId(request.conversationId())
                .build();

        return chatClient.prompt()
                .advisors(advisor)
                .user(request.message())
                .stream()
                .content();
    }
}
```

The `ChatController` component exposes four `@Tool`-annotated methods that the model can call:

| Tool | What it does |
|---|---|
| `listAllItems` | Returns the full inventory with prices |
| `getItemStock` | Looks up stock for a specific item |
| `displayMerchImages` | Returns product cards for the frontend |
| `placeOrder` | Places a confirmed order |

This is a realistic pattern: a conversational interface backed by a model that decides when to call which tool based on what the user says. Observability needs to surface exactly those decisions.

---

## Setting Up OpenTelemetry in Spring Boot 4

Spring Boot 4 ships `spring-boot-starter-opentelemetry`, which pulls in the full OpenTelemetry SDK, the Micrometer Tracing bridge, the OTLP exporters for traces, metrics, and logs, and the auto-configuration wiring. The [Spring Boot OpenTelemetry guide](https://spring.io/blog/2025/11/18/opentelemetry-with-spring-boot) covers the full picture; the essentials are two dependencies and a handful of properties.

### Dependencies

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<!-- OpenTelemetry log appender for Logback -->
<dependency>
    <groupId>io.opentelemetry.instrumentation</groupId>
    <artifactId>opentelemetry-logback-appender-1.0</artifactId>
    <version>2.26.1-alpha</version>
</dependency>
<!-- Spring AI with Anthropic model support -->
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-model-anthropic</artifactId>
</dependency>
```

### Configuration

```properties
spring.application.name=spring-merch-store

# --- Tracing ---
# Sample every request during development; lower this in production
management.tracing.sampling.probability=1.0
# Support both W3C traceparent and B3 headers for context propagation
management.tracing.propagation.type=W3C,B3

# OTLP/HTTP export endpoints (Spring Boot 4 namespace — the old management.otlp.tracing.* is removed)
management.opentelemetry.tracing.export.otlp.endpoint=${OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces
management.opentelemetry.tracing.export.otlp.headers.Authorization=Bearer ${OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION}
management.opentelemetry.tracing.export.otlp.headers.Dash0-Dataset=${DASH0_DATASET}

# --- Metrics ---
management.otlp.metrics.export.url=${OTEL_EXPORTER_OTLP_ENDPOINT}/v1/metrics
management.otlp.metrics.export.headers.Authorization=Bearer ${OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION}
management.otlp.metrics.export.headers.Dash0-Dataset=${DASH0_DATASET}

# --- Logs ---
management.opentelemetry.logging.export.otlp.endpoint=${OTEL_EXPORTER_OTLP_ENDPOINT}/v1/logs
management.opentelemetry.logging.export.otlp.headers.Authorization=Bearer ${OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION}
management.opentelemetry.logging.export.otlp.headers.Dash0-Dataset=${DASH0_DATASET}

# Expose all actuator endpoints (useful during development)
management.endpoints.web.exposure.include=*
```

A few things worth noting:

- The `management.opentelemetry.tracing.export.otlp.*` and `management.opentelemetry.logging.export.otlp.*` namespaces are **new in Spring Boot 4**. The old `management.otlp.tracing.*` keys no longer exist.
- Do **not** set `Content-Type` in the headers map. The OTLP/HTTP exporter sets `application/x-protobuf` internally — overriding it breaks serialization.
- Both `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION` must be set as environment variables before the application starts, because the exporter bean only activates when the endpoint property is non-null.

### Wiring the Log Appender

The OTLP log exporter is configured in properties, but Logback's appender needs to be connected to the running `OpenTelemetry` bean at startup:

```java
@Component
class InstallOpenTelemetryAppender implements InitializingBean {

    private final OpenTelemetry openTelemetry;

    InstallOpenTelemetryAppender(OpenTelemetry openTelemetry) {
        this.openTelemetry = openTelemetry;
    }

    @Override
    public void afterPropertiesSet() {
        OpenTelemetryAppender.install(this.openTelemetry);
    }
}
```

This bridges Logback's `OpenTelemetryAppender` (declared in `logback-spring.xml`) to the SDK instance that Spring Boot auto-configured, so log records are correlated with the active trace and span IDs.

### Aligning JVM Metrics with OTel Conventions

Spring Boot exposes JVM metrics through Micrometer, but the default metric names follow Micrometer's naming convention rather than the OpenTelemetry semantic conventions (`process.runtime.jvm.*`). To align them, register the OTel meter conventions explicitly:

```java
@Configuration(proxyBeanMethods = false)
public class OpenTelemetryConfiguration {

    @Bean
    OpenTelemetryServerRequestObservationConvention openTelemetryServerRequestObservationConvention() {
        return new OpenTelemetryServerRequestObservationConvention();
    }

    @Bean
    OpenTelemetryJvmCpuMeterConventions openTelemetryJvmCpuMeterConventions() {
        return new OpenTelemetryJvmCpuMeterConventions(Tags.empty());
    }

    @Bean
    JvmMemoryMetrics jvmMemoryMetrics() {
        return new JvmMemoryMetrics(List.of(), new OpenTelemetryJvmMemoryMeterConventions(Tags.empty()));
    }

    @Bean
    JvmThreadMetrics jvmThreadMetrics() {
        return new JvmThreadMetrics(List.of(), new OpenTelemetryJvmThreadMeterConventions(Tags.empty()));
    }

    @Bean
    ClassLoaderMetrics classLoaderMetrics() {
        return new ClassLoaderMetrics(new OpenTelemetryJvmClassLoadingMeterConventions());
    }
}
```

This ensures the JVM metrics that land in your observability backend use the same names as OTel-native agents, making dashboards and alerts portable.

---

## What Observability Looks Like for Spring AI

Once the OTLP exporter is running, every chat request produces a trace that maps directly onto the Spring AI execution model.

### The Span Hierarchy

For a request that causes the model to call a tool, the trace looks like this:

```
http post /api/chat/stream                          ~2.6 s  ← Servlet request
└── spring_ai chat_client                           ~2.6 s  ← ChatClient.stream()
    └── message_chat_memory (advisor)               ~2.6 s  ← MessageChatMemoryAdvisor
        └── stream                                  ~2.6 s  ← Advisor chain
            ├── chat claude-haiku-4-5               ~1.8 s  ← First LLM call (tool selection)
            ├── tool_call displayMerchImages         <20 ms  ← Tool execution
            └── chat claude-haiku-4-5               ~1.2 s  ← Second LLM call (final response)
```

This hierarchy answers questions that a single latency metric cannot:

- Was the slowness in the HTTP layer, the model, or a tool?
- Which LLM call decided to invoke the tool vs. which one generated the response?
- How much does the memory advisor add to the overall request?

### Spring AI Span Attributes

Spring AI instruments each layer with structured attributes following the OpenTelemetry GenAI semantic conventions.

**On `chat` spans (LLM calls):**

| Attribute | Example | What it tells you |
|---|---|---|
| `gen_ai.system` | `anthropic` | Which provider was called |
| `gen_ai.request.model` | `claude-haiku-4-5` | Model requested |
| `gen_ai.response.model` | `claude-haiku-4-5-20251001` | Exact model version served |
| `gen_ai.request.max_tokens` | `4096` | Token budget |
| `gen_ai.usage.input_tokens` | `1308–3729` | Tokens in the prompt |
| `gen_ai.usage.output_tokens` | `58–457` | Tokens in the completion |
| `gen_ai.response.finish_reasons` | `["end_turn"]` | Why the model stopped |

**On `tool_call` spans:**

| Attribute | Example |
|---|---|
| `spring.ai.tool.definition.name` | `displayMerchImages` |
| `spring.ai.tool.call.arguments` | `{"query": "Spring AI"}` |
| `spring.ai.tool.call.result` | The JSON the tool returned |

**On advisor spans:**

| Attribute | Value |
|---|---|
| `spring.ai.kind` | `advisor` |
| `spring.ai.advisor.name` | `MessageChatMemoryAdvisor` |
| `spring.ai.advisor.order` | `-2147482648` |

---

## Spring AI-Specific Observability Properties

Spring AI 2.0 gates prompt and completion logging behind explicit flags because this data can be sensitive and high-cardinality:

```properties
# Log prompts and completions to the application log
spring.ai.chat.observations.log-prompt=true
spring.ai.chat.observations.log-completion=true
spring.ai.chat.observations.include-error-logging=true
spring.ai.chat.client.observations.log-prompt=true
spring.ai.chat.client.observations.log-completion=true

# Include tool call arguments and results in spans
spring.ai.tools.observations.include-content=true
```

With `spring.ai.tools.observations.include-content=true` you get the exact arguments and return values of every tool call visible in the trace. This is invaluable during development: you can see precisely what data flowed in and out of `displayMerchImages` or `placeOrder` for a specific user request.

> **Note:** `log-prompt` and `log-completion` write to the application log. To get these values as actual span *attributes* (so they're searchable and filterable in your observability backend), you need the custom convention described later in this guide.

---

## Reactor Context Propagation

Spring AI's streaming endpoint returns a `Flux<String>`. Project Reactor processes this on its own thread pool (scheduler), which means the `ThreadLocal` variables that OpenTelemetry uses to track the current span are not automatically carried across thread boundaries.

Without explicit configuration, the child spans inside the `Flux` pipeline — including the LLM call spans and tool call spans — will appear as disconnected orphan traces rather than children of the root HTTP span.

The fix is a single call to `Hooks.enableAutomaticContextPropagation()` at application startup, plus a `ContextPropagatingTaskDecorator` for Spring's task executor:

```java
@Configuration(proxyBeanMethods = false)
public class ContextPropagationConfiguration {

    @PostConstruct
    void enableReactorContextPropagation() {
        Hooks.enableAutomaticContextPropagation();  // bridges ThreadLocal → Reactor Context
    }

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean
    RestClientCustomizer tracePropagationRestClientCustomizer(OpenTelemetry openTelemetry) {
        return builder -> builder.requestInterceptor((request, body, execution) -> {
            openTelemetry.getPropagators().getTextMapPropagator().inject(
                    Context.current(),
                    request.getHeaders(),
                    (headers, key, value) -> headers.set(key, value)
            );
            return execution.execute(request, body);
        });
    }
}
```

`Hooks.enableAutomaticContextPropagation()` tells Reactor to copy the current `io.opentelemetry.context.Context` into the Reactor `Context` when a new `Flux` or `Mono` is subscribed, and to restore it whenever a Reactor operator resumes execution on a thread. This makes OpenTelemetry context propagation work correctly across all Reactor scheduler hops.

The `RestClientCustomizer` injects `traceparent` (W3C) and `b3` headers into every outgoing `RestClient` request, so that downstream services called from tools appear in the same distributed trace rather than as isolated root spans.

---

## Promoting Prompts and Completions to Span Attributes

Spring AI 2.0 logs prompts and completions to the application log when `log-prompt=true`, but it does not include them as span *attributes* by default. Span attributes are indexed and queryable in your observability backend; log lines are not.

To make prompts and completions filterable and searchable within traces, override `ChatModelObservationConvention` to add them as high-cardinality key-values:

```java
@Configuration
public class ChatObservationConventionConfig {

    @Bean
    public ChatModelObservationConvention promptAndCompletionObservationConvention() {
        return new DefaultChatModelObservationConvention() {

            @Override
            public KeyValues getHighCardinalityKeyValues(ChatModelObservationContext context) {
                KeyValues keyValues = super.getHighCardinalityKeyValues(context);

                // Add prompt content as gen_ai.prompt span attribute
                if (!CollectionUtils.isEmpty(context.getRequest().getInstructions())) {
                    String prompt = context.getRequest().getInstructions().stream()
                            .map(Content::getText)
                            .collect(Collectors.joining("\n"));
                    if (StringUtils.hasText(prompt)) {
                        keyValues = keyValues.and("gen_ai.prompt", prompt);
                    }
                }

                // Add completion content as gen_ai.completion span attribute
                if (context.getResponse() != null
                        && !CollectionUtils.isEmpty(context.getResponse().getResults())) {
                    String completion = context.getResponse().getResults().stream()
                            .filter(g -> g.getOutput() != null
                                    && StringUtils.hasText(g.getOutput().getText()))
                            .map(g -> g.getOutput().getText())
                            .collect(Collectors.joining("\n"));
                    if (StringUtils.hasText(completion)) {
                        keyValues = keyValues.and("gen_ai.completion", completion);
                    }
                }

                return keyValues;
            }
        };
    }
}
```

Spring AI picks up any `ChatModelObservationConvention` bean and uses it in place of the default. This is high-cardinality data — the full text of prompts and completions can be kilobytes per request. Keep it disabled in production unless your observability backend indexes it efficiently and you have a data retention policy for it. During development and debugging it is extremely useful for understanding exactly why the model responded a certain way.

---

## Token Usage: The Hidden Cost Dimension

Traditional application monitoring tracks CPU, memory, and network. For AI applications there is a fourth resource: tokens. Token consumption directly translates to cost, and it grows with every conversation turn because `MessageChatMemoryAdvisor` appends the full conversation history to each prompt.

From observed traces of the store assistant:

```
Input tokens:   1,308 → 3,729  (grows as conversation continues)
Output tokens:    58  →   457  (depends on response complexity)
```

That 2.8× growth in input tokens is not a bug — it is the memory advisor doing its job. Without `gen_ai.usage.input_tokens` visible in your traces you would not know this was happening until the model started hitting context window limits or costs started climbing unexpectedly.

Practical alert thresholds:

```
gen_ai.usage.input_tokens  > 3000   # conversation context is growing large
gen_ai.usage.output_tokens > 400    # unusually verbose response
span.duration (chat spans) > 4s     # latency SLO breach
```

---

## Tool Calls in Traces

Tool calls appear as child spans of the LLM interaction span with `spring.ai.kind=tool_call`. You can see exactly which tools were invoked, with what arguments, and what they returned — in the order the model requested them.

For a user message like "show me all Spring AI items", the trace shows:

1. **First LLM call** — model sees available tools in its system context, decides to call `displayMerchImages("Spring AI")`
2. **`tool_call displayMerchImages`** — executes in under 20 ms, returns a JSON payload
3. **Second LLM call** — model receives the tool result and generates the user-facing response

Performance data from real traces:

| Operation | Latency |
|---|---|
| Any tool call | < 20 ms |
| Single LLM call | 1.2 – 2.7 s |
| Full streaming request | 2.6 – 4.0 s |

Tool calls are negligible. LLM calls dominate. If your traces show a tool taking seconds, investigate whether it is making untraced external HTTP calls.

---

## Surfacing the Trace ID to Clients

When a user reports a problem ("my last request returned something strange"), you need a way to correlate their complaint with the exact trace in your backend without asking them to copy a request ID.

The application includes a servlet filter that writes the current trace ID into each HTTP response:

```java
@Component
class TraceIdFilter extends OncePerRequestFilter {

    private final Tracer tracer;

    TraceIdFilter(Tracer tracer) {
        this.tracer = tracer;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String traceId = getTraceId();
        if (traceId != null) {
            response.setHeader("X-Trace-Id", traceId);
        }
        filterChain.doFilter(request, response);
    }

    private @Nullable String getTraceId() {
        TraceContext context = this.tracer.currentTraceContext().context();
        return context != null ? context.traceId() : null;
    }
}
```

The frontend receives `X-Trace-Id` in every response. A user can report the value from their browser's network inspector and support or an operator can go directly to the trace in the observability backend.

---

## Observability Checklist

Here is a summary of what you get without writing any code, what requires configuration, and what requires a small amount of application code.

**Out of the box (zero configuration beyond the starter):**
- HTTP request spans with method, path, and status code
- `ChatClient` spans with streaming flag and tool names
- LLM call spans with model name, token counts, and finish reason
- Tool call spans with tool name
- Advisor spans with advisor name and order

**Requires configuration properties:**
- Tool arguments and results in spans (`spring.ai.tools.observations.include-content=true`)
- Prompt and completion in application logs (`spring.ai.chat.observations.log-prompt/log-completion=true`)

**Requires application code:**
- Reactor context propagation (`Hooks.enableAutomaticContextPropagation()`)
- Trace context forwarding in outgoing `RestClient` requests
- Prompt and completion as span attributes (`ChatModelObservationConvention`)
- OTel-aligned JVM metric names (`OpenTelemetryJvmMemoryMeterConventions` etc.)
- Trace ID returned to clients via response header
- Logback appender wired to the `OpenTelemetry` bean

**Requires alerting rules in your observability backend:**
- `gen_ai.usage.input_tokens` growth (conversation length / cost management)
- `gen_ai.usage.output_tokens` spikes (unexpectedly verbose responses)
- LLM span duration above threshold (model latency SLO)
- Tool call span error status (silent tool failures)

---

## Summary

Spring AI and Spring Boot 4 give you a solid observability foundation out of the box. The span hierarchy that emerges from a single chat request directly reflects the Spring AI execution model: `ChatClient` → advisor chain → LLM call → tool calls. Each layer carries structured attributes following the GenAI semantic conventions.

The configurations that matter specifically for Spring AI applications are:

1. **`Hooks.enableAutomaticContextPropagation()`** — without this, streaming responses fragment your traces across disconnected orphan spans
2. **`ChatModelObservationConvention`** — the only way to get `gen_ai.prompt` and `gen_ai.completion` as indexed, queryable span attributes rather than just log lines
3. **`RestClientCustomizer` with context injection** — required if any tool makes outbound HTTP calls that should appear in the same distributed trace

The most important signals to watch in production are token usage (it grows with conversation length and drives cost), LLM call duration (it dominates end-to-end latency), and tool call error status (failures here silently degrade assistant quality). All three are visible in traces without custom instrumentation, as long as the OTLP exporter is pointed at a backend that understands OpenTelemetry.
