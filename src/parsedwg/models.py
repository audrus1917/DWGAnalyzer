from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedItem:
    """Нормализованная строка, извлечённая из чертежа или заметки."""

    name: str
    quantity: float
    unit: str
    section: str
    source: str
    note: str = ""
    unit_price: float = 0.0

    @property
    def total_price(self) -> float:
        return round(self.quantity * self.unit_price, 2)
