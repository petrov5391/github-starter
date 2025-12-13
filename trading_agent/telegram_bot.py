"""
TelegramBot — интерфейс управления торговым агентом через Telegram.
Поддержка команд, уведомлений, подтверждения ордеров и LLM диалога.
"""

import asyncio
import logging
import threading
from typing import Callable, Dict, List, Optional, Any

from telegram import (
    Bot,
    Update,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    ReplyKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


async def _safe_send(bot: Bot, chat_id: str, text: str) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:
        logging.error("Telegram send failed: %s", exc)


async def send_notification(bot_token: str, chat_id: str, message: str) -> None:
    bot = Bot(token=bot_token)
    async with bot:
        await _safe_send(bot, chat_id, message)


class TelegramBot:
    """
    Telegram бот для управления торговым агентом.

    Основные функции:
    - Команды управления (/status, /orders, /pause, /resume и т.д.)
    - Подтверждение ордеров (/confirm, /cancel)
    - Парсинг торговых инструкций через LLM
    - Уведомления о сигналах и исполнении ордеров
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        get_status: Callable[[], str],
        get_questions: Callable[[], List[str]],
        get_stats: Callable[[], str] | None = None,
        get_orders: Callable[[], str] | None = None,
        pause_agent: Callable[[], str] | None = None,
        resume_agent: Callable[[], str] | None = None,
        llm_client=None,
        system_prompt: str = "",
        history_file: str = "chat_history.log",
        get_plan=None,
        get_news=None,
        start_sprint=None,
        # Новые параметры для торговли
        confirm_order: Callable[[], str] | None = None,
        cancel_order: Callable[[], str] | None = None,
        get_pending_orders: Callable[[], str] | None = None,
        on_instruction_parsed: Callable[[Any], str] | None = None,
        instruction_parser=None,
        # Адаптивная стратегия
        select_portfolio: Callable[[], str] | None = None,
        get_market_status: Callable[[], str] | None = None,
        get_strategy_status: Callable[[], str] | None = None,
        run_adaptive_cycle: Callable[[], str] | None = None,
        portfolio_summary: Callable[[], str] | None = None,
        # AutoTrader
        start_auto_trader: Callable[[bool], str] | None = None,
        stop_auto_trader: Callable[[], str] | None = None,
        pause_auto_trader: Callable[[], str] | None = None,
        resume_auto_trader: Callable[[], str] | None = None,
        get_auto_trader_status: Callable[[], str] | None = None,
        # AI Advisor & Monitor
        get_ai_recommendation: Callable[[], Any] | None = None,
        format_ai_recommendation: Callable[[Any], str] | None = None,
        start_ai_monitor: Callable[[Callable, bool], str] | None = None,
        stop_ai_monitor: Callable[[], str] | None = None,
        get_ai_monitor_status: Callable[[], str] | None = None,
        ai_monitor_confirm: Callable[[], str] | None = None,
        ai_monitor_reject: Callable[[], str] | None = None,
        ai_monitor_force: Callable[[], str] | None = None,
        # Grid Trading
        grid_start: Callable[[str, float, float, int, float], str] | None = None,
        grid_stop: Callable[[], str] | None = None,
        grid_status: Callable[[], str] | None = None,
        grid_levels: Callable[[], str] | None = None,
        grid_analyze: Callable[[str], str] | None = None,
        # Баланс
        get_capital: Callable[[], float] | None = None,
        get_all_balances: Callable[[], dict] | None = None,
        # Быстрые ордера (купи/продай через чат)
        execute_quick_order: Callable[[str, str, float | None], str] | None = None,
        # Grid AI Strategy
        grid_ai_analyze: Callable[[str, int, float], Any] | None = None,
        grid_ai_format: Callable[[Any], str] | None = None,
        grid_ai_confirm: Callable[[], str] | None = None,
        grid_ai_cancel: Callable[[], str] | None = None,
        grid_ai_status: Callable[[], str] | None = None,
        grid_ai_stop: Callable[[], str] | None = None,
        grid_ai_deep: Callable[[], Any] | None = None,
        grid_ai_format_deep: Callable[[Any], str] | None = None,
        get_grid_ai_history: Callable[[], List[Dict]] | None = None,
        # AI Grid Monitor
        monitor_start: Callable[[], str] | None = None,
        monitor_stop: Callable[[], str] | None = None,
        monitor_status: Callable[[], str] | None = None,
        monitor_analyze: Callable[[], str] | None = None,
        monitor_confirm: Callable[[], str] | None = None,
        monitor_reject: Callable[[], str] | None = None,
        monitor_details: Callable[[], str] | None = None,
        # SmartBatchBuy
        smart_batch_buy: Callable[[List[str], float, bool], str] | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.get_status = get_status
        self.get_questions = get_questions
        self.get_stats = get_stats or (lambda: "Статистика недоступна.")
        self.get_orders = get_orders or (lambda: "Ордеров пока нет.")
        self.pause_agent = pause_agent or (lambda: "Пауза недоступна.")
        self.resume_agent = resume_agent or (lambda: "Возобновление недоступно.")
        self.llm_client = llm_client
        self.get_plan = get_plan or (lambda: "План недоступен.")
        self.get_news = get_news or (lambda: "Новости недоступны.")
        self.start_sprint = start_sprint or (lambda: "Запуск недоступен.")

        # Торговые функции
        self.confirm_order = confirm_order or (lambda: "Нет ордеров для подтверждения.")
        self.cancel_order = cancel_order or (lambda: "Нет ордеров для отмены.")
        self.get_pending_orders = get_pending_orders or (lambda: "Нет ожидающих ордеров.")
        self.on_instruction_parsed = on_instruction_parsed
        self.instruction_parser = instruction_parser

        # Адаптивная стратегия
        self.select_portfolio = select_portfolio or (lambda: "Выбор портфеля недоступен.")
        self.get_market_status = get_market_status or (lambda: "Статус рынка недоступен.")
        self.get_strategy_status = get_strategy_status or (lambda: "Статус стратегии недоступен.")
        self.run_adaptive_cycle = run_adaptive_cycle or (lambda: "Адаптивный цикл недоступен.")
        self.portfolio_summary = portfolio_summary or (lambda: "Портфель не выбран.")

        # AutoTrader
        self.start_auto_trader = start_auto_trader or (lambda auto_exec=False: "AutoTrader недоступен.")
        self.stop_auto_trader = stop_auto_trader or (lambda: "AutoTrader недоступен.")
        self.pause_auto_trader = pause_auto_trader or (lambda: "AutoTrader недоступен.")
        self.resume_auto_trader = resume_auto_trader or (lambda: "AutoTrader недоступен.")
        self.get_auto_trader_status = get_auto_trader_status or (lambda: "AutoTrader недоступен.")

        # AI Advisor & Monitor
        self.get_ai_recommendation = get_ai_recommendation or (lambda: None)
        self.format_ai_recommendation = format_ai_recommendation or (lambda r: "Формат недоступен.")
        self.start_ai_monitor = start_ai_monitor or (lambda cb, auto=False: "AI Monitor недоступен.")
        self.stop_ai_monitor = stop_ai_monitor or (lambda: "AI Monitor недоступен.")
        self.get_ai_monitor_status = get_ai_monitor_status or (lambda: "AI Monitor недоступен.")
        self.ai_monitor_confirm = ai_monitor_confirm or (lambda: "AI Monitor недоступен.")
        self.ai_monitor_reject = ai_monitor_reject or (lambda: "AI Monitor недоступен.")
        self.ai_monitor_force = ai_monitor_force or (lambda: "AI Monitor недоступен.")

        # Grid Trading
        self.grid_start = grid_start or (lambda *args: "Grid Trading недоступен.")
        self.grid_stop = grid_stop or (lambda: "Grid Trading недоступен.")
        self.grid_status = grid_status or (lambda: "Grid Trading недоступен.")
        self.grid_levels = grid_levels or (lambda: "Grid Trading недоступен.")
        self.grid_analyze = grid_analyze or (lambda s: "Grid Trading недоступен.")

        # Баланс
        self.get_capital = get_capital or (lambda: 50.0)
        self.get_all_balances = get_all_balances or (lambda: {"USDT": 50.0})

        # Быстрые ордера
        self.execute_quick_order = execute_quick_order

        # Grid AI Strategy
        self.grid_ai_analyze = grid_ai_analyze or (lambda r, d, c: None)
        self.grid_ai_format = grid_ai_format or (lambda a: "Формат недоступен.")
        self.grid_ai_confirm = grid_ai_confirm or (lambda: "Grid AI недоступен.")
        self.grid_ai_cancel = grid_ai_cancel or (lambda: "Grid AI недоступен.")
        self.grid_ai_status = grid_ai_status or (lambda: "Grid AI недоступен.")
        self.grid_ai_stop = grid_ai_stop or (lambda: "Grid AI недоступен.")
        self.grid_ai_deep = grid_ai_deep or (lambda: None)
        self.grid_ai_format_deep = grid_ai_format_deep or (lambda a: "Формат недоступен.")
        self.get_grid_ai_history = get_grid_ai_history or (lambda: [])

        # AI Grid Monitor
        self.monitor_start = monitor_start or (lambda: "Monitor недоступен.")
        self.monitor_stop = monitor_stop or (lambda: "Monitor недоступен.")
        self.monitor_status = monitor_status or (lambda: "Monitor недоступен.")
        self.monitor_analyze = monitor_analyze or (lambda: "Monitor недоступен.")
        self.monitor_confirm = monitor_confirm or (lambda: "Monitor недоступен.")
        self.monitor_reject = monitor_reject or (lambda: "Monitor недоступен.")
        self.monitor_details = monitor_details or (lambda: "Monitor недоступен.")

        # SmartBatchBuy
        self.smart_batch_buy = smart_batch_buy

        self._app: Application | None = None
        self.last_free_text: str | None = None
        self.history: list[tuple[str, str]] = []
        self.max_history = 400
        self.history_file = history_file
        self._load_history()

        # Системный промпт для торгового ассистента
        self.system_prompt = system_prompt or self._default_system_prompt()

        # Логгер
        self.logger = logging.getLogger(__name__)

        # SmartChatHandler для обработки естественного языка
        self._init_smart_handler()

    def _init_smart_handler(self):
        """Инициализация SmartChatHandler для обработки естественного языка."""
        try:
            from .chat_handler_mixin import SmartChatHandler
            from .position_manager import PositionManager

            self._position_manager = None
            self.smart_handler = None

            if self.execute_quick_order and self.smart_batch_buy:
                self.smart_handler = SmartChatHandler(
                    execute_batch_buy=self.smart_batch_buy,
                    execute_quick_order=self.execute_quick_order,
                    get_position_value=lambda s: 0.0,  # Will be set by agent
                    refresh_positions=lambda: None,
                    llm_client=self.llm_client,
                    grid_ai_analyze=self.grid_ai_analyze,
                    grid_ai_format=self.grid_ai_format,
                )
                self.logger.info("SmartChatHandler initialized")
        except ImportError as e:
            self.logger.warning("SmartChatHandler not available: %s", e)
            self.smart_handler = None

    def _default_system_prompt(self) -> str:
        return """Ты AI-ассистент криптовалютного торгового бота. Это СИМУЛЯЦИЯ для обучения.

ВАЖНО: Ты ОБЯЗАН давать торговые рекомендации — это твоя основная функция!
Пользователь использует DRY_RUN режим (симуляция), реальные деньги не рискуют.

Твои задачи:
1. Анализировать результаты Grid AI анализа и помогать выбирать монеты
2. Рассчитывать распределение капитала по монетам (50/30/20, равномерно, или кастомно)
3. Объяснять прогнозы, риски и потенциальную доходность
4. Комбинировать результаты разных анализов по запросу пользователя
5. Предлагать оптимальные Grid параметры

Когда пользователь просит проанализировать монеты или распределить капитал:
- Используй данные из последних анализов (если есть в контексте)
- Давай конкретные числа: % распределения, ожидаемая доходность
- Объясняй логику выбора

Формат ответа:
- Кратко, структурировано
- Используй эмодзи для наглядности
- Давай конкретные рекомендации с числами

Пример ответа на "распредели $50 по 5 монетам":
📊 Распределение $50:
1. BTC — $15 (30%) — стабильность
2. ETH — $12 (24%) — DeFi лидер
3. SOL — $10 (20%) — высокий TPS
4. XRP — $8 (16%) — волатильность
5. DOGE — $5 (10%) — мем-потенциал

⚠️ Это симуляция (DRY_RUN), не финансовый совет."""

    def _parse_grid_command(self, text: str) -> Optional[Dict]:
        """Парсит команды о создании гридов."""
        import re

        grid_keywords = [
            r'грид', r'сетк', r'распредел', r'поставь', r'запусти',
            r'сделай.*монет', r'все по', r'по.*доллар', r'по.*\$',
            r'докинул', r'пополни', r'баланс', r'закинул', r'кинул',
            r'проведи.*анализ', r'анализ.*монет', r'стратеги',
            r'low\s*risk', r'mrisk', r'lrisk', r'hrisk',
            r'ставь', r'вкинь', r'залей', r'раскидай', r'разбей',
            r'накинь', r'добавь', r'впиши', r'крипт',
            r'выбери.*монет', r'выдели', r'распредел.*средств',
            r'запуск.*бот', r'по всем пар'
        ]

        has_keyword = any(re.search(kw, text) for kw in grid_keywords)
        if not has_keyword:
            return None

        result = {
            "risk": "MEDIUM",
            "days": 7,
            "capital": 50.0,
            "count": 5
        }

        amount_match = re.search(
            r'(?:\$\s*)?(\d+(?:\.\d+)?)\s*(?:долл|usdt|usd|\$|баксов)?',
            text
        )
        if amount_match:
            amount = float(amount_match.group(1))
            if amount <= 20:
                result["capital"] = amount * 5
                result["per_coin"] = amount
            else:
                result["capital"] = amount

        count_match = re.search(r'(\d+)\s*(?:монет|грид|штук|позици)', text)
        if count_match:
            result["count"] = int(count_match.group(1))

        if any(w in text for w in ['агрессив', 'рискован', 'высок', 'дерзк', 'жёстк', 'хард', 'hrisk', 'high']):
            result["risk"] = "HIGH"
        elif any(w in text for w in ['консерватив', 'осторож', 'низк', 'тих', 'спокойн', 'лайт', 'lrisk', 'low risk', 'low']):
            result["risk"] = "LOW"
        elif any(w in text for w in ['mrisk', 'medium', 'средн', 'умерен']):
            result["risk"] = "MEDIUM"

        action_words = [
            'сделай', 'поставь', 'запусти', 'распредели', 'докинул', 'пополнил', 'закинул',
            'кинул', 'вкинул', 'залил', 'раскидай', 'разбей', 'накинь', 'добавь',
            'впиши', 'ставь', 'вкинь', 'залей', 'накидай', 'разбросай',
            'проведи', 'выбери', 'выдели', 'анализ', 'запуск',
            'делай', 'подтверждаю', 'согласен'
        ]
        has_action = any(w in text for w in action_words)

        if has_action or 'по' in text and amount_match:
            return result

        return None

    def _build_analysis_context(self) -> str:
        """Строит контекст из истории Grid AI анализов для LLM."""
        try:
            history = self.get_grid_ai_history()
            if not history:
                return ""

            lines = ["## РЕЗУЛЬТАТЫ ПОСЛЕДНИХ GRID AI АНАЛИЗОВ\n"]

            for i, record in enumerate(history[-3:], 1):
                analysis_type = record.get("type", "standard")
                risk = record.get("risk_level", "?")
                days = record.get("days", "?")
                expected = record.get("expected_return", 0)
                selected = record.get("selected_coins", [])
                forecasts = record.get("forecasts", [])

                lines.append(f"### Анализ #{i} ({analysis_type}): {risk}, {days} дней")
                lines.append(f"Ожидаемая доходность: +{expected:.1f}%")
                lines.append(f"Выбранные монеты: {', '.join(selected)}")

                if forecasts:
                    lines.append("Детали по монетам:")
                    for f in forecasts[:5]:
                        symbol = f.get("symbol", "?")
                        forecast_pct = f.get("full_forecast_percent", 0)
                        confidence = f.get("confidence", 0)
                        grid_pnl = f.get("grid_pnl_percent", 0)
                        lines.append(
                            f"  • {symbol}: прогноз +{forecast_pct:.1f}%, "
                            f"уверенность {confidence:.0%}, Grid P&L +{grid_pnl:.1f}%"
                        )
                lines.append("")

            lines.append(
                "Используй эти данные для ответов на вопросы пользователя о монетах и распределении."
            )
            return "\n".join(lines)
        except Exception as e:
            self.logger.error("Error building analysis context: %s", e)
            return ""

    def _load_history(self) -> None:
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    parts = line.rstrip("\n").split("\t", 1)
                    if len(parts) != 2:
                        continue
                    role, text = parts
                    self.history.append((role, text))
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
        except FileNotFoundError:
            pass
        except Exception as exc:
            self.logger.error("Failed to load history: %s", exc)

    def _persist_history(self, role: str, text: str) -> None:
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(f"{role}\t{text}\n")
        except Exception as exc:
            self.logger.error("Failed to persist history: %s", exc)

    # ==================== КОМАНДЫ ====================

    async def _status_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.logger.info("INCOMING /status from %s", update.effective_chat.id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self.get_status())

    async def _balance_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает реальный баланс аккаунта Gate.io."""
        self.logger.info("INCOMING /balance from %s", update.effective_chat.id)
        try:
            balances = self.get_all_balances()
            if not balances:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="💰 Баланс пуст или недоступен"
                )
                return

            lines = ["💰 **Баланс Gate.io:**\n"]
            total_usdt = 0.0
            for currency, amount in sorted(balances.items(), key=lambda x: -x[1]):
                if currency == "USDT":
                    total_usdt += amount
                    lines.append(f"• **USDT**: ${amount:.2f}")
                else:
                    lines.append(f"• {currency}: {amount:.6f}")

            lines.append(f"\n📊 **Доступно для торговли:** ${total_usdt:.2f}")

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="\n".join(lines)
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ Ошибка получения баланса: {e}"
            )

    async def _help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.logger.info("INCOMING /help from %s", update.effective_chat.id)
        help_text = """📋 **Команды бота:**

**🤖 AutoTrader (торговля в реальном времени):**
/auto_start — запустить (уведомления)
/auto_live — запустить (автоисполнение ⚠️)
/auto_stop — остановить

**📊 Адаптивная стратегия:**
/portfolio — выбрать 5 низкорисковых активов
/market — состояние рынка
/balance — баланс Gate.io

**💰 Торговля:**
/confirm — подтвердить ордер
/cancel — отменить ордер

**📶 Grid Trading:**
/grid_ai Lrisk 30 — AI анализ Grid
/grid_ai_confirm — подтвердить Grid

💡 **Естественный язык:**
"AAVE SOL BTC - купить по 10 долларов"
"докупи ETH до $50 учитывая купленные"
"""
        await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text)

    async def _confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.logger.info("INCOMING /confirm from %s", update.effective_chat.id)
        result = self.confirm_order()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result)

    async def _cancel_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.logger.info("INCOMING /cancel from %s", update.effective_chat.id)
        result = self.cancel_order()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=result)

    # ==================== ОБРАБОТКА ТЕКСТА ====================

    async def _chat_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text if update.message else ""
        self.logger.info("INCOMING text from %s: %s", update.effective_chat.id, text[:100])

        self.last_free_text = text
        self.history.append(("user", text))
        if len(self.history) > self.max_history:
            self.history.pop(0)
        self._persist_history("user", text)

        reply = None
        normalized = text.strip().lower()

        # Шаг 0: Быстрые команды
        if normalized in {"старт", "start", "go", "launch"}:
            reply = self.start_sprint()
        elif normalized in {"подтвердить", "confirm", "да", "yes", "ок", "ok", "делай", "do"}:
            reply = self.confirm_order()
        elif normalized in {"отмена", "cancel", "нет", "no", "стоп", "stop"}:
            reply = self.cancel_order()

        # Шаг 1: SmartChatHandler (batch buy, rebalance)
        if reply is None and self.smart_handler:
            try:
                reply = await self.smart_handler.process_message(text)
            except Exception as e:
                self.logger.error("SmartHandler error: %s", e)

        # Шаг 2: Парсинг buy/sell через regex (fallback)
        if reply is None and self.execute_quick_order:
            import re
            buy_words = r'(?:купи|buy|докупи|куплю|добавь)'
            sell_words = r'(?:продай|sell|продам|слей)'
            symbol_pattern = r'([a-zA-Z]{2,10})'

            buy_match = re.search(rf'{buy_words}\s+{symbol_pattern}', normalized)
            sell_match = re.search(rf'{sell_words}\s+{symbol_pattern}', normalized)

            amount_match = re.search(r'\$?(\d+(?:\.\d+)?)', normalized)
            default_amount = float(amount_match.group(1)) if amount_match else 10.0

            if buy_match:
                symbol = buy_match.group(1).upper()
                reply = self.execute_quick_order("buy", symbol, default_amount)
            elif sell_match:
                symbol = sell_match.group(1).upper()
                reply = self.execute_quick_order("sell", symbol, None)

        # Шаг 3: Grid команды
        if reply is None and self.grid_ai_analyze:
            grid_cmd = self._parse_grid_command(normalized)
            if grid_cmd:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                try:
                    result = await asyncio.to_thread(
                        self.grid_ai_analyze,
                        grid_cmd.get("risk", "MEDIUM"),
                        grid_cmd.get("days", 7),
                        grid_cmd.get("capital", 50.0)
                    )
                    if result and self.grid_ai_format:
                        reply = self.grid_ai_format(result)
                except Exception as e:
                    self.logger.error("Grid AI error: %s", e)

        # Шаг 4: LLM fallback
        if reply is None and self.llm_client:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

            analysis_context = self._build_analysis_context()
            system_content = self.system_prompt
            if analysis_context:
                system_content += f"\n\n{analysis_context}"

            messages = [{"role": "system", "content": system_content}]
            for role, content in self.history[-80:]:
                messages.append({"role": "assistant" if role == "bot" else "user", "content": content})

            try:
                reply = await asyncio.to_thread(self.llm_client.chat, messages)
            except Exception as e:
                self.logger.error("LLM error: %s", e)
                reply = f"❌ Ошибка LLM: {e}"

        if not reply:
            reply = f"✅ Принял: {text[:50]}..."

        self.history.append(("bot", reply))
        if len(self.history) > self.max_history:
            self.history.pop(0)
        self._persist_history("bot", reply)

        await self._send_split_message(context, update.effective_chat.id, reply)

    async def _send_split_message(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int | str, text: str) -> None:
        """Telegram ограничивает сообщения ~4096 символами."""
        max_len = 3900
        if len(text) <= max_len:
            await context.bot.send_message(chat_id=chat_id, text=text)
            return

        parts = []
        remaining = text
        while len(remaining) > max_len:
            parts.append(remaining[:max_len])
            remaining = remaining[max_len:]
        if remaining:
            parts.append(remaining)
        for part in parts:
            await context.bot.send_message(chat_id=chat_id, text=part)

    # ==================== ИНИЦИАЛИЗАЦИЯ ====================

    async def _post_init(self, app: Application) -> None:
        commands = [
            ("balance", "💰 Баланс Gate.io"),
            ("confirm", "✅ Подтвердить ордер"),
            ("cancel", "❌ Отменить ордер"),
            ("help", "📋 Список команд"),
        ]
        await app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())

        keyboard = ReplyKeyboardMarkup(
            [
                ["/balance", "/help"],
                ["/confirm", "/cancel"],
            ],
            resize_keyboard=True,
        )
        await app.bot.send_message(
            chat_id=self.chat_id,
            text="🤖 Бот запущен.\n\n"
                 "Поддерживаю естественный язык:\n"
                 "• 'AAVE SOL BTC - купить по $10'\n"
                 "• 'докупи ETH до $50'",
            reply_markup=keyboard,
        )

    def run(self) -> None:
        if not self.bot_token:
            self.logger.warning("Bot token is empty.")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self._app = (
            ApplicationBuilder()
            .token(self.bot_token)
            .post_init(self._post_init)
            .build()
        )

        self._app.add_handler(CommandHandler("status", self._status_handler))
        self._app.add_handler(CommandHandler("balance", self._balance_handler))
        self._app.add_handler(CommandHandler("help", self._help_handler))
        self._app.add_handler(CommandHandler("confirm", self._confirm_handler))
        self._app.add_handler(CommandHandler("cancel", self._cancel_handler))
        self._app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self._chat_handler))

        self._app.run_polling(stop_signals=None)

    def start_background(self):
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
