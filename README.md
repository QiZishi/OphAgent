<p align="center">
  <img src="figures/system_logo.png" width="120" alt="OphAgent system logo">
</p>

<h1 align="center">OphAgent · “LingTong” Ophthalmic Intelligent Diagnosis System</h1>

<p align="center"><strong>A durable, safety-gated and streaming ophthalmic Agent workspace</strong></p>

<p align="center">
  <a href="README.md">English</a> · <a href="README_zh.md">简体中文</a>
</p>

<p align="center">
  <a href="https://qizishi.github.io/OphVLM-R1/"><img src="https://img.shields.io/badge/Project-Page-2b6cb0?style=for-the-badge" alt="Project page"></a>
  <a href="https://github.com/QiZishi/OphAgent/"><img src="https://img.shields.io/badge/Code-OphAgent-181717?style=for-the-badge&logo=github" alt="OphAgent code"></a>
</p>
<p align="center">
  <a href="https://huggingface.co/QiZishi/OphVLM-R1"><img src="https://img.shields.io/badge/🤗%20Model-Hugging%20Face-FFD21E?style=for-the-badge" alt="Model on Hugging Face"></a>
  <a href="https://www.modelscope.cn/models/MoonNight/OphVLM-R1"><img src="https://img.shields.io/badge/Model-ModelScope-624AFF?style=for-the-badge" alt="Model on ModelScope"></a>
</p>
<p align="center">
  <a href="https://huggingface.co/datasets/QiZishi/OphReason-Vision"><img src="https://img.shields.io/badge/🤗%20Dataset-Hugging%20Face-FFD21E?style=for-the-badge" alt="Dataset on Hugging Face"></a>
  <a href="https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision"><img src="https://img.shields.io/badge/Dataset-ModelScope-624AFF?style=for-the-badge" alt="Dataset on ModelScope"></a>
</p>

## Project Links

- **Project page**: <https://qizishi.github.io/OphVLM-R1/>
- **OphAgent system code**: [GitHub](https://github.com/QiZishi/OphAgent/)
- **OphVLM-R1 model**: [Hugging Face](https://huggingface.co/QiZishi/OphVLM-R1) | [ModelScope](https://www.modelscope.cn/models/MoonNight/OphVLM-R1)
- **OphReason-Vision dataset**: [Hugging Face](https://huggingface.co/datasets/QiZishi/OphReason-Vision) | [ModelScope](https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision)

## News

- **2026.07.29** 🚀 **OphAgent 2.0 released** with a durable Agent runtime, typed DAG orchestration, SSE response streaming, evidence governance, multimodal plugins, project workspaces, medical safety gates and a governed self-evolution Harness.

- **2026.07.07** 🎉 Paper “OphVLM-R1: Efficient Ophthalmic Reasoning via Curriculum Reinforcement Learning” accepted by **WAICA 2026**!
  - 📖 Conference: <https://waica2026.worldaic.com.cn/>

- **2025.12.09** 🎉 **Exciting News!** The “LingTong” Ophthalmic Intelligent Diagnosis System has been featured and promoted by Shanghai AI Laboratory and awarded the **Outstanding Project of InternLM Practical Camp**!
  - 📖 Featured Article: <https://mp.weixin.qq.com/s/BTZPUrVtD8nCS_yMwDhhUQ>

- **2025.11.28** 📊 The high-quality ophthalmic multimodal reasoning dataset **OphReason-Vision** subset has been officially open-sourced on the ModelScope platform!
  - 🔗 Dataset Link: <https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision>

- **2025.11.23** 🎬 A live demo video of the “LingTong” Ophthalmic Intelligent Diagnosis System was released on Bilibili.
  - 🎥 Video Link: <https://www.bilibili.com/video/BV1g4UTBZEEm/>

## Background

**“LingTong” Ophthalmic Intelligent Diagnosis System** is a specialized medical AI platform built upon the self-developed **OphVLM-R1 ophthalmic multimodal reasoning model**. Developed by the AI Safety Laboratory team at the School of Artificial Intelligence and Automation, Huazhong University of Science and Technology, the project aims to address the global disparity in high-quality ophthalmic medical resources and the high rates of misdiagnosis and missed diagnosis in primary medical institutions.

Ophthalmic multimodal large language models face three challenges: training data lacking structured reasoning chains, single-stage training that fails to cultivate deep clinical reasoning, and large model sizes that limit deployment in resource-constrained settings. The project addresses these challenges through an integrated data–model–agent stack. OphReason-Vision converts heterogeneous ophthalmic data into expert-verified reasoning trajectories; OphVLM-R1 develops clinical reasoning through a LoRA cold start followed by curriculum reinforcement learning; and OphAgent exposes model, retrieval and specialist capabilities through a durable clinical-assistance runtime.

The current OphAgent combines **AgentScope ReAct agents**, deterministic medical safety gates, typed DAG planning, multimodal tools, provenance-aware retrieval and a governed self-evolution Harness. It exposes three public professional plugins—lesion localization, auxiliary assessment and report generation—while conversation, evidence retrieval, document parsing, speech and memory are coordinated as core capabilities rather than separate top-level agents. Only public execution summaries are displayed; hidden chain-of-thought is never exposed.

**Core objective:** empower clinicians, especially primary healthcare workers, with AI-assisted early screening and precise diagnosis capabilities for ophthalmic diseases. LingTong is a research and clinical-assistance system and is not a substitute for professional medical judgment.

## OphReason-Vision Dataset Pipeline

The three-stage closed loop transforms 100K+ raw clinical cases and 30+ public datasets into 15,418 reasoning trajectories.

![OphReason-Vision data pipeline](figures/data_pipeline.png)

### 1. Data Standardization

This stage integrates 100K+ clinical cases with 30+ public datasets through a dual-stream strategy. The **text stream** parses unstructured electronic medical records into standardized JSON and resolves inconsistent terminology through a curated ophthalmic synonym table. The **visual stream** generates detailed textual descriptions for datasets that contain only image-level labels, enriching the visual evidence available for subsequent reasoning synthesis.

### 2. Structured Reasoning Synthesis

Intern-S1 generates multidimensional instructions covering lesion localization, multimodal diagnosis, and knowledge question answering. For each instruction, it produces a Chain-of-Thought trajectory that follows the clinical diagnostic workflow:

> visual sign identification → knowledge retrieval → pathological analysis → clinical decision

An LVLM-as-a-Judge filter uses Intern-S1 with threshold τ = 0.7, determined on 500 expert-reviewed pilot samples to maximize F1. It evaluates medical correctness, reasoning consistency, step completeness, and clarity, while flagging hallucinated findings, incorrect disease classification, and logically inconsistent steps.

### 3. Expert-Collaborative Optimization

Three board-certified ophthalmologists review the 18% of samples flagged as difficult. Inter-rater agreement reaches Cohen's κ = 0.82, and disagreements are discussed until consensus. Difficulty is graded from base-model perplexity so that the curriculum can progress from easier perception tasks to harder long-form reasoning tasks. Perceptual hashing, source-identifier cross-referencing, and manual source audits are used to reduce contamination with external benchmarks.

| Split | Records | Purpose |
|---|---:|---|
| Cold-start SFT | 3,418 | Domain knowledge injection |
| Four curriculum stages | 10,000 | Progressive reasoning training |
| In-domain evaluation | 2,000 | Held-out clinical evaluation |
| **Total** | **15,418** | **13,418 train + 2,000 eval** |

## OphVLM-R1 Training Framework and Algorithms

OphVLM-R1 is a 2B-parameter model based on InternVL3.5-2B. Its lightweight scale supports deployment on consumer-grade GPUs while retaining capacity for multimodal clinical reasoning. Training proceeds in two stages: parameter-efficient supervised fine-tuning injects ophthalmic knowledge, followed by curriculum reinforcement learning that progressively develops diagnostic reasoning.

![OphVLM-R1 two-stage training framework](figures/two_stage_training.png)

### Stage 1: LoRA Supervised Fine-Tuning

The 3,418-sample cold-start subset injects broad ophthalmic domain knowledge with Low-Rank Adaptation (LoRA), constraining weight updates to low-rank decomposition. The adapters use rank r = 64 and scaling α = 128 on the W<sub>q</sub>, W<sub>k</sub>, W<sub>v</sub>, and W<sub>o</sub> attention projections. Training uses cosine annealing from a learning rate of 1 × 10<sup>−4</sup>, batch size 32, and 3 epochs; approximately 0.5% of the total parameters are trainable.

### Stage 2: Curriculum Reinforcement Learning

Four tasks are ordered by increasing diagnostic complexity:

1. Lesion Localization.
2. Multi-image Selection.
3. Report Generation.
4. Knowledge Q&A.

Group Sequence-level Policy Optimization (GSPO) addresses instability from token-level policy ratios in long reasoning chains by computing importance ratios at sequence level. Each curriculum stage optimizes a mixed reward combining rule-based verifiable reward and an Intern-S1-mini judge reward, with weights λ<sub>1</sub> = 0.6 and λ<sub>2</sub> = 0.4. Training uses G = 8, ε = 0.2, learning rate 5 × 10<sup>−6</sup>, β<sub>KL</sub> = 0.04, and 2 epochs per stage.

### Hard-Sample Dynamic Backtracking

An on-policy resampling mechanism tracks prompts whose rewards remain below a threshold over the most recent k = 5 rounds and increases their sampling probability according to consecutive failure counts. It stores only prompt indices and failure statistics, ensuring fresh on-policy rollouts whenever a difficult prompt is revisited. Resampling is capped at 30% of each batch to retain coverage of already learned samples.

## Model Performance

Accuracy is reported in percent. The average is reference-only because the benchmarks use different formats, difficulties, and random baselines.

| Model | In-Domain | Fundus | Omni-Eye | Avg.* |
|---|---:|---:|---:|---:|
| InternVL3.5-2B | 34.50 | 36.61 | 55.47 | 42.19 |
| InternVL3.5-4B | 36.23 | 42.10 | 77.51 | 51.95 |
| Lingshu-7B | **44.20** | 41.29 | 87.42 | **57.64** |
| OphthaReason-Qwen-3B | 36.60 | 38.87 | 86.86 | 54.11 |
| **OphVLM-R1-2B (ours)** | 38.40 | 42.58 | **88.24** | 56.41 |

Within the reported comparisons, OphVLM-R1 achieves 88.24% on out-of-domain OmniMedVQA-Eye and 42.58% on Fundus-MMBench. Its 56.41% reference average exceeds InternVL3.5-4B at 51.95% and the domain-adapted OphthaReason-Qwen-3B at 54.11%. Ablations reduce Omni-Eye by 26.21 points with SFT only, 10.10 points with one-shot RL, 3.72 points when GSPO is replaced by token-level GRPO, and 2.12 points without hard-sample backtracking. Results are single runs without confidence intervals or significance tests, and comparisons with off-the-shelf 7B/8B models should be interpreted cautiously because training-data exposure and model scale are not controlled.

## OphAgent

**Works with your ophthalmic context and keeps every step organized.**

OphAgent is a full-stack Agent workspace for ophthalmic research and clinical assistance — deploy it on your own machine or server, extend it with skills and professional plugins, and organize images, documents, guideline evidence and reports in one continuous conversation.

| | |
|---|---|
| **Durable by design** | Conversations, Runs, events, attachments and context snapshots are persisted with clear refresh, reconnect and recovery states. |
| **Evidence first** | Guideline-first hybrid retrieval, source lifecycle, evidence ledgers and paragraph-level claim checks keep answers reviewable. |
| **Security built in** | Red-flag rules, attachment ownership, idempotency, budgets, cancellation, coordinate validation and source gates span the execution path. |
| **Multimodal and parallel** | Fundus, OCT, anterior-segment images, PDFs, text and audio enter a typed DAG whose relevant nodes can execute concurrently. |
| **Extensible** | Three professional plugins, gated `SKILL.md` packages, memory, OpenAI-compatible providers and external tools share composable contracts. |
| **Controlled self-evolution** | Low-authority Memory CRUD and validated low-risk Skill utility adapt online; content, permissions, safety and other risky changes pass isolated offline evaluation and trusted approval. |
| **Available everywhere** | A responsive React workspace covers desktop and mobile, with projects, files, knowledge, skills and settings in one place. |

<details>
<summary><b>What you can do with OphAgent</b></summary>

<br>

- **Ophthalmic Q&A and guideline retrieval**: continue a case discussion with automatic routing, citations and evidence review.
- **Multimodal record review**: upload fundus, OCT, anterior-segment images, examination documents and audio.
- **Professional plugin workflows**: compose lesion localization, auxiliary assessment and report generation on demand.
- **Project-based organization**: group conversations, private files, generated artifacts and clinical goals.
- **Editable reports**: continue editing in the document workspace and export MD, PDF, DOCX or JPG.
- **Personalized capabilities**: manage confirmed memory, gated skills, provider configuration and knowledge sources.
- **Safe self-evolution**: turn outcomes and explicit feedback into candidates, then validate, approve, release or roll them back through an independent Harness.

</details>

---

## OphAgent Contents

- [Quick Start](#quick-start)
- [Product Capabilities](#product-capabilities)
- [Design Architecture](#design-architecture)
- [Execution Profiles](#execution-profiles)
- [Safety and Reliability](#safety-and-reliability)
- [Self-Evolution Harness](#self-evolution-harness)
- [Technology Stack](#technology-stack)
- [Repository Layout](#repository-layout)
- [Knowledge Corpus](#knowledge-corpus)
- [API and Streaming](#api-and-streaming)
- [Development](#development)

---

## Quick Start

### Requirements

- Python 3.11+
- Node.js 20+ and npm
- OpenAI-compatible main Agent and multimodal Sub-agent models
- 8 GB+ RAM recommended; provision a GPU according to your local model

### 1. Install

```bash
git clone https://github.com/QiZishi/OphAgent.git
cd OphAgent

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

npm --prefix frontend ci
npm --prefix frontend run build
```

### 2. Configure

```bash
cp .env.example .env
```

Set the minimum runtime configuration in `.env`:

```dotenv
JWT_SECRET_KEY=replace-with-a-long-random-secret

AGENT_URL=https://your-provider.example/v1
AGENT_API_KEY=...
AGENT_MODEL=...

SUB_AGENT_URL=https://your-provider.example/v1
SUB_AGENT_API_KEY=...
SUB_AGENT_MODEL=...
```

### 3. Run

```bash
python init_db.py
python run.py
```

Open <http://localhost:8013>, create an account and start a conversation. `STRICT_STARTUP=true` validates required model settings during startup. Embeddings, Rerank, AnySearch/Tavily, ASR, TTS, MinerU and OTLP are optional capabilities whose connection state is visible in the workspace.

![OphAgent console](figures/ophagent-workbench.png)

---

## Product Capabilities

| Capability | Experience |
|---|---|
| Multiturn ophthalmic Q&A | Persistent conversations, context snapshots, bounded history compression and follow-up route inheritance |
| Multimodal review | Authenticated fundus/OCT/anterior-segment uploads, validated observations and optional normalized/pixel regions |
| Lesion localization | Validates normalized and pixel coordinates before presenting reviewable regions on the source image |
| Auxiliary assessment | Qualitative differentials with supporting, opposing and missing evidence; support levels are not disease probabilities |
| Report generation | Citation-aware Markdown reports, editable artifacts and MD/PDF/DOCX/JPG export |
| Knowledge retrieval | Guideline-first BM25 + optional BGE-M3 embeddings and Rerank, lifecycle filtering, PDF page visuals and lightweight graph expansion |
| Speech and documents | Optional server-side ASR/TTS, authenticated audio upload and MinerU/local document parsing |
| Workspace management | Projects, private files, generated artifacts, provider overrides, memory, skills, source governance and capability health |

Every screenshot below was captured directly from the current repository running against its real backend in an isolated local demo environment after completing registration, query, retrieval and workspace actions.

### Knowledge and source governance

The knowledge workspace reports sources, chunks, vectors, page visuals and graph edges, with controls for import, index rebuild, source versioning and lifecycle state.

![OphAgent knowledge source governance](figures/ophagent-knowledge.png)

### Project-based clinical workspace

Projects organize related conversations, files and clinical goals. Private files, plugins, memory, knowledge, skills and settings share the same authenticated workspace.

![OphAgent project workspace](figures/ophagent-projects.png)

### Responsive mobile workspace

The React workspace adapts to desktop and mobile layouts, including chat, attachment, plugin and skill entry points.

<p align="center">
  <img src="figures/ophagent-mobile.png" width="360" alt="OphAgent mobile workspace">
</p>

---

## Design Architecture

```mermaid
flowchart TB
    UI["Experience<br/>React workspace · desktop and mobile"]
    API["Access<br/>FastAPI · JWT Cookie · REST · SSE · WebSocket"]
    GATE["Safety and control<br/>red-flag gate · attachment ownership · idempotency · budgets"]
    ROUTER["Orchestration<br/>intent routing · Quick / Standard / Deep · typed DAG"]
    AGENTS["Agents<br/>Supervisor · Clinical · Evidence · Specialist · Critic · Report"]
    TOOLS["Capabilities<br/>OphVLM-R1 · multimodal · guidelines · search · documents · ASR / TTS"]
    STATE["State<br/>ClinicalState · evidence ledger · artifacts · memory · skills"]
    STORE["Persistence<br/>SQLModel · SQLite WAL · Runs · events · attachments · snapshots"]

    UI --> API
    API --> GATE
    GATE --> ROUTER
    ROUTER --> AGENTS
    AGENTS --> TOOLS
    TOOLS --> STATE
    STATE --> STORE
    STORE -. cursor resume and state replay .-> API
```

### Runtime highlights

- **Durable Run protocol** — every state transition, tool result, artifact and public progress event has a stable `run_id`, `trace_id` and monotonic sequence.
- **True response streaming** — provider text is emitted as `answer.delta` events over SSE. Early events are backfilled from a durable cursor, and reconnects resume without duplicated content.
- **Quick / Standard / Deep routing** — deterministic intent and risk rules select a bounded plan, with emergency signals able to override a requested quick mode.
- **Typed clinical state** — user facts, missing information, red flags, evidence and model observations occupy explicit fields.
- **Composable professional plugins** — `lesion_localizer`, `aux_diagnosis` and `report_generator` can be selected explicitly or composed by the router.
- **Controlled memory and skills** — memory enters `proposed`; imported `SKILL.md` packages pass structure, dependency, safety and checksum gates before enablement.
- **Capability health** — model, retrieval, parsing and speech services register their live connection state in one operational view.
- **Privacy-aware observability** — OpenTelemetry exports allowlisted identifiers, status, latency and aggregate token usage while patient content and secrets remain inside the application boundary.

---

## Execution Profiles

| Profile | Typical request | Runtime behavior |
|---|---|---|
| **Quick** | Simple non-medical fact or arithmetic | One bounded direct-answer call; no retrieval or report pipeline |
| **Standard** | Knowledge Q&A, a single image task or routine clinical request | Relevant clinical, evidence and imaging nodes may execute in parallel before synthesis |
| **Deep** | Complex multimodal assessment, high-risk symptoms or report composition | Specialist review plus draft → critic → final safety pipeline |

The public UI presents concise stage summaries, validated outputs and evidence while private chain-of-thought remains internal to the model.

## Safety and Reliability

- Deterministic red-flag patterns run before model routing and can force emergency escalation.
- Attachments are referenced by authenticated IDs. Public REST and WebSocket APIs reject client-supplied server file paths.
- Run budgets bound model calls, tokens, wall time and node concurrency; cancellation is persisted and propagated.
- Required-node failures produce structured failure events. Optional capability failures yield explicit warnings.
- Citations are checked at claim-paragraph level, not merely by the presence of one marker.
- Expired or superseded knowledge sources are excluded by default; low-trust sources are down-weighted and labeled.
- Restart recovery marks unfinished runs as interrupted and preserves completed work for resume/retry.
- This is a research-grade clinical assistance system. It does not provide a definitive diagnosis or replace emergency and professional medical assessment.

---

## Self-Evolution Harness

OphAgent separates bounded online adaptation from risky production changes. `ContinuousEvolutionController` applies explicit CRUD to low-authority preference/workspace Memory and continuously updates bounded utility for those memories and validated low-risk Skills. `EvolutionHarness` creates, freezes, evaluates and promotes content, code, permission and high-risk candidates inside an offline isolated environment. Every component also has an immutable core contract covering its identity, responsibility, authority, input/output semantics and fail-safe mechanisms.

```mermaid
flowchart TB
    OUTCOME["Online outcomes<br/>Run status · explicit feedback · memory governance"]
    SIGNAL["Privacy-minimized signals<br/>hashed fingerprint · route · plugins/skills · cost"]
    ONLINE["Bounded online adaptation<br/>Memory CRUD · Memory/Skill utility"]
    CANDIDATE["Bounded candidates<br/>runtime · skill · memory retrieval/extraction"]
    PROPOSAL["EvolutionProposal<br/>failure cluster · allowlisted paths · risk · activation"]
    ISOLATE["Isolated Git worktree<br/>bound to base commit"]
    FREEZE["Candidate freeze<br/>validate diff and declared paths · pin candidate commit"]
    PAIRED["Paired evaluation<br/>baseline vs candidate on identical cases"]
    SEALED["Sealed test<br/>candidate-invisible · routine / complex / high_risk"]
    GATES["Promotion gates<br/>gain · 95% CI · slice non-regression · safety/citation · cost"]
    APPROVAL["Trusted human approval<br/>HMAC attestation bound to candidate commit"]
    RELEASE["Atomic release<br/>refs/ophagent/releases/* · refs/ophagent/active"]
    EXPERIENCE["Audit and experience<br/>verifiable release · atomic rollback"]

    OUTCOME --> SIGNAL
    SIGNAL --> ONLINE
    SIGNAL --> CANDIDATE
    CANDIDATE --> PROPOSAL
    PROPOSAL --> ISOLATE
    ISOLATE --> FREEZE
    FREEZE --> PAIRED
    PAIRED --> SEALED
    SEALED --> GATES
    GATES --> APPROVAL
    APPROVAL --> RELEASE
    RELEASE --> EXPERIENCE
```

| Stage | Harness implementation |
|---|---|
| Online signals | Stores Run fingerprints, status, risk, route, plugins/skills, error codes, warning counts, tokens, explicit votes and memory-governance actions; patient queries, answers, attachments, evidence text and user identifiers remain outside evolution signals |
| Bounded adaptation | Explicit preference/workspace Memory supports online create, update, delete and expiry; its utility and validated low-risk Skill selection utility move within configured bounds as feedback changes |
| Immutable mechanism | Memory CRUD, provenance, confirmation, conflict handling, clinical protection and user correction/deletion guarantees cannot evolve online |
| Component contracts | `config/immutable/harness_component_contracts.yaml` defines what each component is, which mechanisms make it useful and which state may evolve online |
| Mutation boundary | Mutable strategy paths and immutable control-plane paths cannot share a proposal; built-in Skill definitions, Memory mechanisms, permissions, safety and business rules remain offline-gated |
| Isolation and freeze | Every proposal receives an independent Git worktree; the Harness validates the diff, declared paths and workspace state before pinning one candidate commit |
| Paired evaluation | Baseline and candidate use identical case IDs and report routine, complex and high-risk slices separately |
| Sealed test | Cases and manifest live outside the repository and candidate worktree, with one-shot release evaluation, complete slices, mandatory metrics and controller-issued HMAC attestations |
| Promotion criteria | Mean gain reaches its threshold with a non-negative 95% confidence-interval lower bound; every slice is non-regressive, high-risk cases do not lose score, and safety, citation, component-contract and critical-error gates pass |
| Resource gates | The default candidate token-ratio ceiling is 1.15 and the latency-ratio ceiling is 1.20 |
| Approval and release | Immutable/high-risk changes always require signed human approval bound to the candidate commit; release refs update atomically |
| Rollback and audit | Rollback targets are restricted to frozen releases; proposals, evaluations, approvals, promotions, rollbacks and de-identified experience remain auditable |

The Harness can connect to official **A-Evolve**, **GEPA** and **Adaptive Auto-Harness** packages through `requirements-evolution.txt`. The local adapters handle capability detection and governed invocation while promotion continues through OphAgent safety gates.

<details>
<summary><b>Configure offline evolution and promotion gates</b></summary>
<br>

```bash
# Install only in an isolated offline evaluation environment
pip install -r requirements-evolution.txt
```

```dotenv
# The sealed suite must stay outside the repository and candidate worktree
EVOLUTION_SEALED_TEST_DIR=/secure/path/to/sealed-suite
EVOLUTION_GATE_SECRET_FILE=/secure/path/to/evolution-gate-secret
EVOLUTION_REQUIRE_HUMAN_APPROVAL=true

# Default promotion thresholds
EVOLUTION_MIN_MEAN_IMPROVEMENT=0.01
EVOLUTION_MAX_SLICE_REGRESSION=0.0
EVOLUTION_MIN_CASES_PER_SLICE=1
```

Inspect live signals and candidate status through the authenticated `GET /api/v1/evolution/status` endpoint.

</details>

## Technology Stack

| Layer | Implementation |
|---|---|
| Web client | React 19, TypeScript 5.8, Vite 6, responsive desktop/mobile UI |
| API | FastAPI 0.138, authenticated REST, Server-Sent Events and WebSocket compatibility |
| Agent runtime | AgentScope 1.0 ReAct roles, deterministic routing and typed async DAG execution |
| Persistence | SQLModel conversation/account database + SQLite WAL runtime event store |
| Knowledge | BM25, NumPy vector persistence, OpenAI-compatible embeddings/Rerank, PDF page evidence, OphthaGraph |
| Self-evolution | Online Memory CRUD and bounded Memory/Skill utility plus isolated offline worktrees, paired/sealed evaluation, HMAC attestations and atomic release refs |
| Observability | OpenTelemetry with export-time privacy filtering |
| Quality | Pytest, Vitest, ESLint, Ruff, Playwright and axe accessibility checks |

## Repository Layout

```text
OphAgent/
├── app/
│   ├── api/             # Authenticated REST, SSE and WebSocket surfaces
│   ├── auth/            # JWT cookies, session revocation and login controls
│   ├── domain/          # Run, event, evidence and ClinicalState contracts
│   ├── evolution/       # Content-free online signals and offline gated harness
│   ├── knowledge/       # Source lifecycle, hybrid retrieval and OphthaGraph
│   ├── observability/   # Privacy-filtered tracing
│   ├── plugins/         # Public professional plugin registry
│   ├── runtime/         # Router, planner, AgentScope roles, store and exports
│   ├── services/        # Memory, skill and encrypted provider configuration
│   ├── tools/           # Multimodal, search, document and speech clients
│   └── main.py
├── data/knowledge_base/raw/
├── frontend/            # React workspace, unit tests and Playwright scenarios
├── scripts/             # Portable knowledge CLI and optional evolution installer
├── skills/              # Built-in gated Agent skills
├── tests/               # Backend contract, safety and orchestration tests
├── .env.example
├── init_db.py
└── run.py
```

## Knowledge Corpus

The application automatically indexes supported files under `data/knowledge_base/raw/`. Its portable CLI can also import corpora from any authorized directory:

```bash
python scripts/build_knowledge_base.py \
  --collect \
  --source local-guidelines=/absolute/path/to/guidelines

python scripts/build_knowledge_base.py --build-index --lexical-only
python scripts/build_knowledge_base.py --search "glaucoma visual field follow-up"
python scripts/build_knowledge_base.py --stats
```

Use only material you are authorized to process and distribute. Uploaded sources begin as unverified and should be reviewed in the source-governance workspace.

## API and Streaming

| Endpoint | Purpose |
|---|---|
| `POST /auth/register`, `POST /auth/login` | Create or authenticate an account |
| `POST /api/v1/conversations/{id}/messages` | Create an idempotent message and background Run |
| `GET /api/v1/runs/{id}` | Read durable Run state |
| `GET /api/v1/runs/{id}/events` | Replay ordered events after a cursor |
| `GET /api/v1/runs/{id}/events/stream` | SSE stream with replay cursor and heartbeat |
| `POST /api/v1/upload` | Authenticated typed attachment upload |
| `GET /api/v1/artifacts`, `GET /api/v1/attachments` | Private generated and uploaded files |
| `WS /ws/runs/{id}` | Authenticated WebSocket event bridge |

Interactive OpenAPI documentation is available at `/docs`.

## Development

```bash
source venv/bin/activate
pip install -r requirements-dev.txt

python -m ruff check app tests scripts run.py init_db.py
pytest

npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build

npm --prefix frontend exec playwright install chromium
npm --prefix frontend run test:e2e -- workspace.spec.ts
```

When adding a capability:

1. Add or extend typed input/output contracts in `app/domain/`.
2. Register external behavior in `app/tools/` and declare real health semantics.
3. Update routing/planning in `app/runtime/` without bypassing risk gates or budgets.
4. Add replayable public events and tests for ownership, failure and cancellation paths.
5. Expose only validated public summaries in the React workspace.

## Open Source Status

### Available

- **System code**: frontend/backend implementation, API routes, services, and database models.
- **OphReason-Vision subset**: 3,418 cold-start samples on Hugging Face and ModelScope.
- **OphVLM-R1 model**: model weights on Hugging Face and ModelScope.

### Planned Releases

- Remaining OphReason-Vision records after completion of privacy and ethics review.
- Cold-start SFT and curriculum reinforcement learning scripts.
- Model evaluation code.

## Citation

```bibtex
@inproceedings{qi2026ophvlm,
  title={OphVLM-R1: Efficient Ophthalmic Reasoning via Curriculum Reinforcement Learning},
  author={Qi, Zishi and Hu, Xiaoya and Pan, Huilin and Gao, Ang and Hou, Jiaxin and Li, Jiankun and Qian, Yongao},
  booktitle={Proceedings of the World Artificial Intelligence Conference Academic (WAICA)},
  year={2026}
}
```

## Acknowledgements

The development of this project benefits from the InternLM ecosystem, OpenGVLab, the InternLM Practical Camp, and the Datawhale open-source community. We sincerely thank these communities for providing the model, tooling, and learning resources that support the project, and we thank the ophthalmologists who contributed to data review and quality assurance.

## Related Links

- **InternVL**: <https://github.com/OpenGVLab/InternVL>
- **InternLM online experience**: <https://chat.intern-ai.org.cn/>
- **InternLM Practical Camp**: <https://colearn.intern-ai.org.cn/go>
- **Datawhale**: <https://www.datawhale.cn/>
