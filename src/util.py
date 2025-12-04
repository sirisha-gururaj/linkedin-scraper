import csv
import os

def save_csv(path, data):
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data.keys())
        if not exists:
            writer.writeheader()
        writer.writerow(data)
    print(f"[INFO] Saved → {path}")
