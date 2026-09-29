from network import WLAN
import machine
import time

SSID    = 'Chompy'
MDP     = 'darkAmbush'
TIMEOUT = 10

wlan = WLAN(mode=WLAN.STA)
wlan.connect(ssid=SSID, auth=(WLAN.WPA2, MDP))

debut = time.time()
while not wlan.isconnected():
    if time.time() - debut > TIMEOUT:
        print("WiFi indisponible, demarrage sans reseau")
        break
    machine.idle()

if wlan.isconnected():
    print("WiFi connecte :", wlan.ifconfig())