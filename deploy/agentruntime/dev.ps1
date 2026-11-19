# Deploy the existing ADK agent using the installed Agent Engine/Runtime CLI.
# This is independent of Cloud Run: it does not use the root Dockerfile.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ConfigPath,
    [switch]$CheckPermissions,
    [string]$CredentialsFile,
    [string]$ProjectId,
    [ValidatePattern('^[a-z]+-[a-z]+[0-9]+$')]
    [string]$Region,
    [string]$ModelLocation,
    [string]$ModelName,
    [string]$DisplayName = 'adk-agent-dev',
    [ValidatePattern('^[0-9]+$')]
    [string]$AgentEngineId,
    [string]$ServiceAccount
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $ConfigPath) { $ConfigPath = Join-Path $repositoryRoot 'config/settings.dev.yaml' }
$adkCommand = Join-Path $repositoryRoot '.venv\Scripts\adk.exe'
$pythonCommand = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$configHelper = Join-Path $PSScriptRoot 'config.py'
# Use the project's YAML parser, never execute YAML as PowerShell code.
$configArgs = @($configHelper, '--config', $ConfigPath)
if ($PSBoundParameters.ContainsKey('ModelName')) { $configArgs += @('--model-name', $ModelName) }
if ($PSBoundParameters.ContainsKey('ModelLocation')) { $configArgs += @('--model-location', $ModelLocation) }
$configJson = & $pythonCommand @configArgs
if ($LASTEXITCODE -ne 0) { throw 'Unable to load deployment YAML.' }
$settings = $configJson | ConvertFrom-Json
$mapping = @{
    ProjectId = 'project_id'; Region = 'region'; DisplayName = 'display_name'
    ServiceAccount = 'service_account'; AgentEngineId = 'agent_engine_id'
    CredentialsFile = 'credentials_file'
    ModelLocation = 'model_location'
    ModelName = 'model_name'
}
foreach ($name in $mapping.Keys) {
    if (-not $PSBoundParameters.ContainsKey($name)) {
        $value = $settings.($mapping[$name])
        if ($null -ne $value) { Set-Variable -Name $name -Value $value -WhatIf:$false }
    }
}
if (-not $ProjectId) { $ProjectId = $env:GOOGLE_CLOUD_PROJECT }
if ($Region -notmatch '^[a-z]+-[a-z]+[0-9]+$') { throw 'A regional runtime location is required.' }
if ($ModelLocation -notmatch '^[a-z][a-z0-9-]*$') { throw 'Set model_location independently of the hosting region.' }
if ($ProjectId -and $ProjectId -notmatch '^[a-z][a-z0-9-]+$') { throw 'Invalid project ID.' }
if ($ServiceAccount -notmatch '^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.iam\.gserviceaccount\.com$') {
    throw 'Set service_account to a runtime service-account email, not a key path.'
}
if ($AgentEngineId -and $AgentEngineId -notmatch '^[0-9]+$') { throw 'Invalid resource ID.' }
if ($CredentialsFile) {
    if (-not [IO.Path]::IsPathRooted($CredentialsFile)) {
        $CredentialsFile = Join-Path $repositoryRoot $CredentialsFile
    }
    $CredentialsFile = (Resolve-Path -LiteralPath $CredentialsFile).Path
}
# Validate all three upload roots, including files copied as extra packages.
$agentPath = Join-Path $repositoryRoot 'agents'
$packageHelper = Join-Path $PSScriptRoot 'package_sources.py'
$packageArgs = @('--repository', $repositoryRoot)
if ($CredentialsFile) { $packageArgs += @('--credentials-file', $CredentialsFile) }
& $pythonCommand $packageHelper @packageArgs
if ($LASTEXITCODE -ne 0) { throw 'Application packaging validation failed.' }

# Read only the project setting; do not upload the repository's .env or secrets.
# Explicit parameters and an existing process environment take precedence.
if (-not $PSBoundParameters.ContainsKey('ProjectId') -and
    [string]::IsNullOrWhiteSpace($ProjectId)) {
    $dotenvPath = Join-Path $repositoryRoot '.env'
    if (Test-Path -LiteralPath $dotenvPath) {
        foreach ($line in Get-Content -LiteralPath $dotenvPath) {
            if ($line -match '^\s*GOOGLE_CLOUD_PROJECT\s*=\s*(.*?)\s*$') {
                $ProjectId = $Matches[1].Trim().Trim('"').Trim("'")
            }
        }
    }
}
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw 'Set GOOGLE_CLOUD_PROJECT in the root .env or pass -ProjectId.'
}
if (-not (Test-Path -LiteralPath $adkCommand)) {
    throw 'Project ADK executable missing. Run uv sync from the repository root.'
}
if (-not (Test-Path -LiteralPath (Join-Path $agentPath 'agent.py'))) {
    throw 'The agents/agent.py entry point is missing.'
}
# The deployment CLI reads an agent-local .env automatically. Refuse that case
# rather than accidentally publishing credentials with the source package.
if (Test-Path -LiteralPath (Join-Path $agentPath '.env')) {
    throw 'Remove the agent-local .env from agents before deployment; keep local settings in the repository root.'
}

$deployArgs = @('deploy', 'agent_engine', '--project', $ProjectId,
    '--region', $Region, '--display_name', $DisplayName)
if ($AgentEngineId) { $deployArgs += @('--agent_engine_id', $AgentEngineId) }
if ($ServiceAccount) { $deployArgs += @('--service_account', $ServiceAccount) }

# ADK can clear --temp_folder before generating files. Always provide a fresh,
# unique path outside the source tree; never point it at an existing workspace.
$buildPath = Join-Path ([IO.Path]::GetTempPath()) ('adk-runtime-' + [guid]::NewGuid().ToString('N'))
$deployArgs += @('--temp_folder', $buildPath)
$operation = if ($AgentEngineId) { 'Update Agent Runtime resource' } else { 'Create NEW Agent Runtime resource' }
Write-Host "Action: $operation"
Write-Host "Runtime region: $Region"
Write-Host "Gemini model location: $ModelLocation"
Write-Host "Gemini model: $ModelName"
Write-Host 'Cloud Run is unchanged. No public-access IAM binding will be added.'
if ($CheckPermissions -or $PSCmdlet.ShouldProcess("$ProjectId/$Region ($DisplayName)", $operation)) {
    # Scope ADC and gcloud override to this invocation, restoring caller state even on failure.
    $previousAdc = $env:GOOGLE_APPLICATION_CREDENTIALS
    $previousGcloud = $env:CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE
    $runtimeConfigPath = $null
    $sourceRoot = $null
    Push-Location $repositoryRoot
    try {
        if ($CredentialsFile) {
            $env:GOOGLE_APPLICATION_CREDENTIALS = $CredentialsFile
            $env:CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE = $CredentialsFile
        }
        $checkArgs = @($configHelper, '--project', $ProjectId, '--account', $ServiceAccount)
        if ($AgentEngineId) { $checkArgs += '--updating' }
        & $pythonCommand @checkArgs
        if ($LASTEXITCODE -ne 0) { throw 'Permission preflight failed; deployment blocked.' }
        if ($CheckPermissions) { return }
        $sourceJson = & $pythonCommand $packageHelper @packageArgs --prepare
        if ($LASTEXITCODE -ne 0) { throw 'Application source staging failed.' }
        $sources = $sourceJson | ConvertFrom-Json
        $sourceRoot = $sources.root
        $deployArgs += @('--extra_packages', $sources.tools, '--extra_packages', $sources.composition, $sources.agents)
        # Pass a non-secret model-only variable via ADK's supported runtime config.
        $runtimeConfigPath = & $pythonCommand $configHelper --write-runtime-config $ModelLocation --model-name $ModelName
        if ($LASTEXITCODE -ne 0) { throw 'Failed to generate model runtime configuration.' }
        $deployArgs += @('--agent_engine_config_file', $runtimeConfigPath)
        & $adkCommand @deployArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Agent Runtime deployment failed (exit $LASTEXITCODE). Review the ADK error above."
        }
        Write-Host 'Deployment completed. Save the resource ID printed by ADK for subsequent updates.'
    }
    finally {
        # Restore caller state even if removing a temporary file fails.
        $env:GOOGLE_APPLICATION_CREDENTIALS = $previousAdc
        $env:CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE = $previousGcloud
        Pop-Location
        if ($sourceRoot -and (Test-Path -LiteralPath $sourceRoot)) {
            $resolvedSourceRoot = (Resolve-Path -LiteralPath $sourceRoot).Path
            $expectedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
            if ([IO.Path]::GetDirectoryName($resolvedSourceRoot) -ne $expectedTempRoot -or
                [IO.Path]::GetFileName($resolvedSourceRoot) -notmatch '^adk-sources-[a-zA-Z0-9_-]+-packages$') {
                throw 'Refusing to remove unexpected staging directory.'
            }
            Remove-Item -LiteralPath $resolvedSourceRoot -Recurse -Force
        }
        if ($runtimeConfigPath -and (Test-Path -LiteralPath $runtimeConfigPath)) {
            Remove-Item -LiteralPath $runtimeConfigPath -Force
        }
    }
}
