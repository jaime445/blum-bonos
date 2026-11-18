"""Descarga los EEFF en Markdown (.md) de la carpeta Emisores de Drive a ./datos/<emisor>/.

Solo lectura. Usa GDRIVE_SA_JSON y DRIVE_FOLDER_ID (secrets del repo).
Los PDF no se descargan: el análisis usa solo los .md para ahorrar tokens y tiempo.
"""
import io
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DESTINO = os.path.join(os.path.dirname(__file__), "..", "datos")


def servicio():
    info = json.loads(os.environ["GDRIVE_SA_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def hijos(svc, carpeta_id):
    q = f"'{carpeta_id}' in parents and trashed = false"
    out, token = [], None
    while True:
        r = svc.files().list(q=q, fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                             pageSize=1000, supportsAllDrives=True, includeItemsFromAllDrives=True,
                             pageToken=token).execute()
        out += r.get("files", [])
        token = r.get("nextPageToken")
        if not token:
            return out


def descargar(svc, f, ruta):
    req = svc.files().get_media(fileId=f["id"], supportsAllDrives=True)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as fh:
        fh.write(buf.getvalue())


def main():
    svc = servicio()
    raiz = os.environ["DRIVE_FOLDER_ID"]
    total = 0
    for emisor in hijos(svc, raiz):
        if emisor["mimeType"] != "application/vnd.google-apps.folder":
            continue
        for f in hijos(svc, emisor["id"]):
            if f["name"].lower().endswith(".md"):
                ruta = os.path.join(DESTINO, emisor["name"], f["name"])
                descargar(svc, f, ruta)
                total += 1
    print(f"Archivos .md descargados: {total}")
    if total == 0:
        sys.exit("No se descargó ningún .md. Revisa permisos de la cuenta de servicio.")


if __name__ == "__main__":
    main()
