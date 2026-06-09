# 🎾 Bot Telegram — Padel Argentina

Canal: @PadelArgentina
Bot: @PadelArgentina_bot

---

## QUÉ PUBLICA

### Premier Padel — todos los partidos
- ☀️ 7hs ARG: orden del día con horarios por pista
- 📊 Durante el día: actualización tras cada set
- ✅ Resultado final + próxima ronda + próximos rivales
- 🇦🇷 VICTORIA ARGENTINA cuando gana un argentino
- 🌙 22hs ARG: cierre + anticipo de mañana

### FIP — solo argentinos
- 🎾🇦🇷 VICTORIA ARGENTINA: cuando ganan
- 🎾🇦🇷 Derrota argentina en el FIP de X cuando pierden

### Inicio de torneo — cuadros completos
- Qualifying masculino y femenino
- Cuadro principal masculino y femenino

### Horarios
- Siempre en hora argentina 🇦🇷⏰
- Con hora local entre paréntesis y bandera del país

---

## VARIABLES DE ENTORNO EN RAILWAY

TELEGRAM_TOKEN   = (token del BotFather)
TELEGRAM_CHAT_ID = (chat id del canal, empieza con -100)

---

## DEPLOY EN RAILWAY

1. Subir estos 3 archivos a un nuevo repo GitHub: telegram-bot
2. Nuevo proyecto en Railway → GitHub repo
3. Agregar las 2 variables de entorno
4. Deploy

---

## ACTUALIZAR TORNEOS

Editar telegram_bot.py sección TORNEOS_PREMIER y TORNEOS_FIP
con las URLs de los torneos activos cada semana.
