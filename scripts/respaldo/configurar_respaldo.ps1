<#
  Compliance360 Hub - Configurar el respaldo automático (ejecutar UNA vez)

    cd "C:\Users\User\Documents\2. DESARROLLOS_GITHUB\Compliance360Hub"
    $url = "<DATABASE_PUBLIC_URL de Railway>"
    powershell -ExecutionPolicy Bypass -File scripts\respaldo\configurar_respaldo.ps1 -Url $url

  1. Toma la DATABASE_PUBLIC_URL de -Url (o, si no se pasa, del portapapeles) y la guarda cifrada
     con su usuario de Windows en %USERPROFILE%\.compliance360\db_url.cifrada.
  2. Copia respaldo_bd.ps1 a esa carpeta (así la tarea no depende de la rama de git activa).
  3. Crea la tarea programada «Compliance360 - Respaldo BD»: semanal; si el PC estaba apagado,
     corre en cuanto se encienda.
  4. Toma un primer respaldo de prueba.

  Para cambiar la dirección (p. ej. si Railway rota la clave), vuelva a ejecutarlo.
#>
param(
    [string]$Url,
    [ValidateSet("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo")]
    [string]$Dia = "Viernes",
    [string]$Hora = "17:30",
    [string]$Carpeta = "C:\Users\User\respaldo_bd",
    [int]$Conservar = 12
)

$ErrorActionPreference = "Stop"
$dias = @{ Lunes = "Monday"; Martes = "Tuesday"; Miercoles = "Wednesday"; Jueves = "Thursday";
           Viernes = "Friday"; Sabado = "Saturday"; Domingo = "Sunday" }
$config = Join-Path $env:USERPROFILE ".compliance360"
New-Item -ItemType Directory -Force -Path $config | Out-Null
New-Item -ItemType Directory -Force -Path $Carpeta | Out-Null

# La terminal de VS Code no pega bien en campos ocultos: se recibe por parámetro o del portapapeles
if (-not $Url) {
    Write-Host ""
    Write-Host "Copie la DATABASE_PUBLIC_URL en Railway (servicio Postgres > Variables) y presione Enter." -ForegroundColor Cyan
    Read-Host "Enter cuando la haya copiado" | Out-Null
    $Url = (Get-Clipboard -Raw)
    Set-Clipboard -Value " "          # no dejar la clave en el portapapeles
}
$prueba = ("" + $Url).Trim().Trim('"')
if (-not $prueba.StartsWith("postgres")) { throw "Eso no parece una dirección de PostgreSQL (debe empezar por postgresql://)." }
if ($prueba -match "railway\.internal") { throw "Esa es la dirección interna. Use DATABASE_PUBLIC_URL (termina en ...proxy.rlwy.net:puerto/railway)." }
ConvertTo-SecureString $prueba -AsPlainText -Force | ConvertFrom-SecureString | Set-Content (Join-Path $config "db_url.cifrada")
$prueba = $null
Write-Host "Dirección guardada cifrada (solo su usuario de Windows puede leerla)." -ForegroundColor Green

$script = Join-Path $config "respaldo_bd.ps1"
Copy-Item (Join-Path $PSScriptRoot "respaldo_bd.ps1") $script -Force

$argumentos = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Carpeta `"$Carpeta`" -Conservar $Conservar -Silencioso"
$accion   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argumentos
$disparo  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dias[$Dia] -At $Hora
$ajustes  = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$usuario  = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName "Compliance360 - Respaldo BD" -Action $accion -Trigger $disparo -Settings $ajustes `
    -Principal $usuario -Description "Respaldo semanal de la base de producción de Compliance360 Hub (Railway) en $Carpeta" -Force | Out-Null
Write-Host "Tarea programada creada: cada $Dia a las $Hora (si el PC está apagado, corre al encenderlo)." -ForegroundColor Green

Write-Host ""
Write-Host "Tomando un primer respaldo de prueba..." -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File $script -Carpeta $Carpeta -Conservar $Conservar
if ($LASTEXITCODE -eq 0) {
    Write-Host "Todo listo. Los respaldos quedan en $Carpeta (se conservan los últimos $Conservar)." -ForegroundColor Green
} else {
    Write-Host "El respaldo de prueba falló: revise $Carpeta\respaldo.log" -ForegroundColor Red
}
