"""
SAE5.01 - Phase B - Acquisition GNSS.

Lit la position du recepteur GNSS L76 de la carte Pytrack et l'affiche
dans la console. Aucune connexion reseau ici : ce script prouve que le
GNSS fonctionne (etape 1, premiere moitie).

La fonction get_position() est le livrable de la phase B. Elle est reprise
telle quelle par la phase D, qui y branche la publication MQTT.

Outils de diagnostic fournis :
    etat_gnss()   resume chiffre de ce que recoit l'antenne
    reparer()     coupure et remise sous tension du recepteur
    debug_nmea()  trames brutes en continu

Materiel : module LoPy4 ou FiPy monte sur une carte Pytrack.
Libs requises dans /flash/lib : voir lib/README.md
"""

import time

import pycom

# Le nom de la lib du coprocesseur depend de la version de la carte :
# pycoproc_1 pour les Pytrack/Pysense v1, pycoproc_2 pour les v2.
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
TIMEOUT_GNSS = 10

PERIODE_LECTURE = 2       # pause entre deux lectures, en secondes
PERIODE_BILAN   = 30      # un point sur les satellites toutes les N secondes

# Registre PORTC du coprocesseur PIC de la Pytrack, et bit qui commande
# l'alimentation du recepteur GNSS.
#
# Attention au sens : ce bit vaut 1 quand le recepteur est ALIMENTE. Le
# mettre a 0 coupe le L76, et le bus I2C ne repond alors plus du tout
# (OSError: I2C bus error). C'est ce que fait Pycoproc.go_to_sleep() pour
# economiser la batterie. Verifie sur le materiel, pas deduit de la lib.
PORTC_ADDR    = 0x00E
BIT_ALIM_GNSS = 7

# Couleurs de la LED RGB, pour suivre l'etat sans regarder la console.
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
    decimaux est deja faite par L76GNSS.coordinates().
    """
    lat, lon = gnss.coordinates()

    if lat is None or lon is None:
        return None

    return (lat, lon)


# --- Diagnostic -----------------------------------------------------------

def alimentation_gnss():
    """
    Renvoie True si le coprocesseur alimente le recepteur GNSS.

    Un False ici explique a lui seul une absence totale de trames et des
    OSError sur le bus I2C.
    """
    return bool(py.peek_memory(PORTC_ADDR) & (1 << BIT_ALIM_GNSS))


def _collecte_nmea(duree=5):
    """
    Lit le bus pendant `duree` secondes et renvoie la liste des trames
    NMEA completes recues, sous forme de chaines.
    """
    tampon = b''
    trames = []
    depart = time.time()

    while time.time() - depart < duree:
        try:
            tampon += gnss._read()
        except OSError:
            time.sleep(0.2)
            continue

        while b'\r\n' in tampon:
            brute, tampon = tampon.split(b'\r\n', 1)
            try:
                ligne = brute.decode('ascii').strip()
            except Exception:
                continue
            if ligne.startswith('$'):
                trames.append(ligne)

        # Une trame NMEA fait au plus 82 caracteres : au-dela, ce qui reste
        # dans le tampon est un debut de trame tronque, on ne garde que lui.
        if len(tampon) > 512:
            tampon = tampon[-82:]

        time.sleep(0.05)

    return trames


def etat_gnss(duree=5):
    """
    Resume chiffre de ce que recoit l'antenne. Renvoie un dictionnaire :

        alimente       le recepteur est-il sous tension
        trames         nombre de trames NMEA lues pendant la mesure
        sats_vue       satellites detectes, toutes constellations
        sats_utilises  satellites servant au calcul de position
        qualite        0 = pas de fix, 1 = fix GPS, 2 = fix differentiel

    Lecture des resultats :

        trames a 0                 le recepteur ne repond pas
        trames > 0 et sats_vue 0   il fonctionne mais ne recoit aucun signal
        sats_vue > 0, qualite 0    acquisition en cours, le fix approche
        qualite >= 1               position valide
    """
    trames = _collecte_nmea(duree)

    vue = {}
    sats_utilises = 0
    qualite = 0

    for trame in trames:
        champs = trame.split(',')
        entete = champs[0]

        if entete.endswith('GSV') and len(champs) > 3:
            # Une constellation par talker : GP pour GPS, GL pour GLONASS,
            # GA pour Galileo. On garde le dernier compte annonce par chacun.
            talker = entete[1:3]
            try:
                vue[talker] = int(champs[3])
            except ValueError:
                pass

        elif entete.endswith('GGA') and len(champs) > 7:
            try:
                qualite = int(champs[6]) if champs[6] else 0
                sats_utilises = int(champs[7]) if champs[7] else 0
            except ValueError:
                pass

    return {
        'alimente': alimentation_gnss(),
        'trames': len(trames),
        'sats_vue': sum(vue.values()),
        'sats_utilises': sats_utilises,
        'qualite': qualite,
    }


def diagnostic(duree=5):
    """Affiche l'etat du recepteur en clair. A lancer depuis le REPL."""
    etat = etat_gnss(duree)

    print("alimentation    :", "oui" if etat['alimente'] else "NON")
    print("trames NMEA     :", etat['trames'])
    print("satellites vus  :", etat['sats_vue'])
    print("satellites util.:", etat['sats_utilises'])
    print("qualite du fix  :", etat['qualite'])

    if not etat['alimente']:
        print("-> recepteur hors tension, lancer reparer()")
    elif etat['trames'] == 0:
        print("-> aucune trame, bus I2C muet, lancer reparer()")
    elif etat['sats_vue'] == 0:
        print("-> recepteur vivant mais aucun signal recu")
        print("   sortir a ciel ouvert, puis lancer reparer()")
    elif etat['qualite'] == 0:
        print("-> acquisition en cours, laisser tourner")
    else:
        print("-> fix valide")

    return etat


# --- Reparation -----------------------------------------------------------

def envoyer_pmtk(commande, essais=5):
    """
    Envoie une commande PMTK au recepteur, avec reessais.

    Le bus I2C refuse souvent la premiere ecriture quand le recepteur vient
    de demarrer, d'ou la boucle.
    """
    for _ in range(essais):
        try:
            gnss.write(commande)
            return True
        except OSError:
            time.sleep(0.5)
    return False


def reparer():
    """
    Coupe puis reremet l'alimentation du recepteur, et le force en mode
    pleine puissance avec un demarrage a froid.

    C'est le seul moyen, depuis le logiciel, de sortir le L76 d'un mode
    basse consommation ou d'une configuration laissee par un programme
    precedent. La coupure d'alimentation efface tout etat interne.

    Compter deux a trois minutes a ciel ouvert apres l'appel avant de
    conclure quoi que ce soit.
    """
    print("coupure de l'alimentation du recepteur")
    py.mask_bits_in_memory(PORTC_ADDR, ~(1 << BIT_ALIM_GNSS))
    time.sleep(3)

    print("remise sous tension")
    py.set_bits_in_memory(PORTC_ADDR, 1 << BIT_ALIM_GNSS)
    time.sleep(5)

    if not alimentation_gnss():
        print("ECHEC : le recepteur n'est pas repasse sous tension")
        return False

    # PMTK225,0 sort des modes periodiques type AlwaysLocate, qui mettent la
    # radio en veille la plupart du temps. PMTK104 force un demarrage a
    # froid complet : almanach, ephemerides et position approchee effaces.
    print("mode pleine puissance :", "ok" if envoyer_pmtk('PMTK225,0') else "refuse")
    time.sleep(1)
    print("demarrage a froid     :", "ok" if envoyer_pmtk('PMTK104') else "refuse")
    time.sleep(5)

    return diagnostic()


def debug_nmea():
    """
    Affiche les trames NMEA brutes en continu. Ctrl+C pour sortir.

    Preferer diagnostic(), qui donne le meme constat en trois lignes.
    """
    gnss.dump_nmea()


# --- Boucle principale ----------------------------------------------------

def main():
    depart = time.time()
    premier_fix = None
    dernier_bilan = 0

    print("Recherche du fix GNSS en cours.")
    print("Compter 5 a 15 minutes au premier demarrage, a ciel ouvert.")

    if not alimentation_gnss():
        print("ATTENTION : le recepteur est hors tension, lancer reparer()")

    while True:
        position = get_position()
        ecoule = int(time.time() - depart)

        if position is None:
            print("pas de fix ({} s ecoulees)".format(ecoule))
            pycom.rgbled(LED_RECHERCHE)

            # Sans ce bilan, l'attente est aveugle : on ne sait pas
            # distinguer une acquisition qui progresse d'une antenne qui ne
            # recoit rien.
            if ecoule - dernier_bilan >= PERIODE_BILAN:
                dernier_bilan = ecoule
                etat = etat_gnss(duree=2)
                print("   bilan : {} trames, {} satellites en vue".format(
                    etat['trames'], etat['sats_vue']))
                if etat['sats_vue'] == 0:
                    print("   aucun signal recu, voir diagnostic() et reparer()")
        else:
            lat, lon = position

            if premier_fix is None:
                premier_fix = ecoule
                print("--- PREMIER FIX obtenu en {} s ---".format(premier_fix))

            print("lat = {:.5f}   lon = {:.5f}".format(lat, lon))
            pycom.rgbled(LED_FIX)

        time.sleep(PERIODE_LECTURE)


if __name__ == "__main__":
    main()
