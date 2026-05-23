import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiOperation, ApiParam, ApiQuery } from '@nestjs/swagger';
import { SignalService } from '../services/signal.service';

const toFloat = (v: any): number | null => {
  if (v == null) return null;
  if (typeof v === 'bigint') return Number(v);
  return parseFloat(v.toString());
};

@Controller('signals')
export class SignalsController {
  constructor(private signalService: SignalService) {}

  @Get()
  @ApiOperation({ summary: 'Últimas señales' })
  @ApiQuery({ name: 'limit', required: false, type: Number })
  async getRecent(@Query('limit') limit?: string) {
    const signals = await this.signalService.getRecentSignals(limit ? +limit : 20);
    return signals.map(serializeSignal);
  }

  @Get(':symbol')
  @ApiOperation({ summary: 'Señales por símbolo' })
  @ApiParam({ name: 'symbol', description: 'Ej: BTCUSD' })
  @ApiQuery({ name: 'limit', required: false, type: Number })
  async getBySymbol(@Param('symbol') symbol: string, @Query('limit') limit?: string) {
    const signals = await this.signalService.getSignalsBySymbol(symbol, limit ? +limit : 20);
    return signals.map(serializeSignal);
  }
}

function serializeSignal(s: any) {
  return {
    ...s,
    rsi: toFloat(s.rsi),
    macd: toFloat(s.macd),
    macd_signal: toFloat(s.macd_signal),
    macd_divergence: toFloat(s.macd_divergence),
    ma50: toFloat(s.ma50),
    ma200: toFloat(s.ma200),
    current_price: toFloat(s.current_price),
    volume_ratio: toFloat(s.volume_ratio),
    confidence_level: toFloat(s.confidence_level),
    recommended_quantity: toFloat(s.recommended_quantity),
    volume: Number(s.volume),
    avg_volume: Number(s.avg_volume),
    atr: toFloat(s.atr),
    bb_upper: toFloat(s.bb_upper),
    bb_lower: toFloat(s.bb_lower),
    sentiment_score: toFloat(s.sentiment_score),
  };
}
