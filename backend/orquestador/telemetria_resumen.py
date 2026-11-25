"""Resumen semanal de la telemetría: lee los JSONL de un rango y calcula los números. Sin red ni reloj propio."""
import asyncio
import hashlib
import json
import logging
import math
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Awaitable, Callable

from .agenda import parse_dias, parse_hora, seconds_until_next
from .config import private_write

log = logging.getLogger(__name__)
STATE_FILE = "resumen-semanal.json"


def semana_iso(d: date) -> str:
    anio, semana, _ = d.isocalendar()
    return f"{anio}-W{semana:02d}"


def rango_semana(semana: str) -> tuple[datetime, datetime]:
    anio, num = semana.split("-W")
    lunes = date.fromisocalendar(int(anio), int(num), 1)
    domingo = lunes + timedelta(days=6)
    return (datetime.combine(lunes, time.min).astimezone(),
            datetime.combine(domingo, time(23, 59, 59)).astimezone())


def semana_anterior(hoy: date) -> str:
    return semana_iso(hoy - timedelta(days=7))


def _fecha(ts: object) -> datetime | None:
    try:
        cuando = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return cuando if cuando.tzinfo else cuando.astimezone()


def _meses(desde: datetime, hasta: datetime) -> list[str]:
    anio, mes = desde.year, desde.month
    meses = []
    while (anio, mes) <= (hasta.year, hasta.month):
        meses.append(f"{anio:04d}-{mes:02d}")
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return meses


def leer_eventos(directorio: Path, desde: datetime, hasta: datetime) -> list[dict]:
    eventos = []
    for mes in _meses(desde, hasta):
        try:
            texto = (Path(directorio) / f"{mes}.jsonl").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for linea in texto.splitlines():
            try:
                evento = json.loads(linea)
            except ValueError:
                continue
            cuando = _fecha(evento.get("ts")) if isinstance(evento, dict) else None
            if cuando is not None and desde <= cuando <= hasta:
                eventos.append(evento)
    return eventos


def mediana(xs) -> float | None:
    datos = sorted(xs)
    if not datos:
        return None
    medio = len(datos) // 2
    return datos[medio] if len(datos) % 2 else (datos[medio - 1] + datos[medio]) / 2


def p90(xs) -> float | None:
    datos = sorted(xs)
    return datos[math.ceil(0.9 * len(datos)) - 1] if datos else None


def hace(ts: str, ahora: datetime) -> str:
    cuando = _fecha(ts)
    if cuando is None:
        return ""
    segundos = max(0, int((ahora - cuando).total_seconds()))
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    if segundos < 86400:
        return f"hace {segundos // 3600} h"
    dias = segundos // 86400
    return f"hace {dias} día" + ("s" if dias != 1 else "")


def _de(eventos: list[dict], ev: str) -> list[dict]:
    return [e for e in eventos if e.get("ev") == ev]


def _cuenta(valores) -> dict:
    return dict(Counter(valores))


def _segundos(eventos: list[dict]) -> list[int]:
    return [e["segundos"] for e in eventos if isinstance(e.get("segundos"), int)]


def _clave_error(e: dict) -> tuple:
    return (e.get("plantilla"), e.get("logger"), e.get("tipo_exc"))


def _veces_por_error(eventos: list[dict]) -> Counter:
    total: Counter = Counter()
    for e in _de(eventos, "error_back"):
        total[_clave_error(e)] += e.get("n", 0)
    return total


def _errores(semana: list[dict], previa: list[dict], noventa: list[dict], ahora: datetime) -> dict:
    veces, antes_n = _veces_por_error(semana), _veces_por_error(previa)
    extremos: dict[tuple, list] = {}
    for e in _de(semana + previa + noventa, "error_back"):
        primera, ultima = _fecha(e.get("primera")), _fecha(e.get("ultima"))
        if primera is None or ultima is None:
            continue
        dato = extremos.setdefault(_clave_error(e), [primera, e["primera"], ultima, e["ultima"]])
        if primera < dato[0]:
            dato[0], dato[1] = primera, e["primera"]
        if ultima > dato[2]:
            dato[2], dato[3] = ultima, e["ultima"]
    ordenados = sorted(veces.items(), key=lambda kv: (-kv[1], kv[0][0] or ""))[:5]
    return {"top": [{"plantilla": clave[0], "logger": clave[1], "tipo_exc": clave[2], "n": n,
                     "delta": n - antes_n.get(clave, 0),
                     "primera": extremos[clave][1] if clave in extremos else None,
                     "ultima": extremos[clave][3] if clave in extremos else None,
                     "hace": hace(extremos[clave][3], ahora) if clave in extremos else ""}
                    for clave, n in ordenados],
            "ya_no": list(dict.fromkeys(c[0] for c, _ in antes_n.most_common() if c not in veces))}


def _pedidos(semana: list[dict]) -> dict:
    pedidos = _de(semana, "pedido")
    por_motivo: dict[str, Counter] = {}
    for p in pedidos:
        if p.get("estado") in ("rechazado", "vencido", "descartado"):
            por_motivo.setdefault(p["estado"], Counter())[p.get("motivo") or "sin_motivo"] += 1
    return {"por_tipo": _cuenta(p.get("tipo") or "otro" for p in pedidos),
            "por_origen": _cuenta(p.get("origen") for p in pedidos),
            "por_motivo": {estado: dict(c) for estado, c in por_motivo.items()},
            "mediana_s": mediana(_segundos(pedidos))}


def _grupo(respuestas: list[dict]) -> dict:
    xs = _segundos(respuestas)
    return {"mediana_s": mediana(xs), "p90_s": p90(xs), "n": len(xs)}


def _respuesta(semana: list[dict]) -> dict:
    respuestas = _de(semana, "respuesta")
    resultado: dict = {}
    for aviso in ("asks", "blocked"):
        del_aviso = [r for r in respuestas if r.get("aviso") == aviso and r.get("resultado") == "respondio"]
        resultado[aviso] = {
            "en_app": _grupo([r for r in del_aviso if r.get("en_app")]),
            "celu": _grupo([r for r in del_aviso if not r.get("en_app")])}
    resultado["sin_respuesta"] = sum(1 for r in respuestas if r.get("resultado") == "sin_respuesta")
    return resultado


def _trabas(semana: list[dict]) -> dict:
    trabas = _de(semana, "traba")
    fines = [t for t in trabas if t.get("fase") == "fin"]
    return {"por_tipo": _cuenta(t.get("tipo") for t in trabas if t.get("fase") == "inicio"),
            "mediana_s": mediana(_segundos(fines)),
            "por_fin": _cuenta(t.get("fin") for t in fines if t.get("fin"))}


def _comandos(semana: list[dict]) -> dict:
    comandos = _de(semana, "comando_sesion")
    return {"corridos": sum(1 for c in comandos if c.get("resultado") == "corrido"),
            "fallos": _cuenta(c.get("codigo") or "sin_codigo" for c in comandos if c.get("resultado") == "fallo"),
            "no": sum(1 for c in comandos if c.get("resultado") == "no")}


def _cierres(semana: list[dict]) -> dict:
    cierres = _de(semana, "cierre_frenado")
    resueltos = sum(1 for c in cierres if c.get("resuelto"))
    return {"frenados": len(cierres),
            "resueltos_pct": round(100 * resueltos / len(cierres)) if cierres else None}


def _app(semana: list[dict]) -> dict:
    app = _de(semana, "app")
    return {"errores": _cuenta(f"{a.get('origen')}/{a.get('codigo') or 'sin_codigo'}"
                               for a in app if a.get("ok") is False),
            "tuneles_fallidos": sum(1 for a in app if a.get("evento") == "tunel_fallo"),
            "desconexiones": sum(1 for a in app if a.get("evento") == "desconectado")}


def calcular(eventos_semana: list[dict], eventos_previa: list[dict], eventos_90: list[dict],
             ahora: datetime) -> dict:
    return {"errores": _errores(eventos_semana, eventos_previa, eventos_90, ahora),
            "pedidos": _pedidos(eventos_semana),
            "respuesta": _respuesta(eventos_semana),
            "trabas": _trabas(eventos_semana),
            "comandos": _comandos(eventos_semana),
            "cierres": _cierres(eventos_semana),
            "app": _app(eventos_semana)}


REGLAS = {
    "error_repetido": 20, "pedidos_vencen": 3, "pedidos_descartados": 5, "respuesta_lenta": 1800,
    "trabas_tipo": 5, "comandos_fallan": 3, "cierres_frenados": 10, "app_error": 5,
}
_MIN_RESPUESTAS_LENTAS = 5
_PCT_RESUELTOS_MIN = 80
_MAX_NUEVAS = 5
_SILENCIO = timedelta(days=30)
_PODA = timedelta(days=180)
_SEMANAS_SEGUIMIENTO = 2
_BAJA_MINIMA = 0.3


def _id(regla: str, clave: str) -> str:
    return hashlib.sha256(f"{regla}:{clave}".encode()).hexdigest()[:12]


_TOKEN = re.compile(r"[\w.\-]{1,60}")
_RUTA = re.compile(r"(?:[A-Za-z]:)?[\\/][^\s»]*")


def _token(valor: object) -> str:
    texto = str(valor)
    return texto if _TOKEN.fullmatch(texto) else "otro"


def _plantilla(valor: object) -> str:
    return _RUTA.sub("<ruta>", str(valor))[:200]


def _por_token(cuentas: dict) -> dict:
    total: Counter = Counter()
    for clave, n in cuentas.items():
        total[_token(clave)] += n
    return dict(total)


def _clave_app(clave: str) -> str:
    return "/".join(_token(parte) for parte in str(clave).split("/", 1))


def _por_clave_app(errores: dict) -> dict:
    total: Counter = Counter()
    for clave, n in errores.items():
        total[_clave_app(clave)] += n
    return dict(total)


def _clave_prop_error(e: dict) -> str:
    return f"{_plantilla(e['plantilla'])}|{_token(e['logger'])}|{_token(e['tipo_exc'])}"


def _cand(regla: str, clave: str, texto: str, nombre: str, valor: float, peso: float | None = None) -> dict:
    return {"id": _id(regla, clave), "regla": regla, "clave": clave, "texto": texto,
            "metrica": {"nombre": nombre, "valor": valor},
            "peso": valor / REGLAS[regla] if peso is None else peso}


def _reglas_errores(resumen: dict):
    for e in resumen["errores"]["top"]:
        if e["n"] >= REGLAS["error_repetido"]:
            ultima = f", última {e['hace']}" if e.get("hace") else ""
            yield _cand("error_repetido", _clave_prop_error(e),
                        f"Revisar «{_plantilla(e['plantilla'])}» ({_token(e['tipo_exc'])}): "
                        f"{e['n']} veces esta semana{ultima}", "veces_por_semana", e["n"])


def _reglas_pedidos(resumen: dict):
    por_motivo = resumen["pedidos"]["por_motivo"]
    vencidos = sum(por_motivo.get("vencido", {}).values())
    if vencidos >= REGLAS["pedidos_vencen"]:
        yield _cand("pedidos_vencen", "vencidos",
                    f"{vencidos} pedidos vencieron sin que los vieras: revisar cómo te llegan",
                    "vencidos_por_semana", vencidos)
    for motivo, n in sorted(_por_token(por_motivo.get("descartado", {})).items()):
        if n >= REGLAS["pedidos_descartados"]:
            yield _cand("pedidos_descartados", motivo,
                        f"{n} pedidos descartados por {motivo}: revisar si el límite es el justo",
                        "descartes_con_ese_motivo", n)


def _reglas_respuesta(resumen: dict):
    celu = resumen["respuesta"]["asks"]["celu"]
    mediana_s = celu["mediana_s"]
    if mediana_s is not None and mediana_s > REGLAS["respuesta_lenta"] and celu["n"] >= _MIN_RESPUESTAS_LENTAS:
        yield _cand("respuesta_lenta", "asks_celu",
                    f"Tardás {round(mediana_s / 60)} min de mediana en contestar preguntas que te llegan al celu",
                    "mediana_s", mediana_s)


def _reglas_trabas_comandos(resumen: dict):
    for tipo, n in sorted(_por_token(resumen["trabas"]["por_tipo"]).items()):
        if n >= REGLAS["trabas_tipo"]:
            yield _cand("trabas_tipo", tipo, f"{n} sesiones quedaron colgadas por traba de tipo {tipo}",
                        "trabas_por_semana", n)
    for codigo, n in sorted(_por_token(resumen["comandos"]["fallos"]).items()):
        if n >= REGLAS["comandos_fallan"]:
            yield _cand("comandos_fallan", codigo,
                        f"{n} comandos no se pudieron correr (código {codigo})", "fallos_por_semana", n)


def _reglas_cierres_app(resumen: dict):
    frenados, pct = resumen["cierres"]["frenados"], resumen["cierres"]["resueltos_pct"]
    pesos = []
    if frenados >= REGLAS["cierres_frenados"]:
        pesos.append(frenados / REGLAS["cierres_frenados"])
    if frenados >= 1 and pct is not None and pct < _PCT_RESUELTOS_MIN:
        pesos.append(_PCT_RESUELTOS_MIN / max(pct, 1))
    if pesos:
        sin_resolver = (f"; {round(frenados * (100 - pct) / 100)} no se arreglaron al primer intento"
                        if pct is not None else "")
        yield _cand("cierres_frenados", "frenados",
                    f"El control de cierre frenó {frenados} veces{sin_resolver}",
                    "frenados_por_semana", frenados, max(pesos))
    for clave, n in sorted(_por_clave_app(resumen["app"]["errores"]).items()):
        if n >= REGLAS["app_error"]:
            yield _cand("app_error", clave, f"La app de Windows falló {n} veces ({clave})",
                        "veces_por_semana", n)


def candidatas(resumen: dict) -> list[dict]:
    return [c for generar in (_reglas_errores, _reglas_pedidos, _reglas_respuesta,
                              _reglas_trabas_comandos, _reglas_cierres_app) for c in generar(resumen)]


def metrica_de(resumen: dict, regla: str, clave: str) -> float | None:
    if regla == "error_repetido":
        return next((e["n"] for e in resumen["errores"]["top"] if _clave_prop_error(e) == clave), None)
    if regla == "pedidos_vencen":
        return sum(resumen["pedidos"]["por_motivo"].get("vencido", {}).values())
    if regla == "pedidos_descartados":
        return _por_token(resumen["pedidos"]["por_motivo"].get("descartado", {})).get(clave, 0)
    if regla == "respuesta_lenta":
        return resumen["respuesta"]["asks"]["celu"]["mediana_s"]
    if regla == "trabas_tipo":
        return _por_token(resumen["trabas"]["por_tipo"]).get(clave, 0)
    if regla == "comandos_fallan":
        return _por_token(resumen["comandos"]["fallos"]).get(clave, 0)
    if regla == "cierres_frenados":
        return resumen["cierres"]["frenados"]
    if regla == "app_error":
        return _por_clave_app(resumen["app"]["errores"]).get(clave, 0)
    return None


def _num_semana(semana: str) -> int:
    anio, num = semana.split("-W")
    return date.fromisocalendar(int(anio), int(num), 1).toordinal() // 7


def _tendencia(base: float | None, valor: float | None) -> str:
    if base is None or valor is None:
        return "igual"
    if valor * 10 <= base * 9:
        return "bajo"
    return "subio" if valor * 10 >= base * 11 else "igual"


class PropuestasStore:
    def __init__(self, path: Path, wall: Callable[[], datetime]):
        self.path, self.wall = path, wall

    def cargar(self) -> dict:
        try:
            datos = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return datos if isinstance(datos, dict) else {}

    def _guardar(self, datos: dict) -> None:
        private_write(self.path, json.dumps(datos, ensure_ascii=False, indent=1))

    def decidir(self, pid: str, decision: str, semana: str, metrica_actual: float | None,
                cand: dict | None = None) -> dict:
        datos = self.cargar()
        ahora = self.wall()
        e = datos.get(pid) or {"regla": None, "clave": None, "metrica": {"nombre": None}, "seguimiento": []}
        if cand:
            self._conocer(e, cand)
        e.update(estado=decision, decidida=ahora.isoformat(), actualizada=ahora.isoformat(),
                 silenciada_hasta=(ahora + _SILENCIO).isoformat() if decision == "ignorar" else None)
        if decision == "hacer":
            e["metrica"].update(base=metrica_actual, semana_base=semana)
            e["seguimiento"] = []
        datos[pid] = e
        self._guardar(datos)
        return e

    @staticmethod
    def _conocer(e: dict, c: dict) -> bool:
        if e.get("regla") is not None:
            return False
        e.update(regla=c["regla"], clave=c["clave"])
        e["metrica"]["nombre"] = c["metrica"]["nombre"]
        return True

    def _silenciada(self, e: dict, ahora: datetime) -> bool:
        hasta = e.get("silenciada_hasta")
        return e.get("estado") == "ignorar" and bool(hasta) and datetime.fromisoformat(hasta) > ahora

    @staticmethod
    def _anotar(e: dict, semana: str, valor: float | None) -> bool:
        if valor is None or semana == e["metrica"].get("semana_base"):
            return False
        previo = next((s for s in e["seguimiento"] if s["semana"] == semana), None)
        if previo is None:
            e["seguimiento"].append({"semana": semana, "valor": valor})
        elif previo["valor"] != valor:
            previo["valor"] = valor
        else:
            return False
        return True

    @staticmethod
    def _texto_ausente(e: dict, valor: float | None) -> str:
        dato = "bajo el umbral" if valor is None else f"{valor:g} esta semana"
        return f"{e['regla']} {e['clave']}: {dato}"

    def _seguimiento(self, datos: dict, por_id: dict, semana: str, resumen: dict | None) -> tuple[list, list, bool]:
        seguimiento, volvieron, cambio = [], [], False
        for pid, e in datos.items():
            if e.get("estado") != "hacer" or e["metrica"].get("semana_base") is None:
                continue
            c = por_id.get(pid)
            if e.get("regla") is None and c:
                cambio = self._conocer(e, c) or cambio
            if c:
                valor = c["metrica"]["valor"]
            else:
                valor = metrica_de(resumen, e["regla"], e["clave"]) if resumen and e.get("regla") else None
            if e["metrica"].get("base") is None and valor is not None:
                e["metrica"].update(base=valor, semana_base=semana)
                cambio = True
            base = e["metrica"].get("base")
            cambio = self._anotar(e, semana, valor) or cambio
            pasaron = _num_semana(semana) - _num_semana(e["metrica"]["semana_base"])
            baja_ok = base is not None and valor is not None and valor <= base * (1 - _BAJA_MINIMA)
            if pasaron >= _SEMANAS_SEGUIMIENTO and baja_ok:
                e.update(estado="cumplida", cumplida=semana)
                cambio = True
            elif pasaron >= _SEMANAS_SEGUIMIENTO and valor is not None and base is not None:
                volvieron.append(c if c else {
                    "id": pid, "regla": e["regla"], "clave": e["clave"], "texto": self._texto_ausente(e, valor),
                    "metrica": {"nombre": e["metrica"].get("nombre"), "valor": valor},
                    "peso": valor / REGLAS[e["regla"]]})
            elif pasaron >= 0:
                seguimiento.append({"id": pid, "texto": c["texto"] if c else self._texto_ausente(e, valor),
                                    "base": base, "valor": valor, "tendencia": _tendencia(base, valor)})
        return seguimiento, [{**c, "volvio": True} for c in volvieron], cambio

    def elegir(self, cands: list[dict], semana: str, resumen: dict | None = None) -> dict:
        datos, ahora = self.cargar(), self.wall()
        por_id = {c["id"]: c for c in cands}
        cambio = False
        nuevas, pie = [], []
        for c in cands:
            e = datos.get(c["id"])
            if e is None:
                nuevas.append(c)
                continue
            self._conocer(e, c)
            e["actualizada"] = ahora.isoformat()
            cambio = True
            if self._silenciada(e, ahora):
                continue
            if e.get("estado") == "mas_adelante":
                pie.append(c)
            elif e.get("estado") != "hacer":
                nuevas.append(c)
        seguimiento, volvieron, cambio_seg = self._seguimiento(datos, por_id, semana, resumen)
        if cambio or cambio_seg:
            self._guardar(datos)
        nuevas = sorted(nuevas + volvieron, key=lambda c: -c["peso"])[:_MAX_NUEVAS]
        return {"nuevas": nuevas, "mas_adelante": pie, "seguimiento": seguimiento,
                "volvio": [c for c in nuevas if c.get("volvio")]}

    def registrar(self, cands: list[dict]) -> None:
        datos, ahora, cambio = self.cargar(), self.wall(), False
        for c in cands:
            if c["id"] in datos:
                continue
            datos[c["id"]] = {"regla": c["regla"], "clave": c["clave"], "metrica": {"nombre": c["metrica"]["nombre"]},
                              "estado": "propuesta", "seguimiento": [], "actualizada": ahora.isoformat()}
            cambio = True
        if cambio:
            self._guardar(datos)

    def podar(self) -> int:
        datos, limite = self.cargar(), self.wall() - _PODA
        viejas = [pid for pid, e in datos.items()
                  if datetime.fromisoformat(e.get("actualizada") or e["decidida"]) < limite]
        for pid in viejas:
            del datos[pid]
        if viejas:
            self._guardar(datos)
        return len(viejas)


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


def _mediana_respuesta(resumen: dict) -> float | None:
    grupos = [g for g in resumen["respuesta"]["asks"].values() if g.get("mediana_s") is not None and g.get("n")]
    return max(grupos, key=lambda g: g["n"])["mediana_s"] if grupos else None


def _cuerpo(resumen: dict, propuestas: int) -> str:
    partes = []
    if propuestas:
        partes.append(_plural(propuestas, "propuesta", "propuestas"))
    errores = sum(e["n"] for e in resumen["errores"]["top"] if isinstance(e["n"], int))
    if errores:
        partes.append(_plural(errores, "error", "errores"))
    mediana_s = _mediana_respuesta(resumen)
    if mediana_s is not None:
        partes.append(f"respuesta mediana {round(mediana_s / 60)} min" if mediana_s >= 60
                      else f"respuesta mediana {round(mediana_s)} s")
    return " · ".join(partes) or "Sin novedades esta semana"


def _seguro(paso: Callable[[], object], nombre: str) -> None:
    try:
        paso()
    except Exception as exc:
        log.warning("el resumen semanal no pudo %s: %s", nombre, type(exc).__name__)


async def generar_resumen(*, directorio: Path, semana: str, propuestas: PropuestasStore, biblioteca, push, handler,
                          telemetria, ahora: datetime, avisar: bool = True, guardar: bool = True) -> dict:
    _seguro(handler.flush, "volcar los errores")
    _seguro(telemetria.borrar_viejos, "borrar la telemetría vieja")
    _seguro(lambda: biblioteca.quitar_resumenes_viejos(ahora), "quitar resúmenes viejos")
    _seguro(propuestas.podar, "podar propuestas")
    desde, hasta = rango_semana(semana)
    p_desde, p_hasta = rango_semana(semana_anterior(desde.date()))
    eventos = leer_eventos(directorio, desde, hasta)
    previa = leer_eventos(directorio, p_desde, p_hasta)
    noventa = leer_eventos(directorio, desde - timedelta(days=90), hasta)
    resumen = calcular(eventos, previa, noventa, ahora)
    cands = candidatas(resumen)
    elegidas = propuestas.elegir(cands, semana, resumen)
    propuestas.registrar(elegidas["nuevas"] + elegidas["mas_adelante"])
    datos = {"semana": semana, "desde": desde.date().isoformat(), "hasta": hasta.date().isoformat(),
             "resumen": resumen, "propuestas": elegidas, "generado": ahora.timestamp()}
    ident = ""
    if guardar:
        ident = biblioteca.agregar_resumen(datos)
        telemetria.anotar("resumen", semana=semana, propuestas=len(elegidas["nuevas"]))
    if avisar:
        await push.dispatch_simple("resumen", {
            "title": "Resumen de la semana", "body": _cuerpo(resumen, len(elegidas["nuevas"])), "kind": "resumen",
            "tag": "resumen", "url": f"/?biblioteca={ident}", "session_id": ""}, pref="resumen")
    return datos


class ResumenSemanal:
    def __init__(self, directory: Path, hora: Callable[[], str], dias: Callable[[], list],
                 ejecutar: Callable[[str], Awaitable], now: Callable[[], datetime] | None = None,
                 sleep=asyncio.sleep):
        self.path = directory / STATE_FILE
        self.hora, self.dias, self.ejecutar = hora, dias, ejecutar
        self._now = now or (lambda: datetime.now().astimezone())
        self._sleep = sleep

    def _ultima(self) -> str:
        try:
            valor = json.loads(self.path.read_text(encoding="utf-8")).get("ultima_semana")
        except (OSError, ValueError, AttributeError):
            return ""
        return valor if isinstance(valor, str) else ""

    def marcar(self, semana: str) -> None:
        try:
            private_write(self.path, json.dumps({"ultima_semana": semana}))
        except OSError as exc:
            log.warning("no pude guardar el resumen semanal: %s", type(exc).__name__)

    def _corrida(self, hoy: date, hora: tuple) -> datetime:
        dia = hoy - timedelta(days=hoy.weekday()) + timedelta(days=min(parse_dias(self.dias())))
        return datetime.combine(dia, time(*hora)).astimezone()

    async def run(self) -> None:
        while True:
            tick_fallo = False
            try:
                hora = parse_hora(self.hora())
            except Exception:
                log.exception("el resumen semanal falló al leer la hora")
                await self._sleep(600)
                continue
            if hora is None:
                return
            try:
                await self.tick()
            except Exception:
                log.exception("el resumen semanal falló")
                tick_fallo = True
            try:
                espera = seconds_until_next(hora, [min(parse_dias(self.dias()))], self._now())
            except Exception:
                log.exception("el resumen semanal falló al calcular la espera")
                await self._sleep(600)
                continue
            await self._sleep(min(600, espera) if tick_fallo else espera)

    async def tick(self) -> bool:
        hora = parse_hora(self.hora())
        ahora = self._now()
        if hora is None or ahora < self._corrida(ahora.date(), hora):
            return False
        semana = semana_anterior(ahora.date())
        if self._ultima() == semana:
            return False
        self.marcar(semana)
        await self.ejecutar(semana)
        return True
