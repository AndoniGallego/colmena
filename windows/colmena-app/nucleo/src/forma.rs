//! Rectángulo redondeado en coordenadas físicas para la región de la ventana notch (Windows).

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegionFisica {
    pub izquierda: i32,
    pub arriba: i32,
    pub derecha: i32,
    pub abajo: i32,
    /// Ancho y alto del elipse de esquina para `CreateRoundRectRgn` (mismo valor en ambos ejes).
    pub diametro_esquina: i32,
}

fn err_invalido() -> String {
    "forma inválida".into()
}

/// Convierte la pastilla en coordenadas lógicas (CSS px) a un rect físico inclusivo que coincide exactamente
/// con el área de la pastilla en px físicos: borde izquierdo/arriba `floor(log * escala)`, borde derecho/abajo
/// exclusivos `ceil((log + tamaño) * escala)` menos un px (inclusivo), recortado al área cliente.
///
/// `ancho_ventana_fisico` y `alto_ventana_fisico` son el tamaño interior en píxeles físicos.
pub fn region_desde_pastilla(
    x: f64,
    y: f64,
    ancho: f64,
    alto: f64,
    radio_css: f64,
    factor_escala: f64,
    ancho_ventana_fisico: u32,
    alto_ventana_fisico: u32,
) -> Result<RegionFisica, String> {
    if !(x.is_finite()
        && y.is_finite()
        && ancho.is_finite()
        && alto.is_finite()
        && radio_css.is_finite()
        && factor_escala.is_finite())
    {
        return Err(err_invalido());
    }
    if ancho <= 0.0 || alto <= 0.0 || factor_escala <= 0.0 {
        return Err(err_invalido());
    }
    if radio_css < 0.0 {
        return Err(err_invalido());
    }
    if ancho_ventana_fisico == 0 || alto_ventana_fisico == 0 {
        return Err(err_invalido());
    }

    let mut x = x;
    let mut y = y;
    let mut ancho = ancho;
    let mut alto = alto;
    if x < 0.0 {
        ancho += x;
        x = 0.0;
    }
    if y < 0.0 {
        alto += y;
        y = 0.0;
    }
    if ancho <= 0.0 || alto <= 0.0 {
        return Err(err_invalido());
    }

    // Evitar valores enormes que desborden al escalar.
    const MAX_LOG: f64 = 1.0e7;
    if x > MAX_LOG
        || y > MAX_LOG
        || ancho > MAX_LOG
        || alto > MAX_LOG
        || radio_css > MAX_LOG
        || factor_escala > MAX_LOG
    {
        return Err(err_invalido());
    }

    let s = factor_escala;
    let izq_f = x * s;
    let arr_f = y * s;
    let der_excl_f = (x + ancho) * s;
    let ab_excl_f = (y + alto) * s;

    let izquierda = izq_f.floor() as i64;
    let arriba = arr_f.floor() as i64;
    let derecha_excl = der_excl_f.ceil() as i64;
    let abajo_excl = ab_excl_f.ceil() as i64;

    let max_x = i64::from(ancho_ventana_fisico.saturating_sub(1));
    let max_y = i64::from(alto_ventana_fisico.saturating_sub(1));

    let izquierda = izquierda.clamp(0, max_x);
    let arriba = arriba.clamp(0, max_y);
    let derecha_incl = (derecha_excl - 1).clamp(0, max_x);
    let abajo_incl = (abajo_excl - 1).clamp(0, max_y);

    let izquierda = izquierda.min(derecha_incl);
    let arriba = arriba.min(abajo_incl);

    let ancho_px = (derecha_incl - izquierda + 1).max(1);
    let alto_px = (abajo_incl - arriba + 1).max(1);

    let diam_f = 2.0 * radio_css * s;
    if !diam_f.is_finite() {
        return Err(err_invalido());
    }
    let mut diametro = diam_f.ceil() as i64;
    diametro = diametro.max(0);
    let max_d = ancho_px.min(alto_px);
    diametro = diametro.min(max_d);

    Ok(RegionFisica {
        izquierda: i32::try_from(izquierda).map_err(|_| err_invalido())?,
        arriba: i32::try_from(arriba).map_err(|_| err_invalido())?,
        derecha: i32::try_from(derecha_incl).map_err(|_| err_invalido())?,
        abajo: i32::try_from(abajo_incl).map_err(|_| err_invalido())?,
        diametro_esquina: i32::try_from(diametro).map_err(|_| err_invalido())?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escala_1_rect_interno() {
        let r = region_desde_pastilla(100.0, 10.0, 200.0, 50.0, 22.0, 1.0, 800, 600).unwrap();
        assert_eq!(r.izquierda, 100);
        assert_eq!(r.arriba, 10);
        assert_eq!(r.derecha, 299);
        assert_eq!(r.abajo, 59);
        assert_eq!(r.diametro_esquina, 44);
    }

    #[test]
    fn escala_125() {
        let r = region_desde_pastilla(80.0, 8.0, 160.0, 40.0, 20.0, 1.25, 1000, 800).unwrap();
        assert_eq!(r.izquierda, 100);
        assert_eq!(r.arriba, 10);
        assert_eq!(r.derecha, 299);
        assert_eq!(r.abajo, 59);
        assert_eq!(r.diametro_esquina, 50);
    }

    #[test]
    fn escala_15() {
        let r = region_desde_pastilla(200.0 / 3.0, 20.0 / 3.0, 400.0 / 3.0, 100.0 / 3.0, 44.0 / 3.0, 1.5, 900, 700).unwrap();
        assert_eq!(r.izquierda, 100);
        assert_eq!(r.arriba, 10);
        assert_eq!(r.derecha, 299);
        assert_eq!(r.abajo, 59);
        assert_eq!(r.diametro_esquina, 44);
    }

    #[test]
    fn se_recorta_fuera_de_la_ventana() {
        let r = region_desde_pastilla(700.0, 0.0, 200.0, 50.0, 10.0, 1.0, 800, 100).unwrap();
        assert_eq!(r.izquierda, 700);
        assert_eq!(r.arriba, 0);
        assert_eq!(r.derecha, 799);
        assert_eq!(r.abajo, 49);
        assert_eq!(r.diametro_esquina, 20);
    }

    #[test]
    fn nan_y_negativos_err() {
        assert!(region_desde_pastilla(f64::NAN, 0.0, 10.0, 10.0, 1.0, 1.0, 100, 100).is_err());
        assert!(region_desde_pastilla(0.0, 0.0, -1.0, 10.0, 1.0, 1.0, 100, 100).is_err());
        assert!(region_desde_pastilla(0.0, 0.0, 10.0, 10.0, -1.0, 1.0, 100, 100).is_err());
        assert!(region_desde_pastilla(0.0, 0.0, 10.0, 10.0, 1.0, 0.0, 100, 100).is_err());
    }

    #[test]
    fn recorta_x_negativo_antes_de_escalar() {
        let r = region_desde_pastilla(-1.0, 10.0, 200.0, 50.0, 22.0, 1.0, 800, 600).unwrap();
        assert_eq!(r.izquierda, 0);
        assert_eq!(r.arriba, 10);
    }

    #[test]
    fn recorta_y_negativo_antes_de_escalar() {
        let r = region_desde_pastilla(100.0, -1.0, 200.0, 50.0, 22.0, 1.0, 800, 600).unwrap();
        assert_eq!(r.izquierda, 100);
        assert_eq!(r.arriba, 0);
    }

    #[test]
    fn y_menos_uno_misma_forma_que_y_cero_alto_menos_uno() {
        let a = region_desde_pastilla(0.0, -1.0, 10.0, 10.0, 1.0, 1.0, 100, 100).unwrap();
        let b = region_desde_pastilla(0.0, 0.0, 10.0, 9.0, 1.0, 1.0, 100, 100).unwrap();
        assert_eq!(a, b);
    }
}
