# Инструкция для новой сессии Claude

## Скопируй всё ниже и вставь в новую сессию Claude:

---

Это проект Trading Bot — Telegram бот для управления торговлей на Gate.io через естественный язык.

## Репозиторий
GitHub: `petrov5391/github-starter`
Ветка: `claude/telegram-exchange-bot-01SDotTEnbAC67BmmMHzNhfX`

## Получи файлы

```bash
git clone https://github.com/petrov5391/github-starter.git
cd github-starter
git checkout claude/telegram-exchange-bot-01SDotTEnbAC67BmmMHzNhfX
```

## Структура новых модулей

```
trading_agent/
├── intent_parser.py       # Парсер намерений из текста
├── position_manager.py    # Отслеживание позиций/балансов
├── smart_batch_buy.py     # Умный batch buy с rebalance
├── chat_handler_mixin.py  # Улучшенный обработчик чата
└── INTEGRATION.md         # Инструкция интеграции
```

## Задача

Интегрировать SmartBatchBuy в существующие файлы:
- `telegram_bot.py` — добавить SmartChatHandler в _chat_handler
- `strategy_core.py` — добавить integrate_smart_batch_buy(self)

## Что умеет SmartBatchBuy

Понимает команды на естественном языке:
```
"AAVE SOL BTC - купить по 10 долларов"
→ Покупает каждую монету на $10

"BTC ETH - докупи до $50 учитывая уже купленные"
→ Проверяет текущий баланс, докупает разницу до $50
```

## Критичные моменты

1. Метод: `trader.place_spot_order()`, НЕ `place_order()`
2. Конвертация: `coin_amount = usdt_amount / current_price`
3. Минимум ордера Gate.io: $3
4. Формат символов: `BTC_USDT`

## Начни работу

1. Прочитай файл `trading_agent/INTEGRATION.md`
2. Прочитай файл `CLAUDE_CONTEXT.md`
3. Попроси пользователя дать существующие `telegram_bot.py` и `strategy_core.py`
4. Выполни интеграцию согласно инструкции

---

**КОНЕЦ ИНСТРУКЦИИ ДЛЯ КОПИПАСТЫ**
