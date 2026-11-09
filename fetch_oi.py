"""
NSE participant-wise OI (FII / DII / Pro) roz download karke oi_history.csv me jodta hai.
Sirf Python standard library use hoti hai (kuch install nahi karna).

Env variables (optional):
  START_DATE, END_DATE  ->  YYYY-MM-DD (backfill ke liye). Na diye ho to pichhle 7 din check hote hain.
"""
import csv, os, re, sys, time, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone

HIST = "oi_history.csv"
HEAD = ["Date", "Participant", "Index Fut Long", "Index Fut Short",
        "Index Call Long", "Index Call Short", "Index Put Long", "Index Put Short", "Date (ISO)"]
# Date column me Google Sheets/Excel ka serial number likha jata hai (date text ban ne ki dikkat se bachne ke liye)
EPOCH = date(1899, 12, 30)
ORDER = {"FII": 0, "DII": 1, "Pro": 2}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
URLS = [
    "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d}.csv",
    "https://archives.nseindia.com/content/nsccl/fao_participant_oi_{d}.csv",
]


def fetch_text(url):
    """(HTTP status, text). Network error par (0, None)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8-sig", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        print(f"    network error: {e}")
        return 0, None


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", str(s).lower())).strip()


def parse(text, day):
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().lower().startswith("client type")), -1)
    if start < 0:
        return None
    rows = list(csv.reader(lines[start:]))
    head = [norm(x) for x in rows[0]]
    names = ["future index long", "future index short", "option index call long",
             "option index call short", "option index put long", "option index put short"]
    if any(n not in head for n in names):
        return None
    idx = [head.index(n) for n in names]
    out = {}
    for r in rows[1:]:
        if not r:
            continue
        p = next((k for k in ORDER if k.lower() == r[0].strip().lower()), None)
        if p:
            out[p] = [day.isoformat(), p] + [int(str(r[i]).replace(",", "").strip() or 0) for i in idx]
    return [out[k] for k in sorted(out, key=ORDER.get)] if len(out) == 3 else None


def get_day(day):
    """('ok', rows) / ('none', None) = file nahi (holiday/abhi publish nahi) / ('error', None) = block ya parse issue"""
    saw_error = False
    for tpl in URLS:
        url = tpl.format(d=day.strftime("%d%m%Y"))
        status, text = fetch_text(url)
        print(f"  {day} {url.split('/')[2]} -> HTTP {status}")
        if status == 200 and text:
            rows = parse(text, day)
            if rows:
                return "ok", rows
            print("    file mili par format samajh nahi aaya")
            saw_error = True
        elif status != 404:
            saw_error = True
    return ("error", None) if saw_error else ("none", None)


def load_hist():
    rows = []
    if os.path.exists(HIST):
        with open(HIST, newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            next(r, None)
            for x in r:
                if len(x) >= 9:
                    rows.append([x[8]] + x[1:8])      # naya format: ISO date aakhri column me
                elif len(x) == 8:
                    rows.append(x)                      # purana format
    return rows


def main():
    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()
    s, e = os.environ.get("START_DATE", "").strip(), os.environ.get("END_DATE", "").strip()
    end = date.fromisoformat(e) if e else today
    start = date.fromisoformat(s) if s else end - timedelta(days=7)

    hist = load_hist()
    have = {r[0] for r in hist}
    added = errors = 0
    d = start
    while d <= end:
        if d.weekday() < 5 and d.isoformat() not in have:
            status, rows = get_day(d)
            if status == "ok":
                hist.extend(rows); have.add(d.isoformat()); added += 1
            elif status == "error":
                errors += 1
            time.sleep(1)
        d += timedelta(days=1)

    hist.sort(key=lambda r: (r[0], ORDER.get(r[1], 9)))
    with open(HIST, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEAD)
        for r in hist:
            serial = (date.fromisoformat(r[0]) - EPOCH).days
            w.writerow([serial] + r[1:8] + [r[0]])
    print(f"\nNaye din add hue: {added} | errors (block/format): {errors} | total rows: {len(hist)}")
    if errors and not added:
        print("NSE se koi data nahi aaya (shayad GitHub ko block kiya hai). Upar ke HTTP codes dekho.")
        sys.exit(1)


if __name__ == "__main__":
    main()
