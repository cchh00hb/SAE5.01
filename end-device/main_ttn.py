"""
SAE5.01 - Phase B - Acquisition GNSS et publication LoRaWAN via TTN.

Lit la position du recepteur GNSS L76 de la carte Pytrack et l'envoie
sur le reseau LoRaWAN vers The Things Network (TTN).

Materiel : module LoPy/LoPy4 ou FiPy monte sur une carte Pytrack.
Le gateway LoRaWAN est gere separement par le Raspberry Pi du projet.

Fonctionnement :
  1. initialisation du GNSS ;
  2. initialisation LoRaWAN en EU868 ;
  3. connexion OTAA a TTN ;
  4. lecture de la position ;
  5. envoi de latitude/longitude en binaire sur le port LoRaWAN 1.
"""

import time
import socket
import struct
import ubinascii

import pycom
from network import LoRa


# ---------------------------------------------------------------------------
# Pilote du coprocesseur Pytrack
# ---------------------------------------------------------------------------

try:
    from pycoproc_2 import Pycoproc
except ImportError:
    try:
        from pycoproc_1 import Pycoproc
    except ImportError:
        print("ERREUR : aucune lib pycoproc trouvee sur la carte.")
        print("Depose pycoproc_2.py ou pycoproc_1.py dans /flash/lib.")
        raise

from L76GNSS import L76GNSS


# ---------------------------------------------------------------------------
# Configuration GNSS
# ---------------------------------------------------------------------------

TIMEOUT_GNSS = 10
PERIODE_LECTURE = 10


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

# Ces informations servent a identifier le gateway utilise par le projet.
# Elles ne sont pas utilisees pour etablir la connexion LoRaWAN.
GATEWAY_ID = "eui-58a0cbfffe801e28"
GATEWAY_EUI = "58A0CBFFFE801E28"


# ---------------------------------------------------------------------------
# Configuration TTN / LoRaWAN
# ---------------------------------------------------------------------------

# France -> Europe 868 MHz.
LORA_REGION = LoRa.EU868

# JoinEUI / AppEUI de l'application TTN.
JOIN_EUI = "AABB44455DDF9966"


APP_KEY = "4EC28E5C93BA49E3CF4590B4FA6FE98D"

# DevEUI configure dans TTN.
DEV_EUI = "70B3D57ED0079375"

# Port applicatif LoRaWAN.
LORA_PORT = 1

# Facteur d'echelle de la charge utile, voir INTERFACE.md section 4.2.
# Les degres decimaux sont multiplies par cette valeur puis arrondis, de
# facon a tenir dans un entier signe sur 3 octets.
FACTEUR_ECHELLE = 10000


# ---------------------------------------------------------------------------
# LED
# ---------------------------------------------------------------------------

LED_RECHERCHE = 0x7F3300  # orange : recherche de fix GNSS
LED_FIX = 0x007F00        # vert   : position valide
LED_LORA = 0x00007F       # bleu   : LoRaWAN / envoi
LED_ERREUR = 0x7F0000     # rouge  : erreur


# ---------------------------------------------------------------------------
# Initialisation Pytrack / GNSS
# ---------------------------------------------------------------------------

def ouvrir_coprocesseur():
    """Instancie le pilote du coprocesseur PIC de la Pytrack."""

    if hasattr(Pycoproc, "PYTRACK"):
        return Pycoproc(Pycoproc.PYTRACK)

    return Pycoproc()


pycom.heartbeat(False)
pycom.rgbled(LED_RECHERCHE)

py = ouvrir_coprocesseur()
gnss = L76GNSS(py, timeout=TIMEOUT_GNSS)


# ---------------------------------------------------------------------------
# Initialisation LoRaWAN
# ---------------------------------------------------------------------------

def initialiser_lorawan():

    print("=== Initialisation LoRaWAN ===")
    print("Region      : EU868")
    print("Gateway ID  : {}".format(GATEWAY_ID))
    print("Gateway EUI : {}".format(GATEWAY_EUI))
    print("")

    # Initialisation du module LoRaWAN.
    lora = LoRa(
        mode=LoRa.LORAWAN,
        region=LORA_REGION
    )

    # Affichage du MAC LoRa pour verification.
    mac = ubinascii.hexlify(lora.mac()).decode().upper()

    print("MAC LoRa : {}".format(mac))
    print("DevEUI   : {}".format(DEV_EUI))
    print("")

    # Conversion des identifiants hexadecimaux en bytes.
    dev_eui = ubinascii.unhexlify(DEV_EUI)
    join_eui = ubinascii.unhexlify(JOIN_EUI)
    app_key = ubinascii.unhexlify(APP_KEY)

    # Join OTAA.
    print("Demarrage du Join OTAA vers TTN...")

    lora.join(
        activation=LoRa.OTAA,
        auth=(dev_eui, join_eui, app_key),
        timeout=0
    )

    debut = time.time()

    while not lora.has_joined():

        if time.time() - debut > 180:
            raise RuntimeError(
                "Join OTAA impossible apres 180 secondes. "
                "Verifier le DevEUI, le JoinEUI, l'AppKey, "
                "la region EU868 et le gateway."
            )

        print("Pas encore rejoint...")
        time.sleep(2.5)

    print("")
    print("========== JOIN TTN REUSSI ==========")
    print("")

    pycom.rgbled(LED_LORA)

    # Creation du socket LoRaWAN.
    sock = socket.socket(
        socket.AF_LORA,
        socket.SOCK_RAW
    )

    # Port applicatif.
    sock.bind(LORA_PORT)

    # Attente de la fin de transmission.
    sock.setblocking(True)

    print("Port LoRaWAN : {}".format(LORA_PORT))

    return lora, sock


# ---------------------------------------------------------------------------
# Acquisition GNSS
# ---------------------------------------------------------------------------

def get_position():
    """
    Renvoie :
        (latitude, longitude)

    ou :
        None

    si aucun fix GNSS n'est disponible.
    """

    lat, lon = gnss.coordinates()

    if lat is None or lon is None:
        return None

    return lat, lon


# ---------------------------------------------------------------------------
# Encodage de la position
# ---------------------------------------------------------------------------

def _entier_24_bits(valeur):
    """
    Encode un entier signe sur 3 octets, big-endian, complement a deux.

    struct ne connait pas les entiers de 3 octets : on passe par un int32
    dont on retire l'octet de poids fort. Celui-ci ne porte aucune
    information tant que la valeur tient dans la plage 24 bits signee, il
    vaut 0x00 pour un positif et 0xFF pour un negatif.
    """

    if not -8388608 <= valeur <= 8388607:
        raise ValueError(
            "valeur {} hors de la plage d'un entier signe sur 3 octets".format(
                valeur
            )
        )

    return struct.pack(">i", valeur)[1:]


def encoder_position(position, en_mouvement=True, fix_valide=True):
    """
    Encode la position sur 7 octets, conformement a INTERFACE.md section 4.

    C'est l'objet de l'etape 8 : reduire la charge utile transmise sur la
    couche physique LoRa. Latitude et longitude tiennent chacune sur
    3 octets au lieu de 4, et l'octet de flags remplace les 2 octets
    economises pour transporter l'etat du vehicule.

    Structure :
        octets 0-2  latitude   entier signe, big-endian, complement a deux
        octets 3-5  longitude  idem
        octet  6    flags      bit 0 = mouvement, bit 1 = fix valide

    Facteur d'echelle : degres * 10000, soit une resolution de 0.0001 degre,
    environ 11 metres. Suffisant pour suivre un vehicule sur une carte.

    Le facteur 100000 de la version precedente ne tient pas sur 3 octets :
    la latitude atteindrait 9 000 000 pour 90 degres, au-dela des 8 388 607
    que porte un entier signe de 24 bits.
    """

    lat, lon = position

    lat_i = int(round(lat * FACTEUR_ECHELLE))
    lon_i = int(round(lon * FACTEUR_ECHELLE))

    flags = ((1 if fix_valide else 0) << 1) | (1 if en_mouvement else 0)

    return _entier_24_bits(lat_i) + _entier_24_bits(lon_i) + bytes([flags])


# ---------------------------------------------------------------------------
# Envoi LoRaWAN
# ---------------------------------------------------------------------------

def envoyer_position(sock, position):
    """Encode puis envoie la position sur le port LoRaWAN 1."""

    payload = encoder_position(position)

    print(
        "Position : lat = {:.5f}, lon = {:.5f}".format(
            position[0],
            position[1]
        )
    )

    print(
        "Payload : {}".format(
            ubinascii.hexlify(payload).decode().upper()
        )
    )

    try:
        sock.send(payload)

    except Exception as e:
        print("ERREUR envoi LoRaWAN : {}".format(e))
        return False

    print(
        "Uplink LoRaWAN envoye sur le port {}".format(
            LORA_PORT
        )
    )

    return True


# ---------------------------------------------------------------------------
# Debug GNSS
# ---------------------------------------------------------------------------

def debug_nmea():
    """Affiche les trames NMEA brutes du recepteur GNSS."""

    gnss.dump_nmea()


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main():

    print("")
    print("========================================")
    print("       SAE5.01 - LoRaWAN / TTN")
    print("========================================")
    print("Gateway : {}".format(GATEWAY_ID))
    print("")

    try:
        lora, sock = initialiser_lorawan()

    except Exception as e:

        pycom.rgbled(LED_ERREUR)

        print("")
        print("ERREUR LoRaWAN : {}".format(e))
        print("")

        return

    print("Recherche du fix GNSS en cours...")
    print("Place la Pytrack avec une vue degagee du ciel.")
    print("")

    try:

        while True:

            position = get_position()

            if position is None:

                print("Pas de fix GNSS.")

                pycom.rgbled(LED_RECHERCHE)

                time.sleep(PERIODE_LECTURE)

                continue

            pycom.rgbled(LED_FIX)

            envoyer_position(
                sock,
                position
            )

            pycom.rgbled(LED_LORA)

            time.sleep(PERIODE_LECTURE)

    except KeyboardInterrupt:

        print("")
        print("Arret sur Ctrl+C.")

    finally:

        try:
            sock.close()

        except Exception:
            pass


if __name__ == "__main__":
    main()