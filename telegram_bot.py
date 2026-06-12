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

DIAS_EN  = {0:"MONDAY",1:"TUESDAY",2:"WEDNESDAY",3:"THURSDAY",
            4:"FRIDAY",5:"SATURDAY",6:"SUNDAY"}
MESES_EN = {1:"JANUARY",2:"FEBRUARY",3:"MARCH",4:"APRIL",5:"MAY",6:"JUNE",
            7:"JULY",8:"AUGUST",9:"SEPTEMBER",10:"OCTOBER",11:"NOVEMBER",12:"DECEMBER"}

BANDERAS_PAIS = {
    "spain":"🇪🇸","valencia":"🇪🇸","lanzarote":"🇪🇸","badajoz":"🇪🇸","malaga":"🇪🇸","valladolid":"🇪🇸",
    "china":"🇨🇳","shanghai":"🇨🇳","italy":"🇮🇹","palermo":"🇮🇹","slovenia":"🇸🇮","ljubljana":"🇸🇮",
    "france":"🇫🇷","bordeaux":"🇫🇷","portugal":"🇵🇹","paredes":"🇵🇹","germany":"🇩🇪","poland":"🇵🇱",
    "chile":"🇨🇱","japan":"🇯🇵","osaka":"🇯🇵","argentina":"🇦🇷",
}
CIUDADES = {
    "valencia":"Valencia","shanghai":"Shanghai","palermo":"Palermo","lanzarote":"Lanzarote",
    "slovenia":"Eslovenia","eslovenia":"Eslovenia","badajoz":"Badajoz","portugal":"Portugal",
    "valladolid":"Valladolid","bordeaux":"Bordeaux","malaga":"Málaga","paredes":"Portugal",
    "chile":"Chile","osaka":"Osaka","japan":"Japón",
}
RONDAS_ES = {
    "quarterfinals":"CUARTOS DE FINAL","semifinals":"SEMIFINAL","final":"FINAL",
    "round of 16":"OCTAVOS","round of 32":"R32","round of 64":"R64",
    "qualifying":"QUALY","qualification":"QUALY",
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
    if "promises" in t or "promesas" in t: return "FIP PROMISES"
    if "p1" in t:                          return "PREMIER PADEL P1"
    if "p2" in t:                          return "PREMIER PADEL P2"
    if "major" in t:                       return "PREMIER PADEL MAJOR"
    return "FIP"

def ronda_es(ronda_en):
    t = ronda_en.lower()
    for k, v in RONDAS_ES.items():
        if k in t: return v
    return ronda_en.upper()

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

# ══════════════════════════════════════════════
#  DETECTAR TORNEOS ACTIVOS
# ══════════════════════════════════════════════

def detectar_torneos():
    html = leer_url("https://www.padelfip.com/es/")
    if not html:
        print("⚠️ No se pudo leer home FIP")
        return []
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

# ══════════════════════════════════════════════
#  OBTENER ID Y DÍA DEL TORNEO
# ══════════════════════════════════════════════

def obtener_id_torneo(url_torneo):
    """
    Lee la página del torneo y obtiene el id de matchscorerlive
    buscando data-tid o el patrón FIP-YEAR-ID en el HTML/JS.
    """
    html = leer_url(url_torneo)
    if not html: return None, None

    # Buscar data-tid="XXXX" (aparece en el modal de match stats)
    m = re.search(r'data-tid=["\'](\d+)["\']', html)
    if m:
        tid = m.group(1)
        # Buscar year
        my = re.search(r'data-year=["\'](\d{4})["\']', html)
        year = my.group(1) if my else str(hora_arg().year)
        return tid, year

    # Fallback: buscar FIP-YEAR-ID en el HTML
    m2 = re.search(r'FIP-(\d{4})-(\d+)', html)
    if m2:
        return m2.group(2), m2.group(1)

    return None, None

# ══════════════════════════════════════════════
#  LEER RESULTADOS DEL WIDGET MATCHSCORERLIVE
# ══════════════════════════════════════════════

def leer_widget(tid, year, day):
    """Lee el widget de matchscorerlive para un torneo y día."""
    url = f"https://widget.matchscorerlive.com/screen/resultsbyday/FIP-{year}-{tid}/{day}?t=tol"
    return leer_url(url)

def parsear_widget(html):
    """
    Parsea el HTML del widget matchscorerlive.
    Estructura: tabla con header (pista/ronda) + team1 + team2 + summary
    Devuelve lista de partidos con argentinos.
    """
    soup = BeautifulSoup(html, "html.parser")
    partidos = []

    # Cada partido es una <table class="w-100 mb-3">
    for tabla in soup.find_all("table", class_="w-100"):
        rows = tabla.find_all("tr")
        if len(rows) < 3: continue

        # Extraer ronda del header
        ronda = ""
        for tr in rows:
            div_ronda = tr.find("div")
            if div_ronda:
                ronda = div_ronda.get_text(strip=True)
                break

        # Extraer estado del summary
        summary_txt = ""
        for tr in rows:
            if "summary" in tr.get("class", []):
                summary_txt = tr.get_text(" ", strip=True).lower()
                break

        completado = "completed" in summary_txt
        en_vivo    = "live" in summary_txt

        if not completado and not en_vivo:
            continue  # partido no empezado

        # Extraer equipos (team rows)
        team_rows = [tr for tr in rows if tr.find("div", class_="player-names")]
        if len(team_rows) < 2: continue

        def leer_equipo(tr):
            jugadores = []
            dobles = tr.find_all("div", class_="d-flex")
            for div in dobles:
                img = div.find("img", class_="flags")
                if not img: continue
                src = img.get("src", "")
                es_arg = "ARG" in src
                spans = div.find_all("span")
                nombre = " ".join(s.get_text(strip=True) for s in spans
                                  if s.get_text(strip=True) and "separator" not in s.get("class",[])).strip()
                if nombre:
                    jugadores.append({"nombre": nombre, "es_arg": es_arg})
            return jugadores

        def leer_sets(tr):
            sets = []
            for td in tr.find_all("td", class_="set"):
                t = td.get_text(strip=True)
                if t and t != "-": sets.append(t)
            return sets

        eq1 = leer_equipo(team_rows[0])
        eq2 = leer_equipo(team_rows[1])
        sets1 = leer_sets(team_rows[0])
        sets2 = leer_sets(team_rows[1])

        if len(eq1) < 2 or len(eq2) < 2: continue

        hay_arg = any(j["es_arg"] for j in eq1 + eq2)
        if not hay_arg: continue

        # Ganador: team que tiene set-completed sin set-lost
        def es_ganador(tr):
            for td in tr.find_all("td", class_="set"):
                clases = td.get("class", [])
                if "set-completed" in clases and "set-lost" not in clases:
                    return True
            return False

        gan_es_1 = es_ganador(team_rows[0])
        gan = eq1 if gan_es_1 else eq2
        per = eq2 if gan_es_1 else eq1
        s_gan = sets1 if gan_es_1 else sets2
        s_per = sets2 if gan_es_1 else sets1

        marcador_sets = []
        for i in range(min(3, max(len(s_gan), len(s_per)))):
            g = s_gan[i] if i < len(s_gan) else "?"
            p = s_per[i] if i < len(s_per) else "?"
            marcador_sets.append(f"{g}-{p}")
        marcador = " / ".join(marcador_sets)

        partidos.append({
            "gan": gan, "per": per,
            "marcador": marcador,
            "ronda": ronda,
            "completado": completado,
            "en_vivo": en_vivo,
            "id": f"{gan[0]['nombre']}_{per[0]['nombre']}",
        })

    return partidos

# ══════════════════════════════════════════════
#  ORDEN DEL DÍA (PDF)
# ══════════════════════════════════════════════

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

# ══════════════════════════════════════════════
#  MONITOREO
# ══════════════════════════════════════════════

def monitorear():
    pub = cargar_pub()
    torneos = detectar_torneos()
    year = str(hora_arg().year)

    for torneo in torneos:
        print(f"📂 {torneo['nombre'][:40]}")
        tid, t_year = obtener_id_torneo(torneo["url"])
        if not tid:
            print(f"   ⚠️ Sin id matchscorerlive")
            continue
        t_year = t_year or year
        print(f"   🆔 id={tid}")

        bandera = bandera_de(torneo["nombre"] + " " + torneo["url"])
        cat     = categoria_fip(torneo["nombre"])
        ciudad  = ciudad_de(torneo["nombre"])

        # Probar días del 1 al 10 (cubre todos los torneos)
        for day in range(1, 11):
            html = leer_widget(tid, t_year, day)
            if not html or len(html) < 200: continue

            try:
                partidos = parsear_widget(html)
            except Exception as e:
                print(f"   ⚠️ día {day}: {e}"); continue

            if partidos:
                print(f"   día {day}: {len(partidos)} partidos con arg")

            for p in partidos:
                if not p["completado"]: continue  # solo publicar completados
                pid = f"{torneo['url']}_{p['id']}"
                if pid in pub: continue

                def fmt(j):
                    return f"🇦🇷 {j['nombre']}" if j['es_arg'] else j['nombre']

                gan_arg = any(j["es_arg"] for j in p["gan"])
                ronda_txt = ronda_es(p["ronda"]) if p["ronda"] else ""

                if gan_arg:
                    cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA</b>"
                else:
                    cab = f"🎾🇦🇷 <b>Derrota argentina en el {cat} de {ciudad}</b>"

                ronda_linea = f" | {ronda_txt}" if ronda_txt else ""
                marcador_linea = f"\n🎯 {p['marcador']}" if p["marcador"] else ""

                msg = (f"{cab}\n"
                       f"{bandera} <b>{cat} — {ciudad.upper()}</b>{ronda_linea}\n\n"
                       f"✅ {fmt(p['gan'][0])} / {fmt(p['gan'][1])}\n"
                       f"❌ {fmt(p['per'][0])} / {fmt(p['per'][1])}"
                       f"{marcador_linea}\n\n"
                       f"{LINK_WEB}")
                if tg_enviar(msg):
                    guardar_pub(pid); time.sleep(3)

# ══════════════════════════════════════════════
#  LOOP
# ══════════════════════════════════════════════

def ciclo():
    print("="*50)
    print("🤖 BOT TELEGRAM PADEL ARGENTINA — v14")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)
    tg_enviar("🤖 <b>Bot Padel Argentina v14 ✅</b>\n\n"
              "📡 Fuente: matchscorerlive.com\n"
              "🎾 Resultados con marcador y ronda\n"
              "🇦🇷 Todos los FIP + Premier\n\n"
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
