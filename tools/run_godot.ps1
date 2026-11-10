param([string]$GodotExe = $env:GODOT_EXE, [switch]$PreviewOnly, [switch]$VerifyBattle, [switch]$FormalGame, [int]$QuitAfterFrames = 0)
$ErrorActionPreference = 'Stop'
$projectPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\godot-client'))
if (-not $GodotExe) {
    $command = Get-Command godot -ErrorAction SilentlyContinue
    if ($command) { $GodotExe = $command.Source }
}
if (-not $GodotExe) {
    $projectParent = Split-Path (Split-Path $projectPath -Parent) -Parent
    $candidate = Get-ChildItem -LiteralPath $projectParent -Directory -Filter 'Godot*' |
        Get-ChildItem -File -Filter '*console.exe' | Select-Object -First 1
    if ($candidate) { $GodotExe = $candidate.FullName }
}
if (-not $GodotExe -or -not (Test-Path -LiteralPath $GodotExe -PathType Leaf)) {
    throw 'Godot was not found. Set GODOT_EXE or pass -GodotExe with the engine path.'
}
$ownedBackend = $null
if ($FormalGame -and ($PreviewOnly -or $VerifyBattle)) { throw 'PreviewOnly and VerifyBattle are Demo options.' }
try {
    if (-not $PreviewOnly) {
        $configPath = Join-Path $projectPath 'demos\height_map\battle.json'
        $battleConfig = Get-Content -LiteralPath $configPath -Encoding UTF8 -Raw | ConvertFrom-Json
        $baseUrl = [string]$battleConfig.base_url
        if ($env:BB_HEIGHT_BATTLE_URL) { $baseUrl = $env:BB_HEIGHT_BATTLE_URL }
        if ($FormalGame) { $baseUrl = 'http://127.0.0.1:8000' }
        $serverUri = [Uri]$baseUrl
        $healthy = $false
        try {
            $health = Invoke-RestMethod -Uri ($baseUrl + '/healthz') -TimeoutSec 1
            $healthy = $health.status -eq 'ok'
        } catch { }
        if (-not $healthy) {
            if ($serverUri.Host -notin @('127.0.0.1', 'localhost')) {
                throw 'The configured remote battle service is unavailable.'
            }
            $gamePath = Join-Path (Split-Path $projectPath -Parent) 'game'
            $pythonPath = Join-Path $gamePath 'venv\Scripts\python.exe'
            if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
                throw 'The game Python environment is missing. Use -PreviewOnly for map preview.'
            }
            $dataPath = Join-Path $gamePath '.tmp\height-demo'
            New-Item -ItemType Directory -Force -Path $dataPath | Out-Null
            $dbPath = (Join-Path $dataPath 'battleblitz.db').Replace('\','/')
            if ($FormalGame) {
                $dbPath = (Join-Path $gamePath 'battleblitz.db').Replace('\','/')
                if (Test-Path -LiteralPath $dbPath -PathType Leaf) {
                    $backupDirectory = Join-Path $dataPath 'backups'
                    New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
                    $backupPath = Join-Path $backupDirectory ('before-height-map-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.db')
                    & $pythonPath -c 'import sqlite3,sys; source=sqlite3.connect(sys.argv[1]); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()' $dbPath $backupPath
                    if ($LASTEXITCODE -ne 0) { throw 'Database backup failed. The service was not started.' }
                }
            }
            $previousDb = $env:DATABASE_URL
            $previousHost = $env:BB_HOST
            $previousPort = $env:BB_PORT
            try {
                $env:DATABASE_URL = 'sqlite+aiosqlite:///' + $dbPath
                $listenHost = '127.0.0.1'
                if ($FormalGame) { $listenHost = '0.0.0.0' }
                $env:BB_HOST = $listenHost
                $env:BB_PORT = [string]$serverUri.Port
                $arguments = @('-m', 'uvicorn', 'app.main:app', '--app-dir', ('"' + $gamePath + '"'), '--host', $listenHost, '--port', [string]$serverUri.Port)
                $ownedBackend = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $gamePath -WindowStyle Hidden -PassThru
            } finally {
                $env:DATABASE_URL = $previousDb
                $env:BB_HOST = $previousHost
                $env:BB_PORT = $previousPort
            }
            for ($attempt = 0; $attempt -lt 30; $attempt++) {
                try {
                    $health = Invoke-RestMethod -Uri ($baseUrl + '/healthz') -TimeoutSec 1
                    if ($health.status -eq 'ok') { $healthy = $true; break }
                } catch { }
                if ($ownedBackend.HasExited) { break }
                Start-Sleep -Milliseconds 300
            }
            if (-not $healthy) { throw 'The isolated battle service did not start.' }
        }
        $api = Invoke-RestMethod -Uri ($baseUrl + '/openapi.json') -TimeoutSec 3
        if ($api.info.title -ne 'BattleBlitz Server' -or -not $api.paths.'/games/{game_id}/movement-options') {
            throw 'The configured battle service does not support this Demo version.'
        }
        if ($FormalGame -and -not $api.components.schemas.TileOut.properties.elevation) {
            throw 'The existing service is an older version. Restart that service with the updated code.'
        }
    }
    if ($VerifyBattle) {
        & $GodotExe --path $projectPath --rendering-method gl_compatibility --script res://demos/height_map/verify_battle.gd
    } elseif ($FormalGame) {
        $gameArguments = @('--path', $projectPath, 'res://scenes/main.tscn')
        if ($QuitAfterFrames -gt 0) { $gameArguments += @('--quit-after', [string]$QuitAfterFrames) }
        & $GodotExe @gameArguments
    } else {
        & $GodotExe --path $projectPath --rendering-method gl_compatibility res://demos/height_map/main.tscn
    }
    $demoExit = $LASTEXITCODE
} finally {
    if ($ownedBackend) {
        # Stop only our own helper and descendants; never stop an existing service.
        $pending = [System.Collections.Generic.Queue[int]]::new()
        $pending.Enqueue($ownedBackend.Id)
        $ownedIds = [System.Collections.Generic.List[int]]::new()
        while ($pending.Count -gt 0) {
            $parentId = $pending.Dequeue()
            $ownedIds.Add($parentId)
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$parentId" | ForEach-Object { $pending.Enqueue([int]$_.ProcessId) }
        }
        for ($index = $ownedIds.Count - 1; $index -ge 0; $index--) {
            Stop-Process -Id $ownedIds[$index] -ErrorAction SilentlyContinue
        }
    }
}
exit $demoExit
