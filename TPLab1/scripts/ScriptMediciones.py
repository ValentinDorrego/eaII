"""
organizar_ltspice.py

Parsea el archivo de log/salida de LTspice (las líneas ".step ..." y las
tablas de "Measurement: <nombre>") y organiza los resultados en grupos
donde Rs y Rf quedan fijos y solo varía R.

Ahora soporta automáticamente CUALQUIER medición que aparezca en el log
(por ejemplo "Measurement: vout" y "Measurement: irl" al mismo tiempo),
no hace falta tocar nada para agregar más mediciones: el script las
detecta solas y las muestra como columnas extra.

USO:
    python organizar_ltspice.py archivo_log.txt

Si no se pasa ningún argumento, busca por defecto "log.txt" en el
directorio actual.

SALIDA:
    - Imprime en pantalla, para cada combinación (Rs, Rf) pedida, una tabla
      ordenada por R con TODAS las mediciones encontradas (ej: Vout, I(RL)).
    - Además guarda un .csv por cada combinación (Rs, Rf) en la carpeta
      "salidas_por_combo".
    - Y guarda un único .csv "todo_ordenado.csv" con todos los steps ya
      ordenados por Rs, Rf, R (por si querés revisar/filtrar en Excel).

Podés cambiar la lista COMBOS_OBJETIVO más abajo si necesitás otras
combinaciones de Rs/Rf.
"""

import re
import sys
import csv
import os

# ----------------------------------------------------------------------
# 1) Combinaciones (Rs, Rf) que se quieren extraer, con R variando
#    (según lo que pediste)
# ----------------------------------------------------------------------
COMBOS_OBJETIVO = [
    (10,    1_000),
    (100,   10_000),
    (1_000, 100_000),
    (10_000, 1_000_000),
]


def parsear_log(ruta_archivo):
    """Lee el archivo y devuelve (filas, nombres_mediciones).

    filas: lista de dicts
        [{'step': 1, 'r': 10, 'rf': 1000, 'rs': 10, 'vout': ..., 'irl': ...}, ...]
    nombres_mediciones: lista con los nombres de medición encontrados,
        en el orden en que aparecen en el log (ej: ['vout', 'irl'])
    """
    with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
        contenido = f.read()

    # --- Extraer las líneas .step, en orden (el orden define el número de step) ---
    patron_step = re.compile(
        r"^\.step\s+r=([\d.eE+-]+)\s+rf=([\d.eE+-]+)\s+rs=([\d.eE+-]+)",
        re.MULTILINE,
    )
    steps = []
    for m in patron_step.finditer(contenido):
        r, rf, rs = (float(x) for x in m.groups())
        steps.append({"r": r, "rf": rf, "rs": rs})

    if not steps:
        raise ValueError(
            "No encontré líneas '.step r=... rf=... rs=...' en el archivo."
        )

    # --- Encontrar todos los bloques "Measurement: <nombre>" y parsear cada uno ---
    # Cada bloque termina donde empieza el siguiente "Measurement:" o el fin del archivo.
    patron_bloques = re.compile(
        r"Measurement:\s*(\S+)\s*\n\s*step\s.*?\n(.*?)(?=\nMeasurement:|\Z)",
        re.DOTALL,
    )
    patron_medicion = re.compile(r"^\s*(\d+)\s+([-\d.eE+]+)\s+\S+\s*$", re.MULTILINE)

    mediciones_por_nombre = {}  # nombre -> {step_idx: valor}
    nombres_mediciones = []

    for bloque_match in patron_bloques.finditer(contenido):
        nombre = bloque_match.group(1).strip().lower()
        cuerpo = bloque_match.group(2)
        valores = {}
        for m in patron_medicion.finditer(cuerpo):
            idx = int(m.group(1))
            valores[idx] = float(m.group(2))
        if valores:
            mediciones_por_nombre[nombre] = valores
            nombres_mediciones.append(nombre)

    if not mediciones_por_nombre:
        raise ValueError(
            "No encontré ninguna tabla 'Measurement: ...' en el archivo."
        )

    # --- Combinar: step 1 -> steps[0], etc., con todas las mediciones disponibles ---
    filas = []
    for idx in range(1, len(steps) + 1):
        if idx - 1 >= len(steps):
            continue
        s = steps[idx - 1]
        fila = {"step": idx, "r": s["r"], "rf": s["rf"], "rs": s["rs"]}
        tiene_algo = False
        for nombre in nombres_mediciones:
            valor = mediciones_por_nombre[nombre].get(idx)
            fila[nombre] = valor
            if valor is not None:
                tiene_algo = True
        if tiene_algo:
            filas.append(fila)

    return filas, nombres_mediciones


def formatear_valor(v):
    """Muestra los valores tipo 1000 -> '1k', 1000000 -> '1Meg' para que
    se lea más parecido a como los escribiste vos."""
    if v >= 1_000_000 and v % 1_000_000 == 0:
        return f"{int(v // 1_000_000)}Meg"
    if v >= 1_000 and v % 1_000 == 0:
        return f"{int(v // 1_000)}k"
    return str(int(v)) if v == int(v) else str(v)


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else "log.txt"

    if not os.path.isfile(ruta):
        print(f"No encontré el archivo '{ruta}'.")
        print("Uso: python organizar_ltspice.py archivo_log.txt")
        sys.exit(1)

    filas, nombres_mediciones = parsear_log(ruta)
    print(f"Mediciones encontradas en el log: {', '.join(nombres_mediciones)}\n")

    encabezados = ["step", "Rs", "Rf", "R"] + [n.upper() for n in nombres_mediciones]

    # --- Guardar todo ordenado en un csv general ---
    filas_ordenadas = sorted(filas, key=lambda f: (f["rs"], f["rf"], f["r"]))
    with open("todo_ordenado.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(encabezados)
        for fila in filas_ordenadas:
            writer.writerow(
                [fila["step"], fila["rs"], fila["rf"], fila["r"]]
                + [fila.get(n) for n in nombres_mediciones]
            )
    print("Guardado: todo_ordenado.csv (todos los steps, ordenados por Rs, Rf, R)\n")

    os.makedirs("salidas_por_combo", exist_ok=True)

    # --- Por cada combinación (Rs, Rf) objetivo, filtrar y ordenar por R ---
    for rs_obj, rf_obj in COMBOS_OBJETIVO:
        grupo = [
            f for f in filas if f["rs"] == rs_obj and f["rf"] == rf_obj
        ]
        grupo.sort(key=lambda f: f["r"])

        titulo = f"Rs = {formatear_valor(rs_obj)}   Rf = {formatear_valor(rf_obj)}   (R variable)"
        print(titulo)
        print("-" * len(titulo))
        if not grupo:
            print("  (no se encontraron steps para esta combinación)\n")
            continue

        # encabezado de la tabla en pantalla
        cabecera = f"{'R':>12} | " + " | ".join(f"{n.upper():>15}" for n in nombres_mediciones)
        print(cabecera)
        for fila in grupo:
            valores = " | ".join(
                f"{fila.get(n):>15.6g}" if fila.get(n) is not None else f"{'--':>15}"
                for n in nombres_mediciones
            )
            print(f"{formatear_valor(fila['r']):>12} | {valores}")
        print()

        # guardar csv individual
        nombre_csv = f"salidas_por_combo/Rs{formatear_valor(rs_obj)}_Rf{formatear_valor(rf_obj)}.csv"
        with open(nombre_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["R"] + [n.upper() for n in nombres_mediciones])
            for fila in grupo:
                writer.writerow([fila["r"]] + [fila.get(n) for n in nombres_mediciones])

    print("Listo. Revisá la carpeta 'salidas_por_combo' para los .csv individuales.")


if __name__ == "__main__":
    main()