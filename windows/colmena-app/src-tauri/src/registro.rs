use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock, TryLockError};
use std::time::{SystemTime, UNIX_EPOCH};

use colmena_nucleo::registro::{
    archivos_viejos, linea, nombre_archivo, Fecha, Nivel, Origen, DIAS_GUARDADO,
};
use colmena_nucleo::registro_cola::{
    Cola, Limitador, COLA_MAX, LOTE_BYTES, LOTE_LINEAS, NOTCH_POR_MINUTO,
};
use colmena_nucleo::registro_eventos::{
    bytes_lineas_disponibles, evento as armar_evento, token, ColaEventos, EventoApp, COLA_EVENTOS_MAX,
};
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};

use crate::{escribir_config_archivo, exige_notch, Estado};

const ARCHIVO_PENDIENTES: &str = "pendientes.txt";
const EVENTO_HAY: &str = "registro-hay";
/// El back corta en 200 ítems por POST: eventos y líneas comparten ese tope.
const LOTE_EVENTOS: usize = 50;

/// Lote que ve el notch: junta una parte de líneas y una de eventos bajo un solo id.
#[derive(Serialize)]
pub struct LoteCombinado {
    lote: u64,
    lineas: Vec<String>,
    eventos: Vec<EventoApp>,
}

struct Registro {
    carpeta: PathBuf,
    app: AppHandle,
    cola: Mutex<Cola>,
    limitador: Mutex<Limitador>,
    eventos: Mutex<ColaEventos>,
    siguiente_lote: AtomicU64,
    /// (id combinado, id de la `Cola`, id de la `ColaEventos`)
    en_vuelo: Mutex<Option<(u64, Option<u64>, Option<u64>)>>,
}

static REGISTRO: OnceLock<Registro> = OnceLock::new();

fn ahora_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[cfg(windows)]
fn ahora() -> Fecha {
    use windows::Win32::System::SystemInformation::GetLocalTime;
    let t = unsafe { GetLocalTime() };
    Fecha {
        anio: i32::from(t.wYear),
        mes: t.wMonth as u8,
        dia: t.wDay as u8,
        hora: t.wHour as u8,
        min: t.wMinute as u8,
        seg: t.wSecond as u8,
        ms: t.wMilliseconds,
    }
}

#[cfg(not(windows))]
fn ahora() -> Fecha {
    Fecha::desde_unix_ms(ahora_ms())
}

fn guardar_pendientes(r: &Registro, cola: &Cola) {
    let _ = escribir_config_archivo(&r.carpeta.join(ARCHIVO_PENDIENTES), &cola.texto());
}

fn agregar_al_archivo(r: &Registro, fecha: &Fecha, texto: &str) {
    use std::io::Write;
    let ruta = r.carpeta.join(nombre_archivo(fecha));
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(ruta) {
        let _ = writeln!(f, "{texto}");
    }
}

/// En el caso normal toma el lock; durante un pánico usa `try_lock` y, si no puede, pierde
/// la línea, porque el hook puede dispararse con el lock ya tomado por este mismo hilo.
pub fn anotar(nivel: Nivel, origen: Origen, mensaje: &str) {
    let Some(r) = REGISTRO.get() else {
        return;
    };
    let fecha = ahora();
    let texto = linea(&fecha, nivel, origen, mensaje);
    let en_panico = std::thread::panicking();
    {
        let mut cola = if en_panico {
            match r.cola.try_lock() {
                Ok(c) => c,
                Err(TryLockError::Poisoned(p)) => p.into_inner(),
                Err(TryLockError::WouldBlock) => return,
            }
        } else {
            r.cola.lock().unwrap_or_else(|e| e.into_inner())
        };
        agregar_al_archivo(r, &fecha, &texto);
        cola.anotar(texto);
        guardar_pendientes(r, &cola);
    }
    // emit_to toma un lock bloqueante de Tauri: no se hace durante un pánico.
    if nivel == Nivel::Error && !en_panico {
        let _ = r.app.emit_to("notch", EVENTO_HAY, ());
    }
}

fn ts_evento() -> String {
    ahora().iso().chars().take(19).collect()
}

fn encolar(e: EventoApp) {
    let Some(r) = REGISTRO.get() else {
        return;
    };
    let mut cola = if std::thread::panicking() {
        match r.eventos.try_lock() {
            Ok(c) => c,
            Err(TryLockError::Poisoned(p)) => p.into_inner(),
            Err(TryLockError::WouldBlock) => return,
        }
    } else {
        r.eventos.lock().unwrap_or_else(|e| e.into_inner())
    };
    cola.anotar(e);
}

/// Solo tokens: `evento` y `codigo` pasan por `registro_eventos::token`, nunca texto libre.
pub fn anotar_evento(origen: &str, evento: &'static str, ok: bool, codigo: Option<&str>, ms: Option<u64>) {
    encolar(armar_evento(ts_evento(), origen, evento, ok, codigo, ms, None));
}

pub fn anotar_arranque() {
    let version = env!("CARGO_PKG_VERSION");
    encolar(armar_evento(ts_evento(), "app", "arranque", true, None, None, Some(version)));
}

pub fn carpeta() -> Option<PathBuf> {
    REGISTRO.get().map(|r| r.carpeta.clone())
}

pub fn iniciar(app: &AppHandle) -> Result<PathBuf, String> {
    let carpeta = app.path().app_log_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&carpeta).map_err(|e| e.to_string())?;

    let nombres: Vec<String> = std::fs::read_dir(&carpeta)
        .map(|d| {
            d.flatten()
                .filter_map(|e| e.file_name().into_string().ok())
                .collect()
        })
        .unwrap_or_default();
    for viejo in archivos_viejos(&nombres, &ahora(), DIAS_GUARDADO) {
        let _ = std::fs::remove_file(carpeta.join(viejo));
    }

    let texto = std::fs::read_to_string(carpeta.join(ARCHIVO_PENDIENTES)).unwrap_or_default();
    let registro = Registro {
        carpeta: carpeta.clone(),
        app: app.clone(),
        cola: Mutex::new(Cola::desde_texto(&texto, COLA_MAX)),
        limitador: Mutex::new(Limitador::new(NOTCH_POR_MINUTO, 60_000)),
        eventos: Mutex::new(ColaEventos::new(COLA_EVENTOS_MAX)),
        siguiente_lote: AtomicU64::new(0),
        en_vuelo: Mutex::new(None),
    };
    REGISTRO
        .set(registro)
        .map_err(|_| "registro ya iniciado".to_string())?;

    let anterior = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let mensaje = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| (*s).to_string())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_default();
        let donde = info
            .location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_default();
        anotar(Nivel::Error, Origen::App, &format!("pánico: {mensaje} en {donde}"));
        anterior(info);
    }));
    Ok(carpeta)
}

#[tauri::command]
pub fn registro_pendiente(
    window: WebviewWindow,
    estado: State<'_, Estado>,
) -> Result<Option<LoteCombinado>, String> {
    exige_notch(&window, &estado)?;
    let Some(r) = REGISTRO.get() else {
        return Ok(None);
    };
    let mut en_vuelo = r.en_vuelo.lock().unwrap_or_else(|e| e.into_inner());
    let pendientes = r
        .eventos
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .pendiente(LOTE_EVENTOS);
    let (id_eventos, eventos) = match pendientes {
        Some((id, e)) => (Some(id), e),
        None => (None, Vec::new()),
    };
    let lote_lineas = {
        let mut cola = r.cola.lock().unwrap_or_else(|e| e.into_inner());
        let descartadas = cola.descartadas();
        let encabezado = (descartadas > 0).then(|| {
            linea(
                &ahora(),
                Nivel::Aviso,
                Origen::App,
                &format!("se descartaron {descartadas} líneas pendientes"),
            )
        });
        cola.pendiente(
            encabezado,
            LOTE_LINEAS.saturating_sub(eventos.len()),
            bytes_lineas_disponibles(&eventos, LOTE_BYTES),
        )
    };
    if lote_lineas.is_none() && eventos.is_empty() {
        *en_vuelo = None;
        return Ok(None);
    }
    let lote = r.siguiente_lote.fetch_add(1, Ordering::SeqCst) + 1;
    let (id_lineas, lineas) = match lote_lineas {
        Some(l) => (Some(l.lote), l.lineas),
        None => (None, Vec::new()),
    };
    *en_vuelo = Some((lote, id_lineas, id_eventos));
    Ok(Some(LoteCombinado { lote, lineas, eventos }))
}

#[tauri::command]
pub fn registro_enviado(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    lote: u64,
) -> Result<(), String> {
    exige_notch(&window, &estado)?;
    let Some(r) = REGISTRO.get() else {
        return Ok(());
    };
    let mut en_vuelo = r.en_vuelo.lock().unwrap_or_else(|e| e.into_inner());
    let Some((id, id_lineas, id_eventos)) = *en_vuelo else {
        return Ok(());
    };
    if id != lote {
        return Ok(());
    }
    *en_vuelo = None;
    if let Some(l) = id_lineas {
        let mut cola = r.cola.lock().unwrap_or_else(|e| e.into_inner());
        if cola.enviado(l) {
            guardar_pendientes(r, &cola);
        }
    }
    if let Some(e) = id_eventos {
        r.eventos
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .enviado(e);
    }
    Ok(())
}

#[tauri::command]
pub fn registro_anotar(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    nivel: String,
    mensaje: String,
) -> Result<(), String> {
    exige_notch(&window, &estado)?;
    let nivel = Nivel::desde(&nivel).ok_or_else(|| "nivel inválido".to_string())?;
    let Some(r) = REGISTRO.get() else {
        return Ok(());
    };
    let (permitido, descartadas) = {
        let mut limitador = r.limitador.lock().unwrap_or_else(|e| e.into_inner());
        let permitido = limitador.permitir(ahora_ms());
        (permitido, if permitido { limitador.tomar_descartadas() } else { 0 })
    };
    if !permitido {
        return Ok(());
    }
    if descartadas > 0 {
        anotar(
            Nivel::Aviso,
            Origen::Notch,
            &format!("se descartaron {descartadas} mensajes del notch"),
        );
    }
    anotar(nivel, Origen::Notch, &mensaje);
    Ok(())
}

/// El origen siempre es "notch": no se confía en el que manda la ventana.
#[tauri::command]
pub fn registro_evento(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    origen: String,
    evento: String,
    ok: bool,
    codigo: Option<String>,
) -> Result<(), String> {
    exige_notch(&window, &estado)?;
    let _ = origen;
    let Some(r) = REGISTRO.get() else {
        return Ok(());
    };
    let permitido = r
        .limitador
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .permitir(ahora_ms());
    if !permitido {
        return Ok(());
    }
    let evento = token(&evento);
    let codigo = codigo.map(|c| token(&c));
    encolar(armar_evento(ts_evento(), "notch", &evento, ok, codigo.as_deref(), None, None));
    Ok(())
}
