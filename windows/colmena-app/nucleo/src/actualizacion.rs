//! Ítem "Buscar actualización" de la bandeja: textos y transiciones, sin Tauri.

#[derive(Clone, Debug, PartialEq)]
pub enum EstadoItem {
    Inicial,
    Buscando,
    AlDia,
    Hay(String),
    Instalando,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Paso {
    Buscar,
    Instalar,
    Nada,
}

pub fn texto_item(estado: &EstadoItem) -> String {
    match estado {
        EstadoItem::Inicial => "Buscar actualización".into(),
        EstadoItem::Buscando => "Buscando…".into(),
        EstadoItem::AlDia => "Ya está al día".into(),
        EstadoItem::Instalando => "Instalando…".into(),
        EstadoItem::Hay(v) => match fecha_de_version(v) {
            Some(f) => format!("Actualizar a la versión del {f}"),
            None => format!("Actualizar a la versión {v}"),
        },
    }
}

pub fn item_habilitado(estado: &EstadoItem) -> bool {
    !matches!(estado, EstadoItem::Buscando | EstadoItem::Instalando)
}

pub fn al_tocar(estado: &EstadoItem) -> Paso {
    match estado {
        EstadoItem::Inicial | EstadoItem::AlDia => Paso::Buscar,
        EstadoItem::Hay(_) => Paso::Instalar,
        EstadoItem::Buscando | EstadoItem::Instalando => Paso::Nada,
    }
}

/// El chequeo silencioso del arranque no muestra "Ya está al día".
pub fn tras_buscar(nueva: Option<String>, silencioso: bool) -> EstadoItem {
    match nueva {
        Some(v) => EstadoItem::Hay(v),
        None if silencioso => EstadoItem::Inicial,
        None => EstadoItem::AlDia,
    }
}

fn numero(texto: &str, largo: std::ops::RangeInclusive<usize>) -> Option<u32> {
    if !largo.contains(&texto.len()) || !texto.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    texto.parse().ok()
}

/// `0.<AAAAMMDD>.<HHMM como entero>` (lo que arma scripts/armar-instalador.sh) → `DD/MM HH:MM`.
pub fn fecha_de_version(version: &str) -> Option<String> {
    let mut partes = version.split('.');
    let (Some("0"), Some(dia), Some(hora), None) = (partes.next(), partes.next(), partes.next(), partes.next()) else {
        return None;
    };
    numero(dia, 8..=8)?;
    let mes = numero(&dia[4..6], 2..=2)?;
    let d = numero(&dia[6..8], 2..=2)?;
    let hhmm = numero(hora, 1..=4)?;
    let (h, m) = (hhmm / 100, hhmm % 100);
    if !(1..=12).contains(&mes) || !(1..=31).contains(&d) || h > 23 || m > 59 {
        return None;
    }
    Some(format!("{d:02}/{mes:02} {h:02}:{m:02}"))
}

pub fn endpoint_actualizacion(origen: &str) -> String {
    format!("{}/api/app/actualizacion", origen.trim_end_matches('/'))
}

pub fn url_instalador(origen: &str) -> String {
    format!("{}/api/app/actualizacion/instalador", origen.trim_end_matches('/'))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fecha_legible_desde_la_version_del_armador() {
        assert_eq!(fecha_de_version("0.20261125.1430").as_deref(), Some("25/11 14:30"));
        assert_eq!(fecha_de_version("0.20260103.5").as_deref(), Some("03/01 00:05"));
        assert_eq!(fecha_de_version("0.20261231.2359").as_deref(), Some("31/12 23:59"));
    }

    #[test]
    fn fecha_none_si_no_es_version_del_armador() {
        for v in ["0.1.0", "", "1.20261125.1430", "0.2026112.1430", "0.20261325.1430", "0.20261100.1430",
                  "0.20261125.2400", "0.20261125.1460", "0.20261125.x", "0.20261125.1430.1", "0.2026112a.1430"] {
            assert_eq!(fecha_de_version(v), None, "{v}");
        }
    }

    #[test]
    fn textos_del_item() {
        assert_eq!(texto_item(&EstadoItem::Inicial), "Buscar actualización");
        assert_eq!(texto_item(&EstadoItem::Buscando), "Buscando…");
        assert_eq!(texto_item(&EstadoItem::AlDia), "Ya está al día");
        assert_eq!(texto_item(&EstadoItem::Instalando), "Instalando…");
        assert_eq!(
            texto_item(&EstadoItem::Hay("0.20261125.1430".into())),
            "Actualizar a la versión del 25/11 14:30"
        );
        assert_eq!(texto_item(&EstadoItem::Hay("0.2.0".into())), "Actualizar a la versión 0.2.0");
    }

    #[test]
    fn solo_se_toca_cuando_no_esta_trabajando() {
        assert!(item_habilitado(&EstadoItem::Inicial));
        assert!(item_habilitado(&EstadoItem::AlDia));
        assert!(item_habilitado(&EstadoItem::Hay("0.2.0".into())));
        assert!(!item_habilitado(&EstadoItem::Buscando));
        assert!(!item_habilitado(&EstadoItem::Instalando));
    }

    #[test]
    fn que_hace_al_tocar() {
        assert_eq!(al_tocar(&EstadoItem::Inicial), Paso::Buscar);
        assert_eq!(al_tocar(&EstadoItem::AlDia), Paso::Buscar);
        assert_eq!(al_tocar(&EstadoItem::Hay("0.2.0".into())), Paso::Instalar);
        assert_eq!(al_tocar(&EstadoItem::Buscando), Paso::Nada);
        assert_eq!(al_tocar(&EstadoItem::Instalando), Paso::Nada);
    }

    #[test]
    fn resultado_de_buscar() {
        assert_eq!(tras_buscar(Some("0.2.0".into()), true), EstadoItem::Hay("0.2.0".into()));
        assert_eq!(tras_buscar(Some("0.2.0".into()), false), EstadoItem::Hay("0.2.0".into()));
        assert_eq!(tras_buscar(None, false), EstadoItem::AlDia);
        assert_eq!(tras_buscar(None, true), EstadoItem::Inicial);
    }

    #[test]
    fn urls_desde_el_origen() {
        assert_eq!(
            endpoint_actualizacion("https://m.red.ts.net:8444"),
            "https://m.red.ts.net:8444/api/app/actualizacion"
        );
        assert_eq!(
            url_instalador("https://m.red.ts.net:8444"),
            "https://m.red.ts.net:8444/api/app/actualizacion/instalador"
        );
    }
}
