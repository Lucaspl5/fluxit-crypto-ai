# FluxIT Crypto Bot — Guía de Instalación

## Qué vas a tener al final

Un bot de trading automático en Telegram que:
- Opera con 10.000 USDT virtuales (paper trading)
- Gestiona Stop Loss y Take Profit automáticamente
- Te envía señales de mercado cada 5 minutos
- Tiene un dashboard web en tiempo real

Todo funcionando 24/7 en la nube, gratis.

---

## Lo que necesitas (todo gratis)

- Cuenta en [GitHub](https://github.com) — para subir el código
- Cuenta en [Railway](https://railway.app) — para el servidor
- Un bot de Telegram creado con [@BotFather](https://t.me/BotFather)
- Tu Chat ID de Telegram (lo obtienes con [@userinfobot](https://t.me/userinfobot))

---

## Paso 1 — Crear tu bot en Telegram

1. Abre Telegram y busca **@BotFather**
2. Escribe `/newbot`
3. Ponle un nombre (ej: "Mi Crypto Bot")
4. Ponle un username que termine en `bot` (ej: `micryptobot`)
5. BotFather te da un **token** — guárdalo, tiene este formato:
   ```
   1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```

## Paso 2 — Obtener tu Chat ID

1. Abre Telegram y busca **@userinfobot**
2. Escribe `/start`
3. Te responde con tu **ID** — guárdalo, es un número como `1196127927`

## Paso 3 — Subir el código a GitHub

1. Crea cuenta en [github.com](https://github.com)
2. Crea un repositorio nuevo llamado `fluxit-crypto-bot` (privado)
3. Sube todos los archivos de esta carpeta al repositorio

   Si no sabes usar Git, la forma más fácil:
   - En GitHub, haz clic en **"uploading an existing file"**
   - Arrastra todos los archivos de esta carpeta
   - Haz clic en **"Commit changes"**

## Paso 4 — Crear el proyecto en Railway

1. Entra en [railway.app](https://railway.app) y crea cuenta (gratis)
2. Haz clic en **"New Project"**
3. Selecciona **"Deploy from GitHub repo"**
4. Conecta tu cuenta de GitHub y selecciona el repositorio `fluxit-crypto-bot`
5. Railway empieza a construir el proyecto

## Paso 5 — Añadir la base de datos

1. Dentro del proyecto en Railway, haz clic en **"+ New"**
2. Selecciona **"Database" → "PostgreSQL"**
3. Railway crea la base de datos automáticamente

## Paso 6 — Configurar las variables de entorno

1. Haz clic en tu servicio principal (el del código)
2. Ve a la pestaña **"Variables"**
3. Añade estas variables una por una:

| Variable | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | El token que te dio BotFather |
| `TELEGRAM_CHAT_ID` | Tu Chat ID numérico |
| `TRADING_MODE` | `paper` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |

4. Haz clic en **"Deploy"**

## Paso 7 — Probar el bot

1. Espera 2-3 minutos a que Railway termine el despliegue
2. Abre Telegram y busca tu bot por su username
3. Escribe `/start`
4. ¡Deberías ver el menú del bot!

Prueba estos comandos:
- `/menu` — Dashboard principal con botones
- `/balance` — Ver tu saldo virtual (10.000 USDT)
- `/comprar BTC 500` — Comprar Bitcoin con 500 USDT virtuales
- `/portfolio` — Ver tus posiciones
- `/senales` — Ver señales del mercado

## Paso 8 — Ver el dashboard web

1. En Railway, ve a tu servicio → **Settings → Networking → Generate Domain**
2. Railway te da una URL pública
3. Entra en esa URL — verás la landing page
4. Entra en `tu-url/dashboard` — verás el dashboard en tiempo real

---

## Comandos disponibles

| Comando | Descripción |
|---|---|
| `/menu` | Dashboard principal |
| `/precio BTC` | Precio actual y stats 24h |
| `/analisis BTC` | Análisis técnico completo |
| `/senales` | Señales de todos los pares |
| `/comprar BTC 500` | Comprar con 500 USDT |
| `/comprar BTC 500 sl=40000 tp=60000` | Comprar con Stop Loss y Take Profit |
| `/vender BTC 0.005` | Vender una cantidad |
| `/portfolio` | Ver posiciones abiertas |
| `/balance` | Ver saldo disponible |
| `/posiciones` | Ver órdenes SL/TP activas |
| `/proteger` | Aplicar SL/TP automático a todo |
| `/alerta BTC 50000 above` | Alerta cuando BTC suba de 50.000 |
| `/alertas` | Ver alertas activas |
| `/watchlist` | Ver lista de seguimiento |

---

## Preguntas frecuentes

**¿Puedo perder dinero real?**
No. El modo `paper` usa dinero virtual. Para operar con dinero real necesitas configurar las API keys de Binance (no incluido en este plan).

**¿Cuánto cuesta mantenerlo?**
Railway tiene un plan gratuito con 500 horas al mes. Para uso continuo 24/7 el plan de pago cuesta $5/mes.

**¿Funciona en el móvil?**
Sí, el bot de Telegram funciona en cualquier dispositivo. El dashboard web también es responsive.

**¿Necesito saber programar?**
No. Con esta guía es suficiente. Si tienes dudas, escríbeme: [@lucaspariente](https://t.me/lucaspariente)

---

## Soporte

Si tienes algún problema durante la instalación, escríbeme por Telegram:
**@lucaspariente**

Incluyo 7 días de soporte por email para resolver cualquier duda.
