import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiOperation, ApiParam, ApiQuery } from '@nestjs/swagger';
import { PrismaService } from '../prisma/prisma.service';

const f = (v: any) => v ? parseFloat(v.toString()) : null;

@Controller('performance')
export class PerformanceController {
  constructor(private prisma: PrismaService) {}

  @Get()
  @ApiOperation({ summary: 'Registros de P&L' })
  @ApiQuery({ name: 'limit', required: false, type: Number })
  async getAll(@Query('limit') limit?: string) {
    const records = await this.prisma.performance.findMany({
      orderBy: { created_at: 'desc' },
      take: limit ? +limit : 50,
    });
    return records.map((r) => ({
      ...r,
      entry_price: f(r.entry_price),
      exit_price: f(r.exit_price),
      profit_loss: f(r.profit_loss),
      profit_loss_pct: f(r.profit_loss_pct),
    }));
  }

  @Get('stats/summary')
  @ApiOperation({ summary: 'Resumen de métricas' })
  async summary() {
    const [closed, open] = await Promise.all([
      this.prisma.performance.findMany({ where: { status: 'CLOSED' } }),
      this.prisma.performance.findMany({ where: { status: 'OPEN' } }),
    ]);

    const wins = closed.filter((r) => (r.profit_loss_pct?.toNumber() ?? 0) > 0).length;
    const losses = closed.filter((r) => (r.profit_loss_pct?.toNumber() ?? 0) < 0).length;
    const totalPnL = closed.reduce((sum, r) => sum + (r.profit_loss?.toNumber() ?? 0), 0);
    const avgPct = closed.length > 0
      ? closed.reduce((sum, r) => sum + (r.profit_loss_pct?.toNumber() ?? 0), 0) / closed.length
      : 0;

    return {
      total_trades: closed.length,
      open_trades: open.length,
      winning_trades: wins,
      losing_trades: losses,
      win_rate: closed.length > 0 ? ((wins / closed.length) * 100).toFixed(2) + '%' : '0%',
      total_profit_loss: totalPnL.toFixed(2),
      avg_profit_loss_pct: avgPct.toFixed(4),
    };
  }

  @Get('symbol/:symbol')
  @ApiOperation({ summary: 'P&L por símbolo' })
  @ApiParam({ name: 'symbol' })
  async getBySymbol(@Param('symbol') symbol: string) {
    const records = await this.prisma.performance.findMany({
      where: { symbol: symbol.toUpperCase() },
      orderBy: { created_at: 'desc' },
    });
    return records.map((r) => ({
      ...r,
      entry_price: f(r.entry_price),
      exit_price: f(r.exit_price),
      profit_loss: f(r.profit_loss),
      profit_loss_pct: f(r.profit_loss_pct),
    }));
  }
}
