"""
PositionManager — отслеживание текущих позиций и балансов для rebalance логики.

Ключевые функции:
- Получение текущей стоимости позиций в USDT
- Расчёт суммы докупки до целевого значения
- Учёт уже купленных монет при batch buy
"""

import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class PositionInfo:
    """Информация о позиции."""
    symbol: str
    currency: str
    amount: float
    price: float
    value_usdt: float


class PositionManager:
    """
    Менеджер позиций для учёта текущих балансов.

    Использование:
        pm = PositionManager(trader)
        pm.refresh()  # Обновить данные

        # Получить текущую стоимость позиции
        value = pm.get_position_value("BTC_USDT")

        # Рассчитать сколько докупить
        to_buy = pm.calculate_additional_amount("BTC_USDT", target_usdt=10.0)
    """

    def __init__(self, trader: Any) -> None:
        """
        Args:
            trader: TradeExecutor с методами get_all_balances() и _spot_api
        """
        self.trader = trader
        self.positions: Dict[str, PositionInfo] = {}
        self.logger = logging.getLogger(__name__)
        self._last_refresh = 0

    def refresh(self) -> Dict[str, PositionInfo]:
        """
        Обновляет данные о позициях с биржи.

        Returns:
            Dict символов и их информации
        """
        import time
        self.positions.clear()

        try:
            balances = self.trader.get_all_balances()

            for currency, amount in balances.items():
                if currency == "USDT" or amount <= 0:
                    continue

                symbol = f"{currency}_USDT"

                try:
                    # Получаем текущую цену
                    ticker = self.trader._spot_api.list_tickers(currency_pair=symbol)
                    if ticker:
                        price = float(ticker[0].last)
                        value_usdt = amount * price

                        self.positions[symbol] = PositionInfo(
                            symbol=symbol,
                            currency=currency,
                            amount=amount,
                            price=price,
                            value_usdt=value_usdt,
                        )

                except Exception as e:
                    self.logger.warning("Failed to get price for %s: %s", symbol, e)
                    continue

            self._last_refresh = time.time()
            self.logger.info("Refreshed %d positions", len(self.positions))

        except Exception as e:
            self.logger.error("Failed to refresh positions: %s", e)

        return self.positions

    def get_position_value(self, symbol: str) -> float:
        """
        Возвращает текущую стоимость позиции в USDT.

        Args:
            symbol: Торговая пара (например, "BTC_USDT")

        Returns:
            Стоимость в USDT или 0 если позиции нет
        """
        # Нормализуем символ
        if "_USDT" not in symbol:
            symbol = f"{symbol}_USDT"

        position = self.positions.get(symbol)
        return position.value_usdt if position else 0.0

    def get_position_amount(self, symbol: str) -> float:
        """
        Возвращает количество монет в позиции.

        Args:
            symbol: Торговая пара

        Returns:
            Количество монет или 0
        """
        if "_USDT" not in symbol:
            symbol = f"{symbol}_USDT"

        position = self.positions.get(symbol)
        return position.amount if position else 0.0

    def calculate_additional_amount(self, symbol: str, target_usdt: float) -> float:
        """
        Рассчитывает сколько USDT нужно докупить до целевой суммы.

        Args:
            symbol: Торговая пара
            target_usdt: Целевая сумма в USDT

        Returns:
            Сумма для докупки (>=0)
        """
        current_value = self.get_position_value(symbol)
        additional = target_usdt - current_value
        return max(0.0, additional)

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Возвращает текущую цену монеты.

        Args:
            symbol: Торговая пара

        Returns:
            Цена или None
        """
        if "_USDT" not in symbol:
            symbol = f"{symbol}_USDT"

        position = self.positions.get(symbol)
        if position:
            return position.price

        # Если позиции нет, получаем цену напрямую
        try:
            ticker = self.trader._spot_api.list_tickers(currency_pair=symbol)
            if ticker:
                return float(ticker[0].last)
        except Exception:
            pass

        return None

    def summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку по всем позициям.

        Returns:
            Dict с общей информацией
        """
        total_value = sum(p.value_usdt for p in self.positions.values())

        return {
            "total_positions": len(self.positions),
            "total_value_usdt": total_value,
            "positions": [
                {
                    "symbol": p.symbol,
                    "amount": p.amount,
                    "value_usdt": p.value_usdt,
                    "price": p.price,
                }
                for p in sorted(
                    self.positions.values(),
                    key=lambda x: x.value_usdt,
                    reverse=True
                )
            ]
        }

    def format_summary(self) -> str:
        """Форматирует сводку для Telegram."""
        data = self.summary()

        if not data["positions"]:
            return "📭 Нет открытых позиций (кроме USDT)"

        lines = [
            "💼 **ТЕКУЩИЕ ПОЗИЦИИ**",
            f"Всего: {data['total_positions']} монет",
            f"Общая стоимость: ${data['total_value_usdt']:.2f}",
            ""
        ]

        for p in data["positions"][:10]:  # Топ-10
            lines.append(
                f"• {p['symbol']}: {p['amount']:.6f} "
                f"(${p['value_usdt']:.2f})"
            )

        return "\n".join(lines)
