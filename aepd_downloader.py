# Script Python para descargar automáticamente Resoluciones PDF de la AEPD.
#
# juancarlos@21719.cl
# Agosto de 2025.
#
# Código Python disponible en: https://github.com/JCLLV/descarga_automatica_res_AEPD


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descarga automática de resoluciones (PDF) de la AEPD con paginación.
Autor: (tu nombre)
Uso:
  pip install requests beautifulsoup4 tqdm
  python aepd_downloader.py --out ./aepd_pdfs --delay 1.5 --max-pages 0 --resume
"""

import argparse
import os
import re
import sys
import time
import json
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm


BASE_LIST_URL = "https://www.aepd.es/informes-y-resoluciones/resoluciones"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AEPD-PDF-Downloader/1.0; +https://example.org/bot)"
}

# Patrones útiles
PDF_EXT_RE = re.compile(r"\.pdf($|\?)", re.IGNORECASE)
ID_RE = re.compile(r"([A-Z]{1,4}-\d{3,6}-\d{4})")  # p.ej. PS-00421-2024
SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._\-]+")


def new_session(timeout: int = 25) -> requests.Session:
    """Crea sesión con reintentos y timeouts."""
    session = requests.Session()
    session.headers.update(HEADERS)
    retries = Retry(
        total=5,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Hack sencillo para timeouts por default
    session.request = _timeouted_request(session.request, timeout=timeout)
    return session


def _timeouted_request(request_func, timeout=25):
    def wrapper(method, url, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = timeout
        return request_func(method, url, **kwargs)
    return wrapper


def sanitize_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    name = SAFE_CHARS_RE.sub("_", name)
    return name[:240]  # evitar nombres excesivamente largos


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def is_pdf_response(resp: requests.Response) -> bool:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    return "application/pdf" in ctype or ctype.endswith("/pdf")


def extract_pdf_links_from_page(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """
    Devuelve lista [(url_pdf_o_detalle, texto_link)].
    Incluye candidatos que aparentan ser el enlace a PDF o a la ficha.
    """
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        txt = (a.get_text(strip=True) or "")
        # Preferimos anchors de "Ver documento", IDs tipo PS-xxxxx-YYYY, o que apunten a .pdf
        if PDF_EXT_RE.search(href) or "Ver documento" in txt or ID_RE.search(txt):
            links.append((urljoin(base_url, href), txt))
    # De-duplicar preservando orden
    seen = set()
    uniq = []
    for u, t in links:
        if u not in seen:
            uniq.append((u, t))
            seen.add(u)
    return uniq


def find_next_page_url(soup: BeautifulSoup, current_url: str) -> str | None:
    """
    Intenta localizar la URL de 'siguiente' en la paginación.
    Busca varios selectores típicos (rel=next, aria-label, texto »/>>/Siguiente).
    """
    # 1) rel="next"
    a = soup.select_one('a[rel="next"], a[rel*=next]')
    if a and a.get("href"):
        return urljoin(current_url, a["href"])

    # 2) aria-label contenga 'Siguiente'
    for sel in ['a[aria-label*="Siguiente" i]', 'a[title*="Siguiente" i]']:
        a = soup.select_one(sel)
        if a and a.get("href"):
            return urljoin(current_url, a["href"])

    # 3) por texto visible
    candidates = [x for x in soup.find_all("a", href=True) if x.get_text(strip=True) in {"Siguiente", "»", ">>"}]
    if candidates:
        return urljoin(current_url, candidates[0]["href"])

    # 4) fallback: si hay paginador con números, tomar el siguiente del activo
    pagers = soup.select("ul.pagination li, nav ul li, .pager li, .pagination li")
    active_idx = None
    items = []
    for li in pagers:
        a = li.find("a", href=True)
        label = (a.get_text(strip=True) if a else li.get_text(strip=True))
        items.append((li, a, label))
        if "active" in (li.get("class") or []) or label == "1":  # heurística
            active_idx = len(items) - 1
    if active_idx is not None and active_idx + 1 < len(items):
        _, a, _ = items[active_idx + 1]
        if a and a.get("href"):
            return urljoin(current_url, a["href"])

    return None


def pick_file_name(url_or_text: str, content_url: str) -> str:
    """
    Genera nombre de archivo:
    - Prioriza un ID tipo PS-xxxxx-YYYY si aparece en el texto o en la URL.
    - Si no, usa el nombre del recurso en la URL.
    - Siempre termina en .pdf
    """
    # 1) buscar ID en texto o URL
    m = ID_RE.search(url_or_text) or ID_RE.search(content_url)
    if m:
        base = m.group(1)
    else:
        # 2) tomar nombre de la ruta
        path = unquote(urlparse(content_url).path)
        base = os.path.basename(path) or "documento"
        base = re.sub(r"\.pdf$", "", base, flags=re.IGNORECASE)
    base = sanitize_filename(base)
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def resolve_pdf_url(session: requests.Session, url: str) -> str | None:
    """
    Dado un candidato (que puede ser PDF directo o una ficha),
    intenta devolver una URL que responda con Content-Type PDF.
    """
    try:
        # 1) HEAD rápido
        r = session.head(url, allow_redirects=True)
        if is_pdf_response(r) or PDF_EXT_RE.search(r.url):
            return r.url

        # 2) Si no es PDF, GET de la página y buscar enlaces .pdf
        r = session.get(url, allow_redirects=True)
        if is_pdf_response(r):
            return r.url
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if PDF_EXT_RE.search(href):
                # Comprobar que realmente es PDF
                h = session.head(href, allow_redirects=True)
                if is_pdf_response(h) or PDF_EXT_RE.search(h.url):
                    return h.url
    except requests.RequestException:
        return None
    return None


def download_pdf(session: requests.Session, pdf_url: str, out_dir: str, file_name_hint: str,
                 resume: bool = True) -> str | None:
    """
    Descarga PDF; devuelve ruta local si tuvo éxito.
    Usa el 'hint' para construir un nombre significativo.
    """
    fname = pick_file_name(file_name_hint, pdf_url)
    out_path = os.path.join(out_dir, fname)

    if resume and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path

    try:
        with session.get(pdf_url, stream=True) as r:
            if not is_pdf_response(r):
                # aún así guardar si termina en .pdf (algunos servers no envían content-type correcto)
                if not PDF_EXT_RE.search(r.url):
                    return None
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", "0")) or None
            tmp_path = out_path + ".part"
            with open(tmp_path, "wb") as f, tqdm(
                total=total, unit="B", unit_scale=True, desc=fname, leave=False
            ) as pbar:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
            os.replace(tmp_path, out_path)
        return out_path
    except requests.RequestException:
        # limpiar .part
        try:
            if os.path.exists(out_path + ".part"):
                os.remove(out_path + ".part")
        except OSError:
            pass
        return None


def crawl_all_pdfs(out_dir: str, delay: float, max_pages: int, resume: bool, timeout: int):
    ensure_dir(out_dir)
    session = new_session(timeout=timeout)

    visited_pages = 0
    next_url = BASE_LIST_URL
    seen_pdf_urls = set()

    # Estado para reanudación simple (última página vista)
    state_file = os.path.join(out_dir, "_state.json")
    if resume and os.path.exists(state_file):
        try:
            state = json.load(open(state_file, "r", encoding="utf-8"))
            next_url = state.get("next_url", next_url)
            visited_pages = state.get("visited_pages", 0)
        except Exception:
            pass

    while next_url:
        visited_pages += 1
        print(f"\n[+] Página {visited_pages}: {next_url}")

        try:
            resp = session.get(next_url)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    Error al cargar la página: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = extract_pdf_links_from_page(soup, next_url)
        print(f"    Candidatos en la página: {len(candidates)}")

        for url, txt in candidates:
            # Resolver a URL de PDF real (si es ficha)
            pdf_url = url
            if not PDF_EXT_RE.search(url):
                pdf_url = resolve_pdf_url(session, url)
            else:
                # Confirmar que es PDF válido (con HEAD)
                try:
                    h = session.head(url, allow_redirects=True)
                    if not (is_pdf_response(h) or PDF_EXT_RE.search(h.url)):
                        pdf_url = resolve_pdf_url(session, url)
                except requests.RequestException:
                    pdf_url = resolve_pdf_url(session, url)

            if not pdf_url:
                # No se pudo resolver
                continue

            if pdf_url in seen_pdf_urls:
                continue
            seen_pdf_urls.add(pdf_url)

            saved = download_pdf(session, pdf_url, out_dir, txt or pdf_url, resume=resume)
            if saved:
                print(f"    ✓ Guardado: {os.path.basename(saved)}")
            else:
                print(f"    ✗ Falló: {pdf_url}")

            time.sleep(delay)

        # Siguiente página
        next_candidate = find_next_page_url(soup, next_url)
        if not next_candidate:
            print("[-] No se encontró más paginación. Fin.")
            break
        next_url = next_candidate

        # Guardar estado
        try:
            json.dump({"next_url": next_url, "visited_pages": visited_pages},
                      open(state_file, "w", encoding="utf-8"))
        except Exception:
            pass

        if max_pages and visited_pages >= max_pages:
            print(f"[-] Se alcanzó el límite de páginas: {max_pages}.")
            break

        # Cortesía adicional entre páginas
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="Descargador de resoluciones (PDF) de la AEPD con paginación.")
    parser.add_argument("--out", default="./aepd_pdfs", help="Carpeta de salida (por defecto ./aepd_pdfs)")
    parser.add_argument("--delay", type=float, default=1.5, help="Pausa (segundos) entre descargas (default 1.5)")
    parser.add_argument("--max-pages", type=int, default=0, help="Máximo de páginas a recorrer (0 = todas)")
    parser.add_argument("--resume", action="store_true", help="No re-descargar existentes y reanudar si hay estado")
    parser.add_argument("--timeout", type=int, default=25, help="Timeout por solicitud en segundos (default 25)")
    args = parser.parse_args()

    print("[!] Aviso: respeta robots.txt y limita el ritmo de peticiones.")
    crawl_all_pdfs(out_dir=args.out, delay=args.delay, max_pages=args.max_pages,
                   resume=args.resume, timeout=args.timeout)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        sys.exit(1)
