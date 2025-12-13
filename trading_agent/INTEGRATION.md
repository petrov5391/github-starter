# Интеграция Smart Batch Buy в Telegram Bot

## Обзор архитектуры

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Telegram      │────│   SmartChat      │────│   IntentParser  │
│   Message       │    │   Handler        │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │                         │
                              ▼                         ▼
                    ┌──────────────────┐    ┌─────────────────┐
                    │ DialogContext    │    │ PositionManager │
                    │   (контекст)     │    │  (балансы)      │
                    └──────────────────┘    └─────────────────┘
                              │                         │
                              └───────────┬─────────────┘
                                          ▼
                               ┌──────────────────┐
                               │ SmartBatchBuy    │
                               │  (исполнение)    │
                               └──────────────────┘
                                          │
                                          ▼
                               ┌──────────────────┐
                               │   Gate.io API    │
                               └──────────────────┘
```

## Шаг 1: Интеграция в strategy_core.py

Добавить в `__init__` класса `TradingAgent`:

```python
from .smart_batch_buy import integrate_smart_batch_buy

# После инициализации trader
integrate_smart_batch_buy(self)
```

Это добавит методы:
- `self.smart_batch_buy(symbols, amount, rebalance)`
- `self.execute_batch_buy_command(text)`

## Шаг 2: Интеграция в telegram_bot.py

### 2.1. Импорты

```python
from .chat_handler_mixin import SmartChatHandler
```

### 2.2. В `__init__` добавить:

```python
# После инициализации других компонентов
self.smart_handler = None
if self.execute_quick_order:
    from .position_manager import PositionManager

    # Создаём position manager wrapper
    def get_position_value(symbol):
        if hasattr(self, '_position_manager'):
            return self._position_manager.get_position_value(symbol)
        return 0.0

    def refresh_positions():
        if hasattr(self, '_position_manager'):
            self._position_manager.refresh()

    # Wrapper для batch buy
    def batch_buy_wrapper(symbols, amount, rebalance):
        if hasattr(self, '_smart_batch_buy'):
            results, report = self._smart_batch_buy.execute(
                symbols=symbols,
                amount_per_coin=amount,
                rebalance=rebalance,
            )
            return report
        return "❌ SmartBatchBuy не инициализирован"

    self.smart_handler = SmartChatHandler(
        execute_batch_buy=batch_buy_wrapper,
        execute_quick_order=self.execute_quick_order,
        get_position_value=get_position_value,
        refresh_positions=refresh_positions,
        llm_client=self.llm_client,
        grid_ai_analyze=self.grid_ai_analyze,
        grid_ai_format=self.grid_ai_format,
    )
```

### 2.3. Обновить `_chat_handler`:

```python
async def _chat_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text if update.message else ""
    self.logger.info("INCOMING text from %s: %s", update.effective_chat.id, text[:100])

    # Сохраняем в историю
    self.last_free_text = text
    self.history.append(("user", text))
    if len(self.history) > self.max_history:
        self.history.pop(0)
    self._persist_history("user", text)

    reply = None
    normalized = text.strip().lower()

    # Шаг 0: Быстрые команды (подтверждение/отмена)
    if normalized in {"подтвердить", "confirm", "да", "yes", "ок", "ok"}:
        reply = self.confirm_order()
    elif normalized in {"отмена", "cancel", "нет", "no", "стоп", "stop"}:
        reply = self.cancel_order()

    # Шаг 1: SmartChatHandler (batch buy, rebalance, etc.)
    if reply is None and self.smart_handler:
        try:
            reply = await self.smart_handler.process_message(text)
        except Exception as e:
            self.logger.error("SmartHandler error: %s", e)

    # Шаг 2: Fallback на существующий код (LLM, grid commands, etc.)
    if reply is None:
        # ... существующий код _chat_handler ...
        pass

    # Отправка ответа
    if reply:
        self.history.append(("bot", reply))
        if len(self.history) > self.max_history:
            self.history.pop(0)
        self._persist_history("bot", reply)
        await self._send_split_message(context, update.effective_chat.id, reply)
```

## Шаг 3: Тестирование

### Тестовые команды:

```
# Batch Buy (стандартный)
AAVE SOL BTC - купить по 10 долларов

# Batch Buy с rebalance
BTC ETH - докупи до $50 учитывая уже купленные

# Single Buy
купи SOL на $20

# Проверка баланса
сколько у меня BTC?
```

### Ожидаемые результаты:

1. **Batch Buy**: Покупает каждую монету на указанную сумму
2. **Rebalance**: Показывает preview, ждёт подтверждения, докупает разницу
3. **Single Buy**: Мгновенная покупка одной монеты
4. **Balance**: Показывает текущую стоимость позиции

## Ключевые отличия от исходной реализации

| Аспект | Было | Стало |
|--------|------|-------|
| Rebalance | Не поддерживался | Полная поддержка |
| Position Tracking | Нет | PositionManager |
| Подтверждение | Нет | DialogContext |
| Парсинг | Regex в _chat_handler | Централизованный IntentParser |
| Ошибки | Минимальная обработка | Детальный отчёт |

## Безопасность

1. **Лимиты**: Минимум $3 на ордер (Gate.io requirement)
2. **Подтверждение**: Для > 3 монет или > $50 требуется подтверждение
3. **DRY_RUN**: Поддерживается симуляция
4. **Логирование**: Все действия логируются
