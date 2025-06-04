from __future__ import annotations

import logging
import socket
from typing import Optional, Any
from propcache.api import cached_property
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    ENTITY_ID_FORMAT,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_FRIENDLY_NAME,
    CONF_UNIQUE_ID,
    CONF_VALUE_TEMPLATE,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN, STATE_OFF,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.percentage import percentage_to_ordered_list_item, ordered_list_item_to_percentage
from .const import *

_LOGGER = logging.getLogger(__name__)

PRESET_MODES = list(PRESET_MODES_TO_NAME)


def setup_platform(hass: HomeAssistant, config: ConfigType, add_entities,
                   discovery_info: DiscoveryInfoType | None = None) -> None:
    """Set up the Broan Fan platform."""
    _LOGGER.info("setup platform")
    host = config.get('host')
    port = config.get('port')
    address = config.get('address')
    _LOGGER.warn("host:" + str(config.get('host')))
    _LOGGER.warn("address:" + str(config.get('address')))
    add_entities([BroanFan(hass, config)])


class BroanFan(FanEntity):
    @property
    def supported_features(self):
        """Flag supported features."""
        return (
            FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
            if self.speed_count > 1
            else FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.SET_SPEED
        )

    def __init__(self, hass, config):
        self._hass = hass
        self._config = config
        self._name = "broan"
        self._state = None
        self._preset_mode = None
        self._preset_modes = PRESET_MODES
        self._preset_mode = None
        self._temper = None
        self._humidity = None
        self._status = None
        self._percentage = 0
        self.fan_client = hass.data[DOMAIN]
        self._host = config.get('host') # Store host for unique_id
        self._address = config.get('address') # Store address for unique_id

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"broan_{self._host}_{self._address}"

    @property
    def name(self):
        """Return the name of the fan."""
        return self._name

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return 'mdi:air-conditioner'

    @property
    def in_on(self):
        _LOGGER.info("is on: " + str(self._state))
        work_mode = self.fan_client.search()['mode']
        message = self.fan_client.search()['message']
        _LOGGER.info("broan is_on work mode:" + str(work_mode))
        _LOGGER.info("broan is_on message:" + str(message))
        if work_mode != "00" and message == "正常":
            self._state = STATE_ON
        self._preset_mode = self.fan_client.mapping_mode_key(work_mode)
        _LOGGER.info("broan is_on _preset_mode:" + str(self._preset_mode))
        return self._state not in ["off", None]

    def update(self):
        res = self.fan_client.search()
        work_mode = res['mode']
        message = self._status = res['message']
        self._temper = self.fan_client.Temper
        self._humidity = self.fan_client.Humidity
        mode = self.fan_client.mapping_mode_key(work_mode)
        if mode == "关机" or mode is None:
            self._preset_mode = None
        else:
            self._preset_mode = mode
        _LOGGER.info("broan update _preset_mode: " + str(self._preset_mode))
        if self._preset_mode in self._preset_modes:
            self._state = STATE_ON
        elif self._preset_mode == "关机" or self._preset_mode is None:
            self._state = STATE_OFF
        if self._preset_mode == PRESET_MODE_OUT:
            speed_code = self.fan_client.M2_speed
        else:
            speed_code = self.fan_client.M1_speed
        # _LOGGER.info("broan update speed code: " + str(speed_code))
        name_speed = self.fan_client.mapping_name_speed(speed_code)
        # _LOGGER.info("broan update name_speed: " + str(name_speed))
        if name_speed == "off":
            self._percentage = 0
        else:
            self._percentage = ordered_list_item_to_percentage(ORDERED_NAMED_FAN_SPEEDS, name_speed)
        # _LOGGER.info("broan update _percentage: " + str(self._percentage))
        self._status = message
        data = {"percentage": self._percentage, "status": self._status}
        return data

    @property
    def percentage(self):
        return self._percentage

    @property
    def preset_modes(self) -> list[str]:
        """Return the current preset mode."""
        return self._preset_modes

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        return self._preset_mode

    @property
    def extra_state_attributes(self):
        _attributes = {'temperature': self._temper, 'humidity': self._humidity, "status": self._status}
        return _attributes

    def set_speed_by_mode(self, speed):
        real_speed = self.fan_client.mapping_speed(speed)
        if self._preset_mode is None or self._preset_mode == PRESET_MODE_CHANGE:
            self._preset_mode = PRESET_MODE_CHANGE
            m1_speed = m2_speed = real_speed
        elif self._preset_mode == PRESET_MODE_OUT:
            m1_speed = "00"
            m2_speed = real_speed
        elif self._preset_mode == PRESET_MODE_SMART:
            m1_speed = m2_speed = '01'
        elif self._preset_mode == PRESET_MODE_POWER:
            m1_speed = m2_speed = '03'
        elif self._preset_mode == PRESET_MODE_SAVING:
            m1_speed = m2_speed = '01'
        else:
            m1_speed = m2_speed = '00'
        return m1_speed, m2_speed

    def set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode in self._preset_modes:
            self._preset_mode = preset_mode
        _LOGGER.info("broan set mode: " + preset_mode)
        if self._state == STATE_ON:
            mode_code = self.fan_client.mapping_mode_value(self._preset_mode)
            speed = percentage_to_ordered_list_item(ORDERED_NAMED_FAN_SPEEDS, self._percentage)
            m1_speed, m2_speed = self.set_speed_by_mode(speed)
            cmd = self.fan_client.make_cmd(mode_code, m1_speed, m2_speed, None)
            self.fan_client.send_cmd(cmd)
            self.fan_client.search()

    def turn_off(self, **kwargs):
        mode_code = "00"
        m1_speed = "00"
        m2_speed = "00"
        cmd = self.fan_client.make_cmd(mode_code, m1_speed, m2_speed, None)
        self.fan_client.send_cmd(cmd)
        work_mode = self.fan_client.search()['mode']
        _LOGGER.info("broan turn off work mode: " + str(work_mode))
        if work_mode == "00":
            self._state = STATE_OFF
            self._preset_mode = None
            self._percentage = 0

    def turn_on(self, speed: Optional[str] = None, percentage: Optional[int] = None,
                preset_mode: Optional[str] = None, **kwargs: Any) -> None:
        """Turn on the fan."""
        if percentage is None or int(percentage) == 0:
            self._percentage = 100
        else:
            self._percentage = percentage
        if preset_mode is None and self._preset_modes is None:
            self._preset_mode = PRESET_MODE_CHANGE
        else:
            self._preset_mode = preset_mode
        _LOGGER.info("broan turn on preset_mode: " + str(preset_mode))
        _LOGGER.info("broan turn on self preset_mode: " + str(self._preset_mode))
        speed = percentage_to_ordered_list_item(ORDERED_NAMED_FAN_SPEEDS, self._percentage)
        m1_speed, m2_speed = self.set_speed_by_mode(speed)
        mode_code = self.fan_client.mapping_mode_value(self._preset_mode)
        cmd = self.fan_client.make_cmd(mode_code, m1_speed, m2_speed, None)
        self.fan_client.send_cmd(cmd)
        res = self.fan_client.search()
        work_mode = res['mode']
        if not work_mode == "00":
            self._state = STATE_ON

    def set_percentage(self, percentage):
        m1_speed = None
        m2_speed = None
        self._percentage = percentage
        self._percentage = percentage_to_ordered_list_item(ORDERED_NAMED_FAN_SPEEDS, self._percentage)
        speed = self.fan_client.mapping_speed(self._percentage.lower())

        if self._state == STATE_ON:
            # 若预设模式为空，查询一次
            if self._preset_mode is None:
                work_mode = self.fan_client.search()['mode']
                self._preset_mode = self.fan_client.mapping_mode_key(work_mode)
            _LOGGER.info("preset mode: " + str(self._preset_mode))
            # 若预设模式是换气或者为空 按需设置速度
            if self._preset_mode == PRESET_MODE_CHANGE or self._preset_mode is None:
                m1_speed = speed
                m2_speed = speed
            # 若预设模式为排风 关闭进气
            elif self._preset_mode == PRESET_MODE_OUT:
                m1_speed = "00"
                m2_speed = speed
            # 此外模式不支持
            else:
                _LOGGER.warning("broan warn preset mode: " + self._preset_mode + " do not support change speed")
            # 发送指令
            if m1_speed is not None and m2_speed is not None:
                mode_code = self.fan_client.mapping_mode_value(self._preset_mode)
                _LOGGER.info("send command: " + str(mode_code) + " m1_speed: " + m1_speed)
                cmd = self.fan_client.make_cmd(mode_code, m1_speed, m2_speed, self.fan_client.New_Opt)
                res = self.fan_client.send_cmd(cmd)
                _LOGGER.info("set speed in broan.py: " + str(res))
