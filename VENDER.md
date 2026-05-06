# FluxIT Crypto Bot — Guía para empezar a vender

## 1. Obtener la URL pública de Railway

1. Entra en [railway.app](https://railway.app)
2. Abre el proyecto `fluxit-crypto-ai`
3. Haz clic en el servicio `fluxit-crypto-ai`
4. Ve a **Settings → Networking → Generate Domain**
5. Railway te genera una URL tipo `fluxit-crypto-ai-production.up.railway.app`

Con esa URL tienes:
- `/` → Landing page para vender
- `/dashboard` → Dashboard en tiempo real del cliente
- `/health` → Health check

---

## 2. Personalizar la landing page

Abre `web/landing.html` y cambia estas líneas:

```html
<!-- Línea ~35: nombre del bot de Telegram -->
<a href="https://t.me/fluxit_crypto_bot" class="nav-cta">

<!-- Línea ~70: mismo enlace en el botón hero -->
<a href="https://t.me/fluxit_crypto_bot" class="btn-primary">

<!-- Línea ~230: enlace demo -->
<a href="https://t.me/fluxit_crypto_bot" class="tg-btn">
```

Sustituye `fluxit_crypto_bot` por el username real de tu bot.

---

## 3. Configurar Gumroad para cobrar

1. Ve a [gumroad.com](https://gumroad.com) y crea cuenta gratuita
2. Crea 3 productos:

| Producto | Precio | Descripción |
|---|---|---|
| FluxIT Crypto Starter | €49 | Código + instrucciones |
| FluxIT Crypto Pro | €149 | Setup completo en 24h |
| FluxIT Crypto VIP | €249 | Setup + 3 meses soporte |

3. En cada producto, el link de compra redirige a tu Telegram o WhatsApp
4. Copia los links de Gumroad y pégalos en `web/landing.html` en los botones de precios

---

## 4. Desplegar un cliente nuevo (5 minutos)

Cuando alguien pague, ejecuta en tu terminal:

```bash
cd /ruta/a/fluxit-crypto-ai
bash setup_client.sh
```

El script te pide:
- Nombre del cliente
- Token del bot (el cliente lo crea en @BotFather)
- Chat ID del cliente (lo obtiene con @userinfobot)
- API keys de Binance (opcional, solo para live trading)

Luego:
1. El cliente crea su cuenta en [railway.app](https://railway.app) (gratis)
2. Conecta su GitHub con el repo (o tú lo haces por él)
3. Añade PostgreSQL al proyecto
4. Copia las variables que genera el script en Railway → Variables
5. Añade `DATABASE_URL = ${{Postgres.DATABASE_URL}}`
6. Railway despliega solo en ~3 minutos

---

## 5. Lo que le das al cliente

- Bot de Telegram funcionando 24/7
- URL con dashboard en tiempo real
- Paper trading con 10.000 USDT virtuales
- SL/TP automático
- Señales cada 5 minutos
- Alertas de precio

---

## 6. Checklist antes de vender

- [ ] Obtener URL pública de Railway
- [ ] Cambiar links del bot en `landing.html`
- [ ] Crear cuenta en Gumroad y los 3 productos
- [ ] Pegar links de Gumroad en `landing.html`
- [ ] Hacer commit y push de los cambios
- [ ] Probar la landing en el navegador
- [ ] Probar el dashboard en `/dashboard`
- [ ] Grabar un vídeo corto del bot en acción (30-60 segundos)
