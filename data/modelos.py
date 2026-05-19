# ============================================================
#  data/modelos.py
#  Modelos de datos para el planificador academico.
#  Solo contiene las clases y funciones constructoras,
#  los datos reales se cargan desde la BD en db_programas.py
# ============================================================

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set


# -- Modelos base ---------------------------------------------

@dataclass
class Materia:
    codigo: str
    nombre: str
    creditos: int
    nivel: int
    prerrequisitos: List[str] = field(default_factory=list)
    es_proyecto: bool = False
    es_practica: bool = False
    proyecto_compartido: Optional[str] = None


@dataclass
class GrupoElectiva:
    tipo_codigo: str
    nombre: str
    cantidad: int
    creditos_cu: int
    slot_codigos: List[str]
    opciones: List[Materia] = field(default_factory=list)

    @property
    def slots(self) -> List[str]:
        return self.slot_codigos[:self.cantidad]


@dataclass
class Programa:
    codigo: str
    nombre: str
    facultad: str
    materias: List[Materia] = field(default_factory=list)
    grupos_electivas: List[GrupoElectiva] = field(default_factory=list)

    # Caches internos para evitar recorrer listas en cada consulta
    _placeholders: Dict[str, str] = field(default_factory=dict, repr=False)
    _materias_obligatorias: Dict[str, Materia] = field(default_factory=dict, repr=False)
    _materias_por_nivel: Dict[int, List[Materia]] = field(default_factory=dict, repr=False)
    _codigos_practica: Set[str] = field(default_factory=set, repr=False)
    _codigos_proyecto: Set[str] = field(default_factory=set, repr=False)
    _opciones_electivas: Dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._calcular_caches()

    def _calcular_caches(self):
        for ge in self.grupos_electivas:
            for slot in ge.slot_codigos:
                self._placeholders[slot] = ge.tipo_codigo

        for m in self.materias:
            if m.codigo not in self._placeholders:
                self._materias_obligatorias[m.codigo] = m

        for m in self.materias:
            if m.nivel not in self._materias_por_nivel:
                self._materias_por_nivel[m.nivel] = []
            self._materias_por_nivel[m.nivel].append(m)

        for m in self.materias:
            if m.es_practica:
                self._codigos_practica.add(m.codigo)
            if m.es_proyecto:
                self._codigos_proyecto.add(m.codigo)

        for ge in self.grupos_electivas:
            for opt in ge.opciones:
                self._opciones_electivas[opt.codigo] = ge.tipo_codigo

    @property
    def placeholders(self) -> Dict[str, str]:
        return self._placeholders

    @property
    def materias_obligatorias(self) -> Dict[str, Materia]:
        return self._materias_obligatorias

    @property
    def materias_obligatorias_lista(self) -> List[Materia]:
        return list(self._materias_obligatorias.values())

    @property
    def codigos_practica(self) -> Set[str]:
        return self._codigos_practica

    @property
    def codigos_proyecto(self) -> Set[str]:
        return self._codigos_proyecto

    def get_materia(self, codigo: str) -> Optional[Materia]:
        for m in self.materias:
            if m.codigo == codigo:
                return m
        return None

    def get_materias_por_nivel(self, nivel: int) -> List[Materia]:
        return self._materias_por_nivel.get(nivel, [])

    def es_placeholder(self, codigo: str) -> bool:
        return codigo in self._placeholders

    def es_obligatoria(self, codigo: str) -> bool:
        return codigo in self._materias_obligatorias

    def es_practica(self, codigo: str) -> bool:
        return codigo in self._codigos_practica

    def es_proyecto(self, codigo: str) -> bool:
        return codigo in self._codigos_proyecto

    def es_opcion_electiva(self, codigo: str) -> Optional[str]:
        return self._opciones_electivas.get(codigo)

    def get_grupo_electiva(self, tipo_codigo: str) -> Optional[GrupoElectiva]:
        for ge in self.grupos_electivas:
            if ge.tipo_codigo == tipo_codigo:
                return ge
        return None

    def total_creditos(self) -> int:
        obligatorios = sum(m.creditos for m in self._materias_obligatorias.values())
        electivas = sum(g.cantidad * g.creditos_cu for g in self.grupos_electivas)
        return obligatorios + electivas


# -- Constructores desde diccionario (usados por db_programas.py) -------------

def crear_materia(data) -> Materia:
    if isinstance(data, Materia):
        return data
    return Materia(
        codigo=data["codigo"],
        nombre=data["nombre"],
        creditos=data["creditos"],
        nivel=data["nivel"],
        prerrequisitos=data.get("prerrequisitos", []),
        es_proyecto=data.get("es_proyecto", False),
        es_practica=data.get("es_practica", False),
        proyecto_compartido=data.get("proyecto_compartido", None),
    )


def crear_grupo_electiva(data) -> GrupoElectiva:
    opciones = [crear_materia(opt) for opt in data.get("opciones", [])]
    return GrupoElectiva(
        tipo_codigo=data["tipo_codigo"],
        nombre=data["nombre"],
        cantidad=data["cantidad"],
        creditos_cu=data["creditos_cu"],
        slot_codigos=data["slot_codigos"],
        opciones=opciones,
    )


def crear_programa(data: dict) -> Programa:
    materias = [crear_materia(m) for m in data.get("materias", [])]
    grupos = [crear_grupo_electiva(g) for g in data.get("grupos_electivas", [])]
    return Programa(
        codigo=data["codigo"],
        nombre=data["nombre"],
        facultad=data["facultad"],
        materias=materias,
        grupos_electivas=grupos,
    )


# -- Utilidad para el planificador ----------------------------

def get_codigos_practica(programas: Dict[str, Programa]) -> Dict[str, str]:
    """Devuelve {codigo_programa: codigo_materia_practica} para cada programa."""
    resultado = {}
    for codigo, prog in programas.items():
        if prog.codigos_practica:
            resultado[codigo] = list(prog.codigos_practica)[0]
    return resultado
