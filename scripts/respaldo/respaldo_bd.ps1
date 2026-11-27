<#
  Compliance360 Hub - Respaldo automático de la base de producción (Railway)

  Lo ejecuta la tarea programada «Compliance360 - Respaldo BD» (ver configurar_respaldo.ps1).
  También se puede correr a mano:  powershell -ExecutionPolicy Bypass -File respaldo_bd.ps1

  - Lee la dirección de la base cifrada con su usuario de Windows (DPAPI): nadie más puede leerla.
  - Toma el respaldo con Docker (pg_dump, formato comprimido -Fc), lo verifica y conserva los últimos N.
  - Si algo falla, deja RESPALDO_FALLIDO.txt en la carpeta y muestra una ventana de aviso.
#>
param(
    [string]$Carpeta = "C:\Users\User\respaldo_bd",
    [int]$Conservar = 12,
    [switch]$Silencioso
)

$ErrorActionPreference = "Stop"
$config  = Join-Path $env:USERPROFILE ".compliance360"
$archivoUrl = Join-Path $config "db_url.cifrada"
$log     = Join-Path $Carpeta "respaldo.log"

function Escribir([string]$texto) {
    $linea = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $texto
    Add-Content -Path $log -Value $linea -Encoding UTF8
    if (-not $Silencioso) { Write-Host $linea }
}

function Avisar([string]$titulo, [string]$texto, [int]$icono) {
    try { (New-Object -ComObject WScript.Shell).Popup($texto, 0, $titulo, $icono) | Out-Null } catch { }
}

function DockerListo {
    # En Windows PowerShell 5.1, redirigir el stderr de un programa con «Stop» lanza error: aquí no
    $ErrorActionPreference = "Continue"
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

New-Item -ItemType Directory -Force -Path $Carpeta | Out-Null

try {
    if (-not (Test-Path $archivoUrl)) {
        throw "No hay dirección de base guardada. Ejecute configurar_respaldo.ps1."
    }
    $seguro = Get-Content $archivoUrl | ConvertTo-SecureString
    $url = [System.Net.NetworkCredential]::new("", $seguro).Password
    if (-not $url.StartsWith("postgres")) { throw "La dirección guardada no parece de PostgreSQL. Vuelva a configurarla." }

    # Docker Desktop: si no está abierto, se abre y se espera hasta 3 minutos
    if (-not (DockerListo)) {
        Escribir "Docker no está corriendo: abriendo Docker Desktop..."
        $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (Test-Path $exe) { Start-Process $exe }
        $limite = (Get-Date).AddMinutes(3)
        while (-not (DockerListo)) {
            if ((Get-Date) -gt $limite) { throw "Docker no respondió en 3 minutos." }
            Start-Sleep -Seconds 10
        }
    }

    $nombre = "auto_compliance360_{0}.dump" -f (Get-Date -Format "yyyyMMdd_HHmm")
    $destino = Join-Path $Carpeta $nombre
    Escribir "Iniciando respaldo -> $nombre"

    # La dirección viaja como variable de entorno del contenedor (no queda en la línea de comandos).
    # Sin comillas dobles dentro del comando: Windows PowerShell 5.1 las pasa mal a programas externos.
    $env:C360_DB = $url
    & docker run --rm -e C360_DB -v "${Carpeta}:/respaldo" postgres:latest `
        sh -c 'pg_dump $C360_DB -Fc --no-owner -f /respaldo/$0' $nombre
    $codigo = $LASTEXITCODE
    Remove-Item Env:\C360_DB -ErrorAction SilentlyContinue
    if ($codigo -ne 0) { throw "pg_dump terminó con código $codigo." }

    # Verificación: el archivo debe abrirse y traer la tabla de usuarios y la auditoría
    $contenido = & docker run --rm -v "${Carpeta}:/respaldo" postgres:latest pg_restore --list "/respaldo/$nombre"
    if ($LASTEXITCODE -ne 0) { throw "El respaldo no se puede leer (pg_restore --list falló)." }
    $texto = $contenido -join "`n"
    foreach ($tabla in @("usuarios", "log_auditoria", "organizaciones")) {
        if ($texto -notmatch "(?m)TABLE DATA public $tabla(\s|$)") { throw "El respaldo no contiene los datos de la tabla $tabla." }
    }
    $tamano = [math]::Round((Get-Item $destino).Length / 1MB, 1)
    Escribir "Respaldo OK: $nombre ($tamano MB, verificado)"

    # Rotación: solo los respaldos automáticos; los manuales no se tocan
    $viejos = Get-ChildItem $Carpeta -Filter "auto_compliance360_*.dump" | Sort-Object Name -Descending | Select-Object -Skip $Conservar
    foreach ($v in $viejos) { Remove-Item $v.FullName; Escribir "Rotación: eliminado $($v.Name)" }

    Remove-Item (Join-Path $Carpeta "RESPALDO_FALLIDO.txt") -ErrorAction SilentlyContinue
    if (-not $Silencioso) { Avisar "Compliance360 - Respaldo" "Respaldo listo: $nombre ($tamano MB)." 64 }
    exit 0
}
catch {
    $msg = $_.Exception.Message
    Escribir "ERROR: $msg"
    Set-Content -Path (Join-Path $Carpeta "RESPALDO_FALLIDO.txt") -Encoding UTF8 -Value @(
        "El respaldo automático falló el $(Get-Date -Format 'yyyy-MM-dd HH:mm').",
        "Motivo: $msg",
        "Detalle en respaldo.log. Para reintentar: Programador de tareas > «Compliance360 - Respaldo BD» > Ejecutar."
    )
    Avisar "Compliance360 - Respaldo FALLIDO" "No se pudo respaldar la base de producción.`n`nMotivo: $msg`n`nDetalle en $log" 16
    exit 1
}
