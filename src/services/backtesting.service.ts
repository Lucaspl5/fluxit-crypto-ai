import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { ExchangeService } from './exchange.service';
import { TechnicalAnalysisService } from './technical-analysis.service';
import Decimal from 'decimal.js';

export interface BacktestParams {
  symbol: string;
  startDate: string;
  endDate: string;
  requiredConvergence?: number;
  rsiOverbought?: number;
  rsiOversold?: number;
  stopLossPct?: number;
  takeProfitPct?: number;
  initialCapital?: number;
  riskPctPerTrade?: number;
}

interface BacktestTrade {
  entryDate: Date;
  exitDate: Date;
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  pl: number;
  plPct: number;
  exitReason: string;
}

@Injectable()
export class BacktestingService {
  private readonly logger = new Logger(BacktestingService.name);

  constructor(
    private prisma: PrismaService,
    private exchange: ExchangeService,
    private ta: TechnicalAnalysisService,
  ) {}

  async runBacktest(params: BacktestParams): Promise<string> {
    const {
      symbol,
      startDate,
      endDate,
      requiredConvergence = 2,
      rsiOverbought = 70,
      rsiOversold = 30,
      stopLossPct = 5,
      takeProfitPct = 12,
      initialCapital = 100000,
      riskPctPerTrade = 5,
    } = params;

    this.logger.log(`Starting backtest: ${symbol} ${startDate} → ${endDate}`);

    const allBars = await this.exchange.getHistoricalData(symbol, '1Day', 500);
    const start = new Date(startDate).getTime();
    const end   = new Date(endDate).getTime();

    if (allBars.length < 250) {
      throw new Error(`Not enough historical data for ${symbol}: ${allBars.length} bars`);
    }

    const barsInRange = allBars.filter(b => b.timestamp >= start && b.timestamp <= end);
    if (barsInRange.length < 30) {
      throw new Error(`Not enough bars in date range: ${barsInRange.length}`);
    }

    const trades: BacktestTrade[] = [];
    let capital = initialCapital;
    let position: { entryPrice: number; qty: number; sl: number; tp: number; entryDate: Date } | null = null;

    const warmupBars = allBars.filter(b => b.timestamp < start);
    if (warmupBars.length < 200) {
      throw new Error('Not enough warmup bars before start date for MA200 calculation');
    }

    for (let i = 0; i < barsInRange.length; i++) {
      const windowBars = [...warmupBars, ...barsInRange.slice(0, i + 1)];

      const prices  = windowBars.map(b => b.close);
      const highs   = windowBars.map(b => b.high);
      const lows    = windowBars.map(b => b.low);
      const volumes = windowBars.map(b => b.volume);

      const ind = this.ta.calculateIndicators(prices, highs, lows, volumes);
      if (!ind) continue;

      const recentVol = volumes.slice(-20);
      const avgVol    = recentVol.reduce((a, b) => a + b, 0) / recentVol.length;
      const volRatio  = volumes.at(-1)! / avgVol;

      const currentPrice = prices.at(-1)!;
      const currentDate  = new Date(barsInRange[i].timestamp);

      if (position) {
        if (currentPrice <= position.sl) {
          const pl    = (currentPrice - position.entryPrice) * position.qty;
          const plPct = ((currentPrice - position.entryPrice) / position.entryPrice) * 100;
          capital += position.qty * currentPrice;
          trades.push({ entryDate: position.entryDate, exitDate: currentDate, entryPrice: position.entryPrice, exitPrice: currentPrice, quantity: position.qty, pl, plPct, exitReason: 'Stop Loss' });
          position = null;
          continue;
        }
        if (currentPrice >= position.tp) {
          const pl    = (currentPrice - position.entryPrice) * position.qty;
          const plPct = ((currentPrice - position.entryPrice) / position.entryPrice) * 100;
          capital += position.qty * currentPrice;
          trades.push({ entryDate: position.entryDate, exitDate: currentDate, entryPrice: position.entryPrice, exitPrice: currentPrice, quantity: position.qty, pl, plPct, exitReason: 'Take Profit' });
          position = null;
          continue;
        }
      }

      if (!position) {
        const convergence = this.ta.detectConvergenceSignal(ind, rsiOverbought, rsiOversold, requiredConvergence, volRatio);
        if (convergence?.type === 'BUY') {
          const riskAmount = capital * (riskPctPerTrade / 100);
          const qty        = parseFloat((riskAmount / currentPrice).toFixed(8));
          const cost       = qty * currentPrice;
          if (cost > capital) continue;

          capital -= cost;
          position = {
            entryPrice: currentPrice,
            qty,
            sl: currentPrice * (1 - stopLossPct / 100),
            tp: currentPrice * (1 + takeProfitPct / 100),
            entryDate: currentDate,
          };
        }
      }
    }

    if (position && barsInRange.length > 0) {
      const lastBar = barsInRange.at(-1)!;
      const exitPrice = lastBar.close;
      const pl    = (exitPrice - position.entryPrice) * position.qty;
      const plPct = ((exitPrice - position.entryPrice) / position.entryPrice) * 100;
      trades.push({ entryDate: position.entryDate, exitDate: new Date(lastBar.timestamp), entryPrice: position.entryPrice, exitPrice, quantity: position.qty, pl, plPct, exitReason: 'End of backtest' });
      capital += position.qty * exitPrice;
    }

    const totalPl    = trades.reduce((s, t) => s + t.pl, 0);
    const wins       = trades.filter(t => t.pl > 0);
    const losses     = trades.filter(t => t.pl <= 0);
    const winRate    = trades.length > 0 ? (wins.length / trades.length) * 100 : 0;
    const maxDrawdown = this.calcMaxDrawdown(trades, initialCapital);
    const sharpe     = this.calcSharpe(trades);

    const backtest = await this.prisma.backtest.create({
      data: {
        symbol: symbol.toUpperCase(),
        start_date: new Date(startDate),
        end_date: new Date(endDate),
        strategy_params: {
          requiredConvergence, rsiOverbought, rsiOversold,
          stopLossPct, takeProfitPct, initialCapital, riskPctPerTrade,
        },
        total_trades: trades.length,
        win_rate: new Decimal(winRate.toFixed(2)),
        total_pl: new Decimal(totalPl.toFixed(4)),
        max_drawdown: new Decimal(maxDrawdown.toFixed(4)),
        sharpe_ratio: sharpe != null ? new Decimal(sharpe.toFixed(4)) : null,
        trades: {
          create: trades.map(t => ({
            symbol: symbol.toUpperCase(),
            entry_date: t.entryDate,
            exit_date:  t.exitDate,
            entry_price: new Decimal(t.entryPrice.toFixed(4)),
            exit_price:  new Decimal(t.exitPrice.toFixed(4)),
            quantity: new Decimal(t.quantity.toFixed(8)),
            pl:     new Decimal(t.pl.toFixed(4)),
            pl_pct: new Decimal(t.plPct.toFixed(4)),
            exit_reason: t.exitReason,
          })),
        },
      },
    });

    this.logger.log(`Backtest done: ${trades.length} trades · win rate ${winRate.toFixed(1)}% · P&L $${totalPl.toFixed(2)} · Sharpe ${sharpe?.toFixed(2) ?? 'N/A'}`);
    return backtest.id;
  }

  private calcMaxDrawdown(trades: BacktestTrade[], initialCapital: number): number {
    let peak = initialCapital;
    let runningCapital = initialCapital;
    let maxDD = 0;

    for (const t of trades) {
      runningCapital += t.pl;
      if (runningCapital > peak) peak = runningCapital;
      const dd = ((peak - runningCapital) / peak) * 100;
      if (dd > maxDD) maxDD = dd;
    }
    return maxDD;
  }

  private calcSharpe(trades: BacktestTrade[]): number | null {
    if (trades.length < 2) return null;
    const returns = trades.map(t => t.plPct);
    const mean    = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((a, b) => a + (b - mean) ** 2, 0) / returns.length;
    const stdDev  = Math.sqrt(variance);
    if (stdDev === 0) return null;
    return (mean / stdDev) * Math.sqrt(365 / trades.length);
  }

  async getBacktests(symbol?: string): Promise<any[]> {
    return this.prisma.backtest.findMany({
      where: symbol ? { symbol: symbol.toUpperCase() } : undefined,
      orderBy: { created_at: 'desc' },
      take: 20,
      include: { trades: false },
    });
  }

  async getBacktestById(id: string): Promise<any | null> {
    return this.prisma.backtest.findUnique({
      where: { id },
      include: { trades: { orderBy: { entry_date: 'asc' } } },
    });
  }
}
