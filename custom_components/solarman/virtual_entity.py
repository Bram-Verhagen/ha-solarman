from __future__ import annotations

from typing import Any
from logging import getLogger

from homeassistant.components.number import NumberEntity
from homeassistant.components.switch import SwitchEntity

from .entity import SolarmanCoordinatorEntity

_LOGGER = getLogger(__name__)

class SolarmanVirtualEntity(SolarmanCoordinatorEntity):
    """Base class for virtual entities that don't map to registers"""
    
    def __init__(self, coordinator, sensor: dict):
        super().__init__(coordinator)
        
        self._attr_key = sensor["key"]
        self._attr_name = sensor["name"]
        self._attr_device_class = sensor.get("class") or sensor.get("device_class")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{sensor['key']}"
        self._attr_icon = sensor.get("icon")
        self._virtual_value = None
        
        if unit_of_measurement := sensor.get("uom") or sensor.get("unit_of_measurement"):
            self._attr_native_unit_of_measurement = unit_of_measurement
            
    def set_virtual_value(self, value):
        """Set the virtual value and update state"""
        self._virtual_value = value
        self._attr_native_value = value
        self.async_write_ha_state()
        
    def update(self):
        """Override update to prevent reading from coordinator data"""
        pass  # Virtual entities don't update from coordinator data

class SolarmanVirtualNumberEntity(SolarmanVirtualEntity, NumberEntity):
    """Virtual number entity for battery control"""
    
    def __init__(self, coordinator, sensor: dict):
        super().__init__(coordinator, sensor)
        
        if "configurable" in sensor and (configurable := sensor["configurable"]):
            if "min" in configurable:
                self._attr_native_min_value = configurable["min"]
            if "max" in configurable:
                self._attr_native_max_value = configurable["max"]
            if "step" in configurable:
                self._attr_native_step = configurable["step"]
                
        # Set default value
        self._virtual_value = 0
        self._attr_native_value = 0
        
    async def async_set_native_value(self, value: float) -> None:
        """Update the virtual value"""
        self.set_virtual_value(value)

class SolarmanVirtualSwitchEntity(SolarmanVirtualEntity, SwitchEntity):
    """Virtual switch entity for battery control activation"""
    
    def __init__(self, coordinator, sensor: dict):
        super().__init__(coordinator, sensor)
        
        # Set default value
        self._virtual_value = False
        self._attr_native_value = False
        
        # Get battery control manager
        if not hasattr(coordinator, 'battery_control_manager'):
            from .battery_control import BatteryControlManager
            coordinator.battery_control_manager = BatteryControlManager(coordinator)
            
        self.battery_manager = coordinator.battery_control_manager
        self.battery_manager.register_virtual_entity(sensor["name"], self)
        
    @property
    def is_on(self) -> bool:
        return bool(self._virtual_value)
        
    async def async_turn_on(self, **kwargs: Any):
        """Start battery control"""
        try:
            # Get power and duration from other virtual entities
            power_entity = None
            duration_entity = None
            
            for entity_id, entity in self.battery_manager.virtual_entities.items():
                if "Manual Battery Power" in entity_id:
                    power_entity = entity
                elif "Manual Control Duration" in entity_id:
                    duration_entity = entity
                    
            if not power_entity or not duration_entity:
                _LOGGER.error("Cannot start battery control: missing power or duration entities")
                return
                
            power_watts = power_entity._virtual_value or 0
            duration_minutes = duration_entity._virtual_value or 1
            
            await self.battery_manager.start_battery_control(power_watts, duration_minutes)
            self.set_virtual_value(True)
            
        except Exception as e:
            _LOGGER.error(f"Failed to start battery control: {e}")
            self.set_virtual_value(False)
            
    async def async_turn_off(self, **kwargs: Any):
        """Stop battery control"""
        try:
            await self.battery_manager.stop_battery_control()
            self.set_virtual_value(False)
        except Exception as e:
            _LOGGER.error(f"Failed to stop battery control: {e}")