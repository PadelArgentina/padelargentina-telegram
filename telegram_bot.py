import os
import re
import time
import json
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ══════════════════════════════════════════════
#  CONFIGURACIÓN
# ══════════════════════════════════════════════
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ARGENTINA_TZ     = pytz.timezone("America/Argentina/Buenos_Aires")

INTERVALO_MIN    = 5
ARCHIVO_PUB      = "tg_pub.json"
ARCHIVO_ESTADO   = "tg_estado.json"
LINK_WEB         = "🌐 www.padelargentina.com.ar"

DIAS_EN  = {0:"MONDAY",1:"TUESDAY",2:"WEDNESDAY",3:"THURSDAY",4:"FRIDAY",5:"SATURDAY",6:"SUNDAY"}
MESES_EN = {1:"JANUARY",2:"FEBRUARY",3:"MARCH",4:"APRIL",5:"MAY",6:"JUNE",7:"JULY",8:"AUGUST",9:"SEPTEMBER",10:"OCTOBER",11:"NOVEMBER",12:"DECEMBER"}

BANDERAS = {
    "spain":"🇪🇸","valencia":"🇪🇸","lanzarote":"🇪🇸","badajoz":"🇪🇸","malaga":"🇪🇸","valladolid":"🇪🇸",
    "china":"🇨🇳","shanghai":"🇨🇳","italy":"🇮🇹","palermo":"🇮🇹","slovenia":"🇸🇮","ljubljana":"🇸🇮",
    "france":"🇫🇷","bordeaux":"🇫🇷","portugal":"🇵🇹","paredes":"🇵🇹","germany":"🇩🇪","poland":"🇵🇱",
}

# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════

def hora_arg():
    return datetime.now(ARGENTINA_TZ)

def cargar_json(f):
    if os.path.exists(f):
        with open(f) as x:
            return json.load(x)
    return {}

def guardar_json(f, d):
    with open(f, "w") as x:
        json.dump(d, x, ensure_ascii=False, indent=2)

def cargar_pub():
    return set(cargar_json(ARCHIVO_PUB).get("ids", []))

def guardar_pub(pid):
    d = cargar_json(ARCHIVO_PUB)
    ids = set(d.get("ids", []))
    ids.add(pid)
    guardar_json(ARCHIVO_PUB, {"ids": list(ids)})

def ya_hoy(t):
    return cargar_json(ARCHIVO_ESTADO).get(t) == hora_arg().strftime("%Y-%m-%d")

def marcar_hoy(t):
    e = cargar_json(ARCHIVO_ESTADO)
    e[t] = hora_arg().strftime("%Y-%m-%d")
    guardar_json(ARCHIVO_ESTADO, e)

def bandera_de(texto):
    t = texto.lower()
    for k, v in BANDERAS.items():
        if k in t:
            return v
    return "🌍"

# ══════════════════════════════════════════════
#  LECTOR WEB EN CASCADA
# ══════════════════════════════════════════════

def leer_url(url, espera_pdf=False):
    intentos = [
        ("directo", url),
        ("codetabs", f"https://api.codetabs.com/v1/proxy/?quest={url}"),
        ("allorigins", f"https://api.allorigins.win/raw?url={url}"),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for nombre, u in intentos:
        try:
            r = requests.get(u, headers=headers, timeout=25)
            if r.status_code == 200 and len(r.content) > 100:
                if espera_pdf and b"%PDF" not in r.content[:1024]:
                    continue
                return r.content if espera_pdf else r.text
        except Exception:
            pass
    return None

# ══════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════

def tg_enviar(texto):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": texto,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15)
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} TG: {texto[:45]}...")
        if not ok:
            print(f"   {r.text[:120]}")
        return ok
    except Exception as e:
        print(f"❌ TG error: {e}")
        return False

def tg_enviar_pdf(pdf_bytes, nombre, caption):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
            files={"document": (nombre, pdf_bytes, "application/pdf")},
            timeout=40)
        return r.status_code == 200
    except Exception:
        return False

# ══════════════════════════════════════════════
#  DETECTAR TORNEOS ACTIVOS
# ══════════════════════════════════════════════

def detectar_torneos():
    html = leer_url("https://www.padelfip.com/es/")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    torneos = []
    vistos = set()
    for a in soup.find_all("a", href=True, title=True):
        href = a["href"]
        titulo = a.get("title", "").strip()
        if "/events/" in href and titulo and titulo not in ("En directo", "Ir al evento"):
            if href not in vistos:
                vistos.add(href)
                if not href.startswith("http"):
                    href = "https://www.padelfip.com" + href
                torneos.append({"nombre": titulo, "url": href})
    print(f"🔎 {len(torneos)} torneos activos detectados")
    return torneos

# ══════════════════════════════════════════════
#  EXTRAER RESULTADOS FINALES DE ARGENTINOS
# ══════════════════════════════════════════════

def extraer_resultados(torneo):
    """
    Recorre los jugadores del cuadro en orden. Cada jugador trae:
    bandera, nombre, y (si su pareja ganó) un ✓ con los games.
    Agrupa de a 4 jugadores = 1 partido.
    Devuelve partidos TERMINADOS (con ✓) que tienen al menos un argentino.
    """
    html = leer_url(torneo["url"])
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    # Recolectar jugadores en orden de aparición
    jugadores = []
    for img in soup.find_all("img", {"title": "flag"}):
        src = img.get("src", "")
        es_arg = "argentina" in src.lower()

        # Nombre: primer texto significativo después de la imagen
        nombre = ""
        nodo = img
        for _ in range(5):
            nodo = nodo.find_next(string=True)
            if not nodo:
                break
            t = nodo.strip()
            if len(t) > 4 and "flag" not in t.lower() and not t.startswith("("):
                nombre = t
                break

        # ¿Ganó? buscar ✓ en el entorno cercano del jugador
        entorno = ""
        nodo2 = img
        for _ in range(8):
            nodo2 = nodo2.find_next(string=True)
            if not nodo2:
                break
            entorno += " " + nodo2.strip()
        gano = "✓" in entorno

        # Games: números sueltos en el entorno (después del nombre)
        games = re.findall(r"\b([0-7])\b", entorno)

        if nombre:
            jugadores.append({
                "nombre": nombre, "es_arg": es_arg,
                "gano": gano, "games": games[:3],
            })

    # Agrupar de a 4 (2 parejas)
    partidos = []
    for i in range(0, len(jugadores) - 3, 4):
        g = jugadores[i:i+4]
        if not all(j["nombre"] for j in g):
            continue
        hay_arg = any(j["es_arg"] for j in g)
        # partido terminado si alguno de los 4 tiene ✓
        terminado = any(j["gano"] for j in g)
        if hay_arg and terminado:
            # pareja ganadora: la que tiene ✓
            p1_gano = g[0]["gano"] or g[1]["gano"]
            partidos.append({
                "p1": (g[0], g[1]), "p2": (g[2], g[3]),
                "p1_gano": p1_gano,
            })

    return partidos

# ══════════════════════════════════════════════
#  ORDEN DEL DÍA (PDF)
# ══════════════════════════════════════════════

def url_pdf(fecha):
    dia = DIAS_EN[fecha.weekday()]
    mes = MESES_EN[fecha.month]
    return f"https://www.padelfip.com/wp-content/uploads/2025/12/ORDER-OF-PLAY-{dia}-{fecha.day}-{mes}-{fecha.year}-2.pdf"

def tarea_orden_dia():
    tid = "orden_dia_valencia"
    if ya_hoy(tid):
        return
    manana = (hora_arg() + timedelta(days=1)).date()
    pdf_bytes = leer_url(url_pdf(manana), espera_pdf=True)
    if not pdf_bytes:
        return
    dia_en = DIAS_EN[manana.weekday()].capitalize()
    nombre = f"orden-de-juego-{manana.day}-{MESES_EN[manana.month].lower()}.pdf"
    caption = (
        f"🗓️ <b>ORDEN DE JUEGO — {dia_en} {manana.strftime('%d/%m/%Y')}</b>\n"
        f"🏟️ <b>PREMIER PADEL P1 VALENCIA</b> 🇪🇸\n\n"
        f"📋 Todos los partidos, horarios y pistas.\n\n{LINK_WEB}"
    )
    if tg_enviar_pdf(pdf_bytes, nombre, caption):
        marcar_hoy(tid)
        print("✅ PDF orden del día enviado")

# ══════════════════════════════════════════════
#  MONITOREO
# ══════════════════════════════════════════════

def monitorear():
    pub = cargar_pub()
    torneos = detectar_torneos()

    for torneo in torneos:
        bandera = bandera_de(torneo["nombre"] + " " + torneo["url"])
        print(f"📂 {torneo['nombre'][:40]}")
        try:
            partidos = extraer_resultados(torneo)
        except Exception as e:
            print(f"   ⚠️ {e}")
            continue

        for p in partidos:
            (j1a, j1b) = p["p1"]
            (j2a, j2b) = p["p2"]
            pid = f"{torneo['url']}_{j1a['nombre']}_{j2a['nombre']}"
            if pid in pub:
                continue

            def fmt(j):
                return f"🇦🇷 {j['nombre']}" if j["es_arg"] else j["nombre"]

            if p["p1_gano"]:
                gan_a, gan_b = j1a, j1b
                per_a, per_b = j2a, j2b
            else:
                gan_a, gan_b = j2a, j2b
                per_a, per_b = j1a, j1b

            gano_arg = gan_a["es_arg"] or gan_b["es_arg"]
            perdio_arg = per_a["es_arg"] or per_b["es_arg"]

            lugar = torneo["nombre"].split()[-1]
            if gano_arg:
                cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA</b>"
            else:
                cab = f"🎾🇦🇷 <b>Derrota argentina en {lugar}</b>"

            msg = (
                f"{cab}\n"
                f"{bandera} <b>{torneo['nombre'].upper()}</b>\n\n"
                f"✅ {fmt(gan_a)} / {fmt(gan_b)}\n"
                f"❌ {fmt(per_a)} / {fmt(per_b)}\n\n"
                f"{LINK_WEB}"
            )
            if tg_enviar(msg):
                guardar_pub(pid)
                time.sleep(3)

# ══════════════════════════════════════════════
#  LOOP
# ══════════════════════════════════════════════

def ciclo():
    print("="*50)
    print("🤖 BOT TELEGRAM PADEL ARGENTINA")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)

    tg_enviar(
        "🤖 <b>Bot Padel Argentina activo ✅</b>\n\n"
        "🎾 Resultados finales de argentinos en todos los FIP\n"
        "📋 Orden del día en PDF\n"
        "🇦🇷 Detección automática por bandera argentina\n\n"
        f"{LINK_WEB}"
    )

    contador = 0
    while True:
        print(f"\n🔍 [{hora_arg().strftime('%H:%M:%S')}] Ciclo {contador+1}")
        try:
            tarea_orden_dia()
            monitorear()
        except Exception as e:
            print(f"⚠️ Error: {e}")
        print(f"✅ Próximo en {INTERVALO_MIN} min")
        contador += 1
        time.sleep(INTERVALO_MIN * 60)

if __name__ == "__main__":
    ciclo()
