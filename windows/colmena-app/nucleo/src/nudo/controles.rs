use serde::Serialize;

use crate::posicion::Rect;

pub const TOPE_CONTROLES: usize = 150;
pub const PRESUPUESTO_MS: u64 = 1500;
pub const PRESUPUESTO_REINTENTO_MS: u64 = 3000;
pub const MIN_PRIMERA_VUELTA: usize = 5;
pub const NOMBRE_MAX: usize = 80;
const MISMA_FILA_PX: i64 = 8;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TipoControl {
    Boton,
    Enlace,
    Menu,
    ItemMenu,
    Pestana,
    Casilla,
    Radio,
    Campo,
    Combo,
    Lista,
    ItemLista,
    ItemArbol,
    Deslizador,
}

#[derive(Clone, Debug)]
pub struct Candidato {
    pub tipo_uia: i32,
    pub nombre: String,
    pub rect: Rect,
    pub fuera_de_pantalla: bool,
    pub habilitado: bool,
    pub es_password: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ControlListado {
    pub n: u32,
    pub tipo: TipoControl,
    pub nombre: String,
}

pub fn tipo_desde_uia(id: i32) -> Option<TipoControl> {
    Some(match id {
        50000 | 50031 => TipoControl::Boton,
        50002 => TipoControl::Casilla,
        50003 => TipoControl::Combo,
        50004 => TipoControl::Campo,
        50005 => TipoControl::Enlace,
        50007 => TipoControl::ItemLista,
        50008 => TipoControl::Lista,
        50009 => TipoControl::Menu,
        50011 => TipoControl::ItemMenu,
        50013 => TipoControl::Radio,
        50015 => TipoControl::Deslizador,
        50019 => TipoControl::Pestana,
        50024 => TipoControl::ItemArbol,
        _ => return None,
    })
}

pub fn limpiar_nombre(s: &str) -> String {
    let sin_control: String = s
        .chars()
        .map(|c| if c.is_control() { ' ' } else { c })
        .collect();
    sin_control
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .chars()
        .take(NOMBRE_MAX)
        .collect()
}

pub fn necesita_reintento(cantidad: usize) -> bool {
    cantidad < MIN_PRIMERA_VUELTA
}

fn intersecta(a: Rect, b: Rect) -> bool {
    let (ax, ay) = (i64::from(a.x), i64::from(a.y));
    let (bx, by) = (i64::from(b.x), i64::from(b.y));
    ax < bx + i64::from(b.ancho)
        && bx < ax + i64::from(a.ancho)
        && ay < by + i64::from(b.alto)
        && by < ay + i64::from(a.alto)
}

pub fn filtrar_y_numerar(
    cands: &[Candidato],
    ventana: Rect,
    tope: usize,
) -> Vec<(ControlListado, usize)> {
    let mut vistos: Vec<(i32, String, (i32, i32, u32, u32))> = Vec::new();
    let mut ok: Vec<(usize, TipoControl, String)> = Vec::new();
    for (i, c) in cands.iter().enumerate() {
        if c.es_password || !c.habilitado || c.fuera_de_pantalla {
            continue;
        }
        if c.rect.ancho == 0 || c.rect.alto == 0 || !intersecta(c.rect, ventana) {
            continue;
        }
        let Some(tipo) = tipo_desde_uia(c.tipo_uia) else {
            continue;
        };
        let nombre = limpiar_nombre(&c.nombre);
        if nombre.is_empty() {
            continue;
        }
        let clave = (c.tipo_uia, nombre.clone(), (c.rect.x, c.rect.y, c.rect.ancho, c.rect.alto));
        if vistos.contains(&clave) {
            continue;
        }
        vistos.push(clave);
        ok.push((i, tipo, nombre));
    }

    ok.sort_by_key(|(i, _, _)| (cands[*i].rect.y, cands[*i].rect.x));
    let mut ordenados: Vec<(usize, TipoControl, String)> = Vec::with_capacity(ok.len());
    let mut fila: Vec<(usize, TipoControl, String)> = Vec::new();
    let mut y0 = 0i64;
    for item in ok {
        let y = i64::from(cands[item.0].rect.y);
        if !fila.is_empty() && y - y0 > MISMA_FILA_PX {
            fila.sort_by_key(|(i, _, _)| cands[*i].rect.x);
            ordenados.append(&mut fila);
        }
        if fila.is_empty() {
            y0 = y;
        }
        fila.push(item);
    }
    fila.sort_by_key(|(i, _, _)| cands[*i].rect.x);
    ordenados.append(&mut fila);

    ordenados
        .into_iter()
        .take(tope)
        .enumerate()
        .map(|(k, (i, tipo, nombre))| {
            (ControlListado { n: (k + 1) as u32, tipo, nombre }, i)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(x: i32, y: i32) -> Rect {
        Rect { x, y, ancho: 50, alto: 20 }
    }
    fn cand(nombre: &str, x: i32, y: i32) -> Candidato {
        Candidato {
            tipo_uia: 50000,
            nombre: nombre.into(),
            rect: r(x, y),
            fuera_de_pantalla: false,
            habilitado: true,
            es_password: false,
        }
    }
    const V: Rect = Rect { x: 0, y: 0, ancho: 1000, alto: 800 };

    #[test]
    fn tipo_desde_uia_reconoce_interactivos() {
        assert_eq!(tipo_desde_uia(50000), Some(TipoControl::Boton));
        assert_eq!(tipo_desde_uia(50031), Some(TipoControl::Boton));
        assert_eq!(tipo_desde_uia(50005), Some(TipoControl::Enlace));
        assert_eq!(tipo_desde_uia(50004), Some(TipoControl::Campo));
        assert_eq!(tipo_desde_uia(50019), Some(TipoControl::Pestana));
        assert_eq!(tipo_desde_uia(50020), None);
    }

    #[test]
    fn tipos_serializan_en_snake_case() {
        assert_eq!(serde_json::to_string(&TipoControl::ItemMenu).unwrap(), "\"item_menu\"");
        assert_eq!(serde_json::to_string(&TipoControl::ItemArbol).unwrap(), "\"item_arbol\"");
    }

    #[test]
    fn filtra_password_deshabilitados_fuera_de_pantalla_y_vacios() {
        let mut p = cand("p", 10, 10);
        p.es_password = true;
        let mut d = cand("d", 10, 40);
        d.habilitado = false;
        let mut f = cand("f", 10, 70);
        f.fuera_de_pantalla = true;
        let mut z = cand("z", 10, 100);
        z.rect.ancho = 0;
        z.rect.alto = 0;
        let c = vec![cand("ok", 10, 130), p, d, f, z];
        assert_eq!(filtrar_y_numerar(&c, V, 150).len(), 1);
    }

    #[test]
    fn descarta_sin_nombre_y_fuera_de_la_ventana() {
        let c = vec![cand("  ", 10, 10), cand("lejos", 5000, 5000)];
        assert_eq!(filtrar_y_numerar(&c, V, 150).len(), 0);
    }

    #[test]
    fn descarta_tipos_no_interactivos() {
        let mut t = cand("texto", 10, 10);
        t.tipo_uia = 50020;
        assert_eq!(filtrar_y_numerar(&[t], V, 150).len(), 0);
    }

    #[test]
    fn descarta_duplicados_mismo_tipo_nombre_y_rect() {
        let c = vec![cand("a", 10, 10), cand("a", 10, 10)];
        assert_eq!(filtrar_y_numerar(&c, V, 150).len(), 1);
    }

    #[test]
    fn numera_en_orden_de_lectura() {
        let c = vec![cand("b", 200, 10), cand("a", 10, 12), cand("c", 10, 100)];
        let r = filtrar_y_numerar(&c, V, 150);
        let nombres: Vec<_> = r.iter().map(|(c, _)| (c.n, c.nombre.as_str())).collect();
        assert_eq!(nombres, vec![(1, "a"), (2, "b"), (3, "c")]);
        assert_eq!(r[0].1, 1);
    }

    #[test]
    fn respeta_tope_150() {
        let c: Vec<_> = (0..200).map(|i| cand(&format!("c{i}"), 10, i * 3)).collect();
        let r = filtrar_y_numerar(&c, V, 150);
        assert_eq!(r.len(), 150);
        assert_eq!(r[149].0.n, 150);
    }

    #[test]
    fn limpia_nombres() {
        assert_eq!(limpiar_nombre("  Guardar\u{7}\n "), "Guardar");
        assert_eq!(limpiar_nombre("a \t  b"), "a b");
        assert_eq!(limpiar_nombre(&"x".repeat(100)).chars().count(), 80);
        assert_eq!(limpiar_nombre(&"ñ".repeat(100)).chars().count(), 80);
    }

    #[test]
    fn reintenta_solo_con_pocos_controles() {
        assert!(necesita_reintento(0));
        assert!(necesita_reintento(4));
        assert!(!necesita_reintento(5));
    }
}
