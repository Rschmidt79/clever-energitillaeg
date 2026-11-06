# Clever energitillæg (foreløbigt) for Home Assistant

> **Uofficiel.** Integrationen er ikke lavet af, godkendt af eller tilknyttet Clever A/S eller Energinet. Den beregner et **foreløbigt** skøn. Den endelige sats fastsætter Clever, når måneden er gået.

*English below.*

## Hvad den gør

Clever One-abonnementer med ladeboks har et variabelt energitillæg (vilkår § 3.1.2). Tillægget er den del af månedens gennemsnitlige spotpris inkl. moms for hele Danmark, der ligger over 0,89 kr./kWh, ganget med månedens kWh.

Integrationen henter Energinets åbne **DayAheadPrices** (15-minutterspriser, DKK/MWh) for indeværende måned i både DK1 og DK2. Ved hver hentning regner den hele måneden igen fra kildedata:

```
gennemsnit pr. zone = middel af alle 15-min-priser i de dage, der indgår
landsgennemsnit     = (DK1 + DK2) / 2 × 1,25 / 1000        (kr./kWh inkl. moms)
foreløbig sats      = max(0, landsgennemsnit − 0,89), afrundet til 2 decimaler
foreløbigt tillæg   = sats × månedens kWh (valgfri energisensor)
```

Metoden giver **præcis Clevers offentliggjorte satser** for alle 13 afsluttede måneder fra oktober 2025 til oktober 2026. Det testes automatisk. Clever nævner ikke DK1/DK2-vægtningen i vilkårene. 50/50 er den eneste af de afprøvede metoder, der passer for alle måneder.

### Sensorer

| Sensor | Enhed | Bemærkning |
|---|---|---|
| Foreløbig sats | DKK/kWh | Attributter: `included_days`, `missing_days`, `pending_days`, `fetched`, `status`, `raw_rate`, `note` … |
| Landsgennemsnit | DKK/kWh | Inkl. moms |
| Gennemsnit DK1 / DK2 | DKK/kWh | Inkl. moms |
| Seneste hentning | tidspunkt | Diagnostik |
| Foreløbigt energitillæg | DKK | Kun hvis du har valgt en energisensor |

### Regler

- **Hentning:** kl. 14:30 hver dag. Kl. 18:30 kun hvis dagens hentning fejlede. Kl. 00:05 den 1. i måneden. Desuden ved opstart.
- **Rate limit:** ved HTTP 429 prøver integrationen igen efter 75 s.
- **Komplette dage:** en dag indgår kun, hvis både DK1 og DK2 har alle dagens kvarterer (96, eller 92/100 på dage med skift til sommer- eller vintertid). Inkomplette dage vises som `missing_days`. Priserne for i morgen indgår, når de er offentliggjort.
- **Manglende data er aldrig 0:**
  - Fejler en hentning, beholder integrationen sidste gode beregning for samme måned. Det gælder også efter genstart, og `status` bliver da `error`.
  - Findes der ingen gyldig beregning, er sensoren `unknown`.
- **Tillægssensoren** er `unavailable`, hvis satsen ikke hører til indeværende måned, energisensoren er utilgængelig, eller energisensorens `last_reset` ikke ligger i indeværende måned.

### Installation

1. **HACS** → Integrationer → ⋮ → *Brugerdefinerede repositories* → tilføj `https://github.com/Rschmidt79/clever-energitillaeg` som *Integration*. Installér *Clever energitillæg* og genstart Home Assistant.
2. **Indstillinger → Enheder og tjenester → Tilføj integration → "Clever energitillæg".**
3. Vælg eventuelt en **månedlig energisensor** i kWh for din ladeboks. Den skal nulstilles den 1. i måneden og have `last_reset`. Det har en utility meter:

   ```yaml
   utility_meter:
     ladeboks_denne_maaned:
       source: sensor.min_ladeboks_energi   # samlet kWh fra din lader
       cycle: monthly
   ```

   Grundsats (0,89) og moms (25 %) kan ændres under *Konfigurér*.

### Kendte afvigelser

- Clever henfører en opladning til den måned, hvor den **stopper**. En utility meter deler ved midnat.
- Clever bruger sine egne målinger (app/faktura). Integrationen bruger din energisensor.
- Satsen er foreløbig og ændrer sig frem til månedens udgang.
- Tillægget beregnes med den afrundede sats (2 decimaler).
- Clever kan i princippet bruge en anden kurs eller datakilde. Kun de afrundede satser er verificeret.
- Clever-vilkårene "gældende fra 30. november 2026" nævner, at aftalen overgår til Andel Energi. Formlen er uændret i den version, men tjek vilkårene, hvis de ændres.

Kilder: Clevers vilkår (clever.dk/vilkaar-clever-one-med-ladeboks), clever.dk/satser-tillaeg-og-priser/energitillaeg, Energinet: api.energidataservice.dk/meta/dataset/DayAheadPrices.

---

## English

> **Unofficial.** Not made, endorsed or affiliated with Clever A/S or Energinet. It is a **preliminary** estimate. Clever sets the final rate after the month ends.

The integration fetches Energinet's open **DayAheadPrices** (15-minute, DKK/MWh) for DK1 and DK2 for the current month once a day. It recalculates the whole month from source data every time:

- month-to-date average per area
- 50/50 national average incl. 25 % VAT
- **rate = max(0, average − 0.89 DKK/kWh)**

This reproduces Clever's published rates exactly for all 13 completed months from 2025-10 to 2026-10, and the tests check that.

**Entities:**
- Preliminary rate (DKK/kWh, with included/missing days, fetch time and status as attributes)
- National average
- Average DK1 and DK2
- Last fetch (diagnostic)
- Preliminary surcharge (DKK), when you pick a monthly energy sensor such as a `utility_meter` with `cycle: monthly`

**Missing data is never 0.** A day counts only when both areas have every quarter-hour. On a failed fetch the integration keeps the last good value for the same month, otherwise the rate is `unknown`.

Install via HACS as a custom repository (category *Integration*), restart, then add *Clever energitillæg* under Settings → Devices & services. Threshold and VAT can be changed in the options.

Known differences: Clever attributes a charging session to the month it ends in and uses its own metering.

## Development

```sh
pip install -r requirements_test.txt
pytest && ruff check . && ruff format --check .
```

Tests use saved Energinet responses (`tests/fixtures/`) and need no network.

License: MIT.
