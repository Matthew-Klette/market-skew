# Market Skew installer for Windows 10 and 11. Safe to run again: it only does what is missing and re-makes the shortcuts.
#   install.cmd                      full install, asks a couple of questions (double-click it, or run it in a terminal)
#   -Yes            answer the questions with their defaults (no email is asked for)
#   -SkipTests      skip the quick self-test
#   -NoShortcuts    do not add the Start menu and desktop shortcuts
#   -NoPredictor    do not offer the Google predictor (about 1.4 GB)
param(
    [switch]$Yes,
    [switch]$SkipTests,
    [switch]$NoShortcuts,
    [switch]$NoPredictor
)
$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Project
$Python = Join-Path $Project ".venv\Scripts\python.exe"
$PythonW = Join-Path $Project ".venv\Scripts\pythonw.exe"
$env:PYTHONUTF8 = "1"   # read and write files as UTF-8, as on a Mac

function Say($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Stop-Install($text) { Write-Host ""; Write-Host "Stopped: $text" -ForegroundColor Yellow; exit 1 }
function Ask($question, $default) {
    if ($Yes) { return $default -eq "Y" }
    $reply = Read-Host $question
    if ([string]::IsNullOrWhiteSpace($reply)) { $reply = $default }
    return $reply -match "^[Yy]"
}
function Invoke-Checked($exe, [string[]]$arguments, $failure) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Stop-Install $failure }
}

Say "Checking this PC"
if ($env:OS -ne "Windows_NT") { Stop-Install "install.ps1 is for Windows. On a Mac, run ./install.sh" }
$Arch = $env:PROCESSOR_ARCHITECTURE
if ($Arch -eq "AMD64") { Write-Host "Windows on a 64-bit Intel/AMD processor: good." }
elseif ($Arch -eq "ARM64") { Write-Host "Windows on ARM: fine for the app. (The Google predictor may not work on ARM.)" }
else { Stop-Install "Market Skew needs 64-bit Windows (this PC reports $Arch)." }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Stop-Install "uv (the Python package manager) is not installed. Install it yourself with:
    winget install --id=astral-sh.uv -e
or follow https://docs.astral.sh/uv/getting-started/installation/ . Then close this window, open a new one and run install.cmd again.
(This script does not download and run installers for you.)"
}
Write-Host "uv: found."

Say "Setting up Python packages"
if (-not (Test-Path $Python)) {
    Invoke-Checked "uv" @("venv", "--python", "3.12", ".venv") "uv could not create the Python environment."
} else {
    Write-Host "Python environment already there."
}
Invoke-Checked "uv" @("pip", "install", "--python", $Python, "-r", "requirements-dev.txt") "The Python packages did not install."

Say "Creating your config files (only the ones that are missing)"
Invoke-Checked $Python @("-B", "-c", "from market_skew import seed; made = seed.seed(); print('Created: ' + ', '.join(made) if made else 'Nothing to create; your files are untouched.')") "Could not create the config files."

if (-not $SkipTests) {
    Say "Running the quick self-test"
    & $Python -B -m pytest -q tests
    if ($LASTEXITCODE -ne 0) { Stop-Install "The self-test failed. Re-run with -SkipTests to install anyway, and tell whoever sent you this." }
}

if (-not $NoShortcuts) {
    Say "Adding Market Skew to the Start menu and the desktop"
    $shell = New-Object -ComObject WScript.Shell
    $places = @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))
    foreach ($place in $places) {
        $link = $shell.CreateShortcut((Join-Path $place "Market Skew.lnk"))
        $link.TargetPath = $PythonW
        $link.Arguments = "-X utf8 -I -B `"$(Join-Path $Project 'skew')`" app"
        $link.WorkingDirectory = $Project
        $link.IconLocation = "$(Join-Path $Project 'app\AppIcon.ico'),0"
        $link.Description = "Market Skew"
        $link.Save()
    }
    Write-Host "Added. Search the Start menu for Market Skew, or use the desktop icon. (Right-click it to pin it to the taskbar.)"
}

if (-not $NoPredictor) {
    Say "Google's price prediction (optional)"
    Write-Host "It adds a one-month range, with a track record, to the stocks on the Picks page."
    if ($Arch -eq "AMD64") { $default = "Y"; $prompt = "Matt recommends installing the Google predictor (about 1.4 GB, free, runs on your PC). Install it now? [Y/n]" }
    else { $default = "N"; $prompt = "Install the Google predictor (about 1.4 GB, free)? It may not run on Windows on ARM. [y/N]" }
    if (Ask $prompt $default) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Project "scripts\install-predictor.ps1")
        if ($LASTEXITCODE -ne 0) { Write-Host "The predictor did not finish installing. Everything else works; run scripts\install-predictor.ps1 to try again." }
    } else {
        Write-Host "Skipped. Add it any time with: powershell -ExecutionPolicy Bypass -File scripts\install-predictor.ps1"
    }
}

if (-not $Yes) {
    Say "Optional: an email address for SEC downloads"
    Write-Host "The US SEC asks every program that downloads company filings to say who is asking. Your address is stored only in"
    Write-Host "config\prefs.json on this PC and sent only to sec.gov. Leave it blank to skip; you can add it later in the app (How it works tab)."
    $email = Read-Host "Email (or press Enter to skip)"
    if (-not [string]::IsNullOrWhiteSpace($email)) {
        $env:SKEW_EMAIL = $email
        $save = @'
import json, os
from market_skew import settings
email = os.environ["SKEW_EMAIL"].strip()
if not settings.valid_email(email):
    print("That does not look like an email address, so nothing was saved. Add it later in the app.")
else:
    try:
        saved = json.loads(settings.PREFS.read_text())
    except (OSError, ValueError):
        saved = {}
    saved["sec_contact"] = email
    settings.PREFS.write_text(json.dumps(saved))
    print("Saved.")
'@
        $save | & $Python -B -
        Remove-Item Env:SKEW_EMAIL
    }
}

Say "Done"
Write-Host "Open it from the Start menu (search for Market Skew) or the desktop icon."
Write-Host "The first time, it asks how much you invest each month and scans the market when you open it after the US close."
Write-Host "Not financial advice. See README.md."
