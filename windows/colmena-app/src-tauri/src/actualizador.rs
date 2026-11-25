//! Ítem "Buscar actualización" de la bandeja: chequea la ficha de la notebook, baja, verifica la firma e instala.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use colmena_nucleo::actualizacion::{
    al_tocar, endpoint_actualizacion, item_habilitado, texto_item, tras_buscar, url_instalador, EstadoItem, Paso,
};
use colmena_nucleo::registro::{Nivel, Origen};
use tauri::menu::MenuItem;
use tauri::{AppHandle, Manager, Wry};
use tauri_plugin_updater::{Error, Update, UpdaterExt};
use url::Url;

use crate::registro;
use crate::Estado;

pub const ID_ITEM: &str = "actualizacion";
const AL_DIA_SEGUNDOS: u64 = 4;
const TIEMPO_PEDIDO: Duration = Duration::from_secs(60);
const TIEMPO_DESCARGA: Duration = Duration::from_secs(600);

#[derive(Default)]
pub struct Actualizador {
    estado: Mutex<Option<EstadoItem>>,
    item: Mutex<Option<MenuItem<Wry>>>,
    pendiente: Mutex<Option<Update>>,
    /// Sube en cada cambio: el regreso de "Ya está al día" solo aplica si nadie tocó nada en el medio.
    generacion: AtomicU64,
}

impl Actualizador {
    fn actual(&self) -> EstadoItem {
        self.estado.lock().unwrap().clone().unwrap_or(EstadoItem::Inicial)
    }
}

pub fn crear_item(app: &AppHandle) -> tauri::Result<MenuItem<Wry>> {
    let inicial = EstadoItem::Inicial;
    let item = MenuItem::with_id(app, ID_ITEM, texto_item(&inicial), item_habilitado(&inicial), None::<&str>)?;
    *app.state::<Actualizador>().item.lock().unwrap() = Some(item.clone());
    Ok(item)
}

fn poner(app: &AppHandle, nuevo: EstadoItem) -> u64 {
    let act = app.state::<Actualizador>();
    let gen = act.generacion.fetch_add(1, Ordering::SeqCst) + 1;
    if let Some(item) = act.item.lock().unwrap().as_ref() {
        let _ = item.set_text(texto_item(&nuevo));
        let _ = item.set_enabled(item_habilitado(&nuevo));
    }
    *act.estado.lock().unwrap() = Some(nuevo);
    gen
}

/// Pasa a `nuevo` solo si el estado actual es `desde` (evita pisar un chequeo o una instalación en curso).
fn pasar(app: &AppHandle, desde: &[EstadoItem], nuevo: EstadoItem) -> bool {
    let act = app.state::<Actualizador>();
    {
        let mut e = act.estado.lock().unwrap();
        let actual = e.clone().unwrap_or(EstadoItem::Inicial);
        if !desde.iter().any(|d| std::mem::discriminant(d) == std::mem::discriminant(&actual)) {
            return false;
        }
        *e = Some(nuevo.clone());
    }
    poner(app, nuevo);
    true
}

fn causa(e: &Error) -> &'static str {
    match e {
        Error::Reqwest(_) | Error::Network(_) | Error::Http(_) => "sin conexión con la notebook",
        Error::Minisign(_) | Error::Base64(_) | Error::SignatureUtf8(_) | Error::SignedVersionMismatch { .. }
        | Error::MissingSignedVersion => "la firma no verifica",
        Error::Serialization(_) | Error::Semver(_) | Error::TargetNotFound(_) | Error::TargetsNotFound(_)
        | Error::ReleaseNotFound => "la ficha de la notebook no se entiende",
        Error::Io(_) | Error::Extract(_) | Error::TempDirNotFound | Error::BinaryNotFoundInArchive => {
            "no pude preparar el instalador"
        }
        _ => "error del actualizador",
    }
}

fn origen(app: &AppHandle) -> Option<String> {
    app.state::<Estado>().origen.lock().unwrap().clone()
}

async fn chequear(app: &AppHandle) -> Result<Option<Update>, &'static str> {
    let origen = origen(app).ok_or("todavía no hay dirección de la notebook")?;
    let endpoint = Url::parse(&endpoint_actualizacion(&origen)).map_err(|_| "dirección inválida")?;
    let descarga = Url::parse(&url_instalador(&origen)).map_err(|_| "dirección inválida")?;
    // En Windows el plugin cierra el proceso sin pasar por RunEvent::Exit: los túneles se cierran antes.
    let para_salir = app.clone();
    let updater = app
        .updater_builder()
        .on_before_exit(move || para_salir.state::<Estado>().tuneles.cerrar_todos())
        .endpoints(vec![endpoint])
        .and_then(|b| b.timeout(TIEMPO_PEDIDO).build())
        .map_err(|e| causa(&e))?;
    let nueva = updater.check().await.map_err(|e| causa(&e))?;
    // El instalador se baja siempre del mismo origen que la ficha, diga lo que diga la ficha.
    Ok(nueva.map(|mut u| {
        u.download_url = descarga;
        u.timeout = Some(TIEMPO_DESCARGA);
        u
    }))
}

/// Chequea si hay una versión nueva. `silencioso`: el del arranque, que no muestra "Buscando…" ni "Ya está al día".
pub fn buscar(app: &AppHandle, silencioso: bool) {
    let libres = [EstadoItem::Inicial, EstadoItem::AlDia, EstadoItem::Hay(String::new())];
    if !pasar(app, &libres, EstadoItem::Buscando) {
        return;
    }
    if silencioso {
        // El texto no cambia en el chequeo del arranque, pero el ítem queda ocupado igual.
        if let Some(item) = app.state::<Actualizador>().item.lock().unwrap().as_ref() {
            let _ = item.set_text(texto_item(&EstadoItem::Inicial));
        }
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        match chequear(&app).await {
            Ok(nueva) => {
                let version = nueva.as_ref().map(|u| u.version.clone());
                *app.state::<Actualizador>().pendiente.lock().unwrap() = nueva;
                if let Some(v) = &version {
                    registro::anotar(Nivel::Info, Origen::App, &format!("hay una versión nueva: {v}"));
                }
                let estado = tras_buscar(version, silencioso);
                let al_dia = estado == EstadoItem::AlDia;
                let gen = poner(&app, estado);
                if al_dia {
                    volver_de_al_dia(&app, gen);
                }
            }
            Err(motivo) => {
                registro::anotar(Nivel::Aviso, Origen::App, &format!("no pude buscar la actualización: {motivo}"));
                poner(&app, EstadoItem::Inicial);
            }
        }
    });
}

fn volver_de_al_dia(app: &AppHandle, gen: u64) {
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(AL_DIA_SEGUNDOS));
        let act = app.state::<Actualizador>();
        if act.generacion.load(Ordering::SeqCst) == gen && act.actual() == EstadoItem::AlDia {
            poner(&app, EstadoItem::Inicial);
        }
    });
}

fn instalar(app: &AppHandle) {
    let Some(update) = app.state::<Actualizador>().pendiente.lock().unwrap().clone() else {
        poner(app, EstadoItem::Inicial);
        buscar(app, false);
        return;
    };
    if !pasar(app, &[EstadoItem::Hay(String::new())], EstadoItem::Instalando) {
        return;
    }
    registro::anotar(Nivel::Info, Origen::App, &format!("instalando la versión {}", update.version));
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        // En Windows, si sale bien, el plugin lanza el instalador y cierra la app; el instalador la vuelve a abrir.
        match update.download_and_install(|_, _| {}, || {}).await {
            Ok(()) => app.restart(),
            Err(e) => {
                registro::anotar(
                    Nivel::Aviso,
                    Origen::App,
                    &format!("no pude instalar la actualización: {}", causa(&e)),
                );
                *app.state::<Actualizador>().pendiente.lock().unwrap() = None;
                poner(&app, EstadoItem::Inicial);
            }
        }
    });
}

pub fn tocar(app: &AppHandle) {
    let estado = app.state::<Actualizador>().actual();
    match al_tocar(&estado) {
        Paso::Buscar => buscar(app, false),
        Paso::Instalar => instalar(app),
        Paso::Nada => {}
    }
}
