import { Controller, Post, Get, Param, Body, Query } from '@nestjs/common';
import { ApiOperation, ApiParam, ApiQuery } from '@nestjs/swagger';
import { BacktestingService, BacktestParams } from '../services/backtesting.service';

@Controller('backtest')
export class BacktestingController {
  constructor(private backtestingService: BacktestingService) {}

  @Post('run')
  @ApiOperation({ summary: 'Ejecutar backtest de una estrategia crypto' })
  async run(@Body() body: BacktestParams) {
    try {
      const id = await this.backtestingService.runBacktest(body);
      return { success: true, backtest_id: id };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }

  @Get()
  @ApiOperation({ summary: 'Listar backtests' })
  @ApiQuery({ name: 'symbol', required: false })
  async list(@Query('symbol') symbol?: string) {
    return this.backtestingService.getBacktests(symbol);
  }

  @Get(':id')
  @ApiOperation({ summary: 'Detalle de un backtest' })
  @ApiParam({ name: 'id' })
  async getOne(@Param('id') id: string) {
    const bt = await this.backtestingService.getBacktestById(id);
    if (!bt) return { error: 'Not found' };
    return bt;
  }
}
