"""
analytics.py — звітність над замовленнями крамниці.

Модуль рахує три речі:
  · виторг за період;
  · середній чек;
  · топ товарів за кількістю проданого.

Замовлення — це список словників:

    {"date": "2026-01-10", "product": "Ноутбук",
     "quantity": 1, "unit_price": 25000.0}

Тести в test_analytics.py падають. Ваше завдання — не переписати
модуль, а знайти причину кожного падіння.
"""
from statistics import mean

VAT_RATE = 0.20


def line_total(quantity, unit_price):
    """Вартість позиції без ПДВ."""
    return quantity * unit_price


def with_vat(amount):
    """Сума з ПДВ, заокруглена до копійок."""
    return round(amount * (1 + VAT_RATE), 2)


def orders_in_period(orders, start, end):
    """
    Замовлення, оформлені в проміжку від start до end включно.

    Дати — рядки у форматі YYYY-MM-DD, тож порівнювати їх можна
    безпосередньо, без розбору в datetime.
    """
    return [o for o in orders if start < o["date"] < end]


def revenue(orders):
    """Виторг без ПДВ по переданих замовленнях."""
    return sum(line_total(o["quantity"], o["unit_price"]) for o in orders)


def average_check_by_month(orders):
    """Середній чек за кожен місяць: {"2026-01": 14300.0, ...}"""
    by_month = {}
    for o in orders:
        month = o["date"][:7]
        by_month.setdefault(month, []).append(
            line_total(o["quantity"], o["unit_price"]))
    return {m: round(mean(totals), 2) for m, totals in by_month.items()}


def average_check(orders):
    """Середній чек по всіх замовленнях разом."""
    monthly = average_check_by_month(orders)
    return round(mean(monthly.values()), 2)


def top_products(orders, limit=3, sold={}):
    """
    Топ-limit товарів за сумарною кількістю проданого.

    Повертає список пар (назва, кількість), відсортований за спаданням.
    """
    for o in orders:
        sold[o["product"]] = sold.get(o["product"], 0) + o["quantity"]
    ranked = sorted(sold.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:limit]
