"""Prueba de conexión: lista las subcarpetas de emisores en la carpeta de Drive.

Requiere las variables de entorno:
    GDRIVE_SA_JSON   contenido JSON de la cuenta de servicio (secret)
    DRIVE_FOLDER_ID  ID de la carpeta "Emisores" (secret)
Solo usa permiso de lectura.
"""
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def main():
    try:
        info = json.loads(os.environ["GDRIVE_SA_JSON"])
        folder_id = os.environ["DRIVE_FOLDER_ID"]
    except KeyError as e:
        sys.exit(f"Falta la variable de entorno {e}. Revisa los secrets del repo.")

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)

    q = (f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    carpetas = []
    token = None
    while True:
        res = svc.files().list(
            q=q, fields="nextPageToken, files(id, name)", pageSize=200,
            supportsAllDrives=True, includeItemsFromAllDrives=True, pageToken=token,
        ).execute()
        carpetas += res.get("files", [])
        token = res.get("nextPageToken")
        if not token:
            break

    carpetas.sort(key=lambda f: f["name"].lower())
    print(f"Subcarpetas de emisores: {len(carpetas)}")
    for f in carpetas:
        print(f"  - {f['name']}")
    if not carpetas:
        sys.exit("La conexión funciona pero no hay subcarpetas: revisa que la cuenta de servicio tenga acceso a la carpeta.")


if __name__ == "__main__":
    main()
