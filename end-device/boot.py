from network import WLAN
import machine

wlan = WLAN(mode=WLAN.STA)

wlan.connect(ssid='Chompy', auth=(WLAN.WPA2, 'darkAmbush'))
while not wlan.isconnected():
    machine.idle()
print("WiFi connected successfully")
print(wlan.ifconfig())
