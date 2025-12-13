# Claude Memory - Trading Bot Project

## Проект
Telegram бот для торговли на Gate.io через естественный язык.

## Ключевые файлы
- `CLAUDE_CONTEXT.md` - полный контекст проекта
- `trading_agent/` - модули бота
- `ANALYSIS_VERIFICATION.md` - верификация архитектуры

## Быстрый старт
Используй команду `/load-context` для загрузки контекста.

## Текущие задачи
- [ ] Интегрировать SmartBatchBuy в strategy_core.py
- [ ] Обновить _chat_handler в telegram_bot.py
- [ ] Тестирование batch buy с rebalance

## Важно помнить
1. Метод `place_spot_order()`, не `place_order()`
2. Конвертация USDT в монеты: `amount / price`
3. Минимум ордера Gate.io: $3
4. Символы формата `XXX_USDT`
