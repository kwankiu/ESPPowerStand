from machine import Pin
import network
import ujson
import ntptime

led = Pin(13, Pin.OUT)
led.value(0)

# Read WiFi credentials from config.json
try:
    with open("config.json", "r") as config_file:
        config = ujson.load(config_file)
    wifi_ssid = config["wifi_ssid"]
    wifi_password = config["wifi_password"]
except OSError:
    print("Missing or incorrect configuration in config.json")

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.config(pm=wifi.PM_NONE)  # disable power management

try:
    wifi.connect(wifi_ssid, wifi_password)
except OSError:
    pass