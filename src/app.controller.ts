import { Controller, Get } from '@nestjs/common';
import { TelegramService } from './services/telegram.service';

@Controller()
export class AppController {
  constructor(private telegram: TelegramService) {}

  @Get()
  root() {
    return {
      name: 'Crypto AI — Fluxit',
      version: '1.0.0',
      status: 'running',
      timestamp: new Date().toISOString(),
    };
  }

  @Get('health')
  health() {
    return { status: 'ok', timestamp: new Date().toISOString() };
  }

  @Get('admin/register-webhook')
  async registerWebhook() {
    const result = await this.telegram.forceRegisterWebhook();
    return result;
  }
}
