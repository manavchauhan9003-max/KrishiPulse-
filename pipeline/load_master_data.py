import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("DATABASE_URL not found — check .env file")
    exit(1)

crop_names = ['Onion', 'Potato', 'Tomato', 'Garlic', 'Green Chilli']

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Insert into crop_master
    crop_master_count = 0
    for name in crop_names:
        cur.execute(
            "INSERT INTO crop_master (crop_name) VALUES (%s) ON CONFLICT (crop_name) DO NOTHING",
            (name,)
        )
        crop_master_count += cur.rowcount
    conn.commit()
    print(f"Inserted {crop_master_count} rows into crop_master")

    # Insert into crop_alias_map, linking via crop_name lookup
    alias_count = 0
    for name in crop_names:
        cur.execute(
            """
            INSERT INTO crop_alias_map (raw_string, crop_id)
            SELECT %s, crop_id FROM crop_master WHERE crop_name = %s
            ON CONFLICT (raw_string) DO NOTHING
            """,
            (name, name)
        )
        alias_count += cur.rowcount
    conn.commit()
    print(f"Inserted {alias_count} rows into crop_alias_map")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()