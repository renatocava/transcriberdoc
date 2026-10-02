"""Modelos Pydantic del formulario de historia clínica.

El JSON Schema derivado de `HistoriaClinica` se usa como `input_schema`
del tool que Claude debe llenar.
"""

from __future__ import annotations

import copy
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Paciente(BaseModel):
    nombre: str = ""
    edad: Optional[int] = None
    sexo: Optional[Literal["M", "F", "Otro"]] = None


class Antecedentes(BaseModel):
    personales: list[str] = []
    alergias: list[str] = []
    medicamentos_actuales: list[str] = []


class SignosVitales(BaseModel):
    presion_arterial: str = ""
    frecuencia_cardiaca: str = ""
    temperatura: str = ""
    saturacion_oxigeno: str = ""


class ExamenFisico(BaseModel):
    signos_vitales: SignosVitales = SignosVitales()
    hallazgos: str = ""


class Diagnostico(BaseModel):
    descripcion: str
    tipo: Literal["presuntivo", "definitivo", "diferencial"]
    cie10: str = Field(
        "",
        description=(
            "Código CIE-10 más específico que respalde la consulta, con punto (J03.9). "
            "Vacío si no estás seguro."
        ),
    )
    cie10_alternativas: list[str] = Field(
        [],
        description="Hasta 3 códigos CIE-10 alternativos razonables, por si el principal no es el adecuado.",
    )


class Medicamento(BaseModel):
    nombre: str
    dosis: str = ""
    frecuencia: str = ""
    duracion: str = ""


class Plan(BaseModel):
    medicamentos: list[Medicamento] = []
    examenes_solicitados: list[str] = []
    indicaciones: list[str] = []
    proxima_cita: str = ""


class HistoriaClinica(BaseModel):
    paciente: Paciente = Paciente()
    motivo_consulta: str = Field(..., description="Razón principal de la consulta, 1-2 oraciones")
    enfermedad_actual: str = Field(..., description="Relato cronológico del problema actual")
    antecedentes: Antecedentes = Antecedentes()
    examen_fisico: ExamenFisico = ExamenFisico()
    diagnosticos: list[Diagnostico] = Field(..., description="Lista de diagnósticos")
    plan: Plan = Field(..., description="Plan terapéutico")


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Aplana los `$ref`/`$defs` que genera Pydantic.

    El `input_schema` de un tool de Anthropic no resuelve referencias de forma
    confiable, así que las expandimos in situ antes de enviarlo.
    """
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                nombre = node["$ref"].rsplit("/", 1)[-1]
                resuelto = walk(copy.deepcopy(defs[nombre]))
                resuelto.update({k: v for k, v in node.items() if k != "$ref"})
                return resuelto
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(schema)


def historia_input_schema() -> dict[str, Any]:
    """JSON Schema autocontenido de `HistoriaClinica`, listo para tool use."""
    return _inline_refs(HistoriaClinica.model_json_schema())


def historia_vacia() -> dict[str, Any]:
    """Historia con todos los campos presentes y vacíos."""
    return HistoriaClinica(
        motivo_consulta="", enfermedad_actual="", diagnosticos=[], plan=Plan()
    ).model_dump()


def normalizar_historia(data: dict[str, Any]) -> dict[str, Any]:
    """Valida lo que devolvió el modelo y rellena los campos ausentes.

    Nunca levanta excepción: la demo prefiere un formulario incompleto
    a una pantalla de error.
    """
    base = historia_vacia()
    datos = {**base, **(data or {})}
    for clave in ("paciente", "antecedentes", "examen_fisico", "plan"):
        if isinstance(datos.get(clave), dict):
            datos[clave] = {**base[clave], **datos[clave]}
    if isinstance(datos.get("examen_fisico", {}).get("signos_vitales"), dict):
        datos["examen_fisico"]["signos_vitales"] = {
            **base["examen_fisico"]["signos_vitales"],
            **datos["examen_fisico"]["signos_vitales"],
        }
    try:
        return HistoriaClinica.model_validate(datos).model_dump()
    except Exception:
        return datos
