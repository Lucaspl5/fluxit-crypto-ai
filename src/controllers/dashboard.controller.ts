import { Controller, Get, Res } from '@nestjs/common';
import { Response } from 'express';
import { PrismaService } from '../prisma/prisma.service';
import { ExchangeService } from '../services/exchange.service';

@Controller('dashboard')
export class DashboardController {
  constructor(
    private prisma: PrismaService,
    private exchange: ExchangeService,
  ) {}

  @Get('data')
  async getData() {
    const [signals, orders, performances, account, configs] = await Promise.all([
      this.prisma.signal.findMany({ orderBy: { timestamp: 'desc' }, take: 20 }),
      this.prisma.order.findMany({ orderBy: { timestamp: 'desc' }, take: 20 }),
      this.prisma.performance.findMany({ orderBy: { entry_time: 'desc' }, take: 50 }),
      this.exchange.getAccount(),
      this.prisma.configuration.findMany({ where: { enabled: true } }),
    ]);

    const closed  = performances.filter(p => p.status === 'CLOSED');
    const open    = performances.filter(p => p.status === 'OPEN');
    const totalPL = closed.reduce((s, p) => s + Number(p.profit_loss ?? 0), 0);
    const wins    = closed.filter(p => Number(p.profit_loss ?? 0) > 0).length;
    const winRate = closed.length > 0 ? (wins / closed.length) * 100 : 0;

    const equityCurve = closed
      .filter(p => p.exit_time)
      .sort((a, b) => new Date(a.exit_time!).getTime() - new Date(b.exit_time!).getTime())
      .reduce<{ date: string; equity: number }[]>((acc, p) => {
        const prev  = acc.at(-1)?.equity ?? 0;
        acc.push({ date: new Date(p.exit_time!).toLocaleDateString('es-ES'), equity: parseFloat((prev + Number(p.profit_loss ?? 0)).toFixed(2)) });
        return acc;
      }, []);

    return {
      summary: {
        totalTrades: closed.length,
        openTrades: open.length,
        winRate: parseFloat(winRate.toFixed(2)),
        totalPL: parseFloat(totalPL.toFixed(2)),
        equity: account ? parseFloat(Number(account.equity ?? 0).toFixed(2)) : null,
        buyingPower: account ? parseFloat(Number(account.buying_power ?? 0).toFixed(2)) : null,
        monitoredSymbols: configs.length,
      },
      equityCurve,
      recentSignals: signals.map(s => ({
        id: s.id,
        symbol: s.symbol,
        type: s.signal_type,
        price: Number(s.current_price),
        rsi: Number(s.rsi),
        score: s.convergence_score,
        regime: s.regime_bullish,
        tfAlignment: s.tf_alignment,
        timestamp: s.timestamp,
      })),
      recentOrders: orders.map(o => ({
        id: o.id,
        symbol: o.symbol,
        type: o.order_type,
        qty: Number(o.quantity),
        price: Number(o.price),
        status: o.status,
        timestamp: o.timestamp,
      })),
      openPositions: open.map(p => ({
        id: p.id,
        symbol: p.symbol,
        entryPrice: Number(p.entry_price),
        qty: Number(p.quantity),
        entryTime: p.entry_time,
        trailingStop: p.trailing_stop_price ? Number(p.trailing_stop_price) : null,
        highestPrice: p.highest_price ? Number(p.highest_price) : null,
      })),
    };
  }

  @Get()
  async serveHtml(@Res() res: Response) {
    res.setHeader('Content-Type', 'text/html');
    res.send(DASHBOARD_HTML);
  }
}

const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto AI — Fluxit Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
  header { background: #1e293b; padding: 1rem 2rem; display: flex; align-items: center; gap: 1rem; border-bottom: 1px solid #334155; }
  header h1 { font-size: 1.25rem; font-weight: 700; }
  .badge { background: #f59e0b; color: #000; padding: 2px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 600; }
  .badge-live { background: #22c55e; color: #000; padding: 2px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; padding: 1.5rem 2rem 0; }
  .card { background: #1e293b; border-radius: 12px; padding: 1.25rem; border: 1px solid #334155; }
  .card .label { font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .card .value { font-size: 1.75rem; font-weight: 700; }
  .card .value.green { color: #22c55e; }
  .card .value.red { color: #ef4444; }
  .card .value.blue { color: #60a5fa; }
  .card .value.amber { color: #f59e0b; }
  .section { padding: 1.5rem 2rem; }
  .section h2 { font-size: 0.9rem; font-weight: 600; color: #94a3b8; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .chart-wrap { background: #1e293b; border-radius: 12px; padding: 1.5rem; border: 1px solid #334155; max-height: 300px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th { text-align: left; color: #64748b; font-weight: 500; padding: 0.5rem 0.75rem; border-bottom: 1px solid #334155; }
  td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #1e293b; }
  tr:last-child td { border-bottom: none; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 600; }
  .pill.buy  { background: #14532d; color: #4ade80; }
  .pill.sell { background: #450a0a; color: #f87171; }
  .pill.ok   { background: #1e3a5f; color: #60a5fa; }
  .pill.warn { background: #4a2415; color: #fb923c; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  .tbl-wrap { background: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; }
  .refresh { margin-left: auto; background: #334155; border: none; color: #e2e8f0; padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; }
  .refresh:hover { background: #475569; }
  @media (max-width: 768px) { .two-col { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <span>₿</span>
  <h1>Crypto AI — Fluxit</h1>
  <span class="badge">BINANCE</span>
  <span class="badge-live">24/7</span>
  <button class="refresh" onclick="loadData()">⟳ Actualizar</button>
</header>

<div class="grid" id="summary-cards">
  <div class="card"><div class="label">Equity</div><div class="value amber" id="equity">—</div></div>
  <div class="card"><div class="label">P&L Total</div><div class="value" id="total-pl">—</div></div>
  <div class="card"><div class="label">Win Rate</div><div class="value" id="win-rate">—</div></div>
  <div class="card"><div class="label">Trades</div><div class="value blue" id="total-trades">—</div></div>
  <div class="card"><div class="label">Posiciones</div><div class="value blue" id="open-trades">—</div></div>
  <div class="card"><div class="label">Criptos</div><div class="value amber" id="symbols">—</div></div>
</div>

<div class="section">
  <h2>Curva de Equity</h2>
  <div class="chart-wrap">
    <canvas id="equity-chart"></canvas>
  </div>
</div>

<div class="section two-col">
  <div>
    <h2>Señales recientes</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Cripto</th><th>Tipo</th><th>Precio</th><th>RSI</th><th>Score</th><th>Régimen BTC</th><th>Hora</th></tr></thead>
        <tbody id="signals-table"><tr><td colspan="7" style="text-align:center;color:#64748b">Cargando...</td></tr></tbody>
      </table>
    </div>
  </div>
  <div>
    <h2>Órdenes recientes</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Cripto</th><th>Tipo</th><th>Qty</th><th>Precio</th><th>Estado</th></tr></thead>
        <tbody id="orders-table"><tr><td colspan="5" style="text-align:center;color:#64748b">Cargando...</td></tr></tbody>
      </table>
    </div>
  </div>
</div>

<div class="section">
  <h2>Posiciones abiertas</h2>
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Cripto</th><th>Qty</th><th>Entrada</th><th>Trailing Stop</th><th>Máximo</th><th>Desde</th></tr></thead>
      <tbody id="positions-table"><tr><td colspan="6" style="text-align:center;color:#64748b">Cargando...</td></tr></tbody>
    </table>
  </div>
</div>

<script>
let equityChart = null;

async function loadData() {
  const r = await fetch('/dashboard/data');
  const d = await r.json();

  const pl = d.summary.totalPL;
  document.getElementById('equity').textContent    = d.summary.equity != null ? '$' + d.summary.equity.toLocaleString() : '—';
  document.getElementById('total-pl').textContent  = (pl >= 0 ? '+' : '') + '$' + pl.toFixed(2);
  document.getElementById('total-pl').className    = 'value ' + (pl >= 0 ? 'green' : 'red');
  document.getElementById('win-rate').textContent  = d.summary.winRate.toFixed(1) + '%';
  document.getElementById('win-rate').className    = 'value ' + (d.summary.winRate >= 50 ? 'green' : 'red');
  document.getElementById('total-trades').textContent = d.summary.totalTrades;
  document.getElementById('open-trades').textContent  = d.summary.openTrades;
  document.getElementById('symbols').textContent       = d.summary.monitoredSymbols;

  if (d.equityCurve.length > 0) {
    const ctx = document.getElementById('equity-chart').getContext('2d');
    const labels = d.equityCurve.map(e => e.date);
    const values = d.equityCurve.map(e => e.equity);
    if (equityChart) equityChart.destroy();
    equityChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{ label: 'P&L Acumulado ($)', data: values, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)', tension: 0.3, pointRadius: 3 }]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#94a3b8' } } }, scales: { x: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } }, y: { ticks: { color: '#64748b' }, grid: { color: '#334155' } } } }
    });
  }

  const sigBody = document.getElementById('signals-table');
  if (d.recentSignals.length === 0) {
    sigBody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#64748b">Sin señales</td></tr>';
  } else {
    sigBody.innerHTML = d.recentSignals.map(s => {
      const t = new Date(s.timestamp).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
      const pill = s.type === 'BUY' ? '<span class="pill buy">BUY</span>' : '<span class="pill sell">SELL</span>';
      const regime = s.regime == null ? '—' : s.regime ? '🐂' : '🐻';
      return \`<tr><td><b>\${s.symbol}</b></td><td>\${pill}</td><td>$\${s.price.toFixed(4)}</td><td>\${s.rsi.toFixed(1)}</td><td>\${s.score}/7</td><td>\${regime}</td><td>\${t}</td></tr>\`;
    }).join('');
  }

  const ordBody = document.getElementById('orders-table');
  if (d.recentOrders.length === 0) {
    ordBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b">Sin órdenes</td></tr>';
  } else {
    ordBody.innerHTML = d.recentOrders.map(o => {
      const pill  = o.type === 'BUY' ? '<span class="pill buy">BUY</span>' : '<span class="pill sell">SELL</span>';
      const spill = ['EXECUTED','AUTHORIZED'].includes(o.status) ? '<span class="pill ok">' + o.status + '</span>' : '<span class="pill warn">' + o.status + '</span>';
      return \`<tr><td><b>\${o.symbol}</b></td><td>\${pill}</td><td>\${o.qty.toFixed(8)}</td><td>$\${o.price.toFixed(4)}</td><td>\${spill}</td></tr>\`;
    }).join('');
  }

  const posBody = document.getElementById('positions-table');
  if (d.openPositions.length === 0) {
    posBody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#64748b">No hay posiciones abiertas</td></tr>';
  } else {
    posBody.innerHTML = d.openPositions.map(p => {
      const since = new Date(p.entryTime).toLocaleString('es-ES', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
      const ts    = p.trailingStop != null ? '$' + p.trailingStop.toFixed(4) : '—';
      const high  = p.highestPrice != null ? '$' + p.highestPrice.toFixed(4) : '—';
      return \`<tr><td><b>\${p.symbol}</b></td><td>\${p.qty.toFixed(8)}</td><td>$\${p.entryPrice.toFixed(4)}</td><td>\${ts}</td><td>\${high}</td><td>\${since}</td></tr>\`;
    }).join('');
  }
}

loadData();
setInterval(loadData, 60000);
</script>
</body>
</html>`;
