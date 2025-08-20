********************************************************************************************
Instructivo de Script Python para descargar automáticamente Resoluciones PDF de la AEPD.

juancarlos@21719.cl
Agosto de 2025.

Código Python disponible en: https://github.com/JCLLV/descarga_automatica_res_AEPD

********************************************************************************************


Descargador de **resoluciones (PDF) de la AEPD** con paginación, reintentos, validación de enlaces y reanudación opcional.

> **Objetivo:** facilitar la descarga de resoluciones publicadas por la Agencia Española de Protección de Datos desde su portal público, respetando buenas prácticas de *scraping* (delays, validación de tipo de contenido, manejo de errores).

---
Dependencias

pip install requests beautifulsoup4 tqdm


Recomendación: respeta el robots.txt del sitio y usa un --delay ≥ 1–2 s.

Uso
python aepd_downloader.py --out ./aepd_pdfs --delay 1.5 --max-pages 0


--out: carpeta destino (se crea si no existe).

--delay: segundos a esperar entre solicitudes (float).

--max-pages: 0 = sin límite (recorre todas); o pon un número para acotar en pruebas.

--resume: no vuelve a descargar archivos existentes.

--timeout: segundos de timeout por petición (default 25).



Notas importantes

Respetar el sitio: usa --delay (ej. 1.5–3.0 s) y, si vas a descargar “todo”, considera ejecutar por la noche o con pausas mayores.

Reanudación: con --resume no vuelve a bajar PDFs existentes y recuerda la última página en _state.json.

Robustez: si un enlace de la lista apunta a una ficha, el script abre la ficha y busca dentro el enlace .pdf real; si es PDF directo, lo descarga. Valida por Content-Type y por extensión.

Pruebas: primero corre con --max-pages 2 para verificar que está guardando correctamente, y luego elimina ese límite.

Si luego quieres que lo deje programado para correr cada semana o adaptar nombres/carpeta por año (por ejemplo, 2024/PS-xxxx-2024.pdf), te lo ajusto en un minuto.


---

##  Características

- Recorre la **lista paginada** de resoluciones.
- Detecta enlaces que apunten **directamente a PDF** o a **fichas** y, en estas últimas, resuelve el **.pdf real**.
- **Valida Content-Type** y extensión `.pdf` como respaldo.
- **Nombres de archivo seguros**; si hay un identificador tipo `PS-xxxxx-YYYY`, lo usa como nombre.
- **Reanudación**: con `--resume` evita re-descargar y recuerda el avance en `_state.json`.
- **Progreso** con `tqdm` y descargas en `.part` para evitar archivos corruptos.
- **Reintentos y timeouts** configurados (via `requests` + `urllib3 Retry`).

---

##  Requisitos

- Python 3.x
- Paquetes:
  ```bash
  pip install requests beautifulsoup4 tqdm
  ```

> Consejo: respeta el `robots.txt` del sitio y usa un `--delay` ≥ 1–2 s (1.5–3.0 s recomendado en descargas largas).


---

## Uso rápido

python aepd_downloader.py --out ./aepd_pdfs --delay 1.5 --max-pages 0 --resume


- `--out` : carpeta de salida (se crea si no existe).
- `--delay` : segundos de pausa entre descargas (float).
- `--max-pages` : `0` = sin límite; usa un número para acotar pruebas.
- `--resume` : no vuelve a descargar existentes y **retoma** desde la última página vista.
- `--timeout` : segundos de *timeout* por petición (default 25).

### Ejemplos

- **Prueba rápida (2 páginas):**
  ```bash
  python aepd_downloader.py --out ./aepd_pdfs --delay 2.0 --max-pages 2 --resume
  ```

- **Descarga extensa con cortesía:**
  ```bash
  python aepd_downloader.py --out ./aepd_pdfs --delay 2.5 --max-pages 0 --resume --timeout 30
  ```

---

##  Estructura de salida

```
aepd_pdfs/
├─ PS-00421-2024.pdf
├─ R-00012-2023.pdf
├─ ...
└─ _state.json        # estado simple para reanudar (URL de la siguiente página, contador, etc.)
```

> Los nombres se sanitizan y, cuando es posible, incluyen el **ID oficial** detectado en el texto/URL (ej. `PS-xxxxx-YYYY`).

---

##  Buenas prácticas y límites

- **Respeto por el sitio**: usa `--delay` suficiente; si vas a descargar “todo”, considera tiempos de baja carga.
- **Cumplimiento legal**: el uso de este script debe respetar términos del sitio y normativa aplicable. Tú eres responsable del uso que le des.
- **Cambios de HTML**: si el portal cambia su estructura, puede ser necesario ajustar selectores/heurísticas.

---

##  Solución de problemas

- **No encuentra más páginas**: prueba sin `--max-pages` o revisa que la paginación no haya cambiado.
- **Archivos vacíos o corruptos**: elimina el `.part` correspondiente y vuelve a ejecutar con `--resume`.
- **Muchos errores 429/5xx**: incrementa `--delay` y `--timeout`.
- **Fallo al resolver PDF en fichas**: puede que el enlace haya cambiado o requiera autenticación; revisa el HTML de la ficha.

---

##  Personalización rápida

- **Cambiar carpeta por año**: adapta la función que crea el nombre de archivo para guardar en subcarpetas `YYYY/`.
- **Filtros por tipo de expediente**: añade lógica para procesar solo IDs que cumplan cierto patrón.
- **Registro (logging)**: sustituye `print` por `logging` con niveles y *handlers* a archivo.

---

##  Estructura del código (resumen)

- `new_session()` – sesión `requests` con *retries* y *timeouts* por defecto.
- `extract_pdf_links_from_page()` – obtiene candidatos (PDF directos o fichas).
- `resolve_pdf_url()` – si es ficha, localiza el `.pdf` real.
- `download_pdf()` – guarda el PDF con barra de progreso y `.part`.
- `find_next_page_url()` – intenta detectar el enlace **Siguiente** en diferentes patrones.
- `crawl_all_pdfs()` – *crawler* principal: recorre páginas y descarga.
- `main()` – parseo de argumentos CLI.

---

##  Contribuir

¡Se aceptan *issues* y *PRs*! Algunas ideas:
- Parser más robusto para paginación (distintos temas/plantillas).
- Modo “solo listar” sin descargar (inventario CSV/JSON).
- Soporte para opciones de nombre de archivo personalizadas.

---

