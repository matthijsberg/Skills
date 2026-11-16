# LLM Serving, Model Routing, and Gateway Topologies in Home Assistant Add-ons

A proven architectural pattern for local decision and LLM routing add-ons (such as Laya, Ollama, vLLM, and LiteLLM) serving Home Assistant automations and Hermes Agent.

---

## 1. The Single-Endpoint Constraint in Agent Middleware

Autonomous AI agents (such as Hermes Agent) initialize provider API clients, authentication headers, and network adapters at session startup.
- **What Middleware Can Do:** In-flight request hooks (e.g. `llm_request`) can intercept prompts, evaluate routing heuristics, and rewrite `model` identifiers or reasoning `effort` parameters within the active provider.
- **What Middleware Cannot Do:** Middleware cannot dynamically hot-swap provider adapters or authorization credentials mid-session (e.g. jumping from Google Gemini to Anthropic Claude between turns).

### Architectural Operating Models:

| Topology | Use Case | Mechanism | Trade-offs |
|---|---|---|---|
| **Native Single-Provider** *(e.g. Google Gemini)* | Single-vendor family (Flash Lite, Flash, Pro) | Direct API calls via vendor adapter (`provider: gemini`) | Zero gateway overhead, lowest latency, but confined to one vendor's models. |
| **Unified Gateway Proxy** *(e.g. LiteLLM, OpenRouter)* | Multi-vendor hybrid (Claude for code, Flash for quick, o3-mini for deep) | Agent connects to one OpenAI-compatible endpoint; proxy handles credentials and dispatches downstream | Enables cross-vendor dynamic routing; requires proxy infrastructure and adds slight network hop. |

---

## 2. Exposing Model Catalog & Routing Metadata

Add-on decision engines must expose their active provider and model taxonomy over HTTP so callers can dynamically align without hardcoding:

- **Endpoint Contract (`GET /v1/models`):**
  Returns:
  - `provider`: Active upstream provider (`gemini`, `litellm`, `openrouter`, `custom`).
  - `gateway_url`: Optional proxy endpoint URL when using LiteLLM/OpenRouter.
  - `models`: Dictionary mapping task families (`quick`, `general`, `code`, `deep`) to specific model identifiers.
  - `architecture_limitation_note`: Explicit warning explaining the single-endpoint constraint for human operators.

- **Enriched Per-Turn Decision (`POST /v1/route`):**
  In addition to classification decisions (`family`, `effort`, `confidence`), return the resolved `provider` and concrete `model` identifier mapped to that family. This allows callers to either:
  1. Use their own client-side model mapping based on `family`, OR
  2. Directly forward the resolved `model` name to the provider without duplicate configuration.

---

## 3. Add-on Configuration Schema Design (`config.yaml`)

Allow operators to configure model providers and family mappings directly from the Home Assistant UI:

```yaml
options:
  provider: "gemini"
  model_quick: "gemini-2.5-flash-lite"
  model_general: "gemini-flash-latest"
  model_code: "gemini-flash-latest"
  model_deep: "gemini-2.5-pro"
  gateway_url: ""

schema:
  provider: "list(gemini|litellm|openrouter|custom)"
  model_quick: "str"
  model_general: "str"
  model_code: "str"
  model_deep: "str"
  gateway_url: "str?"
```

Pair this with descriptive field labels in `translations/en.yaml` highlighting that multi-provider setups require a gateway endpoint in the agent configuration.

---

## 4. Generic Add-on Metadata vs. Specific Integration Recipes

When authoring decision routers, AI proxy tools, or model serving add-ons:
- **Keep Add-on Metadata Client-Agnostic:** In `config.yaml` (`name`, `description`), `translations/en.yaml`, and Ingress WebUI headers, describe the add-on generically (e.g. "Local sub-100ms System 1 decision engine for Home Assistant, routing LLM prompts across Gemini, LiteLLM, and OpenRouter"). Never bind the add-on name or manifest description to a single consumer (like Hermes). This preserves broad applicability for Home Assistant automations, Node-RED, scripts, and other agents.
- **Reference Integrations in Documentation:** Put client-specific integration instructions, configuration YAML blocks, and prompt examples in `README.md` and `DOCS.md`.

---

## 5. Handling Oversized Prompts & Tokenizer Latency

When serving transformer-based decision or embedding models with a fixed context window (e.g. 1,024 tokens):
- **The Pitfall:** Relying solely on the model's tokenizer `max_len` truncation causes extreme latency on oversized inputs. If a client submits a 100k-character document or trace dump, the Python/HuggingFace tokenizer tokenizes all 100,000 characters before discarding the excess. On CPU/GPU, this tokenization step alone introduces ~1,800–2,000 ms of pure latency overhead before inference begins.
- **Pre-Tokenization Head+Tail Truncation:** Truncate raw string inputs at the engine formatting layer before passing to the tokenizer. For a 1,024-token (~4,500-char) model:
  ```python
  if len(prompt) > 6000:
      prompt = prompt[:5000] + "\n...[truncated for routing]...\n" + prompt[-1000:]
  ```
  Routing and task classification signals are overwhelmingly concentrated in the head (system/task framing) and tail (final question/output requirements). Truncating at the string boundary reduces total request latency for 100k inputs from ~1.9s down to ~300ms.

---

## 6. Home Assistant Ingress WebUI & Authentication Boundary

When exposing an interactive testing playground or admin dashboard via Home Assistant Ingress (`ingress: true`, `ingress_port: 8000`):
- **The Pitfall:** If the add-on enforces strict Bearer token authentication (`Authorization: Bearer <key>`) for external REST clients, the Ingress iframe in the Home Assistant sidebar will fail with HTTP 401 unless the user manually extracts and injects the token into client-side JS.
- **Trusted Ingress Header Bypass:** Home Assistant Core terminates user authentication before proxying traffic into the add-on container, injecting an `X-Ingress-Path` header on every forwarded request.
- **Pattern:**
  ```python
  def verify_api_key(
      authorization: Optional[str] = Header(default=None),
      x_ingress_path: Optional[str] = Header(default=None),
  ) -> None:
      # Requests proxied through HA Ingress are authenticated by HA Core
      if x_ingress_path:
          return

      # External REST callers must provide configured Bearer token
      if not config.api_key:
          return
      expected = f"Bearer {config.api_key}".encode("utf-8")
      supplied = (authorization or "").encode("utf-8")
      if not hmac.compare_digest(supplied, expected):
          raise HTTPException(status_code=401, detail="Unauthorized")
  ```
- **Air-Gapped UI:** Render the dashboard using pure vanilla HTML, CSS, and JavaScript. Do not depend on external CDNs (Google Fonts, unpkg, cdnjs) so the Ingress panel functions reliably in offline or air-gapped Home Assistant installations.

---

## 7. Dynamic Task Family Collections & Parameter Omission in Add-on Schema

When an add-on router or gateway requires user-configurable routing profiles (e.g. `quick`, `general`, `code`, `deep`, or custom categories like `smarthome`):

### The Fixed-Schema Limitation
- Defining static options in `config.yaml` (`model_quick`, `model_code`) prevents users from introducing custom categories or fine-tuning per-family execution parameters (`temperature`, `max_tokens`, `thinking_budget`) without add-on code changes.

### The Supervisor Dynamic List Schema Pattern
Home Assistant Supervisor's Voluptuous schema parser supports dynamic collections via list-of-objects:

```yaml
options:
  families:
    - name: "quick"
      criteria: "small talk, greetings, simple facts, unit conversions, one-step home control"
      model: "gemini-3.5-flash-lite"
      effort: "low"
      max_tokens: 1024
      temperature: 0.2
      thinking_budget: 0
    - name: "code"
      criteria: "writing or debugging code or configuration files, multi-step tool work"
      model: "gemini-flash-latest"
      effort: "high"
      max_tokens: 8192
      temperature: 0.1

schema:
  families:
    - name: "str"
      criteria: "str"
      model: "str"
      effort: "list(low|medium|high)?"
      max_tokens: "int?"
      temperature: "float?"
      thinking_budget: "int?"
```

- **Home Assistant UI Rendering:** Supervisor renders `families` with a clean "+ ADD" button in the add-on configuration tab, allowing users to define arbitrary new categories without schema violations.

### Dual-Format Normalization in Configuration Loaders
Users may configure `families` either via the HA UI form (which produces a list of dicts) or by writing raw YAML in the editor (which often uses a dict of dicts). In Python, handle both formats seamlessly:

```python
raw_families = data.get("families")
loaded_families = {}

if isinstance(raw_families, list):
    for item in raw_families:
        if isinstance(item, dict) and "name" in item:
            name = str(item["name"]).strip().lower()
            loaded_families[name] = FamilyConfig(...)
elif isinstance(raw_families, dict):
    for name, item in raw_families.items():
        if isinstance(item, dict):
            loaded_families[str(name).strip().lower()] = FamilyConfig(...)
```

### Upstream LLM Parameter Omission Rules
When generating payloads for upstream models (or responses from `/v1/route`), distinguish between explicit constraints and provider defaults:
- **`thinking_budget: 0`:** Strictly disables reasoning tokens for rapid sub-second responses (`quick`).
- **Omitted `thinking_budget` (null):** Allows unconstrained model reasoning without artificial limits (`code`, `deep`).
- **Omitted `temperature` / `max_tokens` (null):** Upstream provider defaults are preserved without modification.
- **Dynamic System 1 Matching:** Dynamically map the configured `criteria` from all defined families into the System 1 choice question at runtime so newly added user categories are immediately evaluated in the single forward pass.

---

## 8. Hermes Plugin Integration & Per-Turn Memoization via llm_request Middleware

When connecting an autonomous agent (like Hermes Agent) to a local Home Assistant decision engine:

### Middleware Contract
Place the plugin under `~/.hermes/profiles/<profile>/plugins/<plugin-name>/` and register the `llm_request` hook in `__init__.py`:
```python
def register(ctx):
    ctx.register_middleware("llm_request", on_llm_request)
```

### The Multi-Step Tool Loop Drift Pitfall
When an agent handles complex turns involving tool calling (where `api_call_count > 1` within the same user turn):
- **The Pitfall:** Re-querying the router on every API request causes the model or parameters to flip mid-turn (e.g. from Flash to Pro or vice versa) as the message history evolves with tool results. This invalidates tool call signatures, breaks prompt caching, and confuses model context.
- **The Solution (Turn Memoization):** Cache routing decisions in an in-memory dictionary keyed by `(session_id, turn_id)`. The first API call of a user turn contacts the decision engine, while all subsequent tool-call continuation requests within that turn replay the memoized decision.

### Fail-Open Resilience & Rollback Options
- **Fail-Open:** Always set a strict timeout on the local decision engine call (e.g. 1.0–1.5s). On timeout, HTTP error, or confidence below threshold, return `None` so Hermes leaves the provider request completely unmodified.
- **Operator Rollback:** Ensure users know how to disable routing in one command:
  1. `hermes plugins disable <plugin-name>`
  2. Or comment out the plugin in `~/.hermes/profiles/<profile>/config.yaml` under `plugins.enabled`
  3. Or remove the directory `~/.hermes/profiles/<profile>/plugins/<plugin-name>`

---

## 9. Observability & Langfuse Trace Synchronization

When routing agent turns dynamically, operators need to inspect routing decisions, confidences, and model assignments directly in their observability platform (such as Langfuse):

### The Middleware vs. Observer Timing Trap
- **The Pitfall:** In Hermes Agent, `llm_request` middleware executes *before* provider request generation and before Langfuse initializes its root span and generations. Attempting to attach metadata directly inside the middleware callback fails because the trace state does not yet exist.
- **Hook Lifecycle Solution:** Register both `llm_request` middleware and post-execution observer hooks in `plugin.yaml`:
  ```yaml
  capabilities:
    provides_middleware:
      - llm_request
    provides_hooks:
      - post_api_request
      - post_llm_call
  ```
- **Post-Execution Trace Attachment:**
  When `post_api_request` or `post_llm_call` fires, the LLM call has completed and Langfuse's trace is fully initialized. Retrieve the memoized decision for `(session_id, turn_id)` and update the root trace:
  ```python
  def on_post_llm_call(*, session_id: str = "", turn_id: str = "", **kwargs: Any) -> None:
      decision = _DECISION_CACHE.get((session_id, turn_id))
      if not decision:
          return
      # Locate active Langfuse state
      for mod in list(sys.modules.values()):
          if hasattr(mod, "_TRACE_STATE") and hasattr(mod, "_STATE_LOCK"):
              with mod._STATE_LOCK:
                  for key, state in mod._TRACE_STATE.items():
                      if (session_id and session_id in key) or (turn_id and turn_id in key):
                          if hasattr(state, "root_span") and hasattr(state.root_span, "update_trace"):
                              state.root_span.update_trace(
                                  metadata={"laya_routing": decision},
                                  tags=["laya-router", str(decision.get("family", ""))]
                              )
                              return
  ```

### Fallback Transparency
When a decision falls below the confidence threshold (e.g. 0.60):
- Do **not** set `decision = None` and discard the prediction.
- Store the prediction with `"routed": false` and an explicit `"fallback_reason": "low_confidence (0.54 < 0.60)"`.
- The middleware still fails open and keeps the default model, but both the local JSONL audit trail and Langfuse trace record the evaluation and the exact reason why the request was not rewritten.



