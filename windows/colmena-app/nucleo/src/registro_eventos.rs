use serde::Serialize;
use std::collections::VecDeque;

pub const ORIGENES: [&str; 8] = ["app", "nudo", "atajos", "guia", "mostrar", "reunion", "tuneles", "notch"];
pub const COLA_EVENTOS_MAX: usize = 500;

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct EventoApp {
    pub ts: String,
    pub origen: &'static str,
    pub evento: String,
    pub ok: bool,
    pub codigo: Option<String>,
    pub ms: Option<u64>,
    pub version: Option<String>,
}

pub fn token(s: &str) -> String {
    let valido = (1..=40).contains(&s.len()) && s.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_');
    if valido { s.to_string() } else { "otro".to_string() }
}

fn version_valida(v: &str) -> bool {
    (1..=20).contains(&v.len()) && v.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'+' | b'-'))
}

pub fn evento(ts: String, origen: &str, evento: &str, ok: bool, codigo: Option<&str>, ms: Option<u64>, version: Option<&str>) -> EventoApp {
    let origen = ORIGENES.iter().copied().find(|o| *o == origen).unwrap_or("app");
    let version = version.filter(|v| evento == "arranque" && version_valida(v)).map(str::to_string);
    EventoApp { ts, origen, evento: token(evento), ok, codigo: codigo.map(token), ms, version }
}

const MARGEN_CLAVES: usize = 128;
const BYTES_EVENTO_SI_FALLA: usize = 200;

/// Bytes que quedan para las líneas de un POST combinado: al tope se le restan
/// los eventos serializados y un margen para las claves del JSON.
pub fn bytes_lineas_disponibles(eventos: &[EventoApp], tope: usize) -> usize {
    let usados: usize = eventos
        .iter()
        .map(|e| serde_json::to_string(e).map_or(BYTES_EVENTO_SI_FALLA, |j| j.len()) + 1)
        .sum();
    tope.saturating_sub(usados).saturating_sub(MARGEN_CLAVES)
}

pub struct ColaEventos {
    eventos: VecDeque<EventoApp>,
    max: usize,
    descartados: u64,
    // ts del evento descartado más reciente: es el ts del evento cola_llena
    ts_descarte: String,
    siguiente_id: u64,
    // (id, eventos de la cola incluidos, descartados que informaba el cola_llena del lote)
    en_vuelo: Option<(u64, usize, u64)>,
}

impl ColaEventos {
    pub fn new(max: usize) -> ColaEventos {
        ColaEventos { eventos: VecDeque::new(), max, descartados: 0, ts_descarte: String::new(), siguiente_id: 0, en_vuelo: None }
    }

    pub fn anotar(&mut self, e: EventoApp) {
        if self.max == 0 {
            self.descartados += 1;
            self.ts_descarte = e.ts;
            return;
        }
        if self.eventos.len() >= self.max {
            if let Some(viejo) = self.eventos.pop_front() {
                self.descartados += 1;
                self.ts_descarte = viejo.ts;
            }
            if let Some((_, n, _)) = self.en_vuelo.as_mut() {
                *n = n.saturating_sub(1);
            }
        }
        self.eventos.push_back(e);
    }

    // Si hubo descartados, el lote empieza con "cola_llena" (cuenta dentro de `max`); su `ms` es la cantidad descartada.
    pub fn pendiente(&mut self, max: usize) -> Option<(u64, Vec<EventoApp>)> {
        let mut lote = Vec::new();
        let mut informados = 0;
        if self.descartados > 0 && max > 0 {
            informados = self.descartados;
            lote.push(evento(self.ts_descarte.clone(), "app", "cola_llena", false, Some("descartados"), Some(informados), None));
        }
        let mut de_cola = 0;
        for e in &self.eventos {
            if lote.len() >= max {
                break;
            }
            lote.push(e.clone());
            de_cola += 1;
        }
        if lote.is_empty() {
            return None;
        }
        self.siguiente_id += 1;
        let id = self.siguiente_id;
        self.en_vuelo = Some((id, de_cola, informados));
        Some((id, lote))
    }

    pub fn enviado(&mut self, lote: u64) -> bool {
        match self.en_vuelo {
            Some((id, n, informados)) if id == lote => {
                for _ in 0..n.min(self.eventos.len()) {
                    self.eventos.pop_front();
                }
                self.descartados = self.descartados.saturating_sub(informados);
                self.en_vuelo = None;
                true
            }
            _ => false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ts() -> String { "2026-11-25T10:00:00Z".to_string() }
    fn err() -> EventoApp { evento(ts(), "app", "error", false, None, None, None) }

    #[test] fn token_valido_e_invalido() {
        assert_eq!(token("uia_sin_foco"), "uia_sin_foco");
        assert_eq!(token("Sin Foco"), "otro");
        assert_eq!(token(&"a".repeat(41)), "otro");
        assert_eq!(token(&"a".repeat(40)), "a".repeat(40));
        assert_eq!(token(""), "otro");
    }
    #[test] fn origen_desconocido_es_app() {
        assert_eq!(evento(ts(), "x", "arranque", true, None, None, None).origen, "app");
        assert_eq!(evento(ts(), "tuneles", "arranque", true, None, None, None).origen, "tuneles");
    }
    #[test] fn version_solo_en_arranque() {
        assert_eq!(evento(ts(), "app", "conectado", true, None, None, Some("1.2.3")).version, None);
        assert_eq!(evento(ts(), "app", "arranque", true, None, None, Some("1.2.3")).version, Some("1.2.3".to_string()));
    }
    #[test] fn version_invalida_se_descarta() {
        assert_eq!(evento(ts(), "app", "arranque", true, None, None, Some("1 2")).version, None);
        assert_eq!(evento(ts(), "app", "arranque", true, None, None, Some(&"1".repeat(21))).version, None);
        assert_eq!(evento(ts(), "app", "arranque", true, None, None, Some("")).version, None);
    }
    #[test] fn nunca_serializa_texto_libre() {
        let e = evento(ts(), "tuneles", "C:\\Users\\ana\\x", false, Some("ssh rechazado por host 10.0.0.1"), Some(5), None);
        let j = serde_json::to_string(&e).unwrap();
        assert!(!j.contains("ana") && !j.contains("10.0.0.1") && j.contains("\"evento\":\"otro\"") && j.contains("\"codigo\":\"otro\""));
    }
    #[test] fn serializa_exactamente_las_claves() {
        let j = serde_json::to_value(evento(ts(), "app", "arranque", true, None, None, None)).unwrap();
        let mut claves: Vec<_> = j.as_object().unwrap().keys().cloned().collect();
        claves.sort();
        assert_eq!(claves, ["codigo", "evento", "ms", "ok", "origen", "ts", "version"]);
    }
    #[test] fn cola_acotada_y_cola_llena() {
        let mut c = ColaEventos::new(3); for _ in 0..5 { c.anotar(err()); }
        let (_, lote) = c.pendiente(10).unwrap();
        assert_eq!(lote[0].evento, "cola_llena"); assert_eq!(lote[0].ms, Some(2)); assert_eq!(lote.len(), 4);
        assert_eq!(lote[0].codigo.as_deref(), Some("descartados")); assert!(!lote[0].ok);
    }
    #[test] fn cola_llena_toma_el_ts_del_ultimo_descartado() {
        let mut c = ColaEventos::new(1);
        c.anotar(evento("t1".into(), "app", "a", true, None, None, None));
        c.anotar(evento("t2".into(), "app", "b", true, None, None, None));
        c.anotar(evento("t3".into(), "app", "c", true, None, None, None));
        let (_, lote) = c.pendiente(10).unwrap();
        assert_eq!(lote[0].ts, "t2");
        assert_eq!(lote[1].evento, "c");
    }
    #[test] fn cola_llena_cuenta_dentro_del_max() {
        let mut c = ColaEventos::new(3); for _ in 0..5 { c.anotar(err()); }
        let (_, lote) = c.pendiente(2).unwrap();
        assert_eq!(lote.len(), 2); assert_eq!(lote[0].evento, "cola_llena");
    }
    #[test] fn enviado_solo_el_ultimo_lote() {
        let mut c = ColaEventos::new(5); c.anotar(err());
        let (a, _) = c.pendiente(10).unwrap(); let (b, _) = c.pendiente(10).unwrap();
        assert!(!c.enviado(a)); assert!(c.enviado(b)); assert!(c.pendiente(10).is_none());
    }
    #[test] fn enviado_saca_los_del_lote_y_deja_los_nuevos() {
        let mut c = ColaEventos::new(5); c.anotar(err()); c.anotar(err());
        let (id, _) = c.pendiente(10).unwrap();
        c.anotar(evento(ts(), "app", "nuevo", true, None, None, None));
        assert!(c.enviado(id));
        let (_, resto) = c.pendiente(10).unwrap();
        assert_eq!(resto.len(), 1); assert_eq!(resto[0].evento, "nuevo");
    }
    #[test] fn desborde_con_lote_en_vuelo_no_borra_los_nuevos() {
        let mut c = ColaEventos::new(2);
        c.anotar(evento(ts(), "app", "a", true, None, None, None)); c.anotar(evento(ts(), "app", "b", true, None, None, None));
        let (id, _) = c.pendiente(10).unwrap();
        c.anotar(evento(ts(), "app", "c", true, None, None, None));
        assert!(c.enviado(id));
        let (_, resto) = c.pendiente(10).unwrap();
        assert_eq!(resto.iter().map(|e| e.evento.as_str()).collect::<Vec<_>>(), ["cola_llena", "c"]);
    }
    #[test] fn confirmar_lote_con_cola_llena_pone_descartados_en_cero() {
        let mut c = ColaEventos::new(2); for _ in 0..4 { c.anotar(err()); }
        let (id, _) = c.pendiente(10).unwrap();
        assert!(c.enviado(id));
        assert!(c.pendiente(10).is_none());
    }
    #[test] fn descartes_durante_el_vuelo_no_se_pierden() {
        let mut c = ColaEventos::new(2); for _ in 0..3 { c.anotar(err()); }   // 1 descartado
        let (id, lote) = c.pendiente(10).unwrap();
        assert_eq!(lote[0].ms, Some(1));
        for _ in 0..2 { c.anotar(err()); }                                     // 2 más mientras vuela
        assert!(c.enviado(id));
        let (_, sig) = c.pendiente(10).unwrap();
        assert_eq!(sig[0].evento, "cola_llena"); assert_eq!(sig[0].ms, Some(2));
    }
    #[test] fn pendiente_vacio_es_none() { assert!(ColaEventos::new(5).pendiente(10).is_none()); }

    #[test] fn lote_combinado_con_eventos_maximos_cabe_en_64_kb() {
        let eventos: Vec<EventoApp> = (0..50)
            .map(|_| evento(ts(), "tuneles", &"e".repeat(40), false, Some(&"c".repeat(40)), Some(u64::MAX), None))
            .collect();
        let disponibles = bytes_lineas_disponibles(&eventos, 60_000);
        assert!(disponibles < 60_000);
        let linea = "x".repeat(disponibles.saturating_sub(10));
        let json = serde_json::json!({"lineas": [linea], "eventos": eventos}).to_string();
        assert!(json.len() <= 64 * 1024, "{}", json.len());
    }
    #[test] fn sin_eventos_solo_descuenta_el_margen() {
        assert_eq!(bytes_lineas_disponibles(&[], 60_000), 60_000 - MARGEN_CLAVES);
        assert_eq!(bytes_lineas_disponibles(&[err()], 0), 0);
    }
}
