# ============================================================
#  motor/planificador.py
#  Planificador académico doble programa UTB
#  Algoritmo: Greedy semestre a semestre optimizado para 20 créditos
# ============================================================

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
# PROGRAMAS y CODIGOS_INGLES ahora vienen de la BD en lugar de estar hardcodeados
from data.db_programas import (
    PROGRAMAS, CODIGOS_INGLES,
)
from data.programas import (
    Programa, Materia, GrupoElectiva, get_codigos_practica,
)

# ── Constantes ───────────────────────────────────────────────
CRED_MAX_ALTO = 20   # promedio >= 4.0
CRED_MAX_BAJO = 18   # promedio <  4.0
CRED_MIN      = 12   # mínimo por semestre activo


# ── Modelos de entrada/salida ────────────────────────────────

@dataclass
class HomologacionExterna:
    codigo_materia: str
    nombre_programa: str


@dataclass
class ParametrosPlan:
    codigo_programa_principal:  str
    codigo_programa_secundario: Optional[str]
    aprobadas:                  Set[str]
    niveles_ingles_homologados: Set[int]
    promedio:                   float
    semestres_cursados:         int
    homologaciones_externas:    List[HomologacionExterna] = field(default_factory=list)
    practica_unica:             bool = True

    @property
    def max_creditos(self) -> int:
        return CRED_MAX_ALTO if self.promedio >= 4.0 else CRED_MAX_BAJO


@dataclass
class MateriaPlan:
    codigo:           str
    nombre:           str
    creditos:         int
    origen:           str
    sirve_para_ambas: bool


@dataclass
class SemestrePlan:
    numero:         int
    materias:       List[MateriaPlan]
    total_creditos: int
    es_primero:     bool
    es_ultimo:      bool


# ── Función principal ────────────────────────────────────────

def generar_plan(params: ParametrosPlan) -> List[SemestrePlan]:
    prog_p = PROGRAMAS.get(params.codigo_programa_principal)
    prog_s = PROGRAMAS.get(params.codigo_programa_secundario) \
             if params.codigo_programa_secundario else None

    if not prog_p:
        raise ValueError(f"Programa '{params.codigo_programa_principal}' no encontrado.")

    aprobadas = cargar_aprobadas(params, prog_p, prog_s)
    grupos_fusionados = fusionar_grupos(prog_p, prog_s)

    cubiertas_por_grupo = calcular_electivas_cubiertas(
        grupos_fusionados, aprobadas, set(), prog_p, prog_s
    )

    placeholders = placeholders_necesarios(
        grupos_fusionados, cubiertas_por_grupo, aprobadas
    )

    pendientes = materias_pendientes(
        prog_p, prog_s, aprobadas, placeholders, params
    )
    
    pendientes_codigos = {m.codigo for m in pendientes}
    
    cubiertas_por_grupo = calcular_electivas_cubiertas(
        grupos_fusionados, aprobadas, pendientes_codigos, prog_p, prog_s
    )
    
    placeholders = placeholders_necesarios(
        grupos_fusionados, cubiertas_por_grupo, aprobadas
    )
    
    pendientes = materias_pendientes(
        prog_p, prog_s, aprobadas, placeholders, params
    )

    print(f"[MOTOR] aprobadas={len(aprobadas)} pendientes={len(pendientes)} "
          f"placeholders={len(placeholders)}")
    for tc, n in cubiertas_por_grupo.items():
        gc = grupos_fusionados[tc]
        print(f"  [{tc}] cubiertas={n}/{gc.cantidad}")

    if not pendientes:
        return []

    plan = planificar_semestres_optimizado(
        pendientes=pendientes,
        aprobadas=aprobadas,
        cred_max=params.max_creditos,
        cred_min=CRED_MIN,
        semestre_inicial=params.semestres_cursados + 1,
        prog_p=prog_p,
        prog_s=prog_s,
    )

    return plan


# ── PASO 1: Cargar aprobadas ─────────────────────────────────

def cargar_aprobadas(
    params: ParametrosPlan,
    prog_p: Programa,
    prog_s: Optional[Programa],
) -> Set[str]:
    aprobadas: Set[str] = set(params.aprobadas)

    for n in params.niveles_ingles_homologados:
        if 1 <= n <= len(CODIGOS_INGLES):
            aprobadas.add(CODIGOS_INGLES[n - 1])

    for h in params.homologaciones_externas:
        aprobadas.add(h.codigo_materia)

    for prog in [prog_p, prog_s]:
        if prog:
            for m in prog.materias:
                if m.creditos == 0:
                    aprobadas.add(m.codigo)

    if params.practica_unica and prog_s and params.codigo_programa_secundario:
        codigos_practica = get_codigos_practica()
        cod_practica_s = codigos_practica.get(params.codigo_programa_secundario)
        if cod_practica_s:
            aprobadas.add(cod_practica_s)

    return aprobadas


# ── PASO 2: Fusionar grupos ──────────────────────────────────

@dataclass
class _GrupoFusionado:
    tipo_codigo: str
    nombre:      str
    cantidad:    int
    creditos_cu: int
    slot_codigos: List[str]
    opciones:    Dict[str, Materia]


def fusionar_grupos(
    prog_p: Programa,
    prog_s: Optional[Programa],
) -> Dict[str, _GrupoFusionado]:
    resultado: Dict[str, _GrupoFusionado] = {}

    for ge in prog_p.grupos_electivas:
        resultado[ge.tipo_codigo] = _GrupoFusionado(
            tipo_codigo  = ge.tipo_codigo,
            nombre       = ge.nombre,
            cantidad     = ge.cantidad,
            creditos_cu  = ge.creditos_cu,
            slot_codigos = list(ge.slot_codigos),
            opciones     = {o.codigo: o for o in ge.opciones},
        )

    if prog_s:
        for ge in prog_s.grupos_electivas:
            if ge.tipo_codigo in resultado:
                gf = resultado[ge.tipo_codigo]
                gf.cantidad = max(gf.cantidad, ge.cantidad)
                for o in ge.opciones:
                    gf.opciones.setdefault(o.codigo, o)
                for slot in ge.slot_codigos:
                    if slot not in gf.slot_codigos:
                        gf.slot_codigos.append(slot)
            else:
                resultado[ge.tipo_codigo] = _GrupoFusionado(
                    tipo_codigo  = ge.tipo_codigo,
                    nombre       = ge.nombre,
                    cantidad     = ge.cantidad,
                    creditos_cu  = ge.creditos_cu,
                    slot_codigos = list(ge.slot_codigos),
                    opciones     = {o.codigo: o for o in ge.opciones},
                )

    return resultado


# ── PASO 3: Calcular cubiertas por grupo ─────────────────────

def calcular_electivas_cubiertas(
    grupos: Dict[str, _GrupoFusionado],
    aprobadas: Set[str],
    pendientes: Set[str],
    prog_p: Programa,
    prog_s: Optional[Programa],
) -> Dict[str, int]:
    cubiertas: Dict[str, int] = {tc: 0 for tc in grupos}
    todas_futuras: Set[str] = aprobadas | pendientes

    print("\n  Calculando electivas cubiertas (incluyendo futuras):")
    for tc, gf in grupos.items():
        contadas: Set[str] = set()
        for cod_opcion in gf.opciones:
            if cod_opcion in aprobadas:
                contadas.add(cod_opcion)
                print(f"    ✓ {cod_opcion} (ya aprobada) → cubre {tc}")
            elif prog_s and cod_opcion in prog_s.materias_obligatorias and cod_opcion in todas_futuras:
                contadas.add(cod_opcion)
                print(f"    ✓ {cod_opcion} (obligatoria de {prog_s.codigo} por cursar) → cubre {tc}")
            elif cod_opcion in prog_p.materias_obligatorias and cod_opcion in todas_futuras:
                contadas.add(cod_opcion)
                print(f"    ✓ {cod_opcion} (obligatoria de {prog_p.codigo} por cursar) → cubre {tc}")
        
        cubiertas[tc] = min(len(contadas), gf.cantidad)
        print(f"    Total cubiertas para {tc}: {cubiertas[tc]}/{gf.cantidad}")

    return cubiertas


# ── PASO 4: Placeholders necesarios ─────────────────────────

def placeholders_necesarios(
    grupos: Dict[str, _GrupoFusionado],
    cubiertas_por_grupo: Dict[str, int],
    aprobadas: Set[str],
) -> Set[str]:
    necesarios: Set[str] = set()

    for tc, gf in grupos.items():
        ya_cubiertas = cubiertas_por_grupo.get(tc, 0)
        faltan = gf.cantidad - ya_cubiertas

        print(f"  Grupo {tc}: requiere {gf.cantidad}, cubiertas={ya_cubiertas}, faltan={faltan}")

        if faltan <= 0:
            continue

        slots_disponibles = [slot for slot in gf.slot_codigos if slot not in aprobadas]
        for slot in slots_disponibles[:faltan]:
            necesarios.add(slot)
            print(f"    → Slot necesario: {slot}")

    return necesarios


# ── PASO 5: Materias pendientes ──────────────────────────────

def materias_pendientes(
    prog_p: Programa,
    prog_s: Optional[Programa],
    aprobadas: Set[str],
    placeholders: Set[str],
    params: ParametrosPlan,
) -> List[Materia]:
    pendientes: Dict[str, Materia] = {}
    proyectos_agregados: Set[str] = set()

    for prog in [prog_p, prog_s]:
        if not prog:
            continue
        for cod, mat in prog.materias_obligatorias.items():
            if cod in aprobadas:
                continue
            
            if mat.es_practica:
                if prog.codigo != params.codigo_programa_principal:
                    continue
                if params.practica_unica and prog.codigo != params.codigo_programa_principal:
                    continue
                pendientes[cod] = mat
                continue
            
            if mat.es_proyecto:
                if mat.proyecto_compartido:
                    if mat.proyecto_compartido in proyectos_agregados:
                        continue
                    proyectos_agregados.add(mat.proyecto_compartido)
                pendientes[cod] = mat
                continue
            
            pendientes[cod] = mat

    for prog in [prog_p, prog_s]:
        if not prog:
            continue
        for ge in prog.grupos_electivas:
            for slot in ge.slot_codigos:
                if slot in placeholders and slot not in pendientes:
                    pendientes[slot] = Materia(
                        codigo=slot,
                        nombre=ge.nombre,
                        creditos=ge.creditos_cu,
                        nivel=8,
                        prerrequisitos=[],
                    )

    return sorted(pendientes.values(), key=lambda m: (m.nivel, -m.creditos))


# ── PASO 6: Planificar semestres OPTIMIZADO ──────────────────

def planificar_semestres_optimizado(
    pendientes: List[Materia],
    aprobadas: Set[str],
    cred_max: int,
    cred_min: int,
    semestre_inicial: int,
    prog_p: Programa,
    prog_s: Optional[Programa],
) -> List[SemestrePlan]:
    """
    Algoritmo optimizado para lograr 20 créditos por semestre:
    1. Distribuye materias de 2 créditos (humanidades) en cada semestre
    2. Prioriza materias de 3 créditos como base
    3. La práctica puede ir sola al final o acompañada
    """
    pendientes_set: Dict[str, Materia] = {m.codigo: m for m in pendientes}
    vistas: Set[str] = set(aprobadas)
    plan: List[SemestrePlan] = []
    semestre = semestre_inicial

    # Separar práctica
    practica: Optional[Materia] = None
    for cod, mat in list(pendientes_set.items()):
        if mat.es_practica:
            practica = mat
            del pendientes_set[cod]

    codigos_p = {m.codigo for m in prog_p.materias}
    codigos_s = {m.codigo for m in prog_s.materias} if prog_s else set()

    # Identificar materias de 2 créditos (humanidades, constitución, etc.)
    materias_2cr = [m for m in pendientes_set.values() if m.creditos == 2]
    materias_restantes = [m for m in pendientes_set.values() if m.creditos != 2]

    while materias_restantes or materias_2cr:
        # Materias disponibles actualmente
        disponibles = [
            mat for mat in materias_restantes + materias_2cr
            if prerequisitos_cumplidos(mat, vistas) and mat.codigo in pendientes_set
        ]
        
        if not disponibles:
            break

        # Separar disponibles por tipo
        disponibles_3cr = [m for m in disponibles if m.creditos >= 3]
        disponibles_2cr = [m for m in disponibles if m.creditos == 2]

        disponibles_3cr.sort(key=lambda m: (m.nivel, -m.creditos))

        semestre_mats: List[Materia] = []
        usados = 0

        # FASE 1: Tomar materias de 3-4 créditos (dejar espacio para 2cr)
        for mat in disponibles_3cr:
            if usados + mat.creditos <= cred_max - 2:
                semestre_mats.append(mat)
                usados += mat.creditos
            if usados >= 18:
                break

        # FASE 2: Agregar UNA materia de 2 créditos si hay disponible
        if usados <= 18 and disponibles_2cr:
            mat_2cr = disponibles_2cr[0]
            semestre_mats.append(mat_2cr)
            usados += mat_2cr.creditos

        # FASE 3: Si aún falta para llegar a 20, agregar más materias
        if usados < cred_max:
            for mat in disponibles_3cr:
                if mat not in semestre_mats and usados + mat.creditos <= cred_max:
                    semestre_mats.append(mat)
                    usados += mat.creditos
                    if usados >= cred_max:
                        break
            if usados < cred_max and disponibles_2cr:
                for mat in disponibles_2cr:
                    if mat not in semestre_mats and usados + mat.creditos <= cred_max:
                        semestre_mats.append(mat)
                        usados += mat.creditos
                        if usados >= cred_max:
                            break

        if not semestre_mats:
            semestre_mats = [disponibles[0]]
            usados = disponibles[0].creditos

        materias_plan = [
            _crear_materia_plan(mat, codigos_p, codigos_s, prog_s)
            for mat in sorted(semestre_mats, key=lambda m: (m.nivel, m.creditos))
        ]

        plan.append(SemestrePlan(
            numero=semestre,
            materias=materias_plan,
            total_creditos=usados,
            es_primero=(semestre == semestre_inicial),
            es_ultimo=False,
        ))

        # Actualizar estado - CORREGIDO: usar mat.codigo como clave
        for mat in semestre_mats:
            vistas.add(mat.codigo)
            if mat.codigo in pendientes_set:
                del pendientes_set[mat.codigo]
        
        # Actualizar listas auxiliares
        materias_restantes = [m for m in materias_restantes if m.codigo in pendientes_set]
        materias_2cr = [m for m in materias_2cr if m.codigo in pendientes_set]

        semestre += 1

    # Agregar práctica al final
    if practica:
        materias_con_practica = [practica]
        creditos_practica = practica.creditos
        
        if creditos_practica <= 17 and materias_2cr:
            for mat in materias_2cr[:]:
                if creditos_practica + mat.creditos <= cred_max:
                    materias_con_practica.append(mat)
                    creditos_practica += mat.creditos
                    if creditos_practica >= cred_max:
                        break

        plan.append(SemestrePlan(
            numero=semestre,
            materias=[_crear_materia_plan(m, codigos_p, codigos_s, prog_s) for m in materias_con_practica],
            total_creditos=creditos_practica,
            es_primero=False,
            es_ultimo=True,
        ))
    elif plan:
        plan[-1].es_ultimo = True

    return plan
# ── Helpers ──────────────────────────────────────────────────

def prerequisitos_cumplidos(mat: Materia, aprobadas: Set[str]) -> bool:
    return all(prereq in aprobadas for prereq in mat.prerrequisitos)


def _crear_materia_plan(
    mat: Materia,
    codigos_p: Set[str],
    codigos_s: Set[str],
    prog_s: Optional[Programa], 
) -> MateriaPlan:
    en_p = mat.codigo in codigos_p
    en_s = mat.codigo in codigos_s

    if mat.es_practica:
        return MateriaPlan(
            codigo=mat.codigo,
            nombre=mat.nombre,
            creditos=mat.creditos,
            origen="practica",
            sirve_para_ambas=True,
        )
    
    if mat.es_proyecto and mat.proyecto_compartido:
        otro_tiene = False
        if prog_s:
            for otro_cod, otro_mat in prog_s.materias_obligatorias.items():
                if otro_mat.es_proyecto and otro_mat.proyecto_compartido == mat.proyecto_compartido:
                    otro_tiene = True
                    break
        if en_p and otro_tiene:
            return MateriaPlan(
                codigo=mat.codigo,
                nombre=mat.nombre,
                creditos=mat.creditos,
                origen="compartida",
                sirve_para_ambas=True,
            )
    
    if en_p and en_s:
        origen, sirve = "compartida", True
    elif en_s:
        origen, sirve = "secundario", False
    elif en_p:
        origen, sirve = "principal", False
    else:
        origen, sirve = "compartida", True

    return MateriaPlan(
        codigo=mat.codigo,
        nombre=mat.nombre,
        creditos=mat.creditos,
        origen=origen,
        sirve_para_ambas=sirve,
    )