import requests
from dotenv import load_dotenv
import os
import json
import time

load_dotenv()
DATA_GOV_API_KEY = os.getenv('DATA_GOV_API_KEY').strip()

api_url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

commodity_values = ["Onion", "Potato", "Tomato", "Garlic", "Green Chilli"]
all_results = {}
unique_data = {}

for crop in commodity_values:
    params = {
        'api-key': DATA_GOV_API_KEY,
        'format': 'json',
        'limit': 20,
        'filters[state.keyword]': 'Gujarat',
        'filters[commodity.keyword]': crop
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
    }

    response = requests.get(api_url, params=params, headers=headers)

    if response.status_code == 200:
        data = response.json()
        all_results[crop] = data['records']

        # Collect unique commodity and variety values
        unique_commodity = data['records'][0]['commodity']
        unique_varieties = {item['variety'] for item in data['records']}
        unique_data[crop] = {
            'unique_commodity': unique_commodity,
            'unique_varieties': list(unique_varieties)
        }
    else:
        print(f"Error fetching data for {crop}: {response.status_code}")
        all_results[crop] = []

    time.sleep(0.5)

# Save the combined result to ingestion/raw_sample_all_crops.json
os.makedirs('ingestion', exist_ok=True)
with open('ingestion/raw_sample_all_crops.json', 'w') as f:
    json.dump(all_results, f, indent=2)

# Print unique commodity and variety values for each crop
for crop, data in unique_data.items():
    print(f"Crop: {crop}")
    print(f"Unique Commodity: {data['unique_commodity']}")
    print(f"Unique Varieties: {', '.join(data['unique_varieties'])}")