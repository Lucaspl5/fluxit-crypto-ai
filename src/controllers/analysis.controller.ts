import { Controller, Post, Body, Logger } from '@nestjs/common';
import { ApiOperation, ApiResponse } from '@nestjs/swagger';
import { SignalService } from '../services/signal.service';

@Controller('analysis')
export class AnalysisController {
  private readonly logger = new Logger(AnalysisController.name);

  constructor(private signalService: SignalService) {}

  @Post('run')
  @ApiOperation({ summary: 'Ejecutar análisis técnico de todas las criptos habilitadas' })
  @ApiResponse({ status: 200, description: 'Análisis completado' })
  async run(@Body() body: { api_key?: string }) {
    const expectedKey = process.env.ANALYSIS_API_KEY;
    if (expectedKey && body.api_key !== expectedKey) {
      return { success: false, error: 'Invalid API key' };
    }

    try {
      this.logger.log('Manual analysis triggered');
      const signals = await this.signalService.executeAnalysis();
      return {
        success: true,
        signals_generated: signals.length,
        timestamp: new Date().toISOString(),
        message: `Analysis completed. ${signals.length} signal(s) generated.`,
      };
    } catch (error) {
      this.logger.error(`Analysis failed: ${error.message}`);
      return { success: false, error: error.message, timestamp: new Date().toISOString() };
    }
  }
}
