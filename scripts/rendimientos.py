"""Rendimiento total de las acciones de los emisores que cotizan.

Usa yfinance (Yahoo Finance) con precios ajustados por dividendos.
Calcula el retorno de cada uno de los ultimos 5 anos calendario cerrados y el YTD.
Salida: docs/acciones.html y docs/rendimientos.json.
Si un ticker falla, se marca como "sin datos" y el resto sigue.

Uso: python scripts/rendimientos.py [carpeta_salida]
"""
import html
import json
import sys
from datetime import date
from pathlib import Path

import yfinance as yf

BASE = Path(__file__).resolve().parent.parent
SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "docs"
ANIOS_CERRADOS = 5


def cierres(ticker):
    hoy = date.today()
    inicio = f"{hoy.year - ANIOS_CERRADOS - 1}-12-01"
    h = yf.Ticker(ticker).history(start=inicio, auto_adjust=True)
    if h is None or h.empty:
        return None
    return [(d.date(), float(c)) for d, c in zip(h.index, h["Close"]) if c == c]


def ultimo_antes(serie, fecha):
    previos = [c for d, c in serie if d <= fecha]
    return previos[-1] if previos else None


def calcular(ticker):
    serie = cierres(ticker)
    if not serie:
        return None
    hoy = date.today()
    ultimo = serie[-1]
    res = {"ultimo": round(ultimo[1], 4), "fecha_ultimo": ultimo[0].isoformat(), "anios": {}, "ytd": None}
    for y in range(hoy.year - ANIOS_CERRADOS, hoy.year):
        base = ultimo_antes(serie, date(y - 1, 12, 31))
        fin = ultimo_antes(serie, date(y, 12, 31))
        if base and fin:
            res["anios"][str(y)] = round((fin / base - 1) * 100, 2)
    base_ytd = ultimo_antes(serie, date(hoy.year - 1, 12, 31))
    if base_ytd:
        res["ytd"] = round((ultimo[1] / base_ytd - 1) * 100, 2)
    return res


def main():
    cfg = json.loads((BASE / "config" / "emisores.json").read_text(encoding="utf-8"))
    tk = json.loads((BASE / "config" / "tickers.json").read_text(encoding="utf-8"))["tickers"]
    salida = []
    for e in cfg["emisores"]:
        if e["carpeta"] not in tk:
            continue
        t = tk[e["carpeta"]]
        try:
            r = calcular(t["ticker"])
        except Exception as exc:  # una falla no detiene al resto
            print(f"ERROR {t['ticker']}: {exc}")
            r = None
        if r is None:
            print(f"SIN DATOS (no se muestra): {e['nombre']} ({t['ticker']})")
            continue
        salida.append({"nombre": e["nombre"], "slug": e["nombre"], "ticker": t["ticker"], "moneda": t["moneda"],
                       "verificar": t["verificar"], "datos": r})
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "rendimientos.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    (SALIDA / "acciones.html").write_text(pagina(salida), encoding="utf-8")
    print(f"{len(salida)} emisores que cotizan -> {SALIDA}")


def color(v):
    if v is None:
        return "#EEEDF3"
    if v >= 0:
        return "#B4F5CC"
    return "#F3C6C6"


def pagina(datos):
    anios = [str(date.today().year - ANIOS_CERRADOS + i) for i in range(ANIOS_CERRADOS)]
    filas = ""
    for d in datos:
        r = d["datos"]
        celdas = "".join(f"<td class='n' style='background:{color(r['anios'].get(a))}'>"
                         f"{fmt(r['anios'].get(a))}</td>" for a in anios)
        celdas += f"<td class='n' style='background:{color(r['ytd'])}'><b>{fmt(r['ytd'])}</b></td>"
        celdas += f"<td class='n'>{r['ultimo']:,.2f} {html.escape(d['moneda'])}</td>"
        filas += f"<tr><td>{html.escape(d['nombre'])}<br><span style='color:#69696A'>{html.escape(d['ticker'])}</span></td>{celdas}</tr>"
    encabezado = "".join(f"<th class='n'>{a}</th>" for a in anios)
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rendimiento de acciones · Blum SAF</title><style>
body{{margin:0;font-family:Montserrat,Arial,sans-serif;background:#F4F3F7;color:#1D113E;font-size:13px}}
header{{background:#1D113E;color:#fff;padding:24px 34px}}.k{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#6AEB9A;font-weight:600}}
h1{{margin:6px 0 4px;font-size:24px}}main{{padding:20px 34px 40px}}.box{{background:#fff;border-radius:10px;padding:14px 16px;overflow-x:auto;box-shadow:0 1px 2px rgba(29,17,62,.08)}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px 9px;border-bottom:1px solid #EEEDF3;text-align:left}}
th{{font-size:10.5px;text-transform:uppercase;color:#69696A;background:#F7F6FA}}td.n,th.n{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.note{{color:#69696A;font-size:12px;margin:12px 0 0}}a{{color:#6AEB9A}}
</style></head><body>
<header><div class="k">Blum SAF · Monitor de emisores</div><h1>Rendimiento de acciones</h1>
<div class="m"><a href="index.html">← Volver al monitor</a></div></header>
<main><div class="box"><table><tr><th>Emisor</th>{encabezado}<th class="n">YTD</th><th class="n">Último precio</th></tr>{filas}</table>
<p class="note">Retorno total en moneda local (precios ajustados por dividendos y splits). Años = retorno del cierre del año anterior al cierre del año. YTD = desde el último cierre de {date.today().year - 1}. Fuente: Yahoo Finance. Verde = positivo, rojo = negativo.</p></div></main></body></html>"""


def fmt(v):
    if v is None:
        return "—"
    return f"{v:,.1f} %".replace(",", "§").replace(".", ",").replace("§", ".")


if __name__ == "__main__":
    main()
