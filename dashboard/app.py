import streamlit as st
import psycopg2

# Title and initial message
st.title("KrishiPulse — Setup Check")
st.write("App is live.")

# Button to run DB Test
if st.button("Run DB Test"):
    try:
        # Connect to the database using credentials from Streamlit secrets
        conn = psycopg2.connect(st.secrets["DATABASE_URL"])
        
        # Create a table if it doesn't exist
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS setup_test (
                    id SERIAL PRIMARY KEY,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            conn.commit()
            
        # Insert a test row into the table
        with conn.cursor() as cur:
            cur.execute("INSERT INTO setup_test (note) VALUES ('KrishiPulse Phase 0 test')")
            conn.commit()
        
        # Fetch and display the last 5 rows from the table
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM setup_test ORDER BY created_at DESC LIMIT 5")
            rows = cur.fetchall()
            
        # Display the results in a Streamlit dataframe
        st.dataframe(rows)
        
    except Exception as e:
        st.error(f"Error during database operation: {e}")
    
    finally:
        if conn:
            conn.close()