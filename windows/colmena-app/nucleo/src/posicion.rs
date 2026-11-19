use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Ancla {
    pub x: i32,
    pub y: i32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub ancho: u32,
    pub alto: u32,
}

pub fn monitor_de(ancla: Ancla, monitores: &[Rect]) -> Option<usize> {
    let px = i64::from(ancla.x);
    let py = i64::from(ancla.y);
    monitores.iter().position(|m| {
        let mx = i64::from(m.x);
        let my = i64::from(m.y);
        let mw = i64::from(m.ancho);
        let mh = i64::from(m.alto);
        px >= mx && px < mx + mw && py >= my && py < my + mh
    })
}

pub fn encajar(ancla: Ancla, ancho: u32, alto: u32, m: Rect) -> (i32, i32) {
    let ancho_i = i64::from(ancho);
    let alto_i = i64::from(alto);
    let mut x = i64::from(ancla.x) - ancho_i / 2;
    let mut y = i64::from(ancla.y);

    let mx = i64::from(m.x);
    let my = i64::from(m.y);
    let mw = i64::from(m.ancho);
    let mh = i64::from(m.alto);

    if ancho_i >= mw {
        x = mx;
    } else {
        if x < mx {
            x = mx;
        }
        if x + ancho_i > mx + mw {
            x = mx + mw - ancho_i;
        }
    }

    if alto_i >= mh {
        y = my;
    } else {
        if y < my {
            y = my;
        }
        if y + alto_i > my + mh {
            y = my + mh - alto_i;
        }
    }

    (x as i32, y as i32)
}

pub fn ancla_de(x: i32, y: i32, ancho: u32) -> Ancla {
    Ancla {
        x: x + (i64::from(ancho) / 2) as i32,
        y,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const M1: Rect = Rect {
        x: 0,
        y: 0,
        ancho: 1920,
        alto: 1080,
    };

    const M2: Rect = Rect {
        x: 1920,
        y: 0,
        ancho: 1920,
        alto: 1080,
    };

    const M_IZQ: Rect = Rect {
        x: -1920,
        y: 0,
        ancho: 1920,
        alto: 1080,
    };

    #[test]
    fn ancla_en_segundo_monitor() {
        let ancla = Ancla { x: 1920 + 960, y: 5 };
        assert_eq!(monitor_de(ancla, &[M1, M2]), Some(1));
    }

    #[test]
    fn ancla_en_monitor_izquierdo_negativo() {
        let ancla = Ancla { x: -960, y: 5 };
        assert_eq!(monitor_de(ancla, &[M_IZQ, M1]), Some(0));
    }

    #[test]
    fn ancla_fuera_de_todo() {
        let ancla = Ancla { x: 5000, y: 5 };
        assert_eq!(monitor_de(ancla, &[M1, M2]), None);
    }

    #[test]
    fn encajar_centrado_sin_clamp() {
        let ancla = Ancla { x: 960, y: 5 };
        assert_eq!(encajar(ancla, 240, 64, M1), (840, 5));
    }

    #[test]
    fn encajar_clamp_derecha() {
        let ancla = Ancla { x: 1900, y: 5 };
        assert_eq!(encajar(ancla, 240, 64, M1), (1680, 5));
    }

    #[test]
    fn encajar_clamp_izquierda() {
        let ancla = Ancla { x: 50, y: 5 };
        assert_eq!(encajar(ancla, 240, 64, M1), (0, 5));
    }

    #[test]
    fn encajar_clamp_abajo() {
        let ancla = Ancla { x: 960, y: 1060 };
        assert_eq!(encajar(ancla, 240, 64, M1), (840, 1016));
    }

    #[test]
    fn encajar_ventana_mas_grande_que_monitor() {
        let ancla = Ancla { x: 960, y: 5 };
        assert_eq!(encajar(ancla, 2000, 1200, M1), (0, 0));
    }

    #[test]
    fn ancla_de_encajar_ida_y_vuelta() {
        let ancla = Ancla { x: 500, y: 12 };
        let (x, y) = encajar(ancla, 200, 80, M1);
        assert_eq!(ancla_de(x, y, 200), ancla);
    }
}
