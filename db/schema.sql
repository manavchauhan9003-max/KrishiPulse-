-- Create crop_master table
CREATE TABLE IF NOT EXISTS crop_master (
    crop_id SERIAL PRIMARY KEY,
    crop_name VARCHAR(50) NOT NULL UNIQUE
);

-- Create crop_alias_map table
CREATE TABLE IF NOT EXISTS crop_alias_map (
    alias_id SERIAL PRIMARY KEY,
    raw_string VARCHAR(100) NOT NULL UNIQUE,
    crop_id INTEGER NOT NULL REFERENCES crop_master(crop_id)
);

-- Create mandi_master table
CREATE TABLE IF NOT EXISTS mandi_master (
    mandi_id SERIAL PRIMARY KEY,
    mandi_name VARCHAR(150) NOT NULL,
    district VARCHAR(100),
    state VARCHAR(50) NOT NULL DEFAULT 'Gujarat',
    UNIQUE (mandi_name, district)
);

-- Create wholesale_price table
CREATE TABLE IF NOT EXISTS wholesale_price (
    price_id SERIAL PRIMARY KEY,
    crop_id INTEGER NOT NULL REFERENCES crop_master(crop_id),
    mandi_id INTEGER NOT NULL REFERENCES mandi_master(mandi_id),
    variety VARCHAR(100),
    price_date DATE NOT NULL,
    min_price NUMERIC(10,2),
    max_price NUMERIC(10,2),
    modal_price NUMERIC(10,2),
    unit VARCHAR(20) NOT NULL DEFAULT 'quintal',
    is_provisional BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (crop_id, mandi_id, variety, price_date)
);

-- Create retail_price table
CREATE TABLE IF NOT EXISTS retail_price (
    retail_id SERIAL PRIMARY KEY,
    crop_id INTEGER NOT NULL REFERENCES crop_master(crop_id),
    city VARCHAR(100) NOT NULL,
    platform VARCHAR(50),
    price_date DATE NOT NULL,
    price NUMERIC(10,2),
    unit VARCHAR(20) NOT NULL DEFAULT 'kg',
    data_type VARCHAR(20) NOT NULL CHECK (data_type IN ('scraped', 'modeled')),
    confidence_note TEXT
);

-- Create price_anomaly table
CREATE TABLE IF NOT EXISTS price_anomaly (
    anomaly_id SERIAL PRIMARY KEY,
    crop_id INTEGER NOT NULL REFERENCES crop_master(crop_id),
    mandi_id INTEGER REFERENCES mandi_master(mandi_id),
    district VARCHAR(100),
    city VARCHAR(100),
    price_date DATE NOT NULL,
    wholesale_price NUMERIC(10,2),
    wholesale_baseline NUMERIC(10,2),
    wholesale_zscore NUMERIC(6,2),
    retail_price NUMERIC(10,2),
    retail_baseline NUMERIC(10,2),
    retail_zscore NUMERIC(6,2),
    wedge_pct NUMERIC(6,2),
    anomaly_flag BOOLEAN NOT NULL DEFAULT FALSE
);