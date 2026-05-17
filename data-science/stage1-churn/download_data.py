"""Fetch the IBM Telco Customer Churn dataset into ./data/telco_churn.csv."""
from pathlib import Path
import sys
import requests

URL = (
    "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/"
    "master/data/Telco-Customer-Churn.csv"
)
OUT = Path(__file__).parent / "data" / "telco_churn.csv"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        print(f"Already have {OUT} ({OUT.stat().st_size:,} bytes). Skipping.")
        return 0

    print(f"Downloading from {URL} ...")
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    OUT.write_bytes(r.content)
    print(f"Saved {len(r.content):,} bytes to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
