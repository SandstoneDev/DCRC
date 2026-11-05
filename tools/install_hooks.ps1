# Select reviewed hooks without overwriting existing hook files.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
git -C $repo config --local core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) { throw 'Cannot configure repository hooks' }
Write-Host 'Selected .githooks; existing hook files were preserved.'
