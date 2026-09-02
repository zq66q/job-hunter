[CmdletBinding()]
param(
	[switch]$SkipChrome,
	[string]$PythonPath
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# Resolution order (highest priority first):
#   1. Explicit -PythonPath override
#   2. The job-agent project's local virtualenv (./.venv / .\.venv)
#   3. jobagent on PATH (may be missing when launched from a desktop icon)
#   4. System 'py' / 'python' (last-resort fallback; may not have jobagent installed)
$VenvScripts = $null
$VenvCandidate = Join-Path $RepoRoot ".venv\Scripts"
if (Test-Path -LiteralPath $VenvCandidate) {
	$VenvScripts = (Resolve-Path -LiteralPath $VenvCandidate).Path
}

function Resolve-JobagentCommand {
	param([string]$VenvScriptsDir, [string]$Override)
	if ($Override) {
		if (-not (Test-Path -LiteralPath $Override)) {
			throw "Configured Python was not found: $Override"
		}
		return [pscustomobject]@{ Source = (Resolve-Path -LiteralPath $Override).Path; Prefix = @("-m", "jobagent.main") }
	}
	if ($VenvScriptsDir) {
		$VenvExe = Join-Path $VenvScriptsDir "python.exe"
		$VenvScript = Join-Path $VenvScriptsDir "jobagent.exe"
		if (Test-Path -LiteralPath $VenvScript) {
			return [pscustomobject]@{ Source = $VenvScript; Prefix = @() }
		}
		if (Test-Path -LiteralPath $VenvExe) {
			return [pscustomobject]@{ Source = $VenvExe; Prefix = @("-m", "jobagent.main") }
		}
	}
	$Jobagent = Get-Command "jobagent" -ErrorAction SilentlyContinue
	if ($Jobagent) {
		return [pscustomobject]@{ Source = $Jobagent.Source; Prefix = @() }
	}
	$Python = Get-Command "py" -ErrorAction SilentlyContinue
	if (-not $Python) {
		$Python = Get-Command "python" -ErrorAction SilentlyContinue
	}
	if (-not $Python) {
		throw "Could not find job-agent or Python. Install the project first with: pip install -e ."
	}
	return [pscustomobject]@{ Source = $Python.Source; Prefix = @("-m", "jobagent.main") }
}

$Resolved = Resolve-JobagentCommand -VenvScriptsDir $VenvScripts -Override $PythonPath
$Runner = $Resolved.Source
$RunnerPrefix = $Resolved.Prefix

$ChromeCandidates = @()
if ($env:ProgramFiles) {
	$ChromeCandidates += Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"
}
if (${env:ProgramFiles(x86)}) {
	$ChromeCandidates += Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"
}
if ($env:LOCALAPPDATA) {
	$ChromeCandidates += Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe"
}
$ChromeCandidates = $ChromeCandidates | Where-Object { Test-Path -LiteralPath $_ }

if (-not $ChromeCandidates) {
	throw "Could not find Google Chrome. Install Chrome or set up a compatible browser manually."
}

$Chrome = $ChromeCandidates | Select-Object -First 1
$ChromeProfile = Join-Path $env:LOCALAPPDATA "JobAgentChrome"
$ChromeArguments = @(
	"--remote-debugging-port=9222",
	"--user-data-dir=$ChromeProfile",
	"https://www.zhipin.com"
)

if (-not $SkipChrome) {
	Write-Host "Starting the job-agent Chrome profile..."
	Start-Process -FilePath $Chrome -ArgumentList $ChromeArguments
	$ChromeReady = $false
	for ($i = 0; $i -lt 20; $i++) {
		Start-Sleep -Milliseconds 500
		try {
			$null = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 2
			$ChromeReady = $true
			break
		} catch {
			# Chrome is still starting.
		}
	}
	if (-not $ChromeReady) {
		Write-Warning "Chrome remote debugging did not become ready within 10 seconds."
	}
}

Write-Host "Starting the Browser Runtime..."
& $Runner @RunnerPrefix "connect"
if ($LASTEXITCODE -ne 0) {
	Write-Warning "Browser connection check returned exit code $LASTEXITCODE. The workbench will still be opened."
}

Write-Host "Starting the local workbench..."
$WebArguments = @($RunnerPrefix) + @("web", "--no-open")
Start-Process -FilePath $Runner -ArgumentList $WebArguments -WorkingDirectory $RepoRoot -WindowStyle Hidden

for ($i = 0; $i -lt 20; $i++) {
	Start-Sleep -Milliseconds 500
	try {
		$null = Invoke-WebRequest -Uri "http://127.0.0.1:8686/" -UseBasicParsing -TimeoutSec 2
		break
	} catch {
		# The local server is still starting.
	}
}

if (-not $SkipChrome) {
	Start-Process -FilePath $Chrome -ArgumentList @(
		"--remote-debugging-port=9222",
		"--user-data-dir=$ChromeProfile",
		"http://127.0.0.1:8686"
	)
}

Write-Host "job-agent is ready. Log in manually in the dedicated Chrome window if needed."
