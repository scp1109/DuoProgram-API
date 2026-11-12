# -*- coding: utf-8 -*-
"""Verifica el motor de planificacion contra las mallas reales de la BD.

Uso (desde la carpeta duo_program_api, con MySQL encendido):
    .\\venv\\Scripts\\python.exe scripts\\validar_planes.py

Hace dos comprobaciones:

1. VALIDEZ. Genera planes para todas las combinaciones de doble programa,
   con dos promedios, tres puntos de partida y practica sola o no
   (144 escenarios), y revisa semestre a semestre que:
     - ninguna materia vaya junto a su prerrequisito en el mismo semestre
     - todo prerrequisito este aprobado en un semestre anterior
     - ningun semestre supere el tope de creditos
   Debe dar 0 planes invalidos.

2. EFICIENCIA. Para cada combinacion desde cero compara los semestres del
   plan contra la cota minima teorica: max(creditos / tope, cadena de
   prerrequisitos mas larga). Ningun algoritmo puede bajar de esa cota.
"""
import math
import os
import sys

# Permite ejecutarlo desde la raiz del proyecto o desde scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import db_programas  # noqa: E402
from motor.planificador import ParametrosPlan, generar_plan  # noqa: E402

PROGRAMAS = db_programas.get_programas()
CODIGOS = sorted(PROGRAMAS)


def generar(p, s, promedio=4.2, cursados=0, practica_sola=False):
    return generar_plan(ParametrosPlan(
        codigo_programa_principal=p,
        codigo_programa_secundario=s,
        aprobadas=set(),
        niveles_ingles_homologados=set(),
        promedio=promedio,
        semestres_cursados=cursados,
        homologaciones_externas=[],
        practica_sola=practica_sola,
    ))


def combinar(a, b):
    """La regla de doble programa, reimplementada aqui A PROPOSITO en vez de
    importarla del motor: si el test usara la misma funcion que prueba, no
    podria detectar que la regla esta mal (eso paso con la union pura).
      - una lista contiene a la otra -> manda la mas estricta
      - no se contienen -> caminos alternativos, basta con uno
    Devuelve una lista de caminos; cumplir cualquiera alcanza."""
    if a <= b:
        return [b]
    if b <= a:
        return [a]
    return [a, b]


def indice(p, s):
    """{materia: [camino, ...]} combinando los dos programas."""
    por_prog = {}
    for prog in (PROGRAMAS[p], PROGRAMAS[s]):
        for m in prog.materias:
            por_prog.setdefault(m.codigo, []).append(set(m.prerrequisitos))
    idx = {}
    for cod, listas in por_prog.items():
        caminos = [listas[0]]
        for otra in listas[1:]:
            caminos = combinar(caminos[0], otra) if len(caminos) == 1 else caminos
        idx[cod] = caminos
    return idx


def fallos_de(plan, idx, tope):
    fallos = []
    aprobadas = set()
    for sem in plan:
        en_sem = {m.codigo for m in sem.materias}
        for m in sem.materias:
            caminos = idx.get(m.codigo)
            if not caminos:
                continue
            # Solo cuentan prerrequisitos que existen en la malla combinada
            ok = any(all(pre in aprobadas for pre in camino if pre in idx)
                     for camino in caminos)
            if not ok:
                junto = [pre for c in caminos for pre in c if pre in en_sem]
                fallos.append("sem %d: %s %s" % (
                    sem.numero, m.codigo,
                    "junto a su prerrequisito " + junto[0] if junto
                    else "sin ningun camino de prerrequisitos cumplido"))
        if sem.total_creditos > tope:
            fallos.append("sem %d: %d creditos, tope %d"
                          % (sem.numero, sem.total_creditos, tope))
        aprobadas |= en_sem
    return fallos


def cadena_mas_larga(codigos, idx):
    memo = {}

    def largo(c, pila):
        if c in memo:
            return memo[c]
        if c in pila or c not in idx:
            return 0
        pila.add(c)
        # El camino mas corto de los alternativos es el que limita
        r = 1 + min((max((largo(p, pila) for p in camino if p in codigos),
                         default=0) for camino in idx[c]), default=0)
        pila.discard(c)
        memo[c] = r
        return r

    return max((largo(c, set()) for c in codigos), default=0)


def main():
    print("1. VALIDEZ DE LOS PLANES")
    total = invalidos = 0
    ejemplos = []
    for p in CODIGOS:
        for s in CODIGOS:
            if p == s:
                continue
            idx = indice(p, s)
            for promedio in (4.2, 3.5):
                tope = 20 if promedio >= 4.0 else 18
                for cursados in (0, 3, 6):
                    for sola in (False, True):
                        total += 1
                        f = fallos_de(generar(p, s, promedio, cursados, sola),
                                      idx, tope)
                        if f:
                            invalidos += 1
                            ejemplos.append("%s+%s prom %.1f: %s"
                                            % (p, s, promedio, f[0]))
    print("   escenarios probados: %d" % total)
    print("   planes invalidos   : %d  %s"
          % (invalidos, "OK" if invalidos == 0 else "<-- FALLA"))
    for e in ejemplos[:5]:
        print("     -", e)

    # Regresion: el caso real que reporto el usuario. Un estudiante de
    # ISCO + CDAT con los semestres 1-3 de ISCO aprobados debe poder ver
    # Estructura de Datos y Matematica Discreta en el semestre 4. Con la
    # union pura de prerrequisitos se le exigia tambien el curso de
    # programacion de CDAT y las dos materias desaparecian.
    print("\n2. REGRESION: ISCO + CDAT, semestres 1-3 de ISCO aprobados")
    from motor.planificador import (
        cargar_aprobadas, fusionar_grupos, calcular_electivas_cubiertas,
        placeholders_necesarios, materias_pendientes, prerequisitos_cumplidos)
    isco, cdat = PROGRAMAS["ISCO"], PROGRAMAS["CDAT"]
    hechas = {m.codigo for m in isco.materias if m.nivel <= 3}
    params = ParametrosPlan("ISCO", "CDAT", hechas, set(), 4.2, 3, [], False)
    ap = cargar_aprobadas(params, isco, cdat)
    gr = fusionar_grupos(isco, cdat)
    ph = placeholders_necesarios(
        gr, calcular_electivas_cubiertas(gr, ap, set(), isco, cdat), ap)
    pend = {m.codigo: m for m in materias_pendientes(isco, cdat, ap, ph, params)}
    for cod, nombre in (("ISCO_C05A", "Estructura de Datos"),
                        ("ISCO_C06A", "Matematica Discreta")):
        disponible = cod in pend and prerequisitos_cumplidos(pend[cod], ap)
        if not disponible:
            invalidos += 1
        print("   %-22s disponible en sem 4: %s"
              % (nombre, "SI  OK" if disponible else "NO  <-- FALLA"))

    print("\n3. EFICIENCIA (desde cero, promedio 4.2, tope 20)")
    print("   combinacion   plan  cota  exceso")
    optimos = 0
    for p in CODIGOS:
        for s in CODIGOS:
            if p == s:
                continue
            plan = generar(p, s)
            idx = indice(p, s)
            codigos = {m.codigo for sem in plan for m in sem.materias}
            creditos = sum(sem.total_creditos for sem in plan)
            cota = max(math.ceil(creditos / 20), cadena_mas_larga(codigos, idx))
            exceso = len(plan) - cota
            optimos += exceso == 0
            print("   %s + %s     %3d   %3d   %+d" % (p, s, len(plan), cota, exceso))
    print("   en la cota minima: %d de 12" % optimos)

    sys.exit(1 if invalidos else 0)


if __name__ == "__main__":
    main()
