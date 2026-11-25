use std::path::PathBuf;
use std::time::{Duration, Instant};

use colmena_nucleo::entornos::{
    Apertura, EstadoEntornos, EstadoTunel, FaseTunel, argv_ssh, conflicto_con_tuneles,
    decidir_apertura, mensaje_ocupados, puertos_ocupados, esperar_puerto, ruta_ssh, url_principal,
    validar_nombre, validar_pedido,
};
use colmena_nucleo::config::{escribir_config, Destino};
use colmena_nucleo::registro::{Nivel, Origen};
use colmena_nucleo::validar::{es_url_local, url_entornos};
use colmena_nucleo::validar::validar_destino;
use tauri::{AppHandle, State, WebviewWindow};
use tauri_plugin_opener::OpenerExt;

use crate::tuneles::Tuneles;
use crate::ventanas;
use crate::{exige_ventana, leer_config_archivo, registro, Estado};

fn exige_colmena(window: &WebviewWindow, estado: &Estado) -> Result<String, String> {
    exige_ventana(window, estado, "colmena")
}

fn exige_notebook(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "notebook" {
        return Err("no permitido".into());
    }
    let url = window.url().map_err(|_| "no permitido".to_string())?;
    if !es_url_local(url.as_str()) {
        return Err("no permitido".into());
    }
    Ok(())
}

/// Anota el motivo de un error de `entorno_abrir` y lo devuelve igual.
fn fallo_abrir(motivo: String) -> String {
    registro::anotar(Nivel::Aviso, Origen::Tuneles, &format!("entorno_abrir: {motivo}"));
    motivo
}

fn ms_desde(inicio: Instant) -> u64 {
    inicio.elapsed().as_millis() as u64
}

const SIN_NOTEBOOK: &str = "Configurá la notebook primero: tocá \"cambiar\" arriba y guardá su dirección.";

#[tauri::command]
pub async fn entorno_abrir(
    app: AppHandle,
    window: WebviewWindow,
    estado: State<'_, Estado>,
    nombre: String,
    puertos: Vec<u16>,
    principal: u16,
) -> Result<EstadoTunel, String> {
    let origen = exige_colmena(&window, &estado)?;
    let ruta_config = estado.ruta_config.clone();
    let tuneles = estado.tuneles.clone();
    let ordenados = validar_pedido(&nombre, &puertos, principal, Some(origen.as_str()))
        .map_err(fallo_abrir)?;

    match decidir_apertura(tuneles.abiertos(&nombre).as_deref(), &ordenados) {
        Apertura::SoloNavegador => {
            app
                .opener()
                .open_url(url_principal(principal), None::<&str>)
                .map_err(|e| fallo_abrir(e.to_string()))?;
            return Ok(EstadoTunel {
                estado: FaseTunel::Abierto,
                puertos: ordenados.clone(),
                error: None,
            });
        }
        Apertura::Reabrir => tuneles.cerrar(&nombre),
        Apertura::Abrir => {}
    }

    let destino = leer_config_archivo(&ruta_config)
        .destino()
        .ok_or_else(|| fallo_abrir(SIN_NOTEBOOK.to_string()))?;

    let otros = tuneles.otros(&nombre);
    if let Some(msg) = conflicto_con_tuneles(&nombre, &ordenados, &otros) {
        return Err(fallo_abrir(msg));
    }
    let ocupados = puertos_ocupados(&ordenados);
    if !ocupados.is_empty() {
        return Err(fallo_abrir(mensaje_ocupados(&ocupados)));
    }

    let system_root = std::env::var("SystemRoot").unwrap_or_else(|_| "C:\\Windows".into());
    let ruta_ssh_exe = PathBuf::from(ruta_ssh(&system_root));
    if !ruta_ssh_exe.exists() {
        return Err(fallo_abrir("falta el cliente SSH de Windows".into()));
    }

    let argv = argv_ssh(&destino, &ordenados);
    let generacion = tuneles
        .lanzar(&nombre, ordenados.clone(), &ruta_ssh_exe, &argv)
        .map_err(fallo_abrir)?;

    let inicio = Instant::now();
    let tuneles_cl = tuneles.clone();
    let nombre_cl = nombre.clone();
    let espera = tauri::async_runtime::spawn_blocking(move || {
        esperar_puerto(
            principal,
            Duration::from_secs(10),
            Duration::from_millis(250),
            || tuneles_cl.terminado(&nombre_cl),
        )
    })
    .await
    .map_err(|e| fallo_abrir(e.to_string()))?;

    if let Err(e) = espera {
        tuneles.cerrar_si(&nombre, generacion);
        registro::anotar(Nivel::Error, Origen::Tuneles, &format!("túnel {nombre} falló: {e}"));
        registro::anotar_evento("tuneles", "tunel_fallo", false, Some("sin_puerto"), Some(ms_desde(inicio)));
        return Err(e);
    }
    let abierto = format!("túnel {nombre} abierto en {principal}");
    registro::anotar(Nivel::Info, Origen::Tuneles, &abierto);
    registro::anotar_evento("tuneles", "tunel_abierto", true, None, Some(ms_desde(inicio)));

    app
        .opener()
        .open_url(url_principal(principal), None::<&str>)
        .map_err(|e| fallo_abrir(e.to_string()))?;

    Ok(EstadoTunel {
        estado: FaseTunel::Abierto,
        puertos: ordenados,
        error: None,
    })
}

#[tauri::command]
pub fn entorno_cerrar(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    nombre: String,
) -> Result<(), String> {
    exige_colmena(&window, &estado)?;
    if !validar_nombre(&nombre) {
        registro::anotar(Nivel::Aviso, Origen::Tuneles, "entorno_cerrar: nombre inválido");
        return Err("nombre inválido".into());
    }
    estado.tuneles.cerrar(&nombre);
    Ok(())
}

#[tauri::command]
pub fn entornos_estado(
    window: WebviewWindow,
    estado: State<'_, Estado>,
) -> Result<EstadoEntornos, String> {
    exige_colmena(&window, &estado)?;
    let cfg = leer_config_archivo(&estado.ruta_config);
    Ok(EstadoEntornos {
        notebook: cfg.destino().map(|d| d.ssh()).unwrap_or_default(),
        tuneles: estado.tuneles.estado(),
    })
}

#[tauri::command]
pub async fn abrir_ajuste_notebook(
    app: AppHandle,
    window: WebviewWindow,
    estado: State<'_, Estado>,
) -> Result<(), String> {
    exige_colmena(&window, &estado)?;
    ventanas::crear_notebook(&app).map(|_| ())
}

#[tauri::command]
pub fn leer_notebook(
    window: WebviewWindow,
    estado: State<'_, Estado>,
) -> Result<Option<Destino>, String> {
    exige_notebook(&window)?;
    Ok(leer_config_archivo(&estado.ruta_config).destino())
}

#[tauri::command]
pub fn guardar_notebook(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    host: String,
    usuario: String,
) -> Result<(), String> {
    exige_notebook(&window)?;
    let destino = validar_destino(&host, &usuario)?;
    let mut cfg = leer_config_archivo(&estado.ruta_config);
    cfg.notebook = Some(destino);
    crate::escribir_config_archivo(&estado.ruta_config, &escribir_config(&cfg)).map_err(|e| e.to_string())?;
    if window.close().is_err() {
        let _ = window.destroy();
    }
    Ok(())
}

pub fn abrir_entornos_desde_bandeja(app: &AppHandle, origen: &str) -> Result<(), String> {
    ventanas::abrir_colmena_url(app, &url_entornos(origen))
}
