# Bibliotheques a deposer ici

Ce dossier est envoye dans `/flash/lib/` sur le module par Pymakr.

Les deux fichiers ci-dessous sont fournis par Pycom. Ils ne sont pas
versionnes dans ce depot : chacun les telecharge une fois, ils ne changent
jamais ensuite.

## Ou les recuperer

Depot officiel : https://github.com/pycom/pycom-libraries

- `L76GNSS.py`
  Chemin dans le depot : `pytrack/lib/L76GNSS.py`
  Role : dialogue avec le recepteur GNSS Quectel L76, decode les trames
  NMEA et expose la methode `coordinates()`.

- `pycoproc_1.py`
  Chemin dans le depot : `pycoproc/pycoproc_1.py`
  Role : pilote le coprocesseur de la carte Pytrack, qui gere
  l'alimentation du GNSS, l'accelerometre et les modes basse consommation.

## Variantes possibles

Selon l'age de la carte et de la bibliotheque, le fichier du coprocesseur
peut s'appeler autrement :

- `pycoproc_1.py` — cartes Pytrack et Pysense v1
- `pycoproc_2.py` — cartes v2
- `pycoproc.py` — ancienne bibliotheque unifiee
- `pytrack.py` — version historique, classe `Pytrack`

`main_gnss.py` essaie ces variantes dans l'ordre, il n'y a donc rien a
modifier dans le code. Deposez simplement le fichier que vous avez.

## Verification

Une fois les fichiers envoyes, dans le REPL :

    import os
    print(os.listdir('/flash/lib'))

Vous devez voir `L76GNSS.py` et le fichier du coprocesseur.
