import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const symbols = [
  // Low risk — BTC & ETH: SL 5% / TP 12% / convergence 2
  { symbol: 'BTCUSDT', profile: 'BAJO',   rsiOB: 75, rsiOS: 25, ma50: 50, ma200: 200, volThr: 110, sl: 5.0,  tp: 12.0, conv: 2 },
  { symbol: 'ETHUSDT', profile: 'BAJO',   rsiOB: 75, rsiOS: 25, ma50: 50, ma200: 200, volThr: 110, sl: 5.0,  tp: 12.0, conv: 2 },
  // Medium risk — Large Cap Altcoins: SL 7% / TP 18% / convergence 2
  { symbol: 'SOLUSDT', profile: 'MEDIUM', rsiOB: 70, rsiOS: 30, ma50: 20, ma200: 200, volThr: 120, sl: 7.0,  tp: 18.0, conv: 2 },
  { symbol: 'AVAXUSDT',profile: 'MEDIUM', rsiOB: 70, rsiOS: 30, ma50: 20, ma200: 200, volThr: 120, sl: 7.0,  tp: 18.0, conv: 2 },
  { symbol: 'LINKUSDT',profile: 'MEDIUM', rsiOB: 70, rsiOS: 30, ma50: 20, ma200: 200, volThr: 120, sl: 7.0,  tp: 18.0, conv: 3 },
  // High risk — Volatile Altcoins: SL 12% / TP 30% / convergence 3
  { symbol: 'DOGEUSDT',profile: 'ALTO',   rsiOB: 65, rsiOS: 35, ma50: 20, ma200: 100, volThr: 150, sl: 12.0, tp: 30.0, conv: 3 },
  { symbol: 'LTCUSDT', profile: 'ALTO',   rsiOB: 65, rsiOS: 35, ma50: 20, ma200: 100, volThr: 150, sl: 12.0, tp: 30.0, conv: 3 },
  { symbol: 'UNIUSDT', profile: 'ALTO',   rsiOB: 65, rsiOS: 35, ma50: 20, ma200: 100, volThr: 150, sl: 12.0, tp: 30.0, conv: 3 },
];

async function main() {
  console.log('Seeding 8 crypto symbols with risk parameters...');

  for (const s of symbols) {
    const macdFast = s.profile === 'ALTO' ? 8 : 12;
    const macdSlow = s.profile === 'ALTO' ? 17 : 26;

    const riskData = {
      enabled: true,
      risk_profile: s.profile as any,
      analysis_interval_min: 15,
      rsi_period: 14,
      rsi_overbought: s.rsiOB,
      rsi_oversold: s.rsiOS,
      macd_fast_period: macdFast,
      macd_slow_period: macdSlow,
      macd_signal_period: 9,
      ma50_period: s.ma50,
      ma200_period: s.ma200,
      volume_threshold_pct: s.volThr,
      required_convergence: s.conv,
      stop_loss_pct: s.sl,
      take_profit_pct: s.tp,
      max_risk_per_trade: 5.0,
      trailing_stop_pct: 3.0,
    };

    await prisma.configuration.upsert({
      where:  { symbol: s.symbol },
      update: riskData,
      create: { symbol: s.symbol, ...riskData },
    });
    console.log(`  ${s.symbol} (${s.profile}): SL ${s.sl}% / TP ${s.tp}% / conv ${s.conv}`);
  }

  console.log('Done. Crypto risk parameters seeded.');
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => { console.error(e); await prisma.$disconnect(); process.exit(1); });
