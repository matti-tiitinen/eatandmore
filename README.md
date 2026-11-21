# Eat & More – verkkosivut (luonnos)

GitHub Pages -luonnos, joka siirretään myöhemmin yrityksen omille verkkosivuille.

- `index.html`, `ostaminen.html`, `tietosuoja.html`: sivut suomeksi
- `ucp/agent.json`: sovelluksen UCP-agenttiprofiili (Universal Commerce Protocol). Kaupat hakevat sen ennen kuin vastaavat sovelluksen hakuihin.

Kun sivut siirretään omalle verkkotunnukselle, vaihda sovelluksessa `AppInfo.siteURL`.

## Suositussignaalit

`signals/ucp_signals.json`: sovelluksen top 3 -suosittelualgoritmin signaalit (merkki, laatuarvio, testitulokset, arviot, trendit) ja painot. Sovellus hakee tiedoston jsDelivrin kautta (`AppInfo.signalsURL`) ja käyttää sitä ilman sovelluspäivitystä. Tiedosto kootaan skriptillä `tools/recommender/build_signals.py` (sovelluksen repositoriossa).

## Yöajo (GitHub Actions)

`.github/workflows/signals.yml` ajaa joka yö (noin klo 3 Suomen aikaa) skriptin `scripts/nightly.py`:
1. UCP: hinnat ja saatavuus kaikista kaupoista (`data/stock.json`).
2. Google Trends merkeittäin (FI, SE, NO, DK; 30 pv vs 12 kk) → `data/trends.json`. Käytössä on epävirallinen
   pytrends-kirjasto: se voi lakata toimimasta, eikä Google tue sitä. Virallinen Google Trends API on alfavaiheessa ja
   vaatii hakemuksen; kun pääsy on, vaihda `fetch_trends`.
3. Arviot: `data/ratings_manual.json` (lähteistetyt). Google-arviot ovat pois päältä, koska Google ei tarjoa julkista
   rajapintaa tuotearvioihin muille kuin kauppiaille, eikä hakutuloksia saa kaapia.
4. `scripts/build_signals.py` → `signals/ucp_signals.json`, ja muutokset commitoidaan päivätyllä viestillä.

Valikoima: kopioi sovelluksen `ViikonRuuat/Resources/ucp_catalog.json` tiedostoon `data/ucp_catalog.json`, kun valikoima muuttuu.
