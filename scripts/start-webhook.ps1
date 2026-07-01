param(
    [string]$Distro = "Ubuntu2404",
    [int]$Port = 8000,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$StdoutLog = Join-Path $RepoRoot "uvicorn.stdout.log"
$StderrLog = Join-Path $RepoRoot "uvicorn.stderr.log"

function Write-Step {
    param([string]$Message)
    Write-Host "[start-webhook] $Message"
}

Write-Step "Starting WSL distro: $Distro"
& wsl.exe -d $Distro -- true
if ($LASTEXITCODE -ne 0) {
    throw "WSL distro '$Distro' could not be started. Check 'wsl -l -v'."
}

if ($RepoRoot.Path -notmatch "^[A-Za-z]:\\") {
    throw "Only local Windows drive paths are supported: $($RepoRoot.Path)"
}

$Drive = $RepoRoot.Path.Substring(0, 1).ToLowerInvariant()
$Rest = $RepoRoot.Path.Substring(2).TrimStart("\").Replace("\", "/")
$LinuxRepo = "/mnt/$Drive/$Rest"

Write-Step "Repository: $LinuxRepo"

$InstallFlag = if ($SkipInstall) { "0" } else { "1" }
Write-Step "Preparing application inside WSL"
& wsl.exe -d $Distro -- bash "$LinuxRepo/scripts/start-webhook.sh" "$LinuxRepo" "$Port" "$InstallFlag"
if ($LASTEXITCODE -ne 0) {
    throw "WSL bootstrap failed."
}

Write-Step "Launching Uvicorn on http://localhost:$Port"
$StartCommand = "cd '$LinuxRepo' && . .venv/bin/activate && exec uvicorn Src.main:app --host 0.0.0.0 --port $Port"
Start-Process `
    -WindowStyle Hidden `
    -FilePath "wsl.exe" `
    -ArgumentList @("-d", $Distro, "--", "bash", "-lc", $StartCommand) `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog

Write-Step "Waiting for server readiness"
$DocsUrl = "http://localhost:$Port/docs"
$Ready = $false
for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $DocsUrl -TimeoutSec 2
        if ($Response.StatusCode -eq 200) {
            $Ready = $true
            break
        }
    } catch {
        # Keep waiting until Uvicorn has finished startup.
    }
}

if (-not $Ready) {
    Write-Host ""
    Write-Host "Server did not respond within the timeout."
    Write-Host "Check logs:"
    Write-Host "  $StdoutLog"
    Write-Host "  $StderrLog"
    exit 1
}

Write-Host ""
Write-Host "Webhook server is running."
Write-Host "Docs: $DocsUrl"
Write-Host "Stop: wsl -d $Distro -- pkill -f uvicorn"
