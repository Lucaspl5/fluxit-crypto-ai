import { Controller, Get, Post, Param, Body } from '@nestjs/common';
import { ApiOperation, ApiParam } from '@nestjs/swagger';
import { ConfigurationService } from '../services/configuration.service';

@Controller('config')
export class ConfigController {
  constructor(private configService: ConfigurationService) {}

  @Get()
  @ApiOperation({ summary: 'Todas las configuraciones activas' })
  async getAll() {
    return this.configService.getEnabledConfigurations();
  }

  @Get(':symbol')
  @ApiOperation({ summary: 'Configuración de una cripto' })
  @ApiParam({ name: 'symbol' })
  async getOne(@Param('symbol') symbol: string) {
    const cfg = await this.configService.getConfiguration(symbol.toUpperCase());
    return cfg ?? { error: 'Not found' };
  }

  @Post(':symbol')
  @ApiOperation({ summary: 'Crear o actualizar configuración de una cripto' })
  @ApiParam({ name: 'symbol' })
  async upsert(@Param('symbol') symbol: string, @Body() body: any) {
    const cfg = await this.configService.ensureConfiguration(symbol.toUpperCase());
    if (Object.keys(body).length > 0) {
      return this.configService.updateConfiguration(symbol.toUpperCase(), body);
    }
    return cfg;
  }

  @Post(':symbol/disable')
  @ApiOperation({ summary: 'Deshabilitar monitoreo de una cripto' })
  @ApiParam({ name: 'symbol' })
  async disable(@Param('symbol') symbol: string) {
    return this.configService.disableConfiguration(symbol.toUpperCase());
  }
}
