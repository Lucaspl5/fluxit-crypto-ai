import { Injectable, Logger } from '@nestjs/common';
import axios from 'axios';
import * as crypto from 'crypto';

export interface MarketBar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type OrderExecutionStatus = 'filled' | 'pending_open' | 'failed';

export interface OrderExecutionResult {
  order: any | null;
  status: OrderExecutionStatus;
  errorMessage?: string;
}

const INTERVAL_MAP: Record<string, string> = {
  '1Day':  '1d',
  '4Hour': '4h',
  '1Hour': '1h',
  '1Min':  '1m',
  '1d': '1d', '4h': '4h', '1h': '1h', '1m': '1m',
};

@Injectable()
export class ExchangeService {
  private readonly logger = new Logger(ExchangeService.name);
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly secretKey: string;
  private ready: boolean;

  constructor() {
    const isTestnet = process.env.BINANCE_TESTNET === 'true';
    this.baseUrl   = isTestnet ? 'https://testnet.binance.vision' : 'https://api.binance.com';
    this.apiKey    = process.env.BINANCE_API_KEY    || '';
    this.secretKey = process.env.BINANCE_SECRET_KEY || '';
    this.ready     = !!(this.apiKey && this.secretKey);

    if (!this.ready) {
      this.logger.error('BINANCE_API_KEY or BINANCE_SECRET_KEY not set — trading disabled');
    } else {
      this.logger.log(`Binance client initialized (${isTestnet ? 'TESTNET' : 'LIVE'})`);
    }
  }

  isMarketOpen(): boolean {
    return true; // Crypto is 24/7
  }

  // ── Private: signed requests ──────────────────────────────────────────────

  private sign(params: Record<string, string | number>): string {
    const qs = Object.entries(params).map(([k, v]) => `${k}=${v}`).join('&');
    return crypto.createHmac('sha256', this.secretKey).update(qs).digest('hex');
  }

  private async signedGet(path: string, params: Record<string, string | number> = {}): Promise<any> {
    const p = { ...params, timestamp: Date.now(), recvWindow: 10000 };
    const signature = this.sign(p);
    const { data } = await axios.get(`${this.baseUrl}${path}`, {
      params: { ...p, signature },
      headers: { 'X-MBX-APIKEY': this.apiKey },
    });
    return data;
  }

  private async signedPost(path: string, params: Record<string, string | number> = {}): Promise<any> {
    const p = { ...params, timestamp: Date.now(), recvWindow: 10000 };
    const signature = this.sign(p);
    const qs = Object.entries({ ...p, signature }).map(([k, v]) => `${k}=${v}`).join('&');
    const { data } = await axios.post(`${this.baseUrl}${path}?${qs}`, null, {
      headers: { 'X-MBX-APIKEY': this.apiKey },
    });
    return data;
  }

  private async signedDelete(path: string, params: Record<string, string | number> = {}): Promise<any> {
    const p = { ...params, timestamp: Date.now(), recvWindow: 10000 };
    const signature = this.sign(p);
    const { data } = await axios.delete(`${this.baseUrl}${path}`, {
      params: { ...p, signature },
      headers: { 'X-MBX-APIKEY': this.apiKey },
    });
    return data;
  }

  // ── Market data ───────────────────────────────────────────────────────────

  async getHistoricalData(symbol: string, timeframe = '1Day', limit = 250): Promise<MarketBar[]> {
    try {
      const interval = INTERVAL_MAP[timeframe] ?? '1d';
      const { data } = await axios.get(`${this.baseUrl}/api/v3/klines`, {
        params: { symbol, interval, limit },
      });
      return (data as any[]).map((k: any[]) => ({
        timestamp: k[0] as number,
        open:      parseFloat(k[1]),
        high:      parseFloat(k[2]),
        low:       parseFloat(k[3]),
        close:     parseFloat(k[4]),
        volume:    parseFloat(k[5]),
      }));
    } catch (error) {
      this.logger.error(`getHistoricalData(${symbol} ${timeframe}): ${error.message}`);
      return [];
    }
  }

  async getLatestPrice(symbol: string): Promise<number | null> {
    try {
      const { data } = await axios.get(`${this.baseUrl}/api/v3/ticker/price`, {
        params: { symbol },
      });
      return parseFloat(data.price);
    } catch (error) {
      this.logger.error(`getLatestPrice(${symbol}): ${error.message}`);
      return null;
    }
  }

  // ── Account ───────────────────────────────────────────────────────────────

  async getAccount(): Promise<any | null> {
    if (!this.ready) return null;
    try {
      const data = await this.signedGet('/api/v3/account');
      const usdt = (data.balances as any[]).find((b: any) => b.asset === 'USDT');
      const free   = parseFloat(usdt?.free   ?? '0');
      const locked = parseFloat(usdt?.locked ?? '0');
      const total  = free + locked;
      return {
        equity:          total,
        cash:            free,
        buying_power:    free,
        unrealized_pl:   0,
        unrealized_plpc: 0,
      };
    } catch (error) {
      this.logger.error(`getAccount: ${error.message}`);
      return null;
    }
  }

  // ── Orders ────────────────────────────────────────────────────────────────

  private formatQty(qty: number, symbol: string): string {
    // BTC needs more decimals than DOGE
    const precision = symbol.startsWith('BTC') ? 5
      : symbol.startsWith('ETH') ? 4
      : symbol.startsWith('SOL') || symbol.startsWith('AVAX') || symbol.startsWith('LINK') ? 2
      : 0; // DOGE, LTC, UNI → integer qty on Binance
    return qty.toFixed(precision);
  }

  async executeOrderWithStatus(params: {
    symbol: string;
    qty: number;
    side: 'buy' | 'sell';
    type: 'market' | 'limit';
    limit_price?: number;
  }): Promise<OrderExecutionResult> {
    if (!this.ready) return { order: null, status: 'failed', errorMessage: 'Exchange not initialized' };

    try {
      const orderParams: Record<string, string | number> = {
        symbol:   params.symbol,
        side:     params.side.toUpperCase(),
        type:     params.type.toUpperCase(),
        quantity: this.formatQty(params.qty, params.symbol),
      };

      if (params.type === 'limit' && params.limit_price) {
        orderParams.price        = params.limit_price.toFixed(2);
        orderParams.timeInForce  = 'GTC';
      }

      const order = await this.signedPost('/api/v3/order', orderParams);
      this.logger.log(`Order placed: ${order.orderId} ${params.side} ${params.symbol} qty=${params.qty} status=${order.status}`);

      if (order.status === 'FILLED' || order.status === 'PARTIALLY_FILLED') {
        return { order: { ...order, id: String(order.orderId) }, status: 'filled' };
      }
      return { order: { ...order, id: String(order.orderId) }, status: 'pending_open' };
    } catch (error) {
      const msg = error.response?.data?.msg ?? error.message ?? 'Unknown error';
      this.logger.error(`executeOrder(${params.symbol}): ${msg}`);
      return { order: null, status: 'failed', errorMessage: msg };
    }
  }

  async executeOrder(params: {
    symbol: string;
    qty: number;
    side: 'buy' | 'sell';
    type: 'market' | 'limit';
    limit_price?: number;
  }): Promise<any | null> {
    const result = await this.executeOrderWithStatus(params);
    return result.order;
  }

  async cancelOrder(orderId: string, symbol: string): Promise<boolean> {
    if (!this.ready) return false;
    try {
      await this.signedDelete('/api/v3/order', { symbol, orderId });
      return true;
    } catch (error) {
      this.logger.error(`cancelOrder(${orderId}): ${error.message}`);
      return false;
    }
  }
}
