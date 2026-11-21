# Eat & More – verkkosivut (luonnos)

GitHub Pages -luonnos, joka siirretään myöhemmin yrityksen omille verkkosivuille.

- `index.html`, `ostaminen.html`, `tietosuoja.html`: sivut suomeksi
- `ucp/agent.json`: sovelluksen UCP-agenttiprofiili (Universal Commerce Protocol). Kaupat hakevat sen ennen kuin vastaavat sovelluksen hakuihin.

Kun sivut siirretään omalle verkkotunnukselle, vaihda sovelluksessa `AppInfo.siteURL`.

## Suositussignaalit

`signals/ucp_signals.json`: sovelluksen top 3 -suosittelualgoritmin signaalit (merkki, laatuarvio, testitulokset, arviot, trendit) ja painot. Sovellus hakee tiedoston jsDelivrin kautta (`AppInfo.signalsURL`) ja käyttää sitä ilman sovelluspäivitystä. Tiedosto kootaan skriptillä `tools/recommender/build_signals.py` (sovelluksen repositoriossa).
