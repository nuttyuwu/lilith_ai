<#
    Lilith launcher for Windows 11 (PowerShell)

    An alternative to lilith.bat for Windows Terminal / PowerShell 7 users:
    UTF-8 works without a code-page dance, and errors are readable.

    First run:
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
        .\lilith.ps1

    Examples:
        .\lilith.ps1                # chat
        .\lilith.ps1 doctor         # setup check
        .\lilith.ps1 edit           # edit config.ini
        .\lilith.ps1 -Web           # start the web interface instead
#>

[CmdletBinding()]
param(
    [switch]$Web,
    [switch]$Reinstall,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Passthrough
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Lilith's output is UTF-8; make sure the console agrees.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

$Host.UI.RawUI.WindowTitle = 'Lilith'
Write-Host "Waking up Lilith's mind..." -ForegroundColor DarkMagenta

function Resolve-Python {
    <#
        The py launcher is tried first, and any python.exe under \WindowsApps\
        is skipped: on Windows 11 that path holds the Microsoft Store App
        Execution Alias, a 0-byte stub that opens the Store instead of running
        Python. Trusting Get-Command blindly is the most common way a working
        Python install still fails to launch anything.
    #>
    # 3.12 downwards first: llama-cpp-python only ships wheels for 3.10-3.12,
    # and "-3" means "newest installed", which on a box with 3.13/3.14 starts
    # a silent source build instead. Note the missing 2>$null -- redirecting a
    # native command's stderr under $ErrorActionPreference='Stop' turns each
    # line into a terminating NativeCommandError, which killed this launcher
    # on machines where py.exe exists but has no default Python registered.
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($version in @('-3.12', '-3.11', '-3.10', '-3')) {
            try {
                & $py.Source $version -c "import sys" | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    return @{ Exe = $py.Source; Args = @($version) }
                }
            } catch {
                # This interpreter is not installed; try the next one.
            }
        }
    }

    foreach ($candidate in (Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($candidate.Source -notmatch '\\WindowsApps\\') {
            return @{ Exe = $candidate.Source; Args = @() }
        }
    }

    Write-Host ''
    if (Get-Command python -ErrorAction SilentlyContinue) {
        Write-Host 'The only "python" on PATH is the Microsoft Store placeholder.' -ForegroundColor Red
        Write-Host 'It opens the Store rather than running Python.'
        Write-Host ''
        Write-Host 'Either install Python from https://www.python.org/downloads/,'
        Write-Host 'or turn off the stub in Settings > Apps > Advanced app settings'
        Write-Host '> App execution aliases > python.exe.'
    }
    else {
        Write-Host 'Python was not found.' -ForegroundColor Red
        Write-Host 'Install Python 3.10+ from https://www.python.org/downloads/'
        Write-Host 'Tick both "Add python.exe to PATH" and "tcl/tk and IDLE".'
    }
    exit 1
}

$activate = Join-Path $PSScriptRoot 'venv\Scripts\Activate.ps1'
$venvPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
$createdVenv = $false

if ($Reinstall -and (Test-Path 'venv')) {
    Write-Host 'Removing the existing virtual environment...' -ForegroundColor Yellow
    Remove-Item -Recurse -Force 'venv'
}

if (-not (Test-Path $activate)) {
    $python = Resolve-Python
    Write-Host "Using $($python.Exe)" -ForegroundColor DarkGray
    Write-Host 'First run: creating a virtual environment...' -ForegroundColor Cyan
    & $python.Exe @($python.Args + @('-m', 'venv', 'venv'))
    if ($LASTEXITCODE -ne 0) { Write-Host 'Could not create the venv.' -ForegroundColor Red; exit 1 }
    $createdVenv = $true
}

. $activate

# Refresh core dependencies whenever the requirements content changes.  A
# content hash is reliable across git checkouts where file timestamps may move
# backwards, unlike an mtime-only stamp.
$requirements = Join-Path $PSScriptRoot 'requirements.txt'
$requirementsStamp = Join-Path $PSScriptRoot 'venv\.requirements-sha256'
$requirementsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $requirements).Hash
$installedHash = ''
if (Test-Path -LiteralPath $requirementsStamp) {
    $installedHash = (Get-Content -Raw -LiteralPath $requirementsStamp).Trim()
}

if ($createdVenv -or $installedHash -ne $requirementsHash) {
    if ($createdVenv) {
        Write-Host 'Installing dependencies...' -ForegroundColor Cyan
        & $venvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Could not upgrade pip; see above.' -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host 'requirements.txt changed; updating dependencies...' -ForegroundColor Cyan
    }

    & $venvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Dependency installation failed; see above.' -ForegroundColor Red
        exit 1
    }
    Set-Content -LiteralPath $requirementsStamp -Value $requirementsHash -Encoding ASCII
    Write-Host 'Dependencies are up to date.' -ForegroundColor Green
    Write-Host ''
}

if ($Web) {
    Write-Host 'Starting the web interface...' -ForegroundColor DarkMagenta
    python web_lilith.py @Passthrough
}
else {
    Write-Host 'Lilith is awakening...' -ForegroundColor DarkMagenta
    Write-Host ''
    python lilith.py @Passthrough
}

$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host ''
    Write-Host "Lilith exited with code $code." -ForegroundColor Yellow
    Write-Host 'Run  .\lilith.ps1 doctor  for a setup check.'
}
exit $code
