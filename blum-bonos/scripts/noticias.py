"""Busca noticias recientes de cada emisor con Google News (RSS, sin API key).

Salida: noticias/noticias_AAAA-MM-DD.json y noticias/ultimas.json
Solo guarda titulares, fuente, fecha y enlace. No resume artículos completos.
"""
import datetime as dt
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DIAS = 7
RAIZ = os.path.join(os.path.dirname(__file__), "..")
SALIDA = os.path.join(RAIZ, "noticias")
EMISORES_DIR = os.path.join(RAIZ, "datos")

# Nombre de búsqueda por carpeta (para no traer homónimos)
BUSQUEDA = {
    "Banco de Crédito e Inversiones": "BCI Banco de Crédito e Inversiones",
    "Banco de Bogotá": "Banco de Bogotá",
    "Banco de Colombia": "Bancolombia",
    "Banco Inbursa Financiero": "Banco Inbursa",
    "Banco Mercantil del Norte": "Banorte Banco Mercantil del Norte",
    "Ares Capital": "Ares Capital Corporation",
    "Barings BDC": "Barings BDC",
    "Blackstone Private Credit Fund": "Blackstone Private Credit Fund BCRED",
    "Blackstone Secured Lend": "Blackstone Secured Lending BXSL",
    "Blue Owl Credit Income": "Blue Owl Credit Income",
    "CELULOSA ARAUCO Y CONSTITUCION S.A": "Empresas CMPC Arauco Celulosa",
    "CODELCO INC": "Codelco",
    "COFIDE": "COFIDE Perú",
    "Enel Chile": "Enel Chile",
    "Enel Generación Chile S.A": "Enel Generación Chile",
    "Falabella S.A": "Falabella",
    "Fondo Mivivienda": "Fondo Mivivienda",
    "HERCULES CAPITAL INC": "Hercules Capital HTGC",
    "HPS Corporate Lending Fund": "HPS Corporate Lending Fund",
    "HSBC Holdings": "HSBC Holdings",
    "ING Bank N.V": "ING Bank",
    "Intercorp Financial Services": "Intercorp Financial Services",
    "Inversiones CMPC SA": "CMPC Empresas CMPC",
    "Main Street Capital Corp": "Main Street Capital MAIN",
    "Morgan Stanley Direct Lending Fund": "Morgan Stanley Direct Lending Fund",
    "Oaktree Specialty Lending Corp": "Oaktree Specialty Lending OCSL",
    "Sempra": "Sempra Energy",
    "SURA Asset Management S.A": "SURA Asset Management",
    "Svenska Handelsbanken AB": "Handelsbanken",
    "UBS AG": "UBS Group",
}


def consulta(nombre):
    termino = f'"{BUSQUEDA.get(nombre, nombre)}" when:{DIAS}d'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": termino, "hl": "es-419", "gl": "CL", "ceid": "CL:es-419"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raiz = ET.fromstring(r.read())
    items = []
    for it in raiz.iter("item"):
        titulo = html.unescape(it.findtext("title", "")).strip()
        fuente = (it.findtext("source") or "").strip()
        if fuente and titulo.endswith(" - " + fuente):
            titulo = titulo[: -(len(fuente) + 3)]
        items.append({
            "titulo": titulo,
            "fuente": fuente,
            "fecha": it.findtext("pubDate", ""),
            "enlace": it.findtext("link", ""),
        })
    return items[:8]


def emisores():
    if not os.path.isdir(EMISORES_DIR):
        return []
    return sorted(d for d in os.listdir(EMISORES_DIR) if os.path.isdir(os.path.join(EMISORES_DIR, d)))


def main():
    os.makedirs(SALIDA, exist_ok=True)
    hoy = dt.date.today().isoformat()
    resultado = {"generado": hoy, "emisores": {}}
    for nombre in emisores():
        try:
            resultado["emisores"][nombre] = consulta(nombre)
        except Exception as e:  # una falla no detiene al resto
            resultado["emisores"][nombre] = {"error": str(e)}
    for nombre_archivo in (f"noticias_{hoy}.json", "ultimas.json"):
        with open(os.path.join(SALIDA, nombre_archivo), "w", encoding="utf-8") as fh:
            json.dump(resultado, fh, ensure_ascii=False, indent=2)
    total = sum(len(v) for v in resultado["emisores"].values() if isinstance(v, list))
    print(f"Titulares guardados: {total} de {len(resultado['emisores'])} emisores")


if __name__ == "__main__":
    main()
