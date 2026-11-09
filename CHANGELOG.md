# Ændringer

## 0.4.0 – 2026-11-09

- Offentlig ladning (fx DC-lynladning på en tur): handlingerne `clever_energitillaeg.tilfoej_offentlig_ladning` (kWh, tidspunkt for stop, note) og `clever_energitillaeg.fjern_offentlig_ladning`. Ladningerne gemmes og overlever genstart.
- Nye sensorer: `offentlig_ladning` og `offentlig_ladning_sidste_maaned` (kWh, med listen `ladninger`), `foreloebigt_energitillaeg_offentlig_ladning` og `energitillaeg_sidste_maaned_offentlig_ladning` (kr.).
- Nye sensorer `foreloebigt_energitillaeg_i_alt` og `energitillaeg_sidste_maaned_i_alt`: sats × (alle valgte energisensorer + offentlig ladning), som Clever opkræver det.

## 0.3.0 – 2026-11-07

- Dag for dag: attributten `dage` (dagsgennemsnit, måned-til-dato og sats efter hver dag) til grafer som Clevers.
- Ny sensor `sats_sidste_maaned` (beregnet for hele sidste måned) og `energitillaeg_sidste_maaned_<sensor>` (ud fra utility meterens `last_period`).
- Sidste og indeværende måned hentes i ét kald til Energinet.
- Sats og gennemsnit har `state_class: measurement`, så HA gemmer langtidsstatistik.
- README: ApexCharts-eksempel.

## 0.2.0 – 2026-11-06

- Flere energisensorer: hver valgt sensor får sit eget foreløbige energitillæg (`sensor.clever_energitillaeg_foreloebigt_energitillaeg_<sensor>`), opkaldt efter sensoren. Fravalgte sensorers tillæg fjernes.
- Opsætningen fra 0.1.0 (én energisensor) migreres automatisk; dens tillægsentitet bevares med historik.
- Helt på dansk: entitets-ID'er (`sensor.clever_energitillaeg_foreloebig_sats` osv.), navne uanset HA-sprog, attributter, status (ok/fejl/ingen_data), enheder kr./kWh og kr., README.
- Eksisterende 0.1.0-entiteter med de automatiske engelske ID'er omdøbes automatisk; historikken bevares. Selvvalgte ID'er røres ikke.
- Tillægssensoren har ikke længere device_class monetary (enheden er nu kr.).

## 0.1.0 – 2026-11-06

- First version: preliminary rate, national/DK1/DK2 averages, last fetch and optional preliminary surcharge.
- Verified against Clever's published rates 2025-10 to 2026-10 (13/13 equal).
