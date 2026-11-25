//! Lector de los Subtítulos en vivo de Windows 11 por UI Automation (copiloto de reuniones).
//! Fuera de Windows el hilo no arranca y el diagnóstico no hace nada.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{channel, sync_channel, Sender, SyncSender};
use std::sync::Mutex;
use std::time::Duration;

use colmena_nucleo::registro::{Nivel, Origen};
use colmena_nucleo::reunion::ESTADO_APAGADO;
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};

use crate::{exige_notch_o_reunion, exige_ventana, ventanas, Estado};

#[cfg(windows)]
mod win;

/// Cuánto espera un comando la respuesta del hilo antes de devolver el último estado conocido.
const ESPERA_RESPUESTA: Duration = Duration::from_secs(3);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PedidoLector {
    Escuchar,
    Pausar,
    Seguir,
    Terminar,
    Diagnostico,
}

/// Lo que recibe el hilo: pedidos de afuera y textos que mandan los avisos de UIA.
pub(crate) enum Mensaje {
    Pedido(PedidoLector),
    Pedir(Solicitud),
    #[cfg_attr(not(windows), allow(dead_code))]
    Evento(Fuente, String),
}

/// Pedido que espera respuesta: el hilo contesta con el estado del lector cuando ya emitió todo lo pendiente.
#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) struct Solicitud {
    pub pedido: PedidoLector,
    pub motivo: Option<&'static str>,
    pub tx: SyncSender<&'static str>,
}

#[cfg_attr(not(windows), allow(dead_code))]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Fuente {
    Nombre,
    TextoCambiado,
}

pub struct LectorReunion {
    tx: Sender<Mensaje>,
}

impl LectorReunion {
    pub fn enviar(&self, p: PedidoLector) {
        let _ = self.tx.send(Mensaje::Pedido(p));
    }

    /// Manda el pedido y espera el estado resultante; `None` si el hilo no contesta a tiempo.
    pub fn pedir(&self, pedido: PedidoLector, motivo: Option<&'static str>) -> Option<&'static str> {
        let (tx, rx) = sync_channel(1);
        self.tx.send(Mensaje::Pedir(Solicitud { pedido, motivo, tx })).ok()?;
        rx.recv_timeout(ESPERA_RESPUESTA).ok()
    }

    /// Escucha 60 s y escribe `reunion-diagnostico.txt` y `reunion-crudo.txt` en la carpeta de config.
    pub fn diagnostico(&self) {
        self.enviar(PedidoLector::Diagnostico);
    }
}

/// Hilo `reunion-uia`: dueño de su propio `IUIAutomation` (MTA), aparte del hilo del nudo.
#[cfg_attr(not(windows), allow(unused_variables))]
pub fn arrancar_hilo(app: AppHandle) -> LectorReunion {
    let (tx, rx) = channel();
    #[cfg(windows)]
    {
        let para_hilo = tx.clone();
        std::thread::Builder::new()
            .name("reunion-uia".into())
            .spawn(move || win::bucle(rx, para_hilo, app))
            .expect("hilo de reunión");
    }
    #[cfg(not(windows))]
    drop(rx);
    LectorReunion { tx }
}

/// Lo que la app sabe de la reunión: si está escuchando (el notch se oculta al compartir) y el último estado del lector.
pub struct EstadoReunion {
    pub escuchando: AtomicBool,
    pub lector: Mutex<&'static str>,
    /// Los Subtítulos en vivo los abrió Colmena en esta reunión (y por eso los cierra al terminar).
    #[cfg_attr(not(windows), allow(dead_code))]
    pub subtitulos_de_colmena: AtomicBool,
}

impl Default for EstadoReunion {
    fn default() -> Self {
        Self { escuchando: AtomicBool::new(false), lector: Mutex::new(ESTADO_APAGADO), subtitulos_de_colmena: AtomicBool::new(false) }
    }
}

pub fn escuchando(app: &AppHandle) -> bool {
    app.state::<Estado>().reunion.escuchando.load(Ordering::SeqCst)
}

fn estado_lector(estado: &Estado) -> &'static str {
    *estado.reunion.lector.lock().unwrap()
}

fn pedir(app: &AppHandle, estado: &Estado, p: PedidoLector, motivo: Option<&'static str>) -> &'static str {
    app.state::<LectorReunion>()
        .pedir(p, motivo)
        .unwrap_or_else(|| estado_lector(estado))
}

/// Corre una espera bloqueante (hasta `ESPERA_RESPUESTA`) fuera de los workers del runtime async.
async fn bloqueante<T: Send + 'static>(f: impl FnOnce() -> T + Send + 'static) -> Result<T, String> {
    tauri::async_runtime::spawn_blocking(f).await.map_err(|e| e.to_string())
}

fn se_ve_al_compartir(estado: &Estado) -> bool {
    crate::leer_config_archivo(&estado.ruta_config).nudo.se_ve_al_compartir
}

/// Cambia `escuchando` y deja ocultas o visibles las ventanas; si falla, revierte el valor.
fn poner_escuchando(app: &AppHandle, estado: &Estado, valor: bool) -> Result<(), String> {
    let antes = estado.reunion.escuchando.swap(valor, Ordering::SeqCst);
    let r = ventanas::aplicar_visibilidad(app, se_ve_al_compartir(estado), valor);
    if r.is_err() {
        estado.reunion.escuchando.store(antes, Ordering::SeqCst);
    }
    crate::bandeja::sincronizar_reunion(app);
    r
}

/// Termina la reunión: el hilo emite lo que quede y recién entonces el notch vuelve a verse al compartir.
pub(crate) fn terminar(app: &AppHandle, motivo: Option<&'static str>) -> Result<&'static str, String> {
    let estado = app.state::<Estado>();
    let r = match app.state::<LectorReunion>().pedir(PedidoLector::Terminar, motivo) {
        Some(r) => r,
        None => {
            // El hilo no contestó: igual hay que avisarle al notch (la bandeja depende de este aviso para postear /terminar).
            *estado.reunion.lector.lock().unwrap() = ESTADO_APAGADO;
            for destino in ["notch", "reunion"] {
                let _ = app.emit_to(
                    destino,
                    "reunion-lector",
                    serde_json::json!({ "estado": ESTADO_APAGADO, "motivo": motivo }),
                );
            }
            ESTADO_APAGADO
        }
    };
    let fin = poner_escuchando(app, &estado, false);
    ventanas::cerrar_reunion(app);
    fin?;
    Ok(r)
}

#[tauri::command(rename_all = "snake_case")]
pub async fn reunion_escuchar(
    window: WebviewWindow,
    app: AppHandle,
    estado: State<'_, Estado>,
) -> Result<String, String> {
    exige_notch_o_reunion(&window, &estado)?;
    let app_ventana = app.clone();
    let lector = bloqueante(move || {
        let estado = app.state::<Estado>();
        poner_escuchando(&app, &estado, true)?;
        Ok::<_, String>(pedir(&app, &estado, PedidoLector::Escuchar, None).to_string())
    })
    .await??;
    // La reunión se sigue en su propia ventana; si no abre, la reunión igual escucha.
    if let Err(e) = ventanas::mostrar_reunion(&app_ventana) {
        crate::registro::anotar(
            Nivel::Aviso,
            Origen::Reunion,
            &format!("no se pudo abrir la ventana: {e}"),
        );
    }
    Ok(lector)
}

/// Trae al frente la ventana "Reunión" (la abre si hace falta); solo la pide el notch.
#[tauri::command(rename_all = "snake_case")]
pub async fn reunion_mostrar_ventana(
    window: WebviewWindow,
    app: AppHandle,
    estado: State<'_, Estado>,
) -> Result<(), String> {
    exige_ventana(&window, &estado, "notch")?;
    ventanas::mostrar_reunion(&app)
}

#[tauri::command(rename_all = "snake_case")]
pub async fn reunion_pausar(
    window: WebviewWindow,
    app: AppHandle,
    estado: State<'_, Estado>,
) -> Result<String, String> {
    exige_notch_o_reunion(&window, &estado)?;
    bloqueante(move || pedir(&app, &app.state::<Estado>(), PedidoLector::Pausar, None).to_string()).await
}

#[tauri::command(rename_all = "snake_case")]
pub async fn reunion_seguir(
    window: WebviewWindow,
    app: AppHandle,
    estado: State<'_, Estado>,
) -> Result<String, String> {
    exige_notch_o_reunion(&window, &estado)?;
    bloqueante(move || pedir(&app, &app.state::<Estado>(), PedidoLector::Seguir, None).to_string()).await
}

#[tauri::command(rename_all = "snake_case")]
pub async fn reunion_terminar(
    window: WebviewWindow,
    app: AppHandle,
    estado: State<'_, Estado>,
) -> Result<String, String> {
    exige_notch_o_reunion(&window, &estado)?;
    bloqueante(move || terminar(&app, None).map(str::to_string)).await?
}

#[tauri::command(rename_all = "snake_case")]
pub async fn reunion_estado(window: WebviewWindow, estado: State<'_, Estado>) -> Result<String, String> {
    exige_notch_o_reunion(&window, &estado)?;
    Ok(estado_lector(&estado).to_string())
}
