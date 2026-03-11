"""
Netherlands Cabinet Dashboard — Data Fetcher
Sources:
  1. opendata.rijksoverheid.nl  (official REST API, no key needed)
  2. RSS feeds per ministry     (fallback / supplement)

Run:    python backend/fetch_data.py
Output: frontend/data/dashboard.json   (read by index.html)
"""

import requests
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path
import time

# ── Schoof cabinet ministers (installed July 2024) ───────────────────────────
MINISTRIES = {
    "ministerie-van-algemene-zaken": {
        "name": "Algemene Zaken",
        "minister": "Dick Schoof",
        "role": "Minister-President",
        "party": "Independent",
        "party_color": "#555e6c",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-algemene-zaken/nieuws.rss",
    },
    "ministerie-van-binnenlandse-zaken-en-koninkrijksrelaties": {
        "name": "Binnenlandse Zaken & Koninkrijksrelaties",
        "minister": "Judith Uitermark",
        "role": "Minister",
        "party": "NSC",
        "party_color": "#0a4f8a",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-binnenlandse-zaken-en-koninkrijksrelaties/nieuws.rss",
    },
    "ministerie-van-buitenlandse-zaken": {
        "name": "Buitenlandse Zaken",
        "minister": "Caspar Veldkamp",
        "role": "Minister",
        "party": "NSC",
        "party_color": "#0a4f8a",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-buitenlandse-zaken/nieuws.rss",
    },
    "ministerie-van-defensie": {
        "name": "Defensie",
        "minister": "Ruben Brekelmans",
        "role": "Minister",
        "party": "VVD",
        "party_color": "#e17000",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-defensie/nieuws.rss",
    },
    "ministerie-van-economische-zaken": {
        "name": "Economische Zaken",
        "minister": "Dirk Beljaarts",
        "role": "Minister",
        "party": "PVV",
        "party_color": "#003580",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-economische-zaken/nieuws.rss",
    },
    "ministerie-van-financien": {
        "name": "Financiën",
        "minister": "Eelco Heinen",
        "role": "Minister",
        "party": "VVD",
        "party_color": "#e17000",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-financien/nieuws.rss",
    },
    "ministerie-van-infrastructuur-en-waterstaat": {
        "name": "Infrastructuur & Waterstaat",
        "minister": "Barry Madlener",
        "role": "Minister",
        "party": "PVV",
        "party_color": "#003580",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-infrastructuur-en-waterstaat/nieuws.rss",
    },
    "ministerie-van-justitie-en-veiligheid": {
        "name": "Justitie & Veiligheid",
        "minister": "David van Weel",
        "role": "Minister",
        "party": "Independent",
        "party_color": "#555e6c",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-justitie-en-veiligheid/nieuws.rss",
    },
    "ministerie-van-landbouw-natuur-en-voedselkwaliteit": {
        "name": "Landbouw, Natuur & Voedselkwaliteit",
        "minister": "Femke Wiersma",
        "role": "Minister",
        "party": "BBB",
        "party_color": "#275937",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-landbouw-natuur-en-voedselkwaliteit/nieuws.rss",
    },
    "ministerie-van-onderwijs-cultuur-en-wetenschap": {
        "name": "Onderwijs, Cultuur & Wetenschap",
        "minister": "Eppo Bruins",
        "role": "Minister",
        "party": "NSC",
        "party_color": "#0a4f8a",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-onderwijs-cultuur-en-wetenschap/nieuws.rss",
    },
    "ministerie-van-sociale-zaken-en-werkgelegenheid": {
        "name": "Sociale Zaken & Werkgelegenheid",
        "minister": "Eddy van Hijum",
        "role": "Minister",
        "party": "NSC",
        "party_color": "#0a4f8a",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-sociale-zaken-en-werkgelegenheid/nieuws.rss",
    },
    "ministerie-van-volksgezondheid-welzijn-en-sport": {
        "name": "Volksgezondheid, Welzijn & Sport",
        "minister": "Fleur Agema",
        "role": "Minister",
        "party": "PVV",
        "party_color": "#003580",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-volksgezondheid-welzijn-en-sport/nieuws.rss",
    },
    "ministerie-van-volkshuisvesting-en-ruimtelijke-ordening": {
        "name": "Volkshuisvesting & Ruimtelijke Ordening",
        "minister": "Mona Keijzer",
        "role": "Minister",
        "party": "BBB",
        "party_color": "#275937",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-volkshuisvesting-en-ruimtelijke-ordening/nieuws.rss",
    },
    "ministerie-van-klimaat-en-groene-groei": {
        "name": "Klimaat & Groene Groei",
        "minister": "Sophie Hermans",
        "role": "Minister",
        "party": "VVD",
        "party_color": "#e17000",
        "rss": "https://www.rijksoverheid.nl/ministeries/ministerie-van-klimaat-en-groene-groei/nieuws.rss",
    },
}

STOPWORDS = {
    "de", "het", "een", "en", "van", "in", "op", "te", "dat", "is", "aan",
    "voor", "met", "als", "er", "ook", "zijn", "maar", "om", "door", "over",
    "bij", "tot", "uit", "nog", "dan", "heeft", "niet", "wordt", "worden",
    "naar", "dit", "deze", "die", "zich", "meer", "zo", "al", "nu", "wel",
    "kan", "wil", "zij", "hun", "per", "minister", "ministers", "ministerie",
    "kabinet", "staatssecretaris", "rijksoverheid", "nieuwe", "gaan", "komen",
    "maken", "samen", "andere", "eerste", "tweede", "mln", "euro", "miljoen",
    "jaar", "heel", "veel", "goed", "the", "and", "for", "of", "are", "will",
    "heeft", "hebben", "werd", "waren", "worden", "wordt", "zijn", "was",
}

HEADERS = {"User-Agent": "NL-Cabinet-Dashboard/1.0 (github.com; open-source)"}


# ── Source 1: Official REST API ───────────────────────────────────────────────
def fetch_api(slug: str, limit: int = 25) -> list:
    url = f"https://opendata.rijksoverheid.nl/v1/infotypes/news/ministries/{slug}"
    try:
        r = requests.get(url, params={"output": "json", "rows": limit},
                         headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"    [API error] {slug}: {e}")
    return []


# ── Source 2: RSS feeds ───────────────────────────────────────────────────────
def fetch_rss(url: str) -> list:
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
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:300]
            date_parsed = None
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
                try:
                    date_parsed = datetime.strptime(pub, fmt).replace(tzinfo=None)
                    break
                except Exception:
                    pass
            items.append({
                "title": title,
                "canonicalUrl": link,
                "publicationDate": date_parsed.strftime("%Y-%m-%dT%H:%M:%S") if date_parsed else "",
                "introduction": desc,
                "source": "rss",
            })
    except Exception as e:
        print(f"    [RSS error] {url}: {e}")
    return items


# ── Merge & deduplicate ───────────────────────────────────────────────────────
def merge(api_items: list, rss_items: list) -> list:
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


# ── Date parsing ──────────────────────────────────────────────────────────────
def parse_date(s: str):
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
    for slug, items in all_news.items():
        meta = MINISTRIES[slug]
        c30 = c7 = 0
        last_date = None
        for item in items:
            d = parse_date(item.get("publicationDate", ""))
            if d:
                if (now - d).days <= 30:
                    c30 += 1
                if (now - d).days <= 7:
                    c7 += 1
                if last_date is None or d > last_date:
                    last_date = d
        days_silent = (now - last_date).days if last_date else 999
        status = "active" if days_silent <= 3 else ("quiet" if days_silent <= 10 else "silent")
        rows.append({
            "slug": slug,
            "ministry": meta["name"],
            "minister": meta["minister"],
            "role": meta["role"],
            "party": meta["party"],
            "party_color": meta["party_color"],
            "count_30d": c30,
            "count_7d": c7,
            "last_publication": last_date.isoformat() if last_date else None,
            "days_since_last": days_silent,
            "status": status,
        })
    return sorted(rows, key=lambda x: x["count_30d"], reverse=True)


def trending_topics(all_news: dict, top_n: int = 60) -> list:
    freq = Counter()
    for items in all_news.values():
        for item in items:
            text = item.get("title", "") + " " + item.get("introduction", "")
            words = re.findall(r'\b[a-zA-ZÀ-ÿ]{4,}\b', text.lower())
            freq.update(w for w in words if w not in STOPWORDS)
    return [{"word": w, "count": c} for w, c in freq.most_common(top_n)]


def build_feed(all_news: dict, limit: int = 100) -> list:
    feed = []
    for slug, items in all_news.items():
        meta = MINISTRIES[slug]
        for item in items:
            d = parse_date(item.get("publicationDate", ""))
            feed.append({
                "title": item.get("title", ""),
                "date": item.get("publicationDate", ""),
                "date_ts": d.isoformat() if d else "",
                "date_display": d.strftime("%-d %b %Y") if d else "–",
                "ministry": meta["name"],
                "minister": meta["minister"],
                "party": meta["party"],
                "party_color": meta["party_color"],
                "url": item.get("canonicalUrl", "https://www.rijksoverheid.nl"),
                "intro": item.get("introduction", "")[:250],
                "source": item.get("source", "api"),
            })
    feed.sort(key=lambda x: x["date_ts"], reverse=True)
    return feed[:limit]


def party_breakdown(activity: list) -> list:
    parties: dict = {}
    for row in activity:
        p = row["party"]
        if p not in parties:
            parties[p] = {
                "party": p,
                "color": row["party_color"],
                "ministers": [],
                "total_30d": 0,
                "total_7d": 0,
            }
        parties[p]["ministers"].append(row["minister"])
        parties[p]["total_30d"] += row["count_30d"]
        parties[p]["total_7d"]  += row["count_7d"]
    return sorted(parties.values(), key=lambda x: x["total_30d"], reverse=True)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    out_dir = Path(__file__).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    all_news: dict = {}
    print("Fetching data...\n")
    for slug, meta in MINISTRIES.items():
        print(f"  {meta['name']:45s} ", end="", flush=True)
        api  = fetch_api(slug, limit=25)
        rss  = fetch_rss(meta["rss"])
        combined = merge(api, rss)
        all_news[slug] = combined
        print(f"API:{len(api):3d}  RSS:{len(rss):3d}  merged:{len(combined):3d}")
        time.sleep(0.35)  # polite crawl rate

    activity = activity_stats(all_news)
    topics   = trending_topics(all_news, top_n=60)
    feed     = build_feed(all_news, limit=100)
    parties  = party_breakdown(activity)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "activity": activity,
        "topics":   topics,
        "feed":     feed,
        "parties":  parties,
    }

    out_path = out_dir / "dashboard.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {out_path}")
    print(f"   {len(activity)} ministries | {len(topics)} topics | {len(feed)} press releases")


if __name__ == "__main__":
    main()
