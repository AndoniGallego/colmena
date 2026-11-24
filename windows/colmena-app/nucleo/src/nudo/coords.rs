use serde::Serialize;

use crate::posicion::Rect;

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct RectLogico {
    pub x: f64,
    pub y: f64,
    pub ancho: f64,
    pub alto: f64,
}

pub fn a_overlay(r: Rect, monitor: Rect, escala: f64) -> Option<RectLogico> {
    if !escala.is_finite() || escala <= 0.0 {
        return None;
    }
    let x0 = i64::from(r.x).max(i64::from(monitor.x));
    let y0 = i64::from(r.y).max(i64::from(monitor.y));
    let x1 = (i64::from(r.x) + i64::from(r.ancho)).min(i64::from(monitor.x) + i64::from(monitor.ancho));
    let y1 = (i64::from(r.y) + i64::from(r.alto)).min(i64::from(monitor.y) + i64::from(monitor.alto));
    if x1 <= x0 || y1 <= y0 {
        return None;
    }
    Some(RectLogico {
        x: (x0 - i64::from(monitor.x)) as f64 / escala,
        y: (y0 - i64::from(monitor.y)) as f64 / escala,
        ancho: (x1 - x0) as f64 / escala,
        alto: (y1 - y0) as f64 / escala,
    })
}

const SEPARACION_GLOBO: f64 = 12.0;
const MARGEN_GLOBO: f64 = 8.0;
const MARGEN_ORIGEN: f64 = 40.0;

pub fn posicion_globo(objetivo: &RectLogico, monitor: (f64, f64), globo: (f64, f64)) -> (f64, f64) {
    let abajo = objetivo.y + objetivo.alto + SEPARACION_GLOBO;
    let y = if abajo + globo.1 <= monitor.1 {
        abajo
    } else {
        objetivo.y - SEPARACION_GLOBO - globo.1
    };
    let x_max = (monitor.0 - MARGEN_GLOBO - globo.0).max(MARGEN_GLOBO);
    (objetivo.x.clamp(MARGEN_GLOBO, x_max), y)
}

fn solapamiento(a: &RectLogico, b: &RectLogico) -> f64 {
    let w = (a.x + a.ancho).min(b.x + b.ancho) - a.x.max(b.x);
    let h = (a.y + a.alto).min(b.y + b.alto) - a.y.max(b.y);
    if w > 0.0 && h > 0.0 {
        w * h
    } else {
        0.0
    }
}

fn toca(a: &RectLogico, b: &RectLogico) -> bool {
    a.x <= b.x + b.ancho && b.x <= a.x + a.ancho && a.y <= b.y + b.alto && b.y <= a.y + a.alto
}

/// Como `posicion_globo`, pero sin pisar menús o popups abiertos (que capturan el clic por coordenadas).
pub fn posicion_globo_evitando(
    objetivo: &RectLogico,
    monitor: (f64, f64),
    globo: (f64, f64),
    evitar: &[RectLogico],
) -> (f64, f64) {
    let base_pos = posicion_globo(objetivo, monitor, globo);
    if evitar.is_empty() {
        return base_pos;
    }
    let area = |r: &RectLogico| r.ancho * r.alto;
    let base = evitar
        .iter()
        .filter(|r| toca(r, objetivo))
        .max_by(|a, b| area(a).total_cmp(&area(b)))
        .unwrap_or(objetivo);
    let x_max = (monitor.0 - MARGEN_GLOBO - globo.0).max(MARGEN_GLOBO);
    let y_max = (monitor.1 - MARGEN_GLOBO - globo.1).max(MARGEN_GLOBO);
    let x_alineado = objetivo.x.clamp(MARGEN_GLOBO, x_max);
    let y_alineado = objetivo.y.clamp(MARGEN_GLOBO, y_max);
    let candidatas = [
        base_pos,
        (x_alineado, objetivo.y + objetivo.alto + SEPARACION_GLOBO),
        (x_alineado, objetivo.y - SEPARACION_GLOBO - globo.1),
        (base.x + base.ancho + SEPARACION_GLOBO, y_alineado),
        (base.x - SEPARACION_GLOBO - globo.0, y_alineado),
    ];
    let rect = |p: (f64, f64)| RectLogico { x: p.0, y: p.1, ancho: globo.0, alto: globo.1 };
    let entra = |p: (f64, f64)| {
        p.0 >= MARGEN_GLOBO
            && p.1 >= MARGEN_GLOBO
            && p.0 + globo.0 <= monitor.0 - MARGEN_GLOBO
            && p.1 + globo.1 <= monitor.1 - MARGEN_GLOBO
    };
    let libre = |p: (f64, f64)| {
        let r = rect(p);
        solapamiento(&r, objetivo) == 0.0 && evitar.iter().all(|e| solapamiento(&r, e) == 0.0)
    };
    if let Some(p) = candidatas.iter().copied().find(|&p| entra(p) && libre(p)) {
        return p;
    }
    let dentro = |p: (f64, f64)| (p.0.clamp(MARGEN_GLOBO, x_max), p.1.clamp(MARGEN_GLOBO, y_max));
    let costo = |p: (f64, f64)| evitar.iter().map(|e| solapamiento(&rect(p), e)).sum::<f64>();
    candidatas
        .iter()
        .copied()
        .map(dentro)
        .fold(None::<((f64, f64), f64)>, |mejor, p| {
            let c = costo(p);
            match mejor {
                Some((_, cm)) if cm <= c => mejor,
                _ => Some((p, c)),
            }
        })
        .map_or(base_pos, |(p, _)| p)
}

/// Lado del globo que mira al objetivo: desde ahí entra y hacia ahí sale (donde está la abejita).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Lado {
    Arriba,
    Abajo,
    Izquierda,
    Derecha,
}

pub fn lado_hacia(globo: &RectLogico, objetivo: &RectLogico) -> Lado {
    let dx = (objetivo.x + objetivo.ancho / 2.0) - (globo.x + globo.ancho / 2.0);
    let dy = (objetivo.y + objetivo.alto / 2.0) - (globo.y + globo.alto / 2.0);
    // Normalizado por el tamaño del globo: un globo ancho y bajo mira arriba/abajo salvo que el objetivo quede bien al costado.
    let nx = dx / (globo.ancho / 2.0).max(1.0);
    let ny = dy / (globo.alto / 2.0).max(1.0);
    if nx.abs() > ny.abs() {
        if nx < 0.0 {
            Lado::Izquierda
        } else {
            Lado::Derecha
        }
    } else if ny < 0.0 {
        Lado::Arriba
    } else {
        Lado::Abajo
    }
}

pub fn origen_nudo(monitor: (f64, f64)) -> (f64, f64) {
    (monitor.0 - MARGEN_ORIGEN, monitor.1 - MARGEN_ORIGEN)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(x: f64, y: f64, ancho: f64, alto: f64) -> RectLogico {
        RectLogico { x, y, ancho, alto }
    }

    #[test]
    fn lado_hacia_globo_debajo_del_objetivo_mira_arriba() {
        assert_eq!(lado_hacia(&r(100.0, 200.0, 280.0, 128.0), &r(100.0, 150.0, 80.0, 30.0)), Lado::Arriba);
    }

    #[test]
    fn lado_hacia_globo_encima_del_objetivo_mira_abajo() {
        assert_eq!(lado_hacia(&r(100.0, 0.0, 280.0, 128.0), &r(100.0, 150.0, 80.0, 30.0)), Lado::Abajo);
    }

    #[test]
    fn lado_hacia_globo_a_la_derecha_mira_a_la_izquierda() {
        assert_eq!(lado_hacia(&r(400.0, 100.0, 280.0, 128.0), &r(300.0, 120.0, 88.0, 80.0)), Lado::Izquierda);
    }

    #[test]
    fn lado_hacia_globo_a_la_izquierda_mira_a_la_derecha() {
        assert_eq!(lado_hacia(&r(0.0, 100.0, 280.0, 128.0), &r(300.0, 120.0, 88.0, 80.0)), Lado::Derecha);
    }

    #[test]
    fn lado_hacia_sin_objetivo_mira_al_origen_del_nudo() {
        let m = (1920.0, 1080.0);
        let (ox, oy) = origen_nudo(m);
        let globo = r(ox - 280.0 + 32.0, oy - 128.0 - 12.0, 280.0, 128.0);
        assert_eq!(lado_hacia(&globo, &r(ox, oy, 0.0, 0.0)), Lado::Abajo);
    }

    #[test]
    fn lado_se_serializa_en_minusculas() {
        assert_eq!(serde_json::to_string(&Lado::Izquierda).unwrap(), "\"izquierda\"");
    }

    #[test]
    fn convierte_a_logico_con_escala_125() {
        let m = Rect { x: 1920, y: 0, ancho: 2560, alto: 1440 };
        assert_eq!(
            a_overlay(Rect { x: 2020, y: 100, ancho: 250, alto: 50 }, m, 1.25),
            Some(RectLogico { x: 80.0, y: 80.0, ancho: 200.0, alto: 40.0 })
        );
    }

    #[test]
    fn convierte_a_logico_con_escala_150() {
        let m = Rect { x: 0, y: 0, ancho: 3840, alto: 2160 };
        assert_eq!(
            a_overlay(Rect { x: 300, y: 150, ancho: 150, alto: 75 }, m, 1.5),
            Some(RectLogico { x: 200.0, y: 100.0, ancho: 100.0, alto: 50.0 })
        );
    }

    #[test]
    fn recorta_al_borde_del_monitor() {
        let m = Rect { x: 1920, y: 0, ancho: 1920, alto: 1080 };
        assert_eq!(
            a_overlay(Rect { x: 1900, y: 100, ancho: 100, alto: 50 }, m, 1.0),
            Some(RectLogico { x: 0.0, y: 100.0, ancho: 80.0, alto: 50.0 })
        );
    }

    #[test]
    fn fuera_del_monitor_o_escala_invalida_es_none() {
        let m = Rect { x: 1920, y: 0, ancho: 1920, alto: 1080 };
        let r = Rect { x: 2000, y: 0, ancho: 100, alto: 50 };
        assert_eq!(a_overlay(Rect { x: -500, y: 0, ancho: 100, alto: 50 }, m, 1.0), None);
        assert_eq!(a_overlay(r, m, 0.0), None);
        assert_eq!(a_overlay(r, m, f64::NAN), None);
        assert_eq!(a_overlay(r, m, -1.0), None);
    }

    #[test]
    fn globo_va_abajo_si_entra() {
        let o = RectLogico { x: 100.0, y: 100.0, ancho: 80.0, alto: 30.0 };
        assert_eq!(posicion_globo(&o, (1920.0, 1080.0), (280.0, 96.0)), (100.0, 142.0));
    }

    #[test]
    fn globo_va_arriba_si_no_entra_abajo() {
        let o = RectLogico { x: 100.0, y: 1000.0, ancho: 80.0, alto: 30.0 };
        assert_eq!(posicion_globo(&o, (1920.0, 1080.0), (280.0, 96.0)).1, 1000.0 - 12.0 - 96.0);
    }

    #[test]
    fn globo_no_se_sale_por_los_costados() {
        let o = RectLogico { x: 1880.0, y: 100.0, ancho: 30.0, alto: 30.0 };
        assert_eq!(posicion_globo(&o, (1920.0, 1080.0), (280.0, 96.0)).0, 1920.0 - 8.0 - 280.0);
        let o = RectLogico { x: 0.0, y: 100.0, ancho: 30.0, alto: 30.0 };
        assert_eq!(posicion_globo(&o, (1920.0, 1080.0), (280.0, 96.0)).0, 8.0);
    }

    #[test]
    fn el_nudo_vive_abajo_a_la_derecha() {
        assert_eq!(origen_nudo((1920.0, 1080.0)), (1880.0, 1040.0));
    }

    fn rl(x: f64, y: f64, ancho: f64, alto: f64) -> RectLogico {
        RectLogico { x, y, ancho, alto }
    }

    fn solapa(a: &RectLogico, b: &RectLogico) -> f64 {
        let w = (a.x + a.ancho).min(b.x + b.ancho) - a.x.max(b.x);
        let h = (a.y + a.alto).min(b.y + b.alto) - a.y.max(b.y);
        if w > 0.0 && h > 0.0 { w * h } else { 0.0 }
    }

    const G: (f64, f64) = (280.0, 96.0);
    const M: (f64, f64) = (1920.0, 1080.0);

    fn rect_globo(p: (f64, f64)) -> RectLogico {
        rl(p.0, p.1, G.0, G.1)
    }

    #[test]
    fn sin_evitar_es_igual_que_antes() {
        let o = rl(100.0, 100.0, 80.0, 30.0);
        assert_eq!(posicion_globo_evitando(&o, M, G, &[]), posicion_globo(&o, M, G));
        let o = rl(1880.0, 1000.0, 30.0, 30.0);
        assert_eq!(posicion_globo_evitando(&o, M, G, &[]), posicion_globo(&o, M, G));
    }

    #[test]
    fn menu_debajo_del_objetivo_manda_el_globo_al_costado() {
        let o = rl(100.0, 100.0, 80.0, 30.0);
        let menu = rl(90.0, 130.0, 200.0, 300.0);
        let p = posicion_globo_evitando(&o, M, G, &[menu]);
        assert_eq!(solapa(&rect_globo(p), &menu), 0.0);
        assert_eq!(solapa(&rect_globo(p), &o), 0.0);
        assert_eq!(p.0, 90.0 + 200.0 + 12.0);
    }

    #[test]
    fn menu_de_todo_el_alto_va_a_la_derecha() {
        let o = rl(100.0, 100.0, 80.0, 30.0);
        let menu = rl(100.0, 0.0, 300.0, 1080.0);
        let p = posicion_globo_evitando(&o, M, G, &[menu]);
        assert_eq!(solapa(&rect_globo(p), &menu), 0.0);
        assert_eq!(p.0, 412.0);
    }

    #[test]
    fn menu_de_todo_el_alto_sin_lugar_a_la_derecha_va_a_la_izquierda() {
        let o = rl(1500.0, 100.0, 80.0, 30.0);
        let menu = rl(1450.0, 0.0, 300.0, 1080.0);
        let p = posicion_globo_evitando(&o, M, G, &[menu]);
        assert_eq!(solapa(&rect_globo(p), &menu), 0.0);
        assert_eq!(p.0, 1450.0 - 12.0 - 280.0);
    }

    #[test]
    fn monitor_chico_sin_lugar_minimiza_la_superposicion_y_queda_dentro() {
        let monitor = (300.0, 200.0);
        let o = rl(10.0, 10.0, 50.0, 20.0);
        let menu = rl(0.0, 30.0, 300.0, 170.0);
        let p = posicion_globo_evitando(&o, monitor, G, &[menu]);
        assert!(p.0 >= 0.0 && p.1 >= 0.0);
        assert!(p.0 + G.0 <= monitor.0 && p.1 + G.1 <= monitor.1);
        let por_defecto = posicion_globo(&o, monitor, G);
        assert!(solapa(&rect_globo(p), &menu) < solapa(&rect_globo(por_defecto), &menu));
    }
}
