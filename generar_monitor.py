"""Genera el monitor de emisores (GitHub Pages).

Lee datos/<carpeta>/<archivo> de cada emisor (config/emisores.json), extrae
activos, pasivos, patrimonio, utilidad e ingresos, verifica la identidad contable,
calcula indicadores y escribe:
    docs/index.html            resumen de todos los emisores
    docs/emisores/<slug>.html  analisis de cada emisor
    docs/datos.json            cifras e indicadores de cada emisor

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


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


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


def indicadores(r):
    a, p, q, u, i = (r.get(c) for c in CAMPOS)
    ind = []
    if u is not None and q:
        ind.append(("ROE", u / q * 100, "%", "Utilidad / patrimonio"))
    if u is not None and a:
        ind.append(("ROA", u / a * 100, "%", "Utilidad / activos"))
    if p is not None and q:
        ind.append(("Pasivos / patrimonio", p / q, "x", "Pasivos / patrimonio (apalancamiento)"))
    if q is not None and a:
        ind.append(("Patrimonio / activos", q / a * 100, "%", "Patrimonio / activos"))
    if u is not None and i:
        ind.append(("Margen neto", u / i * 100, "%", "Utilidad / ingresos"))
    return ind


def historia(e):
    """Un registro por ano con EEFF AAAA.md en la carpeta del emisor."""
    out = []
    carpeta = carpeta_de(e["carpeta"])
    if not carpeta.is_dir():
        return out
    for md in sorted(carpeta.glob("EEFF *.md")):
        m = re.fullmatch(r"EEFF (\d{4})\.md", md.name)
        if not m:
            continue
        r = extraer(md, e.get("reglas", {}))
        if r["activos"] is None:
            continue
        r["anio"] = int(m.group(1))
        r["indicadores"] = indicadores(r)
        out.append(r)
    return sorted(out, key=lambda x: x["anio"])


def clave(nombre):
    """Nombre de carpeta/archivo sin diferencias de acentos (NFC/NFD), mayusculas, puntos ni espacios sobrantes."""
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower().replace(".", "")
    return re.sub(r"\s+", " ", s).strip()


def carpeta_de(nombre):
    if not RAIZ.is_dir():
        return RAIZ / nombre
    exacta = RAIZ / nombre
    if exacta.is_dir():
        return exacta
    for d in RAIZ.iterdir():
        if d.is_dir() and clave(d.name) == clave(nombre):
            return d
    return exacta


def archivo_de(carpeta, archivo):
    """El archivo configurado, o cualquier EEFF 2025 .md de la carpeta si el nombre no coincide."""
    if (carpeta / archivo).exists():
        return carpeta / archivo
    for f in sorted(carpeta.glob("*.md")):
        if re.search(r"eeff.*2025", unicodedata.normalize("NFC", f.name).lower()):
            return f
    return carpeta / archivo


def cargar():
    cfg = json.loads((BASE / "config" / "emisores.json").read_text(encoding="utf-8"))
    res = []
    for e in cfg["emisores"]:
        archivo = e.get("archivo", ARCHIVO_DEFECTO)
        md = archivo_de(carpeta_de(e["carpeta"]), archivo)
        if md.exists():
            r = extraer(md, e.get("reglas", {}))
            r["archivo"] = md.name
        else:
            r = {c: None for c in CAMPOS}
            r.update({"estado": "pendiente", "_derivado": [], "archivo": None,
                      "motivo": f"no existe '{archivo}' en la carpeta '{e['carpeta']}' de Drive"})
        if r["estado"] == "pendiente" and "motivo" not in r:
            r["motivo"] = "el archivo existe pero no tiene las filas de balance esperadas"
        r.update({"nombre": e["nombre"], "tipo": e["tipo"], "unidad": e["unidad"],
                  "carpeta": e["carpeta"], "slug": slug(e["nombre"])})
        r["indicadores"] = indicadores(r)
        r["historia"] = historia(e)
        res.append(r)
    return res


def cargar_noticias():
    if not NOTICIAS.exists():
        return {}
    return json.loads(NOTICIAS.read_text(encoding="utf-8")).get("emisores", {})


def fmt(v, dec=0):
    if v is None:
        return "—"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_ind(valor, unidad):
    if unidad == "%":
        return fmt(valor, 1) + " %"
    return fmt(valor, 2) + " x"


CSS = """*{box-sizing:border-box}body{margin:0;font-family:Montserrat,Arial,sans-serif;background:#F4F3F7;color:#1D113E;font-size:13.5px}
header{background:#1D113E;color:#fff;padding:24px 34px}.k{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#6AEB9A;font-weight:600}
h1{margin:6px 0 4px;font-size:24px}h2{font-size:17px;margin:26px 0 10px}.m{color:#D9D6E2;font-size:12.5px}
main{padding:20px 34px 40px}.box{background:#fff;border-radius:10px;box-shadow:0 1px 2px rgba(29,17,62,.08);padding:14px 16px;overflow-x:auto;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:12.5px}th,td{padding:8px 9px;border-bottom:1px solid #EEEDF3;vertical-align:middle;text-align:left}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#69696A;background:#F7F6FA}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}td.c,th.c{text-align:center;white-space:nowrap}
.ok{background:#B4F5CC;padding:2px 8px;border-radius:10px;font-weight:600;font-size:11.5px;white-space:nowrap}
.warn{background:#E9E7EE;padding:2px 8px;border-radius:10px;font-weight:600;font-size:11.5px;white-space:nowrap}
.pend{border:1px solid #D9D6E2;padding:2px 8px;border-radius:10px;font-weight:600;font-size:11.5px;color:#69696A;white-space:nowrap}
.note{color:#69696A;font-size:12px;margin:12px 0 0}a{color:#1D113E}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:14px}
.kpi{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(29,17,62,.08)}
.kpi .l{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#69696A}.kpi .v{font-size:20px;font-weight:700;margin-top:4px}
.kpi .s{font-size:11px;color:#69696A;margin-top:2px}
.nav a{margin-right:16px;font-weight:600;color:#6AEB9A}.nw ul{margin:0;padding-left:18px}.nw li{margin:4px 0}.fte{color:#69696A;font-size:11.5px}"""
BADGE = {"verificado": '<span class="ok">✓ verificado</span>', "parcial": '<span class="warn">◐ parcial</span>',
         "revisar": '<span class="warn">⚠ revisar</span>', "pendiente": '<span class="pend">○ pendiente</span>'}


def pie(hoy):
    return (f"<p class='note'>Cifras en la unidad que reporta cada EEFF. * = cifra derivada de la identidad "
            f"activos = pasivos + patrimonio. Indicadores calculados con las cifras de esta página (actualizado {hoy}).</p>")


def pendientes_log(filas_):
    for r in filas_:
        if r["estado"] == "pendiente":
            print(f"PENDIENTE: {r['nombre']} -> {r.get('motivo', '')}")


def pagina_indice(filas_, hoy):
    cnt = {k: sum(1 for r in filas_ if r["estado"] == k) for k in BADGE}
    cuerpo = ""
    for r in filas_:
        def celda(campo):
            v = fmt(r[campo])
            return f"{v}*" if campo in r["_derivado"] and r[campo] is not None else v
        ind = {n: (v, u) for n, v, u, _ in r["indicadores"]}
        roe = fmt_ind(*ind["ROE"]) if "ROE" in ind else "—"
        apal = fmt_ind(*ind["Pasivos / patrimonio"]) if "Pasivos / patrimonio" in ind else "—"
        marca = f" <span class='fte'>({html.escape(r.get('motivo', ''))})</span>" if r["estado"] == "pendiente" else ""
        cuerpo += (f"<tr><td>{html.escape(r['tipo'])}</td><td><a href='emisores/{r['slug']}.html'>{html.escape(r['nombre'])}</a>{marca}</td>"
                   f"<td class='c'>{html.escape(r['unidad'])}</td><td class='n'>{celda('activos')}</td><td class='n'>{celda('patrimonio')}</td>"
                   f"<td class='n'>{roe}</td><td class='n'>{apal}</td><td class='c'>{BADGE[r['estado']]}</td></tr>")
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor de emisores · Blum SAF</title><style>{CSS}</style></head><body>
<header><div class="k">Blum SAF · Monitor de emisores</div><h1>Cierre 2025 por emisor</h1>
<div class="m">{len(filas_)} emisores · {cnt['verificado']} verificados · {cnt['revisar']} por revisar · {cnt['parcial']} parciales · {cnt['pendiente']} pendientes · actualizado {hoy}</div>
<div class="nav" style="margin-top:12px"><a href="#resumen">Resumen</a><a href="#noticias">Noticias</a><a href="bci.html">Dashboard BCI</a><a href="acciones.html">Acciones</a></div></header>
<main>
<h2 id="resumen">Resumen por emisor</h2>
<div class="box"><table><tr><th>Tipo</th><th>Emisor (clic para ver el análisis)</th><th class="c">Unidad</th><th class="n">Activos</th>
<th class="n">Patrimonio</th><th class="n">ROE</th><th class="n">Pasivos / patrimonio</th><th class="c">Estado</th></tr>{cuerpo}</table>
{pie(hoy)}</div>
<h2 id="noticias">Noticias de los últimos 7 días</h2>
<div id="bloque-noticias"></div>
</main></body></html>"""


def bloque_noticias(noticias, nombre, carpeta):
    items = noticias.get(carpeta) if noticias else None
    if not isinstance(items, list) or not items:
        return "<p class='note'>Sin noticias de los últimos 7 días.</p>"
    lis = "".join(f"<li><a href='{html.escape(i['enlace'])}' target='_blank' rel='noopener'>{html.escape(i['titulo'])}</a> "
                  f"<span class='fte'>{html.escape(i.get('fuente', ''))}</span></li>" for i in items[:8])
    return f"<div class='box nw'><ul>{lis}</ul></div>"


def svg_barras(titulo, etiquetas, valores, unidad, color="#1D113E"):
    pares = [(e, v) for e, v in zip(etiquetas, valores) if v is not None]
    if len(pares) < 2:
        return f"<div class='box'><b>{html.escape(titulo)}</b><p class='note'>Se necesita más de un año de EEFF para graficar.</p></div>"
    w, h, pad = 560, 220, 36
    mx = max(abs(v) for _, v in pares) or 1
    bw = (w - 2 * pad) / len(pares) * 0.6
    barras = ""
    for k, (e, v) in enumerate(pares):
        x = pad + k * (w - 2 * pad) / len(pares) + ((w - 2 * pad) / len(pares) - bw) / 2
        alto = abs(v) / mx * (h - 2 * pad)
        y = h - pad - alto
        barras += (f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{alto:.1f}' fill='{color}' rx='3'/>"
                   f"<text x='{x + bw / 2:.1f}' y='{y - 6:.1f}' text-anchor='middle' font-size='10' fill='#2B2540'>{fmt(v, 1 if abs(v) < 100 else 0)}</text>"
                   f"<text x='{x + bw / 2:.1f}' y='{h - pad + 14}' text-anchor='middle' font-size='10' fill='#69696A'>{e}</text>")
    return (f"<div class='box'><b>{html.escape(titulo)}</b> <span class='fte'>({html.escape(unidad)})</span>"
            f"<svg viewBox='0 0 {w} {h}' width='100%' role='img'>{barras}</svg></div>")


def svg_lineas(titulo, etiquetas, valores, sufijo):
    pares = [(e, v) for e, v in zip(etiquetas, valores) if v is not None]
    if len(pares) < 2:
        return f"<div class='box'><b>{html.escape(titulo)}</b><p class='note'>Se necesita más de un año de EEFF para graficar.</p></div>"
    w, h, pad = 560, 220, 36
    mn, mx = min(v for _, v in pares), max(v for _, v in pares)
    rango = (mx - mn) or 1
    puntos, marcas = [], ""
    n = len(pares)
    for k, (e, v) in enumerate(pares):
        x = pad + k * (w - 2 * pad) / (n - 1)
        y = h - pad - (v - mn) / rango * (h - 2 * pad)
        puntos.append(f"{x:.1f},{y:.1f}")
        marcas += (f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3.5' fill='#6AEB9A' stroke='#1D113E'/>"
                   f"<text x='{x:.1f}' y='{y - 9:.1f}' text-anchor='middle' font-size='10' fill='#2B2540'>{fmt(v, 1 if abs(v) < 100 else 0)}{sufijo}</text>"
                   f"<text x='{x:.1f}' y='{h - pad + 14}' text-anchor='middle' font-size='10' fill='#69696A'>{e}</text>")
    return (f"<div class='box'><b>{html.escape(titulo)}</b>"
            f"<svg viewBox='0 0 {w} {h}' width='100%' role='img'><polyline points='{' '.join(puntos)}' fill='none' stroke='#1D113E' stroke-width='2'/>{marcas}</svg></div>")


def pagina_emisor(r, noticias, hoy):
    estado = BADGE[r["estado"]]
    ind = r["indicadores"]
    kpis = [("Activos", fmt(r["activos"]), r["unidad"]), ("Patrimonio", fmt(r["patrimonio"]), r["unidad"]),
            ("Pasivos", fmt(r["pasivos"]), r["unidad"]), ("Utilidad", fmt(r["utilidad"]), r["unidad"])]
    kh = "".join(f"<div class='kpi'><div class='l'>{l}</div><div class='v'>{v}</div><div class='s'>{html.escape(s)}</div></div>" for l, v, s in kpis)
    for n, v, u, _ in ind[:3]:
        kh += f"<div class='kpi'><div class='l'>{n}</div><div class='v'>{fmt_ind(v, u)}</div><div class='s'>según el EEFF de este emisor</div></div>"
    cifras = ""
    for lab, campo in [("Activos", "activos"), ("Pasivos", "pasivos"), ("Patrimonio", "patrimonio"),
                       ("Utilidad", "utilidad"), ("Ingresos", "ingresos")]:
        v = r[campo]
        marca = " *" if campo in r["_derivado"] and v is not None else ""
        origen = "derivado" if marca else ("leído del EEFF" if v is not None else "no confirmado en el archivo")
        cifras += f"<tr><td>{lab}</td><td class='n'>{fmt(v)}{marca}</td><td>{origen}</td></tr>"
    filas_ind = "".join(f"<tr><td>{n}</td><td class='n'>{fmt_ind(v, u)}</td><td>{html.escape(f)}</td></tr>" for n, v, u, f in ind) \
        or "<tr><td colspan='3'>Sin indicadores: faltan cifras en el archivo.</td></tr>"
    if r["estado"] == "verificado":
        lectura = "Balance cuadrado con filas del EEFF. Los indicadores se pueden usar."
    elif r["estado"] == "revisar":
        lectura = "La identidad activos = pasivos + patrimonio no cuadra. Revisar el archivo antes de usar los indicadores."
    elif r["estado"] == "parcial":
        lectura = "Faltan cifras en el archivo. Solo se muestran los indicadores que se pueden calcular."
    else:
        lectura = "No hay cifras confirmadas en el archivo."
    link_bci = "<p class='note'><a href='../bci.html'>Ver dashboard BCI completo (historia 2016 a sep-26)</a></p>" if r["carpeta"].startswith("Banco de Crédito") else ""
    hist = r.get("historia") or []
    anios = [str(h["anio"]) for h in hist]
    if not hist:
        hist = [{"anio": 2025, **{c: r[c] for c in CAMPOS}, "indicadores": r["indicadores"], "estado": r["estado"]}]
        anios = ["2025"]

    def ind_de(h, nombre):
        return next((v for n, v, u, _ in h["indicadores"] if n == nombre), None)

    graficas = (
        svg_barras("Activos", anios, [h["activos"] for h in hist], r["unidad"])
        + svg_barras("Utilidad", anios, [h["utilidad"] for h in hist], r["unidad"], "#69696A")
        + svg_lineas("ROE (%)", anios, [ind_de(h, "ROE") for h in hist], "%")
        + svg_lineas("Pasivos / patrimonio (x)", anios, [ind_de(h, "Pasivos / patrimonio") for h in hist], "x")
    )
    tabla_hist = ""
    for h in hist:
        roe = ind_de(h, "ROE")
        roa = ind_de(h, "ROA")
        apal = ind_de(h, "Pasivos / patrimonio")
        tabla_hist += (f"<tr><td>{h['anio']}</td><td class='n'>{fmt(h['activos'])}</td><td class='n'>{fmt(h['pasivos'])}</td>"
                       f"<td class='n'>{fmt(h['patrimonio'])}</td><td class='n'>{fmt(h['utilidad'])}</td><td class='n'>{fmt(h['ingresos'])}</td>"
                       f"<td class='n'>{fmt(roe, 1) + ' %' if roe is not None else '—'}</td><td class='n'>{fmt(roa, 1) + ' %' if roa is not None else '—'}</td>"
                       f"<td class='n'>{fmt(apal, 2) + ' x' if apal is not None else '—'}</td></tr>")
    nota_hist = (f"Historia disponible: {len(hist)} año(s) ({', '.join(anios)}). "
                 + ("Para ver la evolución, sube los EEFF anuales de los años anteriores a la carpeta del emisor en Drive."
                    if len(hist) < 3 else "La historia se actualiza sola cada vez que subes un EEFF nuevo."))
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(r['nombre'])} · Monitor Blum SAF</title><style>{CSS}</style></head><body>
<header><div class="k">{html.escape(r['tipo'])} · {html.escape(r['unidad'])}</div><h1>{html.escape(r['nombre'])}</h1>
<div class="m">Fuente: {html.escape(r['archivo'] or 'sin archivo')} · {estado} · actualizado {hoy}</div>
<div class="nav" style="margin-top:12px"><a href="../index.html">← Todos los emisores</a></div></header>
<main>
<div class="kpis">{kh}</div>
<p class="note" style="margin:0 0 14px">{lectura}</p>
{link_bci}
<h2>Evolución</h2>
<p class="note" style="margin:0 0 10px">{nota_hist}</p>
<div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr))">{graficas}</div>
<h2>Historia por año</h2>
<div class="box"><table><tr><th>Año</th><th class="n">Activos</th><th class="n">Pasivos</th><th class="n">Patrimonio</th><th class="n">Utilidad</th><th class="n">Ingresos</th><th class="n">ROE</th><th class="n">ROA</th><th class="n">Pasivos / patrimonio</th></tr>{tabla_hist}</table></div>
<h2>Cifras del EEFF {html.escape(anios[-1])}</h2>
<div class="box"><table><tr><th>Concepto</th><th class="n">Valor ({html.escape(r['unidad'])})</th><th>Origen</th></tr>{cifras}</table></div>
<h2>Indicadores</h2>
<div class="box"><table><tr><th>Indicador</th><th class="n">Valor</th><th>Fórmula</th></tr>{filas_ind}</table>
<p class="note">Utilidad e ingresos se leen de la misma tabla del EEFF que los activos. Para bancos y aseguradoras el margen neto no es comparable con corporativos.</p></div>
<h2>Noticias de los últimos 7 días</h2>
{bloque_noticias(noticias, r['nombre'], r['carpeta'])}
</main></body></html>"""


if __name__ == "__main__":
    datos = cargar()
    pendientes_log(datos)
    noticias = cargar_noticias()
    hoy = datetime.now().strftime("%d-%m-%Y")
    (SALIDA / "emisores").mkdir(parents=True, exist_ok=True)
    (SALIDA / "index.html").write_text(pagina_indice(datos, hoy), encoding="utf-8")
    for r in datos:
        (SALIDA / "emisores" / f"{r['slug']}.html").write_text(pagina_emisor(r, noticias, hoy), encoding="utf-8")
    (SALIDA / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(datos)} emisores -> {SALIDA} (index + {len(datos)} paginas)")
