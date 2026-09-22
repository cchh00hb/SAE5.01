"""
SAE5.01 - Phase B - Acquisition GNSS seule.

Lit la position du recepteur GNSS L76 de la carte Pytrack et l'affiche
dans la console. Aucune connexion reseau n'est faite ici : ce script sert
uniquement a prouver que le GNSS fonctionne (etape 1, premiere moitie).

La fonction get_position() est le livrable de la phase B. Elle est reprise
telle quelle par la phase D, qui y branche la publication MQTT.

Materiel : module FiPy monte sur une carte Pytrack.
Libs requises dans /flash/lib : voir lib/README.md
"""

import time

import pycom

# Le nom de la lib du coprocesseur change selon la version de la carte et
# de la bibliotheque Pycom installee. On essaie les trois variantes connues
# plutot que d'imposer une seule version a tout le groupe.
try:
    from pycoproc_1 import Pycoproc          # Pytrack / Pysense v1
    _BOARD = Pycoproc.PYTRACK
    _make_coproc = lambda: Pycoproc(_BOARD)
except ImportError:
    try:
        from pycoproc import Pycoproc        # ancienne lib unifiee
        _BOARD = Pycoproc.PYTRACK
        _make_coproc = lambda: Pycoproc(_BOARD)
    except ImportError:
        from pytrack import Pytrack          # lib historique
        _make_coproc = Pytrack

from L76GNSS import L76GNSS


# --- Reglages -------------------------------------------------------------

PERIODE_LECTURE = 2       # secondes entre deux lectures
TIMEOUT_GNSS    = 30      # secondes avant que la lib abandonne une lecture

# Couleurs de la LED RGB, pour savoir ou on en est sans regarder la console.
LED_RECHERCHE = 0x7F3300  # orange : pas encore de fix
LED_FIX       = 0x007F00  # vert   : position valide


# --- Initialisation -------------------------------------------------------

pycom.heartbeat(False)    # on reprend la main sur la LED
pycom.rgbled(LED_RECHERCHE)

py = _make_coproc()
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
    """
    lat, lon = gnss.coordinates()

    if lat is None or lon is None:
        return None

    return (lat, lon)


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


if __name__ == "__main__":
    main()
