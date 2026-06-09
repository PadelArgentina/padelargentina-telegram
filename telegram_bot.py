import os
import time
import json
import requests
import pytz
from datetime import datetime, timedelta

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ARGENTINA_TZ     = pytz.timezone("America/Argentina/Buenos_Aires")
INTERVALO_MIN    = 2
ARCHIVO_PUB      = "tg_pub.json"
ARCHIVO_ESTADO   = "tg_estado.json"
LINK_WEB         = "🌐 www.padelargentina.com.ar"

DIAS_EN = {
    0:"MONDAY",1:"TUESDAY",2:"WEDNESDAY",
    3:"THURSDAY",4:"FRIDAY",5:"SATURDAY",6:"SUNDAY"
}
MESES_EN = {
    1:"JANUARY",2:"FEBRUARY",3:"MARCH",4:"APRIL",
    5:"MAY",6:"JUNE",7:"JULY",8:"AUGUST",
    9:"SEPTEMBER",10:"OCTOBER",11:"NOVEMBER",12:"DECEMBER"
}

TORNEOS_PREMIER = [
    {
        "nombre":"Premier Padel P1 Valencia",
        "ciudad":"Valencia","bandera":"🇪🇸",
        "tz_local":"Europe/Madrid","emoji":"🏟️",
        "ss_id_men":35317,"ss_id_women":35318,
    },
]
TORNEOS_FIP = [
    {
        "nombre":"FIP Bronze Eslovenia",
        "ciudad":"Ljubljana","bandera":"🇸🇮","emoji":"🎾",
        "url_fip":"https://www.padelfip.com/es/events/fip-bronze-slovenia-2026/",
    },
]
ARGENTINOS = {
    "Agustin Tapia":"Agustín Tapia","Federico Chingotto":"Federico Chingotto",
    "Franco Stupaczuk":"Franco Stupaczuk","Leandro Augsburger":"Leandro Augsburger",
    "Martin Di Nenno":"Martín Di Nenno","Gonzalo Alfonso":"Gonzalo Alfonso",
    "Leonel Aguirre":"Leonel Aguirre","Juan Tello":"Juan Tello",
    "Maximiliano Arce":"Maxi Arce","Luciano Capra":"Luciano Capra",
    "Ignacio Piotto":"Ignacio Piotto","Juan Cruz Belluati":"Juan Cruz Belluati",
    "Juan Ignacio Rubini":"Juan I. Rubini","Federico Mourino":"Federico Mouriño",
    "Valentino Libaak":"Valentino Libaak","Alex Chozas":"Alex Chozas",
    "Carlos Gutierrez":"Carlos Gutiérrez","Maximiliano Sanchez Blasco":"Maxi Sánchez Blasco",
    "Agustin Torre":"Agustín Torre","Juan Cruz Forastello":"Juan Cruz Forastello",
    "Juan Ignacio De Pascual":"Juan I. De Pascual","Maximiliano Sanchez Aguero":"Maxi Sánchez Agüero",
    "Delfina Brea":"Delfina Brea","Ariana Sanchez":"Ariana Sánchez","Sofia Araujo":"Sofía Araújo",
}

def hora_arg():
    return datetime.now(ARGENTINA_TZ)

def es_argentino(n):
    return any(k.lower() in n.lower() for k in ARGENTINOS)

def nd(nombre):
    for k,v in ARGENTINOS.items():
        if k.lower() in nombre.lower():
            return f"🇦🇷 {v}"
    return nombre

def apellido(n):
    return n.strip().split()[-1] if n.strip() else n

def cargar_json(f):
    return json.load(open(f)) if os.path.exists(f) else {}

def guardar_json(f, d):
    json.dump(d, open(f,"w"), ensure_ascii=False, indent=2)

def cargar_pub():
    return set(cargar_json(ARCHIVO_PUB).get("ids",[]))

def guardar_pub(pid):
    d = cargar_json(ARCHIVO_PUB)
    ids = set(d.get("ids",[])); ids.add(pid)
    guardar_json(ARCHIVO_PUB,{"ids":list(ids)})

def ya_hoy(t):
    return cargar_json(ARCHIVO_ESTADO).get(t) == hora_arg().strftime("%Y-%m-%d")

def marcar_hoy(t):
    e = cargar_json(ARCHIVO_ESTADO)
    e[t] = hora_arg().strftime("%Y-%m-%d")
    guardar_json(ARCHIVO_ESTADO, e)

# ── PDF ──────────────────────────────────────

def url_pdf(fecha):
    dia=DIAS_EN[fecha.weekday()]; mes=MESES_EN[fecha.month]
    dd=fecha.day; anio=fecha.year
    v2=f"https://www.padelfip.com/wp-content/uploads/2025/12/ORDER-OF-PLAY-{dia}-{dd}-{mes}-{anio}-2.pdf"
    v1=f"https://www.padelfip.com/wp-content/uploads/2025/12/ORDER-OF-PLAY-{dia}-{dd}-{mes}-{anio}.pdf"
    return v2, v1

def descargar_pdf(fecha):
    v2, v1 = url_pdf(fecha)
    for url in [v2, v1]:
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and b'%PDF' in r.content[:10]:
                return r.content, url
        except: pass
    return None, None

# ── TELEGRAM ─────────────────────────────────

def enviar(texto):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":texto,"parse_mode":"HTML"},
            timeout=15)
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} TG: {texto[:60]}...")
        return ok
    except Exception as e:
        print(f"❌ TG: {e}"); return False

def enviar_pdf(pdf_bytes, nombre_archivo, caption):
    """Envía el PDF como documento adjunto al canal"""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
            files={"document": (nombre_archivo, pdf_bytes, "application/pdf")},
            timeout=30)
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} PDF enviado: {nombre_archivo}")
        return ok
    except Exception as e:
        print(f"❌ PDF error: {e}"); return False

# ── SOFASCORE ────────────────────────────────

SS_H = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}

def ss_get(path):
    try:
        r = requests.get(f"https://api.sofascore.com/api/v1{path}",
                         headers=SS_H, timeout=15)
        if r.status_code == 200: return r.json()
    except Exception as e: print(f"[SS] {e}")
    return None

def fin_hoy(ss_id):
    data = ss_get(f"/unique-tournament/{ss_id}/events/last/0")
    if not data: return []
    hoy = hora_arg().date()
    return [p for p in data.get("events",[])
            if p.get("status",{}).get("type")=="finished"
            and datetime.fromtimestamp(p.get("startTimestamp",0),
                                        tz=ARGENTINA_TZ).date()==hoy]

def prox_hoy(ss_id):
    data = ss_get(f"/unique-tournament/{ss_id}/events/next/0")
    if not data: return []
    hoy = hora_arg().date()
    return [p for p in data.get("events",[])
            if datetime.fromtimestamp(p.get("startTimestamp",0),
                                       tz=ARGENTINA_TZ).date()==hoy]

def parsear(p):
    home=p.get("homeTeam",{}); away=p.get("awayTeam",{})
    hs=p.get("homeScore",{}); as_=p.get("awayScore",{})
    j1,j2=home.get("name",""),home.get("subTeamName","") or ""
    j3,j4=away.get("name",""),away.get("subTeamName","") or ""
    sets=[]
    for i in range(1,6):
        sh,sa=hs.get(f"period{i}"),as_.get(f"period{i}")
        if sh is not None and sa is not None: sets.append(f"{sh}-{sa}")
    marcador="/".join(sets) if sets else "—"
    w=p.get("winnerCode",0)
    gan,per=([j1,j2],[j3,j4]) if w==1 else ([j3,j4],[j1,j2])
    tm=p.get("time",{}).get("played")
    return {"id":str(p.get("id","")),"ganadores":gan,"perdedores":per,
            "marcador":marcador,"ronda":p.get("roundInfo",{}).get("name",""),
            "tiempo":f"{tm//60}h {tm%60}min" if tm else None}

# ── MENSAJES ─────────────────────────────────

def msg_resultado_premier(torneo, gan, per, marcador, tiempo, ronda):
    arg_gana = any(es_argentino(j) for j in gan)
    cab = "🇦🇷⚡ <b>VICTORIA ARGENTINA</b>" if arg_gana else "🎾 <b>RESULTADO</b>"
    lineas = [cab,
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b> | {ronda.upper()}",
        f"📍 {torneo['ciudad']} {torneo['bandera']}","",
        f"✅ {nd(gan[0])} / {nd(gan[1])}",
        f"❌ {nd(per[0])} / {nd(per[1])}",
        f"🎯 {marcador}"]
    if tiempo: lineas.append(f"⏱️ {tiempo}")
    lineas += ["", LINK_WEB]
    return "\n".join(lineas)

def msg_resultado_fip(torneo, gan, per, marcador, ronda, arg_gana):
    lugar = torneo["nombre"].split()[-1]
    cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA:</b>" if arg_gana else f"🎾🇦🇷 <b>Derrota argentina en el FIP de {lugar}</b>"
    return "\n".join([cab,
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b> | {ronda.upper()}",
        f"📍 {torneo['ciudad']} {torneo['bandera']}","",
        f"✅ {nd(gan[0])} / {nd(gan[1])}",
        f"❌ {nd(per[0])} / {nd(per[1])}",
        f"🎯 {marcador}","", LINK_WEB])

def caption_pdf(torneo, manana):
    dia_en = DIAS_EN[manana.weekday()].capitalize()
    fecha_str = manana.strftime("%d/%m/%Y")
    return (
        f"🗓️ <b>ORDEN DE JUEGO — {dia_en} {fecha_str}</b>\n"
        f"{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>\n"
        f"📍 {torneo['ciudad']} {torneo['bandera']}\n\n"
        f"📋 Todos los partidos, horarios y pistas del día.\n\n"
        f"{LINK_WEB}"
    )

# ── TAREAS ───────────────────────────────────

def tarea_orden_dia():
    for torneo in TORNEOS_PREMIER:
        tid = f"orden_dia_{torneo['nombre']}"
        if ya_hoy(tid): continue
        if prox_hoy(torneo["ss_id_men"]): continue  # aún hay partidos hoy
        manana = (hora_arg() + timedelta(days=1)).date()
        pdf_bytes, pdf_url = descargar_pdf(manana)
        if not pdf_bytes:
            print(f"[PDF] No encontrado para {manana}"); continue
        dia_en    = DIAS_EN[manana.weekday()]
        nombre_archivo = f"ORDER-OF-PLAY-{dia_en}-{manana.day}-{MESES_EN[manana.month]}-{manana.year}.pdf"
        caption = caption_pdf(torneo, manana)
        if enviar_pdf(pdf_bytes, nombre_archivo, caption):
            marcar_hoy(tid)
            time.sleep(3)

def monitorear_premier():
    pub = cargar_pub()
    for torneo in TORNEOS_PREMIER:
        for ss_id in [torneo["ss_id_men"], torneo["ss_id_women"]]:
            for p in fin_hoy(ss_id):
                d   = parsear(p)
                pid = f"premier_{d['id']}"
                if pid in pub: continue
                msg = msg_resultado_premier(torneo, d["ganadores"], d["perdedores"],
                                            d["marcador"], d["tiempo"], d["ronda"])
                if enviar(msg):
                    guardar_pub(pid); time.sleep(4)

def monitorear_fip():
    from bs4 import BeautifulSoup
    pub = cargar_pub()
    try:
        r    = requests.get("https://www.padelfip.com/es/noticias/",
                            headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(r.text,"html.parser")
        vistos = set()
        for a in soup.find_all("a", href=True):
            href=a.get("href",""); texto=a.get_text(strip=True)
            if "/2026/" not in href or len(texto)<25: continue
            if href in vistos or href in pub: continue
            vistos.add(href)
            tiene_arg = any(k.lower() in texto.lower() for k in ARGENTINOS)
            es_result = any(kw in texto.lower() for kw in
                            ["vence","gana","triunfa","campeón","derrota","elimina","avanza"])
            if not tiene_arg or not es_result: continue
            torneo   = TORNEOS_FIP[0]
            lugar    = torneo["nombre"].split()[-1]
            arg_gana = any(kw in texto.lower() for kw in
                           ["vence","gana","triunfa","campeón","avanza"])
            cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA:</b>" if arg_gana else f"🎾🇦🇷 <b>Derrota argentina en el FIP de {lugar}</b>"
            msg = f"{cab}\n\n{torneo['emoji']} <b>{torneo['nombre'].upper()}</b>\n📍 {torneo['ciudad']} {torneo['bandera']}\n\n📋 {texto}\n\n{LINK_WEB}"
            if enviar(msg):
                guardar_pub(href); time.sleep(3)
    except Exception as e:
        print(f"[FIP TG] {e}")

# ── LOOP ─────────────────────────────────────

def ciclo():
    print(f"\n{'='*50}")
    print(f"🤖 BOT TELEGRAM PADEL ARGENTINA — {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}\n")
    enviar("🤖 <b>Bot Padel Argentina activo ✅</b>\n\n"
           "📋 Cuadros al inicio del torneo\n"
           "🗓️ PDF orden del día al terminar cada jornada\n"
           "🎾 Resultados en tiempo real\n"
           "🇦🇷 Victoria/derrota argentina\n\n"
           f"{LINK_WEB}")
    contador = 0
    while True:
        print(f"\n🔍 [{hora_arg().strftime('%H:%M:%S')}] Ciclo {contador+1}")
        tarea_orden_dia()
        monitorear_premier()
        monitorear_fip()
        print(f"✅ Próximo en {INTERVALO_MIN} min")
        contador += 1
        time.sleep(INTERVALO_MIN * 60)

if __name__ == "__main__":
    ciclo()
