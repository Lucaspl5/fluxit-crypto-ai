import { Controller, Post, Body, Res, Logger } from '@nestjs/common';
import { ApiOperation } from '@nestjs/swagger';
import { TelegramService } from '../services/telegram.service';
import { Response } from 'express';

@Controller('webhook')
export class TelegramController {
  private readonly logger = new Logger(TelegramController.name);

  constructor(private telegram: TelegramService) {}

  @Post('telegram')
  @ApiOperation({ summary: 'Telegram webhook — recibe updates del bot' })
  handleWebhook(@Body() update: any, @Res() res: Response) {
    const type = update?.message ? 'message' : update?.callback_query ? 'callback_query' : 'other';
    const text = update?.message?.text || update?.callback_query?.data || '';
    this.logger.log(`Webhook received: ${type} — "${text}"`);

    res.json({ ok: true });
    this.telegram.processUpdate(update).catch((e) => this.logger.error(`processUpdate: ${e.message}`));
  }
}
