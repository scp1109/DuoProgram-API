# ============================================================
#  data/programas.py
#  Mallas curriculares UTB — Ultra generalizado
#  Agregar nuevo programa = solo agregar un diccionario
# ============================================================

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any
from copy import deepcopy


# ============================================================
# CLASES BASE
# ============================================================

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


# ============================================================
# CONSTANTES GLOBALES
# ============================================================

CODIGOS_INGLES = ["CHUL_LE1A", "CHUL_LE2A", "CHUL_LE3A", "CHUL_LE4A", "CHUL_LE5A"]


# ============================================================
# DEFINICIÓN DE PROGRAMAS (SOLO DICCIONARIOS)
# ============================================================

PROGRAMAS_DATA = {
    
    "ISCO": {
        "codigo": "ISCO",
        "nombre": "Ingeniería de Sistemas y Computación",
        "facultad": "Facultad de Ingeniería",
        "materias": [
            # NIVEL 1
            {"codigo": "CHUM_H01A", "nombre": "Taller de Comprensión Lectora", "creditos": 3, "nivel": 1},
            {"codigo": "CBAS_M01A", "nombre": "Cálculo Diferencial", "creditos": 4, "nivel": 1},
            {"codigo": "CBAS_M02A", "nombre": "Matemáticas Básicas", "creditos": 2, "nivel": 1},
            {"codigo": "CBAS_Q01A", "nombre": "Química General", "creditos": 3, "nivel": 1},
            {"codigo": "ECOU_U01A", "nombre": "Desarrollo Universitario", "creditos": 0, "nivel": 1},
            {"codigo": "ISCO_C01A", "nombre": "Sem. Ing. Sistemas y Computación", "creditos": 1, "nivel": 1},
            {"codigo": "ISCO_C02A", "nombre": "Fundamentos de Programación", "creditos": 3, "nivel": 1},
            # NIVEL 2
            {"codigo": "CHUL_LE1A", "nombre": "Lengua Extranjera I", "creditos": 2, "nivel": 2},
            {"codigo": "CBAS_F01A", "nombre": "Física Mecánica", "creditos": 4, "nivel": 2, "prerrequisitos": ["CBAS_M01A"]},
            {"codigo": "CBAS_M03A", "nombre": "Cálculo Integral", "creditos": 4, "nivel": 2, "prerrequisitos": ["CBAS_M01A"]},
            {"codigo": "CBAS_M04A", "nombre": "Álgebra Lineal", "creditos": 3, "nivel": 2, "prerrequisitos": ["CBAS_M02A"]},
            {"codigo": "ISCO_C03A", "nombre": "Programación", "creditos": 3, "nivel": 2, "prerrequisitos": ["ISCO_C02A"]},
            # NIVEL 3
            {"codigo": "CHUL_LE2A", "nombre": "Lengua Extranjera II", "creditos": 2, "nivel": 3, "prerrequisitos": ["CHUL_LE1A"]},
            {"codigo": "CHUM_H02A", "nombre": "Taller de Escritura Académica", "creditos": 3, "nivel": 3},
            {"codigo": "CBAS_F02A", "nombre": "Física Electricidad y Magnetismo", "creditos": 4, "nivel": 3, "prerrequisitos": ["CBAS_F01A", "CBAS_M03A"]},
            {"codigo": "CBAS_M05A", "nombre": "Cálculo Vectorial", "creditos": 4, "nivel": 3, "prerrequisitos": ["CBAS_M03A"]},
            {"codigo": "ISCO_C04A", "nombre": "Programación Orientada a Objetos", "creditos": 3, "nivel": 3, "prerrequisitos": ["ISCO_C03A"]},
            # NIVEL 4
            {"codigo": "CHUL_LE3A", "nombre": "Lengua Extranjera III", "creditos": 2, "nivel": 4, "prerrequisitos": ["CHUL_LE2A"]},
            {"codigo": "CBAS_F03A", "nombre": "Física Calor y Ondas", "creditos": 4, "nivel": 4, "prerrequisitos": ["CBAS_F01A"]},
            {"codigo": "CBAS_M06A", "nombre": "Ecuaciones Dif. y en Diferencia", "creditos": 4, "nivel": 4, "prerrequisitos": ["CBAS_M05A"]},
            {"codigo": "ISCO_C05A", "nombre": "Estructura de Datos", "creditos": 3, "nivel": 4, "prerrequisitos": ["ISCO_C04A"]},
            {"codigo": "ISCO_C06A", "nombre": "Matemática Discreta", "creditos": 3, "nivel": 4, "prerrequisitos": ["ISCO_C04A"]},
            # NIVEL 5
            {"codigo": "CHUL_LE4A", "nombre": "Lengua Extranjera IV", "creditos": 2, "nivel": 5, "prerrequisitos": ["CHUL_LE3A"]},
            {"codigo": "CHUM_H03A", "nombre": "Constitución Política", "creditos": 2, "nivel": 5},
            {"codigo": "CBAS_E01A", "nombre": "Estadística y Probabilidad", "creditos": 3, "nivel": 5, "prerrequisitos": ["CBAS_M03A"]},
            {"codigo": "ISCO_A01A", "nombre": "Base de Datos", "creditos": 3, "nivel": 5, "prerrequisitos": ["ISCO_C05A"]},
            {"codigo": "ISCO_A02A", "nombre": "Desarrollo de Software", "creditos": 3, "nivel": 5, "prerrequisitos": ["ISCO_C04A"]},
            {"codigo": "ISCO_A03A", "nombre": "Algoritmo y Complejidad", "creditos": 3, "nivel": 5, "prerrequisitos": ["ISCO_C05A"]},
            # NIVEL 6
            {"codigo": "CHUL_LE5A", "nombre": "Lengua Extranjera V", "creditos": 2, "nivel": 6, "prerrequisitos": ["CHUL_LE4A"]},
            {"codigo": "AEMP_G04A", "nombre": "Creatividad y Emprendimiento", "creditos": 3, "nivel": 6},
            {"codigo": "ISCO_A04A", "nombre": "Arquitectura de Software", "creditos": 3, "nivel": 6, "prerrequisitos": ["ISCO_A02A"]},
            {"codigo": "ISCO_C07A", "nombre": "Procesamiento Numérico", "creditos": 3, "nivel": 6, "prerrequisitos": ["ISCO_C04A", "CBAS_M06A"]},
            {"codigo": "ISCO_C08A", "nombre": "Comunicaciones y Redes", "creditos": 3, "nivel": 6, "prerrequisitos": ["ISCO_C05A"]},
            # NIVEL 7
            {"codigo": "CHUM_H05A", "nombre": "Ciudadanía Global", "creditos": 2, "nivel": 7},
            {"codigo": "ECON_M12A", "nombre": "Formulación y Evaluación de Proyectos", "creditos": 3, "nivel": 7, "prerrequisitos": ["CBAS_E01A"]},
            {"codigo": "ISCO_A05A", "nombre": "Ingeniería de Software", "creditos": 3, "nivel": 7, "prerrequisitos": ["ISCO_A04A"]},
            {"codigo": "ISCO_C09A", "nombre": "Arquitectura del Computador", "creditos": 3, "nivel": 7, "prerrequisitos": ["ISCO_C08A"]},
            {"codigo": "ISCO_C10A", "nombre": "Sistemas y Modelos", "creditos": 3, "nivel": 7, "prerrequisitos": ["ISCO_C07A"]},
            {"codigo": "ISCO_P01A", "nombre": "Proyecto de Ingeniería I", "creditos": 3, "nivel": 7, "prerrequisitos": ["ISCO_A02A", "ISCO_A01A"], "es_proyecto": True, "proyecto_compartido": "P01A"},
            # NIVEL 8
            {"codigo": "CHUM_HU1A", "nombre": "Electiva de Humanidades I", "creditos": 2, "nivel": 8},
            {"codigo": "ISCO_A06A", "nombre": "Inteligencia Artificial", "creditos": 3, "nivel": 8, "prerrequisitos": ["CBAS_E01A", "ISCO_A03A"]},
            {"codigo": "ISCO_A07A", "nombre": "Infraestructura para TI", "creditos": 3, "nivel": 8, "prerrequisitos": ["ISCO_C09A"]},
            {"codigo": "ISCO_C11A", "nombre": "Sistemas Operativos", "creditos": 3, "nivel": 8, "prerrequisitos": ["ISCO_C09A"]},
            {"codigo": "ISCO_EC1A", "nombre": "Electiva Complementaria I", "creditos": 3, "nivel": 8, "prerrequisitos": ["ISCO_A02A"]},
            {"codigo": "ISCO_P02A", "nombre": "Proyecto de Ingeniería II", "creditos": 3, "nivel": 8, "prerrequisitos": ["ISCO_P01A"], "es_proyecto": True, "proyecto_compartido": "P02A"},
            # NIVEL 9
            {"codigo": "CHUM_HU2A", "nombre": "Electiva de Humanidades II", "creditos": 2, "nivel": 9, "prerrequisitos": ["CHUM_HU1A"]},
            {"codigo": "ISCO_EE1A", "nombre": "Electiva Empresarial", "creditos": 3, "nivel": 9},
            {"codigo": "ISCO_A08A", "nombre": "Computación en Paralelo", "creditos": 3, "nivel": 9, "prerrequisitos": ["ISCO_A07A"]},
            {"codigo": "ISCO_C12A", "nombre": "Tóp. Esp. Ciencias de la Computación", "creditos": 3, "nivel": 9, "prerrequisitos": ["ISCO_C11A"]},
            {"codigo": "ISCO_EC2A", "nombre": "Electiva Complementaria II", "creditos": 3, "nivel": 9, "prerrequisitos": ["ISCO_EC1A"]},
            {"codigo": "ISCO_EC3A", "nombre": "Electiva Complementaria III", "creditos": 3, "nivel": 9, "prerrequisitos": ["ISCO_EC1A"]},
            # NIVEL 10
            {"codigo": "CHUM_H04A", "nombre": "Ética", "creditos": 2, "nivel": 10},
            {"codigo": "ISCO_EC4A", "nombre": "Electiva Complementaria IV", "creditos": 3, "nivel": 10, "prerrequisitos": ["ISCO_EC2A"]},
            {"codigo": "ISCO_P03A", "nombre": "Prácticas Profesionales", "creditos": 9, "nivel": 10, "prerrequisitos": ["ISCO_P02A"], "es_practica": True},
        ],
        "grupos_electivas": [
            {
                "tipo_codigo": "HUMANIDADES",
                "nombre": "Electiva de Humanidades",
                "cantidad": 2,
                "creditos_cu": 2,
                "slot_codigos": ["CHUM_HU1A", "CHUM_HU2A"],
                "opciones": [
                    {"codigo": "CHUM_A01A", "nombre": "Apreciación del Arte", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_A02A", "nombre": "Apreciación Musical", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_A07A", "nombre": "Fotografía Creativa", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_A10A", "nombre": "Historia del Arte", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_C03A", "nombre": "Cátedra de Paz", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_C07A", "nombre": "Escritura Etnográfica", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_C17A", "nombre": "Ciudadanías Bajo la Lupa", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_F01A", "nombre": "¿Para qué Filosofía?", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L01A", "nombre": "Taller de Escritura Creativa", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L04A", "nombre": "Héroes y Dioses Literatura Gri", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L06A", "nombre": "Literatura Latinoamericana", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L07A", "nombre": "Lectura Crítica y Escritura", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L09A", "nombre": "Literatura y Ciencia", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_S04A", "nombre": "Historia del Mundo Contemporán", "creditos": 2, "nivel": 0},
                ],
            },
            {
                "tipo_codigo": "EMPRESARIAL_ISCO",
                "nombre": "Electiva Empresarial",
                "cantidad": 1,
                "creditos_cu": 3,
                "slot_codigos": ["ISCO_EE1A"],
                "opciones": [
                    {"codigo": "AEMP_O06A", "nombre": "Negocios Inclusivos", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O07A", "nombre": "Empresas Sostenibles", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O08A", "nombre": "Panorama Internacional y Cambio Social", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O12A", "nombre": "Tecnologías Aplicadas a la Administración", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_G11A", "nombre": "Innovación", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O14A", "nombre": "Gestión de la Innovación", "creditos": 3, "nivel": 0},
                ],
            },
            {
                "tipo_codigo": "COMP_ISCO",
                "nombre": "Electiva Complementaria Sistemas",
                "cantidad": 4,
                "creditos_cu": 3,
                "slot_codigos": ["ISCO_EC1A", "ISCO_EC2A", "ISCO_EC3A", "ISCO_EC4A"],
                "opciones": [
                    {"codigo": "IAMB_A11A", "nombre": "Gestión Ambiental", "creditos": 3, "nivel": 0},
                    {"codigo": "IELE_E08A", "nombre": "Energías Renovables", "creditos": 3, "nivel": 0},
                    {"codigo": "IELE_F03A", "nombre": "Circuitos Eléctricos I", "creditos": 3, "nivel": 0},
                    {"codigo": "IETR_C07A", "nombre": "Redes de Alta Velocidad", "creditos": 3, "nivel": 0},
                    {"codigo": "IETR_F02A", "nombre": "Sistemas Digitales I", "creditos": 3, "nivel": 0},
                    {"codigo": "IIND_A05A", "nombre": "Ingeniería Económica", "creditos": 3, "nivel": 0},
                    {"codigo": "ISCO_A19A", "nombre": "Computación e Interfaces", "creditos": 3, "nivel": 0},
                    {"codigo": "ISCO_A20A", "nombre": "Desarrollo Frontend", "creditos": 3, "nivel": 0},
                    {"codigo": "ISCO_Z03A", "nombre": "Gerencia de Sistemas", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_G11A", "nombre": "Innovación", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O14A", "nombre": "Gestión de la Innovación", "creditos": 3, "nivel": 0},
                ],
            },
        ],
    },
    
    "IIND": {
        "codigo": "IIND",
        "nombre": "Ingeniería Industrial",
        "facultad": "Facultad de Ingeniería",
        "materias": [
            # NIVEL 1
            {"codigo": "CHUM_H01A", "nombre": "Taller de Comprensión Lectora", "creditos": 3, "nivel": 1},
            {"codigo": "CBAS_M01A", "nombre": "Cálculo Diferencial", "creditos": 4, "nivel": 1},
            {"codigo": "CBAS_M02A", "nombre": "Matemáticas Básicas", "creditos": 2, "nivel": 1},
            {"codigo": "CBAS_Q01A", "nombre": "Química General", "creditos": 3, "nivel": 1},
            {"codigo": "ECOU_U01A", "nombre": "Desarrollo Universitario", "creditos": 0, "nivel": 1},
            {"codigo": "IIND_A01A", "nombre": "Seminario de Ing. Industrial", "creditos": 1, "nivel": 1},
            {"codigo": "ISCO_C02A", "nombre": "Fundamentos de Programación", "creditos": 3, "nivel": 1},
            # NIVEL 2
            {"codigo": "CHUL_LE1A", "nombre": "Lengua Extranjera I", "creditos": 2, "nivel": 2},
            {"codigo": "CHUM_H02A", "nombre": "Taller de Escritura Académica", "creditos": 3, "nivel": 2},
            {"codigo": "CBAS_F01A", "nombre": "Física Mecánica", "creditos": 4, "nivel": 2, "prerrequisitos": ["CBAS_M01A"]},
            {"codigo": "CBAS_M03A", "nombre": "Cálculo Integral", "creditos": 4, "nivel": 2, "prerrequisitos": ["CBAS_M01A"]},
            {"codigo": "CBAS_M04A", "nombre": "Álgebra Lineal", "creditos": 3, "nivel": 2, "prerrequisitos": ["CBAS_M02A"]},
            {"codigo": "ISCO_C03A", "nombre": "Programación", "creditos": 3, "nivel": 2, "prerrequisitos": ["ISCO_C02A"]},
            # NIVEL 3
            {"codigo": "CHUL_LE2A", "nombre": "Lengua Extranjera II", "creditos": 2, "nivel": 3, "prerrequisitos": ["CHUL_LE1A"]},
            {"codigo": "CBAS_E01A", "nombre": "Estadística y Probabilidad", "creditos": 3, "nivel": 3, "prerrequisitos": ["CBAS_M03A"]},
            {"codigo": "CBAS_F02A", "nombre": "Física Electricidad y Magnetismo", "creditos": 4, "nivel": 3, "prerrequisitos": ["CBAS_F01A", "CBAS_M03A"]},
            {"codigo": "CBAS_M05A", "nombre": "Cálculo Vectorial", "creditos": 4, "nivel": 3, "prerrequisitos": ["CBAS_M03A"]},
            {"codigo": "IMEC_M01A", "nombre": "Materiales I", "creditos": 3, "nivel": 3, "prerrequisitos": ["CBAS_F01A"]},
            {"codigo": "IIND_A02A", "nombre": "Administración Industrial", "creditos": 2, "nivel": 3},
            # NIVEL 4
            {"codigo": "CHUL_LE3A", "nombre": "Lengua Extranjera III", "creditos": 2, "nivel": 4, "prerrequisitos": ["CHUL_LE2A"]},
            {"codigo": "CBAS_E02A", "nombre": "Estadística Inferencial", "creditos": 3, "nivel": 4, "prerrequisitos": ["CBAS_E01A"]},
            {"codigo": "CBAS_F03A", "nombre": "Física Calor y Ondas", "creditos": 4, "nivel": 4, "prerrequisitos": ["CBAS_F02A"]},
            {"codigo": "CBAS_M06A", "nombre": "Ecuaciones Dif. y en Diferencia", "creditos": 4, "nivel": 4, "prerrequisitos": ["CBAS_M05A"]},
            {"codigo": "IIND_A03A", "nombre": "Estrategias de Operaciones", "creditos": 2, "nivel": 4, "prerrequisitos": ["IIND_A02A"]},
            {"codigo": "IIND_R01A", "nombre": "Procesos de Fabricación", "creditos": 3, "nivel": 4, "prerrequisitos": ["IMEC_M01A"]},
            # NIVEL 5
            {"codigo": "CHUL_LE4A", "nombre": "Lengua Extranjera IV", "creditos": 2, "nivel": 5, "prerrequisitos": ["CHUL_LE3A"]},
            {"codigo": "AEMP_G04A", "nombre": "Creatividad y Emprendimiento", "creditos": 3, "nivel": 5},
            {"codigo": "IIND_A04A", "nombre": "Sistemas de Costeo", "creditos": 3, "nivel": 5, "prerrequisitos": ["IIND_A02A"]},
            {"codigo": "IIND_R02A", "nombre": "Optimización", "creditos": 3, "nivel": 5, "prerrequisitos": ["CBAS_M06A"]},
            {"codigo": "IIND_R03A", "nombre": "Procesos Industriales", "creditos": 3, "nivel": 5, "prerrequisitos": ["IIND_R01A"]},
            {"codigo": "ISCO_C07A", "nombre": "Procesamiento Numérico", "creditos": 3, "nivel": 5, "prerrequisitos": ["ISCO_C03A", "CBAS_M06A"]},
            # NIVEL 6
            {"codigo": "CHUL_LE5A", "nombre": "Lengua Extranjera V", "creditos": 2, "nivel": 6, "prerrequisitos": ["CHUL_LE4A"]},
            {"codigo": "CHUM_H03A", "nombre": "Constitución Política", "creditos": 2, "nivel": 6},
            {"codigo": "CHUM_H05A", "nombre": "Ciudadanía Global", "creditos": 2, "nivel": 6},
            {"codigo": "ECON_M12A", "nombre": "Formulación y Evaluación de Proyectos", "creditos": 3, "nivel": 6, "prerrequisitos": ["CBAS_E01A"]},
            {"codigo": "IIND_R04A", "nombre": "Procesos Estocásticos", "creditos": 3, "nivel": 6, "prerrequisitos": ["CBAS_E02A"]},
            {"codigo": "IIND_R13A", "nombre": "Diseño de Experimentos", "creditos": 3, "nivel": 6, "prerrequisitos": ["CBAS_E02A"]},
            {"codigo": "IIND_R05A", "nombre": "Ingeniería de Productividad", "creditos": 3, "nivel": 6, "prerrequisitos": ["IIND_R03A"]},
            # NIVEL 7
            {"codigo": "CHUM_HU1A", "nombre": "Electiva de Humanidades I", "creditos": 2, "nivel": 7},
            {"codigo": "IIND_A05A", "nombre": "Ingeniería Económica", "creditos": 3, "nivel": 7, "prerrequisitos": ["IIND_A04A"]},
            {"codigo": "IIND_EC1A", "nombre": "Electiva Complementaria I", "creditos": 3, "nivel": 7},
            {"codigo": "IIND_EE1A", "nombre": "Electiva Empresarial", "creditos": 3, "nivel": 7},
            {"codigo": "IIND_R07A", "nombre": "Gestión Cadena de Suministro", "creditos": 3, "nivel": 7, "prerrequisitos": ["IIND_R04A"]},
            {"codigo": "IIND_R08A", "nombre": "Diseño de Sistemas Productivos", "creditos": 3, "nivel": 7, "prerrequisitos": ["IIND_R05A"]},
            # NIVEL 8
            {"codigo": "IIND_A06A", "nombre": "Gestión del Talento Humano", "creditos": 3, "nivel": 8},
            {"codigo": "IIND_A07A", "nombre": "Seguridad y Salud Laboral", "creditos": 3, "nivel": 8, "prerrequisitos": ["IIND_R05A"]},
            {"codigo": "IIND_EC2A", "nombre": "Electiva Complementaria II", "creditos": 3, "nivel": 8, "prerrequisitos": ["IIND_EC1A"]},
            {"codigo": "IIND_P01A", "nombre": "Proyecto de Ingeniería I", "creditos": 3, "nivel": 8, "prerrequisitos": ["IIND_R07A"], "es_proyecto": True, "proyecto_compartido": "P01A"},
            {"codigo": "IIND_R09A", "nombre": "Plan, Prog y Cont Producción", "creditos": 3, "nivel": 8, "prerrequisitos": ["IIND_R07A"]},
            {"codigo": "IIND_R10A", "nombre": "Control de Calidad", "creditos": 3, "nivel": 8, "prerrequisitos": ["IIND_R08A"]},
            # NIVEL 9
            {"codigo": "CHUM_H04A", "nombre": "Ética", "creditos": 2, "nivel": 9},
            {"codigo": "CHUM_HU2A", "nombre": "Electiva de Humanidades II", "creditos": 2, "nivel": 9, "prerrequisitos": ["CHUM_HU1A"]},
            {"codigo": "IIND_EC3A", "nombre": "Electiva Complementaria III", "creditos": 3, "nivel": 9, "prerrequisitos": ["IIND_EC2A"]},
            {"codigo": "IIND_P02A", "nombre": "Proyecto de Ingeniería II", "creditos": 3, "nivel": 9, "prerrequisitos": ["IIND_P01A"], "es_proyecto": True, "proyecto_compartido": "P02A"},
            {"codigo": "IIND_R11A", "nombre": "Distribución y Transporte", "creditos": 3, "nivel": 9, "prerrequisitos": ["IIND_R09A"]},
            {"codigo": "IIND_R12A", "nombre": "Simulación", "creditos": 3, "nivel": 9, "prerrequisitos": ["IIND_R10A"]},
            # NIVEL 10
            {"codigo": "IIND_EC4A", "nombre": "Electiva Complementaria IV", "creditos": 3, "nivel": 10, "prerrequisitos": ["IIND_EC3A"]},
            {"codigo": "IIND_P03A", "nombre": "Prácticas Profesionales", "creditos": 9, "nivel": 10, "prerrequisitos": ["IIND_P02A"], "es_practica": True},
        ],
        "grupos_electivas": [
            {
                "tipo_codigo": "HUMANIDADES",
                "nombre": "Electiva de Humanidades",
                "cantidad": 2,
                "creditos_cu": 2,
                "slot_codigos": ["CHUM_HU1A", "CHUM_HU2A"],
                "opciones": [
                    {"codigo": "CHUM_A01A", "nombre": "Apreciación del Arte", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_A02A", "nombre": "Apreciación Musical", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_A07A", "nombre": "Fotografía Creativa", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_A10A", "nombre": "Historia del Arte", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_C03A", "nombre": "Cátedra de Paz", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_C07A", "nombre": "Escritura Etnográfica", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_C17A", "nombre": "Ciudadanías Bajo la Lupa", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_F01A", "nombre": "¿Para qué Filosofía?", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L01A", "nombre": "Taller de Escritura Creativa", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L04A", "nombre": "Héroes y Dioses Literatura Gri", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L06A", "nombre": "Literatura Latinoamericana", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L07A", "nombre": "Lectura Crítica y Escritura", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_L09A", "nombre": "Literatura y Ciencia", "creditos": 2, "nivel": 0},
                    {"codigo": "CHUM_S04A", "nombre": "Historia del Mundo Contemporán", "creditos": 2, "nivel": 0},
                ],
            },
            {
                "tipo_codigo": "EMPRESARIAL_IIND",
                "nombre": "Electiva Empresarial",
                "cantidad": 1,
                "creditos_cu": 3,
                "slot_codigos": ["IIND_EE1A"],
                "opciones": [
                    {"codigo": "AEMP_O06A", "nombre": "Negocios Inclusivos", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O07A", "nombre": "Empresas Sostenibles", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O08A", "nombre": "Panorama Internacional y Cambio Social", "creditos": 3, "nivel": 0},
                    {"codigo": "AEMP_O12A", "nombre": "Tecnologías Aplicadas a la Administración", "creditos": 3, "nivel": 0},
                ],
            },
            {
                "tipo_codigo": "COMP_IIND",
                "nombre": "Electiva Complementaria Industrial",
                "cantidad": 4,
                "creditos_cu": 3,
                "slot_codigos": ["IIND_EC1A", "IIND_EC2A", "IIND_EC3A", "IIND_EC4A"],
                "opciones": [
                    {"codigo": "FNEG_N05A", "nombre": "Estrategias de Negociación", "creditos": 3, "nivel": 0},
                    {"codigo": "FNEG_N06A", "nombre": "Comercio Exterior", "creditos": 3, "nivel": 0},
                    {"codigo": "IAMB_A11A", "nombre": "Gestión Ambiental", "creditos": 3, "nivel": 0},
                    {"codigo": "IIND_A09A", "nombre": "Gestión de Inn. y el Conocimiento", "creditos": 3, "nivel": 0},
                    {"codigo": "IIND_R14A", "nombre": "Ciencia de los Datos", "creditos": 3, "nivel": 0},
                    {"codigo": "IIND_R17A", "nombre": "Ergonomía", "creditos": 3, "nivel": 0},
                    {"codigo": "IIND_R20A", "nombre": "Producción Más Limpia", "creditos": 3, "nivel": 0},
                    {"codigo": "IIND_R21A", "nombre": "Gestión de Ope. Emp de Servicios", "creditos": 3, "nivel": 0},
                ],
            },
        ],
    },
}


# ============================================================
# CONSTRUCTOR DE PROGRAMAS (convierte dict a objetos)
# ============================================================

def _crear_materia(data) -> Materia:
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
        proyecto_compartido=data.get("proyecto_compartido", None),  # ← NUEVO
    )


def _crear_grupo_electiva(data) -> GrupoElectiva:
    opciones = [_crear_materia(opt) for opt in data.get("opciones", [])]
    return GrupoElectiva(
        tipo_codigo=data["tipo_codigo"],
        nombre=data["nombre"],
        cantidad=data["cantidad"],
        creditos_cu=data["creditos_cu"],
        slot_codigos=data["slot_codigos"],
        opciones=opciones,
    )


def _crear_programa(data: dict) -> Programa:
    materias = [_crear_materia(m) for m in data.get("materias", [])]
    grupos = [_crear_grupo_electiva(g) for g in data.get("grupos_electivas", [])]
    return Programa(
        codigo=data["codigo"],
        nombre=data["nombre"],
        facultad=data["facultad"],
        materias=materias,
        grupos_electivas=grupos,
    )


# ============================================================
# REGISTRO DE PROGRAMAS
# ============================================================

PROGRAMAS: Dict[str, Programa] = {
    codigo: _crear_programa(data) for codigo, data in PROGRAMAS_DATA.items()
}


# ============================================================
# FUNCIONES DE UTILIDAD PARA EL PLANIFICADOR
# ============================================================

def get_programa(codigo: str) -> Optional[Programa]:
    return PROGRAMAS.get(codigo)


def get_todos_programas() -> List[Programa]:
    return list(PROGRAMAS.values())


def get_codigos_practica() -> Dict[str, str]:
    result = {}
    for codigo, prog in PROGRAMAS.items():
        if prog.codigos_practica:
            result[codigo] = list(prog.codigos_practica)[0]
    return result


def get_materia_global(codigo: str) -> Optional[Materia]:
    for prog in PROGRAMAS.values():
        materia = prog.get_materia(codigo)
        if materia:
            return materia
    return None


def diagnosticar():
    print("\n" + "="*80)
    print("PROGRAMAS REGISTRADOS")
    print("="*80)
    
    for codigo, prog in PROGRAMAS.items():
        print(f"\n📚 {prog.nombre} ({prog.codigo})")
        print(f"   Facultad: {prog.facultad}")
        print(f"   Materias totales: {len(prog.materias)}")
        print(f"   Materias obligatorias: {len(prog.materias_obligatorias)}")
        print(f"   Placeholders: {len(prog.placeholders)}")
        print(f"   Grupos electivas: {len(prog.grupos_electivas)}")
        print(f"   Créditos totales: {prog.total_creditos()}")
        
        if prog.codigos_practica:
            print(f"   Prácticas: {prog.codigos_practica}")
        if prog.codigos_proyecto:
            print(f"   Proyectos: {prog.codigos_proyecto}")
    
    print("\n" + "="*80)
    print(f"TOTAL: {len(PROGRAMAS)} programas registrados")
    print("="*80)


if __name__ == "__main__":
    diagnosticar()