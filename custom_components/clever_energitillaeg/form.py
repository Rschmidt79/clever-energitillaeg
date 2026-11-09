"""Dashboard form for public charging: date, kWh, price, note and two buttons.

The form values live in memory only; a charge is stored when "Tilføj DC-ladning" is pressed.
"""

from __future__ import annotations

from datetime import date

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import Entity
from homeassistant.util import dt as dt_util

from .const import DK_TZ, DOMAIN
from .coordinator import CleverCoordinator
from .entity import CleverEntity


class FormEntity(CleverEntity, Entity):
    _attr_should_poll = False

    def __init__(self, coordinator: CleverCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._form = coordinator.public.form

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.public.async_add_form_listener(self._form_changed))

    def _form_changed(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return True  # independent of Energinet fetches


def today() -> date:
    return dt_util.now().astimezone(DK_TZ).date()


async def async_submit(coordinator: CleverCoordinator) -> None:
    """Add the typed charge and clear kWh, price and note (the date is kept)."""
    from . import async_add_charge  # avoid an import cycle

    form = coordinator.public.form
    if form.kwh <= 0:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="form_no_kwh")
    # 0 kr. means "no receipt" when an alternative price is set (a Clever customer); otherwise
    # it is a free charge.
    pris = None if form.pris == 0 and coordinator.public_price is not None else form.pris
    await async_add_charge(coordinator, form.kwh, pris, form.dato, form.note or None)
    form.kwh, form.pris, form.note = 0.0, 0.0, ""
    coordinator.public.async_form_changed()


async def async_undo(coordinator: CleverCoordinator) -> None:
    if await coordinator.public.async_remove(None) is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_found")
