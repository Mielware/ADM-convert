import os
import requests
import time

# Folder for output
OUTPUT_DIR = "Historical_Index_Files"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Example API export endpoint (⚠️ this needs to be confirmed via browser dev tools!)
EXPORT_URL = "https://webapp.rma.usda.gov/apps/RIRS/PRFHistoricalIndexesHandler.ashx"

# Example list of grid IDs (you’d expand this with all grids you need)
GRID_IDS = [12345, 12346, 12347]  

def download_historical_index(grid_id, start_year=1948, end_year=2025):
    """Download PRF historical index for a single grid ID."""
    params = {
        "gridId": grid_id,
        "startYear": start_year,
        "endYear": end_year,
        "format": "csv"  # or "excel"
    }
    
    print(f"Downloading grid {grid_id}...")
    r = requests.get(EXPORT_URL, params=params)
    if r.status_code == 200 and r.content:
        filename = os.path.join(OUTPUT_DIR, f"grid_{grid_id}_{start_year}_{end_year}.csv")
        with open(filename, "wb") as f:
            f.write(r.content)
        print(f"Saved {filename}")
    else:
        print(f"Failed to fetch grid {grid_id}: {r.status_code}")

def main():
    for grid in GRID_IDS:
        download_historical_index(grid)
        time.sleep(1)  # throttle requests to avoid hammering USDA server

if __name__ == "__main__":
    main()
