# file: export_prf_history.py
import os
import time
import csv
from pathlib import Path
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

PRF_URL = "https://public-rma.fpac.usda.gov/apps/PRF"
DOWNLOAD_DIR = Path("data/PRF_Historical").resolve()
LOG_DONE = DOWNLOAD_DIR / "_completed_grids.csv"
START_YEAR = 1940   # use 1940 for ~80+ years; adjust as needed
END_YEAR = 2025     # current year shown in the tool (adjust yearly)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def make_driver():
    chrome_opts = Options()
    chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--window-size=1600,1200")
    # Set automatic download folder
    prefs = {
        "download.default_directory": str(DOWNLOAD_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    chrome_opts.add_experimental_option("prefs", prefs)
    return webdriver.Chrome(options=chrome_opts)

@contextmanager
def driver_ctx():
    d = make_driver()
    try:
        yield d
    finally:
        d.quit()

def wait_for(d, css, timeout=20):
    return WebDriverWait(d, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

def get_select_options(sel_el):
    sel = Select(sel_el)
    # skip the placeholder like "Select State"
    return [o for o in sel.options if (o.get_attribute("value") or "").strip()]

def ensure_tab(d, tab_text):
    # Tabs are buttons/links at top: "Grid Locator", "Historical Indexes", etc.
    # Click the one matching tab_text if not active
    tabs = d.find_elements(By.CSS_SELECTOR, "a, button")
    for t in tabs:
        if t.text.strip().lower() == tab_text.lower():
            t.click()
            time.sleep(0.5)
            return

def set_years(d, start_year, end_year):
    ensure_tab(d, "Historical Indexes")
    # Find Year Range selects (Start, End) near "Historical Filter"
    start_sel = wait_for(d, "select#HistoricalStartYear, select[name='HistoricalStartYear']")
    end_sel   = wait_for(d, "select#HistoricalEndYear, select[name='HistoricalEndYear']")
    Select(start_sel).select_by_visible_text(str(start_year))
    time.sleep(0.2)
    Select(end_sel).select_by_visible_text(str(end_year))
    time.sleep(0.2)

def get_completed():
    done = set()
    if LOG_DONE.exists():
        with open(LOG_DONE, newline="") as f:
            for row in csv.reader(f):
                if row:
                    done.add(row[0])
    return done

def mark_completed(grid_id):
    with open(LOG_DONE, "a", newline="") as f:
        csv.writer(f).writerow([grid_id])

def rename_latest_download(tmp_name="HistoricalIndexes.csv", final_name=None, retries=60):
    # The site typically downloads with a fixed name; we wait and then rename.
    src = DOWNLOAD_DIR / tmp_name
    for _ in range(retries):
        if src.exists():
            break
        time.sleep(1)
    if not src.exists():
        raise RuntimeError("Export did not produce the expected CSV file.")
    if final_name:
        dst = DOWNLOAD_DIR / final_name
        # if still being written, wait a moment
        time.sleep(0.5)
        src.replace(dst)
        return dst
    return src

def export_grid_history(d, grid_id, start_year, end_year):
    # Select the grid in the Location Information controls
    ensure_tab(d, "Historical Indexes")
    # Controls are shared UI; first choose State, then County, then Grid ID
    state_sel = wait_for(d, "select#State, select[name='State']")
    county_sel = wait_for(d, "select#County, select[name='County']")
    grid_sel = wait_for(d, "select#GridId, select[name='GridId']")

    # The grid dropdown only populates after state/county selections.
    # We search for the exact grid value under current state/county loop.
    Select(grid_sel).select_by_visible_text(str(grid_id))
    time.sleep(0.3)

    # Set year range
    set_years(d, start_year, end_year)

    # Click "Export to CSV" within Historical Indexes
    # The button typically contains text "Export to CSV"
    export_btns = [b for b in d.find_elements(By.XPATH, "//button|//a") if "export to csv" in b.text.lower()]
    if not export_btns:
        raise RuntimeError("Export to CSV button not found.")
    export_btns[0].click()

    # Rename the downloaded CSV to include the grid and year range
    final_name = f"grid_{grid_id}_{start_year}_{end_year}.csv"
    path = rename_latest_download(final_name=final_name)
    return path

def discover_all_grids(d):
    """Iterate State -> County -> Grid Select to enumerate all grid IDs."""
    ensure_tab(d, "Historical Indexes")
    state_sel = wait_for(d, "select#State, select[name='State']")
    county_sel = wait_for(d, "select#County, select[name='County']")
    grid_sel = wait_for(d, "select#GridId, select[name='GridId']")

    all_grids = []
    for s in get_select_options(state_sel):
        Select(state_sel).select_by_value(s.get_attribute("value"))
        time.sleep(0.4)
        for c in get_select_options(county_sel):
            Select(county_sel).select_by_value(c.get_attribute("value"))
            time.sleep(0.4)
            # Now grid list should be populated
            grids = get_select_options(grid_sel)
            for g in grids:
                grid_val = g.get_attribute("value").strip()
                if grid_val:
                    all_grids.append(grid_val)
    # De-duplicate while preserving order
    seen, ordered = set(), []
    for g in all_grids:
        if g not in seen:
            seen.add(g)
            ordered.append(g)
    return ordered

def main():
    done = get_completed()
    with driver_ctx() as d:
        d.get(PRF_URL)
        # Move into Historical Indexes tab
        ensure_tab(d, "Historical Indexes")

        # Discover grids across all states/counties
        grids = discover_all_grids(d)
        print(f"Discovered {len(grids)} unique Grid IDs.")

        # Loop & export
        for gid in grids:
            if gid in done:
                continue
            try:
                path = export_grid_history(d, gid, START_YEAR, END_YEAR)
                print(f"Saved {path.name}")
                mark_completed(gid)
                time.sleep(1.0)  # polite throttle
            except Exception as e:
                print(f"[WARN] Grid {gid} failed: {e}")
                # soft-fail and continue

if __name__ == "__main__":
    main()

