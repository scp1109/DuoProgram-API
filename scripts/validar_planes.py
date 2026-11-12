# -*- coding: utf-8 -*-
"""Verifica el motor de planificacion contra las mallas reales de la BD.

Uso (desde la carpeta duo_program_api, con MySQL encendido):
    .\\venv\\Scripts\\python.exe scripts\\validar_planes.py

Sale con codigo 0 solo si TODO pasa.

Por que esta escrito asi
------------------------
Una version anterior de este script daba "0 planes invalidos" mientras el
motor generaba planes a los que les faltaban materias y que colocaban una
materia junto a su propio prerrequisito. Fallaba por dos razones:
  1. solo comprobaba el ORDEN, nunca que el plan estuviera COMPLETO;
  2. reutilizaba la misma regla de prerrequisitos que el motor, asi que
     heredaba sus errores.
Por eso aqui todas las reglas se reimplementan sin importar nada del motor
salvo generar_plan, y se comprueba completitud con dos oraculos:
  - para un programa unico, los creditos del plan deben ser EXACTAMENTE los
    de la malla (Programa.total_creditos), que no depende del motor;
  - para doble programa, cada obligatoria y cada electiva exigida debe estar.

Reglas de doble programa que se comprueban
------------------------------------------
- Se cursa la practica del principal; la del secundario queda cubierta.
- Proyectos: dos proyectos de programas DISTINTOS con la misma etiqueta
  `proyecto_compartido` son el mismo y se cursa uno. Dentro de un mismo
  programa cada proyecto cuenta aunque compartan etiqueta.
- Electivas: un grupo se cubre con una materia ya aprobada o con una
  obligatoria del OTRO programa. Nunca con una obligatoria del propio
  programa dueno del grupo: esa ya se cursa por obligatoria y contarla dos
  veces le quitaria al estudiante una electiva.
- Prerrequisitos de una materia compartida: se compara lo que un programa
  pide DIRECTAMENTE con el CIERRE transitivo del otro. Si uno queda dentro
  de la cadena del otro, se exigen ambas listas. Si no, son caminos
  alternativos y basta con uno.
- Un proyecto aprobado o planificado cumple como prerrequisito a su
  equivalente del otro programa.
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import db_programas  # noqa: E402
from motor.planificador import (  # noqa: E402
    ParametrosPlan, PlanIncompletoError, generar_plan)

PROGRAMAS = db_programas.get_programas()
CODIGOS = sorted(PROGRAMAS)
CODIGOS_INGLES = db_programas.get_codigos_ingles()
TOPE = {4.2: 20, 3.5: 18}


# ── Utilidades de malla, independientes del motor ──────────────────────
def slots_de(prog):
    return {s for g in prog.grupos_electivas for s in g.slot_codigos}


def obligatorias(prog):
    """Materias de la malla que no son slots de electiva."""
    slots = slots_de(prog)
    return {m.codigo: m for m in prog.materias if m.codigo not in slots}


def prereqs_de(prog):
    return {m.codigo: set(m.prerrequisitos) for m in prog.materias}


def cierre(cod, grafo, memo):
    """Todos los prerrequisitos de cod, directos e indirectos, en un programa."""
    if cod in memo:
        return memo[cod]
    memo[cod] = set()  # corta ciclos
    total = set()
    for pre in grafo.get(cod, ()):
        total |= {pre} | cierre(pre, grafo, memo)
    memo[cod] = total
    return total


def caminos(cod, progs):
    """Lista de caminos aceptables para cursar cod en este doble programa.
    Cada camino es el conjunto de prerrequisitos DIRECTOS de un programa."""
    versiones = []
    for prog in progs:
        g = prereqs_de(prog)
        if cod in g:
            versiones.append((g[cod], cierre(cod, g, {})))
    if not versiones:
        return []
    if len(versiones) == 1:
        return [versiones[0][0]]
    (da, ca), (db, cb) = versiones
    # Si lo que un programa pide directamente ya esta en la cadena del otro,
    # los dos exigen ambas listas. Cierre contra cierre no sirve: una
    # diferencia rio arriba (Calculo Vectorial en IMEC) volvia alternativas
    # dos versiones que no lo eran (Procesamiento Numerico sin POO).
    if da <= cb or db <= ca:
        return [da | db]
    return [da, db]


# ── Lo que el plan DEBE contener ───────────────────────────────────────
def esperado(p, s, aprobadas):
    """Devuelve (obligatorias que deben aparecer, {tipo: n electivas})."""
    progs = [PROGRAMAS[p]] + ([PROGRAMAS[s]] if s else [])
    obl = {}
    for prog in progs:
        obl[prog.codigo] = obligatorias(prog)

    requeridas = set()
    etiquetas_por_prog = {}
    for prog in progs:
        for m in obl[prog.codigo].values():
            if m.es_proyecto and m.proyecto_compartido:
                etiquetas_por_prog.setdefault(m.proyecto_compartido, set()).add(prog.codigo)

    vistos_tag = set()
    for prog in progs:
        for cod, m in obl[prog.codigo].items():
            if m.creditos == 0:
                continue
            if m.es_practica and prog.codigo != p:
                continue
            if m.es_proyecto and m.proyecto_compartido:
                tag = m.proyecto_compartido
                compartida = len(etiquetas_por_prog.get(tag, ())) > 1
                if compartida:
                    # Equivalente entre programas: basta con uno, aprobado o no
                    equivalentes = {c for q in progs for c, x in obl[q.codigo].items()
                                    if x.es_proyecto and x.proyecto_compartido == tag}
                    if tag in vistos_tag or equivalentes & aprobadas:
                        vistos_tag.add(tag)
                        continue
                    vistos_tag.add(tag)
            if cod not in aprobadas:
                requeridas.add(cod)

    # Electivas: cada grupo de CADA programa se evalua por separado. No se
    # agrupa por tipo_codigo porque distintos tipos pueden compartir el mismo
    # slot (los tres grupos empresariales usan IIND_EE1A): es una sola
    # casilla y una materia de la interseccion de opciones sirve a ambos.
    todas_obl = {q.codigo: set(obl[q.codigo]) for q in progs}
    grupos = []
    for prog in progs:
        otros = set().union(*([todas_obl[q] for q in todas_obl if q != prog.codigo] or [set()]))
        for g in prog.grupos_electivas:
            cubren = {o.codigo for o in g.opciones
                      if o.codigo not in todas_obl[prog.codigo]
                      and (o.codigo in aprobadas or o.codigo in otros)}
            n = max(0, g.cantidad - len(cubren))
            grupos.append(("%s/%s" % (prog.codigo, g.tipo_codigo), set(g.slot_codigos), n))
    return requeridas, grupos


def todos_los_slots(p, s):
    return set().union(*(slots_de(PROGRAMAS[c]) for c in (p, s) if c))


def equivalentes(progs):
    """codigo de proyecto -> proyectos de OTROS programas con su etiqueta.

    Si el estudiante aprobo IIND_P01A, ISCO_P01A queda cumplido: es el mismo
    proyecto. Sin esto el validador marcaba como invalido que ISCO_P02A se
    cursara sin ISCO_P01A, cuando lo correcto es justamente eso."""
    por_tag = {}
    for prog in progs:
        for m in obligatorias(prog).values():
            if m.es_proyecto and m.proyecto_compartido:
                por_tag.setdefault(m.proyecto_compartido, []).append((prog.codigo, m.codigo))
    eq = {}
    for miembros in por_tag.values():
        for pa, ca in miembros:
            eq[ca] = {cb for pb, cb in miembros if pb != pa}
    return eq


def con_equivalentes(hechas, eq):
    return hechas | {e for c in hechas for e in eq.get(c, ())}


# ── Revision de un plan ─────────────────────────────────────────────────
def origen_esperado(cod, p, s, eq):
    """Origen que la app muestra en cada materia, derivado de las mallas."""
    en_p = PROGRAMAS[p].get_materia(cod) is not None
    en_s = bool(s) and PROGRAMAS[s].get_materia(cod) is not None
    m = PROGRAMAS[p].get_materia(cod) or (PROGRAMAS[s].get_materia(cod) if s else None)
    if m is not None and m.es_practica:
        return "practica", True
    if en_p and (en_s or eq.get(cod)):
        return "compartida", True
    if en_s:
        return "secundario", False
    return "principal", False


def revisar(p, s, aprobadas, promedio, sola, ingles=0, cursados=0):
    try:
        plan = generar_plan(ParametrosPlan(
            codigo_programa_principal=p, codigo_programa_secundario=s,
            aprobadas=set(aprobadas), niveles_ingles_homologados=set(range(1, ingles + 1)),
            promedio=promedio, semestres_cursados=cursados, homologaciones_externas=[],
            practica_sola=sola,
        ))
    except PlanIncompletoError as e:
        return [], ["el motor no pudo completar el plan: %s" % e.codigos]
    # Homologar el nivel N de ingles equivale a tener aprobados del 1 al N.
    aprobadas = set(aprobadas) | set(CODIGOS_INGLES[:ingles])
    progs = [PROGRAMAS[p]] + ([PROGRAMAS[s]] if s else [])
    eq = equivalentes(progs)
    fallos = []
    cod_plan = [m.codigo for sem in plan for m in sem.materias]

    # Forma del plan: numeracion, sumas y banderas
    for i, sem in enumerate(plan):
        if sem.numero != cursados + 1 + i:
            fallos.append("semestre %d numerado %d" % (cursados + 1 + i, sem.numero))
        suma = sum(m.creditos for m in sem.materias)
        if sem.total_creditos != suma:
            fallos.append("sem %d: total_creditos %d, suma real %d" % (sem.numero, sem.total_creditos, suma))
        if sem.es_primero != (i == 0) or sem.es_ultimo != (i == len(plan) - 1):
            fallos.append("sem %d: banderas primero/ultimo mal puestas" % sem.numero)
        for m in sem.materias:
            if (m.origen, m.sirve_para_ambas) != origen_esperado(m.codigo, p, s, eq):
                fallos.append("%s: origen %s/%s, se esperaba %s/%s" % (
                    (m.codigo, m.origen, m.sirve_para_ambas) + origen_esperado(m.codigo, p, s, eq)))

    # Duplicados y materias ya aprobadas
    dup = {c for c in cod_plan if cod_plan.count(c) > 1}
    if dup:
        fallos.append("duplicadas: %s" % sorted(dup))
    rep = set(cod_plan) & set(aprobadas)
    if rep:
        fallos.append("ya aprobadas y vueltas a planificar: %s" % sorted(rep))

    # Orden y tope
    hechas = set(aprobadas) | {m.codigo for prog in progs
                                for m in prog.materias if m.creditos == 0}
    slots = todos_los_slots(p, s)
    for sem in plan:
        hechas = con_equivalentes(hechas, eq)
        en_sem = {m.codigo for m in sem.materias}
        if sem.total_creditos > TOPE[promedio]:
            fallos.append("sem %d: %d cr > tope %d" % (sem.numero, sem.total_creditos, TOPE[promedio]))
        for c in en_sem:
            cams = caminos(c, progs)
            if cams and not any(cam <= hechas for cam in cams):
                junto = sorted(set().union(*cams) & en_sem)
                fallos.append("sem %d: %s %s" % (
                    sem.numero, c,
                    "junto a su prerrequisito %s" % junto[0] if junto
                    else "sin prerrequisitos cumplidos"))
        hechas |= en_sem

    # Completitud
    requeridas, grupos = esperado(p, s, set(aprobadas))
    faltan = requeridas - set(cod_plan)
    if faltan:
        fallos.append("faltan obligatorias: %s" % sorted(faltan))
    sobran = {c for c in cod_plan if c not in requeridas and c not in slots}
    if sobran:
        fallos.append("materias que no se exigen: %s" % sorted(sobran))
    en_plan = {c for c in cod_plan if c in slots}
    # Cada grupo debe tener al menos las electivas que exige...
    for nombre, sl, n in grupos:
        if len(en_plan & sl) < n:
            fallos.append("electivas %s: %d en el plan, se exigen %d" % (nombre, len(en_plan & sl), n))
    # ...y ningun slot del plan puede sobrar: debe ser imprescindible para
    # al menos un grupo, o el estudiante cursaria una electiva de mas.
    for slot in en_plan:
        if not any(slot in sl and len(en_plan & sl) <= n for _, sl, n in grupos):
            fallos.append("electiva de mas: %s" % slot)

    # Practica: la del principal, al final
    pr = [m.codigo for m in obligatorias(PROGRAMAS[p]).values() if m.es_practica]
    if pr and pr[0] not in aprobadas:
        if not plan or pr[0] not in {m.codigo for m in plan[-1].materias}:
            fallos.append("la practica %s no esta en el ultimo semestre" % pr[0])
        elif sola and len(plan[-1].materias) > 1:
            # practica_sola: el estudiante pidio el ultimo semestre solo
            # para la practica.
            fallos.append("practica_sola pero el ultimo semestre trae %s" % sorted(
                m.codigo for m in plan[-1].materias if m.codigo != pr[0]))
    return plan, fallos


def cota_inferior(plan_creditos, tope, cadena):
    """Semestres minimos posibles: por creditos y por la cadena de
    prerrequisitos mas larga. Sirve para medir que tan lejos queda el greedy."""
    return max(-(-plan_creditos // tope), cadena)


def cadena_mas_larga(codigos, progs, hechas):
    """Largo (en semestres) de la cadena de prerrequisitos pendientes mas larga."""
    memo = {}

    def largo(c):
        if c in memo:
            return memo[c]
        memo[c] = 1
        pres = [x for cam in caminos(c, progs) for x in cam if x in codigos and x not in hechas]
        memo[c] = 1 + max((largo(x) for x in pres), default=0)
        return memo[c]
    return max((largo(c) for c in codigos), default=0)


# ── Escenarios ──────────────────────────────────────────────────────────
def niveles(c, k):
    return {m.codigo for m in obligatorias(PROGRAMAS[c]).values() if m.nivel <= k}


def historiales(p, s):
    """Historiales a medias. No basta con el principal: el error de Proyecto
    II solo aparecia cuando lo aprobado venia del SECUNDARIO, y la version
    anterior de este script nunca lo probo."""
    yield "nada", set()
    for k in (2, 4, 6, 8):
        yield "%s 1-%d" % (p, k), niveles(p, k)
        yield "%s 1-%d" % (s, k), niveles(s, k)
        yield "ambos 1-%d" % k, niveles(p, k) | niveles(s, k)


def proyectos_cruzados():
    """Proyectos aprobados en el otro programa, uno a uno y en cadena."""
    for p, s in itertools.permutations(CODIGOS, 2):
        eq = equivalentes([PROGRAMAS[p], PROGRAMAS[s]])
        ajenos = sorted(c for c in eq if c.startswith(s + "_") and eq[c])
        for n in range(1, len(ajenos) + 1):
            yield p, s, set(ajenos[:n])


def main():
    total = malos = 0
    ejemplos = []

    def registrar(etiqueta, fallos):
        nonlocal total, malos
        total += 1
        if fallos:
            malos += 1
            if len(ejemplos) < 12:
                ejemplos.append("%s -> %s" % (etiqueta, fallos[0]))

    print("1. PROGRAMA UNICO: creditos del plan = creditos de la malla")
    for p in CODIGOS:
        plan, fallos = revisar(p, None, set(), 4.2, False)
        cr = sum(sem.total_creditos for sem in plan)
        malla = PROGRAMAS[p].total_creditos()
        if cr != malla:
            fallos = ["plan %d cr, malla %d cr" % (cr, malla)] + fallos
        registrar("%s solo" % p, fallos)
        print("   %-5s plan %3d / malla %3d  %s" % (p, cr, malla, "OK" if not fallos else "FALLA: " + fallos[0]))

    print("\n1b. PROGRAMA UNICO con historial: plan = malla - lo aprobado")
    antes = total
    for p in CODIGOS:
        for k in (2, 4, 6, 8):
            hechas = niveles(p, k)
            plan, fallos = revisar(p, None, hechas, 4.2, False)
            cr = sum(sem.total_creditos for sem in plan)
            # hechas sale de niveles(), que solo toma obligatorias de esta
            # malla: el diccionario las tiene todas (get_materia es Optional).
            malla_p = obligatorias(PROGRAMAS[p])
            esperado_cr = PROGRAMAS[p].total_creditos() - sum(
                malla_p[c].creditos for c in hechas)
            if cr != esperado_cr:
                fallos = ["plan %d cr, se esperaban %d" % (cr, esperado_cr)] + fallos
            registrar("%s solo, aprobado 1-%d" % (p, k), fallos)
    print("   escenarios: %d" % (total - antes))

    print("\n2. DOBLE PROGRAMA: validez y completitud con historiales a medias")
    antes = total
    for p, s in itertools.permutations(CODIGOS, 2):
        for desc, hechas in historiales(p, s):
            for promedio in (4.2, 3.5):
                for sola in (False, True):
                    _, fallos = revisar(p, s, hechas, promedio, sola)
                    registrar("%s+%s aprobado %s prom %.1f sola=%s" % (p, s, desc, promedio, sola), fallos)
    print("   escenarios: %d" % (total - antes))

    print("\n2b. PROYECTOS aprobados en el otro programa")
    antes = total
    for p, s, hechas in proyectos_cruzados():
        for base in (set(), niveles(p, 7)):
            for sola in (False, True):
                _, fallos = revisar(p, s, base | hechas, 4.2, sola)
                registrar("%s+%s aprobado %s%s sola=%s" % (
                    p, s, sorted(hechas), " + niveles 1-7" if base else "", sola), fallos)
    print("   escenarios: %d" % (total - antes))

    print("\n2c. INGLES homologado y SEMESTRES ya cursados")
    antes = total
    for p, s in itertools.permutations(CODIGOS, 2):
        for n in (1, 3, 5):
            for base in (set(), niveles(p, 2)):
                _, fallos = revisar(p, s, base, 4.2, False, ingles=n)
                registrar("%s+%s ingles 1-%d%s" % (p, s, n, " + niveles 1-2" if base else ""), fallos)
        _, fallos = revisar(p, s, niveles(p, 4), 3.5, True, cursados=4)
        registrar("%s+%s 4 semestres cursados" % (p, s), fallos)
    for p in CODIGOS:
        _, fallos = revisar(p, None, set(), 4.2, False, ingles=3)
        registrar("%s solo, ingles 1-3" % p, fallos)
    print("   escenarios: %d" % (total - antes))

    print("\n2d. EFICIENCIA (informativo): semestres del plan frente a la cota inferior")
    peor = []
    for p, s in itertools.permutations(CODIGOS, 2):
        for promedio in (4.2, 3.5):
            plan, _ = revisar(p, s, set(), promedio, False)
            if not plan:
                continue
            progs = [PROGRAMAS[p], PROGRAMAS[s]]
            cods = {m.codigo for sem in plan for m in sem.materias}
            cr = sum(sem.total_creditos for sem in plan)
            cota = cota_inferior(cr, TOPE[promedio], cadena_mas_larga(cods, progs, set()))
            peor.append((len(plan) - cota, "%s+%s prom %.1f" % (p, s, promedio), len(plan), cota))
    peor.sort(reverse=True)
    exactos = sum(1 for d, *_ in peor if d == 0)
    print("   en la cota: %d de %d   semestres de mas, maximo: %d" % (exactos, len(peor), peor[0][0]))
    for d, desc, n, cota in peor[:3]:
        if d:
            print("     %-22s %d semestres, cota %d" % (desc, n, cota))

    print("\n3. REGRESIONES de casos reportados")
    # Se comprueba DISPONIBILIDAD (prerrequisitos cumplidos al empezar), no
    # que la materia caiga en el primer semestre: el greedy puede dejarla
    # para el siguiente si el cupo ya esta lleno, y eso no es un error.
    from motor.planificador import (
        cargar_aprobadas, fusionar_grupos, calcular_electivas_cubiertas,
        placeholders_necesarios, materias_pendientes, prerequisitos_cumplidos)

    def disponibles_al_inicio(p, s, hechas):
        params = ParametrosPlan(p, s, set(hechas), set(), 4.2, 0, [], False)
        pp, ps = PROGRAMAS[p], PROGRAMAS[s]
        ap = cargar_aprobadas(params, pp, ps)
        gr = fusionar_grupos(pp, ps)
        ph = placeholders_necesarios(
            gr, calcular_electivas_cubiertas(gr, ap, set(), pp, ps), ap)
        return {m.codigo for m in materias_pendientes(pp, ps, ap, ph, params)
                if prerequisitos_cumplidos(m, ap)}

    casos = [
        # Caminos alternativos: cada programa pone su propio curso de
        # programacion. Con la union pura estas dos desaparecian.
        ("ISCO", "CDAT", niveles("ISCO", 3), ["ISCO_C05A", "ISCO_C06A"], True,
         "ISCO+CDAT: Estructura y Discreta disponibles tras POO"),
        # Cierre transitivo: IIND exige Electricidad, que exige Mecanica; con
        # solo Mecanica aprobada, Calor y Ondas NO debe estar disponible.
        ("ISCO", "IIND", {"CBAS_F01A", "CBAS_M01A", "CBAS_M02A", "CBAS_M03A"},
         ["CBAS_F03A"], False,
         "ISCO+IIND: Calor y Ondas bloqueada sin Electricidad"),
        # Una diferencia rio arriba no vuelve alternativas a dos versiones
        # que no lo son: ISCO exige POO para Procesamiento Numerico, y que
        # IMEC declare Calculo Vectorial distinto no lo cambia.
        ("IMEC", "ISCO", (niveles("ISCO", 3) | {"CBAS_M01A", "CBAS_M02A", "CBAS_M03A",
                                                "CBAS_M04A", "CBAS_M05A", "CBAS_M06A"})
         - {"ISCO_C04A"},
         ["ISCO_C07A"], False,
         "IMEC+ISCO: Proc. Numerico bloqueada sin POO"),
    ]
    for p, s, hechas, cods, esperado_disp, desc in casos:
        disp = disponibles_al_inicio(p, s, hechas)
        ok = all((c in disp) == esperado_disp for c in cods)
        registrar(desc, [] if ok else ["%s: disponible=%s, se esperaba %s"
                                       % (cods, [c in disp for c in cods], esperado_disp)])
        print("   %-55s %s" % (desc, "OK" if ok else "FALLA"))

    print("\n" + "=" * 70)
    print("escenarios totales: %d   con fallos: %d   %s" % (total, malos, "OK" if malos == 0 else "<-- FALLA"))
    for e in ejemplos:
        print("   -", e)
    sys.exit(1 if malos else 0)


if __name__ == "__main__":
    main()
