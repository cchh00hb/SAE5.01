# Bibliotheques du End-Device

Ce dossier est envoye dans `/flash/lib/` sur le module par Pymakr.

Toutes les bibliotheques sont **versionnees dans ce depot**. Il n'y a rien a
telecharger : un `git clone` suffit, et tout le groupe travaille sur les
memes versions. C'etait la source de la plupart de nos pannes de mise au
point, chacun pouvant avoir une variante differente sans le savoir.

## Contenu

Fournies par Pycom, depuis `shields/lib/` du depot
https://github.com/pycom/pycom-libraries (version `75d0e67`) :

- `L76GNSS.py`
  Dialogue en I2C avec le recepteur GNSS Quectel L76, decode les trames
  NMEA et expose `coordinates()` et `dump_nmea()`.

- `pycoproc_1.py`
  Pilote le coprocesseur PIC des cartes Pytrack et Pysense **v1**, celles
  de la salle de TP : alimentation du GNSS, accelerometre, modes basse
  consommation.

- `pycoproc_2.py`
  Meme role pour les cartes **v2**. Conservee parce que `main_gnss.py` et
  `veille.py` essaient les deux noms a l'import : le code s'adapte tout
  seul a la carte presente, il n'y a rien a modifier.

- `LIS2HH12.py`
  Accelerometre de la Pytrack. Utilisee par `veille.py` pour le reveil sur
  mouvement (etape 9).

Ecrite pour MicroPython, reprise du projet micropython-lib :

- `mqtt.py`
  Client MQTT minimal (`umqtt.simple`). Utilisee par `main_gnss.py` pour
  publier la position.

Ces fichiers sont du code tiers : ne les modifiez pas. Si un correctif est
necessaire, faites-le dans notre code, pas dans la lib, sinon la prochaine
mise a jour l'effacera.

## Verification apres upload

Dans le REPL :

    import os
    print(os.listdir('/flash/lib'))

Vous devez voir les cinq fichiers `.py`. Si la liste est vide, la
synchronisation Pymakr n'a pas eu lieu, ou le projet selectionne n'est pas
`end-device`.

Le `README.md` de ce dossier ne monte pas sur la carte : l'extension `md`
n'est pas dans `sync_file_types` de `pymakr.conf`. C'est voulu, le module
n'a que 4 Mo de flash.

## API utilisee par notre code

Verifie dans le code source des libs :

- `Pycoproc(Pycoproc.PYTRACK)` — la constante `PYTRACK` vaut 2
- `L76GNSS(py, timeout=10)` — duree maximale d'une lecture
- `gnss.coordinates()` renvoie `(latitude, longitude)` en **degres
  decimaux**, ou `(None, None)` si le timeout expire sans fix. La
  conversion depuis le NMEA degres-minutes est faite par la lib.
- `gnss.dump_nmea()` affiche les trames brutes, utile quand aucun fix
  n'arrive : il distingue un recepteur muet d'un recepteur qui cherche
  encore ses satellites.
- `LIS2HH12(py).enable_activity_interrupt(seuil_mg, duree_ms, handler)`
  renvoie le seuil et la duree reellement appliques, arrondis aux pas du
  capteur.

## Licence

Les fichiers Pycom sont distribues sous GNU GPL v3. Leurs en-tetes de
licence sont conserves tels quels.
