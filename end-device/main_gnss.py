"""
SAE5.01 - Phase B - Acquisition GNSS seule.

Lit la position du recepteur GNSS L76 de la carte Pytrack et l'affiche
dans la console. Aucune connexion reseau n'est faite ici : ce script sert
uniquement a prouver que le GNSS fonctionne (etape 1, premiere moitie).

La fonction get_position() est le livrable de la phase B. Elle est reprise
telle quelle par la phase D, qui y branche la publication MQTT.

Materiel : module LoPy4 ou FiPy monte sur une carte Pytrack.
Libs requises dans /flash/lib : voir lib/README.md
"""

import time
import pycom

# Le nom de la lib du coprocesseur depend de la version de la carte :
# pycoproc_1 pour les Pytrack/Pysense v1, pycoproc_2 pour les v2.
# On essaie les deux plutot que d'imposer une version a tout le groupe.
try:
    from pycoproc_1 import Pycoproc
except ImportError:
    try:
        from pycoproc_2 import Pycoproc
    except ImportError:
        from pycoproc import Pycoproc     # ancienne lib unifiee

from L76GNSS import L76GNSS


# --- Reglages -------------------------------------------------------------

# Duree maximale d'une lecture. La lib scrute le bus I2C en continu pendant
# ce temps et rend la main des qu'elle capte une trame GNGLL exploitable.
# 10 s est un compromis : assez long pour attraper une trame, assez court
# pour afficher regulierement l'avancement pendant la recherche du fix.
TIMEOUT_GNSS = 10

PERIODE_LECTURE = 2       # pause entre deux lectures, en secondes

# Couleurs de la LED RGB, pour savoir ou on en est sans regarder la console.
LED_RECHERCHE = 0x7F3300  # orange : pas encore de fix
LED_FIX       = 0x007F00  # vert   : position valide


# --- Initialisation -------------------------------------------------------

pycom.heartbeat(False)    # on reprend la main sur la LED
pycom.rgbled(LED_RECHERCHE)

py = Pycoproc(Pycoproc.PYTRACK)
gnss = L76GNSS(py, timeout=TIMEOUT_GNSS)


# --- Acquisition ----------------------------------------------------------

def get_position():
    """
    Renvoie (latitude, longitude) en degres decimaux, ou None si le
    recepteur n'a pas encore de fix.

    C'est cette fonction que la phase D appellera avant de publier en MQTT.
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

    Ctrl+C pour sortir.
    """
    gnss.dump_nmea()


def main():
    debut = time.time()
    premier_fix = None

    print("Recherche du fix GNSS en cours.")
    print("Comptez 5 a 15 minutes au premier demarrage, pres d'une fenetre.")

    while True:
        position = get_position()

        if position is None:
            attente = int(time.time() - debut)
            print("pas de fix ({} s ecoulees)".format(attente))
            pycom.rgbled(LED_RECHERCHE)
        else:
            lat, lon = position

            if premier_fix is None:
                premier_fix = int(time.time() - debut)
                print("--- PREMIER FIX obtenu en {} s ---".format(premier_fix))

            print("lat = {:.5f}   lon = {:.5f}".format(lat, lon))
            pycom.rgbled(LED_FIX)

        time.sleep(PERIODE_LECTURE)



# import socket
#
# server_ip = '1.1.1.1'
# server_port = 1111
#
# s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# donnees = "{},{}".format(lat, lon)
#
# message = donnees.encode('utf-8')
# s.sendto(message, (server_ip, server_port))
# print(message)
# s.close()


if __name__ == "__main__":
    main()
