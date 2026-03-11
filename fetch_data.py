"""
Netherlands Cabinet Dashboard — Data Fetcher
Kabinet-Jetten (D66 / VVD / CDA), sworn in 23 February 2026

The rijksoverheid.nl API slugs haven't changed between cabinets — the same
ministry slugs exist, just with different ministers. We skip the API ministry
list entirely and hardcode the correct Jetten minister per stable slug.

Run:  python backend/fetch_data.py
Out:  frontend/dashboard.json  (read by index.html)
"""

import requests
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path
import time

HEADERS = {"User-Agent": "NL-Cabinet-Dashboard/1.0 (github; open-source)"}

# ── Jetten cabinet — ministry slug → minister info ───────────────────────────
# Slugs are stable rijksoverheid.nl identifiers that don't change between cabinets.
# Ministers are correct as of 23 February 2026.
MINISTRIES = {
    "ministerie-van-algemene-zaken": {
        "name":        "Algemene Zaken",
        "minister":    "Rob Jetten",
        "role":        "Minister-President",
        "party":       "D66",
        "party_color": "#007a2b",
    },
    "ministerie-van-buitenlandse-zaken": {
        "name":        "Buitenlandse Zaken",
        "minister":    "Tom Berendsen",
        "role":        "Minister",
        "party":       "CDA",
        "party_color": "#005f49",
    },
    "ministerie-van-justitie-en-veiligheid": {
        "name":        "Justitie & Veiligheid",
        "minister":    "David van Weel",
        "role":        "Minister",
        "party":       "VVD",
        "party_color": "#c45e00",
    },
    "ministerie-van-binnenlandse-zaken-en-koninkrijksrelaties": {
        "name":        "Binnenlandse Zaken & Koninkrijksrelaties",
        "minister":    "Pieter Heerma",
        "role":        "Minister",
        "party":       "CDA",
        "party_color": "#005f49",
    },
    "ministerie-van-onderwijs-cultuur-en-wetenschap": {
        "name":        "Onderwijs, Cultuur & Wetenschap",
        "minister":    "Rianne Letschert",
        "role":        "Minister",
        "party":       "D66",
        "party_color": "#007a2b",
    },
    "ministerie-van-financien": {
        "name":        "Financiën",
        "minister":    "Eelco Heinen",
        "role":        "Minister",
        "party":       "VVD",
        "party_color": "#c45e00",
    },
    "ministerie-van-defensie": {
        "name":        "Defensie",
        "minister":    "Dilan Yeşilgöz",
        "role":        "Minister / Viceminister-president",
        "party":       "VVD",
        "party_color": "#c45e00",
    },
    "ministerie-van-infrastructuur-en-waterstaat": {
        "name":        "Infrastructuur & Waterstaat",
        "minister":    "Vincent Karremans",
        "role":        "Minister",
        "party":       "VVD",
        "party_color": "#c45e00",
    },
    "ministerie-van-economische-zaken-en-klimaat": {
        "name":        "Economische Zaken & Klimaat",
        "minister":    "Heleen Herbert",
        "role":        "Minister",
        "party":       "CDA",
        "party_color": "#005f49",
    },
    "ministerie-van-landbouw-visserij-voedselzekerheid-en-natuur": {
        # Renamed slug under Jetten
        "name":        "Landbouw, Visserij, Voedselzekerheid & Natuur",
        "minister":    "Jaimi van Essen",
        "role":        "Minister",
        "party":       "D66",
        "party_color": "#007a2b",
    },
    "ministerie-van-sociale-zaken-en-werkgelegenheid": {
        "name":        "Sociale Zaken & Werkgelegenheid",
        "minister":    "Hans Vijlbrief",
        "role":        "Minister",
        "party":       "D66",
        "party_color": "#007a2b",
    },
    "ministerie-van-volksgezondheid-welzijn-en-sport": {
        "name":        "Volksgezondheid, Welzijn & Sport",
        "minister":    "Sophie Hermans",
        "role":        "Minister",
        "party":       "VVD",
        "party_color": "#c45e00",
    },
}

# Cabinet start date — used for display only, not for filtering
# We show all recent press releases regardless of date because Jetten only
# started on 23 Feb 2026 and there are very few items since then.
CABINET_START = datetime(2026, 2, 23)

STOPWORDS = {
    "de","het","een","en","van","in","op","te","dat","is","aan","voor","met",
    "als","er","ook","zijn","maar","om","door","over","bij","tot","uit","nog",
    "dan","heeft","niet","wordt","worden","naar","dit","deze","die","zich",
    "meer","zo","al","nu","wel","kan","wil","zij","hun","per","minister",
    "ministers","ministerie","kabinet","staatssecretaris","rijksoverheid",
    "nieuwe","gaan","komen","maken","samen","andere","eerste","tweede","mln",
    "jaar","heel","veel","goed","the","and","for","are","will","heeft",
    "hebben","werd","waren","worden","wordt","zijn","was","geen","ook",
    "reeds","onder","verder","waarbij","hierbij","daarvoor","hierover",
    "daarmee","hiermee","daarin","hierin","daarna","daartoe","alsmede",
    "echter","tevens","aldus","welke","indien","teneinde","zullen","wordt",
}


# ── Fetch: Official API ───────────────────────────────────────────────────────
def fetch_api(slug: str, limit: int = 30) -> list:
    url = f"https://opendata.rijksoverheid.nl/v1/infotypes/news/ministries/{slug}"
    try:
        r = requests.get(url, params={"output": "json", "rows": limit},
                         headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"      API err: {e}")
    return []


# ── Fetch: RSS feed ───────────────────────────────────────────────────────────
def fetch_rss(slug: str) -> list:
    url = f"https://www.rijksoverheid.nl/ministeries/{slug}/nieuws.rss"
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:300].strip()
            date_parsed = None
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
                try:
                    date_parsed = datetime.strptime(pub, fmt).replace(tzinfo=None)
                    break
                except Exception:
                    pass
            if title:
                items.append({
                    "title":           title,
                    "canonicalUrl":    link,
                    "publicationDate": date_parsed.strftime("%Y-%m-%dT%H:%M:%S") if date_parsed else "",
                    "introduction":    desc,
                    "source":          "rss",
                })
    except Exception as e:
        print(f"      RSS err: {e}")
    return items


def merge(api_items, rss_items):
    seen, merged = set(), []
    for item in api_items:
        k = item.get("title", "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            item.setdefault("source", "api")
            merged.append(item)
    for item in rss_items:
        k = item.get("title", "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            merged.append(item)
    return merged


def parse_date(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime((s or "")[:19], fmt)
        except Exception:
            pass
    return None



# ── Analytics ─────────────────────────────────────────────────────────────────
def activity_stats(all_news: dict) -> list:
    now = datetime.now()
    rows = []
    for slug, entry in all_news.items():
        meta  = entry["meta"]
        items = entry["items"]
        c30 = c7 = 0
        last_date = None
        for item in items:
            d = parse_date(item.get("publicationDate", ""))
            if d:
                if (now - d).days <= 30: c30 += 1
                if (now - d).days <= 7:  c7  += 1
                if last_date is None or d > last_date: last_date = d
        days_silent = (now - last_date).days if last_date else 999
        status = "active" if days_silent <= 3 else ("quiet" if days_silent <= 10 else "silent")
        rows.append({
            "slug":             slug,
            "ministry":         meta["name"],
            "minister":         meta["minister"],
            "role":             meta["role"],
            "party":            meta["party"],
            "party_color":      meta["party_color"],
            "count_30d":        c30,
            "count_7d":         c7,
            "last_publication": last_date.isoformat() if last_date else None,
            "days_since_last":  days_silent,
            "status":           status,
        })
    return sorted(rows, key=lambda x: x["count_30d"], reverse=True)


def trending_topics(all_news: dict, top_n: int = 60) -> list:
    freq = Counter()
    for entry in all_news.values():
        for item in entry["items"]:
            text = item.get("title", "") + " " + item.get("introduction", "")
            words = re.findall(r'\b[a-zA-ZÀ-ÿ]{4,}\b', text.lower())
            freq.update(w for w in words if w not in STOPWORDS)
    return [{"word": w, "count": c} for w, c in freq.most_common(top_n)]


def build_feed(all_news: dict, limit: int = 120) -> list:
    feed = []
    for entry in all_news.values():
        meta = entry["meta"]
        for item in entry["items"]:
            d   = parse_date(item.get("publicationDate", ""))
            url = item.get("canonicalUrl", "") or "https://www.rijksoverheid.nl"
            if url and not url.startswith("http"):
                url = "https://www.rijksoverheid.nl" + url
            feed.append({
                "title":        item.get("title", ""),
                "date":         item.get("publicationDate", ""),
                "date_ts":      d.isoformat() if d else "",
                "date_display": d.strftime("%-d %b %Y") if d else "–",
                "ministry":     meta["name"],
                "minister":     meta["minister"],
                "party":        meta["party"],
                "party_color":  meta["party_color"],
                "url":          url,
                "intro":        item.get("introduction", "")[:250],
                "source":       item.get("source", "api"),
            })
    feed.sort(key=lambda x: x["date_ts"], reverse=True)
    return feed[:limit]


def party_breakdown(activity: list) -> list:
    parties: dict = {}
    for row in activity:
        p = row["party"]
        if p not in parties:
            parties[p] = {
                "party":     p,
                "color":     row["party_color"],
                "ministers": [],
                "total_30d": 0,
                "total_7d":  0,
            }
        parties[p]["ministers"].append(row["minister"])
        parties[p]["total_30d"] += row["count_30d"]
        parties[p]["total_7d"]  += row["count_7d"]
    return sorted(parties.values(), key=lambda x: x["total_30d"], reverse=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    out_dir = Path(__file__).parent.parent / "frontend"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n── Fetching news for {len(MINISTRIES)} Jetten cabinet ministries…\n")

    all_news: dict = {}
    for slug, meta in MINISTRIES.items():
        print(f"  {meta['name'][:52]:52s} ", end="", flush=True)
        api  = fetch_api(slug, limit=30)
        rss  = fetch_rss(slug)
        combined = merge(api, rss)

        all_news[slug] = {"meta": {**meta, "slug": slug}, "items": combined}
        print(f"API:{len(api):3d}  RSS:{len(rss):3d}  items:{len(combined):3d}")
        time.sleep(0.4)

    # Build outputs
    activity = activity_stats(all_news)
    topics   = trending_topics(all_news, top_n=60)
    feed     = build_feed(all_news, limit=120)
    parties  = party_breakdown(activity)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "cabinet":      "Kabinet-Jetten",
        "cabinet_start": CABINET_START.isoformat(),
        "activity":     activity,
        "topics":       topics,
        "feed":         feed,
        "parties":      parties,
    }

    out_path = out_dir / "dashboard.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    total = sum(len(e["items"]) for e in all_news.values())
    print(f"\n✅  {out_path}")
    print(f"   {len(activity)} ministeries | {total} Jetten-era items | {len(feed)} in feed | {len(topics)} topics")


if __name__ == "__main__":
    main()
