pub const MENSAJE_MAX: usize = 500;
pub const DIAS_GUARDADO: u32 = 7;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Nivel {
    Info,
    Aviso,
    Error,
}

impl Nivel {
    pub fn as_str(self) -> &'static str {
        match self {
            Nivel::Info => "info",
            Nivel::Aviso => "aviso",
            Nivel::Error => "error",
        }
    }

    pub fn desde(s: &str) -> Option<Nivel> {
        match s {
            "info" => Some(Nivel::Info),
            "aviso" => Some(Nivel::Aviso),
            "error" => Some(Nivel::Error),
            _ => None,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Origen {
    App,
    Nudo,
    Atajos,
    Guia,
    Reunion,
    Tuneles,
    Notch,
}

impl Origen {
    pub fn as_str(self) -> &'static str {
        match self {
            Origen::App => "app",
            Origen::Nudo => "nudo",
            Origen::Atajos => "atajos",
            Origen::Guia => "guia",
            Origen::Reunion => "reunion",
            Origen::Tuneles => "tuneles",
            Origen::Notch => "notch",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Fecha {
    pub anio: i32,
    pub mes: u8,
    pub dia: u8,
    pub hora: u8,
    pub min: u8,
    pub seg: u8,
    pub ms: u16,
}

// Algoritmos de Howard Hinnant para fechas civiles.
fn dias_desde_civil(anio: i32, mes: u8, dia: u8) -> i64 {
    let y = i64::from(anio) - i64::from(mes <= 2);
    let era = y.div_euclid(400);
    let yoe = y.rem_euclid(400);
    let m = i64::from(mes);
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + i64::from(dia) - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

fn civil_desde_dias(z: i64) -> (i32, u8, u8) {
    let z = z + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let dia = (doy - (153 * mp + 2) / 5 + 1) as u8;
    let mes = if mp < 10 { mp + 3 } else { mp - 9 } as u8;
    let anio = (yoe + era * 400 + i64::from(mes <= 2)) as i32;
    (anio, mes, dia)
}

impl Fecha {
    pub fn iso(&self) -> String {
        format!(
            "{}T{:02}:{:02}:{:02}.{:03}",
            self.dia_iso(),
            self.hora,
            self.min,
            self.seg,
            self.ms
        )
    }

    pub fn dia_iso(&self) -> String {
        format!("{:04}-{:02}-{:02}", self.anio, self.mes, self.dia)
    }

    pub fn desde_unix_ms(ms: u64) -> Fecha {
        let dias = (ms / 86_400_000) as i64;
        let resto = ms % 86_400_000;
        let (anio, mes, dia) = civil_desde_dias(dias);
        Fecha {
            anio,
            mes,
            dia,
            hora: (resto / 3_600_000) as u8,
            min: (resto / 60_000 % 60) as u8,
            seg: (resto / 1000 % 60) as u8,
            ms: (resto % 1000) as u16,
        }
    }
}

fn redactar_tras(texto: &str, marca: &str) -> String {
    let minus = texto.to_ascii_lowercase();
    let mut salida = String::with_capacity(texto.len());
    let mut desde = 0;
    while let Some(pos) = minus[desde..].find(marca) {
        let fin_marca = desde + pos + marca.len();
        let resto = &texto[fin_marca..];
        let seps = resto.len() - resto.trim_start_matches(['\\', '/']).len();
        let tras_seps = &resto[seps..];
        let largo = tras_seps.find(['\\', '/']).unwrap_or(tras_seps.len());
        salida.push_str(&texto[desde..fin_marca + seps]);
        if largo > 0 {
            salida.push('\u{2026}');
        }
        desde = fin_marca + seps + largo;
    }
    salida.push_str(&texto[desde..]);
    salida
}

pub fn limpiar_mensaje(s: &str) -> String {
    let sin_control: String = s
        .chars()
        .map(|c| if c.is_control() || c == '\u{2028}' || c == '\u{2029}' { ' ' } else { c })
        .collect();
    let redactado = redactar_tras(&redactar_tras(&sin_control, "\\users\\"), "/home/");
    let recortado: String = redactado.trim().chars().take(MENSAJE_MAX).collect();
    let recortado = recortado.trim_end().to_string();
    if recortado.is_empty() {
        "-".to_string()
    } else {
        recortado
    }
}

pub fn linea(f: &Fecha, n: Nivel, o: Origen, mensaje: &str) -> String {
    format!("{} {} {} {}", f.iso(), n.as_str(), o.as_str(), limpiar_mensaje(mensaje))
}

pub fn nombre_archivo(f: &Fecha) -> String {
    format!("colmena-{}.log", f.dia_iso())
}

fn fecha_de_nombre(nombre: &str) -> Option<(i32, u8, u8)> {
    let t = nombre.strip_prefix("colmena-")?.strip_suffix(".log")?;
    let b = t.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return None;
    }
    if !t.bytes().enumerate().all(|(i, c)| i == 4 || i == 7 || c.is_ascii_digit()) {
        return None;
    }
    let anio: i32 = t[0..4].parse().ok()?;
    let mes: u8 = t[5..7].parse().ok()?;
    let dia: u8 = t[8..10].parse().ok()?;
    if !(1..=12).contains(&mes) || !(1..=31).contains(&dia) {
        return None;
    }
    Some((anio, mes, dia))
}

pub fn archivos_viejos(nombres: &[String], hoy: &Fecha, dias: u32) -> Vec<String> {
    let hoy_dias = dias_desde_civil(hoy.anio, hoy.mes, hoy.dia);
    nombres
        .iter()
        .filter(|n| {
            fecha_de_nombre(n)
                .map(|(a, m, d)| hoy_dias - dias_desde_civil(a, m, d) > i64::from(dias))
                .unwrap_or(false)
        })
        .cloned()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn linea_tiene_el_formato_del_contrato() {
        let f = Fecha { anio: 2026, mes: 11, dia: 3, hora: 9, min: 5, seg: 7, ms: 42 };
        assert_eq!(
            linea(&f, Nivel::Aviso, Origen::Atajos, "Ctrl+Alt+V ocupado"),
            "2026-11-03T09:05:07.042 aviso atajos Ctrl+Alt+V ocupado"
        );
    }
    #[test]
    fn limpiar_reemplaza_control_y_saltos() {
        assert_eq!(limpiar_mensaje(" a\nb\r\tc\u{2028}d\u{7} "), "a b  c d");
    }
    #[test]
    fn limpiar_recorta_a_500_chars_sin_partir_multibyte() {
        let m = limpiar_mensaje(&"ñ".repeat(700));
        assert_eq!(m.chars().count(), MENSAJE_MAX);
    }
    #[test]
    fn limpiar_vacio_queda_guion() {
        assert_eq!(limpiar_mensaje(" \n "), "-");
    }
    #[test]
    fn redacta_rutas_de_usuario() {
        assert_eq!(limpiar_mensaje(r"no abre C:\Users\Ando\AppData\x.log"), r"no abre C:\Users\…\AppData\x.log");
        assert_eq!(limpiar_mensaje("falta /home/cc/.local/x"), "falta /home/…/.local/x");
        assert_eq!(limpiar_mensaje(r"c:\users\ando\x"), r"c:\users\…\x");
    }
    #[test]
    fn nivel_desde_acepta_solo_los_tres() {
        assert_eq!(Nivel::desde("error"), Some(Nivel::Error));
        assert_eq!(Nivel::desde("ERROR"), None);
        assert_eq!(Nivel::desde("debug"), None);
    }
    #[test]
    fn desde_unix_ms_convierte_fecha_civil() {
        assert_eq!(Fecha::desde_unix_ms(1_795_000_000_123).iso(), "2026-11-18T11:06:40.123");
    }
    #[test]
    fn archivos_viejos_borra_mas_de_7_dias_y_respeta_otros_nombres() {
        let hoy = Fecha { anio: 2026, mes: 3, dia: 2, hora: 0, min: 0, seg: 0, ms: 0 };
        let n: Vec<String> = [
            "colmena-2026-02-23.log",
            "colmena-2026-02-22.log",
            "colmena-2026-03-02.log",
            "pendientes.txt",
            "colmena-xx.log",
            "otro-2020-01-01.log",
        ]
        .map(String::from)
        .into();
        assert_eq!(archivos_viejos(&n, &hoy, DIAS_GUARDADO), vec!["colmena-2026-02-22.log".to_string()]);
    }

    #[test]
    fn redacta_rutas_con_separadores_repetidos() {
        let m = limpiar_mensaje(r"no abre C:\\Users\\Ando\\x");
        assert!(!m.contains("Ando") && m.contains('\u{2026}'));
        let m = limpiar_mensaje("falta /home//cc/x");
        assert!(!m.contains("cc") && m.contains('\u{2026}'));
    }
    #[test]
    fn recorte_no_deja_espacio_al_final() {
        let m = limpiar_mensaje(&format!("{} b", "a".repeat(499)));
        assert!(m.ends_with('a'));
    }
    #[test]
    fn archivos_viejos_ignora_nombres_con_signo() {
        let hoy = Fecha { anio: 2026, mes: 3, dia: 2, hora: 0, min: 0, seg: 0, ms: 0 };
        let n = vec!["colmena-2026-+1-01.log".to_string()];
        assert!(archivos_viejos(&n, &hoy, DIAS_GUARDADO).is_empty());
    }
}
