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

BANDERAS_PAIS = {
    "spain":"🇪🇸","valencia":"🇪🇸","lanzarote":"🇪🇸","badajoz":"🇪🇸","malaga":"🇪🇸","valladolid":"🇪🇸",
    "china":"🇨🇳","shanghai":"🇨🇳","italy":"🇮🇹","palermo":"🇮🇹","slovenia":"🇸🇮","ljubljana":"🇸🇮",
    "france":"🇫🇷","bordeaux":"🇫🇷","portugal":"🇵🇹","paredes":"🇵🇹","germany":"🇩🇪","poland":"🇵🇱",
}
CIUDADES = {
    "valencia":"Valencia","shanghai":"Shanghai","palermo":"Palermo","lanzarote":"Lanzarote",
    "slovenia":"Eslovenia","ljubljana":"Eslovenia","badajoz":"Badajoz","portugal":"Portugal",
    "valladolid":"Valladolid","bordeaux":"Bordeaux","malaga":"Málaga","paredes":"Portugal",
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
    for k, v in BANDERAS_PAIS.items():
        if k in t:
            return v
    return "🌍"

def ciudad_de(nombre):
    t = nombre.lower()
    for k, v in CIUDADES.items():
        if k in t:
            return v
    return nombre.split()[-1] if nombre.split() else nombre

def categoria_fip(nombre):
    t = nombre.lower()
    if "platinum" in t: return "FIP PLATINUM"
    if "gold" in t:     return "FIP GOLD"
    if "silver" in t:   return "FIP SILVER"
    if "bronze" in t:   return "FIP BRONZE"
    if "p1" in t:       return "PREMIER PADEL P1"
    if "p2" in t:       return "PREMIER PADEL P2"
    if "major" in t:    return "PREMIER PADEL MAJOR"
    return "FIP"

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
    for _, u in intentos:
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
    print(f"🔎 {len(torneos)} torneos detectados")
    return torneos

# ══════════════════════════════════════════════
#  PARSER DE PARTIDOS — lee el cuadro de FIP
# ══════════════════════════════════════════════

def parsear_partidos(html, torneo):
    """
    Recorre el HTML del torneo. Extrae partidos con argentinos
    que ya tienen resultado (✓).
    Estrategia: procesar img flags en orden, agrupar de a 4.
    """
    soup = BeautifulSoup(html, "html.parser")
    jugadores = []

    for img in soup.find_all("img", {"title": "flag"}):
        src = img.get("src", "")
        es_arg = "argentina" in src.lower()

        # Nombre del jugador: texto que sigue a esta imagen
        nombre = ""
        nodo = img.next_sibling
        while nodo:
            if isinstance(nodo, str):
                t = nodo.strip()
                # Filtrar seeds como "(1)", "(Q)", "(WC)"
                t_limpio = re.sub(r'\(\d+\)|\(Q\)|\(WC\)|\(LL\w*\)', '', t).strip()
                if len(t_limpio) > 4 and '✓' not in t_limpio and not re.match(r'^[\d\s\-/]+$', t_limpio):
                    nombre = t_limpio
                    break
            elif hasattr(nodo, 'name'):
                # Si llegamos a otra img, parar
                if nodo.name == 'img':
                    break
                t = nodo.get_text(strip=True)
                t_limpio = re.sub(r'\(\d+\)|\(Q\)|\(WC\)|\(LL\w*\)', '', t).strip()
                if len(t_limpio) > 4 and '✓' not in t_limpio:
                    nombre = t_limpio
                    break
            nodo = nodo.next_sibling

        if not nombre:
            continue

        # Buscar si esta pareja ganó: el ✓ aparece en el entorno cercano
        # Mirar los próximos 10 nodos después del nombre
        gano = False
        games = []
        nodo2 = img
        for _ in range(15):
            nodo2 = nodo2.next_sibling
            if not nodo2:
                break
            if hasattr(nodo2, 'name') and nodo2.name == 'img':
                break  # llegamos al próximo jugador
            t = nodo2.get_text(strip=True) if hasattr(nodo2, 'get_text') else str(nodo2).strip()
            if '✓' in t:
                gano = True
            if re.match(r'^[0-7]$', t):
                games.append(t)

        jugadores.append({
            "nombre": nombre,
            "es_arg": es_arg,
            "gano": gano,
            "games": games,
        })

    # Agrupar de a 4 = 1 partido
    partidos = []
    for i in range(0, len(jugadores) - 3, 4):
        g = jugadores[i:i+4]
        if not all(j["nombre"] for j in g):
            continue
        hay_arg = any(j["es_arg"] for j in g)
        terminado = any(j["gano"] for j in g)
        if not hay_arg or not terminado:
            continue

        p1_gano = g[0]["gano"] or g[1]["gano"]
        gan = [g[0], g[1]] if p1_gano else [g[2], g[3]]
        per = [g[2], g[3]] if p1_gano else [g[0], g[1]]

        # Marcador: los games del ganador vs los del perdedor por set
        games_gan = gan[0]["games"] + gan[1]["games"]
        games_per = per[0]["games"] + per[1]["games"]
        sets = []
        for s in range(min(3, max(len(games_gan), len(games_per)))):
            gg = games_gan[s] if s < len(games_gan) else "?"
            gp = games_per[s] if s < len(games_per) else "?"
            if gg != "?" or gp != "?":
                sets.append(f"{gg}-{gp}")
        marcador = " / ".join(sets) if sets else ""

        partidos.append({
            "gan": gan,
            "per": per,
            "marcador": marcador,
            "id": f"{g[0]['nombre']}_{g[2]['nombre']}",
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
        print(f"📂 {torneo['nombre'][:40]}")
        html = leer_url(torneo["url"])
        if not html:
            continue

        try:
            partidos = parsear_partidos(html, torneo)
        except Exception as e:
            print(f"   ⚠️ {e}")
            continue

        bandera = bandera_de(torneo["nombre"] + " " + torneo["url"])
        cat = categoria_fip(torneo["nombre"])
        ciudad = ciudad_de(torneo["nombre"])

        print(f"   → {len(partidos)} partidos con argentinos terminados")

        for p in partidos:
            pid = f"{torneo['url']}_{p['id']}"
            if pid in pub:
                continue

            def fmt(j):
                return f"🇦🇷 {j['nombre']}" if j['es_arg'] else j['nombre']

            gan_arg = any(j["es_arg"] for j in p["gan"])
            if gan_arg:
                cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA</b>"
            else:
                cab = f"🎾🇦🇷 <b>Derrota argentina en el {cat} de {ciudad}</b>"

            linea_marcador = f"\n🎯 {p['marcador']}" if p["marcador"] else ""

            msg = (
                f"{cab}\n"
                f"{bandera} <b>{cat} — {ciudad.upper()}</b>\n\n"
                f"✅ {fmt(p['gan'][0])} / {fmt(p['gan'][1])}\n"
                f"❌ {fmt(p['per'][0])} / {fmt(p['per'][1])}"
                f"{linea_marcador}\n\n"
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
    print("🤖 BOT TELEGRAM PADEL ARGENTINA — v11")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)

    tg_enviar(
        "🤖 <b>Bot Padel Argentina v11 ✅</b>\n\n"
        "🎾 Resultados finales con marcador\n"
        "🇦🇷 Detección por bandera argentina\n"
        "📋 Orden del día en PDF\n\n"
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
