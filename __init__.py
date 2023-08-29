from __future__ import annotations

import socket
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.core import HomeAssistant, _LOGGER
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_ADDRESS, STATE_OFF, STATE_ON
from .const import *

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT): cv.positive_int,
                vol.Optional(CONF_ADDRESS, default=DEFAULT_ADDRESS): cv.string,
            }),
    },
    extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, hass_config: dict):
    config = hass_config[DOMAIN]
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    address = config.get(CONF_ADDRESS)

    entity_id = async_generate_entity_id(DOMAIN + ".{}", "fan", hass=hass)

    load_platform(hass, 'fan', DOMAIN, {}, config)
    hass.data[DOMAIN] = Broan(hass, host, port, address)
    b = hass.data[DOMAIN]
    b.search()
    return True


class Broan:
    def __init__(self, hass, host, port, address):
        self._hass = hass
        self.host = host
        self.port = port
        self.Address = address

        self.Start_Flag = "aa"
        self.Host_Id = "02"
        self.New_Opt = "5a"
        self.End_Flag = "f5"
        self.state = None
        self.Mode = None
        self.M1_speed = None
        self.M2_speed = None
        self.Temper = None
        self.Humidity = None
        self.Error_Code = None

    @staticmethod
    def mapping_speed(speed):
        if speed is None:
            real_speed = "03"
        elif speed == "low":
            real_speed = "01"
        elif speed == "medium":
            real_speed = "02"
        elif speed == "high":
            real_speed = "03"
        elif speed == "off":
            real_speed = "00"
        else:
            real_speed = speed
        return real_speed

    @staticmethod
    def mapping_name_speed(speed_code):
        if speed_code in SPEED_CODE_MAPPING.values():
            speeds = {v: k for k, v in SPEED_CODE_MAPPING.items()}
            return speeds[speed_code]
        else:
            return "off"

    @staticmethod
    def mapping_speed_code(name_speed):
        if name_speed in SPEED_CODE_MAPPING.keys():
            return SPEED_CODE_MAPPING[name_speed]
        else:
            return "00"

    @staticmethod
    def mapping_mode_value(mode_key):
        if mode_key in PRESET_MODES_TO_NAME.keys():
            mode = PRESET_MODES_TO_NAME.get(mode_key)
        else:
            mode = "00"
        return mode

    @staticmethod
    def mapping_mode_key(mode_value):
        preset_modes = {v: k for k, v in PRESET_MODES_TO_NAME.items()}
        if mode_value in PRESET_MODES_TO_NAME.values():
            value = preset_modes.get(mode_value)
        else:
            value = '关机'
        return value

    def send_cmd(self, cmd):
        """
        发送指令
        """
        try:
            host = socket.gethostbyname(self.host)
            port = (host, self.port)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(port)
            s.send(cmd)
            _LOGGER.info("send cmd: " + str(cmd))
            message = s.recv(11)
            message = ''.join(['%02x' % b for b in message])
            s.close()
            return message
        except Exception as e:
            _LOGGER.error(e)
            return e

    def make_cmd(self, mode, m1_speed, m2_speed, new_opt):
        """
        指令转为二进制
        """
        if new_opt is None:
            checksum = bytes.fromhex(self.Address + self.Host_Id + mode + m1_speed + m2_speed + self.New_Opt)
            a = checksum[1:]
            b = "%x" % sum(a)
            cmd = bytes.fromhex(
                self.Start_Flag + self.Address + self.Host_Id + mode + m1_speed + m2_speed + self.New_Opt + str(
                    b) + self.End_Flag)
        else:
            checksum = bytes.fromhex(self.Address + self.Host_Id + mode + m1_speed + m2_speed + new_opt)
            a = checksum[1:]
            b = "%x" % sum(a)
            cmd = bytes.fromhex(
                self.Start_Flag + self.Address + self.Host_Id + mode + m1_speed + m2_speed + new_opt + str(
                    b) + self.End_Flag)
        return cmd

    def search(self):
        mode = "00"
        m1_speed = "00"
        m2_speed = "00"
        new__opt = "a5"

        cmd = self.make_cmd(mode, m1_speed, m2_speed, new__opt)
        response = self.send_cmd(cmd)
        _LOGGER.info("search: " + str(response))
        self.Mode = response[6:8]
        self.M1_speed = response[8:10]
        self.M2_speed = response[10:12]
        temper = response[12:14]
        # self.Humidity = response[14:16]
        self.Humidity = int(bin(int(response[14:16], 16))[2:].rjust(8, "0"), 2)
        error_code = bin(int(response[16:18], 16))[2:].rjust(8, "0")
        temper = bin(int(temper, 16))[2:].rjust(8, "0")
        # _LOGGER.info("origin work mode:" + str(self.Mode))
        if temper.startswith("0", 0, 1):
            self.Temper = int(temper, 2)
        else:
            self.Temper = -int(temper, 2)
        if self.M2_speed == "00":
            self.state = STATE_OFF
        elif self.Mode == "00":
            self.state = STATE_OFF
        else:
            self.state = STATE_ON
        m1_status = error_code[2:3]
        m2_status = error_code[3:4]
        tem_status = error_code[6:7]
        hum_status = error_code[7:8]
        data = [m1_status, m2_status, tem_status, hum_status]
        e = ""
        for i in range(len(data)):
            if data[i] == "1":
                if i == 0:
                    e += "M1马达故障"
                elif i == 1:
                    e += "M2马达故障"
                elif i == 2:
                    e += "温度传感器故障"
                elif i == 3:
                    e += "湿度传感器故障"
        if m1_status == "0" and m2_status == "0" and tem_status == "0" and hum_status == "0":
            e = "正常"
        message = e
        _LOGGER.info("Mode: " + str(self.Mode) + " M1_speed: " + str(self.M1_speed) + " M2_speed: " + str(
            self.M2_speed) + " Temper: " + str(self.Temper) + " Humidity: " + str(self.Humidity) + " ErrorCode: " + str(
            message))
        return {"mode": self.Mode, "m1_status": m1_status, "m2_status": m2_status, "tem_status": tem_status, "hum_status": hum_status, "message": message}
