use serde::{Deserialize, Serialize};

use crate::posicion::Ancla;
use crate::reunion::ventana::VentanaGuardada;
use crate::atajo_teclas::atajo_valido;
use crate::validar::{validar_destino, validar_monitor, validar_origen};

pub use crate::validar::Destino;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Config {
    #[serde(default)]
    pub origen: Option<String>,
    #[serde(default = "default_arranque")]
    pub arranque: bool,
    #[serde(default)]
    pub monitor: Option<String>,
    #[serde(default)]
    pub ancla: Option<Ancla>,
    #[serde(default)]
    pub notebook: Option<Destino>,
    #[serde(default)]
    pub atajos: Atajos,
    #[serde(default)]
    pub nudo: ConfigNudo,
    #[serde(default)]
    pub reunion_ventana: Option<VentanaGuardada>,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Default)]
pub struct ConfigNudo {
    #[serde(default)]
    pub prendido: bool,
    #[serde(default)]
    pub se_ve_al_compartir: bool,
}

/// Acciones con atajo global.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Accion {
    Notas,
    Notch,
    Colmena,
    Guia,
}

impl Accion {
    pub const TODAS: [Accion; 4] = [Accion::Notas, Accion::Notch, Accion::Colmena, Accion::Guia];

    pub fn default_atajo(self) -> &'static str {
        match self {
            Accion::Notas => "Ctrl+Alt+N",
            Accion::Notch => "Ctrl+Alt+M",
            Accion::Colmena => "Ctrl+Alt+C",
            Accion::Guia => "Ctrl+Alt+V",
        }
    }

    pub fn indice(self) -> usize {
        match self {
            Accion::Notas => 0,
            Accion::Notch => 1,
            Accion::Colmena => 2,
            Accion::Guia => 3,
        }
    }

    pub fn clave(self) -> &'static str {
        match self {
            Accion::Notas => "notas",
            Accion::Notch => "notch",
            Accion::Colmena => "colmena",
            Accion::Guia => "guia",
        }
    }

    pub fn nombre(self) -> &'static str {
        match self {
            Accion::Notas => "Notas",
            Accion::Notch => "Notch",
            Accion::Colmena => "Colmena",
            Accion::Guia => "Guía",
        }
    }

    pub fn desde_clave(c: &str) -> Option<Accion> {
        Accion::TODAS.into_iter().find(|a| a.clave() == c)
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Atajos {
    #[serde(default = "default_notas")]
    pub notas: String,
    #[serde(default = "default_notch")]
    pub notch: String,
    #[serde(default = "default_colmena")]
    pub colmena: String,
    #[serde(default = "default_guia")]
    pub guia: String,
}

fn default_notas() -> String {
    Accion::Notas.default_atajo().into()
}
fn default_notch() -> String {
    Accion::Notch.default_atajo().into()
}
fn default_colmena() -> String {
    Accion::Colmena.default_atajo().into()
}
fn default_guia() -> String {
    Accion::Guia.default_atajo().into()
}

impl Default for Atajos {
    fn default() -> Self {
        Self { notas: default_notas(), notch: default_notch(), colmena: default_colmena(), guia: default_guia() }
    }
}

impl Atajos {
    pub fn get(&self, a: Accion) -> &str {
        match a {
            Accion::Notas => &self.notas,
            Accion::Notch => &self.notch,
            Accion::Colmena => &self.colmena,
            Accion::Guia => &self.guia,
        }
    }

    pub fn set(&mut self, a: Accion, atajo: &str) {
        let v = atajo.to_string();
        match a {
            Accion::Notas => self.notas = v,
            Accion::Notch => self.notch = v,
            Accion::Colmena => self.colmena = v,
            Accion::Guia => self.guia = v,
        }
    }
}

fn default_arranque() -> bool {
    true
}

impl Default for Config {
    fn default() -> Self {
        Self {
            origen: None,
            arranque: true,
            monitor: None,
            ancla: None,
            notebook: None,
            atajos: Atajos::default(),
            nudo: ConfigNudo::default(),
            reunion_ventana: None,
        }
    }
}

impl Config {
    pub fn destino(&self) -> Option<Destino> {
        self.notebook.clone()
    }
}

pub fn leer_config(texto: &str) -> Config {
    let mut c: Config = match serde_json::from_str(texto) {
        Ok(c) => c,
        Err(_) => return Config::default(),
    };
    if let Some(ref o) = c.origen {
        c.origen = validar_origen(o).ok();
    }
    if let Some(ref m) = c.monitor {
        c.monitor = validar_monitor(m);
    }
    if let Some(ref dest) = c.notebook {
        c.notebook = validar_destino(&dest.host, &dest.usuario).ok();
    }
    let valor: serde_json::Value = serde_json::from_str(texto).unwrap_or_default();
    let tiene_notas = valor.pointer("/atajos/notas").is_some();
    if !tiene_notas {
        if let Some(viejo) = valor.get("atajo_notas").and_then(|v| v.as_str()) {
            c.atajos.notas = viejo.to_string();
        }
    }
    for a in Accion::TODAS {
        if !atajo_valido(c.atajos.get(a)) {
            c.atajos.set(a, a.default_atajo());
        }
    }
    // Un atajo repetido en dos acciones: la de después vuelve a su default.
    for (i, a) in Accion::TODAS.into_iter().enumerate() {
        let repetido = Accion::TODAS[..i].iter().any(|b| c.atajos.get(*b) == c.atajos.get(a));
        if repetido {
            c.atajos.set(a, a.default_atajo());
        }
    }
    c
}

pub fn escribir_config(c: &Config) -> String {
    serde_json::to_string_pretty(c).expect("serializar config")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::posicion::Ancla;

    #[test]
    fn config_ida_y_vuelta() {
        let c = Config {
            origen: Some("https://pc.ts.net:8444".into()),
            arranque: false,
            monitor: None,
            ancla: None,
            notebook: None,
            atajos: Atajos::default(),
            ..Config::default()
        };
        assert_eq!(leer_config(&escribir_config(&c)), c);
    }

    #[test]
    fn config_ventana_reunion_ida_y_vuelta() {
        let c = Config {
            reunion_ventana: Some(VentanaGuardada { x: 10, y: 20, ancho: 420, alto: 640 }),
            ..Config::default()
        };
        assert_eq!(leer_config(&escribir_config(&c)), c);
        assert_eq!(leer_config("{}").reunion_ventana, None);
    }

    #[test]
    fn config_monitor_ida_y_vuelta() {
        let c = Config {
            origen: Some("https://pc.ts.net:8444".into()),
            arranque: true,
            monitor: Some("\\\\.\\DISPLAY2".into()),
            ancla: None,
            notebook: None,
            atajos: Atajos::default(),
            ..Config::default()
        };
        assert_eq!(leer_config(&escribir_config(&c)), c);
    }

    #[test]
    fn config_ancla_ida_y_vuelta() {
        let c = Config {
            origen: Some("https://pc.ts.net:8444".into()),
            arranque: true,
            monitor: None,
            ancla: Some(Ancla { x: 400, y: 5 }),
            notebook: None,
            atajos: Atajos::default(),
            ..Config::default()
        };
        assert_eq!(leer_config(&escribir_config(&c)), c);
    }

    #[test]
    fn config_sin_monitor_legacy() {
        assert_eq!(
            leer_config(r#"{"origen":"https://pc.ts.net:8444","arranque":false}"#),
            Config {
                origen: Some("https://pc.ts.net:8444".into()),
                arranque: false,
                monitor: None,
                ancla: None,
                notebook: None,
                atajos: Atajos::default(),
                ..Config::default()
            }
        );
    }

    #[test]
    fn config_monitor_nombre_invalido() {
        let largo = "x".repeat(201);
        let json = format!(r#"{{"monitor":"{largo}"}}"#);
        assert_eq!(
            leer_config(&json),
            Config {
                origen: None,
                arranque: true,
                monitor: None,
                ancla: None,
                notebook: None,
                atajos: Atajos::default(),
                ..Config::default()
            }
        );
        assert_eq!(
            leer_config(r#"{"monitor":"linea\nrota"}"#),
            Config {
                origen: None,
                arranque: true,
                monitor: None,
                ancla: None,
                notebook: None,
                atajos: Atajos::default(),
                ..Config::default()
            }
        );
    }

    #[test]
    fn config_rota_vuelve_al_default() {
        assert_eq!(
            leer_config("{no json"),
            Config {
                origen: None,
                arranque: true,
                monitor: None,
                ancla: None,
                notebook: None,
                atajos: Atajos::default(),
                ..Config::default()
            }
        );
        assert_eq!(
            leer_config(r#"{"origen":"http://x","arranque":false}"#),
            Config {
                origen: None,
                arranque: false,
                monitor: None,
                ancla: None,
                notebook: None,
                atajos: Atajos::default(),
                ..Config::default()
            }
        );
        assert_eq!(
            leer_config("{}"),
            Config {
                origen: None,
                arranque: true,
                monitor: None,
                ancla: None,
                notebook: None,
                atajos: Atajos::default(),
                ..Config::default()
            }
        );
    }

    #[test]
    fn config_vieja_sin_notebook_no_tiene_destino() {
        let c = leer_config(r#"{"origen":"https://pc.ts.net:8444","arranque":true}"#);
        assert_eq!(c.notebook, None);
        assert_eq!(c.destino(), None);
    }

    #[test]
    fn defaults_de_los_cuatro_atajos() {
        let a = Config::default().atajos;
        assert_eq!(a.get(Accion::Guia), "Ctrl+Alt+V");
        assert_eq!(a.get(Accion::Notas), "Ctrl+Alt+N");
        assert_eq!(a.get(Accion::Notch), "Ctrl+Alt+M");
        assert_eq!(a.get(Accion::Colmena), "Ctrl+Alt+C");
    }

    #[test]
    fn config_vieja_sin_guia_usa_el_default() {
        let c = leer_config(r#"{"arranque":true,"atajos":{"notas":"Ctrl+Alt+K","notch":"Ctrl+Alt+M","colmena":"Ctrl+Alt+C"}}"#);
        assert_eq!(c.atajos.get(Accion::Guia), "Ctrl+Alt+V");
        assert_eq!(c.atajos.get(Accion::Notas), "Ctrl+Alt+K");
    }

    #[test]
    fn guia_tiene_clave_y_nombre() {
        assert_eq!(Accion::desde_clave("guia"), Some(Accion::Guia));
        assert_eq!(Accion::Guia.nombre(), "Guía");
        let mut a = Atajos::default();
        a.set(Accion::Guia, "Ctrl+Alt+G");
        assert_eq!(a.get(Accion::Guia), "Ctrl+Alt+G");
    }

    #[test]
    fn config_sin_atajos_usa_los_defaults() {
        assert_eq!(leer_config(r#"{"arranque":true}"#).atajos, Atajos::default());
    }

    #[test]
    fn migra_el_atajo_notas_viejo() {
        let c = leer_config(r#"{"atajo_notas":"Ctrl+Shift+Space"}"#);
        assert_eq!(c.atajos.get(Accion::Notas), "Ctrl+Shift+Space");
        assert_eq!(c.atajos.get(Accion::Notch), "Ctrl+Alt+M");
    }

    #[test]
    fn el_atajo_nuevo_gana_sobre_el_viejo() {
        let c = leer_config(
            r#"{"atajo_notas":"Ctrl+Shift+Space","atajos":{"notas":"Ctrl+Alt+N"}}"#,
        );
        assert_eq!(c.atajos.get(Accion::Notas), "Ctrl+Alt+N");
    }

    #[test]
    fn atajo_invalido_vuelve_al_default_de_esa_accion() {
        let c = leer_config(r#"{"atajos":{"notas":"Alt+F4","notch":"Ctrl+Shift+Space"}}"#);
        assert_eq!(c.atajos.get(Accion::Notas), "Ctrl+Alt+N");
        assert_eq!(c.atajos.get(Accion::Notch), "Ctrl+Shift+Space");
        assert_eq!(c.atajos.get(Accion::Colmena), "Ctrl+Alt+C");
    }

    #[test]
    fn el_viejo_invalido_cae_al_default() {
        let c = leer_config(r#"{"atajo_notas":"Alt+F4"}"#);
        assert_eq!(c.atajos.get(Accion::Notas), "Ctrl+Alt+N");
    }

    #[test]
    fn atajo_repetido_en_dos_acciones_vuelve_al_default_de_la_segunda() {
        let c = leer_config(r#"{"atajos":{"notas":"Ctrl+Shift+Space","notch":"Ctrl+Shift+Space"}}"#);
        assert_eq!(c.atajos.get(Accion::Notas), "Ctrl+Shift+Space");
        assert_eq!(c.atajos.get(Accion::Notch), "Ctrl+Alt+M");
        assert_eq!(c.atajos.get(Accion::Colmena), "Ctrl+Alt+C");
    }

    #[test]
    fn atajo_desde_clave_ida_y_vuelta() {
        for a in Accion::TODAS {
            assert_eq!(Accion::desde_clave(a.clave()), Some(a));
        }
        assert_eq!(Accion::desde_clave("otra"), None);
    }

    #[test]
    fn atajos_ida_y_vuelta() {
        let mut c = Config::default();
        c.atajos.set(Accion::Notch, "Ctrl+Shift+Space");
        let texto = escribir_config(&c);
        assert!(!texto.contains("atajo_notas"));
        assert_eq!(leer_config(&texto), c);
    }

    #[test]
    fn config_con_notebook_tiene_destino() {
        let c = leer_config(r#"{"notebook":{"host":"192.168.1.50","usuario":"usuario"}}"#);
        assert_eq!(c.destino().map(|d| d.ssh()), Some("usuario@192.168.1.50".to_string()));
    }

    #[test]
    fn config_notebook_ida_y_vuelta() {
        let c = Config {
            notebook: Some(Destino {
                host: "192.168.1.20".into(),
                usuario: "usuario".into(),
            }),
            ..Config::default()
        };
        assert_eq!(leer_config(&escribir_config(&c)), c);
    }

    #[test]
    fn config_notebook_invalida_queda_sin_destino() {
        let c = leer_config(r#"{"notebook":{"host":"-host","usuario":"cc"}}"#);
        assert_eq!(c.notebook, None);
        assert_eq!(c.destino(), None);
    }

    #[test]
    fn config_notebook_usuario_invalido_queda_none() {
        let c = leer_config(
            r#"{"notebook":{"host":"192.168.1.50","usuario":"UsuarioMayuscula"}}"#,
        );
        assert_eq!(c.notebook, None);
        assert_eq!(c.destino(), None);
    }

    #[test]
    fn config_sin_nudo_queda_apagado_y_oculto() {
        let c = leer_config("{}");
        assert!(!c.nudo.prendido);
        assert!(!c.nudo.se_ve_al_compartir);
    }

    #[test]
    fn config_nudo_ida_y_vuelta() {
        let mut c = Config::default();
        c.nudo = ConfigNudo { prendido: true, se_ve_al_compartir: true };
        assert_eq!(leer_config(&escribir_config(&c)), c);
    }
}
