"""
TradingAgent — ядро торгового агента.
Интегрирует SmartBatchBuy для обработки естественного языка.
"""

import logging
from typing import List, Optional, Dict, Any

from .smart_batch_buy import SmartBatchBuy, integrate_smart_batch_buy
from .position_manager import PositionManager


class TradingAgent:
    """
    Торговый агент с поддержкой SmartBatchBuy.
    """

    def __init__(self, config_path: str = "config.ini") -> None:
        self.logger = logging.getLogger(__name__)

        # Базовые параметры
        self.capital = 50.0
        self.dry_run = True

        # Trader будет инициализирован из конфига
        self.trader = None

        # Telegram
        self.telegram_enabled = False
        self.bot_token = ""
        self.chat_id = ""
        self._telegram_bot = None

        # LLM Client
        self.llm_client = None

        # Инициализация компонентов
        self._init_from_config(config_path)

        # Интегрируем SmartBatchBuy
        if self.trader:
            integrate_smart_batch_buy(self)
            self.logger.info("SmartBatchBuy integrated")

    def _init_from_config(self, config_path: str) -> None:
        """Инициализация из конфига."""
        try:
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(config_path)

            # Gate.io
            if "gateio" in cfg:
                gate = cfg["gateio"]
                api_key = gate.get("api_key", "")
                api_secret = gate.get("api_secret", "")

                if api_key and api_secret:
                    from .trade_executor import TradeExecutor
                    self.trader = TradeExecutor(
                        api_key=api_key,
                        api_secret=api_secret,
                        dry_run=self.dry_run,
                    )

            # Telegram
            if "telegram" in cfg:
                tg = cfg["telegram"]
                self.telegram_enabled = tg.getboolean("notifications_enabled", fallback=False)
                self.bot_token = tg.get("bot_token", "")
                self.chat_id = tg.get("chat_id", "")

            # Agent
            if "agent" in cfg:
                agent = cfg["agent"]
                self.capital = float(agent.get("capital", "50"))
                self.dry_run = agent.getboolean("dry_run", fallback=True)

        except Exception as e:
            self.logger.warning("Config load error: %s", e)

    def get_capital(self) -> float:
        """Возвращает актуальный капитал."""
        if self.trader:
            try:
                balance = self.trader.get_balance("USDT")
                if balance > 0:
                    return balance
            except Exception:
                pass
        return self.capital

    def get_all_balances(self) -> dict:
        """Возвращает все балансы с биржи."""
        if self.trader:
            return self.trader.get_all_balances()
        return {"USDT": self.capital}

    def execute_quick_order(self, side: str, symbol: str, amount: float | None = None) -> str:
        """Быстрое исполнение ордера."""
        if not self.trader:
            return "❌ Trader не инициализирован"

        symbol = symbol.upper()
        if "_USDT" not in symbol:
            symbol = f"{symbol}_USDT"

        try:
            ticker = self.trader._spot_api.list_tickers(currency_pair=symbol)
            if not ticker:
                return f"❌ Пара {symbol} не найдена"
            current_price = float(ticker[0].last)
        except Exception as e:
            return f"❌ Ошибка получения цены: {e}"

        if amount is None:
            amount = min(10.0, self.capital * 0.2)
        if amount < 3.0:
            return f"❌ Минимум ордера $3 (запрошено ${amount:.2f})"

        side = side.lower()
        if side == "buy":
            coin_amount = amount / current_price
            result = self.trader.place_spot_order(symbol, "buy", str(coin_amount))
            if result and result.success:
                return f"✅ BUY {symbol}: ${amount:.2f} @ ${current_price:,.2f}"
            else:
                return f"❌ Ошибка: {result.error if result else 'unknown'}"
        elif side == "sell":
            coin = symbol.replace("_USDT", "")
            balances = self.get_all_balances()
            coin_balance = balances.get(coin, 0)
            if coin_balance <= 0:
                return f"❌ Нет {coin} для продажи"
            result = self.trader.place_spot_order(symbol, "sell", str(coin_balance))
            if result and result.success:
                return f"✅ SELL {symbol}: {coin_balance:.6f}"
            else:
                return f"❌ Ошибка: {result.error if result else 'unknown'}"

        return f"❌ Неизвестная команда: {side}"

    def confirm_order(self) -> str:
        """Подтверждает pending ордер."""
        if self.trader:
            order = self.trader.confirm_order()
            if order:
                return f"✅ Ордер подтверждён: {order.id[-6:]}"
        return "❌ Нет ордеров для подтверждения"

    def cancel_order(self) -> str:
        """Отменяет pending ордер."""
        if self.trader:
            order = self.trader.cancel_order()
            if order:
                return f"🚫 Ордер отменён: {order.id[-6:]}"
        return "❌ Нет ордеров для отмены"

    def start_telegram_bot(self) -> None:
        """Запускает Telegram бот."""
        if not self.telegram_enabled:
            self.logger.info("Telegram disabled")
            return

        from .telegram_bot import TelegramBot

        # Wrapper для smart_batch_buy
        def smart_batch_buy_wrapper(symbols: List[str], amount: float, rebalance: bool) -> str:
            if hasattr(self, 'smart_batch_buy'):
                return self.smart_batch_buy(symbols, amount, rebalance)
            return "❌ SmartBatchBuy не инициализирован"

        self._telegram_bot = TelegramBot(
            bot_token=self.bot_token,
            chat_id=self.chat_id,
            get_status=lambda: "✅ Агент работает",
            get_questions=lambda: [],
            get_capital=self.get_capital,
            get_all_balances=self.get_all_balances,
            execute_quick_order=self.execute_quick_order,
            confirm_order=self.confirm_order,
            cancel_order=self.cancel_order,
            smart_batch_buy=smart_batch_buy_wrapper,
            llm_client=self.llm_client,
        )
        self._telegram_bot.start_background()
        self.logger.info("Telegram bot started")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = TradingAgent(config_path="config.ini")
    agent.start_telegram_bot()

    import time
    while True:
        time.sleep(3600)
