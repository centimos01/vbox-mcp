[CmdletBinding()]
param(
    [switch]$KeepVenv,
    [switch]$PurgeData,
    [switch]$Yes,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$configDir = if ($env:OPENCODE_CONFIG_DIR) { $env:OPENCODE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".config\opencode" }
$dataDir = Join-Path $env:LOCALAPPDATA "vbox-mcp"
$shotsDir = Join-Path $env:TEMP "vbox-mcp-shots"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
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

function Read-Utf8File {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 2 -and (($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF))) {
        throw "El archivo no esta en UTF-8."
    }
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    $offset = 0
    if ($hasBom) {
        $offset = 3
    }
    $utf8 = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false, $true
    try {
        $text = $utf8.GetString($bytes, $offset, $bytes.Length - $offset)
    }
    catch {
        throw "El archivo no contiene UTF-8 valido."
    }
    return [pscustomobject]@{
        Text   = $text
        HasBom = $hasBom
    }
}

function Skip-JsoncTrivia {
    param([string]$Text, [int]$Pos)
    while ($Pos -lt $Text.Length) {
        $ch = $Text[$Pos]
        if ([char]::IsWhiteSpace($ch)) {
            $Pos++
            continue
        }
        if ($ch -eq '/' -and ($Pos + 1) -lt $Text.Length) {
            $next = $Text[$Pos + 1]
            if ($next -eq '/') {
                $Pos += 2
                while ($Pos -lt $Text.Length -and $Text[$Pos] -ne "`n" -and $Text[$Pos] -ne "`r") {
                    $Pos++
                }
                continue
            }
            if ($next -eq '*') {
                $end = $Text.IndexOf('*/', $Pos + 2)
                if ($end -lt 0) {
                    throw "Comentario sin cerrar."
                }
                $Pos = $end + 2
                continue
            }
        }
        break
    }
    return $Pos
}

function Read-JsoncString {
    param([string]$Text, [int]$Pos)
    if ($Pos -ge $Text.Length -or $Text[$Pos] -ne '"') {
        throw "Se esperaba una cadena."
    }
    $start = $Pos
    $Pos++
    while ($Pos -lt $Text.Length) {
        $ch = $Text[$Pos]
        if ($ch -eq '\') {
            $Pos += 2
            continue
        }
        if ($ch -eq '"') {
            return [pscustomobject]@{
                Type  = 'String'
                Start = $start
                End   = $Pos + 1
                Value = $Text.Substring($start + 1, $Pos - $start - 1)
            }
        }
        $Pos++
    }
    throw "Cadena sin cerrar."
}

function Read-JsoncValue {
    param([string]$Text, [int]$Pos)
    $Pos = Skip-JsoncTrivia $Text $Pos
    if ($Pos -ge $Text.Length) {
        throw "Se esperaba un valor."
    }
    $ch = $Text[$Pos]
    if ($ch -eq '{') {
        return Read-JsoncObject $Text $Pos
    }
    if ($ch -eq '[') {
        return Read-JsoncArray $Text $Pos
    }
    if ($ch -eq '"') {
        return Read-JsoncString $Text $Pos
    }
    $start = $Pos
    while ($Pos -lt $Text.Length) {
        $ch = $Text[$Pos]
        if ($ch -eq ',' -or $ch -eq '}' -or $ch -eq ']' -or [char]::IsWhiteSpace($ch)) {
            break
        }
        if ($ch -eq '/' -and ($Pos + 1) -lt $Text.Length -and ($Text[$Pos + 1] -eq '/' -or $Text[$Pos + 1] -eq '*')) {
            break
        }
        $Pos++
    }
    if ($Pos -eq $start) {
        throw "Valor no valido."
    }
    return [pscustomobject]@{
        Type  = 'Primitive'
        Start = $start
        End   = $Pos
    }
}

function Read-JsoncObject {
    param([string]$Text, [int]$Pos)
    $start = $Pos
    $Pos++
    $members = @()
    while ($true) {
        $Pos = Skip-JsoncTrivia $Text $Pos
        if ($Pos -ge $Text.Length) {
            throw "Objeto sin cerrar."
        }
        if ($Text[$Pos] -eq '}') {
            return [pscustomobject]@{
                Type    = 'Object'
                Start   = $start
                End     = $Pos + 1
                Members = $members
            }
        }
        $key = Read-JsoncString $Text $Pos
        $Pos = Skip-JsoncTrivia $Text $key.End
        if ($Pos -ge $Text.Length -or $Text[$Pos] -ne ':') {
            throw "Se esperaba ':'."
        }
        $Pos++
        $value = Read-JsoncValue $Text $Pos
        $members += [pscustomobject]@{
            Key   = $key.Value
            Start = $key.Start
            End   = $value.End
            Value = $value
        }
        $Pos = Skip-JsoncTrivia $Text $value.End
        if ($Pos -ge $Text.Length) {
            throw "Objeto sin cerrar."
        }
        if ($Text[$Pos] -eq ',') {
            $Pos++
            continue
        }
        if ($Text[$Pos] -eq '}') {
            return [pscustomobject]@{
                Type    = 'Object'
                Start   = $start
                End     = $Pos + 1
                Members = $members
            }
        }
        throw "Se esperaba ',' o '}'."
    }
}

function Read-JsoncArray {
    param([string]$Text, [int]$Pos)
    $start = $Pos
    $Pos++
    while ($true) {
        $Pos = Skip-JsoncTrivia $Text $Pos
        if ($Pos -ge $Text.Length) {
            throw "Array sin cerrar."
        }
        if ($Text[$Pos] -eq ']') {
            return [pscustomobject]@{
                Type  = 'Array'
                Start = $start
                End   = $Pos + 1
            }
        }
        $value = Read-JsoncValue $Text $Pos
        $Pos = Skip-JsoncTrivia $Text $value.End
        if ($Pos -ge $Text.Length) {
            throw "Array sin cerrar."
        }
        if ($Text[$Pos] -eq ',') {
            $Pos++
            continue
        }
        if ($Text[$Pos] -eq ']') {
            return [pscustomobject]@{
                Type  = 'Array'
                Start = $start
                End   = $Pos + 1
            }
        }
        throw "Se esperaba ',' o ']'."
    }
}

function Read-JsoncDocument {
    param([string]$Text)
    $node = Read-JsoncValue $Text 0
    $end = Skip-JsoncTrivia $Text $node.End
    if ($end -lt $Text.Length) {
        throw "Contenido extra al final."
    }
    return $node
}

function Get-JsoncMember {
    param($Node, [string]$Name)
    if (-not $Node -or $Node.Type -ne 'Object') {
        return $null
    }
    foreach ($member in $Node.Members) {
        if ($member.Key -eq $Name) {
            return $member
        }
    }
    return $null
}

function Remove-JsoncMember {
    param([string]$Text, $ObjectNode, [string]$Name)
    $members = @($ObjectNode.Members)
    $index = -1
    for ($i = 0; $i -lt $members.Count; $i++) {
        if ($members[$i].Key -eq $Name) {
            $index = $i
            break
        }
    }
    if ($index -lt 0) {
        return $Text
    }
    $member = $members[$index]
    if ($members.Count -eq 1) {
        $start = $member.Start
        $end = $member.End
    }
    elseif ($index -lt ($members.Count - 1)) {
        $start = $member.Start
        $end = $members[$index + 1].Start
    }
    else {
        $start = $members[$index - 1].End
        $end = $member.End
    }
    return $Text.Remove($start, $end - $start)
}

function Remove-JsoncPath {
    param([string]$Text, [string[]]$Path)
    $node = Read-JsoncDocument $Text
    for ($i = 0; $i -lt ($Path.Count - 1); $i++) {
        $member = Get-JsoncMember $node $Path[$i]
        if (-not $member) {
            return $Text
        }
        $node = $member.Value
    }
    if ($node.Type -ne 'Object') {
        return $Text
    }
    return Remove-JsoncMember $Text $node $Path[$Path.Count - 1]
}

try {
    Write-Host "vbox-mcp uninstaller" -ForegroundColor Green
    Write-Host "Repositorio: $root"
    if ($DryRun) {
        Write-Host "Modo dry-run: no se modifica nada." -ForegroundColor Yellow
    }

    if (-not $Yes -and -not $DryRun) {
        $scope = if ($KeepVenv) { "el registro 'vbox' de OpenCode" } else { "el registro 'vbox' de OpenCode y el entorno .venv" }
        $answer = Read-Host "Se eliminara $scope. Continuar? (s/N)"
        if (-not $answer -or $answer.Trim() -notmatch "^(s|si|y|yes)$") {
            Write-Host "Cancelado."
            exit 0
        }
    }

    Write-Step "Eliminando el registro de OpenCode"
    $configFiles = @(Get-OpenCodeConfigs)
    if ($configFiles.Count -eq 0) {
        Write-Host "    No hay configuracion de OpenCode en $configDir"
    }

    $edits = @()
    foreach ($file in $configFiles) {
        $fileData = Read-Utf8File $file.FullName
        try {
            $newText = Remove-JsoncPath $fileData.Text @("mcp", "servers", "vbox")
            $newText = Remove-JsoncPath $newText @("mcp", "vbox")
            if ($newText -ne $fileData.Text) {
                $null = Read-JsoncDocument $newText
            }
        }
        catch {
            throw "No se pudo editar $($file.FullName): $($_.Exception.Message). No se modifico nada."
        }
        if ($newText -eq $fileData.Text) {
            Write-Host "    vbox no estaba registrado en $($file.Name)"
            continue
        }
        $edits += [pscustomobject]@{
            File   = $file
            Text   = $newText
            HasBom = $fileData.HasBom
        }
    }

    foreach ($edit in $edits) {
        if ($DryRun) {
            Write-Host "    (dry-run: se quitaria vbox de $($edit.File.FullName))"
            continue
        }
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss-fffffff"
        $backup = "$($edit.File.FullName).bak-$stamp"
        Copy-Item -LiteralPath $edit.File.FullName -Destination $backup -Force
        Write-Host "    Backup: $backup"

        $encoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $edit.HasBom
        $temp = "$($edit.File.FullName).tmp-$stamp"
        [System.IO.File]::WriteAllText($temp, $edit.Text, $encoding)
        Move-Item -LiteralPath $temp -Destination $edit.File.FullName -Force
        Write-Host "    vbox eliminado de $($edit.File.Name)"
    }
    if ($edits.Count -eq 0) {
        Write-Warning "No se encontro el registro 'vbox' en la configuracion de OpenCode."
    }

    Write-Step "Eliminando el entorno virtual"
    if (Test-Path -LiteralPath $venv) {
        if ($KeepVenv) {
            Write-Host "    Conservando $venv (-KeepVenv)"
        }
        elseif ($DryRun) {
            Write-Host "    (dry-run: se borraria $venv)"
        }
        else {
            if (-not (Test-Path -LiteralPath (Join-Path $venv "pyvenv.cfg")) -or -not (Test-Path -LiteralPath (Join-Path $venv "Scripts\python.exe"))) {
                throw "No se borra ${venv}: no parece el entorno virtual creado por el instalador."
            }
            Remove-Item -LiteralPath $venv -Recurse -Force
            Write-Host "    Borrado: $venv"
        }
    }
    else {
        Write-Host "    No existe $venv"
    }

    if ($PurgeData) {
        Write-Step "Eliminando datos locales"
        foreach ($path in @($dataDir, $shotsDir)) {
            if (-not (Test-Path -LiteralPath $path)) {
                Write-Host "    No existe $path"
            }
            elseif ($DryRun) {
                Write-Host "    (dry-run: se borraria $path)"
            }
            else {
                Remove-Item -LiteralPath $path -Recurse -Force
                Write-Host "    Borrado: $path"
            }
        }
    }

    Write-Host ""
    Write-Host "Desinstalacion completada." -ForegroundColor Green
    if ($DryRun) {
        Write-Host "Ejecuta sin -DryRun para aplicar los cambios."
    }
    else {
        Write-Host "El repositorio, VirtualBox y tus VMs no se han tocado."
        Write-Host "Reinicia OpenCode para que desaparezca la tool vbox."
    }
    exit 0
}
catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
