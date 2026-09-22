# Phase B — Acquisition GNSS (etape 1, premiere moitie)

Objectif : obtenir une position valide du recepteur GNSS de la Pytrack et
l'afficher dans la console. Aucun reseau a ce stade.

Livrable : la fonction `get_position()` de `main_gnss.py`, qui renvoie
`(lat, lon)` ou `None`.


## 1. Montage

Poser le module FiPy sur la carte Pytrack. La LED RGB du module se place
du cote du connecteur USB — verifiez la serigraphie imprimee sur la carte.

Brancher le cable USB sur la Pytrack, pas sur le module.

L'antenne LoRa n'est pas necessaire en phase B puisqu'on n'emet pas.
Prenez quand meme l'habitude de la visser avant toute mise sous tension :
emettre sans antenne detruit l'etage radio, et ce sera indispensable des
l'etape 3.

A la mise sous tension, la LED du module doit clignoter en bleu.


## 2. Connexion depuis VS Code

Installer l'extension **Pymakr**. Elle a besoin de **Node.js** sur le
poste : sans lui elle ne demarre pas, et sans message d'erreur clair.

Reperer le port serie de la carte, puis le renseigner dans `pymakr.conf`
a la racine du depot :

- Windows : `COM3`, `COM4`, ...
- Linux : `/dev/ttyACM0` ou `/dev/ttyUSB0`
- macOS : `/dev/tty.usbmodem*`

Sous Linux, si l'acces au port est refuse :

    sudo usermod -a -G dialout $USER

puis se deconnecter et se reconnecter.

Verifier la liaison dans le REPL Pymakr :

    import os
    print(os.uname())

Vous devez voir le nom du module et la version du firmware.


## 3. Bibliotheques

Telecharger `L76GNSS.py` et `pycoproc_1.py` dans le dossier `lib/`.
La procedure complete est dans `lib/README.md`.


## 4. Envoi et execution

Dans Pymakr, bouton **Upload** : le contenu de `end-device/` part vers
`/flash/` sur le module.

Le script ne se lance pas seul tant qu'il s'appelle `main_gnss.py`. Pour
le demarrer a la main dans le REPL :

    import main_gnss
    main_gnss.main()

C'est volontaire : en phase B on veut garder la main sur la carte. Le
renommage en `main.py`, qui declenche le demarrage automatique, n'aura
lieu qu'en phase D.


## 5. Lecture du resultat

Le script affiche une ligne toutes les 2 secondes et pilote la LED :

- LED orange et `pas de fix (N s ecoulees)` : le recepteur cherche encore
- LED verte et `lat = 48.07940   lon = 7.35850` : position valide

Le compteur de secondes permet de savoir si la recherche progresse ou si
la carte est simplement mal placee.

Au premier fix, le script affiche le temps qu'il a fallu. Notez-le, c'est
une bonne illustration du TTFF (Time To First Fix) si le correcteur pose
la question.


## 6. Validation de la phase B

La phase B est terminee quand vous obtenez une latitude proche de `48.07`
et une longitude proche de `7.35` pour Colmar, stables sur plusieurs
lectures consecutives.

Prevenez alors la phase C : la carte est libre, et `get_position()` est
prete a etre branchee sur la publication MQTT.


## Problemes frequents

**Aucun fix apres 20 minutes.**
Le recepteur a besoin de voir le ciel. Derriere une vitre cela fonctionne
mais lentement, en plein milieu d'une salle de TP jamais. Sortez, ou
collez la carte contre une fenetre. Le premier demarrage est toujours le
plus long car l'almanach des satellites est vide.

**`ImportError: no module named 'L76GNSS'`.**
Les libs ne sont pas dans `/flash/lib`. Verifiez avec
`print(os.listdir('/flash/lib'))`.

**`coordinates()` renvoie toujours `(None, None)` alors que la LED du GPS
clignote.**
Le clignotement signale que le recepteur est alimente, pas qu'il a accroche
les satellites. Il faut au minimum 4 satellites pour un fix. Patientez.

**La carte ne repond plus dans le REPL.**
`Ctrl+C` interrompt la boucle. Si rien ne repond, debranchez et rebranchez.

**Coordonnees aberrantes, du genre 4804.764.**
C'est du format NMEA brut, en degres-minutes. La lib `L76GNSS` fait
normalement la conversion en degres decimaux. Si vous voyez ces valeurs,
vous avez une version differente de la lib : divisez la partie minutes par
60 avant de renvoyer le resultat, et signalez-le au groupe pour mise a
jour du contrat d'interface.
