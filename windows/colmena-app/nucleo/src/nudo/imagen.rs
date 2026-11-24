use base64::Engine;
use serde::Serialize;

use super::ERR_FALLO_PC;

pub const TOPE_IMAGEN: usize = 4 * 1024 * 1024;
pub const CALIDAD_JPEG: u8 = 80;

#[derive(Serialize, Debug)]
pub struct ImagenCodificada {
    pub tipo: &'static str,
    pub ancho: u32,
    pub alto: u32,
    pub b64: String,
}

fn fallo<E>(_: E) -> String {
    ERR_FALLO_PC.to_string()
}

fn a_rgb(bgra: &[u8]) -> Vec<u8> {
    bgra.chunks_exact(4).flat_map(|p| [p[2], p[1], p[0]]).collect()
}

fn a_png(rgb: &[u8], ancho: u32, alto: u32) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    let mut enc = png::Encoder::new(&mut out, ancho, alto);
    enc.set_color(png::ColorType::Rgb);
    enc.set_depth(png::BitDepth::Eight);
    let mut w = enc.write_header().map_err(fallo)?;
    w.write_image_data(rgb).map_err(fallo)?;
    w.finish().map_err(fallo)?;
    Ok(out)
}

fn a_jpeg(rgb: &[u8], ancho: u32, alto: u32) -> Result<Vec<u8>, String> {
    let a = u16::try_from(ancho).map_err(fallo)?;
    let h = u16::try_from(alto).map_err(fallo)?;
    let mut out = Vec::new();
    jpeg_encoder::Encoder::new(&mut out, CALIDAD_JPEG)
        .encode(rgb, a, h, jpeg_encoder::ColorType::Rgb)
        .map_err(fallo)?;
    Ok(out)
}

pub fn codificar(bgra: &[u8], ancho: u32, alto: u32, tope: usize) -> Result<ImagenCodificada, String> {
    if ancho == 0 || alto == 0 || bgra.len() as u64 != ancho as u64 * alto as u64 * 4 {
        return Err(ERR_FALLO_PC.into());
    }
    let rgb = a_rgb(bgra);
    let b64 = |b: &[u8]| base64::engine::general_purpose::STANDARD.encode(b);
    let png = a_png(&rgb, ancho, alto)?;
    if png.len() <= tope {
        return Ok(ImagenCodificada { tipo: "png", ancho, alto, b64: b64(&png) });
    }
    let jpeg = a_jpeg(&rgb, ancho, alto)?;
    if jpeg.len() > tope {
        return Err(ERR_FALLO_PC.into());
    }
    Ok(ImagenCodificada { tipo: "jpeg", ancho, alto, b64: b64(&jpeg) })
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine;
    fn dec(s: &str) -> Vec<u8> { base64::engine::general_purpose::STANDARD.decode(s).unwrap() }
    fn ruido() -> Vec<u8> {
        let mut s: u32 = 12345;
        (0..64 * 64 * 4).map(|_| { s = s.wrapping_mul(1664525).wrapping_add(1013904223); (s >> 24) as u8 }).collect()
    }
    #[test] fn png_chico() {
        let r = codificar(&[0u8; 2 * 2 * 4], 2, 2, TOPE_IMAGEN).unwrap();
        assert_eq!((r.tipo, r.ancho, r.alto), ("png", 2, 2));
        assert!(dec(&r.b64).starts_with(b"\x89PNG\r\n\x1a\n"));
    }
    #[test] fn jpeg_si_el_png_se_pasa() {
        let b = ruido();
        let png = codificar(&b, 64, 64, usize::MAX).unwrap();
        assert_eq!(png.tipo, "png");
        let tam = dec(&png.b64).len();
        let r = codificar(&b, 64, 64, tam - 1).unwrap();
        assert_eq!(r.tipo, "jpeg");
        assert!(dec(&r.b64).starts_with(&[0xFF, 0xD8, 0xFF]));
    }
    #[test] fn ni_jpeg_entra_es_fallo_pc() {
        assert_eq!(codificar(&ruido(), 64, 64, 10).unwrap_err(), "fallo_pc");
    }
    #[test] fn largo_incorrecto_es_fallo_pc() {
        assert_eq!(codificar(&[0u8; 15], 2, 2, TOPE_IMAGEN).unwrap_err(), "fallo_pc");
    }
}
