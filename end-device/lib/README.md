# Bibliotheques a deposer ici

Ce dossier est envoye dans `/flash/lib/` sur le module par Pymakr.

Les deux fichiers ci-dessous sont fournis par Pycom. Ils ne sont pas
versionnes dans ce depot : chacun les telecharge une fois, ils ne changent
jamais ensuite.

## Les deux fichiers, avec leur chemin exact

Depot officiel : https://github.com/pycom/pycom-libraries

Les deux se trouvent dans le dossier `shields/lib/`.

- `L76GNSS.py`
  https://raw.githubusercontent.com/pycom/pycom-libraries/master/shields/lib/L76GNSS.py
  Role : dialogue en I2C avec le recepteur GNSS Quectel L76, decode les
  trames NMEA et expose la methode `coordinates()`.

- `pycoproc_1.py`
  https://raw.githubusercontent.com/pycom/pycom-libraries/master/shields/lib/pycoproc_1.py
  Role : pilote le coprocesseur PIC de la carte Pytrack, qui gere
  l'alimentation du GNSS, l'accelerometre et les modes basse consommation.

Sur la page GitHub d'un fichier, le bouton **Raw** donne le contenu brut,
puis clic droit et Enregistrer sous. Verifiez que le fichier enregistre
porte bien l'extension `.py` et non `.txt`.

## Quelle version du coprocesseur

- `pycoproc_1.py` — cartes Pytrack et Pysense **v1**
- `pycoproc_2.py` — cartes **v2**

Les deux sont dans `shields/lib/`. En cas de doute prenez `pycoproc_1.py` :
c'est la version des cartes en salle de TP. `main_gnss.py` essaie les deux
noms a l'import, il n'y a rien a modifier dans le code selon celui que vous
avez depose.

## Verification

Une fois les fichiers envoyes, dans le REPL :

    import os
    print(os.listdir('/flash/lib'))

Vous devez voir :

    ['L76GNSS.py', 'pycoproc_1.py']

Si la liste est vide, l'upload Pymakr n'a pas eu lieu ou `sync_folder` ne
pointe pas sur `end-device`. Le fichier `README.md` de ce dossier n'est pas
envoye sur la carte : l'extension `md` n'est pas dans `sync_file_types` de
`pymakr.conf`, c'est voulu, la carte n'a que 4 Mo de flash.

## API utilisee par main_gnss.py

Pour information, verifie dans le code source des libs :

- `Pycoproc(Pycoproc.PYTRACK)` — la constante `PYTRACK` vaut 2
- `L76GNSS(py, timeout=10)` — `timeout` est la duree maximale d'une lecture
- `gnss.coordinates()` renvoie un tuple `(latitude, longitude)` en
  **degres decimaux**, ou `(None, None)` si le timeout expire sans fix.
  La conversion depuis le format NMEA degres-minutes est faite par la lib,
  il n'y a rien a recalculer.
- `gnss.dump_nmea()` affiche les trames brutes, utile pour verifier que le
  recepteur repond quand aucun fix n'arrive.
