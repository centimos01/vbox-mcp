param(
    [switch]$Global
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creando entorno virtual en $venv"
    python -m venv $venv
}

Write-Host "Instalando vbox-mcp en modo editable"
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -e $root

$scope = if ($Global) { "--global" } else { "" }

Write-Host ""
Write-Host "Instalación completada."
Write-Host "Registra el servidor en OpenCode con:"
Write-Host ""
Write-Host "  opencode mcp add vbox $scope -- `"$python`" -m vbox_mcp"
Write-Host ""
Write-Host "O añade este bloque a tu opencode.json:"
Write-Host ""
@"
{
  "mcp": {
    "servers": {
      "vbox": {
        "type": "local",
        "command": ["$($python -replace '\\', '\\')", "-m", "vbox_mcp"]
      }
    }
  }
}
"@
