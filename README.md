# Google ADK Scratch to Production

A Google Agent Development Kit (ADK) project using Vertex AI, deployed to **private Google Cloud Run** with the ADK development UI.

Run commands from the repository root in **Windows PowerShell**. All deployment identifiers below are placeholders: replace `your-project-id`, `your-service-name`, `your-region`, and `your-vertex-location` with your own values. No account details or deployed service URLs are included.

## Project structure

```text
app/
└── src/
    ├── agent.py                 # ADK entry point
    └── agents/
        ├── agent.py             # Exposes root_agent
        └── master/
            └── agent.py         # Defines master_agent
deploy/
└── cloudrun/
    └── dev.ps1                  # Cloud Run deployment script
Dockerfile                       # Container image definition
pyproject.toml                   # Python project and dependency configuration
```

## Prerequisites

- Python 3.12 or newer
- `uv`
- Google Cloud CLI (`gcloud`)
- A Google Cloud project with billing enabled
- A Google account authenticated with the Google Cloud CLI

Authenticate and select the project:

```powershell
gcloud.cmd auth login
gcloud.cmd auth application-default login
gcloud.cmd config set project your-project-id
```

Install the Python dependencies:

```powershell
uv sync
```

## Vertex AI configuration

Create a local `.env` file in the repository root. Do not commit this file.

```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=your-vertex-location
```

The local ADK command reads this configuration. The Cloud Run deployment script also reads `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from this file.

## Run locally

From the repository root:

```powershell
uv run adk run app/src
```

The ADK discovers the `root_agent` exported by `app/src/agent.py`.

## ADK API server and web UI

The current [Dockerfile](Dockerfile) starts the ADK API server **with `--with_ui` enabled**. Open `/dev-ui/` for the development UI and `/docs` for API documentation. An older API-only revision may return this at `/`:

```json
{"detail":"Not Found"}
```

This response means the requested route is missing, not that authentication failed. With the private proxy running on port 8081, API documentation is available at:

```text
http://127.0.0.1:8081/docs
```

The Dockerfile also explicitly allows the local proxy browser origins listed below. Changing a local file does not update a running Cloud Run revision: redeploy to apply changes.

## Deploy to Cloud Run

The deployment script performs these operations:

1. Enables the required Google Cloud APIs.
2. Creates the Artifact Registry repository if it does not exist.
3. Builds and pushes the Docker image using Cloud Build.
4. Deploys the image to Cloud Run.
5. Configures the Vertex AI environment variables on the Cloud Run service.

Run the default private deployment:

```powershell
.\deploy\cloudrun\dev.ps1 -ProjectId "your-project-id" -ServiceName "your-service-name" -CloudRunRegion "your-region"
```

Use the same service name, project ID, and Cloud Run region when deploying and starting the proxy. Pass these explicitly rather than relying on repository-specific defaults.

**Keep this service private.** Do not supply the script's optional `-AllowUnauthenticated` switch. Enabling the web UI or allowing local origins does not require public access.

Wait for `Deployment complete` before testing. The script builds remotely using Cloud Build, so a local Docker daemon is not required. Builds, image storage, and service usage can incur Google Cloud charges.

To override values from `.env`, pass parameters explicitly:

```powershell
.\deploy\cloudrun\dev.ps1 `
  -ProjectId "your-project-id" `
  -ServiceName "your-service-name" `
  -CloudRunRegion "your-region" `
  -VertexLocation "your-vertex-location"
```

## Accessing a private Cloud Run service

The Google Cloud CLI can be authenticated while a normal browser request is still unauthenticated. A private Cloud Run service therefore returns `403 Forbidden` when its URL is opened directly.

Install the Cloud Run proxy component from an elevated Google Cloud SDK Shell if the component is missing:

```cmd
gcloud.cmd components install cloud-run-proxy
```

Then start the authenticated local proxy:

```powershell
gcloud.cmd run services proxy your-service-name --port 8081 --region your-region --project your-project-id
```

Keep that terminal running and open [the ADK UI](http://127.0.0.1:8081/dev-ui/). Stop the proxy with `Ctrl+C` when finished.

If installing the component fails because the SDK is under `Program Files`, open PowerShell **as Administrator** for the installation only. Run the proxy afterward in an ordinary terminal.

After redeploying, stop the old proxy, restart it with the command above, and hard-refresh the UI with `Ctrl+F5`. If port 8081 is already occupied by an earlier proxy, stop that proxy in its terminal first.

The proxy forwards requests to the private Cloud Run service using your authenticated Google Cloud CLI session. In PowerShell, use the backtick (`` ` ``) for multiline commands; `^` is the continuation character for `cmd.exe`, not PowerShell.

## Blank UI: confirmed cause and fix

ADK checks the browser's `Origin` header, including on JavaScript module requests. Through the Cloud Run proxy, the upstream host differs from the browser's local origin. Without an explicitly allowed origin, HTML can load while JavaScript requests fail with:

```text
403 Forbidden
Forbidden: origin not allowed
```

The current [Dockerfile](Dockerfile) supplies repeated `--allow_origins` arguments for these exact origins:

```text
http://127.0.0.1:8081
http://localhost:8081
http://127.0.0.1:8080
http://localhost:8080
```

This is separate from Cloud Run IAM. **Do not make the service public to fix it.** Reissuing identity tokens or adding IAM roles does not resolve this origin rejection. If you choose another proxy port, add its exact browser origin and redeploy.

### Apply and verify the fix

1. Run the private deployment command above with your own placeholder values and wait for successful completion.
2. Restart the private proxy on port 8081 using the command above.
3. Open `http://127.0.0.1:8081/dev-ui/` and press `Ctrl+F5`.
4. If the UI is still blank, run this read-only check in another PowerShell terminal:

```powershell
(Invoke-WebRequest -Uri 'http://127.0.0.1:8081/dev-ui/' -Headers @{ Origin = 'http://127.0.0.1:8081' } -UseBasicParsing).StatusCode
```

Expect `200`. A request without an `Origin` header is not enough to verify this fix. If the response still says `origin not allowed`, confirm the new container revision was deployed with the updated Dockerfile. A successful HTML check alone does not prove that model calls work; verify the UI loads and then test the agent separately.

## Configuration details

PowerShell does not automatically import `.env`; the deployment script reads its project and Vertex location explicitly. Current precedence, highest priority first:

| Setting | Resolution order |
| --- | --- |
| Project ID | `-ProjectId`, process `GOOGLE_CLOUD_PROJECT`, root `.env` |
| Vertex location | `-VertexLocation`, root `.env`, process `GOOGLE_CLOUD_LOCATION`, `global` |
| Cloud Run region | `-CloudRunRegion`, process `CLOUD_RUN_REGION`, script default |

`CLOUD_RUN_REGION` in `.env` is not read by the current script. Explicit parameters are the clearest way to override defaults.

Vertex AI model location and Cloud Run hosting region are separate. Choose a Vertex AI location supported by your model; do not assume a model is available in every region.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| `ProjectId is required` | Set the project in the root `.env` or pass `-ProjectId`. |
| Artifact Registry `NOT_FOUND` | The script attempts repository creation when lookup fails. If creation fails, inspect its actual error rather than assuming the repository is merely absent. |
| `403` on the direct Cloud Run URL | Use the authenticated proxy; a normal browser navigation does not carry a Cloud Run identity token. |
| `Forbidden: origin not allowed` | Follow the origin-check section above; this is not an IAM failure. |
| `unrecognized arguments: ^` | Use the one-line PowerShell commands above; `^` belongs to cmd.exe. |
| Vertex AI `SERVICE_DISABLED` | Enable the API identified in the error in the selected project and allow propagation time. |
| Publisher model `404` | Verify model ID, model location, and project access together. |
| UI loads but model requests fail | Inspect the model error and the runtime service account's Vertex AI permissions. |

## Authentication and development scope

| Identity | Purpose |
| --- | --- |
| Google Cloud CLI account | Deployment and authenticated proxy; must have invocation permission |
| Local Application Default Credentials | Local ADK calls to Vertex AI |
| Cloud Run runtime service account | Deployed ADK calls to Vertex AI; does not use local ADC |

The deployment script does not provision a dedicated runtime service account or grant its Vertex AI permissions. It also does not configure durable session or artifact storage. Treat instance-local data as temporary. This is a private **development UI**, not a finished production application.

## Security notes

- Keep `.env` out of Git and never place API keys or service-account private keys in the repository.
- The deployment script keeps Cloud Run private unless `-AllowUnauthenticated` is supplied.
- Use a dedicated service account and least-privilege IAM roles for production deployments.
