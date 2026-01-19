from __future__ import annotations

import asyncio
import voluptuous as vol

from logging import getLogger

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import async_get
from homeassistant.exceptions import ServiceValidationError
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from .const import *
from .coordinator import Coordinator
from .pysolarman.umodbus.functions import FUNCTION_CODE

_LOGGER = getLogger(__name__)

HEADER_SCHEMA = {
    vol.Required(SERVICES_PARAM_DEVICE): vol.All(vol.Coerce(str)),
    vol.Required(SERVICES_PARAM_ADDRESS): vol.All(vol.Coerce(int), vol.Range(min = 0, max = 65535))
}

DEPRECATION_HEADER_SCHEMA = {
    vol.Required(SERVICES_PARAM_DEVICE): vol.All(vol.Coerce(str)),
    vol.Required(SERVICES_PARAM_REGISTER): vol.All(vol.Coerce(int), vol.Range(min = 0, max = 65535))
}

COUNT_SCHEMA = {vol.Required(SERVICES_PARAM_COUNT): vol.All(vol.Coerce(int), vol.Range(min = 0, max = 125))}
VALUE_SCHEMA = {vol.Required(SERVICES_PARAM_VALUE): vol.All(vol.Coerce(int), vol.Range(min = 0, max = 65535))}
VALUES_SCHEMA = {vol.Required(SERVICES_PARAM_VALUES): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min = 0, max = 65535))])}

def _get_device(call: ServiceCall):
    if (config_entry := call.hass.config_entries.async_get_entry(async_get(call.hass).async_get(call.data.get(SERVICES_PARAM_DEVICE)).primary_config_entry)) and config_entry.domain == DOMAIN and isinstance(config_entry.runtime_data, Coordinator):
        return config_entry.runtime_data.device
    raise ServiceValidationError("No communication interface for the device found", translation_domain = DOMAIN, translation_key = "no_interface_found")

async def _read_registers(call: ServiceCall, code: int):
    address = call.data.get(SERVICES_PARAM_ADDRESS) or call.data.get(SERVICES_PARAM_REGISTER)
    count = call.data.get(SERVICES_PARAM_COUNT) or call.data.get(SERVICES_PARAM_QUANTITY)
    try:
        if (response := await _get_device(call).execute(code, address, count = count)) is not None:
            for i in range(0, count):
                yield address + i, response[i]
    except Exception as e:
        raise ServiceValidationError(e, translation_domain = DOMAIN, translation_key = "call_failed")

async def _read_holding_registers(call: ServiceCall):
    _LOGGER.debug(f"read_holding_registers: {call}")
    return {k: v async for k, v in _read_registers(call, FUNCTION_CODE.READ_HOLDING_REGISTERS)}

async def _read_input_registers(call: ServiceCall):
    _LOGGER.debug(f"read_input_registers: {call}")
    return {k: v async for k, v in _read_registers(call, FUNCTION_CODE.READ_INPUT_REGISTERS)}

async def _write_single_register(call: ServiceCall):
    _LOGGER.debug(f"write_single_register: {call}")
    try:
        await _get_device(call).execute(FUNCTION_CODE.WRITE_SINGLE_REGISTER, call.data.get(SERVICES_PARAM_ADDRESS) or call.data.get(SERVICES_PARAM_REGISTER), data = call.data.get(SERVICES_PARAM_VALUE))
    except Exception as e:
        raise ServiceValidationError(e, translation_domain = DOMAIN, translation_key = "call_failed")

async def _battery_control(call: ServiceCall):
    """Service to control battery charging/discharging"""
    _LOGGER.debug(f"battery_control: {call}")
    
    power_watts = call.data.get("power_watts", 0)
    duration_minutes = call.data.get("duration_minutes", 5)
    
    try:
        device = _get_device(call)
        
        # Get rated power for percentage calculation
        coordinator = call.hass.config_entries.async_get_entry(
            async_get(call.hass).async_get(call.data.get(SERVICES_PARAM_DEVICE)).primary_config_entry
        ).runtime_data
        
        rated_power_data = coordinator.data.get("device_rated_power_sensor")
        rated_power = rated_power_data[0] if rated_power_data else 20000
        power_percentage = int((power_watts / rated_power) * 1000)  # Convert to 0.1% units
        power_percentage = max(-1200, min(1200, power_percentage))  # Clamp to valid range
        
        # Set registers for battery control
        await device.execute(0x10, 0x044C, data=[1])      # Remote mode enable
        await device.execute(0x10, 0x0450, data=[1])      # Battery side control  
        await device.execute(0x10, 0x0451, data=[2])      # Power priority
        await device.execute(0x10, 0x044D, data=[300])    # Watchdog 5 minutes
        await device.execute(0x10, 0x0455, data=[power_percentage])  # Battery power
        
        _LOGGER.info(f"Battery control started: {power_watts}W for {duration_minutes} minutes")
        
        # Schedule automatic stop
        async def stop_control():
            await asyncio.sleep(duration_minutes * 60)
            try:
                await device.execute(0x10, 0x044C, data=[0])  # Disable remote mode
                await device.execute(0x10, 0x0455, data=[0])  # Reset power
                _LOGGER.info("Battery control stopped automatically")
            except Exception as e:
                _LOGGER.error(f"Error stopping battery control: {e}")
        
        call.hass.async_create_task(stop_control())
        
    except Exception as e:
        raise ServiceValidationError(e, translation_domain=DOMAIN, translation_key="call_failed")

async def _write_multiple_registers(call: ServiceCall):
    _LOGGER.debug(f"write_multiple_registers: {call}")
    try:
        await _get_device(call).execute(FUNCTION_CODE.WRITE_MULTIPLE_REGISTERS, call.data.get(SERVICES_PARAM_ADDRESS) or call.data.get(SERVICES_PARAM_REGISTER), data = call.data.get(SERVICES_PARAM_VALUES) or call.data.get(SERVICES_PARAM_VALUE))
    except Exception as e:
        raise ServiceValidationError(e, translation_domain = DOMAIN, translation_key = "call_failed")

def register(hass: HomeAssistant):
    _LOGGER.debug("register")
    hass.services.async_register(DOMAIN, SERVICE_READ_HOLDING_REGISTERS, _read_holding_registers, schema = vol.Schema(HEADER_SCHEMA | COUNT_SCHEMA), supports_response = SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_READ_INPUT_REGISTERS, _read_input_registers, schema = vol.Schema(HEADER_SCHEMA | COUNT_SCHEMA), supports_response = SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_WRITE_SINGLE_REGISTER, _write_single_register, schema = vol.Schema(HEADER_SCHEMA | VALUE_SCHEMA))
    hass.services.async_register(DOMAIN, SERVICE_WRITE_MULTIPLE_REGISTERS, _write_multiple_registers, schema = vol.Schema(HEADER_SCHEMA | VALUES_SCHEMA))
    hass.services.async_register(DOMAIN, DEPRECATION_SERVICE_WRITE_SINGLE_REGISTER, _write_single_register, schema = vol.Schema(DEPRECATION_HEADER_SCHEMA | VALUE_SCHEMA))
    hass.services.async_register(DOMAIN, DEPRECATION_SERVICE_WRITE_MULTIPLE_REGISTERS, _write_multiple_registers, schema = vol.Schema(DEPRECATION_HEADER_SCHEMA | VALUES_SCHEMA))
    
    # Battery control service
    hass.services.async_register(
        DOMAIN, 
        "battery_control",
        _battery_control,
        vol.Schema({
            vol.Required(SERVICES_PARAM_DEVICE): vol.All(vol.Coerce(str)),
            vol.Required("power_watts"): vol.All(vol.Coerce(int), vol.Range(min=-24000, max=24000)),
            vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        })
    )
