"""Constants for Clever energitillæg."""

from __future__ import annotations

from zoneinfo import ZoneInfo

DOMAIN = "clever_energitillaeg"
NAME = "Clever energitillæg"

CONF_ENERGY_ENTITY = "energy_entity"
CONF_THRESHOLD = "threshold"
CONF_VAT = "vat_percent"

DEFAULT_THRESHOLD = 0.89  # kr./kWh incl. VAT, Clever terms § 3.1.2
DEFAULT_VAT = 25.0

API_URL = "https://api.energidataservice.dk/dataset/DayAheadPrices"
PRICE_AREAS = ("DK1", "DK2")
# Energinet interprets start/end in Danish time and publishes TimeDK; months are Danish months.
DK_TZ = ZoneInfo("Europe/Copenhagen")

FETCH_TIME = (14, 30)  # prices for tomorrow are published around 13:00 CET
RETRY_TIME = (18, 30)  # only if today's fetch failed
MONTH_START_TIME = (0, 5)  # only on the 1st
RATE_LIMIT_DELAY = 75  # seconds; Energinet answers 429 to more than about one call per minute
REQUEST_TIMEOUT = 60

ATTRIBUTION = "Data: Energinet Energi Data Service (DayAheadPrices)"
