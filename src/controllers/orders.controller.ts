import { Controller, Get, Post, Delete, Param, Query } from '@nestjs/common';
import { ApiOperation, ApiParam, ApiQuery } from '@nestjs/swagger';
import { OrderService } from '../services/order.service';

const toFloat = (v: any) => parseFloat(v?.toString() ?? '0');

@Controller('orders')
export class OrdersController {
  constructor(private orderService: OrderService) {}

  @Get()
  @ApiOperation({ summary: 'Todas las órdenes' })
  @ApiQuery({ name: 'limit', required: false, type: Number })
  async getAll(@Query('limit') limit?: string) {
    const orders = await this.orderService.getAllOrders(limit ? +limit : 50);
    return orders.map((o) => ({ ...o, quantity: toFloat(o.quantity), price: toFloat(o.price) }));
  }

  @Get('symbol/:symbol')
  @ApiOperation({ summary: 'Órdenes por símbolo' })
  @ApiParam({ name: 'symbol' })
  async getBySymbol(@Param('symbol') symbol: string, @Query('limit') limit?: string) {
    const orders = await this.orderService.getOrdersBySymbol(symbol, limit ? +limit : 20);
    return orders.map((o) => ({ ...o, quantity: toFloat(o.quantity), price: toFloat(o.price) }));
  }

  @Post(':id/authorize')
  @ApiOperation({ summary: 'Autorizar y ejecutar una orden pendiente' })
  @ApiParam({ name: 'id', description: 'Order ID' })
  async authorize(@Param('id') id: string) {
    const success = await this.orderService.authorizeAndExecuteOrder(id);
    return { success, message: success ? 'Order executed' : 'Execution failed' };
  }

  @Delete(':id')
  @ApiOperation({ summary: 'Cancelar una orden' })
  @ApiParam({ name: 'id' })
  async cancel(@Param('id') id: string) {
    const success = await this.orderService.cancelOrder(id);
    return { success, message: success ? 'Order cancelled' : 'Cancellation failed' };
  }
}
