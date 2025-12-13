"""
ChatHandlerMixin — улучшенная обработка чата с IntentParser.

Этот миксин заменяет стандартный _chat_handler для обработки:
- Batch buy с rebalance
- Естественный язык без команд
- Контекстный диалог
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict, List, Any, Callable

from .intent_parser import IntentParser, IntentType, ParsedIntent


class DialogContext:
    """
    Контекст диалога для понимания намерений.

    Хранит историю сообщений и позволяет понимать контекст
    типа "да, именно эти" или "добавь ещё SOL".
    """

    def __init__(self, max_history: int = 20, context_ttl: int = 300):
        """
        Args:
            max_history: Максимум сообщений в истории
            context_ttl: Время жизни контекста в секундах
        """
        self.history: List[Dict] = []
        self.max_history = max_history
        self.context_ttl = context_ttl

        # Pending состояния
        self.pending_action: Optional[Dict] = None
        self.last_intent: Optional[ParsedIntent] = None

    def add_message(self, role: str, text: str, intent: Optional[ParsedIntent] = None):
        """Добавляет сообщение в историю."""
        self.history.append({
            "role": role,
            "text": text,
            "intent": intent,
            "timestamp": time.time(),
        })

        if intent:
            self.last_intent = intent

        # Обрезаем историю
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_recent_symbols(self, lookback_seconds: int = 300) -> List[str]:
        """
        Возвращает символы из недавних сообщений.

        Полезно для контекста типа "да, эти монеты".
        """
        cutoff = time.time() - lookback_seconds
        symbols = []

        for msg in reversed(self.history):
            if msg["timestamp"] < cutoff:
                break

            intent = msg.get("intent")
            if intent and intent.symbols:
                symbols.extend(intent.symbols)

        return list(dict.fromkeys(symbols))  # Unique, preserve order

    def get_last_intent(self) -> Optional[ParsedIntent]:
        """Возвращает последнее распознанное намерение."""
        if not self.last_intent:
            return None

        # Проверяем TTL
        for msg in reversed(self.history):
            if msg.get("intent") == self.last_intent:
                if time.time() - msg["timestamp"] < self.context_ttl:
                    return self.last_intent
                break

        return None

    def set_pending_action(self, action: Dict):
        """Устанавливает ожидающее действие (требует подтверждения)."""
        self.pending_action = {
            **action,
            "timestamp": time.time(),
        }

    def get_pending_action(self) -> Optional[Dict]:
        """Возвращает ожидающее действие если не истекло."""
        if not self.pending_action:
            return None

        if time.time() - self.pending_action["timestamp"] > self.context_ttl:
            self.pending_action = None
            return None

        return self.pending_action

    def clear_pending(self):
        """Очищает pending действие."""
        self.pending_action = None


class SmartChatHandler:
    """
    Улучшенный обработчик чата с семантическим анализом.

    Использование:
        handler = SmartChatHandler(
            execute_batch_buy=agent.smart_batch_buy,
            get_position_value=agent._position_manager.get_position_value,
            ...
        )

        response = await handler.process_message(text)
    """

    def __init__(
        self,
        execute_batch_buy: Callable[[List[str], float, bool], str],
        execute_quick_order: Callable[[str, str, Optional[float]], str],
        get_position_value: Callable[[str], float],
        refresh_positions: Callable[[], None],
        llm_client: Optional[Any] = None,
        grid_ai_analyze: Optional[Callable] = None,
        grid_ai_format: Optional[Callable] = None,
    ):
        """
        Args:
            execute_batch_buy: Функция batch buy(symbols, amount, rebalance)
            execute_quick_order: Функция quick order(side, symbol, amount)
            get_position_value: Функция получения стоимости позиции
            refresh_positions: Функция обновления позиций
            llm_client: LLM клиент для fallback
            grid_ai_analyze: Функция Grid AI анализа
            grid_ai_format: Функция форматирования Grid AI
        """
        self.execute_batch_buy = execute_batch_buy
        self.execute_quick_order = execute_quick_order
        self.get_position_value = get_position_value
        self.refresh_positions = refresh_positions
        self.llm_client = llm_client
        self.grid_ai_analyze = grid_ai_analyze
        self.grid_ai_format = grid_ai_format

        self.intent_parser = IntentParser()
        self.context = DialogContext()
        self.logger = logging.getLogger(__name__)

    async def process_message(self, text: str) -> Optional[str]:
        """
        Обрабатывает сообщение и возвращает ответ.

        Args:
            text: Текст сообщения пользователя

        Returns:
            Ответ или None если не обработано
        """
        normalized = text.strip()
        lower = normalized.lower()

        # Шаг 0: Проверяем подтверждение/отмену pending действия
        pending_response = self._check_pending_response(lower)
        if pending_response:
            return pending_response

        # Шаг 1: Парсим намерение
        intent = self.intent_parser.parse(text)
        self.context.add_message("user", text, intent)

        # Шаг 2: Обрабатываем по типу намерения
        if intent.intent == IntentType.BATCH_BUY:
            return await self._handle_batch_buy(intent)

        elif intent.intent == IntentType.SINGLE_BUY:
            return self._handle_single_buy(intent)

        elif intent.intent == IntentType.REBALANCE:
            return await self._handle_rebalance(intent)

        elif intent.intent == IntentType.SELL:
            return self._handle_sell(intent)

        elif intent.intent == IntentType.BALANCE_CHECK:
            return self._handle_balance_check(intent)

        # Шаг 3: Проверяем Grid команды
        grid_response = self._check_grid_command(lower)
        if grid_response:
            return grid_response

        # Шаг 4: Fallback на LLM
        return None  # Вернёт None чтобы telegram_bot использовал LLM

    def _check_pending_response(self, text: str) -> Optional[str]:
        """Проверяет ответ на pending действие."""
        pending = self.context.get_pending_action()
        if not pending:
            return None

        # Подтверждение
        if text in {"да", "yes", "подтвердить", "confirm", "ок", "ok", "делай", "go"}:
            action = pending["action"]
            self.context.clear_pending()

            if action == "batch_buy":
                return self.execute_batch_buy(
                    pending["symbols"],
                    pending["amount"],
                    pending.get("rebalance", False)
                )

            return f"✅ Подтверждено: {action}"

        # Отмена
        if text in {"нет", "no", "отмена", "cancel", "стоп", "stop"}:
            self.context.clear_pending()
            return "🚫 Действие отменено"

        return None

    async def _handle_batch_buy(self, intent: ParsedIntent) -> str:
        """Обработка batch buy."""
        symbols = intent.symbols
        amount = intent.target_amount if intent.target_amount > 0 else 10.0

        # Если много монет или большая сумма — запрашиваем подтверждение
        total_amount = amount * len(symbols)
        if len(symbols) > 3 or total_amount > 50:
            self.context.set_pending_action({
                "action": "batch_buy",
                "symbols": symbols,
                "amount": amount,
                "rebalance": intent.rebalance,
            })

            lines = [
                f"🔍 **Batch Buy** — {len(symbols)} монет по ${amount:.2f}",
                "",
                f"Монеты: {', '.join(symbols)}",
                f"Общая сумма: ${total_amount:.2f}",
                f"Режим: {'Rebalance' if intent.rebalance else 'Standard'}",
                "",
                "**Подтвердить?** (да/нет)",
            ]
            return "\n".join(lines)

        # Выполняем сразу
        return self.execute_batch_buy(symbols, amount, intent.rebalance)

    def _handle_single_buy(self, intent: ParsedIntent) -> str:
        """Обработка покупки одной монеты."""
        if not intent.symbols:
            return "❌ Не указана монета для покупки"

        symbol = intent.symbols[0]
        amount = intent.target_amount if intent.target_amount > 0 else 10.0

        return self.execute_quick_order("buy", symbol, amount)

    async def _handle_rebalance(self, intent: ParsedIntent) -> str:
        """Обработка rebalance."""
        symbols = intent.symbols
        if not symbols:
            # Используем символы из контекста
            symbols = self.context.get_recent_symbols()

        if not symbols:
            return "❌ Не указаны монеты для rebalance. Пример: 'BTC ETH - докупи до $50 каждую'"

        amount = intent.target_amount if intent.target_amount > 0 else 10.0

        # Обновляем позиции
        self.refresh_positions()

        # Показываем текущее состояние
        lines = ["📊 **Rebalance Preview:**", ""]

        for symbol in symbols:
            current = self.get_position_value(f"{symbol}_USDT")
            to_buy = max(0, amount - current)
            status = "✅" if current >= amount else f"➡️ +${to_buy:.2f}"
            lines.append(f"• {symbol}: ${current:.2f} → ${amount:.2f} {status}")

        lines.extend([
            "",
            "**Выполнить?** (да/нет)",
        ])

        self.context.set_pending_action({
            "action": "batch_buy",
            "symbols": symbols,
            "amount": amount,
            "rebalance": True,
        })

        return "\n".join(lines)

    def _handle_sell(self, intent: ParsedIntent) -> str:
        """Обработка продажи."""
        if not intent.symbols:
            return "❌ Не указана монета для продажи"

        symbol = intent.symbols[0]

        if intent.sell_all:
            return self.execute_quick_order("sell", symbol, None)
        else:
            amount = intent.target_amount if intent.target_amount > 0 else None
            return self.execute_quick_order("sell", symbol, amount)

    def _handle_balance_check(self, intent: ParsedIntent) -> str:
        """Обработка запроса баланса."""
        self.refresh_positions()

        if intent.symbols:
            # Конкретные монеты
            lines = ["💰 **Баланс:**", ""]
            for symbol in intent.symbols:
                value = self.get_position_value(f"{symbol}_USDT")
                lines.append(f"• {symbol}: ${value:.2f}")
            return "\n".join(lines)

        # Показать всё
        return "Используйте /balance для полного списка"

    def _check_grid_command(self, text: str) -> Optional[str]:
        """Проверяет Grid команды."""
        if not self.grid_ai_analyze or not self.grid_ai_format:
            return None

        # Ключевые слова Grid
        grid_keywords = [
            r'грид', r'сетк', r'распредел.*монет',
            r'low\s*risk', r'mrisk', r'lrisk', r'hrisk',
            r'сделай.*по.*доллар', r'поставь.*монет',
        ]

        if not any(re.search(kw, text) for kw in grid_keywords):
            return None

        # Извлекаем параметры
        risk = "MEDIUM"
        if any(w in text for w in ['low', 'lrisk', 'консерватив', 'низк']):
            risk = "LOW"
        elif any(w in text for w in ['high', 'hrisk', 'агрессив', 'высок']):
            risk = "HIGH"

        days = 7
        days_match = re.search(r'(\d+)\s*(?:дней|дня|день|days?)', text)
        if days_match:
            days = int(days_match.group(1))

        capital = 50.0
        amount_match = re.search(r'\$?(\d+(?:\.\d+)?)', text)
        if amount_match:
            capital = float(amount_match.group(1))

        try:
            result = self.grid_ai_analyze(risk, days, capital)
            if result:
                return self.grid_ai_format(result)
        except Exception as e:
            self.logger.error("Grid AI error: %s", e)

        return None


# === Пример интеграции с telegram_bot.py ===
"""
В telegram_bot.py добавить в __init__:

    from .chat_handler_mixin import SmartChatHandler

    self.smart_handler = SmartChatHandler(
        execute_batch_buy=self.execute_batch_buy_wrapper,
        execute_quick_order=self.execute_quick_order,
        get_position_value=self.get_position_value_wrapper,
        refresh_positions=self.refresh_positions_wrapper,
        llm_client=self.llm_client,
        grid_ai_analyze=self.grid_ai_analyze,
        grid_ai_format=self.grid_ai_format,
    )

В _chat_handler заменить на:

    async def _chat_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text if update.message else ""

        # Пробуем smart handler
        response = await self.smart_handler.process_message(text)

        if response:
            await self._send_split_message(context, update.effective_chat.id, response)
            return

        # Fallback на LLM (существующий код)
        ...
"""
