#!/bin/bash
# ─────────────────────────────────────────────
# FluxIT Crypto Bot — Setup de cliente nuevo
# Uso: bash setup_client.sh
# ─────────────────────────────────────────────

set -e
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔═══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     FluxIT Crypto Bot — Setup        ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════╝${NC}"
echo ""

# 1. Datos del cliente
read -p "Nombre del cliente: " CLIENT_NAME
read -p "Token del bot de Telegram (@BotFather): " TG_TOKEN
read -p "Chat ID de Telegram del cliente: " TG_CHAT_ID
read -p "Binance API Key (dejar vacío para solo paper trading): " BINANCE_KEY
read -p "Binance API Secret (dejar vacío para solo paper trading): " BINANCE_SECRET

echo ""
echo -e "${YELLOW}Resumen:${NC}"
echo "  Cliente:     $CLIENT_NAME"
echo "  Chat ID:     $TG_CHAT_ID"
echo "  Binance:     ${BINANCE_KEY:+configurado}${BINANCE_KEY:-no configurado (paper trading)}"
echo ""
read -p "¿Todo correcto? (s/n): " CONFIRM
if [[ "$CONFIRM" != "s" ]]; then echo "Cancelado."; exit 0; fi

# 2. Crear .env del cliente
ENV_FILE=".env.${CLIENT_NAME// /_}"
cat > "$ENV_FILE" << EOF
TELEGRAM_BOT_TOKEN=${TG_TOKEN}
TELEGRAM_CHAT_ID=${TG_CHAT_ID}
BINANCE_API_KEY=${BINANCE_KEY}
BINANCE_API_SECRET=${BINANCE_SECRET}
TRADING_MODE=paper
QUOTE_CURRENCY=USDT
ALERT_CHECK_INTERVAL=60
SIGNAL_SCAN_INTERVAL=300
WATCHLIST_DEFAULT=BTC,ETH,BNB,SOL,ADA,XRP,DOGE,AVAX,MATIC,LINK
EOF

echo ""
echo -e "${GREEN}✓ Archivo de configuración creado: ${ENV_FILE}${NC}"
echo ""
echo -e "${CYAN}Próximos pasos para Railway:${NC}"
echo "  1. Ve a railway.app → New Project → Deploy from GitHub"
echo "  2. Selecciona el repo fluxit-crypto-ai"
echo "  3. Añade un servicio PostgreSQL"
echo "  4. En Variables, añade las siguientes (copia desde ${ENV_FILE}):"
echo ""
cat "$ENV_FILE"
echo ""
echo "  5. Añade también: DATABASE_URL = \${{Postgres.DATABASE_URL}}"
echo ""
echo -e "${GREEN}¡Listo! El bot del cliente estará activo en ~5 minutos.${NC}"
echo ""
