#!/usr/bin/env python3
"""Daily data updater for the US economic dashboard.
Runs on GitHub Actions (full internet). Fetches the 5 economic indicators
from FRED and 3 stock indices (monthly OHLC -> close) from Stooq, plus ISM PMI
from Investing.com (best effort), and writes data.json.

Resilient: each source is wrapped in try/except. On failure for a series it
keeps the previous values from the existing data.json so the dashboard never
goes blank.
"""
import json, os, sys, datetime, urllib.request, urllib.error, io, csv, re

BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(BASE, "data.json")
UA   = {"User-Agent": "Mozilla/5.0 (compatible; econ-dashboard/1.0)"}
START = "2015-01"   # trim indicators to this month onward

def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def load_prev():
    try:
        return json.load(open(OUT, encoding="utf-8"))
    except Exception:
        return {"indicators": {}, "indices": {}}

# ---------- FRED ----------
def fred_csv(series_id):
    """Return list[(YYYY-MM, float)] from the keyless fredgraph CSV endpoint."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    text = get(url)
    rows = []
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    for row in rd:
        if len(row) < 2:
            continue
        d, v = row[0].strip(), row[1].strip()
        if v in (".", "", "NaN"):
            continue
        try:
            rows.append((d[:7], float(v)))
        except ValueError:
            continue
    return rows

def mom_pct(rows):
    """Month-over-month % change from a level series."""
    out = []
    for i in range(1, len(rows)):
        d, v = rows[i]
        pv = rows[i-1][1]
        if pv:
            out.append((d, round((v/pv - 1) * 100, 2)))
    return out

def quarter_month(d):  # FRED quarterly dates already start at 01/04/07/10
    return d

# ---------- Stooq (indices, monthly OHLC) ----------
def stooq_monthly_close(symbol):
    """Return list[(YYYY-MM, close)] for a stooq symbol, monthly interval."""
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=m"
    text = get(url)
    rows = []
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    if not header or header[0].lower() != "date":
        raise RuntimeError(f"stooq {symbol}: unexpected response")
    ci = {name: i for i, name in enumerate(h.lower() for h in header)}
    for row in rd:
        if len(row) < 5:
            continue
        try:
            d = row[ci["date"]][:7]
            close = float(row[ci["close"]])
            rows.append((d, round(close, 2)))
        except (ValueError, KeyError):
            continue
    return rows

# ---------- ISM PMI (Investing.com, best effort) ----------
MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

def ism_pmi():
    url = "https://www.investing.com/economic-calendar/ism-manufacturing-pmi-173"
    text = get(url)
    # rows like: "Jun 01, 2026 (May) | 14:00 | 54.0 | 53.3 | 52.7"
    pat = re.compile(r"\(([A-Z][a-z]{2})\)\s*\|[^|]*\|\s*([0-9]{2}\.[0-9])")
    found = {}
    for m in pat.finditer(text):
        mon = MONTHS.get(m.group(1))
        val = float(m.group(2))
        if mon:
            found[mon] = val  # month -> actual (most recent year context)
    # Build YYYY-MM by assuming the listed months are the most recent ones.
    # We can't be 100% sure of year from regex alone; keep prev data and only
    # add/refresh months we can place against the current calendar.
    out = {}
    today = datetime.date.today()
    y = today.year
    for off in range(0, 14):
        d = (today.replace(day=1) - datetime.timedelta(days=off*28)).strftime("%Y-%m")
        mm = d[5:7]
        if mm in found:
            out[d] = found[mm]
    return [(k, v) for k, v in sorted(out.items())]

def trim(rows, start):
    return [(d, v) for d, v in rows if d >= start]

def to_data(rows):
    return [{"d": d, "v": v} for d, v in rows]

def to_close(rows, start):
    return [{"d": d, "c": v} for d, v in rows if d >= start]

def main():
    prev = load_prev()
    out = {
        "generated": datetime.date.today().isoformat(),
        "indices_kind": "close",
        "indicators": {},
        "indices": {},
    }
    log = []

    indic = [
        ("unrate", "UNRATE", "실업률", "%", "monthly", "FRED (BLS)", "level"),
        ("indpro", "INDPRO", "산업생산 (전월대비)", "%", "monthly", "FRED (Federal Reserve)", "mom"),
        ("retail", "RSAFS", "소매판매 (전월대비)", "%", "monthly", "FRED (Census)", "mom"),
        ("gdp", "A191RL1Q225SBEA", "GDP 성장률 (연율)", "%", "quarterly", "FRED (BEA)", "level"),
    ]
    for key, sid, name, unit, freq, src, kind in indic:
        try:
            raw = fred_csv(sid)
            rows = mom_pct(raw) if kind == "mom" else raw
            rows = trim(rows, START)
            if not rows:
                raise RuntimeError("no rows")
            out["indicators"][key] = {"name": name, "unit": unit, "freq": freq,
                                      "source": src, "data": to_data(rows)}
            log.append(f"{key}: {len(rows)} ({rows[0][0]}~{rows[-1][0]})")
        except Exception as e:
            if key in prev.get("indicators", {}):
                out["indicators"][key] = prev["indicators"][key]
                log.append(f"{key}: FAILED ({e}) -> kept previous")
            else:
                log.append(f"{key}: FAILED ({e}) -> missing")

    # PMI
    try:
        pmi_rows = ism_pmi()
        prev_pmi = {p["d"]: p["v"] for p in prev.get("indicators", {}).get("pmi", {}).get("data", [])}
        for d, v in pmi_rows:
            prev_pmi[d] = v
        merged = sorted(prev_pmi.items())
        merged = [(d, v) for d, v in merged if d >= "2024-01"]
        out["indicators"]["pmi"] = {"name": "ISM 제조업 PMI", "unit": "index",
            "freq": "monthly", "source": "Investing.com (ISM)", "data": to_data(merged)}
        log.append(f"pmi: {len(merged)}")
    except Exception as e:
        if "pmi" in prev.get("indicators", {}):
            out["indicators"]["pmi"] = prev["indicators"]["pmi"]
            log.append(f"pmi: FAILED ({e}) -> kept previous")

    # Indices via Stooq
    idx = [
        ("spx", "^spx", "S&P 500"),
        ("dji", "^dji", "다우존스"),
        ("ndx", "^ndx", "나스닥 100"),
    ]
    for key, sym, name in idx:
        try:
            rows = stooq_monthly_close(sym)
            rows = to_close(rows, START)
            if not rows:
                raise RuntimeError("no rows")
            out["indices"][key] = {"name": name, "unit": "index", "freq": "monthly",
                "source": "Stooq", "note": "월간 종가", "data": rows}
            log.append(f"{key}: {len(rows)} ({rows[0]['d']}~{rows[-1]['d']})")
        except Exception as e:
            if key in prev.get("indices", {}):
                out["indices"][key] = prev["indices"][key]
                log.append(f"{key}: FAILED ({e}) -> kept previous")
            else:
                log.append(f"{key}: FAILED ({e}) -> missing")

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("Updated data.json:")
    print("\n".join("  " + l for l in log))

if __name__ == "__main__":
    main()
