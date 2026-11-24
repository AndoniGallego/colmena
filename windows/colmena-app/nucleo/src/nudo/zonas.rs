use serde::{Deserialize, Serialize};

use super::coords::{a_overlay, RectLogico};
use super::orden::{foto_vigente, validar_texto, ETIQUETA_MAX, MARCAS_MAX};
use super::{ERR_FOTO_VIEJA, ERR_INVALIDO};
use crate::posicion::Rect;

pub const LADO_MAX_IMAGEN: u32 = 1568;

#[derive(Deserialize, Serialize, Clone, Copy, Debug, PartialEq)]
pub struct ZonaImagen {
    pub x: u32,
    pub y: u32,
    pub ancho: u32,
    pub alto: u32,
}

#[derive(Deserialize, Clone, Debug, PartialEq)]
pub struct ZonaEtiquetada {
    pub x: u32,
    pub y: u32,
    pub ancho: u32,
    pub alto: u32,
    pub etiqueta: String,
}

impl ZonaEtiquetada {
    pub fn zona(&self) -> ZonaImagen {
        ZonaImagen { x: self.x, y: self.y, ancho: self.ancho, alto: self.alto }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Captura {
    pub foto: u64,
    pub ventana_id: isize,
    pub ventana: Rect,
    pub recorte: Rect,
    pub ancho: u32,
    pub alto: u32,
    pub creada_ms: u64,
}

fn redondear(num: u64, den: u64) -> u64 {
    (num * 2 + den) / (den * 2)
}

pub fn tam_imagen(recorte: Rect, lado_max: u32) -> (u32, u32) {
    let (a, h) = (recorte.ancho as u64, recorte.alto as u64);
    let mayor = a.max(h);
    let max = lado_max as u64;
    if mayor <= max || mayor == 0 {
        return (recorte.ancho.max(1), recorte.alto.max(1));
    }
    let esc = |v: u64| redondear(v * max, mayor).max(1) as u32;
    (esc(a), esc(h))
}

pub fn recorte_captura(ventana: Rect, monitor: Rect) -> Option<Rect> {
    let x0 = (ventana.x as i64).max(monitor.x as i64);
    let y0 = (ventana.y as i64).max(monitor.y as i64);
    let x1 = (ventana.x as i64 + ventana.ancho as i64).min(monitor.x as i64 + monitor.ancho as i64);
    let y1 = (ventana.y as i64 + ventana.alto as i64).min(monitor.y as i64 + monitor.alto as i64);
    if x1 <= x0 || y1 <= y0 {
        return None;
    }
    Some(Rect { x: x0 as i32, y: y0 as i32, ancho: (x1 - x0) as u32, alto: (y1 - y0) as u32 })
}

pub fn validar_zona(z: &ZonaImagen, cap: &Captura) -> Result<(), String> {
    let dentro = z.x as u64 + z.ancho as u64 <= cap.ancho as u64
        && z.y as u64 + z.alto as u64 <= cap.alto as u64;
    if z.ancho == 0 || z.alto == 0 || !dentro {
        return Err(ERR_INVALIDO.into());
    }
    Ok(())
}

pub fn validar_zonas(z: Vec<ZonaEtiquetada>, cap: &Captura) -> Result<Vec<ZonaEtiquetada>, String> {
    if z.is_empty() || z.len() > MARCAS_MAX {
        return Err(ERR_INVALIDO.into());
    }
    z.into_iter()
        .map(|mut e| {
            validar_zona(&e.zona(), cap)?;
            e.etiqueta = validar_texto(&e.etiqueta, ETIQUETA_MAX)?;
            Ok(e)
        })
        .collect()
}

pub fn zona_a_fisico(z: &ZonaImagen, cap: &Captura) -> Rect {
    let (ia, ih) = (cap.ancho.max(1) as u64, cap.alto.max(1) as u64);
    let (ra, rh) = (cap.recorte.ancho as u64, cap.recorte.alto as u64);
    let sx = |v: u32| redondear(v as u64 * ra, ia);
    let sy = |v: u32| redondear(v as u64 * rh, ih);
    Rect {
        x: (cap.recorte.x as i64 + sx(z.x) as i64) as i32,
        y: (cap.recorte.y as i64 + sy(z.y) as i64) as i32,
        ancho: sx(z.ancho).max(1) as u32,
        alto: sy(z.alto).max(1) as u32,
    }
}

/// La ventana al frente sigue siendo la capturada: mismo id y mismo rect visible.
pub fn misma_ventana(capturada: (isize, Rect), actual: Option<(isize, Rect)>) -> bool {
    actual == Some(capturada)
}

pub fn captura_vigente(
    cap: Option<&Captura>,
    foto: u64,
    actual: Option<(isize, Rect)>,
    ahora_ms: u64,
) -> Result<Captura, String> {
    let vieja = || ERR_FOTO_VIEJA.to_string();
    let c = cap.ok_or_else(vieja)?;
    if c.foto != foto || !foto_vigente(c.creada_ms, ahora_ms) {
        return Err(vieja());
    }
    if !misma_ventana((c.ventana_id, c.ventana), actual) {
        return Err(vieja());
    }
    Ok(*c)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn cap() -> Captura { Captura { foto: 7, ventana_id: 11, ventana: Rect { x: 1900, y: -8, ancho: 3160, alto: 1980 },
        recorte: Rect { x: 1920, y: 0, ancho: 3136, alto: 1960 }, ancho: 1568, alto: 980, creada_ms: 1_000 } }
    #[test] fn tam_imagen_achica_al_lado_mayor_sin_agrandar() {
        assert_eq!(tam_imagen(Rect { x: 0, y: 0, ancho: 3136, alto: 1960 }, 1568), (1568, 980));
        assert_eq!(tam_imagen(Rect { x: 0, y: 0, ancho: 2000, alto: 3000 }, 1568), (1045, 1568));
        assert_eq!(tam_imagen(Rect { x: 0, y: 0, ancho: 1500, alto: 900 }, 1568), (1500, 900));
        assert_eq!(tam_imagen(Rect { x: 0, y: 0, ancho: 10_000, alto: 1 }, 1568), (1568, 1));
    }
    #[test] fn recorte_es_la_parte_en_el_monitor() {
        let m = Rect { x: 1920, y: 0, ancho: 3840, alto: 2160 };
        assert_eq!(recorte_captura(cap().ventana, m), Some(Rect { x: 1920, y: 0, ancho: 3140, alto: 1972 }));
        assert_eq!(recorte_captura(Rect { x: 0, y: 0, ancho: 100, alto: 100 }, m), None);
    }
    #[test] fn zona_a_fisico_con_imagen_achicada_y_segundo_monitor_125() {
        let f = zona_a_fisico(&ZonaImagen { x: 100, y: 50, ancho: 200, alto: 40 }, &cap());
        assert_eq!(f, Rect { x: 2120, y: 100, ancho: 400, alto: 80 });
        let m = Rect { x: 1920, y: 0, ancho: 3840, alto: 2160 };
        assert_eq!(a_overlay(f, m, 1.25), Some(RectLogico { x: 160.0, y: 80.0, ancho: 320.0, alto: 64.0 }));
    }
    #[test] fn zona_a_fisico_sin_achicar_con_escala_150_y_100() {
        let c = Captura { recorte: Rect { x: 300, y: 150, ancho: 1500, alto: 900 }, ancho: 1500, alto: 900, ..cap() };
        let f = zona_a_fisico(&ZonaImagen { x: 0, y: 0, ancho: 150, alto: 75 }, &c);
        assert_eq!(f, Rect { x: 300, y: 150, ancho: 150, alto: 75 });
        let m = Rect { x: 0, y: 0, ancho: 3840, alto: 2160 };
        assert_eq!(a_overlay(f, m, 1.5), Some(RectLogico { x: 200.0, y: 100.0, ancho: 100.0, alto: 50.0 }));
        assert_eq!(a_overlay(f, m, 1.0), Some(RectLogico { x: 300.0, y: 150.0, ancho: 150.0, alto: 75.0 }));
    }
    #[test] fn zona_minima_no_queda_en_cero() {
        let f = zona_a_fisico(&ZonaImagen { x: 0, y: 0, ancho: 1, alto: 1 }, &Captura { recorte: Rect { x: 0, y: 0, ancho: 100, alto: 100 }, ancho: 1568, alto: 1568, ..cap() });
        assert!(f.ancho >= 1 && f.alto >= 1);
    }
    #[test] fn validar_zona_fuera_de_la_imagen() {
        assert!(validar_zona(&ZonaImagen { x: 1468, y: 940, ancho: 100, alto: 40 }, &cap()).is_ok());
        for z in [ZonaImagen { x: 1469, y: 0, ancho: 100, alto: 10 }, ZonaImagen { x: 0, y: 941, ancho: 10, alto: 40 },
                  ZonaImagen { x: 0, y: 0, ancho: 0, alto: 10 }, ZonaImagen { x: u32::MAX, y: 0, ancho: 2, alto: 2 }] {
            assert_eq!(validar_zona(&z, &cap()), Err(ERR_INVALIDO.into()));
        }
    }
    #[test] fn validar_zonas_cuenta_y_etiquetas() {
        let z = |e: &str| ZonaEtiquetada { x: 0, y: 0, ancho: 10, alto: 10, etiqueta: e.into() };
        assert!(validar_zonas(vec![z("Menú")], &cap()).is_ok());
        assert!(validar_zonas(vec![], &cap()).is_err());
        assert!(validar_zonas((0..9).map(|_| z("x")).collect(), &cap()).is_err());
        assert!(validar_zonas(vec![z(&"a".repeat(41))], &cap()).is_err());
        assert!(validar_zonas(vec![z("dos\nlíneas")], &cap()).is_err());
    }
    #[test] fn misma_ventana_compara_id_y_rect() {
        let r = cap().ventana;
        assert!(misma_ventana((11, r), Some((11, r))));
        assert!(!misma_ventana((11, r), None));
        assert!(!misma_ventana((11, r), Some((12, r))));
        assert!(!misma_ventana((11, r), Some((11, Rect { ancho: r.ancho + 1, ..r }))));
    }
    #[test] fn captura_vigente_misma_foto_ventana_y_rect() {
        let c = cap();
        assert_eq!(captura_vigente(Some(&c), 7, Some((11, c.ventana)), 2_000), Ok(c));
    }
    #[test] fn captura_vigente_rechaza_foto_otra_vencida_movida_u_otra_ventana() {
        let c = cap();
        let vieja = Err(ERR_FOTO_VIEJA.to_string());
        assert_eq!(captura_vigente(None, 7, Some((11, c.ventana)), 2_000), vieja);
        assert_eq!(captura_vigente(Some(&c), 8, Some((11, c.ventana)), 2_000), vieja);
        assert_eq!(captura_vigente(Some(&c), 7, Some((11, c.ventana)), 1_000 + 300_000), vieja);
        assert_eq!(captura_vigente(Some(&c), 7, Some((11, Rect { x: 1901, ..c.ventana })), 2_000), vieja);
        assert_eq!(captura_vigente(Some(&c), 7, Some((12, c.ventana)), 2_000), vieja);
        assert_eq!(captura_vigente(Some(&c), 7, None, 2_000), vieja);
    }
}
