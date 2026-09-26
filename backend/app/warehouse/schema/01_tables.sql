CREATE TABLE IF NOT EXISTS regions (
    region_id  smallint PRIMARY KEY,
    name       text NOT NULL UNIQUE,
    name_en    text NOT NULL
);

CREATE TABLE IF NOT EXISTS stores (
    store_id   integer PRIMARY KEY,
    name       text NOT NULL,
    city       text NOT NULL,
    region_id  smallint NOT NULL REFERENCES regions,
    channel    text NOT NULL CHECK (channel IN ('offline', 'online')),
    opened_on  date NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id integer PRIMARY KEY,
    full_name   text NOT NULL,
    store_id    integer NOT NULL REFERENCES stores,
    position    text NOT NULL,
    hired_on    date NOT NULL,
    salary      numeric(12, 0) NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id integer PRIMARY KEY,
    full_name   text NOT NULL,
    email       text NOT NULL,
    phone       text NOT NULL,
    address     text NOT NULL,
    city        text NOT NULL,
    region_id   smallint NOT NULL REFERENCES regions,
    segment     text NOT NULL CHECK (segment IN ('regular', 'silver', 'gold', 'platinum')),
    signup_date date NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    category_id smallint PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    name_en     text NOT NULL,
    parent_id   smallint REFERENCES categories
);

CREATE TABLE IF NOT EXISTS products (
    product_id  integer PRIMARY KEY,
    sku         text NOT NULL UNIQUE,
    name        text NOT NULL,
    category_id smallint NOT NULL REFERENCES categories,
    brand       text NOT NULL,
    unit_price  numeric(12, 0) NOT NULL CHECK (unit_price > 0),
    unit_cost   numeric(12, 0) NOT NULL CHECK (unit_cost > 0),
    is_active   boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS inventory (
    store_id         integer NOT NULL REFERENCES stores,
    product_id       integer NOT NULL REFERENCES products,
    quantity_on_hand integer NOT NULL CHECK (quantity_on_hand >= 0),
    reorder_level    integer NOT NULL,
    updated_at       timestamptz NOT NULL,
    PRIMARY KEY (store_id, product_id)
);

CREATE TABLE IF NOT EXISTS promotions (
    promotion_id integer PRIMARY KEY,
    name         text NOT NULL,
    discount_pct numeric(4, 2) NOT NULL CHECK (discount_pct > 0 AND discount_pct < 1),
    starts_on    date NOT NULL,
    ends_on      date NOT NULL,
    CHECK (ends_on >= starts_on)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     integer PRIMARY KEY,
    customer_id  integer NOT NULL REFERENCES customers,
    store_id     integer NOT NULL REFERENCES stores,
    employee_id  integer REFERENCES employees,
    promotion_id integer REFERENCES promotions,
    order_date   timestamptz NOT NULL,
    status       text NOT NULL CHECK (status IN ('completed', 'cancelled', 'returned', 'pending'))
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id   integer NOT NULL REFERENCES orders,
    line_no    smallint NOT NULL,
    product_id integer NOT NULL REFERENCES products,
    quantity   integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 0) NOT NULL,
    discount   numeric(4, 2) NOT NULL DEFAULT 0 CHECK (discount >= 0 AND discount < 1),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id integer PRIMARY KEY,
    order_id   integer NOT NULL REFERENCES orders,
    method     text NOT NULL CHECK (method IN ('cash', 'card', 'momo', 'zalopay', 'bank_transfer', 'cod')),
    amount     numeric(14, 0) NOT NULL,
    paid_at    timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS returns (
    return_id   integer PRIMARY KEY,
    order_id    integer NOT NULL REFERENCES orders,
    product_id  integer NOT NULL REFERENCES products,
    quantity    integer NOT NULL CHECK (quantity > 0),
    reason      text NOT NULL,
    returned_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_orders_order_date   ON orders (order_date);
CREATE INDEX IF NOT EXISTS ix_orders_customer_id  ON orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_orders_store_id     ON orders (store_id);
CREATE INDEX IF NOT EXISTS ix_order_items_product ON order_items (product_id);
CREATE INDEX IF NOT EXISTS ix_payments_order_id   ON payments (order_id);
CREATE INDEX IF NOT EXISTS ix_returns_order_id    ON returns (order_id);
CREATE INDEX IF NOT EXISTS ix_products_category   ON products (category_id);
