# Geopolitisk Daily Briefing

En gratis, personlig daglig geopolitisk nyhets-briefing. Ingen API-kostnader.

## Slik fungerer det

1. **GitHub Actions** kjører `collect.py` hver morgen kl. 07:00 (Oslo-tid)
2. Scriptet henter nyheter fra RSS-feeds + GDELT
3. Artiklene scores med heuristisk impakt-score (1-10)
4. Kun de viktigste sakene (score ≥ 5.0) publiseres til `briefing.json`
5. Dashboardet (`index.html`) leser JSON-filen og viser briefingen

## Scoring-metode

| Faktor | Vekt | Beskrivelse |
|--------|------|-------------|
| Konsensus | 40% | Hvor mange kilder dekker saken |
| Track-match | 30% | Treffer den dine interesseområder |
| Goldstein-proxy | 20% | Intensitetsord (krig, krise, historisk) |
| G20-aktører | 10% | Nevner store internasjonale aktører |

## Oppsett

1. Fork dette repoet
2. Aktiver GitHub Pages (Settings → Pages → Source: main branch)
3. Aktiver GitHub Actions (Actions → "I understand my workflows")
4. Vent til neste kjøring, eller trigge manuelt via Actions-fanen

### Manuell kjøring
```
python collect.py
```

## Tilpasning

Rediger `config.json` for å:
- Legge til/fjerne RSS-kilder
- Endre dine tracks og nøkkelord
- Justere scoring-vekter
- Sette minimum score-terskel

## Stack

- **Innsamling**: Python 3 (kun stdlib — ingen pip-avhengigheter)
- **Kilder**: RSS-feeds + GDELT DOC API (begge gratis)
- **Frontend**: Vanilla HTML/CSS/JS
- **Hosting**: GitHub Pages (gratis)
- **Automatisering**: GitHub Actions (gratis for offentlige repos)

## Kostnad

**$0/mnd.** Alt er gratis.
