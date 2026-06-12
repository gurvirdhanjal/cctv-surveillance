# auto_commit.ps1 — safe auto-commit of tracked changes only.
# Runs after Claude file edits (PostToolUse hook) and via Task Scheduler.
# Never stages untracked files — protects against accidentally committing .env or secrets.

param(
    [string]$RepoDir = "D:\facial_recognistion"
)

Set-Location $RepoDir

# Exit silently if not a git repo
if (-not (Test-Path ".git")) { exit 0 }

# Check for unstaged changes to tracked files only
$diff = git diff --name-only 2>$null
$staged = git diff --staged --name-only 2>$null

if (-not $diff -and -not $staged) { exit 0 }  # nothing to commit

# Stage tracked changes only (never git add -A — could catch .env, secrets)
git add -u 2>$null

# Confirm something is actually staged
$staged = git diff --staged --name-only 2>$null
if (-not $staged) { exit 0 }

# Build message from changed file names (first 3 files, then "and N more")
$files = $staged -split "`n" | Where-Object { $_ }
$preview = ($files | Select-Object -First 3) -join ", "
if ($files.Count -gt 3) { $preview += " and $($files.Count - 3) more" }
$ts = Get-Date -Format "HH:mm"
$msg = "auto: WIP $ts — $preview"

git commit -m $msg 2>$null
if ($LASTEXITCODE -ne 0) { exit 0 }  # nothing to commit / already clean

# Push — best-effort, silent on failure (offline, auth issues, etc.)
git push origin HEAD 2>$null
