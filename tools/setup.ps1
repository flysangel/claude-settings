# Install or update claude-settings into ~/.claude.
#
#   irm <RAW>/tools/setup.ps1 | iex
#   & ([scriptblock]::Create((irm <RAW>/tools/setup.ps1))) --replace
#   & ([scriptblock]::Create((irm <RAW>/tools/setup.ps1))) remove
#
# Exit codes: those of tools/deploy.py, plus 3 when a required command is missing.

# Set this once the public repository exists.
$DefaultRepoUrl = ''

function Invoke-ClaudeSettingsSetup {
    param([string[]]$DeployArgs)

    $repoUrl = if ($env:CLAUDE_SETTINGS_REPO) { $env:CLAUDE_SETTINGS_REPO } else { $DefaultRepoUrl }
    $cloneDir = Join-Path $env:USERPROFILE '.claude-settings'

    $missing = @('git', 'uv') | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) }
    if ($missing) {
        foreach ($cmd in $missing) { Write-Host ('{0,-9} {1}' -f 'missing', $cmd) }
        Write-Host 'Install the missing commands and run this again. Nothing was written.'
        return 3
    }

    if (-not $repoUrl) {
        [Console]::Error.WriteLine('error: the repository URL is not configured in setup.ps1')
        return 1
    }

    if (Test-Path (Join-Path $cloneDir '.git')) {
        & git -C $cloneDir pull --ff-only --quiet | Out-Host
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("error: could not update $cloneDir")
            return 1
        }
    }
    elseif (Test-Path $cloneDir) {
        [Console]::Error.WriteLine("error: $cloneDir exists and is not a clone made by this tool")
        return 1
    }
    else {
        & git clone --quiet $repoUrl $cloneDir | Out-Host
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("error: could not clone $repoUrl")
            return 1
        }
    }

    & uv run --quiet (Join-Path $cloneDir 'tools/deploy.py') @DeployArgs | Out-Host
    return $LASTEXITCODE
}

$code = Invoke-ClaudeSettingsSetup -DeployArgs $args
$global:LASTEXITCODE = $code
# Only end the process when run as a file; under `irm | iex` that would close the user's shell.
if ($MyInvocation.MyCommand.Path) { exit $code }
