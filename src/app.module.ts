import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ScheduleModule } from '@nestjs/schedule';

import { PrismaService } from './prisma/prisma.service';
import { ExchangeService } from './services/exchange.service';
import { TechnicalAnalysisService } from './services/technical-analysis.service';
import { TelegramService } from './services/telegram.service';
import { ConfigurationService } from './services/configuration.service';
import { SignalService } from './services/signal.service';
import { OrderService } from './services/order.service';
import { SentimentService } from './services/sentiment.service';
import { BacktestingService } from './services/backtesting.service';

import { AppController } from './app.controller';
import { AnalysisController } from './controllers/analysis.controller';
import { TelegramController } from './controllers/telegram.controller';
import { SignalsController } from './controllers/signals.controller';
import { OrdersController } from './controllers/orders.controller';
import { PerformanceController } from './controllers/performance.controller';
import { ConfigController } from './controllers/config.controller';
import { BacktestingController } from './controllers/backtesting.controller';
import { DashboardController } from './controllers/dashboard.controller';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    ScheduleModule.forRoot(),
  ],
  controllers: [
    AppController,
    AnalysisController,
    TelegramController,
    SignalsController,
    OrdersController,
    PerformanceController,
    ConfigController,
    BacktestingController,
    DashboardController,
  ],
  providers: [
    PrismaService,
    ExchangeService,
    TechnicalAnalysisService,
    TelegramService,
    ConfigurationService,
    SignalService,
    OrderService,
    SentimentService,
    BacktestingService,
  ],
})
export class AppModule {}
