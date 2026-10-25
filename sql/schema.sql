-- Foodlytics schema: three layers kept strictly apart.
--   raw       : untouched CSV contents (all TEXT) - created dynamically by src/load_postgres.py
--   clean     : typed, constrained, de-duplicated tables (this file)
--   analytics : business views / derived tables (sql/analytical_views.sql)
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS clean;
CREATE SCHEMA IF NOT EXISTS analytics;

DROP TABLE IF EXISTS clean.order_reviews, clean.order_payments, clean.order_items,
    clean.orders, clean.products, clean.product_categories, clean.sellers,
    clean.customers, clean.geolocation CASCADE;

CREATE TABLE clean.geolocation (
    zip_code_prefix CHAR(5) PRIMARY KEY,
    lat             DOUBLE PRECISION NOT NULL,
    lng             DOUBLE PRECISION NOT NULL,
    state           CHAR(2),
    city            TEXT,
    n_points        INT NOT NULL
);

CREATE TABLE clean.customers (
    customer_id              CHAR(32) PRIMARY KEY,     -- one per ORDER in Olist
    customer_unique_id       CHAR(32) NOT NULL,        -- stable person/account proxy
    customer_zip_code_prefix CHAR(5),
    customer_city            TEXT,
    customer_state           CHAR(2)
);

CREATE TABLE clean.sellers (
    seller_id              CHAR(32) PRIMARY KEY,
    seller_zip_code_prefix CHAR(5),
    seller_city            TEXT,
    seller_state           CHAR(2)
);

CREATE TABLE clean.product_categories (
    product_category_name         TEXT PRIMARY KEY,
    product_category_name_english TEXT NOT NULL
);

CREATE TABLE clean.products (
    product_id                 CHAR(32) PRIMARY KEY,
    product_category_name      TEXT NOT NULL REFERENCES clean.product_categories,
    product_name_length        INT,
    product_description_length INT,
    product_photos_qty         INT,
    product_weight_g           NUMERIC,
    product_length_cm          NUMERIC,
    product_height_cm          NUMERIC,
    product_width_cm           NUMERIC
);

CREATE TABLE clean.orders (
    order_id                       CHAR(32) PRIMARY KEY,
    customer_id                    CHAR(32) NOT NULL REFERENCES clean.customers,
    order_status                   TEXT NOT NULL CHECK (order_status IN
        ('created','approved','invoiced','processing','shipped','delivered','unavailable','canceled')),
    order_purchase_timestamp       TIMESTAMP NOT NULL,
    order_approved_at              TIMESTAMP,
    order_delivered_carrier_date   TIMESTAMP,
    order_delivered_customer_date  TIMESTAMP,
    order_estimated_delivery_date  TIMESTAMP NOT NULL,
    flag_delivered_missing_date    BOOLEAN NOT NULL,
    flag_deliv_date_not_delivered  BOOLEAN NOT NULL,
    flag_carrier_before_approval   BOOLEAN NOT NULL,
    flag_carrier_before_purchase   BOOLEAN NOT NULL,
    flag_delivered_before_carrier  BOOLEAN NOT NULL,
    flag_delivered_before_purchase BOOLEAN NOT NULL,
    has_timestamp_anomaly          BOOLEAN NOT NULL
);

CREATE TABLE clean.order_items (
    order_id            CHAR(32) NOT NULL REFERENCES clean.orders,
    order_item_id       INT NOT NULL,
    product_id          CHAR(32) NOT NULL REFERENCES clean.products,
    seller_id           CHAR(32) NOT NULL REFERENCES clean.sellers,
    shipping_limit_date TIMESTAMP,
    price               NUMERIC(10,2) NOT NULL CHECK (price > 0),
    freight_value       NUMERIC(10,2) NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE clean.order_payments (
    order_id                 CHAR(32) NOT NULL REFERENCES clean.orders,
    payment_sequential       INT NOT NULL,
    payment_type             TEXT NOT NULL,
    payment_installments     INT NOT NULL,
    payment_value            NUMERIC(10,2) NOT NULL CHECK (payment_value >= 0),
    flag_zero_value          BOOLEAN NOT NULL,
    flag_invalid_installments BOOLEAN NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE clean.order_reviews (
    order_id                CHAR(32) PRIMARY KEY REFERENCES clean.orders,  -- one kept review per order
    review_id               CHAR(32) NOT NULL,                              -- NOT unique in the source
    review_score            INT NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_creation_date    TIMESTAMP,
    review_answer_timestamp TIMESTAMP
);

-- Indexes for the join/filter paths used by the analytics layer
CREATE INDEX ix_customers_unique   ON clean.customers (customer_unique_id);
CREATE INDEX ix_orders_customer    ON clean.orders (customer_id);
CREATE INDEX ix_orders_purchase_ts ON clean.orders (order_purchase_timestamp);
CREATE INDEX ix_orders_status      ON clean.orders (order_status);
CREATE INDEX ix_items_product      ON clean.order_items (product_id);
CREATE INDEX ix_items_seller       ON clean.order_items (seller_id);
CREATE INDEX ix_products_category  ON clean.products (product_category_name);
