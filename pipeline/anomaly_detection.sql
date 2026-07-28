-- Step 1: Clear existing anomaly rows before re-inserting (idempotent)
DELETE FROM price_anomaly;

-- Step 2: Compute rolling baseline + z-score for wholesale, join retail, insert anomalies
INSERT INTO price_anomaly (
    crop_id, mandi_id, district, city, price_date,
    wholesale_price, wholesale_baseline, wholesale_zscore,
    retail_price, retail_baseline, retail_zscore,
    wedge_pct, anomaly_flag
)
WITH wholesale_stats AS (
    SELECT
        w.crop_id,
        w.mandi_id,
        m.district,
        w.price_date,
        w.modal_price AS wholesale_price,
        AVG(w.modal_price) OVER (
            PARTITION BY w.crop_id, w.mandi_id
            ORDER BY w.price_date
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS wholesale_baseline,
        STDDEV(w.modal_price) OVER (
            PARTITION BY w.crop_id, w.mandi_id
            ORDER BY w.price_date
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS wholesale_stddev,
        COUNT(*) OVER (
            PARTITION BY w.crop_id, w.mandi_id
            ORDER BY w.price_date
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS preceding_count
    FROM wholesale_price w
    JOIN mandi_master m ON w.mandi_id = m.mandi_id
    WHERE w.is_provisional = false
),
wholesale_scored AS (
    SELECT *,
        CASE
            WHEN wholesale_stddev IS NULL OR wholesale_stddev = 0 THEN NULL
            WHEN preceding_count < 7 THEN NULL
            ELSE ROUND(((wholesale_price - wholesale_baseline) / wholesale_stddev)::numeric, 2)
        END AS wholesale_zscore
    FROM wholesale_stats
    WHERE wholesale_baseline IS NOT NULL
),
retail_stats AS (
    SELECT
        crop_id,
        city,
        price_date,
        price AS retail_price,
        AVG(price) OVER (
            PARTITION BY crop_id, city
            ORDER BY price_date
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS retail_baseline,
        STDDEV(price) OVER (
            PARTITION BY crop_id, city
            ORDER BY price_date
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS retail_stddev,
        COUNT(*) OVER (
            PARTITION BY crop_id, city
            ORDER BY price_date
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS preceding_count
    FROM retail_price
    WHERE data_type = 'scraped'
),
retail_scored AS (
    SELECT *,
        CASE
            WHEN retail_stddev IS NULL OR retail_stddev = 0 THEN NULL
            WHEN preceding_count < 7 THEN NULL
            ELSE ROUND(((retail_price - retail_baseline) / retail_stddev)::numeric, 2)
        END AS retail_zscore
    FROM retail_stats
    WHERE retail_baseline IS NOT NULL
)
SELECT
    ws.crop_id,
    ws.mandi_id,
    ws.district,
    rs.city,
    ws.price_date,
    ws.wholesale_price,
    ROUND(ws.wholesale_baseline::numeric, 2),
    ws.wholesale_zscore,
    rs.retail_price,
    ROUND(rs.retail_baseline::numeric, 2),
    rs.retail_zscore,
    ROUND(((rs.retail_price - ws.wholesale_price) / NULLIF(ws.wholesale_price, 0) * 100)::numeric, 2) AS wedge_pct,
    CASE
        WHEN (ws.wholesale_zscore IS NOT NULL AND ABS(ws.wholesale_zscore) > 2)
          OR (rs.retail_zscore IS NOT NULL AND ABS(rs.retail_zscore) > 2)
        THEN true
        ELSE false
    END AS anomaly_flag
FROM wholesale_scored ws
JOIN retail_scored rs
    ON ws.crop_id = rs.crop_id
    AND ws.price_date = rs.price_date;