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

DIAS_EN = {0:"MONDAY",1:"TUESDAY",2:"WEDNESDAY",3:"THURSDAY",
           4:"FRIDAY",5:"SATURDAY",6:"SUNDAY"}
MESES_EN = {1:"JANUARY",2:"FEBRUARY",3:"MARCH",4:"APRIL",5:"MAY",6:"JUNE",
            7:"JULY",8:"AUGUST",9:"SEPTEMBER",10:"OCTOBER",11:"NOVEMBER",12:"DECEMBER"}

# ── Lista de apellidos argentinos (estable, cambia poco) ──
ARGENTINOS = [
    "tapia","chingotto","stupaczuk","augsburger","di nenno","dinenno",
    "alfonso","aguirre","tello","arce","capra","piotto","belluati",
    "rubini","mourino","mouriño","libaak","chozas","gutierrez","gutiérrez",
    "sanchez blasco","sánchez blasco","torre","forastello","de pascual",
    "sanchez aguero","sánchez agüero","brea","sanchez","sánchez","araujo",
    "araújo","valenzuela","pilcher","maldonado","puppo","lopez","lópez",
    "garrido","bergamini","cardona","gil","alonso","ruiz","sanz",
]

# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════

def hora_arg():
    return datetime.now(ARGENTINA_TZ)

def es_argentino(texto):
    t = texto.lower()
    return any(a in t for a in ARGENTINOS)

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

# ══════════════════════════════════════════════
#  LECTOR WEB CON 3 FUENTES EN CASCADA
#  (esquiva el bloqueo de Railway a padelfip.com)
# ══════════════════════════════════════════════

def leer_url(url, espera_pdf=False):
    """
    Intenta leer una URL probando 3 vías en orden:
    1. Directo
    2. Proxy CodeTabs
    3. Proxy AllOrigins
    Devuelve el contenido (bytes si PDF, texto si HTML) o None.
    """
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
                print(f"   ✓ leído vía {nombre}")
                return r.content if espera_pdf else r.text
        except Exception as e:
            print(f"   ✗ {nombre} falló: {str(e)[:60]}")
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
        print(f"{'✅' if ok else '❌'} TG msg: {texto[:50]}...")
        if not ok:
            print(f"   detalle: {r.text[:120]}")
        return ok
    except Exception as e:
        print(f"❌ TG error: {e}")
        return False

def tg_enviar_pdf(pdf_bytes, nombre_archivo, caption):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
            files={"document": (nombre_archivo, pdf_bytes, "application/pdf")},
            timeout=40)
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} TG pdf: {nombre_archivo}")
        return ok
    except Exception as e:
        print(f"❌ TG pdf error: {e}")
        return False

# ══════════════════════════════════════════════
#  DETECCIÓN AUTOMÁTICA DE TORNEOS ACTIVOS
# ══════════════════════════════════════════════

def detectar_torneos_activos():
    """
    Lee la home de FIP y devuelve lista de torneos activos:
    [{nombre, ciudad, pais, url_evento, bandera}]
    """
    html = leer_url("https://www.padelfip.com/es/")
    if not html:
        print("⚠️ No se pudo leer la home de FIP")
        return []

    soup = BeautifulSoup(html, "html.parser")
    torneos = []
    vistos = set()

    # Buscar enlaces a eventos
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/events/" in href and href not in vistos:
            vistos.add(href)
            nombre = a.get_text(strip=True)
            if len(nombre) < 4:
                # buscar texto en el contenedor padre
                cont = a.find_parent()
                if cont:
                    nombre = cont.get_text(" ", strip=True)[:60]
            if not href.startswith("http"):
                href = "https://www.padelfip.com" + href
            torneos.append({
                "nombre": nombre or "Torneo FIP",
                "url_evento": href,
            })

    print(f"🔎 {len(torneos)} torneos detectados en la home")
    return torneos

BANDERAS = {
    "spain":"🇪🇸","espana":"🇪🇸","españa":"🇪🇸","valencia":"🇪🇸","lanzarote":"🇪🇸","badajoz":"🇪🇸",
    "china":"🇨🇳","shanghai":"🇨🇳",
    "italy":"🇮🇹","italia":"🇮🇹","palermo":"🇮🇹",
    "slovenia":"🇸🇮","eslovenia":"🇸🇮","ljubljana":"🇸🇮",
    "france":"🇫🇷","francia":"🇫🇷",
    "portugal":"🇵🇹","germany":"🇩🇪","poland":"🇵🇱",
    "argentina":"🇦🇷","chile":"🇨🇱","mexico":"🇲🇽",
}

def bandera_de(texto):
    t = texto.lower()
    for k, v in BANDERAS.items():
        if k in t:
            return v
    return "🌍"

# ══════════════════════════════════════════════
#  LECTURA DE RESULTADOS DE UN TORNEO
# ══════════════════════════════════════════════

def resultados_torneo(torneo):
    """
    Lee la página de un torneo y extrae resultados finalizados
    donde participan argentinos.
    Devuelve lista de dicts con los datos del partido.
    """
    html = leer_url(torneo["url_evento"])
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text("\n", strip=True)
    lineas = [l for l in texto.split("\n") if l.strip()]

    resultados = []
    bandera = bandera_de(torneo["nombre"] + " " + torneo["url_evento"])

    # Buscar bloques con scores (formato tipo "6-4 6-2")
    patron_score = re.compile(r"\b[0-7]\s*[-/]\s*[0-7]\b")
    for i, linea in enumerate(lineas):
        bloque = " ".join(lineas[max(0,i-3):i+3])
        if patron_score.search(linea) and es_argentino(bloque):
            sig = f"{torneo['nombre']}_{i}_{linea[:40]}"
            resultados.append({
                "torneo": torneo["nombre"],
                "bandera": bandera,
                "detalle": bloque[:240],
                "id": sig,
            })

    return resultados

# ══════════════════════════════════════════════
#  ORDEN DEL DÍA (PDF) — solo Valencia / Premier
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
    pdf_url = url_pdf(manana)
    pdf_bytes = leer_url(pdf_url, espera_pdf=True)
    if not pdf_bytes:
        print(f"[PDF] No disponible aún para {manana}")
        return
    dia_en = DIAS_EN[manana.weekday()].capitalize()
    nombre_archivo = f"orden-de-juego-{manana.day}-{MESES_EN[manana.month].lower()}.pdf"
    caption = (
        f"🗓️ <b>ORDEN DE JUEGO — {dia_en} {manana.strftime('%d/%m/%Y')}</b>\n"
        f"🏟️ <b>PREMIER PADEL P1 VALENCIA</b> 🇪🇸\n\n"
        f"📋 Todos los partidos, horarios y pistas.\n\n"
        f"{LINK_WEB}"
    )
    if tg_enviar_pdf(pdf_bytes, nombre_archivo, caption):
        marcar_hoy(tid)

# ══════════════════════════════════════════════
#  MONITOREO PRINCIPAL
# ══════════════════════════════════════════════

def monitorear_resultados():
    pub = cargar_torneos = cargar_pub()
    torneos = detectar_torneos_activos()
    if not torneos:
        return

    for torneo in torneos:
        print(f"📂 Revisando: {torneo['nombre'][:40]}")
        for res in resultados_torneo(torneo):
            if res["id"] in pub:
                continue
            es_premier = any(k in res["torneo"].lower() for k in
                             ["premier","p1","p2","major","valencia"])
            if es_premier:
                cab = "🇦🇷⚡ <b>VICTORIA ARGENTINA</b>" if es_argentino(res["detalle"]) else "🎾 <b>RESULTADO</b>"
            else:
                lugar = res["torneo"].split()[-1] if res["torneo"].split() else ""
                gana = any(kw in res["detalle"].lower() for kw in
                           ["gana","vence","triunfa","avanza","campeón","campeon"])
                cab = "🎾🇦🇷 <b>VICTORIA ARGENTINA:</b>" if gana else f"🎾🇦🇷 <b>Derrota argentina en el FIP de {lugar}</b>"

            msg = (
                f"{cab}\n\n"
                f"{res['bandera']} <b>{res['torneo'].upper()}</b>\n\n"
                f"📋 {res['detalle']}\n\n"
                f"{LINK_WEB}"
            )
            if tg_enviar(msg):
                guardar_pub(res["id"])
                time.sleep(3)

# ══════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════

def ciclo():
    print("="*50)
    print(f"🤖 BOT TELEGRAM PADEL ARGENTINA")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)

    tg_enviar(
        "🤖 <b>Bot Padel Argentina activo ✅</b>\n\n"
        "Detección automática de torneos FIP + Premier.\n"
        "📋 Orden del día en PDF\n"
        "🎾 Resultados de argentinos en tiempo real\n"
        "🇦🇷 Victoria / derrota argentina\n\n"
        f"{LINK_WEB}"
    )

    contador = 0
    while True:
        print(f"\n🔍 [{hora_arg().strftime('%H:%M:%S')}] Ciclo {contador+1}")
        try:
            tarea_orden_dia()
            monitorear_resultados()
        except Exception as e:
            print(f"⚠️ Error en ciclo: {e}")
        print(f"✅ Próximo en {INTERVALO_MIN} min")
        contador += 1
        time.sleep(INTERVALO_MIN * 60)

if __name__ == "__main__":
    ciclo()
