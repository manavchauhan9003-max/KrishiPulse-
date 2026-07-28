import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import requests
import psycopg2

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
DATA_GOV_API_KEY = os.getenv('DATA_GOV_API_KEY').strip()

if not DATABASE_URL:
    print("DATABASE_URL not found — check .env file")
    exit(1)

crop_names = ['Onion', 'Potato', 'Tomato', 'Garlic', 'Green Chilli']
raw_dir = 'pipeline/raw'
os.makedirs(raw_dir, exist_ok=True)

API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
}
PAGE_LIMIT = 100

def fetch_all_records(crop):
    all_records = []
    offset = 0
    total = None

    while True:
        params = {
            'api-key': DATA_GOV_API_KEY,
            'format': 'json',
            'limit': PAGE_LIMIT,
            'offset': offset,
            'filters[state.keyword]': 'Gujarat',
            'filters[commodity.keyword]': crop
        }
        response = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            print(f"Error fetching {crop} at offset {offset}: {response.status_code}")
            break

        data = response.json()
        records = data.get('records', [])
        if total is None:
            total = int(data.get('total', 0))

        all_records.extend(records)
        print(f"{crop}: fetched {len(all_records)} of {total} records")

        if len(records) < PAGE_LIMIT or len(all_records) >= total:
            break

        offset += PAGE_LIMIT
        time.sleep(0.5)

    return all_records

def get_or_create_mandi(cur, mandi_name, district):
    cur.execute(
        "SELECT mandi_id FROM mandi_master WHERE mandi_name = %s AND district = %s",
        (mandi_name, district)
    )
    result = cur.fetchone()
    if result:
        return result[0]
    cur.execute(
        "INSERT INTO mandi_master (mandi_name, district) VALUES (%s, %s) RETURNING mandi_id",
        (mandi_name, district)
    )
    return cur.fetchone()[0]

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Clear provisional flag for records older than 3 days
    cur.execute("""
        UPDATE wholesale_price
        SET is_provisional = false
        WHERE is_provisional = true
        AND price_date < CURRENT_DATE - INTERVAL '3 days'
    """)
    updated_rows = cur.rowcount
    conn.commit()
    print(f"Provisional flag cleared for {updated_rows} records older than 3 days.")

    total_records_processed = 0
    total_inserted_updated = 0
    total_skipped = 0
    total_flagged_provisional = 0
    today = datetime.now().strftime('%Y-%m-%d')

    for crop in crop_names:
        records = fetch_all_records(crop)

        with open(f'{raw_dir}/raw_wholesale_{crop.replace(" ", "_")}_{today}.json', 'w') as f:
            json.dump(records, f, indent=2)

        for record in records:
            total_records_processed += 1
            commodity = record['commodity']

            cur.execute("SELECT crop_id FROM crop_alias_map WHERE raw_string = %s", (commodity,))
            result = cur.fetchone()
            if not result:
                print(f"Unmapped crop: {commodity}")
                total_skipped += 1
                continue
            crop_id = result[0]

            mandi_name = record['market']
            district = record.get('district')
            mandi_id = get_or_create_mandi(cur, mandi_name, district)

            try:
                arrival_date = datetime.strptime(record['arrival_date'], '%d/%m/%Y').date()
            except (ValueError, TypeError):
                print(f"Bad date for {commodity} at {mandi_name}: {record.get('arrival_date')}")
                total_skipped += 1
                continue

            try:
                min_price_per_kg = float(record.get('min_price', 0)) / 100
                max_price_per_kg = float(record.get('max_price', 0)) / 100
                modal_price_per_kg = float(record.get('modal_price', 0)) / 100
            except (ValueError, TypeError):
                print(f"Bad price data for {commodity} at {mandi_name}")
                total_skipped += 1
                continue

            is_provisional = False
            CROP_PRICE_BOUNDS = {
                'Onion':        (2, 100),
                'Potato':       (3, 80),
                'Tomato':       (5, 150),
                'Garlic':       (20, 500),
                'Green Chilli': (10, 300),
            }
            lower, upper = CROP_PRICE_BOUNDS.get(commodity, (1, 500))
            if modal_price_per_kg < lower or modal_price_per_kg > upper:
                print(f"Suspicious price for {commodity} at {mandi_name}: {modal_price_per_kg}")
                is_provisional = True
                total_flagged_provisional += 1

            if (datetime.now().date() - arrival_date).days <= 3:
                is_provisional = True

            cur.execute(
                """
                INSERT INTO wholesale_price
                    (crop_id, mandi_id, variety, price_date, min_price, max_price, modal_price, unit, is_provisional)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'kg', %s)
                ON CONFLICT (crop_id, mandi_id, variety, price_date) DO UPDATE SET
                    min_price = EXCLUDED.min_price,
                    max_price = EXCLUDED.max_price,
                    modal_price = EXCLUDED.modal_price,
                    is_provisional = EXCLUDED.is_provisional
                """,
                (crop_id, mandi_id, record.get('variety'), arrival_date,
                 min_price_per_kg, max_price_per_kg, modal_price_per_kg, is_provisional)
            )
            total_inserted_updated += 1

        conn.commit()
        time.sleep(0.5)

    if total_records_processed == 0:
        print("ERROR: Zero records processed — pipeline likely broken or API returned nothing")
        cur.close()
        conn.close()
        exit(1)

    cur.close()
    conn.close()

    print(f"\nTotal records processed: {total_records_processed}")
    print(f"Total inserted/updated: {total_inserted_updated}")
    print(f"Total skipped: {total_skipped}")
    print(f"Total flagged as provisional/suspicious: {total_flagged_provisional}")

if __name__ == "__main__":
    main()