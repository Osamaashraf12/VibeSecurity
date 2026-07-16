# VibeSecurity — System Design Document

## 1. Problem Statement

Penetration testing and bug bounty hunting involve a repeating sequence of steps — reconnaissance, attack surface analysis, vulnerability hypothesis, exploitation attempt, and reporting — that require both broad tool knowledge and expert reasoning. This process is time-consuming, inconsistent across practitioners, and inaccessible to less experienced security researchers.

VibeSecurity automates this workflow by combining industry-standard security tooling with AI reasoning, producing structured vulnerability reports from a single target input.

---

## 2. Design Goals

**Primary goals**

- **Autonomous end-to-end scanning** — a user provides a domain; the system produces a vulnerability report with no manual intervention between those two steps.
- **Modular tooling** — each security tool is independently replaceable. Adding a new tool should not require changes to the orchestration layer.
- **Flexible LLM routing** — different pipeline stages have different reasoning requirements. The system should allow any LLM model to be assigned to any stage without code changes.

**Secondary goals**

- Self-hosted and containerised — no external infrastructure dependencies beyond an API key.
- API-first — every feature accessible via REST so it can be embedded in other workflows.
- Accessible to non-experts — a web UI that abstracts CLI complexity.

---

## 3. System Components

### 3.1 FastAPI Backend

The backend is an async FastAPI application. Each feature domain is a separate `APIRouter` registered under a distinct URL prefix. Long-running operations (tool invocations, the Hunter Agent pipeline) are dispatched as background tasks and polled via dedicated status endpoints.

**Routers:**

| Prefix | Responsibility |
|---|---|
| `/api/hunter` | Hunter Agent lifecycle (start, status, report) |
| `/api/chat` | Conversational AI assistant |
| `/api/analyze_traffic` | HTTP traffic vulnerability analysis |
| `/recon` | Reconnaissance tool wrappers |
| `/exploit` | Exploitation and verification modules |
| `/workflow` | Workflow chain execution engine |
| `/recipes` | Saved workflow recipe management |
| `/api/report` | Report retrieval and artifact download |

### 3.2 Hunter Agent (LangGraph Pipeline)

The core feature. A LangGraph state graph that models the penetration testing workflow as a typed DAG. The graph holds a single `AgentState` object that accumulates findings across all nodes.

See `docs/diagrams/hunter_pipeline.svg` for the full node graph.

**Node responsibilities:**

| Node | Type | Responsibility |
|---|---|---|
| `katana` | Tool | Recursive web crawl, HTTP pair capture |
| `synthesizer` | LLM | Endpoint analysis and annotation |
| `cvinder` | Tool + LLM | CVE lookup against detected technology stack |
| `join` | Router | Merges parallel synthesizer and cvinder outputs |
| `threat_modeller` | LLM | OWASP-mapped attack surface assessment |
| `coordinator_dispatch` | Router | Fans out to specialists via `Send()` |
| `auth` | LLM | Authentication and session vulnerabilities |
| `injection` | LLM | SQLi, SSRF, SSTI, command injection |
| `access_control` | LLM | IDOR, privilege escalation, broken object-level auth |
| `business_logic` | LLM | Workflow abuse, race conditions, rule bypasses |
| `client_side` | LLM | XSS, DOM vulnerabilities, CORS misconfiguration |
| `infrastructure` | LLM | Misconfigured headers, exposed panels, takeover |
| `coordinator_checkpoint` | Router | Collects all specialist findings |
| `chainer` | LLM | Builds multi-step attack paths from individual findings |
| `poc_generator` | LLM | Generates proof-of-concept payloads |
| `revisor` | LLM | Deduplicates and validates findings |
| `report_agent` | LLM | Compiles structured vulnerability report |

### 3.3 Tool Wrappers

Python modules in `backend/modules/recon/` and `backend/modules/exploitation/` that wrap CLI tools as subprocess invocations. Each wrapper handles argument construction, stdout capture, output parsing, and error handling. Results are written to `var/scan_results/` as JSON.

**Recon tools:** subfinder, findomain, alterx, puredns, dnsx, httpx, katana, gau, jsluice, gf, uro, trufflehog, ffuf, gobuster

**Exploitation tools:** nuclei (CVE scan, tech scan, misconfig, default credentials, exposed panels, takeover), active HTTP verifiers (JWT, LFI, XSS, HTTP smuggling, open redirect), logic probers (auth bypass, parameter pollution, rate limit)

### 3.4 Tool Registry

A central dictionary mapping tool names to metadata (display name, description, category, expected input schema). Serves three consumers:

- The workflow engine uses it to dispatch steps by name
- The recipe engine validates saved recipes against it
- The frontend Flow Builder fetches it via `GET /api/config/tools` to populate the drag-and-drop node palette

Adding a new tool requires only registering it in the registry; all three consumers gain access automatically.

### 3.5 Frontend

A single-page application in vanilla HTML, CSS, and JavaScript. Each feature is a JS module making REST calls to the backend. The Flow Builder is a drag-and-drop canvas that serialises a node graph into the `OrchestrationPayload` format consumed by `/workflow/execute`.

---

## 4. Key Design Decisions

### 4.1 Belief Store (Shared Agent State)

Each LangGraph node writes findings to a typed `BeliefStore` within the shared `AgentState`, rather than passing free-text between nodes. This means:

- The chainer can query findings across all six specialists by vulnerability class, severity, or endpoint without re-parsing text.
- The revisor can deduplicate across specialists because all findings share a normalised schema.
- The report agent has a single structured source rather than six unstructured text blocks.

**Alternative considered:** chaining prompts with plain text. Rejected because it requires each node to re-parse its inputs, introduces schema drift, and makes cross-specialist deduplication impractical.

### 4.2 Per-Node LLM Configuration

Every LLM call in the Hunter Agent is configured independently via environment variables (e.g., `HUNTER_MODEL_CHAINER`, `HUNTER_MODEL_AUTH`). Each node also has a fallback model that activates on rate limit errors or model unavailability.

**Rationale:** nodes have different reasoning requirements. The synthesizer classifies endpoints mechanically and performs well with small models. The chainer builds multi-step attack paths across a large context and benefits from more capable models. Per-node config allows cost and quality to be optimised independently for each stage.

**Implementation:** `backend/core/llm/model_config.py` reads env vars at startup and builds a typed config object imported by each node.

### 4.3 Parallel Specialist Dispatch via `Send()`

The six specialist agents run concurrently using LangGraph's `Send()` primitive, which creates independent parallel executions of the same graph node with different state payloads. This reduces total pipeline latency from `sum(specialist_times)` to `max(specialist_times)`.

**Alternative considered:** sequential specialist invocation. Rejected because it is approximately 6× slower for no gain in output quality.

### 4.4 Async Background Task Dispatch

All long-running operations (tool invocations, pipeline runs) are dispatched as FastAPI background tasks and tracked by a task manager. Clients receive a task ID immediately and poll for completion via `/status/{task_id}`.

**Rationale:** tool invocations can take 30–300 seconds. Blocking HTTP connections for this duration is impractical. The polling pattern also enables the frontend to display incremental progress.

### 4.5 Docker on Kali Linux

The Docker image uses Kali Linux as the base rather than a minimal distro (Alpine, Debian slim) because Kali's package repositories include many of the required security tools, reducing Dockerfile complexity and ensuring tool version compatibility.

The `var/` directory is volume-mounted so scan results and Hunter Agent sessions persist across container restarts without requiring a database.

---

## 5. Known Limitations

**Tool-chaining I/O normalisation** — the workflow engine can chain any sequence of registered tools, but there is no schema translation layer between steps. Chains that were explicitly designed together work correctly; arbitrary chains of tools with incompatible output/input formats fail silently. The intended fix is a normalisation middleware layer between workflow steps.

**Hunter Agent research phase** — the current pipeline is reactive: it analyses what Katana discovers. It does not yet reason about what is *missing* from the crawl — for example, inferring that an API application with no login endpoint in the results should have common auth paths probed before specialist analysis begins. This "hypothesis-driven crawling" phase is under active design.

**Single-user file system** — scan results are stored in a flat `var/scan_results/` directory with no user isolation. In a multi-user deployment, scans from different users would overwrite each other's results. A session-scoped or user-scoped storage layer is required before multi-user deployment.

**No rate limiting on public routes** — the AI chat and HTTP traffic analyser endpoints are unauthenticated and forward directly to OpenRouter. In a public deployment, these routes would allow unlimited OpenRouter quota consumption by unauthenticated callers.

---

## 6. Future Work

- Research-phase reasoning in the Hunter Agent (hypothesis-driven crawling)
- Tool-chaining I/O format normalisation layer
- User isolation for scan results (session-scoped or user-scoped storage)
- Rate limiting and authentication on public AI routes
- Nuclei template auto-update on container startup
- Structured finding schema versioning for the BeliefStore
- WebSocket-based streaming for real-time pipeline progress (replacing polling)
