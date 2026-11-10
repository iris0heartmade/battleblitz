param([string]$GodotExe = $env:GODOT_EXE, [switch]$PreviewOnly, [switch]$VerifyBattle)
& (Join-Path $PSScriptRoot 'run_godot.ps1') @PSBoundParameters
exit $LASTEXITCODE
