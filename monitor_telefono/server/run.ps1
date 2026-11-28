param(
    [switch]$CreateAdmin
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"

if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $root ".env.example") -Destination $envFile
    throw "Se creó monitor_telefono\.env. Configura SECRET_KEY y DATA_ENCRYPTION_KEY y vuelve a ejecutar."
}

Get-Content -LiteralPath $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if ($name) {
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

if (-not $env:SECRET_KEY -or $env:SECRET_KEY.Length -lt 32) {
    throw "SECRET_KEY debe contener al menos 32 caracteres aleatorios."
}
if (-not $env:DATA_ENCRYPTION_KEY) {
    throw "DATA_ENCRYPTION_KEY no está configurada en monitor_telefono\.env."
}
if (-not $env:PUERTO) { $env:PUERTO = "8100" }

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3 -m venv (Join-Path $PSScriptRoot ".venv")
}
& $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias." }

$env:PYTHONPATH = $PSScriptRoot
Push-Location $PSScriptRoot
try {
    if ($CreateAdmin) {
        & $venvPython -m app.cli create-admin
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la cuenta administradora." }
        exit 0
    }
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port $env:PUERTO --proxy-headers --forwarded-allow-ips=127.0.0.1
    if ($LASTEXITCODE -ne 0) { throw "Uvicorn terminó con un error." }
}
finally {
    Pop-Location
}
