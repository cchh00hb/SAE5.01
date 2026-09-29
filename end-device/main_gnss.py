"""
SAE5.01 - Phase B - Acquisition GNSS et publication MQTT.

Lit la position du recepteur GNSS L76 de la carte Pytrack, l'affiche
dans la console, et la publie sur le broker Mosquitto du poste de
reception.

Ce script a deux modes d'execution, et doit fonctionner dans les deux :
  - au boot, si le fichier est renomme en main.py : boot.py connecte le
    WiFi, puis ce script lit le GNSS et publie ;
  - a la demande, via "Run file on device" de Pymakr : boot.py n'est alors
    PAS execute, la connexion WiFi est donc refaite ici.

L'acquisition et la publication sont dans le meme fichier, mais restent
separees : get_position() ne fait que lire, publier_mqtt() ne fait que
publier. Une phase ulterieure (LoRaWAN via TTN) ne remontera que
get_position() a autre chose.

Materiel : module LoPy4 ou FiPy monte sur une carte Pytrack.
Libs requises dans /flash/lib : mqtt.py, L76GNSS.py, pycoproc_1.py et
pytrack.py. Voir lib/README.md.
"""

import time

import pycom
from mqtt import MQTTClient
from network import WLAN

# Le pilote du coprocesseur depend de la version de la carte : pycoproc_1
# pour les Pytrack/Pysense v1, pycoproc_2 pour les v2. On tente la v2 en
# premier, car c'est celle de la carte de ce projet : son identifiant USB
# est 04d8:f013, la valeur que pycoproc_2 verifie en lecture du PIC. Un
# membre du groupe qui a une carte v1 depose pycoproc_1.py en plus, et le
# repli se fait tout seul.
try:
    from pycoproc_2 import Pycoproc
except ImportError:
    try:
        from pycoproc_1 import Pycoproc
    except ImportError:
        # On relance l'erreur telle quelle plutot que d'echouer sur une
        # troisieme tentative "from pycoproc import Pycoproc" : ce nom
        # correspond a la vieille lib unifiee, qui n'existe plus dans
        # pycom/pycom-libraries, et enverrait le groupe chercher un
        # fichier introuvable.
        print("ERREUR : aucune lib pycoproc trouvee sur la carte.")
        print("Depose pycoproc_2.py (Pytrack v2, celle de ce projet)")
        print("ou pycoproc_1.py (v1) dans end-device/lib/, puis uploade.")
        raise

from L76GNSS import L76GNSS


def ouvrir_coprocesseur():
    """
    Instancie le pilote du coprocesseur PIC de la carte, et renvoie l'objet.

    L'appel de construction n'est pas le meme selon la version, ce qui rend
    un simple Pycoproc(...) impossible a ecrire une fois pour toutes :
      - v2 : Pycoproc() sans argument. La lib deduit le type de carte du
        PIC et verifie l'identifiant USB. C'est le cas de la carte de ce
        projet.
      - v1 : Pycoproc(Pycoproc.PYTRACK), le type de carte se passant en
        premier argument.

    On distingue les deux sur la presence de l'attribut de classe PYTRACK,
    que seule pycoproc_1 definit.
    """
    if hasattr(Pycoproc, "PYTRACK"):
        return Pycoproc(Pycoproc.PYTRACK)

    return Pycoproc()


# --- Reglages -------------------------------------------------------------

# Duree maximale d'une lecture. La lib scrute le bus I2C en continu pendant
# ce temps et rend la main des qu'elle capte une trame GNGLL exploitable.
# 10 s est un compromis : assez long pour attraper une trame, assez court
# pour afficher regulierement l'avancement pendant la recherche du fix.
TIMEOUT_GNSS = 10

PERIODE_LECTURE = 2       # pause entre deux lectures, en secondes

# Broker Mosquitto du poste de reception. A aligner sur la section 1
# d'INTERFACE.md (IP fixe du Raspberry Pi, port 1883).
IP_BROKER = '10.72.189.243'
PORT_BROKER = 1883

# Topic de publication.
#
# ATTENTION : ce script utilise "gps" comme demande, mais la section 2.1
# d'INTERFACE.md impose "sae501/groupeX/position". Les deux ne peuvent pas
# cohabiter : Node-RED et MQTT Box ecoutent le topic du contrat. Changer
# cette seule constante suffit, mais c'est un ecart au document de
# reference, il faut donc le trancher en groupe.
TOPIC_GPS = 'gps'

# Identifiant de client. Doit etre unique : si deux cartes publient avec le
# meme identifiant, Mosquitto deconnecte la premiere au profit de la
# seconde. On y met le token de la carte pour l'identifier dans les logs
# du broker.
ID_CLIENT = 'sae501-Py72a4c7'

# Mosquitto sur un reseau de TP tourne souvent sans authentification. Si le
# broker exige un couple, renseigner ces deux constantes.
UTILISATEUR = None
MOT_DE_PASSE_BROKER = None

# mqtt.py n'a aucun mecanisme de reconnexion, la boucle doit s'en charger.
MQTT_TENTATIVES = 5        # essais de connexion d'affilee
MQTT_PAUSE = 3             # pause entre deux essais, en secondes

# Meme reseau que boot.py, duplique ici pour que le mode "Run file on
# device" fonctionne seul. boot.py n'etant pas execute dans ce mode, la
# connexion doit etre capable de se faire depuis ce fichier. A factoriser
# dans un module commun des qu'un autre script en a besoin.
SSID = 'Chompy'
MOT_DE_PASSE = 'darkAmbush'

# keepalive a 0, et c'est volontaire. mqtt.py n'envoie jamais de PINGREQ
# tout seul (il faudrait appeler ping() a la main) : annoncer un keepalive
# non nul au broker le garantit mort au bout de 1,5 fois ce delai, alors
# qu'avec 0 il ne peut pas nous expulser. A changer seulement si l'on
# ajoute les ping() periodiques.

# Couleurs de la LED RGB, pour savoir ou on en est sans regarder la console.
LED_RECHERCHE = 0x7F3300  # orange : pas encore de fix
LED_FIX       = 0x007F00  # vert   : position valide


# --- Initialisation -------------------------------------------------------

pycom.heartbeat(False)    # on reprend la main sur la LED
pycom.rgbled(LED_RECHERCHE)

py = ouvrir_coprocesseur()
gnss = L76GNSS(py, timeout=TIMEOUT_GNSS)


# --- Connexion ------------------------------------------------------------

def connecter_wifi():
    """
    Connecte le WiFi s'il ne l'est pas deja. Renvoie True si la connexion
    est etablie a la sortie.

    Au boot, boot.py a deja fait le travail : le test renvoie True et on ne
    touche a rien. Lance via "Run file on device", boot.py n'a pas ete
    execute et la publication MQTT echouerait sans cette connexion.
    """
    wlan = WLAN(mode=WLAN.STA)

    if wlan.isconnected():
        print("WiFi deja connecte : {}".format(wlan.ifconfig()))
        return True

    print("Connexion au WiFi {}...".format(SSID))
    wlan.connect(ssid=SSID, auth=(WLAN.WPA2, MOT_DE_PASSE))

    # boot.py boucle sur machine.idle(), sans limite. On borne l'attente
    # pour ne pas rester bloque indefiniment si le reseau de TP est
    # indisponible : le GNSS reste lisible hors ligne, autant le garder.
    for _ in range(20):
        if wlan.isconnected():
            print("WiFi connecte : {}".format(wlan.ifconfig()))
            return True
        time.sleep(1)

    print("ECHEC : WiFi non connecte apres 20 s.")
    print("Sans reseau, la position s'affiche mais ne part pas en MQTT.")
    return False


def connecter_mqtt():
    """
    Ouvre une session MQTT sur le broker. Renvoie le client, ou None si le
    broker reste injoignable apres MQTT_TENTATIVES essais.

    Le client est construit ici et pas au niveau du module : son
    constructeur appelle socket.getaddrinfo(), qui echoue si le WiFi n'est
    pas encore monte. C'est aussi pour cela que connecter_wifi() doit
    passer avant, y compris au boot ou boot.py s'en est charge.
    """
    for essai in range(1, MQTT_TENTATIVES + 1):
        try:
            client = MQTTClient(ID_CLIENT, IP_BROKER, port=PORT_BROKER,
                                user=UTILISATEUR,
                                password=MOT_DE_PASSE_BROKER,
                                keepalive=0)
            client.connect()

            print("MQTT connecte a {}:{} (topic {})".format(
                IP_BROKER, PORT_BROKER, TOPIC_GPS))
            return client

        except Exception as e:
            # Attrape large : selon la cause on peut voir une erreur
            # reseau, un refus d'authentification du broker, ou un echec
            # de resolution de nom si l'IP est erronee.
            print("MQTT echec, essai {}/{} : {}".format(
                essai, MQTT_TENTATIVES, e))
            time.sleep(MQTT_PAUSE)

    return None


# --- Acquisition ----------------------------------------------------------

def get_position():
    """
    Renvoie (latitude, longitude) en degres decimaux, ou None si le
    recepteur n'a pas encore de fix.

    Elle ne publie rien : la lecture et la publication sont separees. Une
    phase ulterieure (LoRaWAN via TTN) reutilisera cette fonction telle
    quelle, en remplacant publier_mqtt().

    Le contrat d'interface impose de ne rien publier sans fix valide, d'ou
    le None plutot qu'un couple (0.0, 0.0) qui placerait le vehicule au
    large du golfe de Guinee.

    La conversion depuis le format NMEA (degres-minutes) vers les degres
    decimaux est deja faite par L76GNSS.coordinates(), il n'y a rien a
    recalculer ici.
    """
    lat, lon = gnss.coordinates()

    if lat is None or lon is None:
        return None

    return (lat, lon)


def publier_mqtt(client, position):
    """
    Publie la position sur TOPIC_GPS. Renvoie True si le message est parti.

    lat et lon sont ecrits comme nombres JSON et non comme chaines, ce
    qu'attend la section 3 d'INTERFACE.md et ce que Node-RED peut exploiter
    sans conversion. Le format reste le degree decimal, la conversion depuis
    le NMEA ayant deja ete faite par L76GNSS.coordinates().

    Aucun message n'est publie sans fix : l'appelant n'arrive pas ici si
    get_position() a rendu None, comme l'impose le contrat.
    """
    lat, lon = position
    payload = '{{"lat": {:.5f}, "lon": {:.5f}}}'.format(lat, lon)

    try:
        client.publish(TOPIC_GPS, payload)
    except Exception as e:
        # Une session cassee (coupure WiFi, broker redemarre) leve ici a
        # chaque envoi. On se contente de le signaler, c'est main() qui
        # decide de rouvrir une session.
        print("publication impossible : {}".format(e))
        return False

    print("publie : {}".format(payload))
    return True


def debug_nmea():
    """
    Affiche les trames NMEA brutes envoyees par le recepteur, en boucle.
    A lancer depuis le REPL quand get_position() ne rend jamais de position :

        import main_gnss
        main_gnss.debug_nmea()

    Si des lignes $GNGGA, $GNGLL, $GPGSV defilent, le recepteur est vivant
    et correctement cable : il cherche juste encore les satellites. Le champ
    qui suit l'heure dans $GNGGA vaut 0 tant qu'il n'y a pas de fix.

    Si rien ne s'affiche du tout, le probleme est materiel : module mal
    enfonce sur la Pytrack, ou mauvaise carte d'extension.

    L'import execute l'initialisation GNSS mais pas main(), grace au
    garde-fou __main__, et n'ouvre aucune session MQTT.

    Ctrl+C pour sortir.
    """
    gnss.dump_nmea()


def main():
    debut = time.time()
    premier_fix = None
    publies = 0
    client = None

    if not connecter_wifi():
        # MQTT repose sur TCP : sans reseau il n'y a rien a tenter. On sort
        # plutot que de boucler indefiniment sur un echec deja connu.
        print("Abandon : pas de WiFi, la publication MQTT est impossible.")
        return

    client = connecter_mqtt()

    print("Recherche du fix GNSS en cours.")
    print("Comptez 5 a 15 minutes au premier demarrage, pres d'une fenetre.")

    try:
        while True:
            position = get_position()

            if position is None:
                attente = int(time.time() - debut)
                print("pas de fix ({} s ecoulees)".format(attente))
                pycom.rgbled(LED_RECHERCHE)
                time.sleep(PERIODE_LECTURE)
                continue

            lat, lon = position

            if premier_fix is None:
                premier_fix = int(time.time() - debut)
                print("--- PREMIER FIX obtenu en {} s ---".format(premier_fix))

            print("lat = {:.5f}   lon = {:.5f}".format(lat, lon))
            pycom.rgbled(LED_FIX)

            if client is None:
                client = connecter_mqtt()

            if client is not None and publier_mqtt(client, position):
                publies += 1
            else:
                # Une session cassee ne se relance pas toute seule, et la
                # republier en boucle ne servirait a rien. On la jette :
                # le tour suivant rouvrira une connexion neuve, et la
                # position en cours est perdue de toute facon.
                client = None

            time.sleep(PERIODE_LECTURE)

    except KeyboardInterrupt:
        print("Arret sur Ctrl+C, {} message(s) publie(s).".format(publies))

    finally:
        # Un seul point de sortie, donc un seul disconnect. Il echoue aussi
        # sur une session cassee, d'ou le rattrapage : sans lui, le Ctrl+C
        # se terminerait sur une traceback au lieu du resume final.
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    main()