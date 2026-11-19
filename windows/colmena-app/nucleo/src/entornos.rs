use std::collections::{BTreeMap, HashSet};
use std::io;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use url::Url;

use crate::validar::Destino;

pub const PUERTOS_BLOQUEADOS: [u16; 6] = [8770, 8771, 2375, 2376, 2377, 7437];
pub const PUERTO_MIN: u16 = 1024;
pub const MAX_PUERTOS: usize = 30;

pub fn validar_nombre(nombre: &str) -> bool {
    let b = nombre.as_bytes();
    if b.is_empty() || b.len() > 64 {
        return false;
    }
    b.iter().all(|&c| matches!(c, b'a'..=b'z' | b'0'..=b'9' | b'_' | b'-'))
}

pub fn validar_pedido(
    nombre: &str,
    puertos: &[u16],
    principal: u16,
    origen: Option<&str>,
) -> Result<Vec<u16>, String> {
    if !validar_nombre(nombre) {
        return Err("nombre inválido".into());
    }
    if !(1..=MAX_PUERTOS).contains(&puertos.len()) {
        return Err("hacen falta entre 1 y 30 puertos".into());
    }
    for &p in puertos {
        if !(PUERTO_MIN..=65535).contains(&p) {
            return Err(format!("el puerto {p} está fuera de rango"));
        }
    }
    let mut vistos = HashSet::new();
    for &p in puertos {
        if !vistos.insert(p) {
            return Err(format!("el puerto {p} está repetido"));
        }
    }
    let puerto_origen = match origen {
        None => {
            return Err("falta la dirección de Colmena en la app".into());
        }
        Some(o) => {
            let url = Url::parse(o).map_err(|_| "falta la dirección de Colmena en la app".to_string())?;
            match url.port_or_known_default() {
                Some(p) => p,
                None => return Err("falta la dirección de Colmena en la app".into()),
            }
        }
    };
    let mut bloqueados: Vec<u16> = PUERTOS_BLOQUEADOS.to_vec();
    bloqueados.push(puerto_origen);
    bloqueados.sort_unstable();
    bloqueados.dedup();
    for &p in puertos {
        if bloqueados.binary_search(&p).is_ok() {
            return Err(format!("el puerto {p} está bloqueado por seguridad"));
        }
    }
    if !puertos.contains(&principal) {
        return Err("el puerto principal no está en la lista".into());
    }
    let mut ordenados: Vec<u16> = puertos.to_vec();
    ordenados.sort_unstable();
    Ok(ordenados)
}

pub fn argv_ssh(destino: &Destino, puertos: &[u16]) -> Vec<String> {
    let mut args: Vec<String> = vec![
        "-N".into(),
        "-T".into(),
        "-o".into(),
        "BatchMode=yes".into(),
        "-o".into(),
        "ExitOnForwardFailure=yes".into(),
        "-o".into(),
        "StrictHostKeyChecking=yes".into(),
        "-o".into(),
        "ServerAliveInterval=30".into(),
        "-o".into(),
        "ServerAliveCountMax=3".into(),
        "-o".into(),
        "ConnectTimeout=8".into(),
    ];
    for &p in puertos {
        args.push("-L".into());
        args.push(format!("127.0.0.1:{p}:localhost:{p}"));
    }
    args.push(destino.ssh());
    args
}

pub fn ruta_ssh(system_root: &str) -> String {
    let root = system_root.trim_end_matches('\\');
    format!("{root}\\System32\\OpenSSH\\ssh.exe")
}

pub fn url_principal(principal: u16) -> String {
    format!("http://localhost:{principal}/")
}

#[derive(Debug, PartialEq)]
pub enum Apertura {
    Abrir,
    SoloNavegador,
    Reabrir,
}

pub fn decidir_apertura(abiertos: Option<&[u16]>, pedidos: &[u16]) -> Apertura {
    let Some(abiertos) = abiertos else {
        return Apertura::Abrir;
    };
    let mut a: Vec<u16> = abiertos.to_vec();
    a.sort_unstable();
    let mut p: Vec<u16> = pedidos.to_vec();
    p.sort_unstable();
    if a == p {
        Apertura::SoloNavegador
    } else {
        Apertura::Reabrir
    }
}

pub fn conflicto_con_tuneles(
    nombre: &str,
    puertos: &[u16],
    otros: &[(String, Vec<u16>)],
) -> Option<String> {
    for (otro_nombre, otro_puertos) in otros {
        if otro_nombre == nombre {
            continue;
        }
        for &p in puertos {
            if otro_puertos.contains(&p) {
                return Some(format!("el puerto {p} ya lo usa el túnel de {otro_nombre}"));
            }
        }
    }
    None
}

pub fn mensaje_ocupados(ocupados: &[u16]) -> String {
    match ocupados.len() {
        0 => String::new(),
        1 => format!("el puerto {} ya está en uso en esta PC", ocupados[0]),
        _ => {
            let lista = ocupados
                .iter()
                .map(|p| p.to_string())
                .collect::<Vec<_>>()
                .join(", ");
            format!("los puertos {lista} ya están en uso en esta PC")
        }
    }
}

fn ipv6_loopback_addr_in_use(p: u16) -> bool {
    match TcpListener::bind((std::net::Ipv6Addr::LOCALHOST, p)) {
        Ok(_) => false,
        Err(e) => e.kind() == io::ErrorKind::AddrInUse,
    }
}

pub fn puertos_ocupados(puertos: &[u16]) -> Vec<u16> {
    let mut out = Vec::new();
    for &p in puertos {
        if TcpListener::bind(("127.0.0.1", p)).is_err() || ipv6_loopback_addr_in_use(p) {
            out.push(p);
        }
    }
    out
}

pub fn esperar_puerto(
    puerto: u16,
    limite: Duration,
    paso: Duration,
    mut terminado: impl FnMut() -> Option<String>,
) -> Result<(), String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], puerto));
    let inicio = Instant::now();
    loop {
        if let Some(e) = terminado() {
            return Err(e);
        }
        match TcpStream::connect_timeout(&addr, paso) {
            Ok(_) => return Ok(()),
            Err(e) if matches!(e.kind(), io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock) => {}
            Err(_) => {}
        }
        if inicio.elapsed() >= limite {
            return Err("la notebook no respondió a tiempo".into());
        }
        thread::sleep(paso);
    }
}

pub fn ultima_linea(stderr: &str) -> String {
    let mut mejor = None::<String>;
    for line in stderr.split('\n') {
        let s = line.trim_end_matches('\r').trim();
        if !s.is_empty() {
            mejor = Some(s.to_string());
        }
    }
    let Some(s) = mejor else {
        return String::new();
    };
    let mut out = String::new();
    for ch in s.chars().take(300) {
        out.push(ch);
    }
    out
}

#[derive(Serialize, Clone, Copy, Debug, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum FaseTunel {
    Abierto,
    Error,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct EstadoTunel {
    pub estado: FaseTunel,
    pub puertos: Vec<u16>,
    pub error: Option<String>,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct EstadoEntornos {
    pub notebook: String,
    pub tuneles: BTreeMap<String, EstadoTunel>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::validar::url_entornos;

    use std::time::Duration;

    const O: Option<&str> = Some("https://pc.ts.net:8444");

    fn cc() -> Destino {
        Destino {
            host: "192.168.1.50".into(),
            usuario: "usuario".into(),
        }
    }

    #[test]
    fn nombres_validos_e_invalidos() {
        for n in ["ps9", "gastos-casa", "a_b"] {
            assert!(validar_nombre(n), "{n}");
        }
        let largo = "a".repeat(65);
        for n in ["", "PS9", "a b", "../x", "ñ", largo.as_str()] {
            assert!(!validar_nombre(n), "{n}");
        }
    }

    #[test]
    fn pedido_valido_se_ordena() {
        assert_eq!(
            validar_pedido("ps9", &[8093, 8080, 8092], 8080, O),
            Ok(vec![8080, 8092, 8093])
        );
    }

    #[test]
    fn origen_fail_closed() {
        let e = Err::<Vec<u16>, String>("falta la dirección de Colmena en la app".into());
        assert_eq!(validar_pedido("ps9", &[8080], 8080, None), e);
        assert_eq!(
            validar_pedido("ps9", &[8080], 8080, Some("basura")),
            e.clone()
        );
        assert_eq!(validar_pedido("ps9", &[8080], 8080, O), Ok(vec![8080]));
    }

    #[test]
    fn nombre_limite_64_caracteres() {
        let ok64 = "a".repeat(64);
        assert!(validar_nombre(&ok64));
        let bad65 = "a".repeat(65);
        assert!(!validar_nombre(&bad65));
    }

    #[test]
    fn cantidad_puertos_30_ok_31_mal() {
        let treinta: Vec<u16> = (2000..2030).collect();
        assert_eq!(treinta.len(), 30);
        assert!(validar_pedido("x", &treinta, 2000, O).is_ok());
        let treinta_y_uno: Vec<u16> = (2000..2031).collect();
        assert_eq!(treinta_y_uno.len(), 31);
        assert_eq!(
            validar_pedido("x", &treinta_y_uno, 2000, O),
            Err("hacen falta entre 1 y 30 puertos".into())
        );
    }

    #[test]
    fn rango_puerto_bordes() {
        assert_eq!(
            validar_pedido("x", &[1023], 1023, O),
            Err("el puerto 1023 está fuera de rango".into())
        );
        assert_eq!(validar_pedido("x", &[1024], 1024, O), Ok(vec![1024]));
        assert_eq!(
            validar_pedido("x", &[65535], 65535, O),
            Ok(vec![65535])
        );
    }

    #[test]
    fn orden_corte_repetido_vs_fuera_rango() {
        assert_eq!(
            validar_pedido("x", &[80, 80], 80, O),
            Err("el puerto 80 está fuera de rango".into())
        );
    }

    #[test]
    fn pedido_invalido() {
        let muchos: Vec<u16> = (2000..2031).collect();
        let e = |s: &str| Err::<Vec<u16>, String>(s.into());
        assert_eq!(validar_pedido("PS9", &[8080], 8080, O), e("nombre inválido"));
        assert_eq!(validar_pedido("ps9", &[], 8080, O), e("hacen falta entre 1 y 30 puertos"));
        assert_eq!(
            validar_pedido("ps9", &muchos, 2000, O),
            e("hacen falta entre 1 y 30 puertos")
        );
        assert_eq!(
            validar_pedido("ps9", &[80, 8080], 8080, O),
            e("el puerto 80 está fuera de rango")
        );
        assert_eq!(
            validar_pedido("ps9", &[8080, 8080], 8080, O),
            e("el puerto 8080 está repetido")
        );
        assert_eq!(
            validar_pedido("ps9", &[8080], 9000, O),
            e("el puerto principal no está en la lista")
        );
    }

    #[test]
    fn puertos_bloqueados_incluido_el_origen() {
        assert_eq!(PUERTOS_BLOQUEADOS, [8770, 8771, 2375, 2376, 2377, 7437]);
        for p in PUERTOS_BLOQUEADOS {
            assert_eq!(
                validar_pedido("x", &[8080, p], 8080, O),
                Err(format!("el puerto {p} está bloqueado por seguridad"))
            );
        }
        assert_eq!(
            validar_pedido("x", &[8444], 8444, O),
            Err("el puerto 8444 está bloqueado por seguridad".into())
        );
        assert!(validar_pedido("x", &[8444], 8444, Some("https://otra.ts.net:9443")).is_ok());
    }

    #[test]
    fn argv_de_ssh_exacto() {
        assert_eq!(
            argv_ssh(&cc(), &[8080, 8092]),
            [
                "-N",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "ConnectTimeout=8",
                "-L",
                "127.0.0.1:8080:localhost:8080",
                "-L",
                "127.0.0.1:8092:localhost:8092",
                "usuario@192.168.1.50",
            ]
            .map(String::from)
            .to_vec()
        );
        assert_eq!(
            ruta_ssh("C:\\Windows"),
            "C:\\Windows\\System32\\OpenSSH\\ssh.exe"
        );
        assert_eq!(
            ruta_ssh("C:\\Windows\\\\"),
            "C:\\Windows\\System32\\OpenSSH\\ssh.exe"
        );
    }

    #[test]
    fn urls_de_entornos() {
        assert_eq!(url_principal(8080), "http://localhost:8080/");
        assert_eq!(
            url_entornos("https://pc.ts.net:8444"),
            "https://pc.ts.net:8444/entornos?app=windows"
        );
    }

    #[test]
    fn decide_si_reabrir() {
        assert_eq!(decidir_apertura(None, &[8080]), Apertura::Abrir);
        assert_eq!(
            decidir_apertura(Some(&[8080, 8092]), &[8092, 8080]),
            Apertura::SoloNavegador
        );
        assert_eq!(
            decidir_apertura(Some(&[8080]), &[8080, 8092]),
            Apertura::Reabrir
        );
    }

    #[test]
    fn conflicto_con_otro_tunel() {
        let otros = vec![("ps9".to_string(), vec![8080, 3306])];
        assert_eq!(
            conflicto_con_tuneles("tienda-a", &[3306, 8088], &otros),
            Some("el puerto 3306 ya lo usa el túnel de ps9".into())
        );
        assert_eq!(conflicto_con_tuneles("ps9", &[8080], &otros), None);
    }

    #[test]
    fn mensajes_de_puertos_ocupados() {
        assert_eq!(
            mensaje_ocupados(&[8080]),
            "el puerto 8080 ya está en uso en esta PC"
        );
        assert_eq!(
            mensaje_ocupados(&[8080, 3306]),
            "los puertos 8080, 3306 ya están en uso en esta PC"
        );
        assert_eq!(mensaje_ocupados(&[]), "");
    }

    #[test]
    fn detecta_puertos_ocupados_en_127() {
        let tomado = TcpListener::bind("127.0.0.1:0").unwrap();
        let p = tomado.local_addr().unwrap().port();
        let q = {
            let l = TcpListener::bind("127.0.0.1:0").unwrap();
            l.local_addr().unwrap().port()
        };
        assert_eq!(puertos_ocupados(&[p, q]), vec![p]);
    }

    #[test]
    fn detecta_puerto_ocupado_en_loopback_ipv6() {
        // [::1] puede no estar disponible en todos los entornos de CI.
        let tomado_v6 = match TcpListener::bind((std::net::Ipv6Addr::LOCALHOST, 0)) {
            Ok(l) => l,
            Err(_) => return,
        };
        let p = tomado_v6.local_addr().unwrap().port();
        let libre = {
            let l = TcpListener::bind("127.0.0.1:0").unwrap();
            l.local_addr().unwrap().port()
        };
        assert_eq!(puertos_ocupados(&[p, libre]), vec![p]);
    }

    #[test]
    fn esperar_puerto_corta_si_ssh_termino() {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let abierto = l.local_addr().unwrap().port();
        let libre = {
            let x = TcpListener::bind("127.0.0.1:0").unwrap();
            x.local_addr().unwrap().port()
        };
        let z = Duration::ZERO;
        let paso = Duration::from_millis(50);
        assert_eq!(esperar_puerto(abierto, z, paso, || None), Ok(()));
        assert_eq!(
            esperar_puerto(libre, z, paso, || Some("Permission denied (publickey).".into())),
            Err("Permission denied (publickey).".into())
        );
        assert_eq!(
            esperar_puerto(libre, z, paso, || None),
            Err("la notebook no respondió a tiempo".into())
        );
    }

    #[test]
    fn esperar_puerto_chequea_terminado_antes_de_conexion() {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let puerto = l.local_addr().unwrap().port();
        let z = Duration::ZERO;
        let paso = Duration::from_millis(50);
        assert_eq!(
            esperar_puerto(puerto, z, paso, || Some("ssh cayó".into())),
            Err("ssh cayó".into())
        );
    }

    #[test]
    fn ultima_linea_de_stderr() {
        assert_eq!(
            ultima_linea("Warning: algo\n\nusuario@192.168.1.50: Permission denied (publickey).\r\n\n"),
            "usuario@192.168.1.50: Permission denied (publickey)."
        );
        assert_eq!(ultima_linea(""), "");
        assert_eq!(ultima_linea(&"é".repeat(400)).chars().count(), 300);
    }

    #[test]
    fn estado_se_serializa_para_la_web() {
        let e = EstadoTunel {
            estado: FaseTunel::Abierto,
            puertos: vec![8080],
            error: None,
        };
        assert_eq!(
            serde_json::to_value(&e).unwrap(),
            serde_json::json!({"estado": "abierto", "puertos": [8080], "error": null})
        );
    }
}
