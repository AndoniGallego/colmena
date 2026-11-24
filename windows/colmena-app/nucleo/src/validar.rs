use std::net::Ipv4Addr;
use std::str::FromStr;

use serde::{Deserialize, Serialize};
use url::Url;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Destino {
    pub host: String,
    pub usuario: String,
}

impl Destino {
    pub fn ssh(&self) -> String {
        format!("{}@{}", self.usuario, self.host)
    }
}

pub const ANCHO_MIN: u32 = 120;
pub const ANCHO_MAX: u32 = 800;
pub const ALTO_MIN: u32 = 40;
pub const ALTO_MAX: u32 = 1400;

fn origen_invalido() -> String {
    "origen inválido".into()
}

pub fn validar_origen(entrada: &str) -> Result<String, String> {
    let url = Url::parse(entrada.trim()).map_err(|_| origen_invalido())?;
    if url.scheme() != "https" {
        return Err(origen_invalido());
    }
    if !url.username().is_empty() || url.password().is_some() {
        return Err(origen_invalido());
    }
    if url.host().is_none() {
        return Err(origen_invalido());
    }
    if url.query().is_some() || url.fragment().is_some() {
        return Err(origen_invalido());
    }
    let path = url.path();
    if !path.is_empty() && path != "/" {
        return Err(origen_invalido());
    }
    Ok(url.origin().ascii_serialization())
}

pub fn mismo_origen(url: &str, origen: &str) -> bool {
    Url::parse(url)
        .map(|u| u.origin().ascii_serialization() == origen)
        .unwrap_or(false)
}

pub fn validar_tamano(ancho: u32, alto: u32) -> Result<(u32, u32), String> {
    if (ANCHO_MIN..=ANCHO_MAX).contains(&ancho) && (ALTO_MIN..=ALTO_MAX).contains(&alto) {
        Ok((ancho, alto))
    } else {
        Err("tamaño fuera de rango".into())
    }
}

pub fn validar_sesion(sid: &str) -> bool {
    if sid.is_empty() || sid.len() > 80 {
        return false;
    }
    sid.bytes().all(|b| {
        b.is_ascii_alphanumeric() || b == b'_' || b == b'.' || b == b':' || b == b'-'
    })
}

pub fn validar_aviso(tipo: &str) -> bool {
    tipo == "te-toca" || tipo == "termino"
}

pub fn url_entornos(origen: &str) -> String {
    format!("{origen}/entornos?app=windows")
}

pub fn url_colmena(origen: &str, sesion: Option<&str>) -> String {
    let sid = sesion.filter(|s| validar_sesion(s));
    match sid {
        Some(s) => format!("{origen}/?session={s}&app=windows"),
        None => format!("{origen}/?app=windows"),
    }
}

/// Id de un ítem de la Biblioteca: 32 hex minúsculas, igual que `ITEM_ID` del front.
pub fn validar_item_biblioteca(item: &str) -> bool {
    item.len() == 32 && item.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

/// URL de Colmena abierta en un ítem de la Biblioteca; `None` si el id no es válido.
pub fn url_biblioteca(origen: &str, item: &str) -> Option<String> {
    validar_item_biblioteca(item).then(|| format!("{origen}/?biblioteca={item}&app=windows"))
}

pub fn url_notch(origen: &str) -> String {
    format!("{origen}/notch")
}

/// Ventana "Reunión": la misma página del notch con la vista de reunión a tamaño completo.
pub fn url_reunion(origen: &str) -> String {
    format!("{}?vista=reunion", url_notch(origen))
}

pub fn es_url_local(url: &str) -> bool {
    let Ok(u) = Url::parse(url) else {
        return false;
    };
    match u.scheme() {
        "tauri" => u.host_str() == Some("localhost"),
        "http" => u.host_str() == Some("tauri.localhost"),
        _ => false,
    }
}

const MONITOR_NOMBRE_MAX: usize = 200;

pub fn validar_destino(host: &str, usuario: &str) -> Result<Destino, String> {
    let host = host.trim().to_ascii_lowercase();
    let usuario = usuario.trim();

    validar_host_destino(&host).map_err(|_| "dirección inválida".to_string())?;
    validar_usuario_destino(usuario).map_err(|_| "usuario inválido".to_string())?;

    Ok(Destino {
        host,
        usuario: usuario.to_string(),
    })
}

fn validar_host_destino(h: &str) -> Result<(), ()> {
    if h.is_empty() || h.len() > 253 {
        return Err(());
    }
    let bytes = h.as_bytes();
    if bytes[0] == b'-' {
        return Err(());
    }
    for &c in bytes {
        let ok = matches!(c, b'a'..=b'z' | b'0'..=b'9' | b'.' | b'-');
        if !ok {
            return Err(());
        }
    }
    let solo_digitos_y_puntos = bytes
        .iter()
        .all(|&c| c.is_ascii_digit() || c == b'.');
    if solo_digitos_y_puntos && Ipv4Addr::from_str(h).is_err() {
        return Err(());
    }
    Ok(())
}

fn validar_usuario_destino(u: &str) -> Result<(), ()> {
    let bytes = u.as_bytes();
    if bytes.is_empty() || bytes.len() > 32 {
        return Err(());
    }
    let first = bytes[0];
    if first != b'_' && !first.is_ascii_lowercase() {
        return Err(());
    }
    for &c in &bytes[1..] {
        let ok = matches!(c, b'a'..=b'z' | b'0'..=b'9' | b'_' | b'-');
        if !ok {
            return Err(());
        }
    }
    Ok(())
}

pub fn validar_monitor(entrada: &str) -> Option<String> {
    if entrada.is_empty() || entrada.len() > MONITOR_NOMBRE_MAX {
        return None;
    }
    if entrada.bytes().any(|b| b < 0x20 || b == 0x7f) {
        return None;
    }
    Some(entrada.to_string())
}

pub fn x_centrada(monitor_x: i32, monitor_ancho: u32, ancho: u32) -> i32 {
    let mx = i64::from(monitor_x);
    let mw = i64::from(monitor_ancho);
    let w = i64::from(ancho);
    if w > mw {
        monitor_x
    } else {
        (mx + (mw - w) / 2) as i32
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn origen_valido_se_normaliza() {
        assert_eq!(
            validar_origen(" https://pc.tail1234.ts.net:8444/ ").unwrap(),
            "https://pc.tail1234.ts.net:8444"
        );
    }

    #[test]
    fn origen_invalido_se_rechaza() {
        for m in [
            "",
            "http://pc.ts.net:8444",
            "https://pc.ts.net/app",
            "https://u:p@pc.ts.net",
            "https://pc.ts.net/?x=1",
            "javascript:alert(1)",
            "pc.ts.net",
        ] {
            assert!(validar_origen(m).is_err(), "{m}");
        }
    }

    #[test]
    fn mismo_origen_no_se_deja_engañar() {
        let o = "https://pc.ts.net:8444";
        assert!(mismo_origen("https://pc.ts.net:8444/notch", o));
        assert!(!mismo_origen("https://pc.ts.net:8443/notch", o));
        assert!(!mismo_origen("https://pc.ts.net:8444.evil.com/notch", o));
        assert!(!mismo_origen("https://pc.ts.net.evil.com:8444/", o));
        assert!(!mismo_origen("http://pc.ts.net:8444/", o));
        assert!(!mismo_origen("no es url", o));
    }

    #[test]
    fn tamano_en_rango() {
        assert_eq!(validar_tamano(120, 40), Ok((120, 40)));
        assert_eq!(validar_tamano(800, 1400), Ok((800, 1400)));
        assert!(validar_tamano(119, 40).is_err());
        assert!(validar_tamano(120, 1401).is_err());
    }

    #[test]
    fn validar_sesion_como_el_service_worker() {
        assert!(validar_sesion("abc-1_2.3:4"));
        for m in ["", "../x", "a b", "a/b", "ñ", &"x".repeat(81)] {
            assert!(!validar_sesion(m), "{m}");
        }
    }

    #[test]
    fn urls_de_las_ventanas() {
        let o = "https://pc.ts.net:8444";
        assert_eq!(url_colmena(o, None), "https://pc.ts.net:8444/?app=windows");
        assert_eq!(
            url_colmena(o, Some("s:1")),
            "https://pc.ts.net:8444/?session=s:1&app=windows"
        );
        assert_eq!(url_colmena(o, Some("../x")), "https://pc.ts.net:8444/?app=windows");
        assert_eq!(url_notch(o), "https://pc.ts.net:8444/notch");
        assert_eq!(url_reunion(o), "https://pc.ts.net:8444/notch?vista=reunion");
    }

    #[test]
    fn url_de_un_item_de_la_biblioteca() {
        let o = "https://pc.ts.net:8444";
        let id = "0123456789abcdef0123456789abcdef";
        assert_eq!(
            url_biblioteca(o, id).as_deref(),
            Some("https://pc.ts.net:8444/?biblioteca=0123456789abcdef0123456789abcdef&app=windows")
        );
    }

    #[test]
    fn un_item_invalido_no_arma_url() {
        let o = "https://pc.ts.net:8444";
        let largo = "a".repeat(33);
        for m in [
            "",
            "abc",
            "0123456789ABCDEF0123456789ABCDEF",
            "0123456789abcdef0123456789abcde&",
            "../0123456789abcdef0123456789ab",
            largo.as_str(),
        ] {
            assert_eq!(url_biblioteca(o, m), None, "{m}");
        }
    }

    #[test]
    fn es_url_local_solo_origen_y_config() {
        assert!(es_url_local("tauri://localhost/origin.html"));
        assert!(es_url_local("http://tauri.localhost/origin.html"));
        assert!(!es_url_local("http://tauri.localhost.evil.com/"));
        assert!(!es_url_local("https://tauri.localhost/"));
        assert!(!es_url_local("http://evil.localhost/"));
    }

    #[test]
    fn avisos_y_centrado() {
        assert!(validar_aviso("te-toca") && validar_aviso("termino") && !validar_aviso("mr"));
        assert_eq!(x_centrada(0, 1920, 400), 760);
        assert_eq!(x_centrada(-1920, 1920, 400), -1160);
    }

    #[test]
    fn destino_valido() {
        let d = |h: &str, u: &str| Destino {
            host: h.into(),
            usuario: u.into(),
        };
        assert_eq!(
            validar_destino("192.168.1.50", "usuario"),
            Ok(d("192.168.1.50", "usuario"))
        );
        assert_eq!(
            validar_destino(" Notebook.Local ", " cc "),
            Ok(d("notebook.local", "cc"))
        );
        assert!(validar_destino("notebook", "usuario_2").is_ok());
        let host_253 = "a".repeat(253);
        assert!(validar_destino(&host_253, "cc").is_ok());
        let user_32 = "a".repeat(32);
        assert!(validar_destino("192.168.1.50", &user_32).is_ok());
    }

    #[test]
    fn destino_invalido() {
        let largo = "a".repeat(254);
        for h in [
            "",
            "-host",
            "-a",
            "-oProxyCommand=calc",
            "a b",
            "host;calc",
            "999.1.1.1",
            "1.2.3",
            "ñandú",
            largo.as_str(),
            "cc@host",
            "host:22",
        ] {
            assert_eq!(
                validar_destino(h, "cc"),
                Err("dirección inválida".into()),
                "{h}"
            );
        }
        let largo = "a".repeat(33);
        for u in ["", "-cc", "Cc", "1cc", "c c", "cc@x", largo.as_str()] {
            assert_eq!(
                validar_destino("192.168.1.50", u),
                Err("usuario inválido".into()),
                "{u}"
            );
        }
    }
}
