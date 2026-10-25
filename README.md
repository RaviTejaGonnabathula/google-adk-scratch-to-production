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

## Project Structure

```text
app/src/
  agent.py                         # Local entry point
  agents/
    __init__.py
    agent.py                       # Exports root_agent
    model_settings.py              # Shared model configuration loader
    master/
      __init__.py
      agent.py                     # Agent and Gemini client configuration
config/
  settings.dev.example.yaml        # Safe deployment template
deploy/
  cloudrun/dev.ps1                 # Private Cloud Run deployment
  agentruntime/
    dev.ps1                        # YAML-driven deployment wrapper
    config.py                      # YAML, runtime config, and IAM checks
    test_config.py                 # Offline tests
sa-key.example.json                # Fake key-format example
Dockerfile                         # Cloud Run build and startup
pyproject.toml / uv.lock            # Dependencies
.python-version                    # Development Python version
.gitignore / .dockerignore / .gcloudignore
README.md                          # Single project guide
```

Local `.env`, `config/settings.dev.yaml`, real keys, environments, and caches are omitted. The fake key example currently lives at the repository root.

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
uv run adk run app/src
```

Development UI:

```powershell
uv run adk web app/src --host 127.0.0.1 --port 8000 --no-reload
```

Open [local ADK UI](http://127.0.0.1:8000/dev-ui/). Stop with Ctrl+C. The local server is for trusted development use; do not expose it publicly. Model requests may incur charges.

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
uv pip check
uv run python -m unittest discover -s deploy/agentruntime -p test_config.py
.\deploy\agentruntime\dev.ps1 -WhatIf
.\deploy\cloudrun\dev.ps1 -WhatIf
.\deploy\agentruntime\dev.ps1 -CheckPermissions
```

The offline suite covers configuration, location separation, and mocked permission outcomes. `-WhatIf` previews locally without cloud calls. `-CheckPermissions` performs read-only live checks using deployment credentials.

Core checks cover project access, service usage, agent create/update, and runtime-account `actAs`. They do not validate all APIs, billing, build permissions, quota, model availability, startup, or an actual agent response. Automated integration and end-to-end tests are not configured.

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

This runs the permission preflight, generates runtime configuration, and deploys `app/src/agents` with `adk deploy agent_engine`. It does not enable APIs or grant roles.

A null/empty effective `agent_engine_id` creates a **new resource**; the display name does not identify an update. Save the numeric ID printed after success:

```yaml
agent_engine_id: "1234567890"
```

Run the same command to update it, keeping the original project and region. Alternatively pass `-AgentEngineId "1234567890"`.

ADK generates its own build files. This workflow does not use the root Dockerfile or automatically apply root `uv.lock` to remote dependencies. Review packaging when adding libraries. Test the deployed resource through its supported authenticated API or console and confirm a real model response.

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
- Git, Docker, Cloud Build, and SDK packaging exclusions are distinct. Keep all secrets outside `app/src/agents`.
- The Agent Runtime wrapper rejects an agent-local `.env` and configured keys inside the uploaded package. Temporary model config contains no credentials.
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
