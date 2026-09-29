"""
SAE5.01 - Validation 6, etape 9 - Reveil par accelerometre et deep sleep.

Par defaut le End-Device dort. Il ne se reveille que lorsque l'accelerometre
LIS2HH12 de la Pytrack detecte un mouvement (le vehicule demarre). A ce
moment seulement, le GNSS et LoRaWAN sont utilises. Le retour en veille est
declenche par le code appelant : inactivite prolongee, ou commande SLEEP
recue en downlink (etape 10, octet 0x00, voir INTERFACE.md section 5).

Ce fichier est une bibliotheque : il ne fait rien a l'import. Il est appele
par le main.py de la phase D (et par test_veille.py pour la demo seule).

API a utiliser :

    import veille
    raison = veille.init(py)       # une fois au demarrage
    veille.en_mouvement()          # True/False, pour le bit 0 des flags
    veille.inactif_depuis()        # secondes sans mouvement
    veille.dormir(py, lora)        # ne revient jamais

`py` est l'objet Pycoproc deja cree par main_gnss.py : on le partage au lieu
d'en creer un second sur le meme bus I2C.

Materiel : LoPy4 ou FiPy sur Pytrack v1 (salle de TP) ou v2.
Libs requises dans /flash/lib : L76GNSS.py, pycoproc_1.py (ou _2), LIS2HH12.py
"""

import time
import machine
import pycom
from machine import Pin

from LIS2HH12 import LIS2HH12

# Meme detection de version que main_gnss.py. Les deux versions de la carte
# ne s'endorment pas de la meme facon (voir dormir()), il faut donc savoir
# laquelle est presente.
try:
    import pycoproc_1 as _coproc
    PYTRACK_V2 = False
except ImportError:
    try:
        import pycoproc_2 as _coproc
        PYTRACK_V2 = True
    except ImportError:
        import pycoproc as _coproc       # ancienne lib unifiee, API de la v1
        PYTRACK_V2 = False


# --- Reglages -------------------------------------------------------------

# Seuil et duree de l'interruption d'activite de l'accelerometre.
# 2000 mg / 200 ms sont les valeurs des exemples Pycom : il faut secouer la
# carte franchement, c'est pratique pour la demo en salle. Pour une vraie
# voiture il faudra sans doute baisser le seuil : utiliser calibrer().
# Contraintes de la lib (pleine echelle 4 g, 50 Hz) :
#   seuil entre 32 et 4000 mg, duree entre 160 et 40800 ms.
SEUIL_MG = 2000
DUREE_MS = 200

# Meme en veille, le coprocesseur a un minuteur : il reveille la carte au
# bout de ce temps si rien ne bouge. C'est un filet de securite, on peut
# aussi s'en servir pour un message "je suis vivant" une fois par jour.
DUREE_SOMMEIL_MAX_S = 24 * 3600

# Raisons de reveil renvoyees par init()
RAISON_MOUVEMENT = "mouvement"   # l'accelerometre a reveille la carte
RAISON_TIMER = "timer"           # le minuteur de securite a expire
RAISON_DEMARRAGE = "demarrage"   # mise sous tension, reset, Ctrl+D, bouton


# --- Etat interne ---------------------------------------------------------

_acc = None
_debut_inactivite = time.time()


def _sur_interruption(pin):
    """
    Appelee par la lib a chaque front sur la broche INT de l'accelerometre
    (P13). Niveau haut = activite, niveau bas = retour au repos. L'etat
    courant est relu directement sur la broche dans en_mouvement(), on ne
    memorise ici que l'instant ou le mouvement s'est arrete.
    """
    global _debut_inactivite
    if not pin():
        _debut_inactivite = time.time()


def _armer_accelerometre(py):
    global _acc, _debut_inactivite
    if _acc is None:
        _acc = LIS2HH12(py)          # reutilise le bus I2C de la Pytrack
    seuil, duree = _acc.enable_activity_interrupt(SEUIL_MG, DUREE_MS,
                                                  _sur_interruption)
    _debut_inactivite = time.time()
    return seuil, duree


# --- API ------------------------------------------------------------------

def raison_reveil(py):
    """
    Renvoie RAISON_MOUVEMENT, RAISON_TIMER ou RAISON_DEMARRAGE.

    Pytrack v1 : le coprocesseur coupe completement l'alimentation du module
    pendant la veille. Au reveil le module redemarre comme a la mise sous
    tension, machine.wake_reason() ne sait donc rien : c'est le coprocesseur
    qui a memorise la cause, on la lui demande.

    Pytrack v2 : le module reste en deep sleep ESP32 et se reveille sur la
    broche P13 reliee a l'accelerometre, machine.wake_reason() suffit.
    """
    if PYTRACK_V2:
        cause = machine.wake_reason()[0]
        if cause == machine.PIN_WAKE:
            return RAISON_MOUVEMENT
        if cause == machine.RTC_WAKE:
            return RAISON_TIMER
        return RAISON_DEMARRAGE

    # Un Ctrl+D ou machine.reset() ne redemarre que le module : le
    # coprocesseur garde alors la cause du reveil precedent, perimee.
    if machine.reset_cause() == machine.SOFT_RESET:
        return RAISON_DEMARRAGE

    cause = py.get_wake_reason()
    if cause == _coproc.WAKE_REASON_ACCELEROMETER:
        return RAISON_MOUVEMENT
    if cause == _coproc.WAKE_REASON_TIMER:
        return RAISON_TIMER
    return RAISON_DEMARRAGE


def init(py):
    """
    A appeler une fois au demarrage, juste apres la creation de `py`.
    Lit la raison du reveil puis arme l'accelerometre pour suivre les
    mouvements pendant le suivi. Renvoie la raison du reveil.
    """
    raison = raison_reveil(py)       # a lire avant de toucher au reste
    seuil, duree = _armer_accelerometre(py)
    print("[veille] reveil : {} (accelerometre {:.0f} mg / {:.0f} ms)".format(
        raison, seuil, duree))
    return raison


def en_mouvement():
    """True si l'accelerometre signale une activite en ce moment."""
    if _acc is None or _acc.int_pin is None:
        return False
    return bool(_acc.int_pin())


def inactif_depuis():
    """Nombre de secondes depuis la fin du dernier mouvement (0 si on bouge)."""
    if en_mouvement():
        return 0
    return time.time() - _debut_inactivite


def dormir(py, lora=None, reveil_mouvement=True,
           duree_max_s=DUREE_SOMMEIL_MAX_S):
    """
    Passe la carte en faible consommation. Ne revient JAMAIS : le reveil est
    un redemarrage complet (boot.py puis main.py).

    lora : l'objet network.LoRa, s'il existe. On sauvegarde alors la session
           LoRaWAN en flash (nvram_save) pour ne pas refaire un join OTAA a
           chaque reveil. Le pole LoRa doit appeler lora.nvram_restore() au
           demarrage, avant de tester lora.has_joined().

    reveil_mouvement : False pour ne se reveiller que sur le minuteur. Utile
           si l'utilisateur coupe le suivi alors que la voiture roule
           encore : sinon elle se reveillerait au prochain feu rouge.

    Le GNSS est laisse en alimentation de secours (gps=True) : il garde les
    ephemerides et refait un fix en quelques secondes au reveil (hot start)
    au lieu de plusieurs minutes.
    """
    if lora is not None:
        try:
            lora.nvram_save()
            print("[veille] session LoRaWAN sauvegardee")
        except Exception as e:
            print("[veille] nvram_save impossible :", e)

    if reveil_mouvement:
        _armer_accelerometre(py)

    print("[veille] deep sleep, reveil sur {} ou dans {} s".format(
        "mouvement" if reveil_mouvement else "minuteur seul", duree_max_s))
    pycom.heartbeat(False)
    pycom.rgbled(0x000000)
    time.sleep_ms(100)               # laisser partir les print sur l'UART

    if PYTRACK_V2:
        # Module en deep sleep ESP32, accelerometre alimente, reveil par P13.
        if reveil_mouvement:
            broches = [Pin('P13', mode=Pin.IN, pull=Pin.PULL_DOWN)]
            machine.pin_sleep_wakeup(broches, machine.WAKEUP_ANY_HIGH, True)
        py.setup_sleep(duree_max_s)
        py.go_to_sleep(gps=True, pycom_module_off=False,
                       accelerometer_off=not reveil_mouvement,
                       wake_interrupt=reveil_mouvement)
        machine.deepsleep(duree_max_s * 1000)
    else:
        # Le coprocesseur coupe l'alimentation du module et surveille la
        # broche INT de l'accelerometre (front montant = activite).
        py.setup_int_wake_up(reveil_mouvement, False)
        py.setup_sleep(duree_max_s)
        py.go_to_sleep(gps=True)

    # Jamais atteint si tout va bien
    print("[veille] ERREUR : la carte ne s'est pas endormie")


def calibrer(py, duree_s=30):
    """
    Affiche l'acceleration mesuree deux fois par seconde. A lancer dans la
    voiture (ou en bougeant la carte) pour choisir SEUIL_MG :

        import main_gnss, veille
        veille.calibrer(main_gnss.py)

    Ctrl+C pour sortir.
    """
    acc = _acc if _acc is not None else LIS2HH12(py)
    fin = time.time() + duree_s
    while time.time() < fin:
        x, y, z = acc.acceleration()
        print("x={:+.3f} g  y={:+.3f} g  z={:+.3f} g".format(x, y, z))
        time.sleep_ms(500)
