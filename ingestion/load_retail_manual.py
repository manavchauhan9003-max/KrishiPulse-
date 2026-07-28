import os
import csv
import io
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
import requests

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
RETAIL_SHEET_URL = os.getenv('RETAIL_SHEET_URL')

if not DATABASE_URL:
    print("DATABASE_URL not found — check .env file")
    exit(1)

if not RETAIL_SHEET_URL:
    print("RETAIL_SHEET_URL not found — check .env file")
    exit(1)

def fetch_sheet():
    response = requests.get(RETAIL_SHEET_URL)
    if response.status_code != 200:
        print(f"Failed to fetch Google Sheet: {response.status_code}")
        exit(1)
    return csv.DictReader(io.StringIO(response.text))

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    total_processed = 0
    total_inserted = 0
    total_skipped = 0

    reader = fetch_sheet()
    for row in reader:
        total_processed += 1

        crop_name = row['crop_name'].strip()
        cur.execute(
            "SELECT crop_id FROM crop_master WHERE crop_name = %s",
            (crop_name,)
        )
        result = cur.fetchone()
        if not result:
            print(f"Unmapped crop: {crop_name} — skipping")
            total_skipped += 1
            continue
        crop_id = result[0]

        try:
            price_date = datetime.strptime(row['entry_date'].strip(), '%Y-%m-%d').date()
        except ValueError:
            print(f"Bad date format: {row['entry_date']} — skipping. Use YYYY-MM-DD.")
            total_skipped += 1
            continue

        try:
            price = float(row['price_per_kg'].strip())
        except ValueError:
            print(f"Bad price for {crop_name} on {row['entry_date']} — skipping")
            total_skipped += 1
            continue

        if price < 1 or price > 1000:
            print(f"Suspicious price for {crop_name}: ₹{price}/kg — skipping")
            total_skipped += 1
            continue

        city = row['city'].strip()
        platform = row['platform'].strip()
        unit = row['unit'].strip()
        confidence_note = row['notes'].strip() or None

        cur.execute(
            """
            INSERT INTO retail_price
                (crop_id, city, platform, price_date, price, unit, data_type, confidence_note)
            VALUES (%s, %s, %s, %s, %s, %s, 'scraped', %s)
            ON CONFLICT (crop_id, city, platform, price_date) DO NOTHING
            """,
            (crop_id, city, platform, price_date, price, unit, confidence_note)
        )
        total_inserted += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    print(f"Total processed: {total_processed}")
    print(f"Total inserted: {total_inserted}")
    print(f"Total skipped: {total_skipped}")

if __name__ == "__main__":
    main()