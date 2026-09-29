# Etape 9 — Reveil par accelerometre et deep sleep (validation 6)

Objectif : par defaut le End-Device dort. Il ne se reveille, n'allume le
GNSS et n'emet en LoRaWAN que lorsque le vehicule bouge, grace a
l'interruption d'activite de l'accelerometre LIS2HH12 de la Pytrack.

Livrable : le module `veille.py`, appele par le `main.py` de la phase D.
`test_veille.py` sert a demontrer le cycle seul, sans LoRaWAN.


## 1. Principe

    deep sleep  --(mouvement)-->  reveil = redemarrage complet
         ^                              |
         |                        veille.init(py) : raison du reveil
         |                        GNSS + uplinks LoRaWAN
         |                              |
         +---- veille.dormir(py, lora) <-+  inactivite prolongee
                                            ou downlink 0x00 (etape 10)

Deux differences selon la carte, gerees automatiquement par `veille.py` :

- **Pytrack v1** (salle de TP) : le coprocesseur PIC coupe l'alimentation du
  module. C'est le PIC qui surveille l'accelerometre et memorise la cause
  du reveil (`py.get_wake_reason()`).
- **Pytrack v2** : le module reste en deep sleep ESP32 et se reveille sur la
  broche P13 reliee a l'accelerometre (`machine.wake_reason()`).

Dans les deux cas le GNSS reste en alimentation de secours pendant la
veille (`go_to_sleep(gps=True)`) : il garde les ephemerides et refait un
fix en quelques secondes au reveil (hot start), au lieu des 5 a 15 minutes
du premier demarrage. `test_veille.py` affiche ce temps : bon argument
pour l'oral.


## 2. Bibliotheque supplementaire

Telecharger `LIS2HH12.py` dans `end-device/lib/`, meme procedure que pour
les autres (voir `lib/README.md`) :

https://raw.githubusercontent.com/pycom/pycom-libraries/master/shields/lib/LIS2HH12.py

Comme les autres libs Pycom, elle n'est pas versionnee : ligne ajoutee
dans `.gitignore`.


## 3. Tester la demo seule

1. Pymakr, bouton **Upload**.
2. Apres un deep sleep le module redemarre et n'execute que `boot.py` puis
   `main.py`. Le vrai `main.py` n'arrive qu'en phase D, donc on en cree un
   **temporaire, directement sur la carte** (rien dans le depot) :

        f = open('/flash/main.py', 'w')
        f.write('import test_veille\ntest_veille.main()\n')
        f.close()

3. `Ctrl+D`. LED bleue pendant 10 s (fenetre pour faire `Ctrl+C`), puis
   recherche GNSS.
4. Laisser la carte immobile 60 s : LED eteinte, la carte dort.
   Pymakr perd la liaison, c'est normal.
5. Secouer franchement la carte : LED violette, elle repart. La console
   affiche `reveil : mouvement` puis le temps du fix.

Pour mesurer le gain de consommation, alimenter la carte sur batterie.
Ordres de grandeur donnes par Pycom pour la v2 : environ 165 µA en veille
avec l'accelerometre actif, contre plusieurs dizaines de mA eveille avec
GNSS et radio.

Supprimer le `main.py` temporaire une fois fini :

    import os
    os.remove('/flash/main.py')

**Reprendre la main si la carte dort :** la secouer pour la reveiller,
reconnecter Pymakr et faire `Ctrl+C` pendant la minute d'eveil.

**Regler le seuil :** `SEUIL_MG` vaut 2000 mg (valeur des exemples Pycom,
il faut secouer fort). Pour une voiture, mesurer avec :

    import main_gnss, veille
    veille.calibrer(main_gnss.py)


## 4. Integration dans le main.py (phase D)

A appeler par le pole qui ecrit le `main.py` final :

    import main_gnss, veille
    py = main_gnss.py                        # on partage le coprocesseur

    raison = veille.init(py)                 # tout au debut
    if raison == veille.RAISON_TIMER:
        veille.dormir(py, lora)              # rien ne bouge, on redort

    # ... join LoRaWAN, boucle d'envoi ...
    flags_moving = 1 if veille.en_mouvement() else 0   # bit 0, INTERFACE 4.3

    if veille.inactif_depuis() > 600:        # 10 min sans mouvement
        veille.dormir(py, lora)

Points a coordonner :

- **Pole LoRa (etape 3)** : `dormir(py, lora)` fait `lora.nvram_save()`.
  Au demarrage il faut appeler `lora.nvram_restore()` avant de tester
  `lora.has_joined()`. Sinon un join OTAA a chaque reveil : lent et
  couteux en temps d'antenne (duty cycle 1 %).
- **Pole downlink (etape 10)** : a la reception de `0x00` (SLEEP), appeler
  `veille.dormir(py, lora)`. Si la voiture roule encore a ce moment, elle
  se reveillera a la prochaine acceleration. Pour couper vraiment le suivi,
  `veille.dormir(py, lora, reveil_mouvement=False)` : reveil par minuteur
  seul. A trancher en groupe.
- **boot.py** : la boucle `while not wlan.isconnected()` n'a pas de delai
  maximal. Dans la voiture, sans WiFi, la carte resterait bloquee a chaque
  reveil. A partir de l'etape 3 le WiFi n'est plus utile au End-Device :
  le supprimer de `boot.py`, ou au minimum ajouter un timeout.
