"""Genera la página del monitor de emisores.

Lee datos/<carpeta>/<archivo> (por defecto 'EEFF 2025.md') para cada emisor de config/emisores.json,
extrae activos, pasivos, patrimonio, utilidad e ingresos según las reglas del emisor,
verifica la identidad contable y escribe:
    docs/index.html   (página publicada en GitHub Pages)
    docs/datos.json   (cifras y estado de cada emisor)

Uso:  python scripts/generar_monitor.py [carpeta_datos] [carpeta_salida]
"""
import html
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAIZ = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "datos"
SALIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "docs"
NOTICIAS = BASE / "noticias" / "ultimas.json"
ARCHIVO_DEFECTO = "EEFF 2025.md"
CAMPOS = ["activos", "pasivos", "patrimonio", "utilidad", "ingresos"]
# Patrones genericos; cada emisor puede sobreescribirlos en config/emisores.json
GENERICOS = {
    "activos": r"^total (de )?activos$|^total assets$",
    "pasivos": r"^total (de )?pasivos$|^total liabilities$",
    "patrimonio": r"^total (de )?patrimonio$|^total equity$|^total net assets$",
    "utilidad": r"^utilidad (neta|del ejercicio)$|^net income$",
    "ingresos": r"^total ingresos operacionales$|^total investment income$|^total revenues?$",
}


def norm(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\*+|_+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def a_numero(tok):
    neg = tok.startswith("(") or tok.startswith("-")
    t = tok.strip("()-")
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        partes = t.split(sep)
        dec = None if (len(partes) > 2 or len(partes[-1]) == 3) else sep
    else:
        dec = None
    if dec:
        ent, frac = t.rsplit(dec, 1)
        t = re.sub(r"[.,]", "", ent) + "." + frac
    else:
        t = re.sub(r"[.,]", "", t)
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def numeros(celdas):
    out = []
    for c in celdas:
        for tok in re.findall(r"\(?-?\d[\d.,]*\)?", c.replace(" ", " ")):
            v = a_numero(tok)
            if v is not None:
                out.append(v)
    # quita el indice de nota (entero pequeno al inicio de la fila)
    if len(out) >= 3 and out[0] == int(out[0]) and 0 < out[0] < 100 and out[0] != out[1]:
        out = out[1:]
    return out


def filas(texto):
    """Cada celda con texto puede ser etiqueta; los numeros son los de las celdas siguientes."""
    for ln in texto.splitlines():
        if not ln.startswith("|"):
            continue
        celdas = [c.strip() for c in ln.strip().strip("|").split("|")]
        for i, c in enumerate(celdas):
            if re.search(r"[a-zA-Z]", norm(c)):
                yield norm(c), numeros(celdas[i + 1:])


def leer_campo(texto, campo, regla):
    """patron null = no leer (se deriva). ocurrencia = cual coincidencia usar (1 = primera). col = columna numerica."""
    if "patron" in regla and regla["patron"] is None:
        return None
    patron = regla.get("patron", GENERICOS[campo])
    col = regla.get("col", 0)
    escala = regla.get("escala", 1)
    ocurrencia = regla.get("ocurrencia", 1)
    n = 0
    for etiq, nums in filas(texto):
        if re.search(patron, etiq) and nums:
            n += 1
            if n < ocurrencia:
                continue
            try:
                return nums[col] * escala
            except IndexError:
                continue
    return None


def extraer(md, reglas):
    texto = md.read_text(encoding="utf-8", errors="ignore")
    r = {c: leer_campo(texto, c, reglas.get(c, {})) for c in CAMPOS}
    r["_derivado"] = []
    if r["patrimonio"] is None and r["activos"] is not None and r["pasivos"] is not None:
        r["patrimonio"] = r["activos"] - r["pasivos"]
        r["_derivado"].append("patrimonio")
    if r["pasivos"] is None and r["activos"] is not None and r["patrimonio"] is not None:
        r["pasivos"] = r["activos"] - r["patrimonio"]
        r["_derivado"].append("pasivos")
    a, p, q = r["activos"], r["pasivos"], r["patrimonio"]
    if None not in (a, p, q):
        dif = abs(a - (p + q)) / abs(a) if a else 1
        r["estado"] = "verificado" if dif < 0.005 else "revisar"
    elif any(v is not None for v in (a, p, q)):
        r["estado"] = "parcial"
    else:
        r["estado"] = "pendiente"
    return r


def cargar():
    cfg = json.loads((BASE / "config" / "emisores.json").read_text(encoding="utf-8"))
    res = []
    for e in cfg["emisores"]:
        md = RAIZ / e["carpeta"] / e.get("archivo", ARCHIVO_DEFECTO)
        if md.exists():
            r = extraer(md, e.get("reglas", {}))
            r["archivo"] = md.name
        else:
            r = {c: None for c in CAMPOS}
            r.update({"estado": "pendiente", "_derivado": [], "archivo": None})
        r.update({"nombre": e["nombre"], "tipo": e["tipo"], "unidad": e["unidad"], "carpeta": e["carpeta"]})
        res.append(r)
    return res


def cargar_noticias():
    if not NOTICIAS.exists():
        return {}
    return json.loads(NOTICIAS.read_text(encoding="utf-8")).get("emisores", {})


def fmt(v):
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", "§").replace(".", ",").replace("§", ".")


CSS = """*{box-sizing:border-box}body{margin:0;font-family:Montserrat,Arial,sans-serif;background:#F4F3F7;color:#1D113E;font-size:13.5px}
header{background:#1D113E;color:#fff;padding:24px 34px}.k{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#6AEB9A;font-weight:600}
h1{margin:6px 0 4px;font-size:24px}h2{font-size:17px;margin:26px 0 10px}.m{color:#D9D6E2;font-size:12.5px}
main{padding:20px 34px 40px}.box{background:#fff;border-radius:10px;box-shadow:0 1px 2px rgba(29,17,62,.08);padding:14px 16px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12.5px}th,td{padding:8px 9px;border-bottom:1px solid #EEEDF3;vertical-align:middle;text-align:left}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#69696A;background:#F7F6FA}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}td.c,th.c{text-align:center;white-space:nowrap}
.ok{background:#B4F5CC;padding:2px 8px;border-radius:10px;font-weight:600;font-size:11.5px;white-space:nowrap}
.warn{background:#E9E7EE;padding:2px 8px;border-radius:10px;font-weight:600;font-size:11.5px;white-space:nowrap}
.pend{border:1px solid #D9D6E2;padding:2px 8px;border-radius:10px;font-weight:600;font-size:11.5px;color:#69696A;white-space:nowrap}
.note{color:#69696A;font-size:12px;margin:12px 0 0}a{color:#1D113E}.nw li{margin:4px 0}.nw ul{margin:0;padding-left:18px}
.nw .fte{color:#69696A;font-size:11.5px}.nav a{margin-right:16px;font-weight:600}"""
BADGE = {"verificado": '<span class="ok">✓ verificado</span>', "parcial": '<span class="warn">◐ parcial</span>',
         "revisar": '<span class="warn">⚠ revisar</span>', "pendiente": '<span class="pend">○ pendiente</span>'}


def tabla(filas_):
    cuerpo = ""
    for r in filas_:
        def celda(campo):
            v = fmt(r[campo])
            return f"{v}*" if campo in r["_derivado"] and r[campo] is not None else v
        cuerpo += (f"<tr><td>{html.escape(r['tipo'])}</td><td>{html.escape(r['nombre'])}</td><td class='c'>{html.escape(r['unidad'])}</td>"
                   f"<td class='n'>{celda('activos')}</td><td class='n'>{celda('pasivos')}</td><td class='n'>{celda('patrimonio')}</td>"
                   f"<td class='n'>{celda('utilidad')}</td><td class='n'>{celda('ingresos')}</td><td class='c'>{BADGE[r['estado']]}</td></tr>")
    return cuerpo


def bloque_noticias(noticias, nombres):
    if not noticias:
        return "<p class='note'>Las noticias se actualizan con el job diario.</p>"
    partes = []
    for carpeta, nombre in nombres:
        items = noticias.get(carpeta)
        if not isinstance(items, list) or not items:
            continue
        lis = "".join(f"<li><a href='{html.escape(i['enlace'])}' target='_blank' rel='noopener'>{html.escape(i['titulo'])}</a> "
                      f"<span class='fte'>{html.escape(i.get('fuente', ''))}</span></li>" for i in items[:5])
        partes.append(f"<div class='box nw' style='margin-bottom:12px'><b>{html.escape(nombre)}</b><ul>{lis}</ul></div>")
    return "".join(partes) or "<p class='note'>Sin noticias de los últimos 7 días.</p>"


def pagina(filas_, noticias):
    cnt = {k: sum(1 for r in filas_ if r["estado"] == k) for k in BADGE}
    nombres = [(r["carpeta"], r["nombre"]) for r in filas_]
    hoy = datetime.now().strftime("%d-%m-%Y")
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor de emisores · Blum SAF</title><style>{CSS}</style></head><body>
<header><div class="k">Blum SAF · Monitor de emisores</div><h1>Cierre 2025 por emisor</h1>
<div class="m">{len(filas_)} emisores · {cnt['verificado']} verificados · {cnt['revisar']} por revisar · {cnt['parcial']} parciales · {cnt['pendiente']} pendientes · actualizado {hoy}</div>
<div class="nav" style="margin-top:12px"><a href="#resumen" style="color:#6AEB9A">Resumen</a><a href="#noticias" style="color:#6AEB9A">Noticias</a><a href="bci.html" style="color:#6AEB9A">Dashboard BCI</a></div></header>
<main>
<h2 id="resumen">Resumen por emisor</h2>
<div class="box"><table><tr><th>Tipo</th><th>Emisor</th><th class="c">Unidad</th><th class="n">Activos</th><th class="n">Pasivos</th>
<th class="n">Patrimonio</th><th class="n">Utilidad</th><th class="n">Ingresos</th><th class="c">Estado</th></tr>{tabla(filas_)}</table>
<p class="note">* Cifra derivada de la identidad activos = pasivos + patrimonio. Verificado: la identidad cuadra con las filas leídas del archivo. Revisar: no cuadra, hay que mirar el archivo. Parcial o pendiente: faltan filas en el EEFF. Cada cifra está en la unidad que reporta su EEFF.</p></div>
<h2 id="noticias">Noticias de los últimos 7 días</h2>
{bloque_noticias(noticias, nombres)}
</main></body></html>"""


if __name__ == "__main__":
    datos = cargar()
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "index.html").write_text(pagina(datos, cargar_noticias()), encoding="utf-8")
    (SALIDA / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(datos)} emisores -> {SALIDA}")
