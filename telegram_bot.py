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

# ══════════════════════════════════════════════
#  TORNEOS ACTIVOS — actualizar cada lunes
#  Cómo obtener el id: abrir la página del torneo,
#  F12 → Network → pestaña "Orden de juego" → buscar "screen"
#  URL: widget.matchscorerlive.com/screen/.../FIP-2026-XXXX/
#  XXXX es el id
# ══════════════════════════════════════════════
TORNEOS = [
    {"nombre":"PREMIER PADEL P1 VALENCIA", "ciudad":"Valencia",  "bandera":"🇪🇸", "cat":"PREMIER PADEL P1", "id":"2403", "year":"2026", "totalday":9},
    {"nombre":"FIP BRONZE ESLOVENIA",       "ciudad":"Eslovenia", "bandera":"🇸🇮", "cat":"FIP BRONZE",       "id":"2404", "year":"2026", "totalday":6},
    {"nombre":"FIP SILVER PALERMO",         "ciudad":"Palermo",   "bandera":"🇮🇹", "cat":"FIP SILVER",       "id":"2606", "year":"2026", "totalday":5},
    {"nombre":"FIP GOLD SHANGHAI",          "ciudad":"Shanghai",  "bandera":"🇨🇳", "cat":"FIP GOLD",         "id":"2412", "year":"2026", "totalday":5},
    {"nombre":"FIP BRONZE LANZAROTE",       "ciudad":"Lanzarote", "bandera":"🇪🇸", "cat":"FIP BRONZE",       "id":"2411", "year":"2026", "totalday":4},
]

RONDAS_ES = {
    "quarterfinals":"CUARTOS DE FINAL", "semifinals":"SEMIFINAL", "final":"FINAL",
    "round of 16":"OCTAVOS", "round of 32":"R32", "round of 64":"R64",
    "qualifying":"QUALY", "menq1":"QUALIFYING", "womenq1":"QUALIFYING",
    "men":"", "women":"",
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

def ronda_es(r):
    t = r.lower().strip()
    for k, v in RONDAS_ES.items():
        if k in t: return v
    return r.upper()

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

def dia_actual_torneo(torneo):
    """Obtiene el día actual del torneo via endpoint FIP."""
    try:
        url = (f"https://www.padelfip.com/wp-content/themes/padelfiptheme/"
               f"template-parts/event/endpoint/get-result-data.php"
               f"?year={torneo['year']}&id={torneo['id']}"
               f"&day=1&totalday={torneo['totalday']}&widget=resultsbyday")
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            dia = data.get("usedDay", 0)
            if dia > 0:
                return dia
    except: pass
    return None

def parsear_widget(html):
    """
    Parser definitivo basado en el HTML real de matchscorerlive.
    Estructura: table.w-100 > tr (header) + tr (team1) + tr (team2) + tr.summary
    Cada equipo: div.player-names > div.double > div.d-flex (uno por jugador)
    Cada jugador: img.flags + div.ml-2 > span (inicial) + span (apellido)
    """
    soup = BeautifulSoup(html, "html.parser")
    partidos = []

    for tabla in soup.find_all("table", class_="w-100"):
        rows = tabla.find_all("tr", recursive=False)
        if len(rows) < 3: continue

        # Ronda: buscar en el header
        ronda = ""
        header = rows[0]
        for div in header.find_all("div"):
            t = div.get_text(strip=True)
            if t and len(t) > 2:
                ronda = t; break

        # Estado: buscar en summary
        summary_txt = ""
        for tr in rows:
            if "summary" in tr.get("class", []):
                summary_txt = tr.get_text(" ", strip=True).lower(); break
        if "completed" not in summary_txt:
            continue

        # Filas de equipos: las que tienen div.player-names
        team_rows = [tr for tr in rows if tr.find("div", class_="player-names")]
        if len(team_rows) < 2: continue

        def leer_equipo(tr):
            """Lee los jugadores de un equipo desde el tr."""
            jugadores = []
            double = tr.find("div", class_="double")
            if not double: return jugadores
            for div_jug in double.find_all("div", class_="d-flex"):
                img = div_jug.find("img", class_="flags")
                if not img: continue
                es_arg = "ARG" in img.get("src", "")
                # Nombre en div.ml-2
                ml2 = div_jug.find("div", class_="ml-2")
                if not ml2: continue
                spans = [s for s in ml2.find_all("span")
                         if "separator" not in s.get("class", [])
                         and s.get_text(strip=True)]
                nombre = " ".join(s.get_text(strip=True) for s in spans[:2]).strip()
                if nombre:
                    jugadores.append({"nombre": nombre, "es_arg": es_arg})
            return jugadores

        def leer_sets(tr):
            return [td.get_text(strip=True)
                    for td in tr.find_all("td", class_="set")
                    if td.get_text(strip=True) not in ("", "-")]

        def es_ganador(tr):
            for td in tr.find_all("td", class_="set"):
                c = td.get("class", [])
                if "set-completed" in c and "set-lost" not in c:
                    return True
            return False

        eq1 = leer_equipo(team_rows[0])
        eq2 = leer_equipo(team_rows[1])
        if len(eq1) < 2 or len(eq2) < 2: continue

        hay_arg = any(j["es_arg"] for j in eq1 + eq2)
        if not hay_arg: continue

        sets1 = leer_sets(team_rows[0])
        sets2 = leer_sets(team_rows[1])
        gan_es_1 = bool(team_rows[0].find("img", src=lambda s: s and "ballg" in s))

        gan = eq1 if gan_es_1 else eq2
        per = eq2 if gan_es_1 else eq1
        s_g = sets1 if gan_es_1 else sets2
        s_p = sets2 if gan_es_1 else sets1

        sets_txt = []
        for i in range(min(3, max(len(s_g), len(s_p)))):
            g = s_g[i] if i < len(s_g) else "?"
            p = s_p[i] if i < len(s_p) else "?"
            sets_txt.append(f"{g}-{p}")
        marcador = " / ".join(sets_txt)

        partidos.append({
            "gan": gan, "per": per, "marcador": marcador, "ronda": ronda,
            "id": f"{gan[0]['nombre']}_{per[0]['nombre']}",
        })

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

    for torneo in TORNEOS:
        print(f"📂 {torneo['nombre']}")

        # Obtener día actual del torneo
        dia_hoy = dia_actual_torneo(torneo)
        if dia_hoy:
            dias = [dia_hoy]  # solo el día de hoy
            print(f"   📅 día actual del torneo: {dia_hoy}")
        else:
            dias = list(range(1, torneo["totalday"] + 1))

        encontrados = 0
        for day in dias:
            url = (f"https://widget.matchscorerlive.com/screen/resultsbyday"
                   f"/FIP-{torneo['year']}-{torneo['id']}/{day}?t=tol")
            html = leer_url(url)
            if not html or len(html) < 500: continue

            try:
                partidos = parsear_widget(html)
            except Exception as e:
                print(f"   ⚠️ día {day}: {e}"); continue

            encontrados += len(partidos)

            for p in partidos:
                pid = f"{torneo['id']}_{p['id']}"
                if pid in pub: continue

                def fmt(j):
                    return f"🇦🇷 {j['nombre']}" if j['es_arg'] else j['nombre']

                gan_arg = any(j["es_arg"] for j in p["gan"])
                ronda_txt = ronda_es(p["ronda"]) if p["ronda"] else ""

                if gan_arg:
                    cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA</b>"
                else:
                    cab = f"🎾🇦🇷 <b>Derrota argentina en el {torneo['cat']} de {torneo['ciudad']}</b>"

                ronda_linea    = f" | {ronda_txt}" if ronda_txt else ""
                marcador_linea = f"\n🎯 {p['marcador']}" if p["marcador"] else ""

                msg = (f"{cab}\n"
                       f"{torneo['bandera']} <b>{torneo['nombre']}</b>{ronda_linea}\n\n"
                       f"✅ {fmt(p['gan'][0])} / {fmt(p['gan'][1])}\n"
                       f"❌ {fmt(p['per'][0])} / {fmt(p['per'][1])}"
                       f"{marcador_linea}\n\n"
                       f"{LINK_WEB}")
                if tg_enviar(msg):
                    guardar_pub(pid)
                    print(f"   ✅ {p['gan'][0]['nombre']}/{p['gan'][1]['nombre']}")
                    time.sleep(3)

        print(f"   → {encontrados} con arg")

def ciclo():
    print("="*50)
    print("🤖 BOT TELEGRAM PADEL ARGENTINA — v17")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)
    tg_enviar(
        "🤖 <b>Bot Padel Argentina v17 ✅</b>\n\n"
        "📡 matchscorerlive | nombres corregidos\n"
        "🎾 Solo resultados del día actual\n"
        "🇦🇷 Valencia · Eslovenia · Palermo · Shanghai · Lanzarote\n\n"
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
