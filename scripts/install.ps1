[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$SkipSmokeTest,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$configDir = if ($env:OPENCODE_CONFIG_DIR) { $env:OPENCODE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".config\opencode" }

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Action
    )
    Write-Step $Label
    if ($DryRun) {
        Write-Host "    (dry-run: no se ejecuta)" -ForegroundColor DarkGray
        return
    }
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Label fallo con codigo $LASTEXITCODE"
    }
}

function Find-BasePython {
    if ($PythonPath) {
        $exe = $PythonPath
        $prefix = @()
        $version = & $exe -c "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $version) {
            throw "No se pudo ejecutar Python en '$PythonPath'."
        }
        if ([version]($version | Select-Object -Last 1) -lt [version]"3.11") {
            throw "Python 3.11+ es obligatorio; '$PythonPath' es $version."
        }
        return @{ Exe = $exe; Prefix = $prefix }
    }

    $attempts = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $attempts += ,@("py", @("-3.11"))
        $attempts += ,@("py", @("-3"))
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $attempts += ,@("python", @())
    }

    foreach ($attempt in $attempts) {
        $exe = $attempt[0]
        $prefix = @($attempt[1])
        $version = & $exe $prefix -c "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            $last = $version | Select-Object -Last 1
            if ([version]$last -ge [version]"3.11") {
                return @{ Exe = $exe; Prefix = $prefix }
            }
        }
    }

    throw "No se encontro Python 3.11+. Instalalo desde https://www.python.org/downloads/ y vuelve a intentarlo."
}

function Find-VBoxManage {
    if ($env:VBOX_MANAGE_PATH -and (Test-Path -LiteralPath $env:VBOX_MANAGE_PATH)) {
        return $env:VBOX_MANAGE_PATH
    }
    $command = Get-Command VBoxManage.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $candidates = @(
        "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
        "C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

function Get-OpenCodeConfigs {
    $files = @()
    if (Test-Path -LiteralPath $configDir) {
        $files += @(
            Get-ChildItem -LiteralPath $configDir -File |
                Where-Object { $_.Name -in @("opencode.jsonc", "opencode.json") }
        )
    }
    if ($env:OPENCODE_CONFIG -and (Test-Path -LiteralPath $env:OPENCODE_CONFIG -PathType Leaf)) {
        $custom = Get-Item -LiteralPath $env:OPENCODE_CONFIG
        $paths = @($files | ForEach-Object { $_.FullName })
        if ($paths -notcontains $custom.FullName) {
            $files += $custom
        }
    }
    return $files
}

function Backup-Configs {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $backups = @()
    foreach ($file in Get-OpenCodeConfigs) {
        $backup = "$($file.FullName).bak-$stamp"
        Copy-Item -LiteralPath $file.FullName -Destination $backup -Force
        $backups += [pscustomobject]@{
            Original = $file.FullName
            Backup   = $backup
        }
    }
    return $backups
}

try {
    Write-Host "vbox-mcp installer" -ForegroundColor Green
    Write-Host "Repositorio: $root"
    if ($DryRun) {
        Write-Host "Modo dry-run: no se modifica nada." -ForegroundColor Yellow
    }

    Write-Step "Comprobando Python 3.11+"
    if (Test-Path -LiteralPath $venvPython) {
        $base = @{ Exe = $venvPython; Prefix = @() }
        $version = & $venvPython -c "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))"
        $versionText = ($version | Select-Object -Last 1)
        if (-not $versionText -or [version]$versionText -lt [version]"3.11") {
            throw "El .venv existente usa Python $versionText. Borra $venv y vuelve a ejecutar el instalador."
        }
        Write-Host "    Venv existente: $venvPython (Python $versionText)"
    }
    else {
        $base = Find-BasePython
        Write-Host "    Python: $($base.Exe) $($base.Prefix -join ' ')"
        if ($DryRun) {
            Write-Host "    (dry-run: se crearia $venv)"
        }
        else {
            & $base.Exe $base.Prefix -m venv $venv
            if ($LASTEXITCODE -ne 0) {
                throw "No se pudo crear el entorno virtual en $venv"
            }
            Write-Host "    Venv creado: $venv"
        }
    }

    Invoke-Step "Actualizando pip" {
        & $venvPython -m pip install --quiet --upgrade pip
    }
    Invoke-Step "Instalando vbox-mcp en modo editable" {
        & $venvPython -m pip install --quiet -e $root
    }

    Write-Step "Comprobando VirtualBox"
    $vbox = Find-VBoxManage
    if ($vbox) {
        Write-Host "    VBoxManage: $vbox"
    }
    else {
        Write-Warning "No se encontro VBoxManage. Instala VirtualBox o define VBOX_MANAGE_PATH."
    }

    Write-Step "Registrando el servidor en OpenCode"
    $opencodeCmd = Get-Command opencode.cmd -ErrorAction SilentlyContinue
    if (-not $opencodeCmd) {
        $opencodeCmd = Get-Command opencode -ErrorAction SilentlyContinue
    }
    if (-not $opencodeCmd) {
        Write-Warning "OpenCode no esta en PATH; se omite el registro automatico."
        Write-Host "    Registra manualmente con:"
        Write-Host "    opencode mcp add vbox --global -- `"$venvPython`" -m vbox_mcp"
    }
    else {
        $opencodeExe = $opencodeCmd.Source
        if (-not $opencodeExe) {
            $opencodeExe = $opencodeCmd.Name
        }
        if ($DryRun) {
            Write-Host "    (dry-run: opencode mcp add vbox --global -- `"$venvPython`" -m vbox_mcp)"
        }
        else {
            $before = @(Get-OpenCodeConfigs | ForEach-Object { $_.FullName })
            $backups = @(Backup-Configs)
            foreach ($item in $backups) {
                Write-Host "    Backup: $($item.Backup)"
            }
            & $opencodeExe mcp add vbox --global -- $venvPython -m vbox_mcp
            if ($LASTEXITCODE -ne 0) {
                foreach ($item in $backups) {
                    Copy-Item -LiteralPath $item.Backup -Destination $item.Original -Force
                }
                foreach ($file in Get-OpenCodeConfigs) {
                    if ($before -notcontains $file.FullName) {
                        Remove-Item -LiteralPath $file.FullName -Force
                    }
                }
                throw "opencode mcp add fallo con codigo $LASTEXITCODE; se restauro la configuracion anterior."
            }
            $listing = ""
            $verifyExit = 1
            for ($attempt = 0; $attempt -lt 3; $attempt++) {
                $oldEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                try {
                    Push-Location $env:USERPROFILE
                    try {
                        $listing = (& $opencodeExe mcp list 2>&1 | Out-String)
                        $verifyExit = $LASTEXITCODE
                    }
                    finally {
                        Pop-Location
                    }
                }
                finally {
                    $ErrorActionPreference = $oldEap
                }
                if ($verifyExit -eq 0 -and $listing -match "vbox") {
                    break
                }
                if ($attempt -lt 2) {
                    Start-Sleep -Seconds 2
                }
            }
            if ($verifyExit -eq 0 -and $listing -match "vbox") {
                Write-Host "    OpenCode: vbox registrado"
            }
            else {
                Write-Warning "No se pudo confirmar 'vbox' con 'opencode mcp list'."
            }
        }
    }

    if (-not $SkipSmokeTest) {
        Write-Step "Smoke test"
        if ($vbox) {
            $smoke = @'
from vbox_mcp.config import Settings
from vbox_mcp.vboxmanage import list_vms

settings = Settings.from_env()
print(f"VMs detectadas: {len(list_vms(settings))}")
'@
            if ($DryRun) {
                Write-Host "    (dry-run: se listarian las VMs reales)"
            }
            else {
                Push-Location $root
                try {
                    $smoke | & $venvPython -
                    if ($LASTEXITCODE -ne 0) {
                        Write-Warning "El smoke test fallo; el servidor queda instalado, revisa la configuracion."
                    }
                }
                finally {
                    Pop-Location
                }
            }
        }
        else {
            Write-Host "    Omitido: VirtualBox no esta disponible." -ForegroundColor DarkGray
        }
    }

    Write-Host ""
    Write-Host "Instalacion completada." -ForegroundColor Green
    if ($DryRun) {
        Write-Host "Ejecuta sin -DryRun para aplicar los cambios."
    }
    else {
        Write-Host "Reinicia OpenCode (o abre una sesion nueva) para cargar las tools."
    }
    exit 0
}
catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
