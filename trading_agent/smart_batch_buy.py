"""
SmartBatchBuy — умный batch buy с учётом текущих позиций.

Ключевые функции:
- Покупка списка монет на заданную сумму каждую
- Rebalance: докупка до целевой суммы с учётом имеющихся монет
- Валидация минимальных сумм ордеров
- Подробный отчёт о выполнении
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .position_manager import PositionManager


class OrderResult(Enum):
    """Результат исполнения ордера."""
    SUCCESS = "success"
    SKIPPED_ENOUGH = "skipped_enough"  # Уже достаточно монет
    SKIPPED_MIN_AMOUNT = "skipped_min"  # Сумма меньше минимума
    FAILED = "failed"
    PAIR_NOT_FOUND = "not_found"


@dataclass
class BatchBuyResult:
    """Результат batch buy."""
    symbol: str
    result: OrderResult
    amount_usdt: float = 0.0
    coin_amount: float = 0.0
    price: float = 0.0
    current_value: float = 0.0  # Для rebalance
    order_id: Optional[str] = None
    error: Optional[str] = None


class SmartBatchBuy:
    """
    Умный batch buy с учётом текущих позиций.

    Использование:
        batch_buy = SmartBatchBuy(trader, position_manager)

        # Обычная покупка
        result = batch_buy.execute(
            symbols=["BTC", "ETH", "SOL"],
            amount_per_coin=10.0,
            rebalance=False
        )

        # Rebalance (докупка до целевой суммы)
        result = batch_buy.execute(
            symbols=["BTC", "ETH", "SOL"],
            amount_per_coin=10.0,
            rebalance=True
        )
    """

    MIN_ORDER_USDT = 3.0  # Минимальная сумма ордера Gate.io

    def __init__(self, trader: Any, position_manager: PositionManager) -> None:
        """
        Args:
            trader: TradeExecutor с методом place_spot_order
            position_manager: PositionManager для учёта позиций
        """
        self.trader = trader
        self.position_manager = position_manager
        self.logger = logging.getLogger(__name__)

    def execute(
        self,
        symbols: List[str],
        amount_per_coin: float,
        rebalance: bool = False,
        dry_run: bool = False,
    ) -> Tuple[List[BatchBuyResult], str]:
        """
        Выполняет batch buy.

        Args:
            symbols: Список символов (без _USDT)
            amount_per_coin: Целевая сумма на монету в USDT
            rebalance: Учитывать уже купленные монеты
            dry_run: Только симуляция (не выполнять ордера)

        Returns:
            Tuple[список результатов, форматированный отчёт]
        """
        results: List[BatchBuyResult] = []
        total_spent = 0.0

        # Обновляем позиции если rebalance
        if rebalance:
            self.position_manager.refresh()

        for symbol in symbols:
            result = self._process_symbol(
                symbol=symbol,
                target_amount=amount_per_coin,
                rebalance=rebalance,
                dry_run=dry_run,
            )
            results.append(result)

            if result.result == OrderResult.SUCCESS:
                total_spent += result.amount_usdt

        # Формируем отчёт
        report = self._format_report(results, total_spent, rebalance)

        return results, report

    def _process_symbol(
        self,
        symbol: str,
        target_amount: float,
        rebalance: bool,
        dry_run: bool,
    ) -> BatchBuyResult:
        """
        Обрабатывает один символ.

        Args:
            symbol: Символ монеты
            target_amount: Целевая сумма в USDT
            rebalance: Режим rebalance
            dry_run: Симуляция

        Returns:
            BatchBuyResult
        """
        # Нормализуем символ
        symbol_clean = symbol.upper().replace("_USDT", "")
        symbol_full = f"{symbol_clean}_USDT"

        result = BatchBuyResult(
            symbol=symbol_full,
            result=OrderResult.FAILED,
        )

        try:
            # Получаем текущую цену
            ticker = self.trader._spot_api.list_tickers(currency_pair=symbol_full)
            if not ticker:
                result.result = OrderResult.PAIR_NOT_FOUND
                result.error = "Пара не найдена на Gate.io"
                return result

            current_price = float(ticker[0].last)
            result.price = current_price

            # Рассчитываем сколько купить
            if rebalance:
                current_value = self.position_manager.get_position_value(symbol_full)
                result.current_value = current_value

                if current_value >= target_amount:
                    result.result = OrderResult.SKIPPED_ENOUGH
                    result.error = f"Уже ${current_value:.2f} >= ${target_amount:.2f}"
                    return result

                amount_to_buy = target_amount - current_value
            else:
                amount_to_buy = target_amount

            # Проверяем минимальную сумму
            if amount_to_buy < self.MIN_ORDER_USDT:
                result.result = OrderResult.SKIPPED_MIN_AMOUNT
                result.error = f"Мин. ордер ${self.MIN_ORDER_USDT}, запрошено ${amount_to_buy:.2f}"
                return result

            # Конвертируем в количество монет
            coin_amount = amount_to_buy / current_price
            result.amount_usdt = amount_to_buy
            result.coin_amount = coin_amount

            # Выполняем ордер
            if dry_run:
                result.result = OrderResult.SUCCESS
                result.order_id = "DRY_RUN"
                return result

            order_result = self.trader.place_spot_order(
                symbol_full,
                "buy",
                str(coin_amount)
            )

            if order_result and order_result.success:
                result.result = OrderResult.SUCCESS
                result.order_id = order_result.order_id
            else:
                result.result = OrderResult.FAILED
                result.error = order_result.error if order_result else "Unknown error"

        except Exception as e:
            self.logger.error("Error processing %s: %s", symbol_full, e)
            result.result = OrderResult.FAILED
            result.error = str(e)

        return result

    def _format_report(
        self,
        results: List[BatchBuyResult],
        total_spent: float,
        rebalance: bool,
    ) -> str:
        """
        Форматирует отчёт о batch buy.

        Args:
            results: Список результатов
            total_spent: Общая сумма покупок
            rebalance: Был ли режим rebalance

        Returns:
            Форматированная строка
        """
        lines = []

        # Заголовок
        mode = "Rebalance" if rebalance else "Batch Buy"
        lines.append(f"📦 **{mode}** — {len(results)} монет")
        lines.append("")

        # Результаты по каждой монете
        success_count = 0
        skip_count = 0
        fail_count = 0

        for r in results:
            symbol_short = r.symbol.replace("_USDT", "")

            if r.result == OrderResult.SUCCESS:
                success_count += 1
                action = "Докуплено" if rebalance and r.current_value > 0 else "Куплено"
                lines.append(
                    f"✅ {symbol_short}: {action} ${r.amount_usdt:.2f} "
                    f"({r.coin_amount:.6f} @ ${r.price:,.2f})"
                )

            elif r.result == OrderResult.SKIPPED_ENOUGH:
                skip_count += 1
                lines.append(f"➡️ {symbol_short}: уже достаточно (${r.current_value:.2f})")

            elif r.result == OrderResult.SKIPPED_MIN_AMOUNT:
                skip_count += 1
                lines.append(f"⚠️ {symbol_short}: {r.error}")

            elif r.result == OrderResult.PAIR_NOT_FOUND:
                fail_count += 1
                lines.append(f"❌ {symbol_short}: не найдена на бирже")

            else:
                fail_count += 1
                lines.append(f"❌ {symbol_short}: ошибка — {r.error}")

        # Итог
        lines.append("")
        lines.append("📊 **ИТОГ:**")
        lines.append(f"• Успешно: {success_count}")
        lines.append(f"• Пропущено: {skip_count}")
        lines.append(f"• Ошибок: {fail_count}")
        lines.append(f"• Потрачено: ${total_spent:.2f}")

        return "\n".join(lines)


# === Интеграция с TradingAgent ===
def integrate_smart_batch_buy(agent: Any) -> None:
    """
    Интегрирует SmartBatchBuy в существующий TradingAgent.

    Добавляет методы:
    - agent.smart_batch_buy(symbols, amount, rebalance)
    - agent.execute_batch_buy_command(text)

    Использование:
        from trading_agent.smart_batch_buy import integrate_smart_batch_buy
        integrate_smart_batch_buy(agent)

        result = agent.smart_batch_buy(["BTC", "ETH"], 10.0, rebalance=True)
    """
    from .position_manager import PositionManager
    from .intent_parser import IntentParser, IntentType

    # Создаём компоненты
    position_manager = PositionManager(agent.trader)
    batch_buy = SmartBatchBuy(agent.trader, position_manager)
    intent_parser = IntentParser()

    # Добавляем методы в agent
    agent._position_manager = position_manager
    agent._smart_batch_buy = batch_buy
    agent._intent_parser = intent_parser

    def smart_batch_buy(
        symbols: List[str],
        amount_per_coin: float,
        rebalance: bool = False,
    ) -> str:
        """Умный batch buy через agent."""
        results, report = batch_buy.execute(
            symbols=symbols,
            amount_per_coin=amount_per_coin,
            rebalance=rebalance,
            dry_run=agent.dry_run,
        )
        return report

    def execute_batch_buy_command(text: str) -> Optional[str]:
        """
        Парсит и выполняет batch buy команду.

        Returns:
            Отчёт о выполнении или None если это не batch buy команда
        """
        result = intent_parser.parse(text)

        if result.intent not in (IntentType.BATCH_BUY, IntentType.SINGLE_BUY, IntentType.REBALANCE):
            return None

        if not result.symbols:
            return "❌ Не найдены символы монет в запросе"

        if result.target_amount <= 0:
            result.target_amount = 10.0  # Default

        results, report = batch_buy.execute(
            symbols=result.symbols,
            amount_per_coin=result.target_amount,
            rebalance=result.rebalance,
            dry_run=agent.dry_run,
        )

        return report

    # Привязываем методы
    agent.smart_batch_buy = smart_batch_buy
    agent.execute_batch_buy_command = execute_batch_buy_command

    logging.getLogger(__name__).info("SmartBatchBuy integrated into TradingAgent")


# === Тесты ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("SmartBatchBuy module loaded. Import and integrate with TradingAgent.")
