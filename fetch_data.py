"""
Netherlands Cabinet Dashboard — Data Fetcher
Kabinet-Jetten (D66 / VVD / CDA), sworn in 23 February 2026

Strategy:
  1. Fetch the official ministry list from the API to get correct slugs
  2. Match those slugs to Jetten cabinet ministers
  3. Fetch news per ministry via API + RSS
  4. Write frontend/dashboard.json

Run:  python backend/fetch_data.py
"""

import requests
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path
import time

HEADERS = {"User-Agent": "NL-Cabinet-Dashboard/1.0 (github; open-source non-commercial)"}

# ── Jetten cabinet ministers, keyed by ministry name fragments for matching ──
# Each entry: partial Dutch ministry name → minister info
MINISTER_MAP = [
    ("algemene zaken",                   "Rob Jetten",              "Minister-President", "D66"),
    ("buitenlandse zaken",               "Tom Berendsen",           "Minister",           "CDA"),
    ("buitenlandse handel",              "Sjoerd Sjoerdsma",        "Minister",           "D66"),
    ("justitie",                         "David van Weel",          "Minister",           "VVD"),
    ("binnenlandse zaken",               "Pieter Heerma",           "Minister",           "CDA"),
    ("volkshuisvesting",                 "Elanor Boekholt-O'Sullivan","Minister",         "D66"),
    ("onderwijs",                        "Rianne Letschert",        "Minister",           "D66"),
    ("financien",                        "Eelco Heinen",            "Minister",           "VVD"),
    ("financiën",                        "Eelco Heinen",            "Minister",           "VVD"),
    ("defensie",                         "Dilan Yeşilgöz",          "Minister",           "VVD"),
    ("infrastructuur",                   "Vincent Karremans",       "Minister",           "VVD"),
    ("economische zaken",                "Heleen Herbert",          "Minister",           "CDA"),
    ("landbouw",                         "Jaimi van Essen",         "Minister",           "D66"),
    ("sociale zaken",                    "Hans Vijlbrief",          "Minister",           "D66"),
    ("volksgezondheid",                  "Sophie Hermans",          "Minister",           "VVD"),
    ("asiel",                            "Bart van den Brink",      "Minister",           "CDA"),
]

PARTY_COLORS = {
    "D66": "#007a2b",
    "VVD": "#c45e00",
    "CDA": "#005f49",
}

STOPWORDS = {
    "de","het","een","en","van","in","op","te","dat","is","aan","voor","met",
    "als","er","ook","zijn","maar","om","door","over","bij","tot","uit","nog",
    "dan","heeft","niet","wordt","worden","naar","dit","deze","die","zich",
    "meer","zo","al","nu","wel","kan","wil","zij","hun","per","minister",
    "ministers","ministerie","kabinet","staatssecretaris","rijksoverheid",
    "nieuwe","gaan","komen","maken","samen","andere","eerste","tweede","mln",
    "jaar","heel","veel","goed","the","and","for","are","will","heeft",
    "hebben","werd","waren","worden","wordt","zijn","was","naar","zijn",
    "geen","ook","reeds","onder","verder","waarbij","hierbij","daarvoor",
    "hierover","daarmee","hiermee","daarin","hierin","daarna","hierna",
    "daartoe","hiertoe","daarmee","alsmede","echter","tevens","aldus",
}


# ── Step 1: fetch the real ministry slugs from the API ───────────────────────
def fetch_ministry_list() -> list[dict]:
    """Returns list of {id, name, slug, title} from the official API."""
    url = "https://opendata.rijksoverheid.nl/v1/infotypes/ministry"
    try:
        r = requests.get(url, params={"output": "json", "rows": 50}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        ministries = []
        for item in (data if isinstance(data, list) else []):
            # The canonical URL ends in the slug, e.g. .../ministerie-van-financien
            canonical = item.get("canonicalUrl", "") or item.get("canonical", "")
            slug = canonical.rstrip("/").split("/")[-1] if canonical else ""
            name = item.get("name", "") or item.get("title", "")
            ministries.append({"id": item.get("id",""), "name": name, "slug": slug})
        print(f"  Found {len(ministries)} ministries in API")
        return ministries
    except Exception as e:
        print(f"  [!] Could not fetch ministry list: {e}")
        return []


def match_minister(ministry_name: str, ministry_slug: str) -> dict | None:
    """Match a ministry name/slug to a Jetten cabinet minister."""
    search = (ministry_name + " " + ministry_slug).lower()
    for fragment, minister, role, party in MINISTER_MAP:
        if fragment.lower() in search:
            return {
                "minister": minister,
                "role": role,
                "party": party,
                "party_color": PARTY_COLORS.get(party, "#888"),
            }
    return None


# ── Step 2: fetch news per ministry ─────────────────────────────────────────
def fetch_api_news(slug: str, limit: int = 30) -> list:
    url = f"https://opendata.rijksoverheid.nl/v1/infotypes/news/ministries/{slug}"
    try:
        r = requests.get(url, params={"output": "json", "rows": limit},
                         headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"      API error: {e}")
    return []


def build_rss_url(slug: str) -> str:
    return f"https://www.rijksoverheid.nl/ministeries/{slug}/nieuws.rss"


def fetch_rss(slug: str) -> list:
    url = build_rss_url(slug)
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
                    "title": title,
                    "canonicalUrl": link,
                    "publicationDate": date_parsed.strftime("%Y-%m-%dT%H:%M:%S") if date_parsed else "",
                    "introduction": desc,
                    "source": "rss",
                })
    except Exception as e:
        print(f"      RSS error: {e}")
    return items


def merge(api_items, rss_items):
    seen, merged = set(), []
    for item in api_items:
        k = item.get("title","").strip().lower()
        if k and k not in seen:
            seen.add(k)
            item.setdefault("source", "api")
            merged.append(item)
    for item in rss_items:
        k = item.get("title","").strip().lower()
        if k and k not in seen:
            seen.add(k)
            merged.append(item)
    return merged


# ── Date utils ────────────────────────────────────────────────────────────────
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
    for entry in all_news.values():
        meta  = entry["meta"]
        items = entry["items"]
        c30 = c7 = 0
        last_date = None
        for item in items:
            d = parse_date(item.get("publicationDate",""))
            if d:
                if (now - d).days <= 30: c30 += 1
                if (now - d).days <= 7:  c7  += 1
                if last_date is None or d > last_date: last_date = d
        days_silent = (now - last_date).days if last_date else 999
        status = "active" if days_silent <= 3 else ("quiet" if days_silent <= 10 else "silent")
        rows.append({
            "slug":             meta["slug"],
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
            text = item.get("title","") + " " + item.get("introduction","")
            words = re.findall(r'\b[a-zA-ZÀ-ÿ]{4,}\b', text.lower())
            freq.update(w for w in words if w not in STOPWORDS)
    return [{"word": w, "count": c} for w, c in freq.most_common(top_n)]


def build_feed(all_news: dict, limit: int = 100) -> list:
    feed = []
    for entry in all_news.values():
        meta  = entry["meta"]
        for item in entry["items"]:
            d = parse_date(item.get("publicationDate",""))
            url = item.get("canonicalUrl","") or "https://www.rijksoverheid.nl"
            # Make sure URL is absolute
            if url and not url.startswith("http"):
                url = "https://www.rijksoverheid.nl" + url
            feed.append({
                "title":       item.get("title",""),
                "date":        item.get("publicationDate",""),
                "date_ts":     d.isoformat() if d else "",
                "date_display": d.strftime("%-d %b %Y") if d else "–",
                "ministry":    meta["name"],
                "minister":    meta["minister"],
                "party":       meta["party"],
                "party_color": meta["party_color"],
                "url":         url,
                "intro":       item.get("introduction","")[:250],
                "source":      item.get("source","api"),
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

    # 1. Get real ministry slugs
    print("\n── Step 1: Fetching ministry list from API…")
    api_ministries = fetch_ministry_list()

    # 2. Match to Jetten ministers, skip unmatched
    matched = []
    for m in api_ministries:
        info = match_minister(m["name"], m["slug"])
        if info and m["slug"]:
            matched.append({**m, **info})

    # Also add any hardcoded ones we might have missed
    print(f"  Matched {len(matched)} ministries to Jetten cabinet")
    for m in matched:
        print(f"    {m['slug'][:55]:55s} → {m['minister']} ({m['party']})")

    if len(matched) == 0:
        print("  [!] No matches found — using fallback slugs")
        # Fallback: use known stable slugs
        matched = [
            {"slug":"ministerie-van-algemene-zaken","name":"Algemene Zaken","minister":"Rob Jetten","role":"Minister-President","party":"D66","party_color":"#007a2b"},
            {"slug":"ministerie-van-buitenlandse-zaken","name":"Buitenlandse Zaken","minister":"Tom Berendsen","role":"Minister","party":"CDA","party_color":"#005f49"},
            {"slug":"ministerie-van-justitie-en-veiligheid","name":"Justitie & Veiligheid","minister":"David van Weel","role":"Minister","party":"VVD","party_color":"#c45e00"},
            {"slug":"ministerie-van-binnenlandse-zaken-en-koninkrijksrelaties","name":"Binnenlandse Zaken","minister":"Pieter Heerma","role":"Minister","party":"CDA","party_color":"#005f49"},
            {"slug":"ministerie-van-volkshuisvesting-en-ruimtelijke-ordening","name":"Volkshuisvesting & RO","minister":"Elanor Boekholt-O'Sullivan","role":"Minister","party":"D66","party_color":"#007a2b"},
            {"slug":"ministerie-van-onderwijs-cultuur-en-wetenschap","name":"Onderwijs, Cultuur & Wetenschap","minister":"Rianne Letschert","role":"Minister","party":"D66","party_color":"#007a2b"},
            {"slug":"ministerie-van-financien","name":"Financiën","minister":"Eelco Heinen","role":"Minister","party":"VVD","party_color":"#c45e00"},
            {"slug":"ministerie-van-defensie","name":"Defensie","minister":"Dilan Yeşilgöz","role":"Minister","party":"VVD","party_color":"#c45e00"},
            {"slug":"ministerie-van-infrastructuur-en-waterstaat","name":"Infrastructuur & Waterstaat","minister":"Vincent Karremans","role":"Minister","party":"VVD","party_color":"#c45e00"},
            {"slug":"ministerie-van-economische-zaken","name":"Economische Zaken & Klimaat","minister":"Heleen Herbert","role":"Minister","party":"CDA","party_color":"#005f49"},
            {"slug":"ministerie-van-landbouw-natuur-en-voedselkwaliteit","name":"Landbouw, Natuur & Voedselkwaliteit","minister":"Jaimi van Essen","role":"Minister","party":"D66","party_color":"#007a2b"},
            {"slug":"ministerie-van-sociale-zaken-en-werkgelegenheid","name":"Sociale Zaken & Werkgelegenheid","minister":"Hans Vijlbrief","role":"Minister","party":"D66","party_color":"#007a2b"},
            {"slug":"ministerie-van-volksgezondheid-welzijn-en-sport","name":"Volksgezondheid, Welzijn & Sport","minister":"Sophie Hermans","role":"Minister","party":"VVD","party_color":"#c45e00"},
        ]

    # 3. Fetch news
    print("\n── Step 2: Fetching news per ministry…")
    all_news = {}
    for m in matched:
        slug = m["slug"]
        print(f"  {m['name'][:50]:50s} ", end="", flush=True)
        api  = fetch_api_news(slug, limit=30)
        rss  = fetch_rss(slug)
        combined = merge(api, rss)
        all_news[slug] = {"meta": m, "items": combined}
        print(f"API:{len(api):3d}  RSS:{len(rss):3d}  total:{len(combined):3d}")
        time.sleep(0.4)

    # 4. Build output
    activity = activity_stats(all_news)
    topics   = trending_topics(all_news, top_n=60)
    feed     = build_feed(all_news, limit=120)
    parties  = party_breakdown(activity)

    total_items = sum(len(e["items"]) for e in all_news.values())
    print(f"\n  Total items fetched: {total_items}")
    print(f"  Feed items (after sort+limit): {len(feed)}")

    payload = {
        "generated_at": datetime.now().isoformat(),
        "activity":     activity,
        "topics":       topics,
        "feed":         feed,
        "parties":      parties,
    }

    out_path = out_dir / "dashboard.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n✅  Saved → {out_path}")
    print(f"   {len(activity)} ministeries | {len(topics)} topics | {len(feed)} persberichten")


if __name__ == "__main__":
    main()
