use std::collections::{BTreeMap, HashMap};
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use colmena_nucleo::entornos::{EstadoTunel, FaseTunel, ultima_linea};
use colmena_nucleo::registro::{Nivel, Origen};
use colmena_nucleo::util::recortar_inicio;

use crate::registro;

const STDERR_MAX: usize = 4096;
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

enum Entrada {
    Abierto {
        generacion: u64,
        hijo: Child,
        puertos: Vec<u16>,
        stderr: Arc<Mutex<String>>,
        lector_join: JoinHandle<()>,
    },
    Error {
        generacion: u64,
        puertos: Vec<u16>,
        error: String,
    },
}

enum RefrescarSalida {
    SigueVivo {
        hijo: Child,
        puertos: Vec<u16>,
        stderr: Arc<Mutex<String>>,
        lector_join: JoinHandle<()>,
    },
    TerminoConError { puertos: Vec<u16>, error: String },
}

fn texto_stderr(stderr: &Arc<Mutex<String>>) -> String {
    stderr
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone()
}

fn refrescar(
    hijo: Child,
    puertos: Vec<u16>,
    stderr: Arc<Mutex<String>>,
    lector_join: JoinHandle<()>,
) -> RefrescarSalida {
    let mut hijo = hijo;
    match hijo.try_wait() {
        Ok(None) => RefrescarSalida::SigueVivo {
            hijo,
            puertos,
            stderr,
            lector_join,
        },
        Ok(Some(_)) => {
            let _ = lector_join.join();
            let texto = texto_stderr(&stderr);
            let err = ultima_linea(&texto);
            let err = if err.is_empty() {
                "el túnel terminó".into()
            } else {
                err
            };
            RefrescarSalida::TerminoConError { puertos, error: err }
        }
        Err(_) => RefrescarSalida::SigueVivo {
            hijo,
            puertos,
            stderr,
            lector_join,
        },
    }
}

fn anotar_cerrado(nombre: &str) {
    registro::anotar(Nivel::Info, Origen::Tuneles, &format!("túnel {nombre} cerrado"));
}

fn push_stderr_tail(buf: &mut String, line: &str) {
    buf.push_str(line);
    buf.push('\n');
    if buf.len() > STDERR_MAX {
        recortar_inicio(buf, STDERR_MAX);
    }
}

fn finaliza_abierto(
    mapa: &mut HashMap<String, Entrada>,
    nombre: String,
    generacion: u64,
    hijo: Child,
    puertos: Vec<u16>,
    stderr: Arc<Mutex<String>>,
    lector_join: JoinHandle<()>,
) -> Option<EstadoTunel> {
    match refrescar(hijo, puertos, stderr, lector_join) {
        RefrescarSalida::SigueVivo {
            hijo,
            puertos,
            stderr,
            lector_join,
        } => {
            let p = puertos.clone();
            mapa.insert(
                nombre,
                Entrada::Abierto {
                    generacion,
                    hijo,
                    puertos: p.clone(),
                    stderr,
                    lector_join,
                },
            );
            Some(EstadoTunel {
                estado: FaseTunel::Abierto,
                puertos: p,
                error: None,
            })
        }
        RefrescarSalida::TerminoConError { puertos, error } => {
            let err = error.clone();
            mapa.insert(
                nombre,
                Entrada::Error {
                    generacion,
                    puertos: puertos.clone(),
                    error,
                },
            );
            Some(EstadoTunel {
                estado: FaseTunel::Error,
                puertos,
                error: Some(err),
            })
        }
    }
}

#[derive(Clone)]
pub struct Tuneles {
    inner: Arc<Mutex<HashMap<String, Entrada>>>,
    gen_siguiente: Arc<AtomicU64>,
}

impl Default for Tuneles {
    fn default() -> Self {
        Self {
            inner: Arc::new(Mutex::new(HashMap::new())),
            gen_siguiente: Arc::new(AtomicU64::new(0)),
        }
    }
}

impl Tuneles {
    pub fn estado(&self) -> BTreeMap<String, EstadoTunel> {
        let mut mapa = self.inner.lock().unwrap();
        let claves: Vec<String> = mapa.keys().cloned().collect();
        let mut out = BTreeMap::new();
        for k in claves {
            let Some(ent) = mapa.remove(&k) else {
                continue;
            };
            match ent {
                Entrada::Abierto {
                    generacion,
                    hijo,
                    puertos,
                    stderr,
                    lector_join,
                } => {
                    if let Some(e) = finaliza_abierto(
                        &mut mapa,
                        k.clone(),
                        generacion,
                        hijo,
                        puertos,
                        stderr,
                        lector_join,
                    ) {
                        out.insert(k, e);
                    }
                }
                Entrada::Error {
                    puertos,
                    error,
                    ..
                } => {
                    out.insert(
                        k,
                        EstadoTunel {
                            estado: FaseTunel::Error,
                            puertos,
                            error: Some(error),
                        },
                    );
                }
            }
        }
        out
    }

    pub fn abiertos(&self, nombre: &str) -> Option<Vec<u16>> {
        let mut mapa = self.inner.lock().unwrap();
        let Some(ent) = mapa.remove(nombre) else {
            return None;
        };
        match ent {
            Entrada::Abierto {
                generacion,
                hijo,
                puertos,
                stderr,
                lector_join,
            } => match refrescar(hijo, puertos, stderr, lector_join) {
                RefrescarSalida::SigueVivo {
                    hijo,
                    puertos,
                    stderr,
                    lector_join,
                } => {
                    let p = puertos.clone();
                    mapa.insert(
                        nombre.to_string(),
                        Entrada::Abierto {
                            generacion,
                            hijo,
                            puertos,
                            stderr,
                            lector_join,
                        },
                    );
                    Some(p)
                }
                RefrescarSalida::TerminoConError { puertos, error } => {
                    mapa.insert(
                        nombre.to_string(),
                        Entrada::Error {
                            generacion,
                            puertos,
                            error,
                        },
                    );
                    None
                }
            },
            Entrada::Error { .. } => {
                mapa.insert(nombre.to_string(), ent);
                None
            }
        }
    }

    pub fn otros(&self, nombre: &str) -> Vec<(String, Vec<u16>)> {
        let est = self.estado();
        est
            .into_iter()
            .filter(|(n, e)| n != nombre && e.estado == FaseTunel::Abierto)
            .map(|(n, e)| (n, e.puertos))
            .collect()
    }

    pub fn lanzar(
        &self,
        nombre: &str,
        puertos: Vec<u16>,
        ssh: &Path,
        argv: &[String],
    ) -> Result<u64, String> {
        let mut mapa = self.inner.lock().unwrap();
        match mapa.remove(nombre) {
            Some(Entrada::Abierto {
                generacion: prev_gen,
                mut hijo,
                puertos: prev_p,
                stderr: prev_e,
                lector_join: prev_join,
            }) => match hijo.try_wait() {
                Ok(None) => {
                    mapa.insert(
                        nombre.to_string(),
                        Entrada::Abierto {
                            generacion: prev_gen,
                            hijo,
                            puertos: prev_p,
                            stderr: prev_e,
                            lector_join: prev_join,
                        },
                    );
                    return Err("ese entorno ya está abierto".into());
                }
                Ok(Some(_)) => {
                    let _ = hijo.wait();
                    let _ = prev_join.join();
                }
                Err(_) => {
                    let _ = hijo.kill();
                    let _ = hijo.wait();
                    let _ = prev_join.join();
                }
            },
            Some(Entrada::Error { .. }) | None => {}
        }

        let generacion = self.gen_siguiente.fetch_add(1, Ordering::SeqCst) + 1;

        let mut cmd = Command::new(ssh);
        cmd.args(argv);
        cmd.stdin(Stdio::null());
        cmd.stdout(Stdio::null());
        cmd.stderr(Stdio::piped());
        #[cfg(windows)]
        cmd.creation_flags(CREATE_NO_WINDOW);

        let mut hijo = cmd.spawn().map_err(|e| e.to_string())?;
        let stderr_pipe = hijo.stderr.take().ok_or_else(|| "stderr".to_string())?;
        let stderr = Arc::new(Mutex::new(String::new()));
        let compartido = Arc::clone(&stderr);
        let lector_join = std::thread::spawn(move || {
            let mut lector = BufReader::new(stderr_pipe);
            let mut buf_line = Vec::new();
            loop {
                buf_line.clear();
                match lector.read_until(b'\n', &mut buf_line) {
                    Ok(0) => break,
                    Ok(_) => {
                        let fragment = String::from_utf8_lossy(&buf_line);
                        let line = fragment.trim_end_matches(|c| c == '\r' || c == '\n');
                        let mut g = compartido.lock().unwrap_or_else(|e| e.into_inner());
                        push_stderr_tail(&mut *g, line);
                    }
                    Err(_) => break,
                }
            }
        });

        mapa.insert(
            nombre.to_string(),
            Entrada::Abierto {
                generacion,
                hijo,
                puertos,
                stderr,
                lector_join,
            },
        );
        Ok(generacion)
    }

    pub fn terminado(&self, nombre: &str) -> Option<String> {
        let mut mapa = self.inner.lock().unwrap();
        let Some(ent) = mapa.remove(nombre) else {
            return None;
        };
        match ent {
            Entrada::Abierto {
                generacion,
                hijo,
                puertos,
                stderr,
                lector_join,
            } => match refrescar(hijo, puertos, stderr, lector_join) {
                RefrescarSalida::SigueVivo {
                    hijo,
                    puertos,
                    stderr,
                    lector_join,
                } => {
                    mapa.insert(
                        nombre.to_string(),
                        Entrada::Abierto {
                            generacion,
                            hijo,
                            puertos,
                            stderr,
                            lector_join,
                        },
                    );
                    None
                }
                RefrescarSalida::TerminoConError { puertos, error } => {
                    let ret = error.clone();
                    mapa.insert(
                        nombre.to_string(),
                        Entrada::Error {
                            generacion,
                            puertos,
                            error,
                        },
                    );
                    Some(ret)
                }
            },
            Entrada::Error { .. } => {
                mapa.insert(nombre.to_string(), ent);
                None
            }
        }
    }

    pub fn cerrar_si(&self, nombre: &str, generacion: u64) {
        let mut mapa = self.inner.lock().unwrap();
        let coincide = match mapa.get(nombre) {
            Some(Entrada::Abierto { generacion: g, .. }) => *g == generacion,
            Some(Entrada::Error { generacion: g, .. }) => *g == generacion,
            None => return,
        };
        if !coincide {
            return;
        }
        let Some(ent) = mapa.remove(nombre) else {
            return;
        };
        match ent {
            Entrada::Abierto {
                mut hijo,
                lector_join,
                ..
            } => {
                let _ = hijo.kill();
                let _ = hijo.wait();
                let _ = lector_join.join();
            }
            Entrada::Error { .. } => {}
        }
    }

    pub fn cerrar(&self, nombre: &str) {
        let mut mapa = self.inner.lock().unwrap();
        let Some(ent) = mapa.remove(nombre) else {
            return;
        };
        match ent {
            Entrada::Abierto {
                mut hijo,
                lector_join,
                ..
            } => {
                let _ = hijo.kill();
                let _ = hijo.wait();
                let _ = lector_join.join();
                anotar_cerrado(nombre);
            }
            Entrada::Error { .. } => {}
        }
    }

    pub fn cerrar_todos(&self) {
        let mut mapa = self.inner.lock().unwrap();
        for (nombre, ent) in mapa.drain() {
            if let Entrada::Abierto {
                mut hijo,
                lector_join,
                ..
            } = ent
            {
                let _ = hijo.kill();
                let _ = hijo.wait();
                let _ = lector_join.join();
                anotar_cerrado(&nombre);
            }
        }
    }
}
