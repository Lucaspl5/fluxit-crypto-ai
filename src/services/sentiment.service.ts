import { Injectable, Logger } from '@nestjs/common';
import axios from 'axios';

interface SentimentResult {
  score: number;
  label: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  articleCount: number;
  summary: string;
}

const BULLISH_TERMS = [
  // Generic
  'beat', 'surpasses', 'exceeds', 'record', 'high', 'growth', 'upgrade', 'buy',
  'strong', 'outperform', 'bullish', 'rally', 'surge', 'gains', 'positive', 'optimistic',
  // Crypto-specific
  'adoption', 'halving', 'etf', 'institutional', 'accumulation', 'mainnet', 'launch',
  'partnership', 'listing', 'bull', 'moon', 'defi', 'staking', 'upgrade', 'migration',
  'breakout', 'all-time high', 'ath', 'whale buying', 'inflow',
];

const BEARISH_TERMS = [
  // Generic
  'miss', 'disappoints', 'below', 'loss', 'decline', 'falls', 'downgrade', 'sell',
  'weak', 'underperform', 'bearish', 'crash', 'drops', 'plunge', 'negative', 'pessimistic',
  // Crypto-specific
  'hack', 'exploit', 'rug', 'scam', 'regulation', 'ban', 'crackdown', 'sec',
  'fud', 'dump', 'bear', 'correction', 'liquidation', 'delisting', 'sanctions',
  'fraud', 'lawsuit', 'investigation', 'outflow', 'fear', 'panic', 'sell-off',
  'bankruptcy', 'default', 'warning', 'risk',
];

function scoreText(text: string): number {
  const lower = text.toLowerCase();
  let score = 0;
  for (const t of BULLISH_TERMS) if (lower.includes(t)) score += 1;
  for (const t of BEARISH_TERMS) if (lower.includes(t)) score -= 1;
  return score;
}

@Injectable()
export class SentimentService {
  private readonly logger = new Logger(SentimentService.name);
  private readonly apiKey = process.env.NEWS_API_KEY;

  private cache = new Map<string, { result: SentimentResult; fetchedAt: number }>();
  private readonly cacheTtlMs = 30 * 60 * 1000;

  async getSentiment(symbol: string): Promise<SentimentResult> {
    if (!this.apiKey) {
      return { score: 0, label: 'NEUTRAL', articleCount: 0, summary: 'NEWS_API_KEY not configured' };
    }

    const cached = this.cache.get(symbol);
    if (cached && Date.now() - cached.fetchedAt < this.cacheTtlMs) {
      return cached.result;
    }

    // Use the base coin name for better news results (e.g., BTCUSD → bitcoin)
    const coinName = this.toCoinName(symbol);

    try {
      const response = await axios.get('https://newsapi.org/v2/everything', {
        params: {
          q: coinName,
          language: 'en',
          sortBy: 'publishedAt',
          pageSize: 20,
          apiKey: this.apiKey,
        },
        timeout: 5000,
      });

      const articles: any[] = response.data?.articles ?? [];
      if (articles.length === 0) {
        const result: SentimentResult = { score: 0, label: 'NEUTRAL', articleCount: 0, summary: 'No recent news' };
        this.cache.set(symbol, { result, fetchedAt: Date.now() });
        return result;
      }

      let totalScore = 0;
      for (const article of articles) {
        const text = `${article.title ?? ''} ${article.description ?? ''}`;
        totalScore += scoreText(text);
      }

      const avgScore = totalScore / articles.length;
      const normalizedScore = Math.max(-1, Math.min(1, avgScore / 3));
      const label: SentimentResult['label'] =
        normalizedScore > 0.15 ? 'BULLISH' : normalizedScore < -0.15 ? 'BEARISH' : 'NEUTRAL';

      const result: SentimentResult = {
        score: parseFloat(normalizedScore.toFixed(3)),
        label,
        articleCount: articles.length,
        summary: `${articles.length} artículos · ${label} (score: ${normalizedScore.toFixed(2)})`,
      };

      this.cache.set(symbol, { result, fetchedAt: Date.now() });
      this.logger.log(`Sentiment ${symbol}: ${label} (${normalizedScore.toFixed(2)}) from ${articles.length} articles`);
      return result;
    } catch (error) {
      this.logger.warn(`Sentiment fetch failed for ${symbol}: ${error.message}`);
      return { score: 0, label: 'NEUTRAL', articleCount: 0, summary: `Error: ${error.message}` };
    }
  }

  isSentimentBlocking(result: SentimentResult): boolean {
    return result.label === 'BEARISH' && result.score < -0.3;
  }

  private toCoinName(symbol: string): string {
    const map: Record<string, string> = {
      BTCUSD: 'bitcoin',
      ETHUSD: 'ethereum',
      SOLUSD: 'solana',
      AVAXUSD: 'avalanche',
      LINKUSD: 'chainlink',
      DOGEUSD: 'dogecoin',
      LTCUSD: 'litecoin',
      UNIUSD: 'uniswap',
    };
    return map[symbol.toUpperCase()] ?? symbol.replace('USD', '').toLowerCase();
  }
}
