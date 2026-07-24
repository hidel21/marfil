import json
import requests

urls = [
    "https://pydolarve.org/api/v1/dollar?page=bcv",
    "https://pydolarve.org/api/v1/dollar?page=binance",
]

for url in urls:
    print("URL:", url)
    try:
        r = requests.get(url, timeout=10)
        print("STATUS", r.status_code)
        data = r.json()
        print("KEYS", list(data.keys()))
        if isinstance(data, dict) and "monedas" in data:
            print("MONEDAS KEYS", list(data["monedas"].keys()))
            for k, v in data["monedas"].items():
                print("  COIN", k, "TYPE", type(v).__name__, "FIELDS", list(v.keys()) if isinstance(v, dict) else None)
        print(json.dumps(data, indent=2, ensure_ascii=False)[:4000])
    except Exception as exc:
        print("ERROR", exc)
    print("---")
