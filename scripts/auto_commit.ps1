# auto_commit.ps1 - safe auto-commit of tracked changes only.
# Runs after Claude file edits (PostToolUse hook) and via Task Scheduler.
# NEVER stages untracked files - protects .env and secrets.
# NEVER runs during merge/rebase/cherry-pick in progress.
# Always exits 0 - never crashes or fails the calling hook.

param(
    [string]$RepoDir = "D:\facial_recognistion"
)

$ErrorActionPreference = "SilentlyContinue"

try {
    # Guard: directory must exist
    if (-not (Test-Path $RepoDir -PathType Container)) { exit 0 }
    Set-Location $RepoDir

    # Guard: must be a git repo
    if (-not (Test-Path ".git" -PathType Container)) { exit 0 }

    # Guard: bail if a merge, rebase, cherry-pick, or bisect is in progress.
    # Committing during these would corrupt the operation.
    $lockFiles = @(
        ".git\MERGE_HEAD",
        ".git\REBASE_HEAD",
        ".git\CHERRY_PICK_HEAD",
        ".git\REVERT_HEAD",
        ".git\BISECT_LOG"
    )
    foreach ($lf in $lockFiles) {
        if (Test-Path $lf) { exit 0 }
    }

    # Guard: bail if git index is locked (another git process is running)
    if (Test-Path ".git\index.lock") { exit 0 }

    # Check for changes to tracked files only
    $unstaged = git diff --name-only 2>$null
    $alreadyStaged = git diff --staged --name-only 2>$null
    if (-not $unstaged -and -not $alreadyStaged) { exit 0 }

    # Stage tracked changes only (git add -u never touches untracked files)
    git add -u 2>$null

    # Confirm something is actually staged after add
    $staged = git diff --staged --name-only 2>$null
    if (-not $staged) { exit 0 }

    # Build a readable commit message: "auto: WIP 14:32 -- file1.py, file2.py (+3)"
    $files = ($staged -split "`n") | Where-Object { $_ -ne "" }
    $preview = ($files | Select-Object -First 3) -join ", "
    if ($files.Count -gt 3) { $preview += " (+$($files.Count - 3))" }
    $ts = Get-Date -Format "HH:mm"

    git commit -m "auto: WIP $ts -- $preview" 2>$null
    if ($LASTEXITCODE -ne 0) { exit 0 }

    # Push best-effort - silent on auth failures, network issues, etc.
    git push origin HEAD 2>$null

} catch {
    # Swallow everything - this script must never crash the hook or Task Scheduler
}

exit 0
