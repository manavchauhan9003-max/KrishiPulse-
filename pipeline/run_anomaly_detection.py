import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("DATABASE_URL not found — check .env file")
    exit(1)

SQL_PATH = 'pipeline/anomaly_detection.sql'

def main():
    with open(SQL_PATH, 'r') as f:
        sql = f.read()

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(sql)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM price_anomaly")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM price_anomaly WHERE anomaly_flag = true")
    flagged = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(f"Anomaly detection complete. Total rows: {total}, Flagged: {flagged}")

if __name__ == "__main__":
    main()