//! Hilo de UI Automation del nudo: dueño de la foto (referencias a los elementos) y de los avisos de "usado".
//! Fuera de Windows todo responde `sin_ventana`.

use std::sync::atomic::AtomicIsize;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use colmena_nucleo::nudo::controles::ControlListado;
use colmena_nucleo::nudo::ERR_FALLO_PC;
use colmena_nucleo::posicion::Rect;

#[cfg(windows)]
mod win;
#[cfg(windows)]
pub use win::diagnostico_en_hilo;

// Lectura completa: hasta 1,5 s + 3 s de UIA, con margen.
const ESPERA_LEER: Duration = Duration::from_secs(10);
const ESPERA_RECT: Duration = Duration::from_secs(3);

pub struct Lectura {
    pub foto: u64,
    pub titulo: String,
    pub proceso: String,
    /// Rect físico de la ventana leída (para elegir el monitor).
    pub ventana: Rect,
    /// En orden de `n`: el control `n` es `controles[n - 1]`.
    pub controles: Vec<ControlListado>,
}

pub enum PedidoUia {
    Leer(Sender<Result<Lectura, String>>),
    /// Como `Leer`, pero 0 controles da una foto vacía en vez de `sin_controles` (para "Mostrame").
    LeerMostrar(Sender<Result<Lectura, String>>),
    /// Posición actual del control `idx` de la foto; foto distinta o vencida → `foto_vieja`.
    Rect { foto: u64, idx: usize, resp: Sender<Result<Rect, String>> },
    /// Igual que `Rect` pero sin vencimiento: el seguimiento de un señalar ya aceptado.
    Seguir { foto: u64, idx: usize, resp: Sender<Result<Rect, String>> },
    /// Avisa "usado" por `usado` si el control se invoca o toma el foco.
    Vigilar { foto: u64, idx: usize, usado: Sender<String> },
    Soltar,
}

pub struct HiloUia {
    tx: Mutex<Sender<PedidoUia>>,
    vigia: Arc<AtomicIsize>,
}

impl HiloUia {
    fn enviar(&self, p: PedidoUia) -> Result<(), String> {
        self.tx.lock().unwrap().send(p).map_err(|_| ERR_FALLO_PC.to_string())
    }

    fn pedir<T>(
        &self,
        armar: impl FnOnce(Sender<Result<T, String>>) -> PedidoUia,
        espera: Duration,
    ) -> Result<T, String> {
        let (tx, rx) = channel();
        self.enviar(armar(tx))?;
        rx.recv_timeout(espera).map_err(|_| ERR_FALLO_PC.to_string())?
    }

    pub fn leer(&self) -> Result<Lectura, String> {
        self.pedir(PedidoUia::Leer, ESPERA_LEER)
    }

    pub fn leer_para_mostrar(&self) -> Result<Lectura, String> {
        self.pedir(PedidoUia::LeerMostrar, ESPERA_LEER)
    }

    pub fn rect(&self, foto: u64, idx: usize) -> Result<Rect, String> {
        self.pedir(|resp| PedidoUia::Rect { foto, idx, resp }, ESPERA_RECT)
    }

    pub fn seguir(&self, foto: u64, idx: usize) -> Result<Rect, String> {
        self.pedir(|resp| PedidoUia::Seguir { foto, idx, resp }, ESPERA_RECT)
    }

    pub fn vigilar(&self, foto: u64, idx: usize, usado: Sender<String>) {
        let _ = self.enviar(PedidoUia::Vigilar { foto, idx, usado });
    }

    pub fn soltar(&self) {
        let _ = self.enviar(PedidoUia::Soltar);
    }

    /// Rect físico de la última ventana ajena al frente, si sigue abierta.
    pub fn rect_ventana(&self) -> Option<Rect> {
        #[cfg(windows)]
        {
            win::rect_ventana(&self.vigia)
        }
        #[cfg(not(windows))]
        {
            let _ = &self.vigia;
            None
        }
    }

    /// Id y rect físico visible (sin la sombra de DWM) de la última ventana ajena al frente.
    pub fn ventana_visible(&self) -> Option<(isize, Rect)> {
        #[cfg(windows)]
        {
            win::ventana_visible(&self.vigia)
        }
        #[cfg(not(windows))]
        {
            let _ = &self.vigia;
            None
        }
    }
}

/// La última ventana ajena al frente (hwnd y proceso), para saber sobre cuál se dibuja la marca.
pub fn ventana_guardada() -> Option<colmena_nucleo::nudo::pc::Guardada> {
    #[cfg(windows)]
    {
        win::guardada_actual()
    }
    #[cfg(not(windows))]
    {
        None
    }
}

/// Rects físicos de pantalla de los menús o popups efímeros abiertos (vacío fuera de Windows).
pub fn rects_efimeros() -> Vec<Rect> {
    #[cfg(windows)]
    {
        win::rects_efimeros()
    }
    #[cfg(not(windows))]
    {
        Vec::new()
    }
}

pub fn arrancar_hilo(vigia: Arc<AtomicIsize>) -> HiloUia {
    let (tx, rx) = channel();
    let para_hilo = Arc::clone(&vigia);
    std::thread::Builder::new()
        .name("nudo-uia".into())
        .spawn(move || bucle(rx, para_hilo))
        .expect("hilo del nudo");
    HiloUia { tx: Mutex::new(tx), vigia }
}

#[cfg(windows)]
fn bucle(rx: Receiver<PedidoUia>, vigia: Arc<AtomicIsize>) {
    win::bucle(rx, vigia)
}

#[cfg(not(windows))]
fn bucle(rx: Receiver<PedidoUia>, _vigia: Arc<AtomicIsize>) {
    use colmena_nucleo::nudo::ERR_SIN_VENTANA;
    for p in rx {
        match p {
            PedidoUia::Leer(r) | PedidoUia::LeerMostrar(r) => {
                let _ = r.send(Err(ERR_SIN_VENTANA.into()));
            }
            PedidoUia::Rect { resp, .. } | PedidoUia::Seguir { resp, .. } => {
                let _ = resp.send(Err(ERR_SIN_VENTANA.into()));
            }
            PedidoUia::Vigilar { .. } | PedidoUia::Soltar => {}
        }
    }
}

/// Recuerda la última ventana al frente que no es de Colmena (0 si no hay).
pub fn arrancar_vigia_foreground(app: tauri::AppHandle) -> Arc<AtomicIsize> {
    let vigia = Arc::new(AtomicIsize::new(0));
    #[cfg(windows)]
    win::arrancar_vigia(Arc::clone(&vigia), app);
    vigia
}
