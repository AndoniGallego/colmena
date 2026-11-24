use serde::{Deserialize, Serialize};

use super::ERR_INVALIDO;

pub const PASOS_MAX: u32 = 15;

#[derive(Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct PasoGuia {
    pub paso: u32,
    pub total: u32,
    pub fin: bool,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct GloboGuia {
    pub cabecera: String,
    pub siguiente: bool,
    pub listo: bool,
    /// Paso vigente y total (0 sin paso): el globo dibuja un puntito de panal por paso.
    pub paso: u32,
    pub total: u32,
}

pub fn acotar_paso(paso: u32, total: u32, fin: bool) -> PasoGuia {
    let paso = paso.clamp(1, PASOS_MAX);
    PasoGuia { paso, total: total.clamp(paso, PASOS_MAX), fin }
}

pub fn globo_guia(p: Option<PasoGuia>) -> GloboGuia {
    match p {
        None => GloboGuia { cabecera: "Guía".into(), siguiente: true, listo: false, paso: 0, total: 0 },
        Some(p) => {
            let p = acotar_paso(p.paso, p.total, p.fin);
            GloboGuia {
                cabecera: format!("Paso {} de {}", p.paso, p.total),
                siguiente: !p.fin,
                listo: p.fin,
                paso: p.paso,
                total: p.total,
            }
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum AccionGuia {
    Siguiente,
    Listo,
}

impl AccionGuia {
    pub fn desde(s: &str) -> Result<AccionGuia, String> {
        match s {
            "siguiente" => Ok(AccionGuia::Siguiente),
            "listo" => Ok(AccionGuia::Listo),
            _ => Err(ERR_INVALIDO.to_string()),
        }
    }

    pub fn evento(self) -> &'static str {
        match self {
            AccionGuia::Siguiente => "guia-siguiente",
            AccionGuia::Listo => "guia-listo",
        }
    }
}

/// Qué hace el atajo de la guía según el globo que está a la vista.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum AtajoGuia {
    /// Hay un paso a la vista: hace lo mismo que el botón del globo, sin mostrar ni activar ninguna ventana.
    Avanzar(AccionGuia),
    /// Sin paso a la vista: abre la cajita con el foco en el campo.
    AbrirCajita,
}

/// `globo` es el globo de guía visible (None si no hay globo o no es de guía).
pub fn atajo_guia(globo: Option<&GloboGuia>) -> AtajoGuia {
    match globo {
        Some(g) if g.siguiente => AtajoGuia::Avanzar(AccionGuia::Siguiente),
        Some(g) if g.listo => AtajoGuia::Avanzar(AccionGuia::Listo),
        _ => AtajoGuia::AbrirCajita,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::nudo::ERR_INVALIDO;

    #[test]
    fn con_un_paso_a_la_vista_el_atajo_avanza() {
        let g = globo_guia(Some(PasoGuia { paso: 1, total: 3, fin: false }));
        assert_eq!(atajo_guia(Some(&g)), AtajoGuia::Avanzar(AccionGuia::Siguiente));
        assert_eq!(atajo_guia(Some(&globo_guia(None))), AtajoGuia::Avanzar(AccionGuia::Siguiente));
    }

    #[test]
    fn en_el_ultimo_paso_el_atajo_termina() {
        let g = globo_guia(Some(PasoGuia { paso: 3, total: 3, fin: true }));
        assert_eq!(atajo_guia(Some(&g)), AtajoGuia::Avanzar(AccionGuia::Listo));
    }

    #[test]
    fn sin_globo_de_guia_el_atajo_abre_la_cajita() {
        assert_eq!(atajo_guia(None), AtajoGuia::AbrirCajita);
        let sin_botones = GloboGuia { cabecera: "Guía".into(), siguiente: false, listo: false, paso: 0, total: 0 };
        assert_eq!(atajo_guia(Some(&sin_botones)), AtajoGuia::AbrirCajita);
    }

    #[test]
    fn acotar_paso_respeta_limites() {
        assert_eq!(acotar_paso(0, 0, false), PasoGuia { paso: 1, total: 1, fin: false });
        assert_eq!(acotar_paso(3, 2, false), PasoGuia { paso: 3, total: 3, fin: false });
        assert_eq!(acotar_paso(99, 999, true), PasoGuia { paso: 15, total: 15, fin: true });
    }

    #[test]
    fn globo_guia_sin_paso_paso_y_fin() {
        assert_eq!(
            globo_guia(None),
            GloboGuia { cabecera: "Guía".into(), siguiente: true, listo: false, paso: 0, total: 0 }
        );
        assert_eq!(
            globo_guia(Some(PasoGuia { paso: 2, total: 4, fin: false })),
            GloboGuia { cabecera: "Paso 2 de 4".into(), siguiente: true, listo: false, paso: 2, total: 4 }
        );
        assert_eq!(
            globo_guia(Some(PasoGuia { paso: 3, total: 3, fin: true })),
            GloboGuia { cabecera: "Paso 3 de 3".into(), siguiente: false, listo: true, paso: 3, total: 3 }
        );
    }

    #[test]
    fn globo_guia_lleva_el_paso_acotado_para_los_puntitos() {
        let g = globo_guia(Some(PasoGuia { paso: 40, total: 90, fin: false }));
        assert_eq!((g.paso, g.total), (15, 15));
    }

    #[test]
    fn accion_guia_desde_texto() {
        assert_eq!(AccionGuia::desde("siguiente").map(|a| a.evento()), Ok("guia-siguiente"));
        assert_eq!(AccionGuia::desde("listo").map(|a| a.evento()), Ok("guia-listo"));
        assert_eq!(AccionGuia::desde("salir"), Err(ERR_INVALIDO.to_string()));
    }
}
