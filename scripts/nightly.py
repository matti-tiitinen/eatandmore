"""Eat & More -suositussignaalien yöajo (GitHub Actions).

1. Varasto ja hinnat: UCP lookup_catalog jokaisesta kaupasta (data/stock.json).
2. Trendit: Google Trends merkeittäin Suomessa ja Pohjoismaissa, 30 päivän kiinnostus suhteessa 12 kuukauteen
   (data/trends.json). Käytössä pytrends, joka on epävirallinen kirjasto: se voi lakata toimimasta, eikä Google
   tue sitä. Virallinen Google Trends API on alfavaiheessa ja vaatii hakemuksen; kun pääsy on, vaihda fetch_trends.
3. Arviot: kytkettävät lähteet (data/ratings.json). Google ei tarjoa julkista rajapintaa tuotearvioihin muille
   kuin kauppiaille, eikä Googlen hakutuloksia saa kaapia ehtojen vuoksi, joten Google-arviot ovat pois päältä.
   Käytössä: data/ratings_manual.json (toimituksen lisäämät, lähteistetyt arviot).
4. Asiantuntijat: data/expert_signals.json (toimituksen julkisista lähteistä kokoamat testit ja palkinnot, lähde-URL ja vuosi).
5. Signaalit: scripts/build_signals.py → signals/ucp_signals.json.

Lukuja ei keksitä: jos lähde ei vastaa, sen signaali jää pois ja vanha poistuu tuoreusikkunan jälkeen.
"""
import json, sys, time, datetime, subprocess, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROFILE = "https://cdn.jsdelivr.net/gh/matti-tiitinen/eatandmore@main/ucp/agent.json"
CONTEXT = {"address_country": "FI", "language": "fi", "currency": "EUR"}
GEOS = ["FI", "SE", "NO", "DK"]
# Hakusana merkille, kun merkin nimi on yleinen sana tai lyhenne.
TERMS = {"Fred": "Fred safety", "BIBS": "BIBS pacifier", "Snuz": "SnuzPod", "Cam Cam": "Cam Cam Copenhagen",
         "Konges": "Konges Sløjd", "Bibado": "Bibado bib", "Voksi": "Voksi footmuff", "Nuna": "Nuna baby",
         "Owlet": "Owlet sock", "Hauck": "Hauck baby", "Fraupow": "Fraupow", "Jollein": "Jollein"}
MIN_INTEREST = 5   # vähimmäiskiinnostus 0–100, jottei pienen hakumäärän piikki nouse trendiksi
TODAY = datetime.date.today().isoformat()


def ucp(endpoint, tool, args):
    args = dict(args, meta={"ucp-agent": {"profile": PROFILE}})
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(endpoint, body, {"Content-Type": "application/json", "Accept": "application/json",
                                                  "User-Agent": "EatAndMore-signals/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    if "error" in d:
        raise RuntimeError(d["error"].get("message"))
    res = d["result"]
    if res.get("structuredContent"):
        return res["structuredContent"]
    return json.loads(res["content"][0]["text"])


def fetch_stock(catalog):
    out = {}
    shops = {s["id"]: s for s in catalog["shops"]}
    for sid, shop in shops.items():
        items = [p for p in catalog["products"] if p["shop"] == sid]
        for i in range(0, len(items), 10):
            batch = items[i:i + 10]
            try:
                r = ucp(shop["endpoint"], "lookup_catalog", {"catalog": {"ids": [p["variant"] for p in batch], "context": CONTEXT}})
            except Exception as e:
                print(f"stock: {sid} ei vastannut ({e})")
                continue
            found = {v["id"]: v for prod in r.get("products", []) for v in prod.get("variants", [])}
            for p in batch:
                v = found.get(p["variant"])
                if not v:
                    continue
                price = v.get("price") or {}
                out[p["id"]] = {"available": bool((v.get("availability") or {}).get("available", True)),
                                "price": price.get("amount", 0) / 100 if price.get("currency") == "EUR" else None, "date": TODAY}
            time.sleep(0.3)
    print(f"stock: {len(out)} tuotetta päivitetty")
    return out


def fetch_trends(brands):
    """Google Trends merkeittäin: viimeisten 4 viikon keskiarvo suhteessa 12 kuukauden keskiarvoon."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("trends: pytrends puuttuu, ohitetaan")
        return {}
    py = TrendReq(hl="fi-FI", tz=-120, timeout=(10, 30))
    terms = {TERMS.get(b, b): b for b in brands}
    growth = {b: [] for b in brands}
    failures = 0
    for geo in GEOS:
        names = list(terms)
        for i in range(0, len(names), 5):
            kw = names[i:i + 5]
            try:
                py.build_payload(kw, timeframe="today 12-m", geo=geo)
                df = py.interest_over_time()
            except Exception as e:
                print(f"trends: {geo} {kw} epäonnistui ({str(e)[:80]})")
                failures += 1
                if failures >= 4:
                    print("trends: Google ei vastaa, lopetetaan tältä yöltä")
                    break
                time.sleep(15)
                continue
            for term in kw:
                if df is None or df.empty or term not in df or df[term].mean() < MIN_INTEREST:
                    continue
                growth[terms[term]].append(float(df[term].tail(4).mean() / df[term].mean()))
            time.sleep(4)
    out = {}
    for b, g in growth.items():
        if not g:
            continue
        ratio = sum(g) / len(g)
        # Kasvu 1,0 (tasainen) → 0,35; 1,5 → 0,85; 1,65+ → 1.
        out[b] = {"score": round(max(0.0, min(1.0, 0.35 + (ratio - 1.0))), 3), "growth": round(ratio, 3),
                  "source": f"Google Trends ({', '.join(GEOS)}), 30 pv vs 12 kk", "date": TODAY}
    print(f"trends: {len(out)} merkkiä")
    if not out:
        return {}
    # Yhdistetään aiempaan: merkki, jota ei saatu tänä yönä, säilyy kunnes sen tuoreusikkuna (45 pv) umpeutuu.
    old = DATA / "trends.json"
    merged = (json.loads(old.read_text()).get("brands") if old.exists() else None) or {}
    merged.update(out)
    return {"brands": merged}


def fetch_ratings():
    """Kytkettävät arviolähteet. Google-arviot pois päältä (ei julkista, ehtojen mukaista rajapintaa)."""
    manual = DATA / "ratings_manual.json"
    data = json.loads(manual.read_text()) if manual.exists() else {}
    out = {k: v for k, v in data.items() if not k.startswith("_") and {"value", "count", "source", "date"} <= set(v)}
    print(f"ratings: {len(out)} lähteistettyä arviota (Google-arviot pois päältä)")
    return out


def main():
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_signals
    catalog = json.loads((DATA / "ucp_catalog.json").read_text())
    stock = fetch_stock(catalog)
    shops = {s["id"]: s for s in catalog["shops"]}
    brands = sorted({build_signals.brand_of(p, shops) for p in catalog["products"]})
    trends = fetch_trends(brands)
    ratings = fetch_ratings()
    for name, d in [("stock", stock), ("trends", trends), ("ratings", ratings)]:
        if d:
            (DATA / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
    args = [sys.executable, str(ROOT / "scripts" / "build_signals.py"), str(DATA / "ucp_catalog.json"), str(ROOT / "signals" / "ucp_signals.json")]
    for name in ["trends", "ratings", "stock"]:
        if (DATA / f"{name}.json").exists():
            args += [f"--{name}", str(DATA / f"{name}.json")]
    if (DATA / "expert_signals.json").exists():
        args += ["--experts", str(DATA / "expert_signals.json")]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    main()
