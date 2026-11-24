use serde::Deserialize;

use super::{ERR_INVALIDO, ERR_SIN_CONTROL};

pub const TEXTO_MAX: usize = 120;
pub const ETIQUETA_MAX: usize = 40;
pub const MARCAS_MAX: usize = 8;
pub const SESION_MAX: usize = 60;
pub const ESPERA_DEFAULT_S: u32 = 120;
pub const ESPERA_MAX_S: u32 = 600;
pub const FOTO_VENCE_MS: u64 = 300_000;

#[derive(Deserialize, Clone, Debug, PartialEq)]
pub struct Marca {
    pub n: u32,
    pub etiqueta: String,
}

pub fn validar_texto(t: &str, max: usize) -> Result<String, String> {
    if t.chars().any(|c| c.is_control()) {
        return Err(ERR_INVALIDO.into());
    }
    let t = t.trim();
    if t.is_empty() || t.chars().count() > max {
        return Err(ERR_INVALIDO.into());
    }
    Ok(t.to_string())
}

pub fn validar_marcas(m: Vec<Marca>) -> Result<Vec<Marca>, String> {
    if m.is_empty() || m.len() > MARCAS_MAX {
        return Err(ERR_INVALIDO.into());
    }
    let mut vistos = std::collections::HashSet::new();
    if m.iter().any(|x| x.n == 0 || !vistos.insert(x.n)) {
        return Err(ERR_INVALIDO.into());
    }
    m.into_iter()
        .map(|x| Ok(Marca { n: x.n, etiqueta: validar_texto(&x.etiqueta, ETIQUETA_MAX)? }))
        .collect()
}

pub fn validar_n(n: u32, cantidad: usize) -> Result<usize, String> {
    if n == 0 || n as usize > cantidad {
        return Err(ERR_SIN_CONTROL.into());
    }
    Ok(n as usize - 1)
}

pub fn validar_espera(s: Option<u32>) -> Result<Option<u32>, String> {
    match s {
        None => Ok(None),
        Some(0) => Ok(Some(ESPERA_DEFAULT_S)),
        Some(v) if v > ESPERA_MAX_S => Err(ERR_INVALIDO.into()),
        Some(v) => Ok(Some(v)),
    }
}

pub fn foto_vigente(creada_ms: u64, ahora_ms: u64) -> bool {
    ahora_ms.saturating_sub(creada_ms) < FOTO_VENCE_MS
}

#[cfg(test)]
mod tests {
    use super::*;

    fn marcas(k: u32) -> Vec<Marca> {
        (1..=k).map(|n| Marca { n, etiqueta: "x".into() }).collect()
    }

    #[test] fn texto_valido_se_recorta() { assert_eq!(validar_texto("  Tocá Guardar ", 120), Ok("Tocá Guardar".into())); }
    #[test] fn texto_con_control_se_rechaza() { assert_eq!(validar_texto("a\nb", 120), Err("invalido".into())); }
    #[test] fn control_en_los_bordes_se_rechaza() {
        assert_eq!(validar_texto("a\n", 120), Err("invalido".into()));
        assert_eq!(validar_texto("\ta", 120), Err("invalido".into()));
        assert_eq!(validar_texto("Tocá \"Guardar\"\n", 120), Err("invalido".into()));
    }
    #[test] fn marcas_con_n_cero_o_repetido_se_rechazan() {
        let m = |n| Marca { n, etiqueta: "x".into() };
        assert!(validar_marcas(vec![m(0)]).is_err());
        assert!(validar_marcas(vec![m(1), m(1)]).is_err());
        assert!(validar_marcas(vec![m(1), m(2)]).is_ok());
    }
    #[test] fn texto_vacio_o_largo_se_rechaza() {
        assert!(validar_texto("   ", 120).is_err());
        assert!(validar_texto(&"á".repeat(121), 120).is_err());
        assert!(validar_texto(&"á".repeat(120), 120).is_ok());
    }
    #[test] fn marcas_hasta_8() {
        assert!(validar_marcas(marcas(9)).is_err());
        assert!(validar_marcas(marcas(8)).is_ok());
        assert!(validar_marcas(vec![]).is_err());
    }
    #[test] fn n_fuera_de_rango_es_sin_control() {
        assert_eq!(validar_n(0, 10), Err("sin_control".into()));
        assert_eq!(validar_n(11, 10), Err("sin_control".into()));
        assert_eq!(validar_n(10, 10), Ok(9));
    }
    #[test] fn espera_default_y_tope() {
        assert_eq!(validar_espera(None), Ok(None));
        assert_eq!(validar_espera(Some(0)), Ok(Some(120)));
        assert!(validar_espera(Some(601)).is_err());
        assert_eq!(validar_espera(Some(30)), Ok(Some(30)));
    }
    #[test] fn foto_vence_a_los_5_minutos() { assert!(foto_vigente(0, 299_999)); assert!(!foto_vigente(0, 300_000)); }
}
