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
DIAG            = True   # imprime diagnóstico en el log

DIAS_EN  = {0:"MONDAY",1:"TUESDAY",2:"WEDNESDAY",3:"THURSDAY",4:"FRIDAY",5:"SATURDAY",6:"SUNDAY"}
MESES_EN = {1:"JANUARY",2:"FEBRUARY",3:"MARCH",4:"APRIL",5:"MAY",6:"JUNE",7:"JULY",8:"AUGUST",9:"SEPTEMBER",10:"OCTOBER",11:"NOVEMBER",12:"DECEMBER"}

BANDERAS = {
    "spain":"🇪🇸","valencia":"🇪🇸","lanzarote":"🇪🇸","badajoz":"🇪🇸","malaga":"🇪🇸","valladolid":"🇪🇸",
    "china":"🇨🇳","shanghai":"🇨🇳","italy":"🇮🇹","palermo":"🇮🇹","slovenia":"🇸🇮","ljubljana":"🇸🇮",
    "france":"🇫🇷","bordeaux":"🇫🇷","portugal":"🇵🇹","paredes":"🇵🇹","germany":"🇩🇪","poland":"🇵🇱",
}

CIUDADES = {
    "valencia":"Valencia","shanghai":"Shanghai","palermo":"Palermo","lanzarote":"Lanzarote",
    "slovenia":"Eslovenia","ljubljana":"Eslovenia","badajoz":"Badajoz","portugal":"Portugal",
    "valladolid":"Valladolid","bordeaux":"Bordeaux","malaga":"Málaga","paredes":"Portugal",
}

RONDAS = {
    "final":"FINAL","semfinal":"SEMIFINAL","semi-final":"SEMIFINAL","1/2":"SEMIFINAL",
    "quarterfinal":"CUARTOS DE FINAL","quarter":"CUARTOS DE FINAL","1/4":"CUARTOS DE FINAL",
    "round of 16":"OCTAVOS","r16":"OCTAVOS","1/8":"OCTAVOS",
    "round of 32":"R32","r32":"R32","1/16":"R32","round of 64":"R64","r64":"R64",
    "qualifying":"QUALY","qualification":"QUALY","qualy":"QUALY",
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

def ciudad_de(nombre):
    t = nombre.lower()
    for k, v in CIUDADES.items():
        if k in t:
            return v
    return nombre.split()[-1] if nombre.split() else "el torneo"

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

def detectar_ronda(texto):
    t = texto.lower()
    for k, v in RONDAS.items():
        if k in t:
            return v
    return ""

# ══════════════════════════════════════════════
#  LECTOR WEB EN CASCADA
# ══════════════════════════════════════════════

def leer_url(url, espera_pdf=False, espera_json=False):
    intentos = [
        ("directo", url),
        ("codetabs", f"https://api.codetabs.com/v1/proxy/?quest={url}"),
        ("allorigins", f"https://api.allorigins.win/raw?url={url}"),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for nombre, u in intentos:
        try:
            r = requests.get(u, headers=headers, timeout=25)
            if r.status_code == 200 and len(r.content) > 50:
                if espera_pdf and b"%PDF" not in r.content[:1024]:
                    continue
                if espera_json:
                    try:
                        return r.json()
                    except Exception:
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
    for t in torneos:
        print(f"   📌 {t['nombre'][:40]} -> {t['url'][-40:]}")
    return torneos

# ══════════════════════════════════════════════
#  EXTRAER ID MATCHSCORERLIVE Y DÍA DEL TORNEO
# ══════════════════════════════════════════════

def datos_torneo(torneo):
    """
    Lee la página del torneo y saca:
    - id matchscorerlive (de FIP-AÑO-ID)
    - year, totalday
    Devuelve dict o None.
    """
    html = leer_url(torneo["url"])
    if not html:
        return None

    # Buscar patrón FIP-2026-XXXX
    print(f"   🔬 HTML largo={len(html)} primeros chars={repr(html[:200])}")
    m = re.search(r"FIP-(\d{4})-(\d+)", html)
    if not m:
        if DIAG:
            print(f"   🔬 No se encontró id matchscorerlive en {torneo['nombre'][:30]}")
        return None
    year = m.group(1)
    tid  = m.group(2)

    # Buscar totalday (cantidad de días del torneo)
    mt = re.search(r"totalday['\"]?\s*[:=]\s*['\"]?(\d+)", html)
    totalday = mt.group(1) if mt else "9"

    if DIAG:
        print(f"   🔬 {torneo['nombre'][:25]} -> id={tid} year={year} totalday={totalday}")
    return {"id": tid, "year": year, "totalday": totalday}

def dia_torneo_hoy(html_o_datos):
    """Calcula qué número de día del torneo es hoy. Aproximación: usa el día actual."""
    # Estrategia simple: probar varios días y quedarse con el que tenga partidos terminados hoy
    return None

# ══════════════════════════════════════════════
#  LEER RESULTADOS DEL DÍA VÍA ENDPOINT FIP
# ══════════════════════════════════════════════

def resultados_del_dia(torneo, datos):
    """
    Consulta el endpoint get-result-data.php para cada día posible
    y lee el widget matchscorerlive con el detalle.
    Devuelve lista de partidos terminados con argentinos.
    """
    year = datos["year"]
    tid = datos["id"]
    totalday = int(datos["totalday"])

    partidos_arg = []

    # Probar todos los días del torneo, quedarnos con los que tienen partidos terminados
    for day in range(1, totalday + 1):
        endpoint = (f"https://www.padelfip.com/wp-content/themes/padelfiptheme/"
                    f"template-parts/event/endpoint/get-result-data.php"
                    f"?year={year}&id={tid}&day={day}&totalday={totalday}&widget=resultsbyday")
        data = leer_url(endpoint, espera_json=True)
        if not data or not data.get("success"):
            continue
        # ¿hay partidos terminados ese día?
        ended = [m for m in data.get("dayEndStatus", []) if m.get("matchEnded") == 1]
        if not ended:
            continue

        oop_url = data.get("oopUrl", "")
        if not oop_url:
            continue

        # Leer el widget matchscorerlive con el detalle
        widget_html = leer_url(oop_url)
        if not widget_html:
            continue

        if DIAG:
            print(f"   🔬 Widget día {day}: {len(widget_html)} chars")
            # imprimir una muestra para ajustar el parser
            muestra = re.sub(r"\s+", " ", widget_html)[:400]
            print(f"   🔬 Muestra: {muestra}")

        partidos = parsear_widget(widget_html, torneo, day)
        partidos_arg.extend(partidos)

    return partidos_arg

def parsear_widget(html, torneo, day):
    """
    Parsea el widget matchscorerlive. Busca partidos con argentinos.
    El widget tiene los jugadores con nacionalidad y el marcador.
    """
    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text("\n", strip=True)

    partidos = []
    # Detectar bloques con "ARG" o "Argentina" y marcador
    if "arg" not in texto.lower() and "argentina" not in texto.lower():
        return partidos

    # Buscar imágenes de bandera argentina en el widget
    tiene_arg = False
    for img in soup.find_all("img"):
        src = (img.get("src", "") + img.get("alt", "")).lower()
        if "arg" in src or "argentina" in src:
            tiene_arg = True
            break

    if tiene_arg or "argentina" in texto.lower():
        # Marcar para diagnóstico — el parser fino se ajusta con el log
        partidos.append({
            "torneo": torneo,
            "day": day,
            "texto_crudo": texto[:500],
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
        datos = datos_torneo(torneo)
        if not datos:
            continue
        try:
            partidos = resultados_del_dia(torneo, datos)
        except Exception as e:
            print(f"   ⚠️ {e}")
            continue

        if DIAG and partidos:
            print(f"   🔬 {len(partidos)} bloques con argentinos detectados")

# ══════════════════════════════════════════════
#  LOOP
# ══════════════════════════════════════════════

def ciclo():
    print("="*50)
    print("🤖 BOT TELEGRAM PADEL ARGENTINA — v10 (matchscorerlive)")
    print(f"📅 {hora_arg().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)

    tg_enviar(
        "🤖 <b>Bot Padel Argentina v10 ✅</b>\n\n"
        "Nueva fuente: matchscorerlive (resultados limpios)\n"
        "🎾 Resultados finales de argentinos\n"
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
