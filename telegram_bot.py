import os
import time
import json
import requests
import pytz
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ARGENTINA_TZ     = pytz.timezone("America/Argentina/Buenos_Aires")

INTERVALO_MIN      = 2
ARCHIVO_PUBLICADOS = "tg_publicados.json"
ARCHIVO_ESTADO     = "tg_estado.json"
LINK_WEB           = "🌐 www.padelargentina.com.ar"

TORNEOS_PREMIER = [
    {
        "nombre":    "Premier Padel P1 Valencia",
        "ciudad":    "Valencia",
        "bandera":   "🇪🇸",
        "tz_local":  "Europe/Madrid",
        "emoji":     "🏟️",
        "ss_id_men": 35317,
        "ss_id_women": 35318,
    },
]

TORNEOS_FIP = [
    {
        "nombre":  "FIP Bronze Eslovenia",
        "ciudad":  "Ljubljana",
        "bandera": "🇸🇮",
        "emoji":   "🎾",
        "url_fip": "https://www.padelfip.com/es/events/fip-bronze-slovenia-2026/",
    },
]

ARGENTINOS = {
    "Agustin Tapia":              "Agustín Tapia",
    "Federico Chingotto":         "Federico Chingotto",
    "Franco Stupaczuk":           "Franco Stupaczuk",
    "Leandro Augsburger":         "Leandro Augsburger",
    "Martin Di Nenno":            "Martín Di Nenno",
    "Gonzalo Alfonso":            "Gonzalo Alfonso",
    "Leonel Aguirre":             "Leonel Aguirre",
    "Juan Tello":                 "Juan Tello",
    "Maximiliano Arce":           "Maxi Arce",
    "Luciano Capra":              "Luciano Capra",
    "Ignacio Piotto":             "Ignacio Piotto",
    "Juan Cruz Belluati":         "Juan Cruz Belluati",
    "Juan Ignacio Rubini":        "Juan I. Rubini",
    "Federico Mourino":           "Federico Mouriño",
    "Valentino Libaak":           "Valentino Libaak",
    "Alex Chozas":                "Alex Chozas",
    "Carlos Gutierrez":           "Carlos Gutiérrez",
    "Maximiliano Sanchez Blasco": "Maxi Sánchez Blasco",
    "Agustin Torre":              "Agustín Torre",
    "Juan Cruz Forastello":       "Juan Cruz Forastello",
    "Juan Ignacio De Pascual":    "Juan I. De Pascual",
    "Maximiliano Sanchez Aguero": "Maxi Sánchez Agüero",
    "Delfina Brea":               "Delfina Brea",
    "Ariana Sanchez":             "Ariana Sánchez",
    "Sofia Araujo":               "Sofía Araújo",
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def hora_arg():
    return datetime.now(ARGENTINA_TZ)

def es_argentino(nombre):
    return any(k.lower() in nombre.lower() for k in ARGENTINOS)

def nombre_display(nombre):
    for k, v in ARGENTINOS.items():
        if k.lower() in nombre.lower():
            return f"🇦🇷 {v}"
    return nombre

def apellido(nombre):
    return nombre.strip().split()[-1] if nombre.strip() else nombre

def cargar_json(archivo):
    if os.path.exists(archivo):
        with open(archivo) as f:
            return json.load(f)
    return {}

def guardar_json(archivo, data):
    with open(archivo, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cargar_publicados():
    d = cargar_json(ARCHIVO_PUBLICADOS)
    return set(d.get("ids", []))

def guardar_publicado(pid):
    d = cargar_json(ARCHIVO_PUBLICADOS)
    ids = set(d.get("ids", []))
    ids.add(pid)
    guardar_json(ARCHIVO_PUBLICADOS, {"ids": list(ids)})

def ya_hecho_hoy(tarea):
    estado = cargar_json(ARCHIVO_ESTADO)
    return estado.get(tarea) == hora_arg().strftime("%Y-%m-%d")

def marcar_hecho_hoy(tarea):
    estado = cargar_json(ARCHIVO_ESTADO)
    estado[tarea] = hora_arg().strftime("%Y-%m-%d")
    guardar_json(ARCHIVO_ESTADO, estado)

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def enviar(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       texto,
            "parse_mode": "HTML",
        }, timeout=15)
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} TG: {texto[:60]}...")
        return ok
    except Exception as e:
        print(f"❌ TG error: {e}")
        return False

# ─────────────────────────────────────────────
# SOFASCORE API
# ─────────────────────────────────────────────

SS_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

def ss_get(path):
    try:
        r = requests.get(f"https://api.sofascore.com/api/v1{path}",
                         headers=SS_HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[SS] {path}: {e}")
    return None

def partidos_finalizados_hoy(ss_id):
    data = ss_get(f"/unique-tournament/{ss_id}/events/last/0")
    if not data:
        return []
    hoy = hora_arg().date()
    result = []
    for p in data.get("events", []):
        if p.get("status", {}).get("type") != "finished":
            continue
        ts = p.get("startTimestamp", 0)
        if datetime.fromtimestamp(ts, tz=ARGENTINA_TZ).date() == hoy:
            result.append(p)
    return result

def partidos_proximos_hoy(ss_id):
    data = ss_get(f"/unique-tournament/{ss_id}/events/next/0")
    if not data:
        return []
    hoy = hora_arg().date()
    return [
        p for p in data.get("events", [])
        if datetime.fromtimestamp(p.get("startTimestamp", 0),
                                   tz=ARGENTINA_TZ).date() == hoy
    ]

def orden_dia_manana(ss_id, tz_local):
    data = ss_get(f"/unique-tournament/{ss_id}/events/next/0")
    if not data:
        return {}
    manana = (hora_arg() + timedelta(days=1)).date()
    tz     = pytz.timezone(tz_local)
    pistas = {}

    for p in data.get("events", []):
        ts = p.get("startTimestamp", 0)
        dt_local = datetime.fromtimestamp(ts, tz=tz)
        dt_arg   = datetime.fromtimestamp(ts, tz=ARGENTINA_TZ)
        if dt_local.date() != manana:
            continue

        pista = p.get("venue", {}).get("name") or "Pista"
        home  = p.get("homeTeam", {})
        away  = p.get("awayTeam", {})

        if pista not in pistas:
            pistas[pista] = []
        pistas[pista].append({
            "hora_arg":   dt_arg.strftime("%H:%M"),
            "hora_local": dt_local.strftime("%H:%M"),
            "j1": home.get("name", ""),
            "j2": home.get("subTeamName", "") or "",
            "j3": away.get("name", ""),
            "j4": away.get("subTeamName", "") or "",
        })

    for pista in pistas:
        pistas[pista].sort(key=lambda x: x["hora_arg"])
    return pistas

def cuadros_ss(ss_id):
    data = ss_get(f"/unique-tournament/{ss_id}/events/next/0")
    if not data:
        return []
    parejas = []
    for p in data.get("events", []):
        home = p.get("homeTeam", {})
        away = p.get("awayTeam", {})
        j1 = home.get("name", "")
        j3 = away.get("name", "")
        j2 = home.get("subTeamName", "") or ""
        j4 = away.get("subTeamName", "") or ""
        if j1 and j3:
            parejas.append((j1, j2, j3, j4))
    return parejas

def parsear(p):
    home  = p.get("homeTeam", {})
    away  = p.get("awayTeam", {})
    hs    = p.get("homeScore", {})
    as_   = p.get("awayScore", {})
    j1, j2 = home.get("name", ""), home.get("subTeamName", "") or ""
    j3, j4 = away.get("name", ""), away.get("subTeamName", "") or ""

    sets = []
    for i in range(1, 6):
        sh = hs.get(f"period{i}")
        sa = as_.get(f"period{i}")
        if sh is not None and sa is not None:
            sets.append(f"{sh}-{sa}")
    marcador = " / ".join(sets) if sets else "—"

    winner = p.get("winnerCode", 0)
    if winner == 1:
        gan, per = [j1, j2], [j3, j4]
    else:
        gan, per = [j3, j4], [j1, j2]

    tm = p.get("time", {}).get("played")
    tiempo = f"{tm//60}h {tm%60}min" if tm else None

    return {
        "id":        str(p.get("id", "")),
        "ganadores": gan,
        "perdedores": per,
        "marcador":  marcador,
        "ronda":     p.get("roundInfo", {}).get("name", ""),
        "tiempo":    tiempo,
    }

# ─────────────────────────────────────────────
# MENSAJES TELEGRAM
# ─────────────────────────────────────────────

def msg_cuadros(torneo, genero, parejas_q, parejas_p):
    emoji_gen = "👨" if genero == "Masculino" else "👩"
    lineas = [
        f"📋 <b>CUADROS {genero.upper()} {emoji_gen}</b>",
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>",
        f"📍 {torneo['ciudad']} {torneo['bandera']}",
        "",
        "🔹 <b>QUALIFYING</b>",
    ]
    for j1, j2, j3, j4 in parejas_q[:6]:
        lineas.append(f"  {nombre_display(j1)}/{nombre_display(j2)} vs {nombre_display(j3)}/{nombre_display(j4)}")
    lineas += ["", "🔸 <b>CUADRO PRINCIPAL</b>"]
    for j1, j2, j3, j4 in parejas_p[:8]:
        lineas.append(f"  {nombre_display(j1)}/{nombre_display(j2)} vs {nombre_display(j3)}/{nombre_display(j4)}")
    lineas += ["", LINK_WEB]
    return "\n".join(lineas)

def msg_orden_dia(torneo, pistas):
    manana = (hora_arg() + timedelta(days=1)).strftime("%d/%m/%Y")
    lineas = [
        f"🗓️ <b>ORDEN DE JUEGO — {manana}</b>",
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>",
        f"📍 {torneo['ciudad']} {torneo['bandera']}",
        "",
    ]
    for pista, partidos in pistas.items():
        lineas.append(f"🎾 <b>{pista}</b>")
        for p in partidos:
            j1 = nombre_display(p["j1"])
            j3 = nombre_display(p["j3"])
            lineas.append(
                f"  🇦🇷⏰ {p['hora_arg']}hs "
                f"({torneo['bandera']} {p['hora_local']}hs)\n"
                f"  {j1} / {nombre_display(p['j2'])} vs {j3} / {nombre_display(p['j4'])}"
            )
        lineas.append("")
    lineas += ["¡Nos vemos mañana! 🎾🇦🇷", "", LINK_WEB]
    return "\n".join(lineas)

def msg_resultado_premier(torneo, gan, per, marcador, tiempo, ronda):
    arg_gana = any(es_argentino(j) for j in gan)
    cab = "🇦🇷⚡ <b>VICTORIA ARGENTINA</b>" if arg_gana else "🎾 <b>RESULTADO</b>"
    lineas = [
        cab,
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b> | {ronda.upper()}",
        f"📍 {torneo['ciudad']} {torneo['bandera']}",
        "",
        f"✅ {nombre_display(gan[0])} / {nombre_display(gan[1])}",
        f"❌ {nombre_display(per[0])} / {nombre_display(per[1])}",
        f"🎯 {marcador}",
    ]
    if tiempo:
        lineas.append(f"⏱️ {tiempo}")
    lineas += ["", LINK_WEB]
    return "\n".join(lineas)

def msg_resultado_fip(torneo, gan, per, marcador, ronda, arg_gana):
    lugar = torneo["nombre"].split()[-1]
    cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA:</b>" if arg_gana else f"🎾🇦🇷 <b>Derrota argentina en el FIP de {lugar}</b>"
    lineas = [
        cab,
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b> | {ronda.upper()}",
        f"📍 {torneo['ciudad']} {torneo['bandera']}",
        "",
        f"✅ {nombre_display(gan[0])} / {nombre_display(gan[1])}",
        f"❌ {nombre_display(per[0])} / {nombre_display(per[1])}",
        f"🎯 {marcador}",
        "",
        LINK_WEB,
    ]
    return "\n".join(lineas)

def msg_campeon(torneo, cam, fin, marcador, es_arg):
    if es_arg:
        cab = "👑🇦🇷 <b>¡¡CAMPEONES ARGENTINOS!! ¡¡LOS PIBES SE LLEVARON EL TÍTULO!!</b>"
    else:
        cab = f"🏆 <b>¡CAMPEONES! {apellido(cam[0])} y {apellido(cam[1])}</b>"
    return "\n".join([
        cab,
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()} — FINAL</b>",
        f"📍 {torneo['ciudad']} {torneo['bandera']}",
        "",
        f"🥇 {nombre_display(cam[0])} / {nombre_display(cam[1])}",
        f"🥈 {nombre_display(fin[0])} / {nombre_display(fin[1])}",
        f"🎯 {marcador}",
        "",
        LINK_WEB,
    ])

# ─────────────────────────────────────────────
# TAREAS
# ─────────────────────────────────────────────

def tarea_cuadros():
    for torneo in TORNEOS_PREMIER:
        tid = f"cuadros_{torneo['nombre']}"
        if ya_hecho_hoy(tid):
            continue
        for ss_id, genero in [(torneo["ss_id_men"], "Masculino"),
                               (torneo["ss_id_women"], "Femenino")]:
            parejas = cuadros_ss(ss_id)
            if parejas:
                msg = msg_cuadros(torneo, genero, parejas[:6], parejas)
                enviar(msg)
                time.sleep(4)
        marcar_hecho_hoy(tid)

def tarea_orden_dia():
    for torneo in TORNEOS_PREMIER:
        tid = f"orden_dia_{torneo['nombre']}"
        if ya_hecho_hoy(tid):
            continue
        # Solo publicar si ya no quedan partidos hoy
        if partidos_proximos_hoy(torneo["ss_id_men"]):
            continue
        pistas = orden_dia_manana(torneo["ss_id_men"], torneo["tz_local"])
        if pistas:
            if enviar(msg_orden_dia(torneo, pistas)):
                marcar_hecho_hoy(tid)

def monitorear_premier():
    publicados = cargar_publicados()
    for torneo in TORNEOS_PREMIER:
        for ss_id in [torneo["ss_id_men"], torneo["ss_id_women"]]:
            for p in partidos_finalizados_hoy(ss_id):
                d   = parsear(p)
                pid = f"premier_{d['id']}"
                if pid in publicados:
                    continue
                msg = msg_resultado_premier(
                    torneo, d["ganadores"], d["perdedores"],
                    d["marcador"], d["tiempo"], d["ronda"]
                )
                if enviar(msg):
                    guardar_publicado(pid)
                    time.sleep(4)

def monitorear_fip():
    from bs4 import BeautifulSoup
    publicados = cargar_publicados()
    try:
        r = requests.get("https://www.padelfip.com/es/noticias/",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        vistos = set()
        for a in soup.find_all("a", href=True):
            href  = a.get("href", "")
            texto = a.get_text(strip=True)
            if "/2026/" not in href or len(texto) < 25:
                continue
            if href in vistos or href in publicados:
                continue
            vistos.add(href)
            tiene_arg = any(k.lower() in texto.lower() for k in ARGENTINOS)
            es_result = any(kw in texto.lower() for kw in [
                "vence", "gana", "triunfa", "campeón", "derrota", "elimina", "avanza"
            ])
            if not tiene_arg or not es_result:
                continue
            torneo   = TORNEOS_FIP[0]
            arg_gana = any(kw in texto.lower() for kw in
                           ["vence", "gana", "triunfa", "campeón", "avanza"])
            lugar    = torneo["nombre"].split()[-1]
            cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA:</b>" if arg_gana else f"🎾🇦🇷 <b>Derrota argentina en el FIP de {lugar}</b>"
            msg = (
                f"{cab}\n\n"
                f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>\n"
                f"📍 {torneo['ciudad']} {torneo['bandera']}\n\n"
                f"📋 {texto}\n\n"
                f"{LINK_WEB}"
            )
            if enviar(msg):
                guardar_publicado(href)
                time.sleep(3)
    except Exception as e:
        print(f"[FIP TG] {e}")

# ─────────────────────────────────────────────
# LOOP
# ─────────────────────────────────────────────

def ciclo():
    print(f"\n{'='*50}")
    print(f"🤖 BOT TELEGRAM — PADEL ARGENTINA INICIADO")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*50}\n")

    enviar(
        "🤖 <b>Bot Padel Argentina activado ✅</b>\n\n"
        "Publicaré:\n"
        "📋 Cuadros de torneos al inicio\n"
        "🗓️ Orden del día al terminar cada jornada\n"
        "🎾 Resultados en tiempo real\n"
        "🇦🇷 Victoria/derrota argentina\n\n"
        f"{LINK_WEB}"
    )

    contador = 0
    while True:
        print(f"\n🔍 [{hora_arg().strftime('%H:%M:%S')}] Ciclo {contador+1}")
        tarea_cuadros()
        tarea_orden_dia()
        monitorear_premier()
        monitorear_fip()
        print(f"✅ Próximo en {INTERVALO_MIN} min")
        contador += 1
        time.sleep(INTERVALO_MIN * 60)

if __name__ == "__main__":
    ciclo()
