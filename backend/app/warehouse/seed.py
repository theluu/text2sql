"""Deterministic synthetic retail data (vi_VN) for the warehouse."""

from __future__ import annotations

import math
import random
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import psycopg
from faker import Faker
from psycopg import sql

ICT = timezone(timedelta(hours=7))
PERIOD_START = date(2024, 1, 1)
PERIOD_END = date(2026, 8, 31)

# (region_id, name, name_en, cities)
REGIONS: list[tuple[int, str, str, list[str]]] = [
    (1, "Đồng bằng sông Hồng", "Red River Delta", ["Hà Nội", "Hải Phòng", "Bắc Ninh"]),
    (2, "Trung du và miền núi phía Bắc", "Northern Midlands", ["Thái Nguyên", "Lào Cai"]),
    (3, "Duyên hải miền Trung", "Central Coast", ["Đà Nẵng", "Huế", "Nha Trang"]),
    (4, "Tây Nguyên", "Central Highlands", ["Buôn Ma Thuột", "Đà Lạt"]),
    (5, "Đông Nam Bộ", "Southeast", ["TP. Hồ Chí Minh", "Biên Hòa", "Thủ Dầu Một"]),
    (6, "Đồng bằng sông Cửu Long", "Mekong Delta", ["Cần Thơ", "Long Xuyên"]),
]
REGION_WEIGHTS = [0.28, 0.05, 0.14, 0.05, 0.38, 0.10]

# (category_id, name, name_en, parent_id, price_min, price_max, brands)
CATEGORIES: list[tuple[int, str, str, int | None, int, int, list[str]]] = [
    (1, "Điện tử", "Electronics", None, 0, 0, []),
    (2, "Thời trang", "Fashion", None, 0, 0, []),
    (3, "Nhà cửa & Đời sống", "Home & Living", None, 0, 0, []),
    (4, "Sắc đẹp", "Beauty", None, 0, 0, []),
    (5, "Thực phẩm", "Grocery", None, 0, 0, []),
    (6, "Điện thoại", "Smartphones", 1, 2_500_000, 35_000_000,
     ["Samsung", "Apple", "Xiaomi", "OPPO", "vivo"]),
    (7, "Laptop", "Laptops", 1, 9_000_000, 55_000_000, ["Dell", "HP", "Lenovo", "ASUS", "Apple"]),
    (8, "Phụ kiện điện tử", "Electronic Accessories", 1, 90_000, 2_500_000,
     ["Anker", "Baseus", "Ugreen", "Sony"]),
    (9, "Thời trang nam", "Men's Fashion", 2, 150_000, 1_800_000,
     ["Owen", "Routine", "Coolmate", "Uniqlo"]),
    (10, "Thời trang nữ", "Women's Fashion", 2, 150_000, 2_200_000,
     ["IVY moda", "Elise", "Uniqlo", "Zara"]),
    (11, "Giày dép", "Footwear", 2, 250_000, 3_500_000, ["Biti's", "Nike", "Adidas", "Ananas"]),
    (12, "Đồ gia dụng", "Home Appliances", 3, 200_000, 12_000_000,
     ["Sunhouse", "Philips", "Panasonic", "Lock&Lock"]),
    (13, "Nội thất", "Furniture", 3, 500_000, 15_000_000, ["IKEA", "Hòa Phát", "Nhà Xinh"]),
    (14, "Mỹ phẩm", "Cosmetics", 4, 80_000, 1_500_000,
     ["Cocoon", "La Roche-Posay", "Innisfree", "L'Oréal"]),
    (15, "Đồ uống & Snack", "Beverages & Snacks", 5, 10_000, 350_000,
     ["Vinamilk", "TH true MILK", "Oishi", "Trung Nguyên"]),
]  # fmt: skip
LEAF_CATEGORIES = [c for c in CATEGORIES if c[3] is not None]

# (title, salary_min, salary_max, weight)
POSITIONS = [
    ("Nhân viên bán hàng", 7_000_000, 11_000_000, 0.60),
    ("Thu ngân", 7_500_000, 10_000_000, 0.20),
    ("Kho vận", 8_000_000, 12_000_000, 0.15),
    ("Quản lý cửa hàng", 18_000_000, 32_000_000, 0.05),
]
PAYMENT_METHODS = ["cash", "card", "momo", "zalopay", "bank_transfer", "cod"]
PAYMENT_WEIGHTS = [0.22, 0.25, 0.20, 0.10, 0.13, 0.10]
RETURN_REASONS = [
    "Sản phẩm lỗi",
    "Không đúng mô tả",
    "Giao sai hàng",
    "Đổi ý",
    "Hư hỏng khi vận chuyển",
]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com"]
MOBILE_PREFIXES = ["090", "091", "093", "097", "098", "086", "088", "070", "079"]
SEGMENT_ORDER_WEIGHT = {"regular": 1.0, "silver": 2.0, "gold": 3.5, "platinum": 6.0}
# (name, month, day, length_days, discount_percent)
SEASONAL_PROMOS = [("Sale Tết", 1, 10, 20, 10), ("Siêu sale 11.11", 11, 9, 4, 30),
                   ("Sale 12.12", 12, 10, 4, 20)]  # fmt: skip

BASE_COUNTS = {"stores": 30, "employees": 300, "customers": 20_000, "products": 800,
               "promotions": 40, "orders": 60_000}  # fmt: skip
MIN_COUNTS = {"stores": 6, "employees": 12, "customers": 50, "products": 20,
              "promotions": 4, "orders": 100}  # fmt: skip

Promo = tuple[int, str, int, date, date]  # id, name, percent, starts, ends
Product = tuple[int, str, str, int, str, int, int, bool]


def _scaled(name: str, scale: float) -> int:
    return max(MIN_COUNTS[name], round(BASE_COUNTS[name] * scale))


def _slug(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(ch for ch in ascii_text.lower() if ch.isalnum())


def _round_thousand(value: float) -> int:
    return max(1000, int(round(value / 1000.0)) * 1000)


def _day_weight(day: date) -> float:
    weight = 1.0
    if day.month == 1 or (day.month == 2 and day.day <= 15):
        weight *= 1.6  # Tết
    if (day.month, day.day) == (11, 11):
        weight *= 4.0
    elif (day.month, day.day) == (12, 12):
        weight *= 3.0
    if day.weekday() >= 5:
        weight *= 1.2
    progress = (day - PERIOD_START).days / (PERIOD_END - PERIOD_START).days
    return weight * (1 + 0.35 * progress)


def _copy(
    conn: psycopg.Connection[Any], table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]
) -> None:
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with conn.cursor() as cur, cur.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)


def seed(conn: psycopg.Connection[Any], scale: float = 1.0, seed_value: int = 42) -> None:
    rng = random.Random(seed_value)
    fake = Faker("vi_VN")
    fake.seed_instance(seed_value)
    total_days = (PERIOD_END - PERIOD_START).days

    _copy(conn, "regions", ("region_id", "name", "name_en"), [r[:3] for r in REGIONS])

    # Stores: store 1 is the online channel, the rest are physical shops.
    stores: list[tuple[int, str, str, int, str, date]] = [
        (1, "Datum Online", "TP. Hồ Chí Minh", 5, "online", date(2023, 6, 1))
    ]
    for store_id in range(2, _scaled("stores", scale) + 1):
        region = rng.choices(REGIONS, weights=REGION_WEIGHTS)[0]
        city = rng.choice(region[3])
        opened = PERIOD_START - timedelta(days=rng.randint(30, 1500))
        stores.append(
            (store_id, f"Datum {city} {store_id:02d}", city, region[0], "offline", opened)
        )
    _copy(conn, "stores", ("store_id", "name", "city", "region_id", "channel", "opened_on"), stores)
    offline = [s for s in stores if s[4] == "offline"]

    staff: dict[int, list[int]] = {s[0]: [] for s in offline}
    employees: list[tuple[Any, ...]] = []
    for employee_id in range(1, _scaled("employees", scale) + 1):
        store = offline[(employee_id - 1) % len(offline)]
        title, lo, hi, _ = rng.choices(POSITIONS, weights=[p[3] for p in POSITIONS])[0]
        hired = PERIOD_START - timedelta(days=rng.randint(0, 2000))
        employees.append(
            (employee_id, fake.name(), store[0], title, hired, rng.randrange(lo, hi, 100_000))
        )
        staff[store[0]].append(employee_id)
    _copy(conn, "employees",
          ("employee_id", "full_name", "store_id", "position", "hired_on", "salary"),
          employees)  # fmt: skip

    customers: list[tuple[Any, ...]] = []
    for customer_id in range(1, _scaled("customers", scale) + 1):
        region = rng.choices(REGIONS, weights=REGION_WEIGHTS)[0]
        name = fake.name()
        customers.append((
            customer_id,
            name,
            f"{_slug(name)[:20]}{customer_id}@{rng.choice(EMAIL_DOMAINS)}",
            f"{rng.choice(MOBILE_PREFIXES)}{rng.randint(0, 9_999_999):07d}",
            fake.street_address(),
            rng.choice(region[3]),
            region[0],
            rng.choices(["regular", "silver", "gold", "platinum"], [0.62, 0.22, 0.12, 0.04])[0],
            PERIOD_START - timedelta(days=rng.randint(0, 1100)),
        ))  # fmt: skip
    _copy(conn, "customers",
          ("customer_id", "full_name", "email", "phone", "address", "city", "region_id",
           "segment", "signup_date"),
          customers)  # fmt: skip

    _copy(conn, "categories", ("category_id", "name", "name_en", "parent_id"),
          [c[:4] for c in CATEGORIES])  # fmt: skip

    products: list[Product] = []
    for product_id in range(1, _scaled("products", scale) + 1):
        category = (
            LEAF_CATEGORIES[product_id - 1]
            if product_id <= len(LEAF_CATEGORIES)
            else rng.choice(LEAF_CATEGORIES)
        )
        brand = rng.choice(category[6])
        price = _round_thousand(math.exp(rng.uniform(math.log(category[4]), math.log(category[5]))))
        cost = _round_thousand(price * rng.uniform(0.55, 0.8))
        model = f"{rng.choice('ABCDEFGHKMNPRSTX')}{rng.randint(10, 999)}"
        products.append((
            product_id, f"{category[0]:02d}-{product_id:05d}", f"{category[1]} {brand} {model}",
            category[0], brand, price, cost, rng.random() > 0.05,
        ))  # fmt: skip
    _copy(conn, "products",
          ("product_id", "sku", "name", "category_id", "brand", "unit_price", "unit_cost",
           "is_active"),
          products)  # fmt: skip
    popularity = [1 / (rank**1.1) for rank in range(1, len(products) + 1)]
    rng.shuffle(popularity)

    snapshot = datetime.combine(PERIOD_END, time(22), ICT)
    inventory: list[tuple[Any, ...]] = []
    for store in stores:
        for product in products:
            if rng.random() >= 0.6:
                continue
            reorder = rng.randint(5, 30)
            qty = rng.randint(0, reorder - 1) if rng.random() < 0.08 else rng.randint(reorder, 250)
            inventory.append((store[0], product[0], qty, reorder,
                              snapshot - timedelta(hours=rng.randint(0, 72))))  # fmt: skip
    _copy(conn, "inventory",
          ("store_id", "product_id", "quantity_on_hand", "reorder_level", "updated_at"),
          inventory)  # fmt: skip

    promos: list[Promo] = []
    for year in (2024, 2025, 2026):
        for name, month, day, length, percent in SEASONAL_PROMOS:
            starts = date(year, month, day)
            if starts <= PERIOD_END:
                promos.append((len(promos) + 1, f"{name} {year}", percent, starts,
                               starts + timedelta(days=length - 1)))  # fmt: skip
    while len(promos) < _scaled("promotions", scale):
        starts = PERIOD_START + timedelta(days=rng.randint(0, total_days - 14))
        promos.append((len(promos) + 1, f"Khuyến mãi tuần {starts:%d/%m/%Y}",
                       rng.choice([5, 10, 15, 20]), starts,
                       starts + timedelta(days=rng.randint(3, 14) - 1)))  # fmt: skip
    _copy(conn, "promotions",
          ("promotion_id", "name", "discount_pct", "starts_on", "ends_on"),
          [(p[0], p[1], p[2] / 100, p[3], p[4]) for p in promos])  # fmt: skip

    days = [PERIOD_START + timedelta(days=i) for i in range(total_days + 1)]
    promos_by_day: dict[date, list[Promo]] = {d: [] for d in days}
    for promo in promos:
        current = promo[3]
        while current <= min(promo[4], PERIOD_END):
            promos_by_day[current].append(promo)
            current += timedelta(days=1)

    customer_ids = [c[0] for c in customers]
    customer_weights = [SEGMENT_ORDER_WEIGHT[c[7]] for c in customers]
    order_days = sorted(
        rng.choices(days, weights=[_day_weight(d) for d in days], k=_scaled("orders", scale))
    )
    pending_from = PERIOD_END - timedelta(days=4)
    period_close = datetime.combine(PERIOD_END, time(23, 59), ICT)

    orders: list[tuple[Any, ...]] = []
    items: list[tuple[Any, ...]] = []
    payments: list[tuple[Any, ...]] = []
    returns: list[tuple[Any, ...]] = []
    for order_id, order_day in enumerate(order_days, start=1):
        store = stores[0] if rng.random() < 0.35 else rng.choice(offline)
        is_online = store[4] == "online"
        active = promos_by_day[order_day]
        order_promo = rng.choice(active) if active and rng.random() < 0.55 else None
        placed = datetime.combine(order_day, time(rng.randint(8, 22), rng.randint(0, 59)), ICT)
        roll = rng.random()
        status = "cancelled" if roll < 0.06 else "returned" if roll < 0.10 else "completed"
        if order_day >= pending_from and status == "completed" and rng.random() < 0.5:
            status = "pending"
        orders.append((
            order_id, rng.choices(customer_ids, weights=customer_weights)[0], store[0],
            None if is_online else rng.choice(staff[store[0]]),
            order_promo[0] if order_promo else None, placed, status,
        ))  # fmt: skip

        n_lines = rng.choices([1, 2, 3, 4, 5], [0.50, 0.25, 0.13, 0.07, 0.05])[0]
        picked = {p[0]: p for p in rng.choices(products, weights=popularity, k=n_lines)}
        percent = order_promo[2] if order_promo else 0
        total = 0
        for line_no, product in enumerate(picked.values(), start=1):
            qty = rng.choices([1, 2, 3, 4], [0.72, 0.18, 0.07, 0.03])[0]
            items.append((order_id, line_no, product[0], qty, product[5], percent / 100))
            total += qty * product[5] * (100 - percent) // 100

        if status != "cancelled":
            method = rng.choices(PAYMENT_METHODS, PAYMENT_WEIGHTS)[0]
            if is_online and method == "cash":
                method = "cod"
            elif not is_online and method == "cod":
                method = "cash"
            payments.append((len(payments) + 1, order_id, method, total,
                             min(placed + timedelta(minutes=rng.randint(0, 90)), period_close)))  # fmt: skip
        if status == "returned":
            first = next(iter(picked.values()))
            returns.append((len(returns) + 1, order_id, first[0], 1, rng.choice(RETURN_REASONS),
                            min(placed + timedelta(days=rng.randint(2, 20)), period_close)))  # fmt: skip

    _copy(conn, "orders",
          ("order_id", "customer_id", "store_id", "employee_id", "promotion_id", "order_date",
           "status"),
          orders)  # fmt: skip
    _copy(conn, "order_items",
          ("order_id", "line_no", "product_id", "quantity", "unit_price", "discount"),
          items)  # fmt: skip
    _copy(conn, "payments", ("payment_id", "order_id", "method", "amount", "paid_at"), payments)
    _copy(conn, "returns",
          ("return_id", "order_id", "product_id", "quantity", "reason", "returned_at"),
          returns)  # fmt: skip
    conn.execute("ANALYZE")
