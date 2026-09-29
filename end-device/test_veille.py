"""
SAE5.01 - Etape 9 - Demonstration autonome du cycle veille / reveil.

Ne fait pas de LoRaWAN : sert a valider le mecanisme avant l'integration
dans le main.py de la phase D. Reutilise get_position() de main_gnss.py.

Cycle demontre :
  1. la carte dort (LED eteinte) ;
  2. on la secoue -> elle se reveille (LED violette), cherche le GNSS ;
  3. apres INACTIVITE_S secondes sans mouvement -> elle se rendort ;
  4. si c'est le minuteur de securite qui l'a reveillee -> elle se rendort.

Lancement : voir README_etape9.md (il faut un main.py sur la carte, car
apres un deep sleep le module redemarre et n'execute que boot.py/main.py).
"""

import time
import pycom

import main_gnss                   # cree py et gnss, allume le GNSS
import veille

INACTIVITE_S = 60      # court pour la demo ; en vrai plutot 5 a 10 minutes
FENETRE_CTRL_C_S = 10  # delai au demarrage pour reprendre la main au REPL

LED_REVEIL_MOUVEMENT = 0x3F003F   # violet
LED_DEMARRAGE = 0x00003F          # bleu


def main():
    py = main_gnss.py
    reveil = time.time()
    raison = veille.init(py)

    if raison == veille.RAISON_TIMER:
        # Rien ne bouge : on pourrait envoyer ici un uplink "je suis vivant".
        veille.dormir(py)

    if raison == veille.RAISON_DEMARRAGE:
        # Mise sous tension ou reset : on laisse le temps de faire Ctrl+C,
        # sinon la carte s'endort et Pymakr ne peut plus s'y connecter.
        pycom.rgbled(LED_DEMARRAGE)
        print("Demarrage : Ctrl+C dans les {} s pour garder la main".format(
            FENETRE_CTRL_C_S))
        time.sleep(FENETRE_CTRL_C_S)
    else:
        pycom.rgbled(LED_REVEIL_MOUVEMENT)

    premier_fix = None
    while True:
        if veille.inactif_depuis() >= INACTIVITE_S:
            print("Aucun mouvement depuis {} s".format(INACTIVITE_S))
            veille.dormir(py)                 # plus tard : dormir(py, lora)

        position = main_gnss.get_position()   # bloque jusqu'a 10 s
        depuis = int(time.time() - reveil)
        mouvement = veille.en_mouvement()

        if position is None:
            pycom.rgbled(main_gnss.LED_RECHERCHE)
            print("t={:3d} s  pas de fix   mouvement={}".format(
                depuis, mouvement))
        else:
            if premier_fix is None:
                premier_fix = depuis
                print("--- fix obtenu {} s apres le reveil ---".format(depuis))
            pycom.rgbled(main_gnss.LED_FIX)
            print("t={:3d} s  lat={:.5f} lon={:.5f}  mouvement={}".format(
                depuis, position[0], position[1], mouvement))

        time.sleep(main_gnss.PERIODE_LECTURE)
