from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

MAX_ITEMS = 200
MAX_ID = 200
MAX_GRUPOS = 200
MAX_GRUPO = 200


def normalizar_orden(raw: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or len(item) < 1 or len(item) > MAX_ID:
            raise ValueError("id inválido")
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) > MAX_ITEMS:
            raise ValueError("demasiados")
    return out


class OrdenTableroBody(BaseModel):
    orden: list[str]

    @field_validator("orden")
    @classmethod
    def validar(cls, v: list) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("orden debe ser una lista")
        if len(v) > MAX_ITEMS:
            raise ValueError("demasiados")
        return normalizar_orden(v)


def normalizar_grupo(grupo: str) -> str:
    if not isinstance(grupo, str) or len(grupo) < 1 or len(grupo) > MAX_GRUPO:
        raise ValueError("grupo inválido")
    return grupo


class PlegadasBody(BaseModel):
    plegadas: list[str]

    @field_validator("plegadas")
    @classmethod
    def validar(cls, v: list) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("plegadas debe ser una lista")
        if len(v) > MAX_ITEMS:
            raise ValueError("demasiados")
        return normalizar_orden(v)


class OrdenPestanasBody(BaseModel):
    grupo: str
    orden: list[str]

    @field_validator("grupo")
    @classmethod
    def validar_grupo(cls, v: str) -> str:
        return normalizar_grupo(v)

    @field_validator("orden")
    @classmethod
    def validar_orden(cls, v: list) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("orden debe ser una lista")
        if len(v) > MAX_ITEMS:
            raise ValueError("demasiados")
        return normalizar_orden(v)


class SilencioBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: StrictBool
