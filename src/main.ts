import { NestFactory } from '@nestjs/core';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  app.enableCors({ origin: '*', methods: 'GET,HEAD,PUT,PATCH,POST,DELETE' });

  const swagger = new DocumentBuilder()
    .setTitle('Crypto AI — Fluxit')
    .setDescription('Sistema de trading automático de criptomonedas con análisis técnico y Telegram')
    .setVersion('1.0.0')
    .build();

  SwaggerModule.setup('api-docs', app, SwaggerModule.createDocument(app, swagger));

  const port = process.env.PORT || 3000;
  await app.listen(port, '0.0.0.0');

  console.log(`Crypto AI running on port ${port}`);
  console.log(`Docs: http://localhost:${port}/api-docs`);
}

bootstrap();
