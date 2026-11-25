use serde::Serialize;
use std::collections::VecDeque;

pub const COLA_MAX: usize = 2000;
pub const LOTE_LINEAS: usize = 200;
pub const LOTE_BYTES: usize = 60_000;
pub const NOTCH_POR_MINUTO: u32 = 60;

#[derive(Serialize, Debug, PartialEq)]
pub struct Lote {
    pub lote: u64,
    pub lineas: Vec<String>,
}

pub struct Cola {
    lineas: VecDeque<String>,
    max: usize,
    descartadas: u64,
    siguiente_id: u64,
    // (id, líneas de la cola incluidas, si llevaba encabezado)
    en_vuelo: Option<(u64, usize, bool)>,
}

fn costo(linea: &str) -> usize {
    serde_json::to_string(linea).map(|j| j.len()).unwrap_or(linea.len() + 2) + 1
}

impl Cola {
    pub fn new(max: usize) -> Cola {
        Cola { lineas: VecDeque::new(), max, descartadas: 0, siguiente_id: 0, en_vuelo: None }
    }

    pub fn desde_texto(texto: &str, max: usize) -> Cola {
        let mut c = Cola::new(max);
        for l in texto.lines().filter(|l| !l.is_empty()) {
            c.anotar(l.to_string());
        }
        c.descartadas = 0;
        c
    }

    pub fn anotar(&mut self, linea: String) {
        if self.max == 0 {
            self.descartadas += 1;
            return;
        }
        if self.lineas.len() >= self.max {
            self.lineas.pop_front();
            self.descartadas += 1;
            if let Some((_, n, _)) = self.en_vuelo.as_mut() {
                *n = n.saturating_sub(1);
            }
        }
        self.lineas.push_back(linea);
    }

    pub fn descartadas(&self) -> u64 {
        self.descartadas
    }

    pub fn pendiente(&mut self, encabezado: Option<String>, max_lineas: usize, max_bytes: usize) -> Option<Lote> {
        let mut lineas = Vec::new();
        let mut bytes = 0;
        let con_encabezado = encabezado.is_some();
        if let Some(e) = encabezado {
            let c = costo(&e);
            if max_lineas == 0 || c > max_bytes {
                return None;
            }
            bytes += c;
            lineas.push(e);
        }
        let mut de_cola = 0;
        for l in &self.lineas {
            let c = costo(l);
            if lineas.len() >= max_lineas || bytes + c > max_bytes {
                break;
            }
            bytes += c;
            lineas.push(l.clone());
            de_cola += 1;
        }
        if lineas.is_empty() {
            return None;
        }
        self.siguiente_id += 1;
        let id = self.siguiente_id;
        self.en_vuelo = Some((id, de_cola, con_encabezado));
        Some(Lote { lote: id, lineas })
    }

    pub fn enviado(&mut self, lote: u64) -> bool {
        match self.en_vuelo {
            Some((id, n, con_encabezado)) if id == lote => {
                for _ in 0..n.min(self.lineas.len()) {
                    self.lineas.pop_front();
                }
                if con_encabezado {
                    self.descartadas = 0;
                }
                self.en_vuelo = None;
                true
            }
            _ => false,
        }
    }

    pub fn texto(&self) -> String {
        self.lineas.iter().map(|l| format!("{l}\n")).collect()
    }
}

pub struct Limitador {
    max: u32,
    ventana_ms: u64,
    inicio: Option<u64>,
    usadas: u32,
    descartadas: u32,
}

impl Limitador {
    pub fn new(max: u32, ventana_ms: u64) -> Limitador {
        Limitador { max, ventana_ms, inicio: None, usadas: 0, descartadas: 0 }
    }

    pub fn permitir(&mut self, ahora_ms: u64) -> bool {
        match self.inicio {
            Some(i) if ahora_ms.saturating_sub(i) < self.ventana_ms => {}
            _ => {
                self.inicio = Some(ahora_ms);
                self.usadas = 0;
            }
        }
        if self.usadas < self.max {
            self.usadas += 1;
            true
        } else {
            self.descartadas += 1;
            false
        }
    }

    pub fn tomar_descartadas(&mut self) -> u32 {
        std::mem::take(&mut self.descartadas)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test] fn pendiente_vacio_es_none() { assert_eq!(Cola::new(10).pendiente(None, 200, 60_000), None); }
    #[test] fn lote_respeta_max_lineas() {
        let mut c = Cola::new(10); for i in 0..5 { c.anotar(format!("l{i}")); }
        let l = c.pendiente(None, 3, 60_000).unwrap();
        assert_eq!(l.lineas, ["l0", "l1", "l2"]);
    }
    #[test] fn lote_respeta_max_bytes_contando_json() {
        let mut c = Cola::new(10); c.anotar("\"".repeat(10)); c.anotar("x".into());
        // serde_json::to_string de 10 comillas = 22 bytes, + 1 = 23 > 22: no entra ni la primera
        assert_eq!(c.pendiente(None, 200, 22), None);
        assert_eq!(c.pendiente(None, 200, 27).unwrap().lineas.len(), 2);   // 23 + ("\"x\"" 3 + 1) = 27
    }
    #[test] fn enviado_saca_las_del_lote_y_deja_las_nuevas() {
        let mut c = Cola::new(10); c.anotar("a".into()); c.anotar("b".into());
        let l = c.pendiente(None, 200, 60_000).unwrap(); c.anotar("c".into());
        assert!(c.enviado(l.lote));
        assert_eq!(c.texto(), "c\n");
    }
    #[test] fn enviado_de_lote_viejo_no_borra() {
        let mut c = Cola::new(10); c.anotar("a".into());
        let viejo = c.pendiente(None, 200, 60_000).unwrap(); let _nuevo = c.pendiente(None, 200, 60_000).unwrap();
        assert!(!c.enviado(viejo.lote)); assert_eq!(c.texto(), "a\n");
    }
    #[test] fn desborde_descarta_la_mas_vieja_y_cuenta() {
        let mut c = Cola::new(2); for x in ["a", "b", "c"] { c.anotar(x.into()); }
        assert_eq!(c.texto(), "b\nc\n"); assert_eq!(c.descartadas(), 1);
    }
    #[test] fn desborde_con_lote_en_vuelo_no_borra_lineas_nuevas_al_confirmar() {
        let mut c = Cola::new(2); c.anotar("a".into()); c.anotar("b".into());
        let l = c.pendiente(None, 200, 60_000).unwrap();   // a, b
        c.anotar("c".into());                               // sale a
        assert!(c.enviado(l.lote));
        assert_eq!(c.texto(), "c\n");
    }
    #[test] fn encabezado_va_primero_y_confirmarlo_pone_descartadas_en_cero() {
        let mut c = Cola::new(1); c.anotar("a".into()); c.anotar("b".into());
        let l = c.pendiente(Some("enc".into()), 200, 60_000).unwrap();
        assert_eq!(l.lineas, ["enc", "b"]); assert!(c.enviado(l.lote)); assert_eq!(c.descartadas(), 0);
    }
    #[test] fn desde_texto_ignora_vacios_y_conserva_los_ultimos() {
        assert_eq!(Cola::desde_texto("a\n\nb\nc\n", 2).texto(), "b\nc\n");
    }
    #[test] fn limitador_corta_en_el_maximo_y_cuenta() {
        let mut l = Limitador::new(2, 60_000);
        assert!(l.permitir(0)); assert!(l.permitir(1)); assert!(!l.permitir(2)); assert!(!l.permitir(3));
        assert_eq!(l.tomar_descartadas(), 2); assert_eq!(l.tomar_descartadas(), 0);
    }
    #[test] fn limitador_reabre_al_pasar_la_ventana() {
        let mut l = Limitador::new(1, 60_000); assert!(l.permitir(0)); assert!(!l.permitir(59_999)); assert!(l.permitir(60_000));
    }
}
