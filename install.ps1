# Windows installer for cursorswap (the Python package, installed as a uv tool).
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.ps1 | iex"
# Installs uv first if it's missing. Run from a checkout, it installs that
# checkout instead of GitHub main.
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found - installing it (https://docs.astral.sh/uv/)..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$HOME\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv install failed - install it manually, then re-run"
    }
}

$source = "git+https://github.com/CuKhoi/cursor-swap"
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "pyproject.toml"))) {
    $source = $PSScriptRoot
}

uv tool install --force --python 3.12 $source
if ($LASTEXITCODE) { throw "uv tool install failed" }

$dest = (uv tool dir --bin)
Write-Host "Installed to $dest\cursorswap.exe"
if (($env:Path -split ";") -notcontains $dest) {
    Write-Host "note: $dest is not on your PATH - run: uv tool update-shell, then open a new terminal"
}
Write-Host "Run: cursorswap --help"
