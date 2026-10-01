"""
SAE5.01 - Phase D - LoRaWAN / TTN avec veille par accelerometre.

Meme fonctionnement que main_ttn.py (GNSS L76 + uplink LoRaWAN vers TTN),
avec en plus la gestion de la veille de la carte Pytrack via veille.py :
l'End-Device dort par defaut et ne se reveille que si l'accelerometre
LIS2HH12 detecte un mouvement. Pendant la veille, ni le GNSS ni la radio ne
consomment de courant.

C'est le main.py de la phase D prevu par README_etape9.md section 4. A
renommer en main.py sur la carte : apres un deep sleep le module redemarre et
n'execute que boot.py puis main.py.

Differences avec main_ttn.py :
  - veille.init(py) lit la raison du reveil et arme l'accelerometre ;
  - lora.nvram_restore() evite un join OTAA a chaque reveil ;
  - un reveil par le minuteur de securite sans mouvement se rendort
    immediatement, sans uplink inutile ;
  - le bit 0 des flags (INTERFACE.md section 4.3) vient de l'accelerometre ;
  - l'inactivite prolongee declenche veille.dormir(py, lora) au lieu de
    boucler indefiniment.

Le downlink SLEEP 0x00 de l'etape 10 s'appuiera sur veille.dormir() lui aussi,
avec reveil_mouvement=False pour couper vraiment le suivi.

Materiel : module LoPy/LoPy4 ou FiPy monte sur une carte Pytrack.
Libs requises dans /flash/lib : pycoproc_2.py (ou pycoproc_1.py), L76GNSS.py,
LIS2HH12.py. Veille.py, ce fichier et les libs restent dans /flash.

Attention boot.py : sa boucle de connexion WiFi n'a pas de delai maximal
(README_etape9.md section 4). A partir de l'etape 3 le WiFi n'est plus utile
au End-Device, le supprimer de boot.py ou lui mettre un timeout, sinon la
carte reste bloquee a chaque reveil en voiture.
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

import veille


# ---------------------------------------------------------------------------
# Configuration GNSS
# ---------------------------------------------------------------------------

TIMEOUT_GNSS = 10
PERIODE_LECTURE = 10

# Duree sans mouvement avant de rendre la main au deep sleep. Le choix est un
# compromis : assez long pour ne pas couper le suivi au milieu d'un trajet
# (feu rouge,/arret dans une file), assez court pour ne pas consommer la
# batterie du vehicule a l'arret. 5 a 10 minutes est la valeur d'oral de
# l'etape 9. A raccourcir en test de bench, le bruit de la voiture faisant
# vibrer l'accelerometre en permanence.
SEUIL_INACTIVITE_S = 600

# Fenetre laissee au REPL apres un mise sous tension ou un reset, avant que la
# boucle ne reprenne la main sur la carte. Sans elle, la carte part en veille
# et Pymakr ne peut plus s'y connecter pour arreter le script.
FENETRE_CTRL_C_S = 10


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
LED_REVEIL = 0x3F003F     # violet : reveil par l'accelerometre
LED_DEMARRAGE = 0x00003F  # bleu   : mise sous tension / reset


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

    # Restauration de la session avant tout test de connexion. veille.dormir()
    # appelle lora.nvram_save() a chaque mise en veille : sans cette
    # restauration, chaque reveil repartirait d'un join OTAA complet, long et
    # couteux en temps d'antenne (duty cycle 1 %). Sans session en nvram
    # (premier demarrage, ou carte dont la flash a ete reinitialisee) la
    # restauration echoue sans consequence : on retombe sur le join.
    try:
        lora.nvram_restore()
        print("Session LoRaWAN restauree depuis la nvram.")

    except Exception as e:
        print("Pas de session LoRaWAN en nvram ({}) : join OTAA.".format(e))

    # Conversion des identifiants hexadecimaux en bytes.
    dev_eui = ubinascii.unhexlify(DEV_EUI)
    join_eui = ubinascii.unhexlify(JOIN_EUI)
    app_key = ubinascii.unhexlify(APP_KEY)

    if not lora.has_joined():

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

    else:
        print("Session LoRaWAN deja etablie, join OTAA epargne.")

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

def envoyer_position(sock, position, en_mouvement=False):
    """
    Encode puis envoie la position sur le port LoRaWAN 1.

    `en_mouvement` vient de l'accelerometre (veille.en_mouvement()) et occupe
    le bit 0 des flags : le recepteur sait ainsi si la voiture roule ou est a
    l'arret, information qui conditionne le repli en veille cote TTN.
    """

    payload = encoder_position(position, en_mouvement=en_mouvement)

    print(
        "Position : lat = {:.5f}, lon = {:.5f}, mouvement = {}".format(
            position[0],
            position[1],
            en_mouvement
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
    print("    SAE5.01 - LoRaWAN / TTN / veille")
    print("========================================")
    print("Gateway : {}".format(GATEWAY_ID))
    print("")

    # A lire avant toute autre chose : veille.init() lit la cause du reveil
    # avant d'armer l'accelerometre, sinon elle est ecrasee.
    raison = veille.init(py)

    if raison == veille.RAISON_DEMARRAGE:
        # Mise sous tension, reset ou Ctrl+D : on laisse la main au REPL le
        # temps d'un Ctrl+C, sinon impossible d'arreter la carte en salle.
        pycom.rgbled(LED_DEMARRAGE)
        print("Demarrage : Ctrl+C dans les {} s pour garder la main".format(
            FENETRE_CTRL_C_S))
        time.sleep(FENETRE_CTRL_C_S)

    else:
        pycom.rgbled(LED_REVEIL)
        print("Reveil sur {}.".format(raison))

    try:
        lora, sock = initialiser_lorawan()

    except Exception as e:

        pycom.rgbled(LED_ERREUR)

        print("")
        print("ERREUR LoRaWAN : {}".format(e))
        print("")

        return

    if raison == veille.RAISON_TIMER:
        # Reveil de securite sans mouvement : la voiture est a l'arret depuis
        # au moins DUREE_SOMMEIL_MAX_S. On se rendort aussitot, sans uplink :
        # la position n'a pas bouge et le downlink n'a rien a dire. C'est ce
        # qui donne le "je suis vivant" periodique du docstring de veille.py,
        # que le pole reception peut ajouter ici si la maquette doit
        # blogger regulierement sur la carte.
        print("Minuteur de securite expire, rien n'a bouge : on se rendort.")
        veille.dormir(py, lora)

    print("Recherche du fix GNSS en cours...")
    print("Place la Pytrack avec une vue degagee du ciel.")
    print("")

    try:

        while True:

            inactif = veille.inactif_depuis()

            if inactif >= SEUIL_INACTIVITE_S:
                # Le vehicule est a l'arret depuis assez longtemps : la boucle
                # ne ferait que repeter la meme position et vider la batterie.
                # veille.dormir() ne revient pas, le reveil se fera sur le
                # prochain mouvement (ou le prochain minuteur de securite).
                print("Aucun mouvement depuis {} s, mise en veille.".format(
                    int(inactif)))
                veille.dormir(py, lora)

            position = get_position()

            if position is None:

                print("Pas de fix GNSS.")

                pycom.rgbled(LED_RECHERCHE)

                time.sleep(PERIODE_LECTURE)

                continue

            pycom.rgbled(LED_FIX)

            envoyer_position(
                sock,
                position,
                en_mouvement=veille.en_mouvement()
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
