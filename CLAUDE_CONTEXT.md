# Trading Bot Context - Telegram Exchange Bot

## Цель проекта
Telegram бот для управления торговлей на Gate.io через естественный язык (без команд /).

## Текущий статус
Реализованы модули для умного batch buy с rebalance. Требуется интеграция в существующий код.

---

## Структура проекта

```
trading_agent/
├── __init__.py              # Экспорты
├── intent_parser.py         # Парсер намерений из текста
├── position_manager.py      # Отслеживание позиций/балансов
├── smart_batch_buy.py       # Умный batch buy с rebalance
├── chat_handler_mixin.py    # Улучшенный обработчик чата
├── INTEGRATION.md           # Инструкция интеграции
│
├── telegram_bot.py          # [СУЩЕСТВУЮЩИЙ] Telegram бот
├── strategy_core.py         # [СУЩЕСТВУЮЩИЙ] Ядро агента
├── trade_executor.py        # [СУЩЕСТВУЮЩИЙ] Исполнитель ордеров
└── auto_trader.py           # [СУЩЕСТВУЮЩИЙ] Автотрейдер
```

---

## Ключевые классы

### IntentParser (intent_parser.py)
Парсит текст и определяет намерение:
- `BATCH_BUY` - "AAVE SOL BTC - купить по $10"
- `REBALANCE` - "докупи до $50 учитывая купленные"
- `SINGLE_BUY` - "купи ETH на $20"
- `SELL` - "продай все XRP"

```python
parser = IntentParser()
result = parser.parse("AAVE SOL - купить по 10 долларов")
# result.intent = IntentType.BATCH_BUY
# result.symbols = ["AAVE", "SOL"]
# result.target_amount = 10.0
```

### PositionManager (position_manager.py)
Отслеживает текущие балансы:
```python
pm = PositionManager(trader)
pm.refresh()
value = pm.get_position_value("BTC_USDT")  # $45.50
to_buy = pm.calculate_additional_amount("BTC_USDT", 50.0)  # $4.50
```

### SmartBatchBuy (smart_batch_buy.py)
Умная покупка с учётом позиций:
```python
batch = SmartBatchBuy(trader, position_manager)
results, report = batch.execute(
    symbols=["BTC", "ETH", "SOL"],
    amount_per_coin=10.0,
    rebalance=True  # Учитывать имеющиеся монеты
)
```

---

## Интеграция (TODO)

### 1. В strategy_core.py

Добавить в `__init__`:
```python
from .smart_batch_buy import integrate_smart_batch_buy
integrate_smart_batch_buy(self)
```

### 2. В telegram_bot.py

Добавить в `__init__`:
```python
from .chat_handler_mixin import SmartChatHandler
# ... инициализация smart_handler
```

Обновить `_chat_handler`:
```python
async def _chat_handler(self, update, context):
    text = update.message.text

    # Сначала SmartHandler
    if self.smart_handler:
        reply = await self.smart_handler.process_message(text)
        if reply:
            await self._send_split_message(context, update.effective_chat.id, reply)
            return

    # Потом существующий код...
```

---

## Тестовые команды

```
# Batch Buy
AAVE SOL BTC - купить по 10 долларов

# Rebalance
BTC ETH - докупи до $50 учитывая уже купленные

# Single Buy
купи SOL на $20

# Продажа
продай все XRP
```

---

## Критичные моменты

1. **Метод ордера**: Использовать `trader.place_spot_order()`, НЕ `place_order()`
2. **Конвертация**: USDT → количество монет: `coin_amount = usdt_amount / price`
3. **Минимум ордера**: Gate.io требует минимум $3
4. **Символы**: Нормализовать к формату `BTC_USDT`

---

## Файлы для чтения

При старте новой сессии прочитай:
1. `trading_agent/INTEGRATION.md` - полная инструкция
2. `trading_agent/intent_parser.py` - парсер
3. `trading_agent/smart_batch_buy.py` - batch buy логика
4. `ANALYSIS_VERIFICATION.md` - верификация анализа
