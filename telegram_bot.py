import os
import time
import json
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

ARGENTINA_TZ     = pytz.timezone("America/Argentina/Buenos_Aires")

ARCHIVO_PUBLICADOS  = "telegram_publicados.json"
ARCHIVO_ESTADO      = "telegram_estado.json"

INTERVALO_PREMIER   = 2   # minutos
INTERVALO_FIP       = 5   # minutos
HORA_RESUMEN_MANANA = 22  # 22hs Argentina = resumen del día siguiente
HORA_ORDEN_DIA      = 7   # 7hs Argentina = orden del día

LINK_WEB = "🌐 www.padelargentina.com.ar"

TORNEOS_PREMIER = [
    {
        "nombre":   "Premier Padel P1 Valencia",
        "url":      "https://www.padelfip.com/es/events/valencia-p1-2026/",
        "emoji":    "🏟️",
        "ciudad":   "Valencia",
        "pais":     "España",
        "bandera":  "🇪🇸",
        "tz_local": "Europe/Madrid",
        "tz_offset": "+2hs",
        "categoria": "P1",
    },
]

TORNEOS_FIP = [
    {
        "nombre":   "FIP Bronze Eslovenia",
        "url":      "https://www.padelfip.com/es/events/fip-bronze-slovenia-2026/",
        "emoji":    "🎾",
        "ciudad":   "Ljubljana",
        "pais":     "Eslovenia",
        "bandera":  "🇸🇮",
        "tz_local": "Europe/Ljubljana",
        "tz_offset": "+5hs",
        "categoria": "FIP Bronze",
    },
]

ARGENTINOS = {
    "Agustin Tapia":              "🇦🇷 Agustín Tapia",
    "Federico Chingotto":         "🇦🇷 Federico Chingotto",
    "Franco Stupaczuk":           "🇦🇷 Franco Stupaczuk",
    "Leandro Augsburger":         "🇦🇷 Leandro Augsburger",
    "Martin Di Nenno":            "🇦🇷 Martín Di Nenno",
    "Gonzalo Alfonso":            "🇦🇷 Gonzalo Alfonso",
    "Leonel Aguirre":             "🇦🇷 Leonel Aguirre",
    "Juan Tello":                 "🇦🇷 Juan Tello",
    "Maximiliano Arce":           "🇦🇷 Maxi Arce",
    "Luciano Capra":              "🇦🇷 Luciano Capra",
    "Ignacio Piotto":             "🇦🇷 Ignacio Piotto",
    "Juan Cruz Belluati":         "🇦🇷 Juan Cruz Belluati",
    "Juan Ignacio Rubini":        "🇦🇷 Juan I. Rubini",
    "Federico Mourino":           "🇦🇷 Federico Mouriño",
    "Valentino Libaak":           "🇦🇷 Valentino Libaak",
    "Alex Chozas":                "🇦🇷 Alex Chozas",
    "Carlos Gutierrez":           "🇦🇷 Carlos Gutiérrez",
    "Maximiliano Sanchez Blasco": "🇦🇷 Maxi Sánchez Blasco",
    "Agustin Torre":              "🇦🇷 Agustín Torre",
    "Juan Cruz Forastello":       "🇦🇷 Juan Cruz Forastello",
    "Juan Ignacio De Pascual":    "🇦🇷 Juan I. De Pascual",
    "Maximiliano Sanchez Aguero": "🇦🇷 Maxi Sánchez Agüero",
    "Delfina Brea":               "🇦🇷 Delfina Brea",
    "Ariana Sanchez":             "🇦🇷 Ariana Sánchez",
    "Sofia Araujo":               "🇦🇷 Sofía Araújo",
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def hora_argentina():
    return datetime.now(ARGENTINA_TZ)

def convertir_hora_arg(hora_local_str, tz_local_str):
    """Convierte hora local del torneo a hora argentina"""
    try:
        tz_local = pytz.timezone(tz_local_str)
        hoy = datetime.now(tz_local).date()
        h, m = map(int, hora_local_str.split(":"))
        dt_local = tz_local.localize(datetime(hoy.year, hoy.month, hoy.day, h, m))
        dt_arg = dt_local.astimezone(ARGENTINA_TZ)
        return dt_arg.strftime("%H:%M")
    except:
        return hora_local_str

def nombre_display(nombre):
    for clave, display in ARGENTINOS.items():
        if clave.lower() in nombre.lower():
            return display
    return nombre

def es_argentino(nombre):
    return any(k.lower() in nombre.lower() for k in ARGENTINOS)

def cargar_json(archivo):
    if os.path.exists(archivo):
        with open(archivo, "r") as f:
            return json.load(f)
    return {}

def guardar_json(archivo, data):
    with open(archivo, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cargar_publicados():
    d = cargar_json(ARCHIVO_PUBLICADOS)
    return set(d.get("ids", []))

def guardar_publicado(id_msg):
    d = cargar_json(ARCHIVO_PUBLICADOS)
    ids = set(d.get("ids", []))
    ids.add(id_msg)
    guardar_json(ARCHIVO_PUBLICADOS, {"ids": list(ids)})

# ─────────────────────────────────────────────
# ENVÍO TELEGRAM
# ─────────────────────────────────────────────

def enviar_mensaje(texto, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       texto,
        "parse_mode": parse_mode,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print(f"✅ Telegram: {texto[:60]}...")
            return True
        else:
            print(f"❌ Telegram error {r.status_code}: {r.text[:100]}")
            return False
    except Exception as e:
        print(f"❌ Telegram excepción: {e}")
        return False

# ─────────────────────────────────────────────
# SCRAPING
# ─────────────────────────────────────────────

def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] fetch {url}: {e}")
        return None

def obtener_orden_juego(torneo):
    """Scrapea el orden de juego del torneo desde padelfip.com"""
    soup = fetch(torneo["url"])
    if not soup:
        return []
    partidos = []
    texto = soup.get_text()
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    for i, linea in enumerate(lineas):
        if any(h in linea for h in ["10:30", "10.30", "9:00", "9.00", "12:00", "14:00", "16:00", "18:00", "20:00"]):
            bloque = " ".join(lineas[i:i+6])
            partidos.append(bloque[:300])
    return partidos

def obtener_cuadro(torneo, tipo="principal"):
    """Scrapea el cuadro del torneo"""
    soup = fetch(torneo["url"])
    if not soup:
        return []
    jugadores = []
    for img in soup.find_all("img", {"title": "flag"}):
        siguiente = img.find_next_sibling(string=True)
        if siguiente and len(siguiente.strip()) > 3:
            jugadores.append(siguiente.strip())
    return jugadores

def obtener_noticias_fip():
    soup = fetch("https://www.padelfip.com/es/noticias/")
    if not soup:
        return []
    noticias = []
    vistos = set()
    for a in soup.find_all("a", href=True):
        href  = a.get("href", "")
        texto = a.get_text(strip=True)
        if "/2026/" in href and len(texto) > 25 and href not in vistos:
            vistos.add(href)
            noticias.append({"titulo": texto, "url": href})
    return noticias

# ─────────────────────────────────────────────
# MENSAJES FORMATEADOS
# ─────────────────────────────────────────────

def msg_cuadro_qualifying(torneo, genero="Masculino"):
    emoji_gen = "👨" if genero == "Masculino" else "👩"
    soup = fetch(torneo["url"])
    if not soup:
        return None

    jugadores = obtener_cuadro(torneo)
    if not jugadores:
        return None

    # Tomar primeros 32 para qualifying
    cuadro = jugadores[:32]
    lineas_cuadro = ""
    for i in range(0, min(len(cuadro), 16), 2):
        j1 = nombre_display(cuadro[i])   if i < len(cuadro) else "—"
        j2 = nombre_display(cuadro[i+1]) if i+1 < len(cuadro) else "—"
        lineas_cuadro += f"  {j1} vs {j2}\n"

    msg = (
        f"📋 <b>CUADRO QUALIFYING {genero.upper()}</b> {emoji_gen}\n"
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>\n"
        f"📍 {torneo['ciudad']} {torneo['bandera']}\n\n"
        f"{lineas_cuadro}\n"
        f"{LINK_WEB}"
    )
    return msg

def msg_cuadro_principal(torneo, genero="Masculino"):
    emoji_gen = "👨" if genero == "Masculino" else "👩"
    soup = fetch(torneo["url"])
    if not soup:
        return None

    jugadores = obtener_cuadro(torneo)
    if not jugadores:
        return None

    cuadro = jugadores[32:80] if len(jugadores) > 32 else jugadores
    lineas_cuadro = ""
    for i in range(0, min(len(cuadro), 16), 2):
        j1 = nombre_display(cuadro[i])   if i < len(cuadro) else "—"
        j2 = nombre_display(cuadro[i+1]) if i+1 < len(cuadro) else "—"
        lineas_cuadro += f"  {j1} vs {j2}\n"

    msg = (
        f"🏆 <b>CUADRO PRINCIPAL {genero.upper()}</b> {emoji_gen}\n"
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>\n"
        f"📍 {torneo['ciudad']} {torneo['bandera']}\n\n"
        f"{lineas_cuadro}\n"
        f"{LINK_WEB}"
    )
    return msg

def msg_orden_dia(torneo, partidos_dia):
    """Mensaje de inicio del día con todos los partidos por pista"""
    ahora = hora_argentina()
    fecha = ahora.strftime("%d/%m/%Y")

    lineas = []
    lineas.append(f"☀️ <b>ORDEN DE JUEGO — {fecha}</b>")
    lineas.append(f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>")
    lineas.append(f"📍 {torneo['ciudad']} {torneo['bandera']}")
    lineas.append("")

    for pista, partidos in partidos_dia.items():
        lineas.append(f"🎾 <b>{pista}</b>")
        for p in partidos:
            hora_arg = convertir_hora_arg(p["hora_local"], torneo["tz_local"])
            lineas.append(
                f"  🇦🇷⏰ {hora_arg}hs "
                f"({torneo['bandera']} {p['hora_local']}hs)\n"
                f"  {nombre_display(p['j1'])} / {nombre_display(p['j2'])}\n"
                f"  vs\n"
                f"  {nombre_display(p['j3'])} / {nombre_display(p['j4'])}"
            )
        lineas.append("")

    lineas.append(LINK_WEB)
    return "\n".join(lineas)

def msg_resultado_premier(torneo, ganadores, perdedores, sets,
                           tiempo, ronda_actual, ronda_siguiente,
                           proximos_rivales):
    """Resultado completo Premier Padel con actualización por set"""
    arg_gana = any(es_argentino(j) for j in ganadores)

    g1 = nombre_display(ganadores[0])
    g2 = nombre_display(ganadores[1])
    p1 = nombre_display(perdedores[0])
    p2 = nombre_display(perdedores[1])

    cabecera = "🇦🇷⚡ <b>VICTORIA ARGENTINA</b>" if arg_gana else "🎾 <b>RESULTADO</b>"

    lineas = [
        cabecera,
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b> | {ronda_actual.upper()}",
        f"📍 {torneo['ciudad']} {torneo['bandera']}",
        "",
        f"✅ {g1} / {g2}",
        f"❌ {p1} / {p2}",
        f"🎯 {sets}",
    ]
    if tiempo:
        lineas.append(f"⏱️ {tiempo}")
    lineas.append("")
    if ronda_siguiente:
        lineas.append(f"➡️ Avanzan a <b>{ronda_siguiente}</b>")
    if proximos_rivales:
        lineas.append(f"🆚 Próximos rivales: {proximos_rivales}")
    lineas.append("")
    lineas.append(LINK_WEB)

    return "\n".join(lineas)

def msg_resultado_set(torneo, j1, j2, j3, j4, sets_hasta_ahora, ronda):
    """Actualización parcial tras finalizar un set"""
    p1 = nombre_display(j1)
    p2 = nombre_display(j2)
    p3 = nombre_display(j3)
    p4 = nombre_display(j4)

    return (
        f"📊 <b>PARCIAL — SET FINALIZADO</b>\n"
        f"{torneo['emoji']} {torneo['nombre']} | {ronda}\n\n"
        f"  {p1} / {p2}\n"
        f"  vs\n"
        f"  {p3} / {p4}\n\n"
        f"🎯 Parcial: {sets_hasta_ahora}\n\n"
        f"{LINK_WEB}"
    )

def msg_resultado_fip(torneo, ganadores, perdedores, marcador,
                      ronda_actual, ronda_siguiente, arg_gana):
    g1 = nombre_display(ganadores[0])
    g2 = nombre_display(ganadores[1])
    p1 = nombre_display(perdedores[0])
    p2 = nombre_display(perdedores[1])

    partes = torneo["nombre"].split()
    lugar  = partes[-1]

    if arg_gana:
        cabecera = f"🎾🇦🇷 <b>VICTORIA ARGENTINA:</b>"
    else:
        cabecera = f"🎾🇦🇷 <b>Derrota argentina en el FIP de {lugar}</b>"

    lineas = [
        cabecera,
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b> | {ronda_actual.upper()}",
        f"📍 {torneo['ciudad']} {torneo['bandera']}",
        "",
        f"✅ {g1} / {g2}",
        f"❌ {p1} / {p2}",
        f"🎯 {marcador}",
        "",
    ]
    if arg_gana and ronda_siguiente:
        lineas.append(f"➡️ Avanzan a <b>{ronda_siguiente}</b>")
        lineas.append("")
    lineas.append(LINK_WEB)

    return "\n".join(lineas)

def msg_campeon_premier(torneo, campeones, finalistas, marcador, es_arg):
    c1 = nombre_display(campeones[0])
    c2 = nombre_display(campeones[1])
    f1 = nombre_display(finalistas[0])
    f2 = nombre_display(finalistas[1])

    if es_arg:
        cabecera = "👑🇦🇷 <b>¡¡CAMPEONES ARGENTINOS!! ¡¡LOS PIBES SE LLEVARON EL TÍTULO!!</b>"
    else:
        ap1 = campeones[0].split()[-1]
        ap2 = campeones[1].split()[-1]
        cabecera = f"🏆 <b>¡CAMPEONES! {ap1} y {ap2}</b>"

    return (
        f"{cabecera}\n\n"
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()} — FINAL</b>\n"
        f"📍 {torneo['ciudad']} {torneo['bandera']}\n\n"
        f"🥇 {c1} / {c2}\n"
        f"🥈 {f1} / {f2}\n"
        f"🎯 {marcador}\n\n"
        f"{LINK_WEB}"
    )

def msg_resumen_manana(torneo, partidos_manana):
    """Mensaje de cierre del día con anticipo de mañana"""
    manana = (hora_argentina() + timedelta(days=1)).strftime("%d/%m/%Y")

    lineas = []
    lineas.append(f"🌙 <b>MAÑANA EN LA PISTA — {manana}</b>")
    lineas.append(f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>")
    lineas.append(f"📍 {torneo['ciudad']} {torneo['bandera']}")
    lineas.append("")

    for pista, partidos in partidos_manana.items():
        lineas.append(f"🎾 <b>{pista}</b>")
        for p in partidos:
            hora_arg = convertir_hora_arg(p["hora_local"], torneo["tz_local"])
            lineas.append(
                f"  🇦🇷⏰ {hora_arg}hs "
                f"({torneo['bandera']} {p['hora_local']}hs)\n"
                f"  {nombre_display(p['j1'])} / {nombre_display(p['j2'])}\n"
                f"  vs\n"
                f"  {nombre_display(p['j3'])} / {nombre_display(p['j4'])}"
            )
        lineas.append("")

    lineas.append("¡Nos vemos mañana! 🎾🇦🇷")
    lineas.append("")
    lineas.append(LINK_WEB)
    return "\n".join(lineas)

def msg_noticia_destacada(titulo, url):
    return (
        f"📰 <b>NOTICIA DESTACADA</b>\n\n"
        f"{titulo}\n\n"
        f"🔗 {url}\n\n"
        f"{LINK_WEB}"
    )

# ─────────────────────────────────────────────
# PUBLICAR CUADROS AL INICIO DEL TORNEO
# ─────────────────────────────────────────────

def publicar_cuadros_torneo(torneo):
    pid = f"cuadros_{torneo['nombre']}"
    publicados = cargar_publicados()
    if pid in publicados:
        return

    print(f"📋 Publicando cuadros de {torneo['nombre']}...")

    for genero in ["Masculino", "Femenino"]:
        # Qualifying
        msg_q = msg_cuadro_qualifying(torneo, genero)
        if msg_q:
            enviar_mensaje(msg_q)
            time.sleep(3)

        # Principal
        msg_p = msg_cuadro_principal(torneo, genero)
        if msg_p:
            enviar_mensaje(msg_p)
            time.sleep(3)

    guardar_publicado(pid)

# ─────────────────────────────────────────────
# MONITOREO DE NOTICIAS Y RESULTADOS
# ─────────────────────────────────────────────

def procesar_noticias(noticias, torneos, solo_argentinos=False):
    publicados = cargar_publicados()

    for noticia in noticias:
        url    = noticia["url"]
        titulo = noticia["titulo"]

        if url in publicados:
            continue

        tiene_arg = any(a.lower() in titulo.lower() for a in ARGENTINOS)
        es_resultado = any(kw in titulo.lower() for kw in [
            "vence", "gana", "triunfa", "campeón", "resultado",
            "derrota", "elimina", "avanza", "final", "día"
        ])

        if not es_resultado:
            continue

        if solo_argentinos and not tiene_arg:
            continue

        # Encontrar torneo correspondiente
        torneo_match = None
        for t in torneos:
            if any(p.lower() in url.lower() for p in t["nombre"].lower().split()):
                torneo_match = t
                break

        if not torneo_match:
            torneo_match = torneos[0] if torneos else None

        if not torneo_match:
            continue

        # Formatear mensaje
        if solo_argentinos:
            arg_gana = any(kw in titulo.lower() for kw in
                          ["vence", "gana", "triunfa", "campeón", "avanza"])
            partes   = torneo_match["nombre"].split()
            lugar    = partes[-1]
            if arg_gana:
                cabecera = f"🎾🇦🇷 <b>VICTORIA ARGENTINA:</b>"
            else:
                cabecera = f"🎾🇦🇷 <b>Derrota argentina en el FIP de {lugar}</b>"
        else:
            if tiene_arg:
                cabecera = "🇦🇷⚡ <b>VICTORIA ARGENTINA</b>"
            else:
                cabecera = "🎾 <b>RESULTADO</b>"

        msg = (
            f"{cabecera}\n\n"
            f"{torneo_match['emoji']} <b>{torneo_match['nombre'].upper()}</b>\n"
            f"📍 {torneo_match['ciudad']} {torneo_match['bandera']}\n\n"
            f"📋 {titulo}\n\n"
            f"{LINK_WEB}"
        )

        if enviar_mensaje(msg):
            guardar_publicado(url)
            time.sleep(3)

# ─────────────────────────────────────────────
# TAREAS PROGRAMADAS
# ─────────────────────────────────────────────

estado = cargar_json(ARCHIVO_ESTADO)

def ya_hecho_hoy(tarea):
    hoy = hora_argentina().strftime("%Y-%m-%d")
    return estado.get(tarea) == hoy

def marcar_hecho_hoy(tarea):
    estado[tarea] = hora_argentina().strftime("%Y-%m-%d")
    guardar_json(ARCHIVO_ESTADO, estado)

def tareas_programadas():
    ahora = hora_argentina()
    hora  = ahora.hour

    # 7hs — orden del día
    if hora == HORA_ORDEN_DIA and not ya_hecho_hoy("orden_dia"):
        for torneo in TORNEOS_PREMIER:
            # Publicar cuadros si es inicio de torneo
            publicar_cuadros_torneo(torneo)
            # Mensaje de bienvenida al día
            msg = (
                f"☀️ <b>¡BUENOS DÍAS PADELEROS! 🎾🇦🇷</b>\n\n"
                f"Hoy tenemos pádel de alto nivel.\n"
                f"Te traemos todos los resultados en tiempo real.\n\n"
                f"{LINK_WEB}"
            )
            enviar_mensaje(msg)
        marcar_hecho_hoy("orden_dia")

    # 22hs — anticipo de mañana
    if hora == HORA_RESUMEN_MANANA and not ya_hecho_hoy("resumen_manana"):
        for torneo in TORNEOS_PREMIER:
            msg = (
                f"🌙 <b>CERRAMOS LA JORNADA 🎾</b>\n\n"
                f"Mañana seguimos con más pádel en vivo.\n"
                f"Todos los horarios y resultados acá.\n\n"
                f"{torneo['emoji']} {torneo['nombre']}\n"
                f"📍 {torneo['ciudad']} {torneo['bandera']}\n\n"
                f"¡Hasta mañana! 🇦🇷\n\n"
                f"{LINK_WEB}"
            )
            enviar_mensaje(msg)
        marcar_hecho_hoy("resumen_manana")

# ─────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────

def ciclo():
    print(f"\n{'='*50}")
    print(f"🤖 BOT TELEGRAM PADEL ARGENTINA — INICIADO")
    print(f"📅 {hora_argentina().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*50}\n")

    # Mensaje de inicio
    enviar_mensaje(
        "🤖 <b>Bot Padel Argentina activado</b>\n\n"
        "Voy a publicar todos los resultados de Premier Padel "
        "y los partidos de argentinos en torneos FIP en tiempo real.\n\n"
        f"{LINK_WEB}"
    )

    contador = 0

    while True:
        ahora_str = hora_argentina().strftime("%H:%M:%S")
        print(f"\n🔍 [{ahora_str}] Chequeando...")

        # Tareas programadas (orden del día, cierre de jornada)
        tareas_programadas()

        # Obtener noticias
        noticias = obtener_noticias_fip()

        # Premier Padel — todos los resultados
        procesar_noticias(noticias, TORNEOS_PREMIER, solo_argentinos=False)

        # FIP — solo argentinos
        procesar_noticias(noticias, TORNEOS_FIP, solo_argentinos=True)

        intervalo = INTERVALO_PREMIER if contador % 2 == 0 else INTERVALO_FIP
        print(f"✅ Ciclo {contador+1} — próximo en {intervalo} min")
        contador += 1
        time.sleep(intervalo * 60)

if __name__ == "__main__":
    ciclo()
