import json
import ssl
import paho.mqtt.client as mqtt

BROKER = "eu1.cloud.thethings.network"
PORT = 8883

USERNAME = "end-device-ncyrm@ttn"
PASSWORD = "NNSXS.G24ZNOZNXYSVNVH7PIIDKB22YROLLUAGP57TLIQ.XMCDO2JMVDWAHZFCAACFRJB4SUBPO2T6VA37TOXKQF4VSERQ3UIA"

DEVICE_ID = "end-device-ncyrm"

TOPIC = f"v3/end-device-ncyrm@ttn/devices/end-device-ncyrm/up"


def on_connect(client, userdata, flags, rc):
    print("Connecté à TTN, code :", rc)
    client.subscribe(TOPIC)
    print("Abonné à :", TOPIC)


def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())

    print(json.dumps(data, indent=2))

    # Récupération du payload décodé par TTN
    decoded = data.get("uplink_message", {}).get("decoded_payload")

    if decoded:
        print("Latitude :", decoded.get("latitude"))
        print("Longitude:", decoded.get("longitude"))


client = mqtt.Client()
client.username_pw_set(USERNAME, PASSWORD)

client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

client.on_connect = on_connect
client.on_message = on_message

print("Connexion à TTN...")
client.connect(BROKER, PORT)

client.loop_forever()