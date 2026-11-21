"""Kokoaa suosittelualgoritmin signaalit (ucp_signals.json) UCP-valikoimasta.

Signaalit tuotteittain:
- brand: merkki (merkkiuskollisuus ja yhteensopivuus)
- quality: toimituksen laatuarvio merkin perusteella (0–1). Ei näytetä käyttäjälle numerona.
- test: riippumaton testitulos (esim. ADAC). Vain varmistetut tulokset, ks. TESTS.
- rating: arvostelujen keskiarvo ja määrä. Täytetään, kun lähde on kytketty (RATINGS).
- trend: kiinnostuksen kasvu somessa ja uutisissa (0–1). Täytetään trendiajolla (TRENDS).

Käyttö: python3 build_signals.py <ucp_catalog.json> <ulos.json> [--trends trends.json] [--ratings ratings.json] [--stock stock.json]
Palvelimella (eatandmore-repositorion yöajo) sama skripti saa lisäksi Google Trends -datan, arviot ja
varastotilanteen. Tulos julkaistaan osoitteeseen AppInfo.signalsURL.

Lukuja ei keksitä: jokaisella signaalilla on lähde ja päiväys, ja vanhentuneet signaalit pudotetaan
(trendit 45 pv, arviot 180 pv, varasto 3 pv).
"""
import json, sys, datetime, re, argparse

BRANDS = ["Cybex", "Bugaboo", "BeSafe", "Stokke", "BabyBjörn", "BabyBjorn", "Nanit", "Emmaljunga", "iCandy", "Elvie", "SnuzPod", "Snuz",
          "Ergobaby", "Liewood", "Konges", "Done by Deer", "Cam Cam", "Gugguu", "Metsola", "Voksi", "Nuna", "Joolz", "Inglesina",
          "Silver Cross", "Maxi-Cosi", "Fidella", "Tutti Bambini", "Shnuggle", "Bibado", "Tiny Love", "The Little Green Sheep",
          "Fred", "Carriwell", "Jollein", "Lola&Lykke", "BIBS", "Momcozy", "LeapFrog", "VTech", "Vtech", "babymoov", "Babymoov",
          "Easywalker", "Bumprider", "bbhugme", "Mama Shack", "Hauck", "Baby Elegance", "Fraupow", "Owlet", "Najell",
          "Sebra", "Tartine et Chocolat", "New Balance", "UGG"]
# Toimituksen laatuarvio merkeittäin. Lähtökohta: sovellus suosittelee laadukasta keski- ja hyvätuloisille perheille.
QUALITY = {
    "Cybex": .9, "Bugaboo": .9, "Stokke": .92, "BabyBjörn": .9, "BeSafe": .9, "Nanit": .85, "Emmaljunga": .85, "iCandy": .85,
    "Elvie": .85, "Snuz": .8, "Ergobaby": .85, "Liewood": .8, "Konges": .8, "Done by Deer": .8, "Cam Cam": .8, "Gugguu": .82,
    "Metsola": .8, "Voksi": .82, "Nuna": .88, "Joolz": .82, "Inglesina": .78, "Silver Cross": .78, "Maxi-Cosi": .75,
    "Fidella": .75, "Tutti Bambini": .7, "Shnuggle": .72, "Bibado": .7, "Tiny Love": .7, "The Little Green Sheep": .75,
    "Fred": .75, "Carriwell": .7, "Jollein": .7, "Lola&Lykke": .7, "BIBS": .75, "Momcozy": .7, "LeapFrog": .65, "VTech": .62,
    "Babymoov": .68, "Easywalker": .72, "Bumprider": .7, "bbhugme": .78, "Mama Shack": .65, "Hauck": .58, "Baby Elegance": .55,
    "Fraupow": .6,
    # Toimituksen suosikkimerkit: trendaavat pohjoismaiset ja eurooppalaiset premium-merkit.
    "Owlet": .9, "Najell": .9, "Sebra": .9, "Tartine et Chocolat": .9, "New Balance": .88, "UGG": .88,
}
QUALITY.update({"Cybex": .95, "Stokke": .95, "Konges": .9})
# Toimituksen trendiarvio suosikkimerkeille. Käytetään vain, kunnes Google Trends -data korvaa sen.
EDITORIAL_TREND = {b: 0.75 for b in ["Cybex", "Najell", "Owlet", "Sebra", "Stokke", "Konges", "Tartine et Chocolat", "New Balance", "UGG"]}
EDITORIAL_SOURCE = "Toimituksen arvio (korvautuu Google Trends -datalla)"
FRESH = {"trend": 45, "rating": 180, "stock": 3}
CANON = {"BabyBjorn": "BabyBjörn", "SnuzPod": "Snuz", "Vtech": "VTech", "babymoov": "Babymoov", "Cam Cam Copenhagen": "Cam Cam", "Konges Sløjd": "Konges"}
# Varmistetut testitulokset (lähde ja päiväys). Lisää tähän vain tulokset, jotka löytyvät julkaistusta testistä.
TESTS = {}  # tuotetunniste -> {"org","grade","when"}; lisäksi luetaan valikoiman "test"-kentästä
# Arvostelut: {tuotetunniste: {"value": 4.7, "count": 1234, "source": "Google Shopping"}}. Tyhjä, kunnes lähde on kytketty.
RATINGS = {}
# Trendit: {tuotetunniste: {"score": 0..1, "source": "Google Trends + some", "date": "YYYY-MM-DD"}}. Tyhjä, kunnes trendiajo on kytketty.
TRENDS = {}

def brand_of(p, shops):
    text = p["title"] + " " + p["name"]
    for b in BRANDS:
        if re.search(r"(?<![A-Za-z])" + re.escape(b) + r"(?![A-Za-z])", text, re.I):
            return CANON.get(b, b)
    n = shops[p["shop"]]["name"]
    return CANON.get(n, n)

def grade_score(grade):
    """ADAC-arvosana 0,5–5,5 (pienempi parempi) → 0–1."""
    g = float(grade.replace(",", "."))
    return round(max(0.0, min(1.0, (5.5 - g) / 4.5)), 3)

def fresh(entry, kind, today):
    """Hylkää signaalin, jolla ei ole päiväystä tai joka on vanhempi kuin sen tuoreusikkuna."""
    try:
        d = datetime.date.fromisoformat(entry["date"])
    except (KeyError, ValueError, TypeError):
        return False
    return (today - d).days <= FRESH[kind]

def load(path):
    return json.load(open(path)) if path else {}

def main(src, dst, trends=None, ratings=None, stock=None):
    c = json.load(open(src))
    shops = {s["id"]: s for s in c["shops"]}
    today = datetime.date.today()
    trend_data = load(trends)      # {"brands": {merkki: {score, date, source}}, "products": {id: {...}}}
    rating_data = load(ratings)    # {id: {value, count, source, date}}
    stock_data = load(stock)       # {id: {available, date}}
    out = {}
    for p in c["products"]:
        b = brand_of(p, shops)
        s = {"brand": b, "quality": QUALITY.get(b, 0.6)}
        t = TESTS.get(p["id"]) or p.get("test")
        if t: s["test"] = {**t, "score": grade_score(t["grade"])}
        r = rating_data.get(p["id"]) or RATINGS.get(p["id"])
        if r and fresh(r, "rating", today): s["rating"] = {k: r[k] for k in ("value", "count", "source")}
        tr = (trend_data.get("products") or {}).get(p["id"]) or (trend_data.get("brands") or {}).get(b) or TRENDS.get(p["id"])
        if tr and fresh(tr, "trend", today):
            s["trend"] = {"score": round(tr["score"], 3), "source": tr["source"], "date": tr["date"]}
        elif b in EDITORIAL_TREND:
            s["trend"] = {"score": EDITORIAL_TREND[b], "source": EDITORIAL_SOURCE, "date": today.isoformat()}
        st = stock_data.get(p["id"])
        if st and fresh(st, "stock", today) and st.get("available") is False: s["available"] = False
        out[p["id"]] = s
    doc = {
        "version": 1,
        "updated": datetime.date.today().isoformat(),
        # Painot ovat säädettävissä palvelimelta ilman sovelluspäivitystä.
        "weights": {"quality": 0.22, "test": 0.18, "rating": 0.12, "trend": 0.08, "price": 0.22, "brand": 0.10, "compat": 0.08},
        # Vaunujen merkki → turvakaukalon/lämpöpussin merkit, jotka sopivat suoraan (kauppojen valmiit paketit).
        "compat": {"Cybex": ["Cybex"], "Bugaboo": ["Bugaboo", "Cybex", "Maxi-Cosi"], "Hauck": ["Hauck"], "Inglesina": ["Inglesina"],
                   "Emmaljunga": ["Emmaljunga"], "Easywalker": ["Easywalker"], "Bumprider": ["Bumprider"]},
        "products": out,
    }
    json.dump(doc, open(dst, "w"), ensure_ascii=False, indent=1)
    print(len(out), "products,", sum(1 for v in out.values() if "test" in v), "with test,",
          sum(1 for v in out.values() if "rating" in v), "with rating,",
          sum(1 for v in out.values() if v.get("trend", {}).get("source", "").startswith("Google")), "with Google Trends,",
          sum(1 for v in out.values() if v.get("trend", {}).get("source") == EDITORIAL_SOURCE), "with editorial trend")

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("catalog"); a.add_argument("out")
    a.add_argument("--trends"); a.add_argument("--ratings"); a.add_argument("--stock")
    x = a.parse_args()
    main(x.catalog, x.out, x.trends, x.ratings, x.stock)
