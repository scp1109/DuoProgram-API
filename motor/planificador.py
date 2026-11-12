# ============================================================
#  Planificador académico doble programa UTB
#  Algoritmo: Greedy semestre a semestre optimizado para 20 créditos
# ============================================================

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Set, Tuple
# Los programas y los codigos de ingles vienen de la BD, no hardcodeados.
# OJO: se importan los ACCESORES, no los diccionarios/listas.
# `from data.db_programas import PROGRAMAS` ataba este modulo al dict que
# existia al momento del import; cuando el admin edita una malla y se llama a
# recargar_programas(), esa funcion rebindea PROGRAMAS alla, pero aqui el
# nombre seguia apuntando al dict viejo y el motor planificaba con datos
# obsoletos hasta reiniciar el servidor. Los accesores resuelven el global en
# cada llamada, asi que siempre leen el estado vigente.
from data.db_programas import (
    get_programas, get_codigos_ingles, get_codigos_practica,
)
# Las clases y constructores vienen de modelos.py (sin datos hardcodeados)
from data.modelos import Programa, Materia, GrupoElectiva

# ── Constantes ───────────────────────────────────────────────
CRED_MAX_ALTO = 20   # promedio >= 4.0
CRED_MAX_BAJO = 18   # promedio <  4.0


class PlanIncompletoError(ValueError):
    """Quedan materias pendientes cuyos prerrequisitos nunca se cumplen.

    Antes el greedy hacia break y devolvia un plan sin esas materias, que
    parecia valido. Un plan al que le falta Proyecto II es peor que un error:
    el estudiante lo sigue y no se gradua.
    """

    def __init__(self, materias: List["Materia"]):
        orden = sorted(materias, key=lambda m: m.codigo)
        self.codigos = [m.codigo for m in orden]
        # El mensaje llega tal cual al estudiante: nombres, no solo codigos.
        super().__init__(
            "No se pudo armar un plan completo. Estas materias tienen "
            "prerrequisitos que nunca se cumplen: "
            + ", ".join("%s (%s)" % (m.nombre, m.codigo) for m in orden))


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
    # Ya no existe `practica_unica`: el estudiante de doble programa cursa una
    # sola practica, la del programa principal, siempre. El flag nunca hizo
    # nada (la rama que lo consultaba era inalcanzable) y se elimino.
    practica_sola:              bool = False  # True = ultimo semestre solo con practica

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


# ----- Función principal ---------------------------------------

def generar_plan(params: ParametrosPlan) -> List[SemestrePlan]:
    programas = get_programas()
    prog_p = programas.get(params.codigo_programa_principal)
    prog_s = programas.get(params.codigo_programa_secundario) \
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

    if not pendientes:
        return []

    plan = planificar_semestres_optimizado(
        pendientes=pendientes,
        aprobadas=aprobadas,
        cred_max=params.max_creditos,
        semestre_inicial=params.semestres_cursados + 1,
        prog_p=prog_p,
        prog_s=prog_s,
        practica_sola=params.practica_sola,
    )

    return plan


# --- PASO 1: Cargar aprobadas ----------------------------

def cargar_aprobadas(
    params: ParametrosPlan,
    prog_p: Programa,
    prog_s: Optional[Programa],
) -> Set[str]:
    aprobadas: Set[str] = set(params.aprobadas)

    # Se lee la lista vigente en cada llamada (ver comentario del import)
    codigos_ingles = get_codigos_ingles()
    for n in params.niveles_ingles_homologados:
        if 1 <= n <= len(codigos_ingles):
            aprobadas.add(codigos_ingles[n - 1])

    for h in params.homologaciones_externas:
        aprobadas.add(h.codigo_materia)

    for prog in [prog_p, prog_s]:
        if prog:
            for m in prog.materias:
                if m.creditos == 0:
                    aprobadas.add(m.codigo)

    # Practica unica: se cursa solo la practica del programa principal, asi que
    # la del secundario se da por cumplida siempre. Antes esto colgaba del flag
    # params.practica_unica, pero el flag no cambiaba nada (materias_pendientes
    # descartaba la practica del secundario en todos los casos) y se elimino.
    if prog_s and params.codigo_programa_secundario:
        codigos_practica = get_codigos_practica()
        cod_practica_s = codigos_practica.get(params.codigo_programa_secundario)
        if cod_practica_s:
            aprobadas.add(cod_practica_s)

    return aprobadas


# --- PASO 2: Fusionar grupos ------------------------------------

@dataclass
class _GrupoFusionado:
    tipo_codigo: str
    nombre:      str
    cantidad:    int
    creditos_cu: int
    slot_codigos: List[str]
    opciones:    Dict[str, Materia]
    # Programas a los que pertenece el grupo. Hace falta para no contar como
    # electiva cubierta una materia que ya es obligatoria del propio dueno.
    duenos:      Set[str] = field(default_factory=set)


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
            duenos       = {prog_p.codigo},
        )

    if prog_s:
        for ge in prog_s.grupos_electivas:
            if ge.tipo_codigo in resultado:
                gf = resultado[ge.tipo_codigo]
                gf.cantidad = max(gf.cantidad, ge.cantidad)
                gf.duenos.add(prog_s.codigo)
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
                    duenos       = {prog_s.codigo},
                )

    return resultado


# --- PASO 3: Calcular cubiertas por grupo -------------------

def calcular_electivas_cubiertas(
    grupos: Dict[str, _GrupoFusionado],
    aprobadas: Set[str],
    pendientes: Set[str],
    prog_p: Programa,
    prog_s: Optional[Programa],
) -> Dict[str, int]:
    cubiertas: Dict[str, int] = {tc: 0 for tc in grupos}
    todas_futuras: Set[str] = aprobadas | pendientes
    obligatorias = {prog.codigo: set(prog.materias_obligatorias)
                    for prog in (prog_p, prog_s) if prog}

    for tc, gf in grupos.items():
        # Una opcion cubre la electiva si ya esta aprobada o si es obligatoria
        # del OTRO programa (el beneficio del doble programa). Nunca si es
        # obligatoria del propio dueno del grupo: ya se cursa por obligatoria
        # y contarla otra vez le quitaba al estudiante una electiva. Pasaba
        # con COMP_CDAT, que lista ISCO_C02A, ISCO_C05A y ECON_M01A (obligatorias
        # de CDAT): el plan de CDAT salia con 2 electivas en vez de 5.
        obl_duenos = set().union(*(obligatorias.get(d, set()) for d in gf.duenos))
        obl_otros = set().union(*([v for k, v in obligatorias.items()
                                   if k not in gf.duenos] or [set()]))
        contadas: Set[str] = set()
        for cod_opcion in gf.opciones:
            if cod_opcion in obl_duenos:
                continue
            if cod_opcion in aprobadas:
                contadas.add(cod_opcion)
            elif cod_opcion in obl_otros and cod_opcion in todas_futuras:
                contadas.add(cod_opcion)
        cubiertas[tc] = min(len(contadas), gf.cantidad)

    return cubiertas


# --- PASO 4: Placeholders necesarios ------------------------

def placeholders_necesarios(
    grupos: Dict[str, _GrupoFusionado],
    cubiertas_por_grupo: Dict[str, int],
    aprobadas: Set[str],
) -> Set[str]:
    necesarios: Set[str] = set()

    for tc, gf in grupos.items():
        ya_cubiertas = cubiertas_por_grupo.get(tc, 0)
        faltan = gf.cantidad - ya_cubiertas

        if faltan <= 0:
            continue

        slots_disponibles = [slot for slot in gf.slot_codigos if slot not in aprobadas]
        for slot in slots_disponibles[:faltan]:
            necesarios.add(slot)

    return necesarios


# --- PASO 5: Materias pendientes ---------------------------------

def cierre_prerrequisitos(prog: Programa) -> Callable[[str], Set[str]]:
    """Devuelve una funcion cod -> todos sus prerrequisitos en `prog`,
    directos e indirectos. Memoriza, y corta ciclos si la BD trajera alguno."""
    grafo = {m.codigo: m.prerrequisitos for m in prog.materias}
    memo: Dict[str, Set[str]] = {}

    def cierre(cod: str) -> Set[str]:
        if cod in memo:
            return memo[cod]
        memo[cod] = set()
        total: Set[str] = set()
        for pre in grafo.get(cod, ()):
            total |= {pre} | cierre(pre)
        memo[cod] = total
        return total

    return cierre


def _fusionar_prerrequisitos(
    pendientes: Dict[str, Materia],
    cierres: Dict[str, Set[str]],
    cod: str,
    mat: Materia,
    cierre_mat: Set[str],
) -> None:
    """Guarda la materia combinando sus prerrequisitos con los ya registrados
    por el otro programa (ver combinar_prerrequisitos). `cierres` guarda el
    cierre transitivo de la version que quedo registrada para cada codigo."""
    previa = pendientes.get(cod)
    if previa is None:
        pendientes[cod] = mat
        cierres[cod] = cierre_mat
        return
    prereqs, alternativas = combinar_prerrequisitos(
        previa.prerrequisitos, mat.prerrequisitos, cierres[cod], cierre_mat)
    pendientes[cod] = replace(
        previa, prerrequisitos=prereqs, alternativas=alternativas)
    cierres[cod] = cierres[cod] | cierre_mat


def combinar_prerrequisitos(
    a: List[str],
    b: List[str],
    cierre_a: Optional[Set[str]] = None,
    cierre_b: Optional[Set[str]] = None,
) -> Tuple[List[str], List[List[str]]]:
    """Combina los prerrequisitos que dos programas exigen a la misma materia.

    Devuelve (prerrequisitos, alternativas). Se compara la lista DIRECTA de
    un programa con el CIERRE transitivo del otro (cierre_a, cierre_b):

    - Si lo que pide un programa ya esta en la cadena del otro, uno domina:
      se exigen ambas listas y no hay alternativas. Sin mirar la cadena esto
      fallaba con Fisica Calor y Ondas: ISCO exige Fisica Mecanica e IIND
      exige Electricidad y Magnetismo, que a su vez exige Mecanica. Las
      listas directas no se contienen, se trataban como caminos alternativos
      y el plan colocaba Calor y Ondas junto a Electricidad.
    - Si ninguno domina, cada programa exige SU propio camino (Estructura de
      Datos: POO en ISCO, Programacion para Ciencia de Datos en CDAT). Se
      devuelven como alternativas y basta con cumplir una.

    Sin cierres (None) compara las listas directas.
    """
    ca = set(a) | (cierre_a or set())
    cb = set(b) | (cierre_b or set())
    union = list(dict.fromkeys([*a, *b]))
    # Se compara lo que un programa pide DIRECTAMENTE con el cierre del otro,
    # no cierre contra cierre. Cierre contra cierre fallaba con cualquier
    # diferencia rio arriba: en IMEC+ISCO, Procesamiento Numerico pide POO en
    # ISCO y solo Programacion en IMEC, pero el cierre de IMEC trae Algebra
    # Lineal porque IMEC declara Calculo Vectorial distinto. Ningun cierre
    # contenia al otro, se volvian caminos alternativos y POO dejaba de ser
    # obligatoria antes.
    #
    # Si un programa domina se devuelve la UNION de las listas directas, no
    # solo la del dominante. No exige nada de mas: la lista del otro ya esta
    # en la cadena del dominante. Y pedirla explicitamente evita depender de
    # que la cadena intermedia no se haya relajado con caminos alternativos
    # al combinar los dos programas.
    if set(a) <= cb or set(b) <= ca:
        return union, []
    return union, [list(a), list(b)]


def materias_pendientes(
    prog_p: Programa,
    prog_s: Optional[Programa],
    aprobadas: Set[str],
    placeholders: Set[str],
    params: ParametrosPlan,
) -> List[Materia]:
    pendientes: Dict[str, Materia] = {}
    cierres: Dict[str, Set[str]] = {}
    cierre_de = {prog.codigo: cierre_prerrequisitos(prog)
                 for prog in (prog_p, prog_s) if prog}

    # Proyectos equivalentes entre programas: la etiqueta proyecto_compartido
    # dice que ISCO_P01A e IIND_P01A son el mismo proyecto. Se guarda QUE
    # PROGRAMAS ya cubren cada etiqueta, por dos razones:
    #  - CDAT e IMEC usan una sola etiqueta para Proyecto I y II (CDAT_PG,
    #    IMEC_PI). Con un set de etiquetas a secas, Proyecto II se descartaba
    #    como "ya agregado" y desaparecia del plan. Dentro de un mismo
    #    programa cada proyecto cuenta; solo se omite el de OTRO programa.
    #  - Un proyecto ya aprobado tambien cubre su etiqueta. Antes el continue
    #    de las aprobadas saltaba antes de registrarla y el plan pedia cursar
    #    el equivalente del otro programa.
    # etiqueta -> programa -> codigos que la cubren (aprobados o en el plan).
    cubiertos: Dict[str, Dict[str, List[str]]] = {}
    for prog in [prog_p, prog_s]:
        if not prog:
            continue
        for cod, mat in prog.materias_obligatorias.items():
            if mat.es_proyecto and mat.proyecto_compartido and cod in aprobadas:
                cubiertos.setdefault(mat.proyecto_compartido, {}) \
                         .setdefault(prog.codigo, []).append(cod)

    # Proyecto omitido -> el proyecto equivalente que lo cubre. Hace falta
    # porque otras materias siguen pidiendo el omitido: ISCO_P02A exige
    # ISCO_P01A. Si el estudiante aprobo IIND_P01A, ISCO_P01A se omite, nadie
    # lo marcaba como cumplido y Proyecto II desaparecia del plan sin aviso.
    # Al final se reescriben esos prerrequisitos para que apunten al
    # equivalente: si esta aprobado se cumplen ya, y si esta en el plan se
    # respeta el orden.
    sustituto: Dict[str, str] = {}

    for prog in [prog_p, prog_s]:
        if not prog:
            continue
        for cod, mat in prog.materias_obligatorias.items():
            if cod in aprobadas:
                continue
            
            if mat.es_practica:
                # Solo se cursa la practica del programa PRINCIPAL: en doble
                # programa la UTB no exige dos practicas. La del secundario se
                # marca como aprobada en cargar_aprobadas().
                if prog.codigo != params.codigo_programa_principal:
                    continue
                _fusionar_prerrequisitos(
                    pendientes, cierres, cod, mat, cierre_de[prog.codigo](cod))
                continue

            if mat.es_proyecto:
                tag = mat.proyecto_compartido
                if tag:
                    otros = [c for p, cods in cubiertos.get(tag, {}).items()
                             if p != prog.codigo for c in cods]
                    if otros:
                        # Su equivalente de otro programa ya cuenta.
                        sustituto[cod] = otros[0]
                        continue
                    cubiertos.setdefault(tag, {}) \
                             .setdefault(prog.codigo, []).append(cod)
                _fusionar_prerrequisitos(
                    pendientes, cierres, cod, mat, cierre_de[prog.codigo](cod))
                continue

            _fusionar_prerrequisitos(
                pendientes, cierres, cod, mat, cierre_de[prog.codigo](cod))

    for prog in [prog_p, prog_s]:
        if not prog:
            continue
        for ge in prog.grupos_electivas:
            for slot in ge.slot_codigos:
                if slot in placeholders and slot not in pendientes:
                    # Los slots de electiva PUEDEN traer prerrequisitos: el
                    # slot de Humanidades II exige el de Humanidades I. Antes
                    # el placeholder se creaba con la lista vacia y se perdia
                    # esa regla, asi que el plan colocaba las dos el mismo
                    # semestre. Se recupera la declaracion real del slot en
                    # cualquiera de los dos programas.
                    # Misma regla que las materias normales: si ambos
                    # programas declaran el slot, se combinan con
                    # combinar_prerrequisitos.
                    prereqs_slot: List[str] = []
                    alternativas_slot: List[List[str]] = []
                    cierre_slot: Set[str] = set()
                    for prog_busca in (prog_p, prog_s):
                        if not prog_busca:
                            continue
                        real = prog_busca.get_materia(slot)
                        if real:
                            cierre_real = cierre_de[prog_busca.codigo](slot)
                            prereqs_slot, alternativas_slot = \
                                combinar_prerrequisitos(
                                    prereqs_slot, real.prerrequisitos,
                                    cierre_slot, cierre_real)
                            cierre_slot |= cierre_real
                    pendientes[slot] = Materia(
                        codigo=slot,
                        nombre=ge.nombre,
                        creditos=ge.creditos_cu,
                        nivel=8,
                        prerrequisitos=prereqs_slot,
                        alternativas=alternativas_slot,
                    )

    if sustituto:
        def _sust(codigos: List[str]) -> List[str]:
            return list(dict.fromkeys(sustituto.get(c, c) for c in codigos))

        for cod, mat in list(pendientes.items()):
            usa = set(mat.prerrequisitos).union(*mat.alternativas)
            if usa & sustituto.keys():
                pendientes[cod] = replace(
                    mat,
                    prerrequisitos=_sust(mat.prerrequisitos),
                    alternativas=[_sust(c) for c in mat.alternativas],
                )

    lista = list(pendientes.values())

    # Reasignar nivel de las lenguas extranjeras pendientes.
    # Si el estudiante homologo hasta nivel N, la siguiente (N+1) debe
    # poder cursarse en el primer semestre disponible, no en el nivel
    # que le corresponde en la malla original.
    codigos_ingles = get_codigos_ingles()
    codigos_ingles_set = set(codigos_ingles)
    ingles_pendientes = sorted(
        [m for m in lista if m.codigo in codigos_ingles_set],
        key=lambda m: codigos_ingles.index(m.codigo),
    )
    if ingles_pendientes:
        # El primer ingles pendiente arranca en nivel 1 del plan restante;
        # los siguientes se espacian uno por semestre para respetar la cadena
        ajustados = {
            m.codigo: replace(m, nivel=i + 1)
            for i, m in enumerate(ingles_pendientes)
        }
        lista = [
            ajustados.get(m.codigo, m) for m in lista
        ]

    return sorted(lista, key=lambda m: (m.nivel, -m.creditos))


# --- PASO 6: Planificar semestres OPTIMIZADO --------------------

def planificar_semestres_optimizado(
    pendientes: List[Materia],
    aprobadas: Set[str],
    cred_max: int,
    semestre_inicial: int,
    prog_p: Programa,
    prog_s: Optional[Programa],
    practica_sola: bool = False,
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
    # Materias (no MateriaPlan) del ultimo semestre emitido. Hace falta para
    # decidir si la cola se puede fusionar con la practica: MateriaPlan no
    # lleva los prerrequisitos y sin ellos no se puede validar la fusion.
    ultimo_grupo: List[Materia] = []

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
            raise PlanIncompletoError(materias_restantes + materias_2cr)

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

        # Se ordena por nivel para que el ingles ajustado (nivel=1) llegue
        # antes que otras materias de 2cr con nivel mayor (humanidades, etc.)
        disponibles_2cr_sorted = sorted(disponibles_2cr, key=lambda m: m.nivel)

        # FASE 2: Agregar materias de 1 credito antes de las de 2 creditos.
        # Asi Seminario y similares no quedan desplazadas por una materia de 2cr
        # cuando solo habia 1 credito libre.
        if usados < cred_max:
            disponibles_1cr = [
                m for m in disponibles if m.creditos == 1 and m not in semestre_mats
            ]
            for mat in disponibles_1cr:
                if usados + mat.creditos <= cred_max:
                    semestre_mats.append(mat)
                    usados += mat.creditos

        # FASE 3: Agregar UNA materia de 2 créditos si hay disponible
        if usados <= 18 and disponibles_2cr_sorted:
            mat_2cr = disponibles_2cr_sorted[0]
            if mat_2cr not in semestre_mats and usados + mat_2cr.creditos <= cred_max:
                semestre_mats.append(mat_2cr)
                usados += mat_2cr.creditos

        # FASE 4: Si aun falta para llegar al maximo, rellenar con las materias
        # grandes (3cr+) que quepan.
        # Aqui habia una segunda pasada de materias de 1cr identica a la FASE 2;
        # era codigo muerto: la FASE 2 solo deja fuera una materia de 1cr cuando
        # usados ya llego a cred_max, y en ese caso este bloque no se ejecuta
        # (ni la FASE 3 puede subir usados, porque exige usados + 2 <= cred_max).
        if usados < cred_max:
            disponibles_grandes = [
                m for m in disponibles
                if m.creditos != 1 and m not in semestre_mats
            ]
            disponibles_grandes.sort(key=lambda m: (m.nivel, -m.creditos))
            for mat in disponibles_grandes:
                if usados + mat.creditos <= cred_max:
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

        ultimo_grupo = list(semestre_mats)

        # Actualizar estado
        for mat in semestre_mats:
            vistas.add(mat.codigo)
            if mat.codigo in pendientes_set:
                del pendientes_set[mat.codigo]
        
        # Actualizar listas auxiliares
        materias_restantes = [m for m in materias_restantes if m.codigo in pendientes_set]
        materias_2cr = [m for m in materias_2cr if m.codigo in pendientes_set]

        semestre += 1

    # Agregar practica al final
    if practica:
        if not prerequisitos_cumplidos(practica, vistas):
            raise PlanIncompletoError([practica])
        materias_con_practica = [practica]
        creditos_practica = practica.creditos

        # Fusionar la cola con la practica cuando cabe.
        #
        # El greedy vacia los pendientes y deja un ultimo semestre con las
        # sobras; la practica caia en uno aparte. En 11 de las 12
        # combinaciones de doble programa eso costaba un semestre entero
        # que no hacia falta.
        #
        # No se fusiona si alguna materia de la cola es prerrequisito de la
        # practica: las de IIND, IMEC e ISCO los tienen, y cursarlas a la
        # vez daria un plan invalido.
        if (not practica_sola and plan and ultimo_grupo):
            creditos_cola = sum(m.creditos for m in ultimo_grupo)
            codigos_cola = {m.codigo for m in ultimo_grupo}
            bloquea = any(pre in codigos_cola for pre in practica.prerrequisitos)
            if not bloquea and creditos_cola + practica.creditos <= cred_max:
                # Se descarta el semestre de la cola y sus materias pasan a
                # acompanar a la practica.
                plan.pop()
                semestre -= 1
                materias_con_practica.extend(ultimo_grupo)
                creditos_practica += creditos_cola

        # Aqui habia dos bloques que, despues del bucle, metian junto a la
        # practica las materias que el greedy no habia colocado. Eran codigo
        # muerto: el bucle solo termina con materias_restantes y materias_2cr
        # vacias, o lanzando PlanIncompletoError. La cola ya se aprovecha con
        # la fusion de arriba.

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
# --- Helpers ----------------------------------------------

def prerequisitos_cumplidos(mat: Materia, aprobadas: Set[str]) -> bool:
    # Con alternativas basta con completar UNO de los caminos.
    if mat.alternativas:
        return any(all(p in aprobadas for p in camino)
                   for camino in mat.alternativas)
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
