# VibeSecurity

> An AI-powered web application security testing platform for bug bounty hunters and penetration testers.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.4+-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/docker-Kali%20Linux-blue.svg)](https://www.docker.com/)

VibeSecurity is an autonomous security reconnaissance and vulnerability hunting platform. It combines a multi-agent LLM pipeline (the **Hunter Agent**) with a suite of battle-tested open-source security tools to crawl, analyse, and report on web application attack surfaces — all driven from a clean web UI.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Docker (Recommended)](#docker-recommended)
  - [Manual Setup](#manual-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Entry Points](#api-entry-points)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## Features

### Hunter Agent (Autonomous AI Pipeline)
A fully autonomous LangGraph multi-agent system that takes a target domain and produces a structured vulnerability report with zero manual intervention.

- **Katana web crawler** — deep crawl of HTTP endpoints and JS files
- **Parallel analysis fork** — Synthesizer (LLM endpoint analysis) and CVINDER (CVE lookup) run concurrently
- **Threat Modeller** — LLM-driven OWASP-mapped threat surface assessment
- **6 Specialist AI Agents** dispatched in parallel:
  - `auth` — Authentication & session vulnerabilities
  - `injection` — SQLi, SSTI, command injection, SSRF
  - `access_control` — IDOR, privilege escalation, broken object-level auth
  - `business_logic` — Workflow abuse, race conditions, business rule bypasses
  - `client_side` — XSS, prototype pollution, DOM-based vulnerabilities
  - `infrastructure` — Misconfigurations, exposed services, subdomain takeover
- **Attack Chainer** — chains multi-step exploits from individual findings
- **PoC Generator** — generates working proof-of-concept payloads
- **Revisor** — cross-validates and deduplicates findings
- **Report Agent** — produces a structured, human-readable vulnerability report

### Reconnaissance
Modular wrappers around industry-standard tools:

| Category | Tools |
|---|---|
| Subdomain enumeration | subfinder, findomain, alterx, puredns |
| DNS resolution | dnsx |
| HTTP probing | httpx |
| Web crawling | katana, gau, gobuster, ffuf |
| JS analysis | jsluice, js-beautifier |
| Secret detection | trufflehog |
| Pattern matching | gf (with custom patterns) |
| URL deduplication | uro |

### Exploitation Modules
- **Active Verifiers** — confirm findings with live HTTP probes: JWT misconfigurations, LFI, XSS, HTTP request smuggling, open redirect
- **Logic Probers** — test business logic flaws: auth bypass, parameter pollution, rate limit bypass
- **Nuclei Integration** — CVE scanning, technology fingerprinting, default credentials, misconfiguration detection, exposed admin panels, subdomain takeover checks

### AI Chat
Interactive security assistant powered by OpenRouter — ask questions about findings, get remediation advice, or explore attack vectors conversationally.

### Workflow & Recipe Engine
Build, save, and reuse named scan recipes that chain multiple tools together — define your own standard recon methodology and replay it on any target.

### Automated Reporting
Generate structured vulnerability reports from scan results with severity ratings and remediation guidance.

### Web UI
A self-hosted, browser-based interface for managing scans, reviewing results, interacting with the AI, and downloading reports.

---

## Architecture

### Hunter Agent Pipeline

The Hunter Agent is a **LangGraph state graph** that wires together AI reasoning and security tooling in a structured pipeline:

```
                     ┌─────────────────────────────────────────┐
START ──► katana ───►│  Parallel Fork                          │
                     │  synthesizer ──────────────────┐        │
                     │  cvinder   ────────────────────┤        │
                     └────────────────────────────────┼────────┘
                                                      ▼
                                                    join
                                                      │
                                                      ▼
                                             threat_modeller
                                                      │
                                                      ▼
                                           coordinator_dispatch
                                                      │
                    ┌─────────────────────────────────┼─────────────────────────────────┐
                    │         Specialist Fan-out (parallel Send())                       │
                    ▼         ▼            ▼              ▼           ▼           ▼      │
                  auth   injection  access_control  business_logic client_side infra     │
                    └─────────────────────────────────┬─────────────────────────────────┘
                                                      ▼
                                           coordinator_checkpoint
                                                      │
                                             chainer ──► poc_generator ──► revisor ──► report_agent ──► END
```

### Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Agent Orchestration | LangGraph ≥ 0.4 |
| LLM Gateway | OpenRouter API (configurable per node) |
| Local LLM (optional) | Ollama |
| Security Tools | ProjectDiscovery suite + Kali tooling |
| Frontend | Vanilla HTML / CSS / JS |
| Containerisation | Docker (Kali Linux base) |

---

## Prerequisites

### Docker path (recommended)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- An [OpenRouter API key](https://openrouter.ai/) (free tier available)

### Manual path
- Python 3.11+
- Kali Linux or any Debian-based Linux distro (for tool availability)
- Go 1.21+ (for Go-based tools)
- All security tools listed in `recon_requirements.txt`
- An [OpenRouter API key](https://openrouter.ai/)

> **Note:** The Docker image handles all tool installation automatically. Manual setup requires installing each tool individually — see `recon_requirements.txt` for the full list and install commands.

---

## Installation

### Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone https://github.com/Osamaashraf12/VibeSecurity.git
   cd VibeSecurity
   ```

2. **Configure your environment**
   ```bash
   cp .env.example .env
   # Edit .env and set your OPENROUTER_API_KEY
   ```

3. **Build and start the container**
   ```bash
   docker compose up --build
   ```

4. **Open the UI**
   ```
   http://localhost:8000
   ```

The `var/` directory is volume-mounted, so scan results and sessions persist across container restarts.

---

### Manual Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Osamaashraf12/VibeSecurity.git
   cd VibeSecurity
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt -r worker_requirements.txt
   ```

4. **Install security tools**
   Follow the instructions in `recon_requirements.txt` to install each tool. All tools must be on your `$PATH`.

   ```bash
   # Quick check once tools are installed
   # The /recon/health endpoint will tell you which tools are found
   ```

5. **Install GF patterns**
   ```bash
   chmod +x setup_gf.sh
   ./setup_gf.sh
   ```

6. **Configure your environment**
   ```bash
   cp .env.example .env
   # Edit .env — see the Configuration section below
   ```

7. **Start the server**
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```

8. **Open the UI**
   ```
   http://localhost:8000
   ```

---

## Configuration

All configuration is managed through environment variables in the `.env` file. Copy `.env.example` and fill in your values.

### Required

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | Your OpenRouter API key — **required** for the Hunter Agent and AI features |

### LLM Model Selection

Each node in the Hunter Agent pipeline uses its own independently configurable LLM. This allows you to assign cheaper/faster models to simpler nodes and more capable models where it matters.

```env
# Primary model per node
HUNTER_MODEL_THREAT_MODELLER=openai/gpt-4o-mini
HUNTER_MODEL_COORDINATOR=openai/gpt-4o
HUNTER_MODEL_AUTH=anthropic/claude-3-haiku
HUNTER_MODEL_INJECTION=anthropic/claude-3.5-sonnet
# ... (see .env.example for full list)

# Fallback model if the primary fails (rate limits, deprecation, etc.)
HUNTER_FALLBACK_AUTH=openai/gpt-4o-mini
# ...
```

All model strings use [OpenRouter's model IDs](https://openrouter.ai/models). Free-tier models are available and set as the default in `.env.example`.

### Optional: Local LLM via Ollama

```env
OLLAMA_URL_MAIN=http://localhost:11434
OLLAMA_URL_HACKER=http://localhost:11434
```
> **Note:** When running the server, it automatically connects to the current Ollama URL. This is done automatically if you are already running the [Ollama_Cloudflare_serving.ipynb](colab_cloud/Ollama_Cloudflare_serving.ipynb) notebook.

### Path Configuration

```env
VIBESEC_STATIC_DIR=data/static   # GF patterns, payloads, prompts
VIBESEC_RUNTIME_DIR=var          # Scan results, sessions, logs
```

## Usage

### Hunter Agent (Autonomous Scan)

The Hunter Agent is the core feature — a single target in, a full report out.

**Via the Web UI:**
1. Navigate to the Hunter tab
2. Enter a target domain (e.g., `demo.owasp-juice.shop`)
3. Click **Start Hunt**
4. Monitor progress in real-time; the report appears when complete

**Via the API:**
```bash
# Start a scan
curl -X POST http://localhost:8000/api/hunter/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"target": "demo.testfire.net"}'

# Poll session status
curl http://localhost:8000/api/hunter/session/{session_id} \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Reconnaissance Modules

```bash
# Check which tools are installed
curl http://localhost:8000/recon/health \
  -H "Authorization: Bearer YOUR_API_KEY"

# Run subdomain enumeration
curl -X POST http://localhost:8000/recon/subfinder \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target": "example.com"}'
```

### Example Targets (Safe to Test Against)

The following are intentionally vulnerable apps safe for testing:

```
zero.webappsecurity.com
demo.testfire.net
demo.owasp-juice.shop
```

Interactive API docs (Swagger / ReDoc) are available at `http://localhost:8000/docs` and `http://localhost:8000/redoc` once the server is running.

---

## API Entry Points

This section covers every surface where VibeSecurity accepts user input — both the web UI and the HTTP API — including the exact request schema, authentication requirement, and what each input flows into.

### 1. Web UI

**`GET /`** — serves `frontend/templates/index.html`

The single-page application is the primary interface for all features. User input in the UI is translated to the API calls described below. Each tab in the UI maps to a backend domain:

| UI Tab | Calls |
|---|---|
| Hunter | `/api/hunter/start`, `/api/hunter/status/{id}`, `/api/hunter/report/{id}` |
| AI Chat | `/api/chat` |
| HTTP Analyser | `/api/analyze_traffic` |
| Recon | `/recon/asset/*`, `/recon/content/*` |
| Exploit | `/exploit/*` |
| Flow Builder | `/api/config/tools`, `/workflow/execute` |
| Recipes | `/recipes/*` |
| Reporting | `/api/report/*`, `/report/generate` |

---

### 2. Hunter Agent

The main autonomous pipeline. One target string in; a structured vulnerability report out.

**`POST /api/hunter/start`**

```json
{
  "target": "demo.testfire.net"
}
```

`target` is the domain or host to scan. It is passed directly to Katana for crawling, then flows through the entire LangGraph pipeline (synthesizer → threat modeller → 6 specialist agents → chainer → PoC generator → report).

**`GET /api/hunter/status/{session_id}?cursor=0`**

Polls pipeline progress. `cursor` is the index of the last log entry the client has seen — pass the `next_cursor` from the previous response to receive only new entries. Returns `complete: true` when the pipeline finishes.

**`GET /api/hunter/report/{session_id}`**

Returns the final report once `complete` is `true`. Returns `202` while still running.

---

### 3. AI Chat

A conversational security assistant.

**`POST /api/chat`**

```json
{
  "message": "What does a JWT none-algorithm attack look like?"
}
```

`message` is a freeform string. It is sent to the LLM client (Ollama) with the `chat` persona.

---

### 4. HTTP Traffic Analyser

Paste a raw HTTP request/response pair and get an AI-generated vulnerability analysis.

**`POST /api/analyze_traffic`**

```json
{
  "http_request":  "GET /api/users/1 HTTP/1.1\r\nHost: target.com\r\n...",
  "http_response": "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n...",
  "analysis_type": "manual"
}
```

| Field | Type | Max length | Description |
|---|---|---|---|
| `http_request` | string | 500,000 chars | Raw HTTP request including headers and body |
| `http_response` | string | 500,000 chars | Raw HTTP response including headers and body |
| `analysis_type` | string | — | `manual` (all vulns), `pipeline` (logic flaws only), `auth_only` (auth/authz only). Defaults to `manual` |

The pair is sent to OpenRouter for a single-pass vulnerability scan. After the Markdown report is generated, a second LLM call (using the fallback/lighter model to conserve quota) converts the output to structured JSON and saves it as `var/scan_results/http_report.json`.

---

### 5. Reconnaissance

All recon endpoints share the same request schema:

```json
{
  "target": "example.com",
  "options": {}
}
```

`target` is the domain or URL. `options` is a pass-through dict forwarded to the underlying tool wrapper — valid keys depend on the specific module (see the individual wrapper files in `backend/modules/recon/`).

| Endpoint | Tool invoked | Input consumed |
|---|---|---|
| `POST /recon/asset/subdomain-enum` | subfinder + findomain | Domain → subdomains list |
| `POST /recon/asset/subdomain-brute` | puredns + ffuf | Domain + wordlist → brute-forced subdomains |
| `POST /recon/asset/subdomain-permute` | alterx | Existing subdomains → permutations |
| `POST /recon/asset/subdomain-check` | dnsx + httpx | Subdomain list → live hosts |
| `POST /recon/content/tech-detect` | httpx fingerprinting | Live hosts → tech stack |
| `POST /recon/content/crawl` | katana + gau | Live host → URLs and HTTP pairs |
| `POST /recon/content/js-analyze` | jsluice + js-beautifier | Crawled URLs → JS secrets and endpoints |
| `POST /recon/content/link-analyze` | gf + uro | Crawled URLs → interesting parameter patterns |

**`GET /recon/health`** — returns which CLI tools are on `$PATH`.

**`GET /recon/tools`** — returns the full tool registry.

---

### 6. Exploitation

**`POST /exploit/vuln-scan`**

```json
{
  "target": "https://example.com",
  "options": { "tools": ["tech_cve_scan", "misconfiguration_scan"] }
}
```

Runs Nuclei-based scans. The `tools` option selects which Nuclei wrappers to invoke: `tech_cve_scan`, `tech_scan`, `default_credentials`, `misconfiguration_scan`, `exposed_panels`, `takeover_checker`. Omit `tools` to run all.

**`POST /exploit/active-verify`**

```json
{
  "target": "https://example.com",
  "options": { "tools": ["xss_verifier", "lfi_verifier"] }
}
```

Runs active HTTP-probe verifiers. Available verifiers: `jwt_verifier`, `lfi_verifier`, `xss_verifier`, `smuggle_verifier`, `redirect_verifier`.

**`POST /exploit/ai-hacker`**

```json
{
  "target": "https://example.com",
  "options": {}
}
```

Loads previously crawled Katana output for the target, then invokes the AI Hacker module to generate attack payloads against the discovered endpoints.

---

### 7. Workflow Engine

Executes an arbitrary ordered chain of tools in a single API call. This is the backend that powers both the Flow Builder UI and Recipe execution.

**`POST /workflow/execute`**

```json
{
  "workflow_id": "my-recon-chain-001",
  "target": "example.com",
  "source": "manual_selection",
  "steps": [
    {
      "tool_name": "sub_enumer",
      "arguments": { "target": "example.com" }
    },
    {
      "tool_name": "sub_checker",
      "arguments": { "target": "example.com" }
    }
  ]
}
```

| Field | Description |
|---|---|
| `workflow_id` | Unique string for tracking this run |
| `target` | Primary target domain |
| `source` | Origin label — `ai_parser`, `manual_selection`, or `workflow_builder` |
| `steps` | Ordered list of `{ tool_name, arguments }` objects. `tool_name` must match a key in the tool registry |

Each step is dispatched as a background task; poll `/status/{task_id}` or `/status/chain/{chain_id}` for progress.

---

### 8. Recipe Engine

Recipes are saved workflow chains that can be replayed against any target.

**`POST /recipes/save`**

```json
{
  "recipe_name": "Full Recon",
  "description": "Subdomain enum → live check → crawl → JS analysis",
  "steps": [
    { "tool_name": "sub_enumer", "arguments": {} },
    { "tool_name": "sub_checker", "arguments": {} },
    { "tool_name": "sub_crawler", "arguments": {} },
    { "tool_name": "js_analyzer", "arguments": {} }
  ]
}
```

**`GET /recipes/list`** — returns all saved recipes.

**`POST /recipes/execute/{recipe_id}`**

```json
{
  "target": "example.com"
}
```

Fetches the saved recipe by ID, injects `target` into every step, and hands the resulting `OrchestrationPayload` to the workflow engine.

**`DELETE /recipes/{recipe_id}`** — deletes a recipe.

---

### 9. Reporting

**`POST /report/generate`**

```json
{
  "target": "example.com"
}
```

Reads all scan output files from `var/scan_results/` for the given target, consolidates them into a single `report.json`, and returns the report.

| Endpoint | Description |
|---|---|
| `GET /api/report` | Returns `var/scan_results/report.json` (consolidated recon + exploit report) |
| `GET /api/report/http` | Returns the last HTTP traffic analysis report |
| `GET /api/report/hunter` | Returns the last Hunter Agent report |
| `GET /api/report/artifacts` | Lists every file in `var/scan_results/` with size and type metadata |
| `GET /api/report/download/{filepath}` | Streams a specific artifact file. `filepath` is relative to `var/scan_results/` — path traversal is blocked |

---

### 10. System & Status

| Endpoint | Description |
|---|---|
| `GET /api/quota/status` | Returns current OpenRouter API quota usage |
| `GET /api/config/tools` | Returns the full tool registry as structured JSON for the Flow Builder |
| `GET /status/{task_id}` | Polls the status of a single background task |
| `GET /status/chain/{chain_id}` | Polls the status of a multi-step workflow chain |

---

## Project Structure

```
VibeSecurity/
├── backend/
│   ├── main.py                        # FastAPI app entry point
│   ├── api/                           # Route handlers
│   │   ├── routes_ai.py               # AI chat & HTTP pair analysis
│   │   ├── routes_hunter.py           # Hunter Agent endpoints
│   │   ├── routes_recon.py            # Recon tool endpoints
│   │   ├── routes_scan.py             # Exploitation endpoints
│   │   ├── routes_report.py           # Report generation
│   │   ├── routes_recipes.py          # Scan recipe management
│   │   ├── routes_workflow.py         # Workflow chain engine
│   │   └── routes_config.py           # Model/config management
│   ├── agents/
│   │   └── hunter_agent/
│   │       ├── graph.py               # LangGraph state machine definition
│   │       ├── hacker_agent.py        # Session manager & pipeline runner
│   │       ├── state.py               # Shared agent state schema
│   │       ├── belief_store.py        # Structured finding accumulator
│   │       ├── knowledge_graph.py     # Attack surface graph
│   │       ├── nodes/                 # Individual pipeline nodes
│   │       │   ├── katana_node.py     # Web crawler node
│   │       │   ├── synthesizer.py     # Endpoint analysis node
│   │       │   ├── cvinder_node.py    # CVE lookup node
│   │       │   ├── coordinator.py     # Specialist dispatch & checkpoint
│   │       │   ├── threat_modeller.py # OWASP threat mapping
│   │       │   ├── chainer.py         # Attack chain builder
│   │       │   ├── poc_generator.py   # PoC payload generator
│   │       │   ├── revisor.py         # Finding validator
│   │       │   ├── report_agent.py    # Report synthesis
│   │       │   └── specialists/       # 6 parallel specialist agents
│   │       ├── prompts/               # System & user prompts per node
│   │       └── utils/                 # HTTP helpers, token counting
│   ├── core/
│   │   ├── openrouter_client.py       # OpenRouter LLM client
│   │   ├── llm_client.py              # Ollama LLM client
│   │   ├── orchestration.py           # Tool orchestration engine
│   │   ├── schemas.py                 # Pydantic data models
│   │   ├── task_manager.py            # Background task management
│   │   ├── registry.py                # Tool plugin registry
│   │   └── llm/
│   │       └── model_config.py        # Per-node model configuration
│   └── modules/
│       ├── exploitation/
│       │   ├── active_verifiers/      # JWT, LFI, XSS, smuggling, redirect
│       │   ├── logic_probers/         # Auth bypass, param pollution, rate limits
│       │   ├── nuclei/                # Nuclei scan wrappers
│       │   └── payload_generation.py  # Dynamic payload generation
│       ├── recon/
│       │   ├── asset/                 # Subdomain & DNS tools
│       │   └── content/               # Crawler & JS analysis tools
│       └── reporting/
│           └── report_builder.py      # Report formatting
├── frontend/
│   ├── templates/index.html           # Single-page application
│   └── static/
│       ├── css/                       # Styles
│       └── js/                        # Feature modules (chat, scan, flow, etc.)
├── data/
│   └── static/
│       ├── gf_patterns/               # Custom GF grep patterns
│       ├── payloads/                  # Static payload lists
│       └── prompts/                   # Static system prompts
├── var/                               # Runtime output (gitignored)
│   ├── scan_results/                  # Tool output JSON
│   ├── hunter_sessions/               # Agent session snapshots
│   ├── generated_payloads/            # Dynamic PoC outputs
│   └── logs/                          # LLM call logs (JSONL)
├── colab_cloud/                       # Ollama + Cloudflare tunnel notebook
├── docs/                              # Technical documentation & architecture diagrams
│   ├── system_design.md               # System design documentation
│   └── diagrams/                      # Architecture & sequence diagrams
│       ├── system_architecture.png    # System architecture diagram
│       ├── hunter_pipeline.png        # Hunter pipeline graph diagram
│       └── data_flow.png              # End-to-end data flow diagram
├── Dockerfile                         # Kali Linux image with all tools
├── docker-compose.yaml
├── requirements.txt                   # Core Python dependencies
├── worker_requirements.txt            # Worker Python dependencies
├── recon_requirements.txt             # CLI tool install instructions
└── .env.example                       # Environment variable template
```

---

## Documentation

The `docs/` directory contains technical documentation and architecture diagrams.

| File | Description |
|---|---|
| [`docs/system_design.md`](docs/system_design.md) | Problem statement, design goals, component breakdown, key architectural decisions, and known limitations |
| [`docs/diagrams/system_architecture.png`](docs/diagrams/system_architecture.png) | Structural diagram: Docker container, internal components, and external dependencies |
| [`docs/diagrams/hunter_pipeline.png`](docs/diagrams/hunter_pipeline.png) | Full LangGraph node graph for the Hunter Agent pipeline |
| [`docs/diagrams/data_flow.png`](docs/diagrams/data_flow.png) | End-to-end data flow from user input to client response |

---

## Contributing

Contributions are welcome! Here's how to get involved:

1. **Fork** the repository
2. **Create a branch** for your feature or fix
   ```bash
   git checkout -b feat/your-feature-name
   ```
3. **Make your changes** and write clear, concise commit messages
4. **Test your changes** against intentionally vulnerable targets (see the examples above)
5. **Open a Pull Request** describing what you changed and why

### Areas for Contribution

- New tools in `backend/modules/`
- New scanning recipes
- Additional specialist agents or pipeline nodes
- Better AI-hunter orchestration
- Better AI-hunter harnessing
- Frontend UI improvements
- Documentation improvements
- Bug fixes

### Code Style

- Follow existing module patterns (each tool wrapper should have a consistent interface)
- Add docstrings to new classes and functions
- Keep LLM prompts in the `prompts/` directory, not inline in node logic
- Do not commit `.env` files or runtime output under `var/`

---

## Disclaimer

> **For authorised security testing only.**

VibeSecurity is designed for use by security professionals, bug bounty hunters, and penetration testers conducting authorised assessments. **You are solely responsible for ensuring you have explicit written permission from the target system owner before running any scans.**

Unauthorised security testing is illegal in most jurisdictions and may violate computer fraud laws including but not limited to the Computer Fraud and Abuse Act (CFAA) in the US and the Computer Misuse Act in the UK.

The developers of VibeSecurity accept no liability for misuse of this tool.

**Only test systems you own or have been given explicit, documented permission to test.**