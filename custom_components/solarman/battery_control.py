from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from logging import getLogger

_LOGGER = getLogger(__name__)

class BatteryControlManager:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.control_active = False
        self.control_end_time = None
        self.watchdog_task = None
        self.virtual_entities = {}
        
    def register_virtual_entity(self, name, entity):
        """Register a virtual entity for management"""
        self.virtual_entities[name] = entity
        
    async def start_battery_control(self, power_watts, duration_minutes):
        """Start battery control with specified power and duration"""
        if self.control_active:
            await self.stop_battery_control()
            
        try:
            # Get rated power for percentage calculation
            rated_power_data = self.coordinator.data.get("device_rated_power_sensor")
            rated_power = rated_power_data[0] if rated_power_data else 20000
            power_percentage = int((power_watts / rated_power) * 1000)  # Convert to 0.1% units
            
            # Clamp to valid range
            power_percentage = max(-1200, min(1200, power_percentage))
            
            # Set all required registers
            registers = [
                (0x044C, 1),      # Remote mode enable
                (0x0450, 1),      # Battery side control
                (0x0451, 2),      # Power priority
                (0x044D, 300),    # Watchdog 5 minutes
                (0x0455, power_percentage)  # Battery power control
            ]
            
            for address, value in registers:
                await self.coordinator.device.execute(0x10, address, data=[value])
                
            # Set control state
            self.control_active = True
            self.control_end_time = datetime.now() + timedelta(minutes=duration_minutes)
            
            # Start watchdog ping task (every 4 minutes)
            self.watchdog_task = asyncio.create_task(self._watchdog_ping())
            
            # Schedule automatic stop
            asyncio.create_task(self._auto_stop(duration_minutes))
            
            _LOGGER.info(f"Battery control started: {power_watts}W for {duration_minutes} minutes")
            
        except Exception as e:
            _LOGGER.error(f"Failed to start battery control: {e}")
            await self.stop_battery_control()
            raise
            
    async def stop_battery_control(self):
        """Stop battery control and reset registers"""
        if not self.control_active:
            return
            
        try:
            # Cancel watchdog task
            if self.watchdog_task:
                self.watchdog_task.cancel()
                
            # Reset registers
            reset_registers = [
                (0x044C, 0),      # Disable remote mode
                (0x0455, 0),      # Reset power control
            ]
            
            for address, value in reset_registers:
                await self.coordinator.device.execute(0x10, address, data=[value])
                
            # Reset state
            self.control_active = False
            self.control_end_time = None
            
            # Reset virtual entities
            if "Manual Battery Power" in self.virtual_entities:
                self.virtual_entities["Manual Battery Power"].set_virtual_value(0)
            if "Manual Control Active" in self.virtual_entities:
                self.virtual_entities["Manual Control Active"].set_virtual_value(False)
                
            _LOGGER.info("Battery control stopped")
            
        except Exception as e:
            _LOGGER.error(f"Error stopping battery control: {e}")
            
    async def _watchdog_ping(self):
        """Send periodic watchdog pings to keep remote mode active"""
        while self.control_active and datetime.now() < self.control_end_time:
            try:
                await asyncio.sleep(240)  # Wait 4 minutes
                if self.control_active:
                    # Refresh remote mode to reset watchdog
                    await self.coordinator.device.execute(0x10, 0x044C, data=[1])
                    _LOGGER.debug("Watchdog ping sent")
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Watchdog ping failed: {e}")
                
    async def _auto_stop(self, duration_minutes):
        """Automatically stop control after duration"""
        await asyncio.sleep(duration_minutes * 60)
        if self.control_active:
            await self.stop_battery_control()