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

# ══════════════════════════════════════════════
#  TORNEOS ACTIVOS — actualizar cada semana
#  Cómo obtener el id: pedirle a Claude in Chrome
#  que entre a cada página, F12 → Network →
#  pestaña "Orden de juego" → filtrar por "screen"
#  La URL tiene: widget.matchscorerlive.com/screen/.../FIP-2026-XXXX/
# ══════════════════════════════════════════════
TORNEOS = [
    {"nombre":"VALLADOLID P2",         "ciudad":"Valladolid", "bandera":"🇪🇸", "cat":"PREMIER PADEL P2", "id":"3801", "year":"2026"},
    {"nombre":"FIP GOLD ABIDJAN",      "ciudad":"Abidjan",    "bandera":"🇨🇮", "cat":"FIP GOLD",         "id":"3411", "year":"2026"},
    {"nombre":"FIP SILVER GIULIANOVA", "ciudad":"Giulianova", "bandera":"🇮🇹", "cat":"FIP SILVER",       "id":"2604", "year":"2026"},
    {"nombre":"FIP BRONZE ASTORGA",    "ciudad":"Astorga",    "bandera":"🇪🇸", "cat":"FIP BRONZE",       "id":"2602", "year":"2026"},
    {"nombre":"FIP BRONZE SELANGOR",   "ciudad":"Selangor",   "bandera":"🇲🇾", "cat":"FIP BRONZE",       "id":"2609", "year":"2026"},
    {"nombre":"FIP BRONZE IQUIQUE",    "ciudad":"Iquique",    "bandera":"🇨🇱", "cat":"FIP BRONZE",       "id":"801",  "year":"2026"},
]

RONDAS_ES = {
    "semifinals":"SEMIFINAL","semifinal":"SEMIFINAL",
    "quarterfinals":"CUARTOS DE FINAL","quarterfinal":"CUARTOS DE FINAL",
    "final":"FINAL",
    "round of 16":"OCTAVOS","round of 32":"R32","round of 64":"R64",
    "qualifying":"QUALY","qualification":"QUALY",
}

MESES_WIDGET = {
    "JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
    "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12
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

def ronda_es(r):
    t = r.lower().strip()
    for k, v in RONDAS_ES.items():
        if k in t: return v
    return r.upper() if r else ""

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

def dia_actual_widget(torneo):
    """
    Lee el widget día 1 para obtener el selector de días.
    Compara cada fecha del selector con la fecha de HOY en Argentina.
    Devuelve el número de día que corresponde a hoy.
    """
    url = f"https://widget.matchscorerlive.com/screen/resultsbyday/FIP-{torneo['year']}-{torneo['id']}/1?t=tol"
    html = leer_url(url)
    if not html: return None
    soup = BeautifulSoup(html, "html.parser")
    hoy = hora_arg()

    active = soup.find("div", class_="play-day-button active")
    if active:
        parent = active.find_parent("a")
        if parent:
            m = re.search(r'/(\d+)\?', parent.get("href", ""))
            if m:
                print(f"   📅 día {m.group(1)} (active)")
                return int(m.group(1))

    mejor_dia = None
    menor_diff = 999
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        m = re.search(r'/(\d+)\?', href)
        if not m: continue
        num_dia = int(m.group(1))
        btn = a.find("div", class_="play-day-button")
        if not btn: continue
        fecha_span = btn.find("span", class_="play-day-date")
        if not fecha_span: continue
        fecha_txt = fecha_span.get_text(strip=True)
        partes = fecha_txt.split()
        if len(partes) >= 2:
            try:
                mes_num = MESES_WIDGET.get(partes[0].upper()[:3], 0)
                dia_num = int(partes[1])
                if mes_num > 0:
                    diff = abs((hoy.month - mes_num) * 31 + (hoy.day - dia_num))
                    if diff < menor_diff:
                        menor_diff = diff
                        mejor_dia = num_dia
            except: pass

    if mejor_dia:
        print(f"   📅 día {mejor_dia} (por fecha, diff={menor_diff})")
        return mejor_dia

    return None

def parsear_widget(html):
    """
    Parser basado en HTML real de matchscorerlive.
    Ganador: clase 'winner' en div.ml-2
    Marcador: TODOS los sets de cada equipo en orden, set_gan[i]-set_per[i]
    Solo COMPLETED.
    """
    soup = BeautifulSoup(html, "html.parser")
    partidos = []

    for tabla in soup.find_all("table", class_="w-100"):
        rows = tabla.find_all("tr", recursive=False)
        if len(rows) < 3: continue

        ronda = ""
        ronda_div = rows[0].find("div", class_="round-name")
        if ronda_div:
            for div in ronda_div.find_all("div"):
                t = div.get_text(strip=True)
                if t and t not in ("Men", "Women"):
                    ronda = t; break

        summary = next((tr for tr in rows if "summary" in tr.get("class", [])), None)
        if not summary or "completed" not in summary.get_text().lower(): continue

        team_rows = [tr for tr in rows if tr.find("div", class_="player-names")]
        if len(team_rows) < 2: continue

        def leer_equipo(tr):
            jugadores = []
            es_ganador = False
            double = tr.find("div", class_="double")
            if not double: return jugadores, False
            for div_jug in double.find_all("div", class_="d-flex"):
                img = div_jug.find("img", class_="flags")
                if not img: continue
                es_arg = "ARG" in img.get("src", "")
                ml2 = div_jug.find("div", class_="ml-2")
                if not ml2: continue
                if "winner" in ml2.get("class", []):
                    es_ganador = True
                spans = [s for s in ml2.find_all("span")
                         if "separator" not in s.get("class", [])
                         and s.get_text(strip=True)]
                nombre = " ".join(s.get_text(strip=True) for s in spans[:2]).strip()
                if nombre:
                    jugadores.append({"nombre": nombre, "es_arg": es_arg})
            return jugadores, es_ganador

        def todos_sets(tr):
            return [td.get_text(strip=True)
                    for td in tr.find_all("td", class_="set")
                    if td.get_text(strip=True) not in ("", "-")]

        eq1, gan1 = leer_equipo(team_rows[0])
        eq2, gan2 = leer_equipo(team_rows[1])
        if len(eq1) < 2 or len(eq2) < 2: continue

        hay_arg = any(j["es_arg"] for j in eq1 + eq2)
        if not hay_arg: continue
        if not gan1 and not gan2: continue

        gan = eq1 if gan1 else eq2
        per = eq2 if gan1 else eq1
        tr_gan = team_rows[0] if gan1 else team_rows[1]
        tr_per = team_rows[1] if gan1 else team_rows[0]

        sets_gan = todos_sets(tr_gan)
        sets_per = todos_sets(tr_per)

        sets_txt = []
        for i in range(max(len(sets_gan), len(sets_per))):
            g = sets_gan[i] if i < len(sets_gan) else "?"
            p = sets_per[i] if i < len(sets_per) else "?"
            sets_txt.append(f"{g}-{p}")
        marcador = " / ".join(sets_txt)

        partidos.append({
            "gan": gan, "per": per,
            "marcador": marcador,
            "ronda": ronda,
            "id": f"{gan[0]['nombre']}_{per[0]['nombre']}",
        })

    return partidos

def monitorear():
    pub = cargar_pub()
    for torneo in TORNEOS:
        print(f"📂 {torneo['nombre']}")
        dia = dia_actual_widget(torneo)
        if not dia:
            print(f"   ⚠️ No se pudo determinar el día")
            continue

        url = (f"https://widget.matchscorerlive.com/screen/resultsbyday"
               f"/FIP-{torneo['year']}-{torneo['id']}/{dia}?t=tol")
        html = leer_url(url)
        if not html or len(html) < 500:
            print(f"   ⚠️ Widget no disponible")
            continue

        try:
            partidos = parsear_widget(html)
        except Exception as e:
            print(f"   ⚠️ {e}"); continue

        print(f"   → {len(partidos)} con arg")

        for p in partidos:
            pid = f"{torneo['id']}_{p['id']}"
            if pid in pub: continue

            def fmt(j):
                return f"🇦🇷 {j['nombre']}" if j['es_arg'] else j['nombre']

            gan_arg = any(j["es_arg"] for j in p["gan"])
            ronda_txt = ronda_es(p["ronda"])

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

def ciclo():
    print("="*50)
    print("🤖 BOT TELEGRAM PADEL ARGENTINA — v23")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)
    tg_enviar(
        "🤖 <b>Bot Padel Argentina v23 ✅</b>\n\n"
        "📡 matchscorerlive | marcador correcto\n"
        "🎾 Solo día actual por fecha\n"
        "🇦🇷 Valladolid · Abidjan · Giulianova · Astorga · Selangor · Iquique\n\n"
        f"{LINK_WEB}"
    )
    contador = 0
    while True:
        print(f"\n🔍 [{hora_arg().strftime('%H:%M:%S')}] Ciclo {contador+1}")
        try:
            monitorear()
        except Exception as e:
            print(f"⚠️ Error: {e}")
        print(f"✅ Próximo en {INTERVALO_MIN} min")
        contador += 1
        time.sleep(INTERVALO_MIN * 60)

if __name__ == "__main__":
    ciclo()
