import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { configuration } from '@prisma/client';

@Injectable()
export class ConfigurationService {
  private readonly logger = new Logger(ConfigurationService.name);

  constructor(private prisma: PrismaService) {}

  async ensureConfiguration(symbol: string): Promise<configuration> {
    let config = await this.prisma.configuration.findUnique({ where: { symbol } });

    if (!config) {
      config = await this.prisma.configuration.create({
        data: {
          symbol: symbol.toUpperCase(),
          enabled: true,
          required_convergence: 2,
          stop_loss_pct: 5.0,
          take_profit_pct: 12.0,
          max_risk_per_trade: 5.0,
          volume_threshold_pct: 130,
          trailing_stop_pct: 3.0,
          max_open_positions: 5,
          use_kelly: true,
          kelly_fraction: 0.5,
          regime_filter: true,
          use_sentiment: false,
        },
      });
      this.logger.log(`Created default configuration for ${symbol}`);
    }

    return config;
  }

  async getEnabledConfigurations(): Promise<configuration[]> {
    return this.prisma.configuration.findMany({ where: { enabled: true } });
  }

  async getConfiguration(symbol: string): Promise<configuration | null> {
    return this.prisma.configuration.findUnique({ where: { symbol } });
  }

  async updateConfiguration(symbol: string, updates: Partial<configuration>): Promise<configuration> {
    return this.prisma.configuration.update({ where: { symbol }, data: updates });
  }

  async disableConfiguration(symbol: string): Promise<configuration> {
    return this.prisma.configuration.update({ where: { symbol }, data: { enabled: false } });
  }
}
