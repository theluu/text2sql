"""Rule-based fallback: answers common BI questions with no LLM at all.

A question is decomposed into metric × dimension × time range × entity filters (+ top-N),
plus a few special intents (low stock, return reasons, order status, …). Templates only ever
emit SQL built from fixed fragments and catalog values, never user text. No match → None:
the caller says it cannot answer rather than inventing SQL.
"""

import difflib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.text import normalize
from app.llm.timeparse import TimeRange, parse_time
from app.semantic.loader import SemanticLayer, load_semantic_layer
from app.warehouse.seed import CATEGORIES, REGIONS

REVENUE = "SUM(oi.quantity * oi.unit_price * (1 - oi.discount))"

# (metric, patterns). First match wins; order matters (specific before generic).
METRICS: list[tuple[str, str]] = [
    ("return_rate", r"ty le (hoan|tra)( hang)?|return rate|refund rate|ti le (hoan|tra)"),
    (
        "aov",
        r"gia tri (trung binh (moi|cua|1|mot) don|don( hang)? trung binh)|\baov\b|average order value|average basket",
    ),
    ("margin", r"loi nhuan|lai gop|bien loi nhuan|gross margin|\bmargin\b|\bprofit"),
    (
        "units",
        r"so luong (ban|san pham ban)|san luong|units? sold|quantity sold|so (san pham|mon) ban",
    ),
    (
        "orders",
        r"so (luong )?don|bao nhieu don|luong don|number of orders|how many orders|order count|so order",
    ),
    (
        "customers",
        r"so (luong )?khach|bao nhieu khach|number of customers|how many customers|customer count",
    ),
    (
        "revenue",
        r"doanh thu|doanh so|revenue|\bsales\b|ban duoc bao nhieu|tong tien|thu ve|turnover",
    ),
]

# (dimension, patterns) in priority order.
DIMENSIONS: list[tuple[str, str]] = [
    (
        "month",
        r"theo thang|tung thang|hang thang|moi thang|cac thang|monthly|by month|per month|month by month|xu huong|\btrend",
    ),
    ("quarter", r"theo quy|tung quy|hang quy|cac quy|by quarter|quarterly|per quarter"),
    ("day", r"theo ngay|tung ngay|hang ngay|moi ngay|daily|by day|per day"),
    ("weekday", r"thu trong tuan|ngay trong tuan|day of (the )?week|weekday"),
    ("year", r"theo nam|tung nam|hang nam|cac nam|by year|yearly|per year|annual"),
    ("payment_method", r"(phuong thuc|hinh thuc|cach) thanh toan|payment method|pay(ment)? type"),
    ("channel", r"\bkenh\b|channel|online (va|hay|vs|or|and) offline"),
    ("region", r"khu vuc|\bvung\b|\bmien\b|region"),
    ("city", r"thanh pho|tinh thanh|\bcity|\bcities"),
    ("category", r"danh muc|nganh hang|loai (san pham|hang)|categor"),
    ("brand", r"thuong hieu|nhan hang|\bbrand"),
    ("segment", r"hang thanh vien|phan khuc|\bsegment|hang khach|nhom khach"),
    ("store", r"cua hang|chi nhanh|\bstores?\b|\bshops?\b|\bbranch"),
    ("product", r"san pham|mat hang|\bproducts?\b|\bitems?\b|\bsku"),
    ("customer", r"khach hang|\bcustomers?\b|nguoi mua|buyer"),
]
GROUPING_HINT = (
    r"\b(theo|tung|moi|cac|nhung|by|per|each|across|breakdown|phan theo|nao|which|top|nhat)\b"
)
UNSUPPORTED = re.compile(
    r"\b(luy ke|cumulative|running total|trung binh truot|moving average|xep hang|rank|ty trong|share of|"
    r"trung vi|median|moi khach|per customer|each customer|tai sao|vi sao|why|du bao|forecast|predict|du doan|cohort|retention|giu chan|chuyen doi|"
    r"conversion|churn|roi bo|ngung mua|luong|salary|lifetime|clv|ltv|email|so dien thoai|phone|dia chi|address)\b"
)
TOP = re.compile(
    r"\btop (\d{1,3})\b|\b(\d{1,3}) (san pham|khach hang|cua hang|danh muc|thuong hieu|products|customers|stores|categories|brands|mat hang)\b"
)
DESC = re.compile(
    r"nhieu nhat|cao nhat|lon nhat|ban chay|chay nhat|tot nhat|best|highest|most|top|largest|biggest"
)
ASC = re.compile(
    r"it nhat|thap nhat|nho nhat|ban cham|kem nhat|te nhat|lowest|least|worst|slowest|bottom"
)

REGION_ALIASES: dict[str, list[int]] = {
    "mien bac": [1, 2], "northern": [1, 2], "north": [1, 2],
    "mien trung": [3, 4], "central": [3, 4],
    "mien nam": [5, 6], "southern": [5, 6], "south": [5, 6],
}  # fmt: skip
PAYMENT_ALIASES: dict[str, str] = {
    "tien mat": "cash", "cash": "cash", "the": "card", "card": "card", "momo": "momo",
    "zalopay": "zalopay", "zalo pay": "zalopay", "chuyen khoan": "bank_transfer",
    "bank transfer": "bank_transfer", "cod": "cod", "thanh toan khi nhan hang": "cod",
}  # fmt: skip
SEGMENT_ALIASES = {"platinum": "platinum", "bach kim": "platinum", "gold": "gold", "vang": "gold",
                   "silver": "silver", "bac": "silver", "regular": "regular", "thuong": "regular"}  # fmt: skip

SUGGESTIONS = {
    "vi": [
        "Doanh thu theo khu vực quý này",
        "Top 10 sản phẩm bán chạy nhất tháng trước",
        "Những cửa hàng nào có tồn kho dưới mức đặt lại?",
        "Tỷ lệ hoàn hàng theo danh mục năm 2025",
        "Doanh thu theo tháng năm nay",
    ],
    "en": [
        "Revenue by region this quarter",
        "Top 10 best-selling products last month",
        "Which stores have stock below reorder level?",
        "Return rate by category in 2025",
        "Monthly revenue this year",
    ],
}


@dataclass
class RuleMatch:
    intent: str
    sql: str
    params: dict[str, Any]
    confidence: float
    explanation: str


@dataclass
class _Plan:
    lang: str
    role: str
    metric: str = "revenue"
    dimension: str | None = None
    time: TimeRange | None = None
    filters: list[tuple[str, str, str]] = field(default_factory=list)  # (dim, sql, label)
    top: int | None = None
    ascending: bool = False
    penalty: float = 0.0
    notes: list[str] = field(default_factory=list)


def _alias(plan: _Plan, vi: str, en: str) -> str:
    return vi if plan.lang == "vi" else en


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _match_entity(text: str, names: dict[str, Any]) -> tuple[Any, bool] | None:
    """Exact (normalized substring) match first, then a fuzzy one for typos. Returns (value, exact)."""
    for name in sorted(names, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", text):
            return names[name], True
    words = text.split()
    for size in (4, 3, 2):
        for i in range(len(words) - size + 1):
            chunk = " ".join(words[i : i + size])
            for close in difflib.get_close_matches(chunk, list(names), n=3, cutoff=0.85):
                # Word by word too, so "theo trang" never passes for "thoi trang".
                pairs = zip(chunk.split(), close.split(), strict=False)
                if len(close.split()) == size and all(
                    difflib.SequenceMatcher(None, x, y).ratio() >= 0.8 for x, y in pairs
                ):
                    return names[close], False
    return None


def _catalogs() -> dict[str, dict[str, Any]]:
    regions: dict[str, Any] = {}
    for region_id, vi, en, _cities in REGIONS:
        regions[normalize(vi)] = ([region_id], vi, en)
        regions[normalize(en)] = ([region_id], vi, en)
    for alias, ids in REGION_ALIASES.items():
        regions[alias] = (ids, alias.title(), alias.title())
    categories: dict[str, Any] = {}
    for category_id, vi, en, parent, *_ in CATEGORIES:
        entry = (category_id, parent is None, vi, en)
        categories[normalize(vi)] = entry
        categories[normalize(en)] = entry
    cities = {normalize(c): c for *_, city_list in REGIONS for c in city_list}
    cities["hcm"] = cities["sai gon"] = cities["saigon"] = "TP. Hồ Chí Minh"
    cities["ho chi minh"] = "TP. Hồ Chí Minh"
    return {"region": regions, "category": categories, "city": cities}


CATALOGS = _catalogs()


def _detect_filters(t: str, plan: _Plan) -> None:
    region = _match_entity(t, CATALOGS["region"])
    if region:
        (ids, vi, en), exact = region
        plan.filters.append(("region", f"s.region_id IN ({', '.join(map(str, ids))})",
                             _alias(plan, vi, en)))  # fmt: skip
        plan.penalty += 0 if exact else 0.1
    category = _match_entity(t, CATALOGS["category"])
    if category:
        (category_id, is_parent, vi, en), exact = category
        condition = (
            f"(c.category_id = {category_id} OR c.parent_id = {category_id})"
            if is_parent
            else f"c.category_id = {category_id}"
        )
        plan.filters.append(("category", condition, _alias(plan, vi, en)))
        plan.penalty += 0 if exact else 0.1
    city = _match_entity(t, CATALOGS["city"])
    if city and not region:
        name, exact = city
        plan.filters.append(("city", f"s.city = {_lit(name)}", name))
        plan.penalty += 0 if exact else 0.1
    if re.search(r"\b(online|truc tuyen)\b", t) and not re.search(
        r"online (va|hay|vs|or|and) offline", t
    ):
        plan.filters.append(("channel", "s.channel = 'online'", "online"))
    elif re.search(r"\b(offline|tai cua hang|in store)\b", t):
        plan.filters.append(("channel", "s.channel = 'offline'", "offline"))
    for alias, method in PAYMENT_ALIASES.items():
        if alias in ("the", "bac", "vang", "thuong"):
            continue  # too ambiguous as bare words
        if re.search(rf"\b{alias}\b", t):
            plan.filters.append(("payment_method", f"pm.method = {_lit(method)}", method))
            break
    for alias, segment in SEGMENT_ALIASES.items():
        if re.search(
            rf"\b(khach|hang|segment|thanh vien|customers?) {alias}\b|\b{alias} (customers?|members?)\b",
            t,
        ):
            plan.filters.append(("segment", f"cu.segment = {_lit(segment)}", segment))
            break


def _detect_dimension(t: str, plan: _Plan) -> None:
    filtered = {f[0] for f in plan.filters}
    found = [dim for dim, pattern in DIMENSIONS if re.search(pattern, t)]
    candidates = []
    for dim in found:
        hinted = re.search(rf"{GROUPING_HINT} ({dict(DIMENSIONS)[dim]})", t)
        if dim in filtered and not hinted:
            continue  # "doanh thu khu vực Đông Nam Bộ" filters, it does not group
        if dim in ("customer", "product", "store") and not (
            hinted or DESC.search(t) or ASC.search(t)
        ):
            continue  # "khách hàng gold", "sản phẩm điện thoại" describe, they do not group
        candidates.append(dim)
    time_dims = [d for d in candidates if d in ("month", "quarter", "day", "weekday", "year")]
    other = [d for d in candidates if d not in time_dims]
    if other and time_dims:
        # "doanh thu theo tháng của từng khu vực": two groupings is beyond the templates
        plan.penalty += 0.15
    if len(other) > 1:
        # "khách hàng" and "sản phẩm" both appear in many phrasings; keep the most specific.
        plan.penalty += 0.05 if other[-1] in ("customer", "product") else 0.15
    plan.dimension = (other or time_dims)[0] if (other or time_dims) else None


def _time_condition(plan: _Plan) -> list[str]:
    if not plan.time:
        return []
    return [
        f"o.order_date >= DATE '{plan.time.start.isoformat()}'",
        f"o.order_date < DATE '{plan.time.end.isoformat()}'",
    ]


def _metric_sql(metric: str, when: str | None = None) -> str:
    """Aggregate for `metric`; with `when`, every aggregate gets FILTER (WHERE when)."""
    f = f" FILTER (WHERE {when})" if when else ""
    revenue = f"SUM(oi.quantity * oi.unit_price * (1 - oi.discount)){f}"
    orders = f"COUNT(DISTINCT o.order_id){f}"
    returned = (
        f"(WHERE o.status = 'returned' AND {when})" if when else "(WHERE o.status = 'returned')"
    )
    return {
        "revenue": f"ROUND({revenue})",
        "units": f"SUM(oi.quantity){f}",
        "orders": orders,
        "customers": f"COUNT(DISTINCT o.customer_id){f}",
        "aov": f"ROUND({revenue} / NULLIF({orders}, 0))",
        "margin": f"ROUND(SUM(oi.quantity * (oi.unit_price * (1 - oi.discount) - p.unit_cost)){f})",
        "return_rate": (
            f"ROUND(100.0 * COUNT(DISTINCT o.order_id) FILTER {returned} / NULLIF({orders}, 0), 2)"
        ),
    }[metric]


METRIC_ALIASES = {
    "revenue": ("doanh_thu", "revenue"),
    "units": ("so_luong_ban", "units_sold"),
    "orders": ("so_don", "orders"),
    "customers": ("so_khach_hang", "customers"),
    "aov": ("gia_tri_don_tb", "avg_order_value"),
    "margin": ("loi_nhuan_gop", "gross_margin"),
    "return_rate": ("ty_le_hoan_pct", "return_rate_pct"),
}
METRIC_LABELS = {
    "revenue": ("doanh thu", "revenue"),
    "units": ("số lượng bán", "units sold"),
    "orders": ("số đơn hàng", "number of orders"),
    "customers": ("số khách hàng", "number of customers"),
    "aov": ("giá trị đơn trung bình", "average order value"),
    "margin": ("lợi nhuận gộp", "gross margin"),
    "return_rate": ("tỷ lệ hoàn hàng (%)", "return rate (%)"),
}


def _dimension_sql(plan: _Plan, customers: str) -> tuple[list[str], list[str], str | None]:
    """(select expressions, group-by expressions, time-ordered?)"""
    d = plan.dimension

    def a(vi: str, en: str) -> str:
        return _alias(plan, vi, en)

    name = "name" if plan.lang == "vi" else "name_en"
    mapping: dict[str, tuple[list[str], list[str]]] = {
        "month": (
            [f"to_char(date_trunc('month', o.order_date), 'YYYY-MM') AS {a('thang', 'month')}"],
            ["1"],
        ),
        "quarter": ([f"to_char(o.order_date, 'YYYY-\"Q\"Q') AS {a('quy', 'quarter')}"], ["1"]),
        "day": ([f"o.order_date::date AS {a('ngay', 'day')}"], ["1"]),
        "weekday": (
            [f"EXTRACT(ISODOW FROM o.order_date)::int AS {a('thu_trong_tuan', 'iso_weekday')}"],
            ["1"],
        ),
        "year": ([f"EXTRACT(YEAR FROM o.order_date)::int AS {a('nam', 'year')}"], ["1"]),
        "region": ([f"r.{name} AS {a('khu_vuc', 'region')}"], ["1"]),
        "city": ([f"s.city AS {a('thanh_pho', 'city')}"], ["1"]),
        "store": ([f"s.name AS {a('cua_hang', 'store')}"], ["s.store_id", "s.name"]),
        "channel": ([f"s.channel AS {a('kenh', 'channel')}"], ["1"]),
        "category": ([f"c.{name} AS {a('danh_muc', 'category')}"], ["c.category_id", f"c.{name}"]),
        "brand": ([f"p.brand AS {a('thuong_hieu', 'brand')}"], ["1"]),
        "product": ([f"p.name AS {a('san_pham', 'product')}"], ["p.product_id", "p.name"]),
        "payment_method": ([f"pm.method AS {a('phuong_thuc', 'payment_method')}"], ["1"]),
        "segment": ([f"cu.segment AS {a('hang_thanh_vien', 'segment')}"], ["1"]),
        "customer": (
            [f"cu.full_name AS {a('khach_hang', 'customer')}"],
            ["cu.customer_id", "cu.full_name"],
        ),
    }
    if d is None:
        return [], [], None
    select, group = mapping[d]
    return select, group, d if d in ("month", "quarter", "day", "weekday", "year") else None


def _build_metric_sql(plan: _Plan, layer: SemanticLayer) -> str:
    customers = layer.visible_name("customers", plan.role)
    used = {plan.dimension} | {f[0] for f in plan.filters}
    needs_items = plan.metric in ("revenue", "units", "aov", "margin") or used & {
        "category",
        "brand",
        "product",
    }
    joins = []
    if needs_items:
        joins.append("JOIN order_items oi ON oi.order_id = o.order_id")
    if used & {"region", "city", "store", "channel"}:
        joins.append("JOIN stores s ON s.store_id = o.store_id")
    if "region" in used:
        joins.append("JOIN regions r ON r.region_id = s.region_id")
    if plan.metric == "margin" or used & {"category", "brand", "product"}:
        joins.append("JOIN products p ON p.product_id = oi.product_id")
    if "category" in used:
        joins.append("JOIN categories c ON c.category_id = p.category_id")
    if "payment_method" in used:
        joins.append("JOIN payments pm ON pm.order_id = o.order_id")
    if used & {"segment", "customer"}:
        joins.append(f"JOIN {customers} cu ON cu.customer_id = o.customer_id")

    select, group, time_dim = _dimension_sql(plan, customers)
    metric_alias = _alias(plan, *METRIC_ALIASES[plan.metric])
    cancelled = any(f[0] == "status" for f in plan.filters)
    where = [
        *([] if cancelled else ["o.status <> 'cancelled'"]),
        *_time_condition(plan),
        *(f[1] for f in plan.filters),
    ]
    if plan.metric == "customers" and not plan.time and not plan.filters and plan.dimension is None:
        # "Có bao nhiêu khách hàng?" means the customer base, not customers who ordered.
        alias = _alias(plan, *METRIC_ALIASES["customers"])
        return f"SELECT COUNT(*) AS {alias} FROM {layer.visible_name('customers', plan.role)}"
    sql = f"SELECT {', '.join([*select, f'{_metric_sql(plan.metric)} AS {metric_alias}'])} FROM orders o"
    if joins:
        sql += " " + " ".join(joins)
    sql += " WHERE " + " AND ".join(where)
    if group:
        sql += " GROUP BY " + ", ".join(group)
        if time_dim:
            sql += " ORDER BY 1"
        else:
            sql += f" ORDER BY {metric_alias} {'ASC' if plan.ascending else 'DESC'} NULLS LAST"
    limit = plan.top or (
        None
        if time_dim or not group
        else (10 if plan.dimension in ("product", "customer", "store", "brand") else 100)
    )
    if limit:
        sql += f" LIMIT {limit}"
    return sql


def _special(t: str, plan: _Plan, layer: SemanticLayer) -> tuple[str, str] | None:
    def a(vi: str, en: str) -> str:
        return _alias(plan, vi, en)

    name = "name" if plan.lang == "vi" else "name_en"
    time_where = " AND ".join(_time_condition(plan)) or "TRUE"
    if re.search(
        r"ton kho (duoi|thap|it|sap het|khong du)|sap het hang|het hang|duoi muc dat( hang)? lai|muc dat lai|low (stock|inventory)|out of stock|below reorder|reorder level|restock",
        t,
    ):
        if re.search(
            r"cua hang nao|which stores?|stores? (have|has|with)|theo cua hang|by store|cac cua hang|nhung cua hang",
            t,
        ):
            return "low_stock_by_store", (
                f"SELECT s.name AS {a('cua_hang', 'store')}, COUNT(*) AS {a('so_mat_hang_duoi_muc', 'items_below_reorder')} "
                "FROM inventory i JOIN stores s ON s.store_id = i.store_id "
                "WHERE i.quantity_on_hand < i.reorder_level GROUP BY s.store_id, s.name ORDER BY 2 DESC LIMIT 100"
            )
        return "low_stock_items", (
            f"SELECT s.name AS {a('cua_hang', 'store')}, p.name AS {a('san_pham', 'product')}, "
            f"i.quantity_on_hand AS {a('ton_kho', 'on_hand')}, i.reorder_level AS {a('muc_dat_lai', 'reorder_level')} "
            "FROM inventory i JOIN stores s ON s.store_id = i.store_id JOIN products p ON p.product_id = i.product_id "
            "WHERE i.quantity_on_hand < i.reorder_level ORDER BY i.quantity_on_hand - i.reorder_level LIMIT 200"
        )
    if re.search(r"\b(ton kho|inventory|stock on hand|stock level)", t):
        by_store = plan.dimension == "store" or re.search(r"cua hang|store", t)
        if by_store:
            return "inventory_by_store", (
                f"SELECT s.name AS {a('cua_hang', 'store')}, SUM(i.quantity_on_hand) AS {a('tong_ton_kho', 'units_on_hand')} "
                "FROM inventory i JOIN stores s ON s.store_id = i.store_id GROUP BY s.store_id, s.name ORDER BY 2 DESC LIMIT 100"
            )
        return "inventory_by_category", (
            f"SELECT c.{name} AS {a('danh_muc', 'category')}, SUM(i.quantity_on_hand) AS {a('tong_ton_kho', 'units_on_hand')} "
            "FROM inventory i JOIN products p ON p.product_id = i.product_id JOIN categories c ON c.category_id = p.category_id "
            "GROUP BY c.category_id, c.{name} ORDER BY 2 DESC".replace("{name}", name)
        )
    if re.search(
        r"ly do (tra|hoan)|nguyen nhan (tra|hoan)|return reasons?|reasons? for returns?|why .*return",
        t,
    ):
        where = time_where.replace("o.order_date", "rt.returned_at")
        return "return_reasons", (
            f"SELECT rt.reason AS {a('ly_do', 'reason')}, COUNT(*) AS {a('so_luot_tra', 'returns')} "
            f"FROM returns rt WHERE {where} GROUP BY 1 ORDER BY 2 DESC"
        )
    if re.search(r"khach hang moi|khach moi|new customers?|dang ky moi|signups?|sign ups?", t):
        where = time_where.replace("o.order_date", "cu.signup_date")
        customers = layer.visible_name("customers", plan.role)
        return "new_customers_by_month", (
            f"SELECT to_char(date_trunc('month', cu.signup_date), 'YYYY-MM') AS {a('thang', 'month')}, "
            f"COUNT(*) AS {a('khach_hang_moi', 'new_customers')} FROM {customers} cu WHERE {where} GROUP BY 1 ORDER BY 1"
        )
    if re.search(
        r"trang thai|order status|by status|don (bi )?huy|cancel+ed orders|huy don|tinh trang don",
        t,
    ):
        return "orders_by_status", (
            f"SELECT o.status AS {a('trang_thai', 'status')}, COUNT(*) AS {a('so_don', 'orders')} "
            f"FROM orders o WHERE {time_where} GROUP BY 1 ORDER BY 2 DESC"
        )
    if re.search(r"khuyen mai|chuong trinh giam gia|promotions?|campaigns?", t):
        return "revenue_by_promotion", (
            f"SELECT pr.name AS {a('khuyen_mai', 'promotion')}, COUNT(DISTINCT o.order_id) AS {a('so_don', 'orders')}, "
            f"ROUND({REVENUE}) AS {a('doanh_thu', 'revenue')} FROM orders o "
            "JOIN order_items oi ON oi.order_id = o.order_id JOIN promotions pr ON pr.promotion_id = o.promotion_id "
            f"WHERE o.status <> 'cancelled' AND {time_where} GROUP BY pr.promotion_id, pr.name ORDER BY 3 DESC LIMIT {plan.top or 20}"
        )
    if re.search(r"(so|bao nhieu|number of|how many) (luong )?(nhan vien|employees|staff)", t):
        employees = layer.visible_name("employees", plan.role)
        return "employees_by_store", (
            f"SELECT s.name AS {a('cua_hang', 'store')}, COUNT(*) AS {a('so_nhan_vien', 'employees')} "
            f"FROM {employees} e JOIN stores s ON s.store_id = e.store_id GROUP BY s.store_id, s.name ORDER BY 2 DESC"
        )
    return None


def _compare(t: str, plan: _Plan, layer: SemanticLayer) -> str | None:
    if not re.search(
        r"so voi|so sanh|compared?|\bvs\b|versus|tang truong|growth|tang hay giam|\bmom\b|\bqoq\b|\byoy\b|cung ky",
        t,
    ):
        return None
    if plan.time is None or plan.metric not in (
        "revenue",
        "orders",
        "units",
        "aov",
        "margin",
        "customers",
    ):
        return None
    current = plan.time
    if re.search(r"cung ky|yoy|year over year|nam truoc|last year", t) and current.grain != "year":
        previous = TimeRange(current.start.replace(year=current.start.year - 1),
                             current.end.replace(year=current.end.year - 1),
                             "cùng kỳ năm trước", "same period last year", current.grain)  # fmt: skip
    else:
        previous = current.previous()
    plan.notes.append(f"{current.label_vi} vs {previous.label_vi}")

    def a(vi: str, en: str) -> str:
        return _alias(plan, vi, en)

    def period(tr: TimeRange) -> str:
        return f"o.order_date >= DATE '{tr.start}' AND o.order_date < DATE '{tr.end}'"

    inner_select, inner_group, _ = _dimension_sql(plan, layer.visible_name("customers", plan.role))
    cur_label, prev_label = a("ky_nay", "current_period"), a("ky_truoc", "previous_period")
    change = a("thay_doi_pct", "change_pct")

    plan_sql = _build_metric_sql(plan, layer)
    from_clause = plan_sql[plan_sql.index(" FROM orders o") : plan_sql.index(" WHERE ")]
    where = ["o.status <> 'cancelled'", f"o.order_date >= DATE '{previous.start}'",
             f"o.order_date < DATE '{current.end}'", *(f[1] for f in plan.filters)]  # fmt: skip
    select = [
        *inner_select,
        f"{_metric_sql(plan.metric, period(current))} AS {cur_label}",
        f"{_metric_sql(plan.metric, period(previous))} AS {prev_label}",
    ]
    sql = f"SELECT {', '.join(select)}{from_clause} WHERE {' AND '.join(where)}"
    if inner_group:
        sql += " GROUP BY " + ", ".join(inner_group)
    sql = f"SELECT *, ROUND(100.0 * ({cur_label} - {prev_label}) / NULLIF({prev_label}, 0), 1) AS {change} FROM ({sql}) t"
    if inner_group:
        sql += f" ORDER BY {cur_label} DESC NULLS LAST LIMIT {plan.top or 50}"
    return sql


def detect_lang(question: str) -> str:
    from app.core.text import strip_accents

    if strip_accents(question) != question:
        return "vi"
    vi_words = r"\b(doanh thu|thang|nam|quy|khach hang|san pham|cua hang|bao nhieu|theo|nhung|nao|ty le|ton kho)\b"
    return "vi" if re.search(vi_words, normalize(question)) else "en"


def match(
    question: str, role: str, as_of: date, layer: SemanticLayer | None = None
) -> RuleMatch | None:
    layer = layer or load_semantic_layer()
    t = normalize(question)
    if not t or UNSUPPORTED.search(t):
        return None
    plan = _Plan(lang=detect_lang(question), role=role)
    plan.time = parse_time(t, as_of)

    top = TOP.search(t)
    if top:
        plan.top = int(top.group(1) or top.group(2))
    plan.ascending = bool(ASC.search(t)) and not re.search(r"\btop\b", t)

    metrics = [m for m, pattern in METRICS if re.search(pattern, t)]
    if metrics:
        plan.metric = metrics[0]
        if len(metrics) > 1 and not (metrics[0] in ("aov", "return_rate") and "revenue" in metrics):
            plan.penalty += 0.2  # two different metrics asked at once
    elif re.search(r"ban chay|ban cham|best.?sell|top.?sell|bestseller|slowest.?sell", t):
        plan.metric = "units"
    _detect_filters(t, plan)
    _detect_dimension(t, plan)

    if (
        plan.metric == "orders"
        and re.search(r"\b(huy|bi huy|cancel\w*)\b", t)
        and not re.search(r"trang thai|status", t)
    ):
        plan.filters.append(("status", "o.status = 'cancelled'", "cancelled"))
    special = _special(t, plan, layer)
    if special:
        intent, sql = special
        return RuleMatch(
            intent, sql, _params(plan), round(0.9 - plan.penalty, 2), _explain(plan, intent)
        )

    if not metrics and plan.metric != "units":
        if plan.dimension is None:
            return None  # nothing we recognise as a measurable question
        plan.penalty += 0.2  # metric guessed (revenue)
    if plan.dimension in ("product", "customer", "store", "brand", "category") and (
        DESC.search(t) or ASC.search(t)
    ):
        plan.top = plan.top or 10
    compare_sql = _compare(t, plan, layer)
    if compare_sql:
        intent = f"{plan.metric}_compare" + (f"_by_{plan.dimension}" if plan.dimension else "")
        return RuleMatch(
            intent, compare_sql, _params(plan), round(0.9 - plan.penalty, 2), _explain(plan, intent)
        )
    sql = _build_metric_sql(plan, layer)
    intent = f"{'top_' if plan.top else ''}{plan.metric}" + (
        f"_by_{plan.dimension}" if plan.dimension else "_total"
    )
    confidence = 0.92 - plan.penalty
    return RuleMatch(
        intent, sql, _params(plan), round(max(confidence, 0.3), 2), _explain(plan, intent)
    )


def _params(plan: _Plan) -> dict[str, Any]:
    return {
        "metric": plan.metric,
        "dimension": plan.dimension,
        "time": None
        if plan.time is None
        else {
            "start": plan.time.start.isoformat(),
            "end": plan.time.end.isoformat(),
            "label": plan.time.label_vi if plan.lang == "vi" else plan.time.label_en,
        },  # fmt: skip
        "filters": [{"dimension": d, "value": label} for d, _, label in plan.filters],
        "top": plan.top,
        "order": "asc" if plan.ascending else "desc",
        "lang": plan.lang,
    }


def _explain(plan: _Plan, intent: str) -> str:
    vi = plan.lang == "vi"
    metric = METRIC_LABELS[plan.metric][0 if vi else 1]
    parts = [("Mẫu truy vấn dự phòng" if vi else "Fallback template") + f" `{intent}`: {metric}"]
    if plan.dimension:
        parts.append(("theo " if vi else "by ") + plan.dimension)
    if plan.time:
        parts.append(plan.time.label_vi if vi else plan.time.label_en)
    else:
        parts.append("toàn bộ dữ liệu" if vi else "all data")
    for dim, _, label in plan.filters:
        parts.append(f"{dim} = {label}")
    if plan.top:
        parts.append(f"top {plan.top}")
    note = "; ".join(parts)
    rule = " Đơn đã hủy không được tính." if vi else " Cancelled orders are excluded."
    return note + "." + rule
