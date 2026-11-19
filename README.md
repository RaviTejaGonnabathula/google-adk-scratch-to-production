# Google ADK Scratch to Production

A Python ADK agent using Vertex AI, with separate private Cloud Run and Agent Runtime deployment workflows.

## Overview

This project demonstrates how to run an agent locally and prepare it for managed Google Cloud hosting. It is a development foundation, not a production-ready application. A successful preflight does not prove a successful remote build or agent response.

Run commands from the repository root in **Windows PowerShell**, unless instructed otherwise. Replace all placeholders with your values.

## Features

- Master agent exposed through ADK's `root_agent` entry point.
- Local terminal interaction and ADK development UI.
- Private Cloud Run deployment with authenticated proxy access.
- YAML-driven Agent Runtime deployment, previews, and IAM checks.
- Separate hosting and model locations.
- Offline configuration tests and credential upload safeguards.
- Versioned capability selection with lazy imports and fresh agent factories.
- Synthetic FAQ function-tool, delegated scheduling, and RAG AgentTool examples.

## Tech Stack

| Component | Technology |
| --- | --- |
| Language and dependencies | Python 3.12+, uv, `pyproject.toml`, `uv.lock` |
| Agent framework | Google ADK |
| Model | Gemini through Vertex AI |
| API and development UI | ADK's FastAPI-based server |
| Hosting | Cloud Run or Agent Runtime |
| Build and images | Cloud Build, Artifact Registry, Dockerfile for Cloud Run |
| Deployment automation | PowerShell, Google Cloud CLI, Agent Platform SDK |

No external application database is configured by this repository.

## Architecture

The same agent code supports three independent execution paths:

```text
Terminal / local ADK UI ----------> Local agent ------> Vertex AI Gemini
Browser -> authenticated proxy --> Private Cloud Run -> Vertex AI Gemini
Authenticated platform client ---> Agent Runtime ----> Vertex AI Gemini
```

Deployment credentials authorize resource creation. The deployed runtime identity authorizes the agent's model and tool access. Cloud Run's proxy does not target Agent Runtime.

The application now uses repository-root `agents/`, `tools/`, and `composition/` packages, following the [Phase 2 Notion plan](https://app.notion.com/p/41bf308b91b7813db47de1ba01fa0757). The public aliases remain `agent.root_agent` → `agents.root_agent` → `agents.agent.root_agent` → `agents.master.master_agent`. A small `app/src/agent.py` launcher preserves the earlier local commands; it contains no second implementation.

`composition` validates the entire selection before resolving any capability factory. `master/factory.py` constructs fresh masters; specialist factories construct fresh agents and injected adapters. `master/agent.py` builds the one compatibility export for normal ADK loading. Package exports are lazy so importing factories or model settings does not construct that singleton. No module import or construction makes a model request or discovers credentials.

`tools` owns deterministic operations, validation, authorization checks, and adapter contracts. ADK agent instructions stay with their definitions. This phase adds no second framework, separate API server, external session store, generic domain layer, or infrastructure templates.

## Project Structure

```text
agent.py                           # Repository-root ADK entry point
agents/
  __init__.py / agent.py            # Lazy public export / root_agent alias
  model_settings.py / models.py    # Existing precedence / fresh model wrapper
  capabilities.yaml                # Packaged non-secret selection; empty by default
  requirements.txt                 # Generated from uv.lock for Agent Runtime
  master/
    __init__.py / agent.py          # Compatibility master_agent export
    factory.py                     # Fresh master construction
  sub_agents/
    scheduler/                     # Delegated specialist factory
    rag/                           # AgentTool specialist factory
tools/
  contracts.py                     # Typed adapter, identity, and result contracts
  faq/ / scheduler/ / rag/          # Deterministic tools and synthetic adapters
composition/
  specs.py / config.py             # Strict schema and manifest loading
  registry.py / builder.py         # Lazy factories and fresh ADK graph
app/src/agent.py                    # Compatibility launcher for original commands
tests/                             # Offline schema, behavior, isolation, packaging checks
config/
  settings.dev.example.yaml        # Safe deployment template
deploy/
  cloudrun/dev.ps1                 # Private Cloud Run deployment
  agentruntime/
    dev.ps1                        # YAML-driven deployment wrapper
    config.py                      # YAML, runtime config, and IAM checks
    package_sources.py             # Guarded upload roots and source staging
    test_config.py                 # Offline tests
sa-key.example.json                # Fake key-format example
Dockerfile                         # Cloud Run build and startup
pyproject.toml / uv.lock            # Dependencies
.python-version                    # Development Python version
.gitignore / .dockerignore / .gcloudignore
README.md                          # Single project guide
```

Local `.env`, `config/settings.dev.yaml`, real keys, environments, and caches are omitted. The fake key example currently lives at the repository root.

Only implemented packages exist. Database, human escalation, API integration, the FAQ specialist, templates, and the generator skill remain future work. Keep documentation in this root README.

### Capability selection

Edit `agents/capabilities.yaml`, then restart locally or rebuild/redeploy the application. It is packaged with the agent in both deployment targets, independently of private deployment YAML. It must never contain credentials, connection strings, module paths, or caller identities.

The default remains master-only:

```yaml
schema_version: 1
capabilities: []
```

This mixed selection enables every Phase 2 example:

```yaml
schema_version: 1
capabilities:
  - name: faq
    integration: direct_tool
  - name: scheduler
    integration: sub_agent
  - name: rag
    integration: agent_tool
```

| Capability / supported mode | Behavior | Model-visible argument |
| --- | --- | --- |
| `faq` / `direct_tool` | Master calls `lookup_faq`; no FAQ specialist is constructed | `question` |
| `scheduler` / `sub_agent` | Control transfers to `scheduler_agent`, which calls `check_slots` | `day` in `YYYY-MM-DD` format |
| `rag` / `agent_tool` | Master calls `rag_agent`; it retrieves synthetic documents and returns its answer to the master | AgentTool `request`; retriever `query` |

For an individual example, keep only its entry. Each entry optionally accepts `enabled: false` (strict boolean; default `true`) and `adapter: mock` (default). Disabled entries are structurally validated but do not import their implementation or resolve adapters. Unknown names/fields, duplicate names including disabled entries, invalid modes, enabled but unsupported pairs, and non-mock enabled adapters fail before capability construction. The remaining three capability names are recognized only for disabled/future selections.

The file requires exactly `schema_version: 1` and a `capabilities` list. Duplicate YAML keys, empty files, malformed YAML, and unsupported schema versions fail with `ConfigurationError`; they do not silently disable capabilities. An absent default file preserves master-only behavior. An explicitly requested missing file fails.

For embedding or tests, `build_application(master_factory=..., specification=...)` accepts a `CompositionSpec` or the same mapping. `specification=[]` explicitly selects master-only and takes precedence over any manifest path. `manifest_path=...` loads a required file; `default_manifest_path=...` permits an absent file. The ADK entry point resolves the default path relative to the agent package, never the working directory. There is no capability environment override and capability selection is not read from `config/settings.dev.yaml`.

### Adapters and authorization

Factories accept injected `model`, `adapter`, and `authorization` dependencies. `build_application` also accepts `model_factory(agent_name)` and an optional `adapter_factories` mapping keyed by capability. Supplying that mapping requires a callable for every enabled capability. A factory must return a new compatible adapter for each build. The registry uses fixed module references, not paths supplied by YAML.

Phase 2 adapters are in-memory and use immutable synthetic records, returning fresh result containers so one session cannot mutate a later session's data. Their default authorization provider returns a **synthetic demo identity**, not the identity of an authenticated user. An injected provider must obtain verified identity from the serving/authentication boundary; model arguments and client-controlled session state are not authoritative. Tool wrappers enforce tenant `demo` and the relevant read scope before calling adapters; mocks also enforce these rules. Neither adapters nor authorization parameters are exposed to the model. No real user-data integration is enabled.

| Boundary | Contract / deferred requirement |
| --- | --- |
| FAQ | `FAQAdapter.lookup(question, context)` returns an answer and source status |
| Scheduling | `SchedulingAdapter.check_slots(day, context)` returns UTC synthetic availability; no booking |
| Retrieval | `RetrievalAdapter.retrieve(query, context)` returns synthetic documents with IDs; no embeddings/vector store |
| Database (deferred) | Read-only scoped adapter, parameterized queries, verified tenant/record authorization |
| Human escalation (deferred) | Explicit confirmed handoff, permission checks, idempotency key and audit record |
| API integration (deferred) | Allowlisted endpoints, bounded timeouts, scoped authorization; confirmed/idempotent audited mutations |

Tools return `{status, data, error}`. Expected input, authorization, timeout, and adapter failures become stable error codes without private exception details; unexpected programming errors propagate. Text inputs are bounded and scheduling dates are validated. Future network adapters must enforce their own timeouts and cancellation and produce redacted audit records at the tool boundary. No network client, retry policy, persistent audit sink, or write workflow is implemented in this phase.

## Prerequisites

- Python 3.12+, uv, Git, and Google Cloud CLI.
- A billing-enabled Google Cloud project and appropriate IAM access.
- A supported model and model location.
- Docker only if you choose to build/run containers locally; the supplied Cloud Run script builds remotely.
- For Agent Runtime, a compatible SDK exposing `Client.runtimes`. ADK 2.12.0 and SDK 2.6.0 were checked during setup; recheck after upgrades.

## Installation

```powershell
git clone <repository-url>
cd google-adk-scratch-to-production
uv sync
uv pip check
```

Replace `<repository-url>` before running. Configure your CLI identity:

```powershell
gcloud.cmd auth login
gcloud.cmd config set project your-project-id
```

For personal Application Default Credentials (ADC), used by local model calls and optionally Agent Runtime deployment:

```powershell
gcloud.cmd auth application-default login
```

CLI login and ADC are separate credential configurations.

## Environment Configuration

### Local development and Cloud Run

Create a root `.env`; never commit it:

```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=your-model-location
```

Cloud Run reads the project from its parameters, process environment, or this file. Shared model settings come from the YAML below or explicit overrides.

| Cloud Run setting | Priority, highest first |
| --- | --- |
| Project | Parameter, process environment, root `.env` |
| Model name/location | Parameter, process `ADK_MODEL_NAME` / `ADK_MODEL_LOCATION`, application YAML |
| Hosting region | Parameter, process `CLOUD_RUN_REGION`, script default |

`CLOUD_RUN_REGION` inside `.env` is not read by the script.

### Shared model settings and Agent Runtime

Create the local settings file without overwriting an existing one:

```powershell
if (-not (Test-Path config/settings.dev.yaml)) {
    Copy-Item config/settings.dev.example.yaml config/settings.dev.yaml
}
```

Populate the following fields, keeping the template's Cloud Run section:

```yaml
application:
  model_name: "gemini-3.5-flash-lite"
  model_location: "us"
google_cloud:
  project_id: "your-project-id"
deployment:
  credentials_file: null
  agentruntime:
    region: "us-central1"
    display_name: "your-agent-dev"
    service_account: "your-runtime-account@your-project-id.iam.gserviceaccount.com"
    agent_engine_id: null
```

- `credentials_file`: null uses existing ADC. Alternatively, supply a local JSON key path, preferably outside the repo: `"C:/secure/google-cloud/sa-key.json"`. Relative paths resolve from the repo root.
- `service_account`: runtime identity email, not a key path. The deployer and runtime identities can differ.
- `application.model_name`: Gemini model ID used by the master agent in all three execution paths.
- `application.model_location`: supported Gemini endpoint location, independent of deployment hosting `region`.
- `agent_engine_id`: null for a new deployment; quoted numeric ID for updates.

The wrapper temporarily sets ADC/gcloud credential overrides for a configured key and restores them afterward. The deployed agent uses its attached identity, not the local key.

Agent Runtime parameters override YAML: `-ProjectId`, `-Region`, `-ModelName`, `-ModelLocation`, `-DisplayName`, `-ServiceAccount`, `-AgentEngineId`, and `-CredentialsFile`. Use `-ConfigPath` for another YAML file. Project ID additionally falls back to process `GOOGLE_CLOUD_PROJECT`, then root `.env`.

For both deployment scripts, model precedence is **explicit parameters > process `ADK_MODEL_NAME` / `ADK_MODEL_LOCATION` > application YAML**. Locally, those environment variables override YAML. Missing or invalid values fail early instead of silently choosing a model.

Both scripts pass only the resolved model settings to the deployed agent as environment variables; the private YAML is not uploaded. Gemini uses `client_kwargs.location`; Agent Runtime's reserved `GOOGLE_CLOUD_LOCATION` remains its hosting region.

To switch models, edit `application.model_name` (and location if needed), remove any conflicting environment override, then restart the local ADK process or redeploy the cloud service. Editing local YAML does not change an already deployed service. Model access and regional availability still need verification.

## Running Locally

Terminal interaction:

```powershell
uv run adk run agents
```

Development UI:

```powershell
uv run adk web agents --host 127.0.0.1 --port 8000 --no-reload
```

Open [local ADK UI](http://127.0.0.1:8000/dev-ui/). Stop with Ctrl+C. The local server is for trusted development use; do not expose it publicly. Model requests may incur charges.

The original `uv run adk run app/src` and `uv run adk web app/src --host 127.0.0.1 --port 8000 --no-reload` commands remain available through the compatibility launcher. There is one authoritative agent tree at the repository root.

## API Documentation

ADK supplies the API schema and interactive documentation; this repository does not define a separate custom API contract.

- Local server: [Swagger UI](http://127.0.0.1:8000/docs).
- Private Cloud Run through the proxy below: [Swagger UI](http://127.0.0.1:8081/docs).
- Development playground: `/dev-ui/`.

Read the running server's OpenAPI schema:

```powershell
$schema = Invoke-RestMethod http://127.0.0.1:8000/openapi.json
$schema.paths.PSObject.Properties.Name
```

The response is an OpenAPI JSON document with endpoint paths and request/response schemas. Use those installed-version examples for session and agent requests. Cloud Run proxy endpoints are not Agent Runtime endpoints.

## Testing

```powershell
uv sync --locked
uv pip check
uv run --locked python -m unittest discover -s deploy/agentruntime -p test_config.py
uv run --locked python -m unittest discover -s tests -p "test_*.py"
.\deploy\agentruntime\dev.ps1 -WhatIf
.\deploy\cloudrun\dev.ps1 -WhatIf
.\deploy\agentruntime\dev.ps1 -CheckPermissions
```

The original suite covers configuration, location separation, and mocked permission outcomes. The architecture suite covers strict configuration, factory validation, fresh instances, function schemas, authorization failures, fake-model execution of all three patterns, import sentinels, and deployment artifacts. Fake models exercise the ADK Runner; network connections and ADC lookup are blocked. Isolated subprocesses import staged packages without the checkout or private YAML. Tests do not need cloud credentials.

`-WhatIf` validates upload roots and previews locally without cloud calls; it stops before SDK staging. `-CheckPermissions` performs read-only live checks using deployment credentials and is separate from the offline suite.

Core permission checks cover project access, service usage, agent create/update, and runtime-account `actAs`. They do not validate all APIs, billing, build permissions, quota, model availability, startup, or an actual agent response. Cloud end-to-end tests are not configured.

### Phase 2 verification record — November 18, 2026

Implementation branch: `feature/phase2-modular-architecture`, based on refreshed `origin/main` at `63da6f28feaffbb3ef9d025e7c05c4ae56ce6cb4`. That base has the same tree as the reviewed `develop` commit `83b319c8ac55558e8cba4ebda16c58a4392f1af6`. The implementation is local and awaits merge review.

Tested with Python **3.12.7**, Google ADK **2.12.0**, Agent Platform SDK **2.6.0**, and PyYAML **6.0.3**. PyYAML is now an explicit dependency; the existing resolved versions were retained. `uv sync --locked` and `uv pip check` passed.

| Check | Observed result |
| --- | --- |
| Existing configuration regression suite | All **10** tests passed after the package move; model-setting precedence remains covered |
| Phase 2 regression suite | All **25** tests passed, including actual ADK Runner execution with fake models for the three patterns |
| Compatibility and isolation | Matching master/root aliases, original launcher, ADK loader, API server discovery, fresh factories, schema exclusions, and unselected import sentinels passed |
| Agent Runtime artifact | Actual installed ADK staging ran with its cloud client mocked; default, individual, and mixed manifests imported correctly outside the checkout; locked requirements and upload safeguards passed |
| Cloud Run artifact inputs | Dockerfile COPY sources/startup path and isolated imports passed for default, individual, and mixed selections; this is a source-layout check, not a container execution check |
| Deployment previews | Both PowerShell `-WhatIf` commands passed; no remote submission occurred |
| Local Docker build/run | **Not performed:** Docker Desktop's Linux engine was unavailable |
| Remote validation | **Not performed:** no cloud deployment, live IAM check, remote build/startup, authenticated service request, or real model response was tested in this implementation run |

The architecture is ready for merge review. Full capability examples, additional capability/mode pairs, provider integrations, the generator skill/templates, CI, and production operations remain deferred as described in the plan. These results do not establish production readiness.

## Deployment

Both workflows can incur build, storage, hosting, and model charges.

### Cloud access preparation

Use an authorized administrator to verify billing and relevant Agent Platform, Cloud Build, Artifact Registry, IAM, Resource Manager, Storage, and observability APIs.

| Identity | Access to verify |
| --- | --- |
| Deployer | Deployment permissions; service usage; permission to attach the runtime account |
| Runtime identity | Model access, commonly `roles/aiplatform.user`, and tool-specific permissions |
| Build identities | Build, artifact, and source access for the chosen workflow |

For Agent Runtime, `roles/serviceusage.serviceUsageConsumer` supplies `serviceusage.services.use`. Grant `roles/iam.serviceAccountUser` to the deployer **on the specific runtime account** for `iam.serviceAccounts.actAs`.

If needed, provision Google-managed identities:

```powershell
gcloud.cmd beta services identity create --service=aiplatform.googleapis.com --project your-project-id
```

Verify these standard project bindings:

| Google-managed identity | Role |
| --- | --- |
| `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com` | `roles/aiplatform.serviceAgent` |
| `service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com` | `roles/aiplatform.reasoningEngineServiceAgent` |

Grant these roles only to their matching Google-managed identities, not the application account. Allow IAM propagation time.

### Private Cloud Run

After completing installation, CLI login, and environment configuration, preview from the repository root:

```powershell
.\deploy\cloudrun\dev.ps1 -WhatIf
```

Then build and deploy with no arguments:

```powershell
.\deploy\cloudrun\dev.ps1
```

- Project ID: process `GOOGLE_CLOUD_PROJECT`, then root `.env`.
- Model name/location: process `ADK_MODEL_NAME` / `ADK_MODEL_LOCATION`, then `application` in `config/settings.dev.yaml`.
- Service name: script default. Hosting region: process `CLOUD_RUN_REGION`, then script default.
- Authentication: existing Google Cloud CLI login; this script does not load the YAML credential-file setting.

The YAML `deployment.cloudrun` section is not currently consumed. Explicit parameters override the settings above when needed:

```powershell
.\deploy\cloudrun\dev.ps1 -ProjectId "your-project-id" -ServiceName "your-service-name" -CloudRunRegion "your-region"
```

Use `-ModelName` and `-ModelLocation` for model overrides; `-VertexLocation` remains an alias for `-ModelLocation`. Deployment does not automatically open the playground.

The script enables APIs, ensures Artifact Registry exists, builds remotely, and deploys the image. It does not provision a dedicated runtime account or grant its model permissions. **Do not pass `-AllowUnauthenticated`.**

After deployment completes, start the authenticated proxy:

```powershell
gcloud.cmd run services proxy your-service-name --port 8081 --region your-region --project your-project-id
```

Keep it running and open [ADK playground](http://127.0.0.1:8081/dev-ui/). The CLI identity needs invocation permission. After redeploying, restart the proxy and refresh with Ctrl+F5.

Install missing CLI components with `gcloud.cmd components install cloud-run-proxy` or `gcloud.cmd components install beta`. If Program Files is not writable, elevate only for installation, then return to a normal terminal.

### Agent Runtime

After reviewing YAML and passing the checks in [Testing](#testing):

```powershell
.\deploy\agentruntime\dev.ps1
```

This validates upload roots, runs the permission preflight, stages sanitized copies, generates runtime configuration, and deploys `agents/` with `adk deploy agent_engine`. `tools/` and `composition/` are explicit `--extra_packages`. The primary upload is never the repository root. Source and model-config staging folders are cleaned afterward. This does not enable APIs or grant roles.

A null/empty effective `agent_engine_id` creates a **new resource**; the display name does not identify an update. Save the numeric ID printed after success:

```yaml
agent_engine_id: "1234567890"
```

Run the same command to update it, keeping the original project and region. Alternatively pass `-AgentEngineId "1234567890"`.

ADK generates its own build files. This workflow does not use the root Dockerfile or automatically consume root `uv.lock`. The tracked `agents/requirements.txt` is an exact dependency export from the lock, and a regression test detects drift. After an intentional dependency change, regenerate it:

```powershell
uv lock
uv export --locked --no-dev --no-hashes --no-emit-project --no-annotate --output-file agents/requirements.txt
uv sync --locked
```

The SDK may append a compatible Agent Platform minimum-version constraint during staging; the exported exact pins remain. Both wrappers reject `.env` and unexpected data/credential files inside all three upload roots. Staging copies Python sources, the manifest, and exported requirements while omitting caches; symlinks/junctions are rejected. Future capability data files require an explicit packaging-policy change. Docker uses an allowlist of application/build inputs. Tests inspect the actual SDK-generated artifact with the cloud client mocked, plus the root Dockerfile's copy and startup paths. Test any deployed resource separately through its authenticated API and confirm a real model response.

## CI/CD Pipeline

No CI/CD workflow is configured in this repository. Tests and deployments are currently run manually. Cloud Build invoked by the Cloud Run script is not an automatic Git-triggered pipeline.

## Logging & Monitoring

- Local ADK commands print logs and may report a log-file location.
- Inspect Cloud Run revision and Cloud Build logs in Google Cloud Console.
- For Agent Runtime, inspect the deployment operation and relevant Cloud Logging entries.
- No repository-defined dashboards, alerts, or explicit tracing/export configuration are provided. Platform defaults may still emit telemetry.
- Never log private keys, access tokens, or sensitive conversation content.

Troubleshoot build failure, runtime startup, authentication, and model errors separately.

## Security

- Keep Cloud Run private and use authenticated access. Local ADK UI is a development tool, not a public application.
- Keep keys outside the repository. A service-account email is an identifier; its private key is secret.
- [sa-key.example.json](sa-key.example.json) is fake and cannot authenticate. Never fill it with real secrets.
- Real YAML is ignored; [the example template](config/settings.dev.example.yaml) stays eligible for Git.
- Ignore rules do not remove tracked secrets or detect every filename. Revoke/rotate any exposed key.
- Git, Docker, Cloud Build, and SDK packaging exclusions are distinct. Keep all secrets outside `agents/`, `tools/`, and `composition/`.
- Both wrappers validate those upload roots. Agent Runtime also rejects configured keys under any of them. Temporary model config and the capability manifest contain no credentials.
- Durable storage is not configured by the Cloud Run script; instance-local data is temporary. Review persistence and security before production use.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Direct Cloud Run URL returns 403 | Use the authenticated proxy and verify invocation permission |
| Root URL returns `Not Found` | Open `/dev-ui/` or `/docs`; older API-only revisions need UI-enabled redeployment |
| Blank UI / `origin not allowed` | Verify allowed origins in the deployed Dockerfile; do not make the service public |
| Missing SDK / `Client.runtimes` | Run `uv sync` and check SDK compatibility |
| Missing project or YAML | Supply the correct configuration file or explicit parameters |
| `serviceusage.services.use` missing | Grant Service Usage Consumer to the deployer on the project |
| `iam.serviceAccounts.actAs` missing | Grant Service Account User on the runtime account, not Service Account Admin |
| `SERVICE_DISABLED` / other 403 | Inspect the named API or denied operation; avoid broad role grants |
| Artifact Registry `NOT_FOUND` | The script attempts creation; inspect any subsequent creation error |
| Model 404 | Check model ID, model location, and project access |
| UI loads but agent fails | Inspect runtime identity permissions and the model error |
| `unrecognized arguments: ^` | Use one-line commands or PowerShell backticks, not cmd.exe carets |
| SDK component installation denied | Elevate for component installation only |
| Key file not found | Correct `credentials_file`; relative paths resolve from the repo root |

The Dockerfile allows localhost and 127.0.0.1 on ports 8080 and 8081. Another proxy port requires its exact origin and redeployment. To check origin handling:

```powershell
(Invoke-WebRequest -Uri 'http://127.0.0.1:8081/dev-ui/' -Headers @{ Origin = 'http://127.0.0.1:8081' } -UseBasicParsing).StatusCode
```

Expect 200. This verifies HTML access, not JavaScript loading or model behavior.

## Contributing

Suggested workflow; automated enforcement is not configured:

1. Create a focused branch and keep changes small.
2. Update placeholder examples and this README when behavior changes.
3. Run offline tests and a deployment preview.
4. Review `git diff --cached` for credentials before committing.
5. Open a pull request explaining the change and checks performed.

Do not deploy or modify shared IAM solely to test an unrelated documentation change.

## License

No license specified. Do not assume permission to use or redistribute the project under an open-source license.

## Maintainers

Ravi Teja Gonnabathula — [GitHub](https://github.com/RaviTejaGonnabathula).

For Google Cloud deployment details, consult [Runtime setup](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/setup) and [deployment configuration](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/deploy-an-agent).
