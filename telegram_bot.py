import os
import re
import time
import json
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ARGENTINA_TZ     = pytz.timezone("America/Argentina/Buenos_Aires")
INTERVALO_MIN    = 5
ARCHIVO_PUB      = "tg_pub.json"
ARCHIVO_ESTADO   = "tg_estado.json"
LINK_WEB         = "🌐 www.padelargentina.com.ar"

DIAS_EN  = {0:"MONDAY",1:"TUESDAY",2:"WEDNESDAY",3:"THURSDAY",4:"FRIDAY",5:"SATURDAY",6:"SUNDAY"}
MESES_EN = {1:"JANUARY",2:"FEBRUARY",3:"MARCH",4:"APRIL",5:"MAY",6:"JUNE",
            7:"JULY",8:"AUGUST",9:"SEPTEMBER",10:"OCTOBER",11:"NOVEMBER",12:"DECEMBER"}

BANDERAS_PAIS = {
    "spain":"🇪🇸","valencia":"🇪🇸","lanzarote":"🇪🇸","badajoz":"🇪🇸","malaga":"🇪🇸","valladolid":"🇪🇸",
    "china":"🇨🇳","shanghai":"🇨🇳","italy":"🇮🇹","palermo":"🇮🇹","slovenia":"🇸🇮","ljubljana":"🇸🇮",
    "france":"🇫🇷","bordeaux":"🇫🇷","portugal":"🇵🇹","paredes":"🇵🇹","germany":"🇩🇪","poland":"🇵🇱",
}
CIUDADES = {
    "valencia":"Valencia","shanghai":"Shanghai","palermo":"Palermo","lanzarote":"Lanzarote",
    "slovenia":"Eslovenia","eslovenia":"Eslovenia","badajoz":"Badajoz","portugal":"Portugal",
    "valladolid":"Valladolid","bordeaux":"Bordeaux","malaga":"Málaga","paredes":"Portugal",
}

def hora_arg():
    return datetime.now(ARGENTINA_TZ)

def cargar_json(f):
    if os.path.exists(f):
        with open(f) as x: return json.load(x)
    return {}

def guardar_json(f, d):
    with open(f, "w") as x: json.dump(d, x, ensure_ascii=False, indent=2)

def cargar_pub():
    return set(cargar_json(ARCHIVO_PUB).get("ids", []))

def guardar_pub(pid):
    d = cargar_json(ARCHIVO_PUB)
    ids = set(d.get("ids", [])); ids.add(pid)
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
        if k in t: return v
    return "🌍"

def ciudad_de(nombre):
    t = nombre.lower()
    for k, v in CIUDADES.items():
        if k in t: return v
    return nombre.split()[-1] if nombre.split() else nombre

def categoria_fip(nombre):
    t = nombre.lower()
    if "platinum" in t or "platino" in t: return "FIP PLATINUM"
    if "gold" in t:                        return "FIP GOLD"
    if "silver" in t or "plata" in t:      return "FIP SILVER"
    if "bronze" in t or "bronce" in t:     return "FIP BRONZE"
    if "p1" in t:                          return "PREMIER PADEL P1"
    if "p2" in t:                          return "PREMIER PADEL P2"
    if "major" in t:                       return "PREMIER PADEL MAJOR"
    return "FIP"

def leer_url(url, espera_pdf=False):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
    for u in [url,
              f"https://api.codetabs.com/v1/proxy/?quest={url}",
              f"https://api.allorigins.win/raw?url={url}"]:
        try:
            r = requests.get(u, headers=headers, timeout=25)
            if r.status_code == 200 and len(r.content) > 100:
                if espera_pdf and b"%PDF" not in r.content[:1024]: continue
                return r.content if espera_pdf else r.text
        except: pass
    return None

def tg_enviar(texto):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":texto,
                  "parse_mode":"HTML","disable_web_page_preview":True},
            timeout=15)
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} TG: {texto[:50]}...")
        if not ok: print(f"   {r.text[:120]}")
        return ok
    except Exception as e:
        print(f"❌ TG: {e}"); return False

def tg_enviar_pdf(pdf_bytes, nombre, caption):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            data={"chat_id":TELEGRAM_CHAT_ID,"caption":caption,"parse_mode":"HTML"},
            files={"document":(nombre,pdf_bytes,"application/pdf")},timeout=40)
        return r.status_code == 200
    except: return False

def detectar_torneos():
    html = leer_url("https://www.padelfip.com/es/")
    print(f"   🔬 home FIP: {len(html) if html else 0} chars")
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    torneos, vistos = [], set()
    for a in soup.find_all("a", href=True, title=True):
        href = a["href"]; titulo = a.get("title","").strip()
        if "/events/" in href and titulo and titulo not in ("En directo","Ir al evento"):
            if href not in vistos:
                vistos.add(href)
                if not href.startswith("http"):
                    href = "https://www.padelfip.com" + href
                torneos.append({"nombre":titulo,"url":href})
    print(f"🔎 {len(torneos)} torneos")
    return torneos

def parsear_partidos(html):
    """
    Parser definitivo. Estrategia: buscar el jugador con ✓ (ganador),
    y armar el partido como [i-1, i] (gan) + [i+1, i+2] (per).
    Esto evita los problemas de agrupamiento con Byes y slots vacíos.
    """
    soup = BeautifulSoup(html, "html.parser")
    jugadores = []

    for img in soup.find_all("img", {"title": "flag"}):
        src = img.get("src", "")
        es_arg = "argentina" in src.lower()

        # Recopilar texto entre esta img y la siguiente img flag
        texto = ""
        nodo = img.next_sibling
        while nodo:
            if hasattr(nodo, 'name') and nodo.name == 'img' and nodo.get('title') == 'flag':
                break
            texto += " " + (nodo if isinstance(nodo, str) else nodo.get_text() if hasattr(nodo, 'get_text') else "")
            nodo = nodo.next_sibling

        texto = re.sub(r'\s+', ' ', texto).strip()
        if not texto: continue

        # Nombre: texto antes del primer seed, ✓, RET o game
        nombre_raw = re.split(r'[✓]|RET|\(\d+\)|\(Q\)|\(WC\)|\(LL\w*\)|\b[0-7]\b', texto)[0]
        nombre = re.sub(r'\s+', ' ', nombre_raw).strip()
        if not nombre or len(nombre) < 3: continue

        gano  = '✓' in texto
        games = re.findall(r'\b([0-7])\b', texto)

        jugadores.append({"nombre": nombre, "es_arg": es_arg, "gano": gano, "games": games})

    # Buscar partidos: el jugador con ✓ es el 2do de la pareja ganadora
    partidos = []
    i = 0
    while i < len(jugadores):
        if jugadores[i]["gano"] and i >= 1 and i + 2 < len(jugadores):
            gan = [jugadores[i-1], jugadores[i]]
            per = [jugadores[i+1], jugadores[i+2]]

            # Solo partidos con al menos un argentino
            hay_arg = any(j["es_arg"] for j in gan + per)
            if hay_arg:
                # Marcador: games del 2do gan vs games del 2do per
                g_gan = jugadores[i]["games"]
                g_per = jugadores[i+2]["games"]
                sets = []
                for s in range(min(3, max(len(g_gan), len(g_per)))):
                    gg = g_gan[s] if s < len(g_gan) else "?"
                    gp = g_per[s] if s < len(g_per) else "?"
                    sets.append(f"{gg}-{gp}")
                marcador = " / ".join(sets) if sets else ""

                partidos.append({
                    "gan": gan, "per": per, "marcador": marcador,
                    "id": f"{gan[0]['nombre']}_{per[0]['nombre']}"
                })
            i += 3  # saltar los 2 perdedores ya procesados
        else:
            i += 1

    return partidos

def url_pdf(fecha):
    return (f"https://www.padelfip.com/wp-content/uploads/2025/12/"
            f"ORDER-OF-PLAY-{DIAS_EN[fecha.weekday()]}-{fecha.day}"
            f"-{MESES_EN[fecha.month]}-{fecha.year}-2.pdf")

def tarea_orden_dia():
    tid = "orden_dia_valencia"
    if ya_hoy(tid): return
    manana = (hora_arg() + timedelta(days=1)).date()
    pdf_bytes = leer_url(url_pdf(manana), espera_pdf=True)
    if not pdf_bytes: return
    dia_en = DIAS_EN[manana.weekday()].capitalize()
    nombre = f"orden-de-juego-{manana.day}-{MESES_EN[manana.month].lower()}.pdf"
    caption = (f"🗓️ <b>ORDEN DE JUEGO — {dia_en} {manana.strftime('%d/%m/%Y')}</b>\n"
               f"🏟️ <b>PREMIER PADEL P1 VALENCIA</b> 🇪🇸\n\n"
               f"📋 Todos los partidos, horarios y pistas.\n\n{LINK_WEB}")
    if tg_enviar_pdf(pdf_bytes, nombre, caption):
        marcar_hoy(tid); print("✅ PDF enviado")

def monitorear():
    pub = cargar_pub()
    torneos = detectar_torneos()

    for torneo in torneos:
        print(f"📂 {torneo['nombre'][:40]}")
        html = leer_url(torneo["url"])
        if not html: continue

        try:
            partidos = parsear_partidos(html)
        except Exception as e:
            print(f"   ⚠️ {e}"); continue

        bandera = bandera_de(torneo["nombre"] + " " + torneo["url"])
        cat     = categoria_fip(torneo["nombre"])
        ciudad  = ciudad_de(torneo["nombre"])
        print(f"   → {len(partidos)} con arg")

        for p in partidos:
            pid = f"{torneo['url']}_{p['id']}"
            if pid in pub: continue

            def fmt(j):
                return f"🇦🇷 {j['nombre']}" if j['es_arg'] else j['nombre']

            gan_arg = any(j["es_arg"] for j in p["gan"])
            if gan_arg:
                cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA</b>"
            else:
                cab = f"🎾🇦🇷 <b>Derrota argentina en el {cat} de {ciudad}</b>"

            marcador_linea = f"\n🎯 {p['marcador']}" if p["marcador"] else ""
            msg = (f"{cab}\n"
                   f"{bandera} <b>{cat} — {ciudad.upper()}</b>\n\n"
                   f"✅ {fmt(p['gan'][0])} / {fmt(p['gan'][1])}\n"
                   f"❌ {fmt(p['per'][0])} / {fmt(p['per'][1])}"
                   f"{marcador_linea}\n\n"
                   f"{LINK_WEB}")
            if tg_enviar(msg):
                guardar_pub(pid); time.sleep(3)

def ciclo():
    print("="*50)
    print("🤖 BOT TELEGRAM PADEL ARGENTINA — v13")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)
    tg_enviar("🤖 <b>Bot Padel Argentina v13 ✅</b>\n\n"
              "🎾 Parser definitivo por posición del ✓\n"
              "🇦🇷 Todos los torneos FIP + Premier\n\n"
              f"{LINK_WEB}")
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
