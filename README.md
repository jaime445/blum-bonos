# Blum · Monitor de emisores

Página con el cierre de cada emisor de bonos, dashboard BCI y noticias de la última semana.

## Cómo se actualiza

Todos los días a las 08:00 (Lima) el workflow `monitor-diario`:

1. Baja desde Drive los `.md` de `BMM_BC/Emisores/<emisor>/`.
2. Busca noticias de cada emisor (Google News, últimos 7 días).
3. Genera `docs/index.html` y `docs/datos.json`.
4. Publica la carpeta `docs/` en GitHub Pages.

Para actualizar un dato, solo sube el `.md` nuevo a la carpeta del emisor en Drive. Para correrlo ya, ve a Actions → monitor-diario → Run workflow.

## Agregar un emisor o cambiar una regla

Edita `config/emisores.json`:

- `carpeta`: nombre exacto de la subcarpeta en Drive.
- `archivo`: EEFF a leer (por defecto `EEFF 2025.md`).
- `reglas`: por cifra, `patron` (regex sobre la etiqueta de la fila, en minúsculas y sin tildes), `col` (0 = primer número, -1 = último), `ocurrencia` (qué coincidencia usar), `escala` (multiplicador a la unidad del emisor). `"patron": null` deriva la cifra de la identidad activos = pasivos + patrimonio.

Un emisor queda "revisar" si la identidad no cuadra. Ahí conviene abrir el `.md` y ajustar la regla.

## Configuración única

En Settings → Pages, elige Source: "GitHub Actions". Los secrets `GDRIVE_SA_JSON` y `DRIVE_FOLDER_ID` ya deben estar en Settings → Secrets.
