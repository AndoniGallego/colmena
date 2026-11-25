<#
.SYNOPSIS
  Atajo de la PC para cada entrega de Colmena: compilar e instalar la app de Windows, o subir el ZIP al repo publico.

.DESCRIPTION
  colmena.ps1 instalar   Baja el ultimo ZIP de la notebook, lo descomprime en la carpeta de build, compila la
                         app (Tauri), cierra la que este abierta, instala en silencio y la abre.
  colmena.ps1 publicar   Baja el ultimo ZIP y su mensaje, deja el repo publico igual al ZIP y hace commit y push.

  La configuracion vive en $env:USERPROFILE\.colmena-pc.json (fuera del repo): notebook (usuario@direccion),
  carpetaBuild, repoPublico y carpetaEntregas (en la notebook). Si falta, la primera vez se pregunta y se guarda.
  El ZIP lo arma scripts/entregar.sh en la notebook. Requiere PowerShell 5.1 o superior, ssh, scp, git, node y cargo.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('instalar', 'publicar')]
    [string]$Accion
)

$ErrorActionPreference = 'Stop'

function Mostrar-Uso {
    Write-Host 'Uso: colmena.ps1 instalar | publicar'
    Write-Host '  instalar   baja el ultimo ZIP, compila e instala la app de Windows'
    Write-Host '  publicar   baja el ultimo ZIP y lo sube al repo publico de GitHub'
}

# Corre un programa nativo y corta si devuelve distinto de 0. Con 'Stop', el texto que git, npm o scp mandan
# por stderr (progreso) se tomaria como error, por eso adentro se usa 'Continue' y se mira $LASTEXITCODE.
function Ejecutar {
    param([Parameter(Mandatory = $true)][string]$Programa, [string[]]$Argumentos = @())
    $previo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Programa @Argumentos
        $codigo = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previo
    }
    if ($codigo -ne 0) {
        throw "Fallo '$Programa $($Argumentos -join ' ')' (codigo $codigo)."
    }
}

# Igual que Ejecutar pero devuelve la salida (una cadena por linea).
function Capturar {
    param([Parameter(Mandatory = $true)][string]$Programa, [string[]]$Argumentos = @())
    $previo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $salida = & $Programa @Argumentos
        $codigo = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previo
    }
    if ($codigo -ne 0) {
        throw "Fallo '$Programa $($Argumentos -join ' ')' (codigo $codigo)."
    }
    return $salida
}

function Cargar-Config {
    $ruta = Join-Path $env:USERPROFILE '.colmena-pc.json'
    $config = @{}
    if (Test-Path -LiteralPath $ruta) {
        $json = Get-Content -LiteralPath $ruta -Raw | ConvertFrom-Json
        foreach ($p in $json.PSObject.Properties) { $config[$p.Name] = $p.Value }
    }

    $porDefecto = [ordered]@{
        carpetaBuild    = 'C:\dev\colmena'
        repoPublico     = (Join-Path $env:USERPROFILE 'colmena-publico')
        carpetaEntregas = '~/Desktop'
    }
    $cambio = $false

    if (-not $config['notebook']) {
        $valor = Read-Host 'Notebook (usuario@direccion, para ssh)'
        if (-not $valor) { throw 'Falta la notebook (usuario@direccion).' }
        $config['notebook'] = $valor.Trim()
        $cambio = $true
    }
    foreach ($clave in $porDefecto.Keys) {
        if (-not $config[$clave]) {
            $valor = Read-Host "$clave [$($porDefecto[$clave])]"
            if (-not $valor) { $valor = $porDefecto[$clave] }
            $config[$clave] = $valor.Trim()
            $cambio = $true
        }
    }

    if ($cambio) {
        $texto = [pscustomobject]$config | ConvertTo-Json
        [IO.File]::WriteAllText($ruta, $texto, (New-Object Text.UTF8Encoding $false))
        Write-Host "Configuracion guardada en $ruta"
    }
    return $config
}

# Busca el ultimo ZIP en la notebook y lo baja a $env:TEMP. Devuelve la ruta remota y la local.
function Bajar-Zip {
    param($Config, [switch]$ConMensaje)
    $remoto = Capturar 'ssh' @($Config.notebook, "ls -t $($Config.carpetaEntregas)/colmena-*.zip | head -1")
    $remoto = ("$remoto").Trim()
    if (-not $remoto) { throw "No hay ningun colmena-*.zip en $($Config.carpetaEntregas) de la notebook. Corre scripts/entregar.sh alla." }
    Write-Host "Ultimo ZIP: $remoto"

    $remotos = @($remoto)
    if ($ConMensaje) { $remotos += ($remoto -replace '\.zip$', '.mensaje.txt') }

    Push-Location $env:TEMP
    try {
        foreach ($r in $remotos) {
            Ejecutar 'scp' @("$($Config.notebook):$r", '.')
        }
    }
    finally {
        Pop-Location
    }

    $nombre = Split-Path -Leaf $remoto
    $zip = Join-Path $env:TEMP $nombre
    $mensaje = $null
    if ($ConMensaje) {
        $mensaje = Join-Path $env:TEMP ($nombre -replace '\.zip$', '.mensaje.txt')
        if (-not (Test-Path -LiteralPath $mensaje)) { throw "No se bajo el mensaje: $mensaje" }
    }
    if (-not (Test-Path -LiteralPath $zip)) { throw "No se bajo el ZIP: $zip" }
    return [pscustomobject]@{ Zip = $zip; Mensaje = $mensaje; Nombre = $nombre }
}

function Instalar {
    param($Config)
    $entrega = Bajar-Zip -Config $Config

    New-Item -ItemType Directory -Force -Path $Config.carpetaBuild | Out-Null
    Write-Host "Descomprimiendo en $($Config.carpetaBuild)"
    Expand-Archive -LiteralPath $entrega.Zip -DestinationPath $Config.carpetaBuild -Force

    $app = Join-Path $Config.carpetaBuild 'windows\colmena-app'
    Push-Location $app
    try {
        Ejecutar 'npm' @('install')
        Ejecutar 'npm' @('run', 'tauri', 'icon', '..\..\frontend\public\icons\icon-512.png')
        Ejecutar 'npm' @('run', 'build')
    }
    finally {
        Pop-Location
    }

    $nsis = Join-Path $app 'src-tauri\target\release\bundle\nsis'
    $instalador = Get-ChildItem -LiteralPath $nsis -Filter 'Colmena_*_x64-setup.exe' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $instalador) { throw "No encontre el instalador en $nsis" }

    # productName de tauri.conf.json: Colmena
    $abiertos = @(Get-Process -Name 'Colmena' -ErrorAction SilentlyContinue)
    if ($abiertos.Count -gt 0) {
        Write-Host 'Cerrando Colmena...'
        $abiertos | Stop-Process -Force
        $abiertos | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
    }

    Write-Host "Instalando $($instalador.Name)..."
    $proceso = Start-Process -FilePath $instalador.FullName -ArgumentList '/S' -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { throw "El instalador termino con codigo $($proceso.ExitCode)." }

    $candidatos = @(
        (Join-Path $env:LOCALAPPDATA 'Colmena\Colmena.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Colmena\Colmena.exe'),
        (Join-Path $env:ProgramFiles 'Colmena\Colmena.exe')
    )
    $exe = $candidatos | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($exe) {
        Write-Host "Abriendo $exe"
        Start-Process -FilePath $exe
    }
    else {
        Write-Warning 'Instalada, pero no encontre Colmena.exe para abrirla: abrila desde el menu Inicio.'
    }
    Remove-Item -LiteralPath $entrega.Zip -Force -ErrorAction SilentlyContinue
    Write-Host 'Listo.'
}

function Publicar {
    param($Config)
    $repo = $Config.repoPublico
    if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
        throw "$repo no es un repo git (falta .git). Clona el repo publico ahi primero."
    }
    $entrega = Bajar-Zip -Config $Config -ConMensaje

    Write-Host "Dejando $repo igual al ZIP"
    Get-ChildItem -LiteralPath $repo -Force | Where-Object { $_.Name -ne '.git' } | Remove-Item -Recurse -Force
    Expand-Archive -LiteralPath $entrega.Zip -DestinationPath $repo -Force

    Push-Location $repo
    try {
        Ejecutar 'git' @('add', '-A')
        $cambios = Capturar 'git' @('status', '--porcelain')
        if (-not $cambios) {
            Write-Host 'No hay cambios respecto de lo publicado: no se commitea.'
            return
        }

        $texto = [IO.File]::ReadAllText($entrega.Mensaje, [Text.Encoding]::UTF8)
        $archivoMensaje = Join-Path $env:TEMP 'colmena-commit-mensaje.txt'
        [IO.File]::WriteAllText($archivoMensaje, $texto, (New-Object Text.UTF8Encoding $false))

        Ejecutar 'git' @('commit', '-F', $archivoMensaje)
        Ejecutar 'git' @('push')
        Remove-Item -LiteralPath $archivoMensaje -Force -ErrorAction SilentlyContinue
        Write-Host 'Publicado.'
    }
    finally {
        Pop-Location
    }
    Remove-Item -LiteralPath $entrega.Zip, $entrega.Mensaje -Force -ErrorAction SilentlyContinue
}

try {
    if (-not $Accion) { Mostrar-Uso; return }
    $config = Cargar-Config
    switch ($Accion) {
        'instalar' { Instalar -Config $config }
        'publicar' { Publicar -Config $config }
    }
}
catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
