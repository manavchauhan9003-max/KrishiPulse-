import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("DATABASE_URL not found — check .env file")
    exit(1)

CITY_FACTORS = {
    'Surat':       1.05,
    'Vadodara':    1.03,
    'Rajkot':      1.08,
    'Gandhinagar': 1.02,
    'Bhavnagar':   1.10,
}

CONFIDENCE_NOTE = "Modeled: Ahmedabad Blinkit price × city margin factor (transport/distribution estimate)"

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Fetch all scraped Ahmedabad rows
    cur.execute("""
        SELECT crop_id, price_date, price
        FROM retail_price
        WHERE city = 'Ahmedabad'
        AND data_type = 'scraped'
    """)
    ahmedabad_rows = cur.fetchall()

    if not ahmedabad_rows:
        print("No Ahmedabad scraped data found — run load_retail_manual.py first")
        exit(1)

    total_inserted = 0
    total_skipped = 0

    for crop_id, price_date, ahmedabad_price in ahmedabad_rows:
        for city, factor in CITY_FACTORS.items():
            modeled_price = round(float(ahmedabad_price) * factor, 2)

            cur.execute("""
                INSERT INTO retail_price
                    (crop_id, city, platform, price_date, price, unit, data_type, confidence_note)
                VALUES (%s, %s, 'modeled', %s, %s, 'kg', 'modeled', %s)
                ON CONFLICT (crop_id, city, platform, price_date) DO NOTHING
            """, (crop_id, city, price_date, modeled_price, CONFIDENCE_NOTE))

            if cur.rowcount:
                total_inserted += 1
            else:
                total_skipped += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Modeled rows inserted: {total_inserted}")
    print(f"Modeled rows skipped (already exist): {total_skipped}")

if __name__ == "__main__":
    main()