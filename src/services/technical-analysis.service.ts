import { Injectable, Logger } from '@nestjs/common';
import { RSI, MACD, SMA, BollingerBands, ATR, OBV } from 'technicalindicators';

export interface Indicators {
  rsi: number;
  macd: number;
  macdSignal: number;
  ma50: number;
  ma200: number;
  currentPrice: number;
  atr: number;
  bbUpper: number;
  bbMiddle: number;
  bbLower: number;
  obv: number;
  rsiDivergence: 'bullish' | 'bearish' | null;
}

export interface ConvergenceSignal {
  type: 'BUY' | 'SELL';
  convergentCount: number;
  reasoning: string;
  tfAlignment: string;
}

@Injectable()
export class TechnicalAnalysisService {
  private readonly logger = new Logger(TechnicalAnalysisService.name);

  calculateIndicators(
    prices: number[],
    highs: number[],
    lows: number[],
    volumes: number[],
    rsiPeriod = 14,
    macdFast = 12,
    macdSlow = 26,
    macdSignalPeriod = 9,
    ma50Period = 50,
    ma200Period = 200,
  ): Indicators | null {
    const minRequired = Math.max(ma200Period > 0 ? ma200Period : 50, macdSlow + macdSignalPeriod - 1, 20);
    if (prices.length < minRequired) {
      this.logger.warn(`Not enough data: ${prices.length} bars (need ${minRequired})`);
      return null;
    }

    try {
      const rsiValues = RSI.calculate({ values: prices, period: rsiPeriod });
      const macdValues = MACD.calculate({
        values: prices,
        fastPeriod: macdFast,
        slowPeriod: macdSlow,
        signalPeriod: macdSignalPeriod,
        SimpleMAOscillator: false,
        SimpleMASignal: false,
      });
      const ma50Period_ = Math.min(ma50Period, prices.length - 1);
      const ma200Period_ = Math.min(ma200Period, prices.length - 1);
      const ma50Values  = SMA.calculate({ values: prices, period: ma50Period_ });
      const ma200Values = SMA.calculate({ values: prices, period: ma200Period_ });

      const atrValues = ATR.calculate({ high: highs, low: lows, close: prices, period: 14 });
      const bbValues  = BollingerBands.calculate({ values: prices, period: 20, stdDev: 2 });
      const obvValues = OBV.calculate({ close: prices, volume: volumes });

      const rsi      = rsiValues.at(-1) ?? 50;
      const macdData = macdValues.at(-1);
      const ma50     = ma50Values.at(-1)  ?? prices.at(-1)!;
      const ma200    = ma200Values.at(-1) ?? prices.at(-1)!;
      const atr      = atrValues.at(-1)   ?? 0;
      const bb       = bbValues.at(-1);
      const obv      = obvValues.at(-1)   ?? 0;

      const rsiDivergence = this.detectRsiDivergence(prices, rsiValues);

      return {
        rsi,
        macd: macdData?.MACD ?? 0,
        macdSignal: macdData?.signal ?? 0,
        ma50,
        ma200,
        currentPrice: prices.at(-1)!,
        atr,
        bbUpper:  bb?.upper  ?? prices.at(-1)! * 1.02,
        bbMiddle: bb?.middle ?? prices.at(-1)!,
        bbLower:  bb?.lower  ?? prices.at(-1)! * 0.98,
        obv,
        rsiDivergence,
      };
    } catch (error) {
      this.logger.error(`calculateIndicators: ${error.message}`);
      return null;
    }
  }

  private detectRsiDivergence(prices: number[], rsiValues: number[]): 'bullish' | 'bearish' | null {
    if (prices.length < 10 || rsiValues.length < 10) return null;
    const p = prices.slice(-10);
    const r = rsiValues.slice(-10);

    const priceLL  = p.at(-1)! < Math.min(...p.slice(0, -1));
    const rsiHL    = r.at(-1)! > Math.min(...r.slice(0, -1));
    if (priceLL && rsiHL) return 'bullish';

    const priceHH  = p.at(-1)! > Math.max(...p.slice(0, -1));
    const rsiLH    = r.at(-1)! < Math.max(...r.slice(0, -1));
    if (priceHH && rsiLH) return 'bearish';

    return null;
  }

  detectConvergenceSignal(
    ind: Indicators,
    rsiOverbought = 70,
    rsiOversold = 30,
    requiredConvergence = 2,
    volumeRatio = 1,
    h4ind?: Indicators | null,
    h1ind?: Indicators | null,
  ): ConvergenceSignal | null {
    const bullish: string[] = [];
    const bearish: string[] = [];

    // RSI
    if (ind.rsi < rsiOversold)        bullish.push(`RSI oversold (${ind.rsi.toFixed(1)})`);
    else if (ind.rsi > rsiOverbought) bearish.push(`RSI overbought (${ind.rsi.toFixed(1)})`);

    // RSI divergence
    if (ind.rsiDivergence === 'bullish') bullish.push('RSI bullish divergence');
    else if (ind.rsiDivergence === 'bearish') bearish.push('RSI bearish divergence');

    // MACD
    if (ind.macd > ind.macdSignal)  bullish.push('MACD above signal');
    else if (ind.macd < ind.macdSignal) bearish.push('MACD below signal');

    // Moving averages
    if (ind.currentPrice > ind.ma50)  bullish.push('Price above MA50');
    else if (ind.currentPrice < ind.ma50) bearish.push('Price below MA50');

    if (ind.currentPrice > ind.ma200) bullish.push('Price above MA200');
    else if (ind.currentPrice < ind.ma200) bearish.push('Price below MA200');

    // Bollinger Bands
    if (ind.currentPrice < ind.bbLower)  bullish.push('Price below BB lower (oversold squeeze)');
    else if (ind.currentPrice > ind.bbUpper) bearish.push('Price above BB upper (overbought)');

    // Volume
    if (volumeRatio > 1.2) {
      const tag = `High volume (+${((volumeRatio - 1) * 100).toFixed(0)}%)`;
      if (bullish.length > bearish.length) bullish.push(tag);
      else if (bearish.length > bullish.length) bearish.push(tag);
    }

    // Multi-timeframe
    const tfParts: string[] = [];
    if (h4ind) {
      const h4Bull = h4ind.macd > h4ind.macdSignal && h4ind.currentPrice > h4ind.ma50;
      const h4Bear = h4ind.macd < h4ind.macdSignal && h4ind.currentPrice < h4ind.ma50;
      if (h4Bull) { bullish.push('4H trend bullish'); tfParts.push('4H✅'); }
      else if (h4Bear) { bearish.push('4H trend bearish'); tfParts.push('4H🔴'); }
      else tfParts.push('4H⚪');
    }
    if (h1ind) {
      const h1Bull = h1ind.macd > h1ind.macdSignal;
      const h1Bear = h1ind.macd < h1ind.macdSignal;
      if (h1Bull) { bullish.push('1H momentum bullish'); tfParts.push('1H✅'); }
      else if (h1Bear) { bearish.push('1H momentum bearish'); tfParts.push('1H🔴'); }
      else tfParts.push('1H⚪');
    }

    const tfAlignment = tfParts.join(' ');

    if (bullish.length >= requiredConvergence) {
      return { type: 'BUY', convergentCount: bullish.length, reasoning: bullish.join('; '), tfAlignment };
    }
    if (bearish.length >= requiredConvergence) {
      return { type: 'SELL', convergentCount: bearish.length, reasoning: bearish.join('; '), tfAlignment };
    }
    return null;
  }

  calculateAtrLevels(
    entryPrice: number,
    atr: number,
    side: 'BUY' | 'SELL',
    slAtrMult = 2.0,
    tpAtrMult = 4.0,
  ): { stopLoss: number; takeProfit: number } {
    if (side === 'BUY') {
      return {
        stopLoss:   entryPrice - atr * slAtrMult,
        takeProfit: entryPrice + atr * tpAtrMult,
      };
    }
    return {
      stopLoss:   entryPrice + atr * slAtrMult,
      takeProfit: entryPrice - atr * tpAtrMult,
    };
  }
}
