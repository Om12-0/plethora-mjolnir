-- Restaurant ordering system database schema (PostgreSQL)
-- Assignment 3 - normalization exercise

CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    full_name     TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT
);

CREATE TABLE menu_items (
    item_id       SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    price_cents   INTEGER NOT NULL CHECK (price_cents >= 0),
    category      TEXT NOT NULL
);

CREATE TABLE orders (
    order_id      SERIAL PRIMARY KEY,
    customer_id   INTEGER REFERENCES customers(customer_id),
    placed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE order_lines (
    order_id      INTEGER REFERENCES orders(order_id) ON DELETE CASCADE,
    item_id       INTEGER REFERENCES menu_items(item_id),
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, item_id)
);

-- Third normal form: no partial dependencies, no transitive dependencies.
-- Deliverable requested: restaurant database schema with 3NF justification.
