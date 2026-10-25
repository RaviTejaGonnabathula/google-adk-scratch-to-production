
# =============================================================================
# 1. DEPLOYMENT PARAMETERS
# =============================================================================
# Defines the Google Cloud project, deployment regions, service name,
# Artifact Registry repository, and whether public access is allowed.

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
    [string]$CloudRunRegion = $(if ($env:CLOUD_RUN_REGION) { $env:CLOUD_RUN_REGION } else { "us-central1" }),
    [Alias('VertexLocation')]
    [string]$ModelLocation,
    [string]$ModelName,
    [string]$ConfigPath,
    [string]$ServiceName = "google-adk-scratch-to-production-dev",
    [string]$ArtifactRepository = "cloud-run-source-deploy",
    [switch]$AllowUnauthenticated
)


# =============================================================================
# 2. INITIALIZE PATHS AND ERROR HANDLING
# =============================================================================
# Stop on PowerShell errors, locate the repository root, and find its Dockerfile.

$ErrorActionPreference = "Stop"

# On Windows, PowerShell can resolve `gcloud` to gcloud.ps1. Calling the .cmd
# launcher avoids execution-policy failures while still using the installed
# Google Cloud CLI. Other platforms use the normal gcloud executable.
$gcloudCommand = if ($env:OS -eq "Windows_NT") { "gcloud.cmd" } else { "gcloud" }

# $PSScriptRoot = directory containing this script.
# ..\.. = navigate from deploy\cloudrun back to the repository root.
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$dockerfilePath = Join-Path $repositoryRoot "Dockerfile"

# PowerShell does not automatically load a repository .env file. Read the
# project setting here so this script uses the same project as local ADK
# development. Model settings are resolved separately below. Explicit parameters and existing
# environment variables still take priority over values from .env.
$dotenvPath = Join-Path $repositoryRoot ".env"
$dotenvValues = @{}

if (Test-Path -LiteralPath $dotenvPath) {
    foreach ($line in Get-Content -LiteralPath $dotenvPath) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $key = $Matches[1]
            $value = $Matches[2].Trim()

            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }

            $dotenvValues[$key] = $value
        }
    }
}

if (-not $PSBoundParameters.ContainsKey("ProjectId") -and
    [string]::IsNullOrWhiteSpace($ProjectId) -and
    $dotenvValues.ContainsKey("GOOGLE_CLOUD_PROJECT")) {
    $ProjectId = $dotenvValues["GOOGLE_CLOUD_PROJECT"]
}

# Resolve only shared model settings from YAML. Other Cloud Run options retain
# their existing parameter/.env behavior; YAML credentials are not used here.
if (-not $ConfigPath) { $ConfigPath = Join-Path $repositoryRoot 'config/settings.dev.yaml' }
$pythonCommand = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
$configHelper = Join-Path $repositoryRoot 'deploy/agentruntime/config.py'
$modelArgs = @($configHelper, '--model-config', $ConfigPath)
if ($PSBoundParameters.ContainsKey('ModelName')) { $modelArgs += @('--model-name', $ModelName) }
if ($PSBoundParameters.ContainsKey('ModelLocation')) { $modelArgs += @('--model-location', $ModelLocation) }
$modelJson = & $pythonCommand @modelArgs
if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve shared model settings.' }
$modelSettings = $modelJson | ConvertFrom-Json
$ModelName = $modelSettings.model_name
$ModelLocation = $modelSettings.model_location


# =============================================================================
# 3. VALIDATE PREREQUISITES
# =============================================================================
# Ensure gcloud is installed, a project ID is provided, and the Dockerfile
# exists and is not empty before starting deployment.

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

Assert-Command $gcloudCommand

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "ProjectId is required. Set GOOGLE_CLOUD_PROJECT or pass -ProjectId."
}

if (-not (Test-Path -LiteralPath $dockerfilePath)) {
    throw "Dockerfile was not found at $dockerfilePath."
}

if ((Get-Item -LiteralPath $dockerfilePath).Length -eq 0) {
    throw "Dockerfile is empty. Configure the Dockerfile before deploying."
}


# =============================================================================
# 4. GENERATE DOCKER IMAGE NAME
# =============================================================================
# Create a timestamped image tag to distinguish deployments.
# Image format: REGION-docker.pkg.dev/PROJECT/REPOSITORY/IMAGE:TAG

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$image = "$CloudRunRegion-docker.pkg.dev/$ProjectId/$ArtifactRepository/$ServiceName`:$timestamp"

Write-Host "Project:          $ProjectId"
Write-Host "Cloud Run region: $CloudRunRegion"
Write-Host "Model location:   $ModelLocation"
Write-Host "Model name:       $ModelName"
Write-Host "Service:          $ServiceName"
Write-Host "Image:            $image"

# Stop before all cloud operations when previewing.
if (-not $PSCmdlet.ShouldProcess("$ProjectId/$CloudRunRegion/$ServiceName", 'Build and deploy Cloud Run')) { return }


# =============================================================================
# 5. ENABLE REQUIRED GOOGLE CLOUD APIs
# =============================================================================
# Enable Cloud Run, Artifact Registry, Cloud Build, and Vertex AI APIs.
# The backtick (`) allows a PowerShell command to continue on the next line.

Write-Host "Enabling required Google Cloud APIs..."

& $gcloudCommand services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    aiplatform.googleapis.com `
    --project $ProjectId

# $LASTEXITCODE = exit code of the previous native command (0 = success).
if ($LASTEXITCODE -ne 0) { throw "Failed to enable required Google Cloud APIs." }


# =============================================================================
# 6. CREATE OR REUSE ARTIFACT REGISTRY
# =============================================================================
# Artifact Registry stores our Docker container images.
# Check whether the repository exists; attempt creation if lookup fails.

Write-Host "Ensuring the Artifact Registry repository exists..."

# `gcloud describe` returns exit code 1 when the repository is absent. Because
# this script uses ErrorActionPreference=Stop, temporarily allow that expected
# lookup failure so the following create command can run.
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"

& $gcloudCommand artifacts repositories describe $ArtifactRepository `
    --location $CloudRunRegion `
    --project $ProjectId *> $null

$repositoryExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $previousErrorActionPreference

if (-not $repositoryExists) {
    Write-Host "Artifact Registry repository '$ArtifactRepository' was not found; creating it..."

    & $gcloudCommand artifacts repositories create $ArtifactRepository `
        --repository-format docker `
        --location $CloudRunRegion `
        --description "Cloud Run container images" `
        --project $ProjectId

    if ($LASTEXITCODE -ne 0) { throw "Failed to create the Artifact Registry repository." }
}


# =============================================================================
# 7. BUILD AND PUSH DOCKER IMAGE
# =============================================================================
# Cloud Build uses the Dockerfile to build our application image
# and pushes the resulting image to Artifact Registry.

Write-Host "Building the container image with Cloud Build..."

# Temporarily switch to the repository root for the build.
Push-Location $repositoryRoot

try {
    # Submit current directory (.) as the Cloud Build source context.
    & $gcloudCommand builds submit . --tag $image --project $ProjectId

    if ($LASTEXITCODE -ne 0) { throw "Cloud Build failed." }
}
finally {
    # Restore the previous working directory, even if the build fails.
    Pop-Location
}


# =============================================================================
# 8. CONFIGURE CLOUD RUN ACCESS
# =============================================================================
# By default, Cloud Run requires authenticated invocation.
# -AllowUnauthenticated requests public access when explicitly provided.

$authFlag = "--no-allow-unauthenticated"

if ($AllowUnauthenticated) {
    $authFlag = "--allow-unauthenticated"
}


# =============================================================================
# 9. DEPLOY APPLICATION TO GOOGLE CLOUD RUN
# =============================================================================
# Deploy the built image as a managed Cloud Run service.
# Configure CPU, memory, port, timeout, and Vertex AI environment variables.

Write-Host "Deploying to Cloud Run..."

& $gcloudCommand run deploy $ServiceName `
    --image $image `
    --project $ProjectId `
    --region $CloudRunRegion `
    --platform managed `
    --port 8080 `
    --memory 1Gi `
    --cpu 1 `
    --timeout 300 `
    --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$ProjectId,GOOGLE_CLOUD_LOCATION=$ModelLocation,ADK_MODEL_NAME=$ModelName,ADK_MODEL_LOCATION=$ModelLocation" `
    $authFlag

if ($LASTEXITCODE -ne 0) { throw "Cloud Run deployment failed." }


# =============================================================================
# 10. RETRIEVE DEPLOYED SERVICE URL
# =============================================================================
# Fetch the Cloud Run endpoint and display it after deployment.
# The URL may still require authentication depending on access settings.

$serviceUrl = & $gcloudCommand run services describe $ServiceName `
    --project $ProjectId `
    --region $CloudRunRegion `
    --format "value(status.url)"

Write-Host "Deployment complete: $serviceUrl" -ForegroundColor Green
