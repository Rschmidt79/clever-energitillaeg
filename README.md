# Clever energitillæg (foreløbigt) for Home Assistant

> **Uofficiel.** Integrationen er ikke lavet af, godkendt af eller tilknyttet Clever A/S eller Energinet. Den beregner et **foreløbigt** skøn. Den endelige sats fastsætter Clever, når måneden er gået.

## Hvad den gør

Clever One-abonnementer med ladeboks har et variabelt energitillæg (vilkår § 3.1.2). Tillægget er den del af månedens gennemsnitlige spotpris inkl. moms for hele Danmark, der ligger over 0,89 kr./kWh, ganget med månedens kWh.

Integrationen henter Energinets åbne **DayAheadPrices** (15-minutterspriser, DKK/MWh) for indeværende måned i både DK1 og DK2. Ved hver hentning regner den hele måneden igen fra kildedata:

```
gennemsnit pr. zone = middel af alle 15-min-priser i de dage, der indgår
landsgennemsnit     = (DK1 + DK2) / 2 × 1,25 / 1000        (kr./kWh inkl. moms)
foreløbig sats      = max(0, landsgennemsnit − 0,89), afrundet til 2 decimaler
foreløbigt tillæg   = sats × månedens kWh (én pr. valgt energisensor)
```

Metoden giver **præcis Clevers offentliggjorte satser** for alle 13 afsluttede måneder fra oktober 2025 til oktober 2026. Det testes automatisk. Clever nævner ikke DK1/DK2-vægtningen i vilkårene. 50/50 er den eneste af de afprøvede metoder, der passer for alle måneder.

### Sensorer

| Entitet | Enhed | Bemærkning |
|---|---|---|
| `sensor.clever_energitillaeg_foreloebig_sats` | kr./kWh | Attributter: `maaned`, `status` (ok/fejl/ingen_data), `dage_indgaar`, `manglende_dage`, `afventer_dage`, `hentet`, `sats_raa`, `dage` (dag for dag), `note` … |
| `sensor.clever_energitillaeg_landsgennemsnit` | kr./kWh | Inkl. moms |
| `sensor.clever_energitillaeg_gennemsnit_dk1` / `_dk2` | kr./kWh | Inkl. moms |
| `sensor.clever_energitillaeg_seneste_hentning` | tidspunkt | Diagnostik |
| `sensor.clever_energitillaeg_foreloebigt_energitillaeg_<sensor>` | kr. | Én pr. valgt energisensor, opkaldt efter den (fx to biler eller to ladebokse) |
| `sensor.clever_energitillaeg_sats_sidste_maaned` | kr./kWh | Sidste måneds sats, beregnet ud fra hele måneden; med `landsgennemsnit`, `dage` m.m. |
| `sensor.clever_energitillaeg_energitillaeg_sidste_maaned_<sensor>` | kr. | Sidste måneds sats × energisensorens `last_period` (kræver en utility meter) |
| `sensor.clever_energitillaeg_offentlig_ladning` / `_sidste_maaned` | kWh | Offentlig ladning, du har tilføjet (se nedenfor). Attribut `ladninger` |
| `sensor.clever_energitillaeg_foreloebigt_energitillaeg_offentlig_ladning` | kr. | Sats × offentlig ladning denne måned |
| `sensor.clever_energitillaeg_energitillaeg_sidste_maaned_offentlig_ladning` | kr. | Sidste måneds sats × offentlig ladning sidste måned |
| `sensor.clever_energitillaeg_foreloebigt_energitillaeg_i_alt` | kr. | Sats × (alle energisensorer + offentlig ladning). Attribut `energi_kwh_dele` |
| `sensor.clever_energitillaeg_energitillaeg_sidste_maaned_i_alt` | kr. | Det samme for sidste måned |

Sats og gennemsnit gemmes som langtidsstatistik, så HA's historik og statistikgrafer kan vise dem måned efter måned.

### Offentlig ladning (DC/lynladning)

Clever medregner dit månedlige kWh-forbrug "både hjemme og ude på netværket" i energitillægget ([clever.dk/energitillaeg](https://clever.dk/satser-tillaeg-og-priser/energitillaeg/)). Med Clever One betaler du ikke ekstra for at lade på Clevers lynladere, men kWh tæller med i tillægget med **samme sats** som hjemme. Opladning hos andre operatører (roaming) betales med operatørens pris og er ikke med her.

Ladning ude måles ikke af din ladeboks, så du tilføjer den selv:

```yaml
action: clever_energitillaeg.tilfoej_offentlig_ladning
data:
  kwh: 120
  tidspunkt: "2026-11-08 17:30:00"   # valgfri: hvornår opladningen stoppede (standard: nu)
  note: Tur til København            # valgfri
```

Det kan også gøres under *Udviklerværktøjer → Handlinger*. Clever henfører en opladning til den måned, hvor den **stopper**, så det er tidspunktet, der afgør måneden. `clever_energitillaeg.fjern_offentlig_ladning` fjerner den senest tilføjede ladning eller en bestemt med `id` (se attributten `ladninger`). Ladningerne gemmes i Home Assistant og overlever genstart. De seneste 13 måneder gemmes.

`..._i_alt` er sats × (månedens kWh fra alle valgte energisensorer + offentlig ladning), som Clever regner det. Den er `unavailable`, hvis en af energisensorerne ikke kan bruges, så en del aldrig tæller som 0.

### Dag for dag

Attributten `dage` indeholder én post pr. dag, der indgår:

```yaml
- dato: "2026-11-01"
  dagsgennemsnit: 2.3912      # dagens spotpris inkl. moms, DK1/DK2 50/50
  maanedsgennemsnit: 2.3912   # måned-til-dato efter dagen
  sats: 1.50                  # energitillægssats efter dagen
```

Med [ApexCharts Card](https://github.com/RomRider/apexcharts-card) (HACS → Frontend) kan du tegne den samme graf som på Clevers side: søjler for hver dag, linjer for månedens gennemsnit og satsen og en vandret linje ved 0,89. Headeren viser den aktuelle sats og månedens gennemsnit, og den nyeste værdi står også ved linjerne. Kortet til sidste måned bruger `sensor.clever_energitillaeg_sats_sidste_maaned` og `offset: -31d`.

```yaml
- type: custom:apexcharts-card
  header:
    show: true
    title: Clever energitillæg · denne måned
    show_states: true
    colorize_states: true
  graph_span: 31d
  span:
    start: month
  update_interval: 1h
  yaxis:
  - min: 0
    decimals: 2
  all_series_config:
    show:
      legend_value: false
  apex_config:
    legend:
      show: true
    dataLabels:
      enabled: true
      enabledOnSeries:
      - 1
      - 2
      formatter: 'EVAL:function(v, o) { const d = o.w.config.series[o.seriesIndex].data; return o.dataPointIndex === d.length - 1 ? v.toFixed(2).replace(''.'', '','') + '' kr'' : ''''; }'
    tooltip:
      shared: true
      x:
        format: d. MMM
    xaxis:
      labels:
        datetimeUTC: false
        format: d
  series:
  - entity: sensor.clever_energitillaeg_foreloebig_sats
    name: Gns. spotpris inkl. moms (dag)
    type: column
    color: '#7dd3dc'
    data_generator: return (entity.attributes.dage || []).map(d => [new Date(d.dato + "T12:00:00").getTime(), d.dagsgennemsnit]);
    show:
      in_header: false
  - name: Gns. spotpris måned
    type: line
    color: '#c3c24a'
    stroke_width: 2
    unit: kr./kWh
    float_precision: 2
    show:
      in_header: true
    entity: sensor.clever_energitillaeg_landsgennemsnit
    data_generator: return (hass.states['sensor.clever_energitillaeg_foreloebig_sats'].attributes.dage || []).map(d => [new Date(d.dato + "T12:00:00").getTime(), d.maanedsgennemsnit]);
  - entity: sensor.clever_energitillaeg_foreloebig_sats
    name: Energitillægssats
    type: line
    color: '#a033b0'
    stroke_width: 2
    data_generator: return (entity.attributes.dage || []).map(d => [new Date(d.dato + "T12:00:00").getTime(), d.sats]);
    unit: kr./kWh
    float_precision: 2
    show:
      in_header: true
  - entity: sensor.clever_energitillaeg_foreloebig_sats
    name: Grundsats
    type: line
    color: '#9e9e9e'
    stroke_width: 1
    data_generator: 'const m = (entity.attributes.maaned || "").split("-").map(Number); if (!m[0]) return [];

      const n = new Date(m[0], m[1], 0).getDate(); const g = entity.attributes.grundsats || 0.89;

      return Array.from({length: n}, (_, i) => [new Date(m[0], m[1] - 1, i + 1, 12).getTime(), g]);'
    show:
      in_header: false
- type: custom:apexcharts-card
  header:
    show: true
    title: Clever energitillæg · sidste måned
    show_states: true
    colorize_states: true
  graph_span: 31d
  span:
    start: month
    offset: -31d
  update_interval: 1h
  yaxis:
  - min: 0
    decimals: 2
  all_series_config:
    show:
      legend_value: false
  apex_config:
    legend:
      show: true
    dataLabels:
      enabled: true
      enabledOnSeries:
      - 1
      - 2
      formatter: 'EVAL:function(v, o) { const d = o.w.config.series[o.seriesIndex].data; return o.dataPointIndex === d.length - 1 ? v.toFixed(2).replace(''.'', '','') + '' kr'' : ''''; }'
    tooltip:
      shared: true
      x:
        format: d. MMM
    xaxis:
      labels:
        datetimeUTC: false
        format: d
  series:
  - entity: sensor.clever_energitillaeg_sats_sidste_maaned
    name: Gns. spotpris inkl. moms (dag)
    type: column
    color: '#7dd3dc'
    data_generator: return (entity.attributes.dage || []).map(d => [new Date(d.dato + "T12:00:00").getTime(), d.dagsgennemsnit]);
    show:
      in_header: false
  - name: Gns. spotpris måned
    type: line
    color: '#c3c24a'
    stroke_width: 2
    unit: kr./kWh
    float_precision: 2
    show:
      in_header: true
    entity: sensor.clever_energitillaeg_sats_sidste_maaned
    attribute: landsgennemsnit
    data_generator: return (entity.attributes.dage || []).map(d => [new Date(d.dato + "T12:00:00").getTime(), d.maanedsgennemsnit]);
  - entity: sensor.clever_energitillaeg_sats_sidste_maaned
    name: Energitillægssats
    type: line
    color: '#a033b0'
    stroke_width: 2
    data_generator: return (entity.attributes.dage || []).map(d => [new Date(d.dato + "T12:00:00").getTime(), d.sats]);
    unit: kr./kWh
    float_precision: 2
    show:
      in_header: true
  - entity: sensor.clever_energitillaeg_sats_sidste_maaned
    name: Grundsats
    type: line
    color: '#9e9e9e'
    stroke_width: 1
    data_generator: 'const m = (entity.attributes.maaned || "").split("-").map(Number); if (!m[0]) return [];

      const n = new Date(m[0], m[1], 0).getDate(); const g = entity.attributes.grundsats || 0.89;

      return Array.from({length: n}, (_, i) => [new Date(m[0], m[1] - 1, i + 1, 12).getTime(), g]);'
    show:
      in_header: false
```

Uden ApexCharts kan du bruge et almindeligt historik- eller statistikkort med `sensor.clever_energitillaeg_foreloebig_sats` og `sensor.clever_energitillaeg_landsgennemsnit`. Det viser, hvordan satsen har udviklet sig fra dag til dag.

### Regler

- **Hentning:** kl. 14:30 hver dag. Kl. 18:30 kun hvis dagens hentning fejlede. Kl. 00:05 den 1. i måneden. Desuden ved opstart.
- **Rate limit:** ved HTTP 429 prøver integrationen igen efter 75 s.
- **Komplette dage:** en dag indgår kun, hvis både DK1 og DK2 har alle dagens kvarterer (96, eller 92/100 på dage med skift til sommer- eller vintertid). Inkomplette dage vises som `manglende_dage`. Priserne for i morgen indgår, når de er offentliggjort.
- **Manglende data er aldrig 0:**
  - Fejler en hentning, beholder integrationen sidste gode beregning for samme måned. Det gælder også efter genstart, og `status` bliver da `fejl`.
  - Findes der ingen gyldig beregning, er sensoren `unknown`.
- **Hver tillægssensor** er `unavailable`, hvis satsen ikke hører til indeværende måned, energisensoren er utilgængelig, eller energisensorens `last_reset` ikke ligger i indeværende måned.

### Installation

1. **HACS** → Integrationer → ⋮ → *Brugerdefinerede repositories* → tilføj `https://github.com/Rschmidt79/clever-energitillaeg` som *Integration*. Installér *Clever energitillæg* og genstart Home Assistant.
2. **Indstillinger → Enheder og tjenester → Tilføj integration → "Clever energitillæg".**
3. Vælg eventuelt en eller flere **månedlige energisensorer** i kWh, fx én pr. bil eller ladeboks. Hver får sit eget foreløbige energitillæg. Sensorerne skal nulstilles den 1. i måneden og have `last_reset`. Det har en utility meter:

   ```yaml
   utility_meter:
     ladeboks_denne_maaned:
       source: sensor.min_ladeboks_energi   # samlet kWh fra din lader
       cycle: monthly
   ```

   Grundsats (0,89) og moms (25 %) kan ændres under *Konfigurér*.

### Kendte afvigelser

- Clever henfører en opladning til den måned, hvor den **stopper**. En utility meter deler ved midnat.
- Clever bruger sine egne målinger (app/faktura). Integrationen bruger dine energisensorer.
- Satsen er foreløbig og ændrer sig frem til månedens udgang.
- Tillægget beregnes med den afrundede sats (2 decimaler).
- Clever kan i princippet bruge en anden kurs eller datakilde. Kun de afrundede satser er verificeret.
- Clever-vilkårene "gældende fra 30. november 2026" nævner, at aftalen overgår til Andel Energi. Formlen er uændret i den version, men tjek vilkårene, hvis de ændres.

Kilder: Clevers vilkår (clever.dk/vilkaar-clever-one-med-ladeboks), clever.dk/satser-tillaeg-og-priser/energitillaeg, Energinet: api.energidataservice.dk/meta/dataset/DayAheadPrices.

## Udvikling

```sh
pip install -r requirements_test.txt
pytest && ruff check . && ruff format --check .
```

Testene bruger gemte svar fra Energinet (`tests/fixtures/`) og kræver ikke netværk.

Licens: MIT.
