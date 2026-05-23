import { Injectable, Logger, OnApplicationBootstrap } from '@nestjs/common';
import { Cron } from '@nestjs/schedule';
import { PrismaService } from '../prisma/prisma.service';
import { ExchangeService } from './exchange.service';
import { TechnicalAnalysisService } from './technical-analysis.service';
import { TelegramService } from './telegram.service';
import { ConfigurationService } from './configuration.service';
import { SentimentService } from './sentiment.service';
import { signal as SignalModel } from '@prisma/client';
import Decimal from 'decimal.js';

// Crypto market reference — BTC is used as the broad market indicator (like SPY for stocks)
const MARKET_REFERENCE = 'BTCUSD';

@Injectable()
export class SignalService implements OnApplicationBootstrap {
  private readonly logger = new Logger(SignalService.name);
  private slTpRunning = false;

  constructor(
    private prisma: PrismaService,
    private exchange: ExchangeService,
    private ta: TechnicalAnalysisService,
    private telegram: TelegramService,
    private config: ConfigurationService,
    private sentiment: SentimentService,
  ) {}

  async onApplicationBootstrap(): Promise<void> {
    const cancelled = await this.prisma.order.updateMany({
      where: { status: 'PENDING' },
      data: { status: 'CANCELLED', status_reason: 'Stale order cleared on startup' },
    });
    if (cancelled.count > 0) {
      this.logger.log(`Startup cleanup: cancelled ${cancelled.count} stale PENDING order(s)`);
    }

    await this.prisma.signal.updateMany({
      where: { telegram_message_id: { not: null } },
      data: { telegram_message_id: null },
    });
    this.logger.log('Startup cleanup: cleared stale Telegram message IDs from signals');
  }

  @Cron('*/15 * * * *')
  async scheduledAnalysis(): Promise<void> {
    this.logger.log('Scheduled analysis started');
    const signals = await this.executeAnalysis();
    this.logger.log(`Scheduled analysis finished — ${signals.length} signal(s) generated`);
  }

  @Cron('0 18 * * 0')
  async weeklyReport(): Promise<void> {
    this.logger.log('Sending weekly report to Telegram');
    await this.telegram.sendWeeklySummary();
  }

  // Crypto is 24/7 — check SL/TP every 5 minutes, always
  @Cron('*/5 * * * *')
  async checkStopLossTakeProfit(): Promise<void> {
    if (this.slTpRunning) {
      this.logger.warn('SL/TP check skipped — previous run still in progress');
      return;
    }
    this.slTpRunning = true;
    try {
      await this.runStopLossTakeProfit();
    } finally {
      this.slTpRunning = false;
    }
  }

  private async runStopLossTakeProfit(): Promise<void> {
    const openPositions = await this.prisma.performance.findMany({
      where: { status: 'OPEN' },
      include: { buy_order: true, configuration: true },
    });
    if (openPositions.length === 0) return;

    const bySymbol = new Map<string, typeof openPositions>();
    for (const pos of openPositions) {
      if (!bySymbol.has(pos.symbol)) bySymbol.set(pos.symbol, []);
      bySymbol.get(pos.symbol)!.push(pos);
    }

    for (const [symbol, positions] of bySymbol) {
      const currentPrice = await this.exchange.getLatestPrice(symbol);
      if (!currentPrice) continue;

      const ref = positions[0];
      const cfg = ref.configuration;

      const ageMs = Date.now() - new Date(ref.entry_time).getTime();
      if (ageMs < 2 * 60 * 60 * 1000) {
        this.logger.log(`${symbol}: skipping SL/TP check — position is less than 2h old`);
        continue;
      }

      const trailPct = Number(cfg.trailing_stop_pct ?? 3);
      const newTrailingStop = currentPrice * (1 - trailPct / 100);
      const currentHighest  = Number(ref.highest_price ?? ref.entry_price);
      const currentTrailSL  = Number(ref.trailing_stop_price ?? 0);

      if (currentPrice > currentHighest) {
        await this.prisma.performance.update({
          where: { id: ref.id },
          data: {
            highest_price: new Decimal(currentPrice),
            trailing_stop_price: new Decimal(newTrailingStop),
          },
        });
        this.logger.log(`${symbol}: trailing stop raised to $${newTrailingStop.toFixed(4)} (price=$${currentPrice})`);
      }

      const sl = Number(ref.buy_order.stop_loss_price ?? 0);
      const tp = Number(ref.buy_order.take_profit_price ?? 0);

      const effectiveSL = Math.max(sl, currentTrailSL);

      const hitSL = effectiveSL > 0 && currentPrice <= effectiveSL;
      const hitTP = tp > 0 && currentPrice >= tp;

      if (!hitSL && !hitTP) continue;

      const stillOpen = await this.prisma.performance.findFirst({ where: { id: ref.id, status: 'OPEN' } });
      if (!stillOpen) {
        this.logger.warn(`${symbol}: position already closed, skipping`);
        continue;
      }

      const reason   = hitSL ? (currentTrailSL > sl ? 'Trailing Stop' : 'Stop Loss') : 'Take Profit';
      const exitTime = new Date();
      let totalPL    = 0;

      this.logger.log(`${symbol}: ${reason} triggered at $${currentPrice} — closing ${positions.length} position(s)`);

      for (const pos of positions) {
        const entry    = Number(pos.entry_price);
        const qty      = Number(pos.quantity);
        const pl       = (currentPrice - entry) * qty;
        const plPct    = ((currentPrice - entry) / entry) * 100;
        const duration = Math.floor((exitTime.getTime() - new Date(pos.entry_time).getTime()) / 1000);
        totalPL += pl;

        await this.prisma.performance.update({
          where: { id: pos.id },
          data: {
            exit_price: new Decimal(currentPrice),
            exit_time: exitTime,
            profit_loss: new Decimal(pl),
            profit_loss_pct: new Decimal(plPct),
            duration_seconds: duration,
            status: 'CLOSED',
          },
        });
      }

      const totalQty   = positions.reduce((s, p) => s + Number(p.quantity), 0);
      const alpacaOrder = await this.exchange.executeOrder({ symbol, qty: totalQty, side: 'sell', type: 'market' });

      await this.prisma.order.create({
        data: {
          configuration_id: ref.configuration_id,
          symbol,
          order_type: 'SELL',
          quantity: new Decimal(totalQty),
          price: new Decimal(currentPrice),
          max_risk_eur: ref.buy_order.max_risk_eur,
          status: alpacaOrder ? 'EXECUTED' : 'CANCELLED',
          alpaca_order_id: alpacaOrder?.id,
          execution_time: exitTime,
          notes: `Auto-closed by ${reason} (${positions.length} position(s))`,
        },
      });

      const totalPlPct = ((currentPrice - Number(ref.entry_price)) / Number(ref.entry_price)) * 100;
      await this.telegram.sendAutoClose(symbol, reason, currentPrice, totalPL, totalPlPct);
      this.logger.log(`${symbol} auto-closed (${reason}): total P&L=${totalPL >= 0 ? '+' : ''}$${totalPL.toFixed(2)}`);
    }
  }

  async executeAnalysis(): Promise<SignalModel[]> {
    const configs = await this.config.getEnabledConfigurations();
    const results: SignalModel[] = [];

    for (const cfg of configs) {
      const signal = await this.analyzeSymbol(cfg.symbol);
      if (signal) results.push(signal);
    }

    return results;
  }

  async analyzeSymbol(symbol: string): Promise<SignalModel | null> {
    try {
      const cfg = await this.config.ensureConfiguration(symbol);

      // === CRYPTO MARKET REGIME FILTER ===
      // For altcoins, only take BUY signals when BTC is above its MA200 (bullish crypto market)
      // BTC itself skips this filter
      let regimeBullish = true;
      if (cfg.regime_filter && symbol !== MARKET_REFERENCE) {
        const btcBars = await this.exchange.getHistoricalData(MARKET_REFERENCE, '1Day', 220);
        if (btcBars.length >= 200) {
          const btcPrices = btcBars.map(b => b.close);
          const btcMa200  = btcPrices.slice(-200).reduce((a, b) => a + b, 0) / 200;
          regimeBullish   = btcPrices.at(-1)! > btcMa200;
          this.logger.log(`Crypto regime: BTC $${btcPrices.at(-1)!.toFixed(0)} vs MA200 $${btcMa200.toFixed(0)} — ${regimeBullish ? 'BULLISH' : 'BEARISH'}`);
        }
      }

      // === DAILY BARS ===
      const bars = await this.exchange.getHistoricalData(symbol, '1Day', cfg.ma200_period + 50);
      if (bars.length === 0) {
        this.logger.warn(`No market data for ${symbol}`);
        return null;
      }

      const prices  = bars.map(b => b.close);
      const highs   = bars.map(b => b.high);
      const lows    = bars.map(b => b.low);
      const volumes = bars.map(b => b.volume);
      const currentPrice = prices.at(-1)!;

      const ind = this.ta.calculateIndicators(
        prices, highs, lows, volumes,
        cfg.rsi_period, cfg.macd_fast_period, cfg.macd_slow_period,
        cfg.macd_signal_period, cfg.ma50_period, cfg.ma200_period,
      );
      if (!ind) return null;

      // === MULTI-TIMEFRAME: 4H and 1H ===
      const [bars4h, bars1h] = await Promise.all([
        this.exchange.getHistoricalData(symbol, '4Hour', 120),
        this.exchange.getHistoricalData(symbol, '1Hour', 100),
      ]);

      const ind4h = bars4h.length >= 60
        ? this.ta.calculateIndicators(bars4h.map(b => b.close), bars4h.map(b => b.high), bars4h.map(b => b.low), bars4h.map(b => b.volume), 14, 12, 26, 9, 20, 50)
        : null;

      const ind1h = bars1h.length >= 40
        ? this.ta.calculateIndicators(bars1h.map(b => b.close), bars1h.map(b => b.high), bars1h.map(b => b.low), bars1h.map(b => b.volume), 14, 12, 26, 9, 20, 50)
        : null;

      this.logger.log(
        `${symbol}: $${currentPrice.toFixed(4)} RSI=${ind.rsi.toFixed(1)} MACD=${ind.macd.toFixed(4)} ATR=${ind.atr.toFixed(4)} BB[${ind.bbLower.toFixed(4)}-${ind.bbUpper.toFixed(4)}]`,
      );

      const recentVol = volumes.slice(-20);
      const avgVol    = recentVol.reduce((a, b) => a + b, 0) / recentVol.length;
      const volRatio  = volumes.at(-1)! / avgVol;

      const convergence = this.ta.detectConvergenceSignal(
        ind, cfg.rsi_overbought, cfg.rsi_oversold, cfg.required_convergence, volRatio, ind4h, ind1h,
      );
      if (!convergence) return null;

      if (convergence.type === 'BUY' && !regimeBullish) {
        this.logger.log(`${symbol}: skipping BUY — BTC in bear regime (below MA200)`);
        return null;
      }

      // === SENTIMENT FILTER ===
      let sentimentScore = 0;
      if (cfg.use_sentiment) {
        const sentimentResult = await this.sentiment.getSentiment(symbol);
        sentimentScore = sentimentResult.score;
        if (convergence.type === 'BUY' && this.sentiment.isSentimentBlocking(sentimentResult)) {
          this.logger.log(`${symbol}: skipping BUY — bearish sentiment (${sentimentResult.summary})`);
          return null;
        }
      }

      // === POSITION GUARDS ===
      if (convergence.type === 'BUY') {
        const openPosition = await this.prisma.performance.findFirst({
          where: { symbol: symbol.toUpperCase(), status: 'OPEN' },
        });
        if (openPosition) {
          this.logger.log(`${symbol}: skipping BUY — already have an open position`);
          return null;
        }

        const totalOpen = await this.prisma.performance.count({ where: { status: 'OPEN' } });
        if (totalOpen >= cfg.max_open_positions) {
          this.logger.log(`${symbol}: skipping BUY — max open positions reached (${totalOpen}/${cfg.max_open_positions})`);
          return null;
        }

        const recentClose = await this.prisma.order.findFirst({
          where: {
            symbol: symbol.toUpperCase(),
            order_type: 'SELL',
            notes: { contains: 'Auto-closed' },
            execution_time: { gte: new Date(Date.now() - 6 * 60 * 60 * 1000) },
          },
        });
        if (recentClose) {
          this.logger.log(`${symbol}: skipping BUY — auto-close triggered less than 6h ago`);
          return null;
        }
      }

      if (convergence.type === 'SELL') {
        const openPosition = await this.prisma.performance.findFirst({
          where: { symbol: symbol.toUpperCase(), status: 'OPEN' },
        });
        if (!openPosition) {
          this.logger.log(`${symbol}: skipping SELL — no open position`);
          return null;
        }
      }

      // === POSITION SIZING: Kelly Criterion (fractional crypto) ===
      const account     = await this.exchange.getAccount();
      const buyingPower = account ? Number(account.buying_power ?? 0) : 0;
      const recommendedQty = cfg.use_kelly
        ? await this.calculateKellyQuantity(symbol, cfg, buyingPower, currentPrice, convergence.convergentCount, ind.rsi)
        : this.calculateRecommendedQuantity(convergence.convergentCount, ind.rsi, cfg.rsi_oversold, convergence.type as 'BUY' | 'SELL', buyingPower, currentPrice, cfg.risk_profile);

      const atrLevels = this.ta.calculateAtrLevels(currentPrice, ind.atr, convergence.type as 'BUY' | 'SELL');

      const saved = await this.prisma.signal.create({
        data: {
          configuration_id: cfg.id,
          symbol: symbol.toUpperCase(),
          signal_type: convergence.type,
          rsi: new Decimal(ind.rsi),
          macd: new Decimal(ind.macd),
          macd_signal: new Decimal(ind.macdSignal),
          macd_divergence: new Decimal(ind.macd - ind.macdSignal),
          ma50: new Decimal(ind.ma50),
          ma200: new Decimal(ind.ma200),
          current_price: new Decimal(currentPrice),
          volume: BigInt(Math.round(volumes.at(-1)!)),
          avg_volume: BigInt(Math.round(avgVol)),
          volume_ratio: new Decimal(volRatio),
          convergent_indicators: convergence.convergentCount,
          convergence_score: convergence.convergentCount,
          confidence_level: new Decimal(Math.min(100, 60 + convergence.convergentCount * 10)),
          risk_level: cfg.risk_profile === 'BAJO' ? 'LOW' : cfg.risk_profile === 'MEDIUM' ? 'MEDIUM' : 'HIGH',
          recommendation: this.toRecommendation(convergence.type, convergence.convergentCount),
          reasoning: convergence.reasoning,
          recommended_quantity: new Decimal(recommendedQty),
          atr: new Decimal(ind.atr),
          bb_upper: new Decimal(ind.bbUpper),
          bb_lower: new Decimal(ind.bbLower),
          sentiment_score: new Decimal(sentimentScore),
          regime_bullish: regimeBullish,
          tf_alignment: convergence.tfAlignment,
        },
      });

      this.logger.log(`Signal saved: ${symbol} ${convergence.type} (${convergence.convergentCount} indicators, qty=${recommendedQty}, ATR SL=$${atrLevels.stopLoss.toFixed(4)})`);

      const messageId = await this.telegram.sendSignalNotification({
        symbol,
        signalType: convergence.type,
        price: currentPrice.toFixed(4),
        rsi: ind.rsi.toFixed(2),
        macd: ind.macd.toFixed(4),
        ma50: ind.ma50.toFixed(4),
        ma200: ind.ma200.toFixed(4),
        reasoning: convergence.reasoning,
        signalId: saved.id,
        recommendedQuantity: recommendedQty,
        convergentCount: convergence.convergentCount,
        atr: ind.atr,
        bbUpper: ind.bbUpper,
        bbLower: ind.bbLower,
        tfAlignment: convergence.tfAlignment,
        regimeBullish,
        sentimentScore: cfg.use_sentiment ? sentimentScore : undefined,
        atrStopLoss: atrLevels.stopLoss,
        atrTakeProfit: atrLevels.takeProfit,
      });

      if (messageId) {
        await this.prisma.signal.update({ where: { id: saved.id }, data: { telegram_message_id: messageId } });
      }

      return saved;
    } catch (error) {
      this.logger.error(`analyzeSymbol(${symbol}): ${error.message}`);
      return null;
    }
  }

  private async calculateKellyQuantity(
    symbol: string,
    cfg: any,
    buyingPower: number,
    currentPrice: number,
    convergentCount: number,
    rsi: number,
  ): Promise<number> {
    if (currentPrice <= 0 || buyingPower <= 0) return 0.001;

    const kellyFraction = Number(cfg.kelly_fraction ?? 0.5);
    const tpPct = Number(cfg.take_profit_pct ?? 12);
    const slPct = Number(cfg.stop_loss_pct ?? 5);

    const closedTrades = await this.prisma.performance.findMany({
      where: { symbol: symbol.toUpperCase(), status: 'CLOSED', profit_loss: { not: null } },
      take: 50,
    });

    let p: number;
    let b: number;

    if (closedTrades.length >= 10) {
      const wins   = closedTrades.filter(t => Number(t.profit_loss) > 0);
      p = wins.length / closedTrades.length;
      const avgWin  = wins.length > 0 ? wins.reduce((s, t) => s + Number(t.profit_loss_pct ?? 0), 0) / wins.length : tpPct;
      const losses  = closedTrades.filter(t => Number(t.profit_loss) <= 0);
      const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s, t) => s + Number(t.profit_loss_pct ?? 0), 0) / losses.length) : slPct;
      b = avgLoss > 0 ? avgWin / avgLoss : tpPct / slPct;
    } else {
      p = 0.5;
      b = tpPct / slPct;
    }

    const kelly = b > 0 ? (p * b - (1 - p)) / b : 0;
    const safeFraction = Math.max(0.005, Math.min(kelly * kellyFraction, 0.20));

    const strengthBonus = convergentCount >= 5 ? 1.2 : convergentCount >= 4 ? 1.1 : 1.0;
    const investAmount = buyingPower * safeFraction * strengthBonus;

    // Return fractional quantity — minimum 0.0001 for micro coins
    const rawQty = investAmount / currentPrice;
    const minQty = currentPrice > 1000 ? 0.0001 : currentPrice > 10 ? 0.01 : 1;
    return Math.max(minQty, parseFloat(rawQty.toFixed(8)));
  }

  async getRecentSignals(limit = 20): Promise<SignalModel[]> {
    return this.prisma.signal.findMany({ orderBy: { timestamp: 'desc' }, take: limit });
  }

  async getSignalsBySymbol(symbol: string, limit = 20): Promise<SignalModel[]> {
    return this.prisma.signal.findMany({
      where: { symbol: symbol.toUpperCase() },
      orderBy: { timestamp: 'desc' },
      take: limit,
    });
  }

  private toRecommendation(type: string, score: number): string {
    if (score >= 4) return type === 'BUY' ? 'STRONG_BUY' : 'STRONG_SELL';
    if (score >= 3) return type === 'BUY' ? 'BUY' : 'SELL';
    return 'NEUTRAL';
  }

  private calculateRecommendedQuantity(
    convergentCount: number,
    rsi: number,
    rsiOversold: number,
    signalType: 'BUY' | 'SELL',
    buyingPower: number,
    currentPrice: number,
    riskProfile: string,
  ): number {
    if (currentPrice <= 0 || buyingPower <= 0) return 0.001;

    const baseRiskPct  = riskProfile === 'BAJO' ? 3 : riskProfile === 'ALTO' ? 8 : 5;
    const strengthMul  = convergentCount >= 4 ? 1.5 : convergentCount >= 3 ? 1.25 : 1.0;
    const rsiDepth     = signalType === 'BUY' ? Math.max(0, rsiOversold - rsi) : 0;
    const rsiBonusMul  = rsiDepth >= 5 ? 1.2 : 1.0;

    const investAmount = buyingPower * (baseRiskPct / 100) * strengthMul * rsiBonusMul;
    const rawQty = investAmount / currentPrice;
    const minQty = currentPrice > 1000 ? 0.0001 : currentPrice > 10 ? 0.01 : 1;
    return Math.max(minQty, parseFloat(rawQty.toFixed(8)));
  }
}
