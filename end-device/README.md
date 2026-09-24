# Phase B — Acquisition GNSS (etape 1, premiere moitie)

Objectif : obtenir une position valide du recepteur GNSS de la Pytrack et
l'afficher dans la console. Aucun reseau a ce stade.

Livrable : la fonction `get_position()` de `main_gnss.py`, qui renvoie
`(lat, lon)` ou `None`.


## 1. Montage

Poser le module LoPy4 ou FiPy sur la carte Pytrack. La LED RGB du module
se place du cote du connecteur USB — verifiez la serigraphie imprimee sur
la carte.

Les deux modules conviennent pour ce projet. La LoPy4 a le WiFi et le LoRa,
c'est tout ce dont on a besoin. Elle n'a pas le modem cellulaire de la FiPy,
mais les etapes qui l'utilisaient sont hors sujet.

Brancher le cable USB sur la Pytrack, pas sur le module.

L'antenne LoRa n'est pas necessaire en phase B puisqu'on n'emet pas.
Prenez quand meme l'habitude de la visser avant toute mise sous tension :
emettre sans antenne detruit l'etage radio, et ce sera indispensable des
l'etape 3.

A la mise sous tension, la LED du module doit clignoter en bleu.


## 2. Connexion depuis VS Code

Installer l'extension **Pymakr**. Elle a besoin de **Node.js** sur le
poste : sans lui elle ne demarre pas, et sans message d'erreur clair.

Reperer le port serie de la carte :

- Windows : `COM3`, `COM4`, ...
- Linux : `/dev/ttyACM0` ou `/dev/ttyUSB0`
- macOS : `/dev/tty.usbmodem*`

Sous Linux, si l'acces au port est refuse :

    sudo usermod -a -G dialout $USER

puis se deconnecter et se reconnecter.

Verifier la liaison dans le REPL Pymakr :

    import os
    print(os.uname())

Vous devez voir le nom du module et la version du firmware, par exemple :

    (sysname='LoPy4', nodename='LoPy4', release='1.20.2.r6', ...)


## 2 bis. Desactiver Pybytes

Si la banniere de demarrage affiche une ligne `Pybytes Version`, le service
cloud de Pycom est actif sur la carte. Il tente de prendre le WiFi et le
LoRa au demarrage et entre en conflit avec notre code, aux etapes 1 et 3.

A desactiver une fois pour toutes :

    import pycom
    pycom.pybytes_on_boot(False)

Puis `Ctrl+D` pour redemarrer. La ligne `Pybytes Version` doit avoir
disparu de la banniere.

Symptomes si vous oubliez : le WiFi se connecte a un reseau que vous n'avez
pas choisi, ou le join LoRaWAN de l'etape 3 echoue sans message clair.


## 3. Bibliotheques

Telecharger `L76GNSS.py` et `pycoproc_1.py` dans le dossier `lib/`.
La procedure complete est dans `lib/README.md`.


## 4. Envoi et execution

Le fichier `pymakr.conf` est place dans `end-device/`, et non a la racine
du depot. C'est volontaire : pour Pymakr 2.x, le projet est le dossier qui
contient `pymakr.conf`, et son contenu est copie tel quel dans `/flash/`.

Si vous ajoutez le projet depuis la racine `SAE5.01`, Pymakr envoie tout le
depot sur la carte : vous vous retrouvez avec `/flash/end-device/lib/` au
lieu de `/flash/lib/`, et les imports echouent. Dans la section **Projects**
de Pymakr, le projet a selectionner est donc `end-device`.

Puis **ADD DEVICES**, choisir le port de la carte, et lancer la
synchronisation avec la fleche vers le haut.

Recuperer d'abord le contenu de la carte avec la fleche vers le bas : le
bouton de synchronisation ecrase les fichiers de meme nom, et un programme
peut deja etre present sur le module.

## 4 bis. Rattraper une synchronisation partie de la racine

Si les libs se retrouvent dans `/flash/end-device/lib/`, pas besoin de tout
recommencer. Copiez-les au bon endroit depuis le REPL :

    open('/flash/lib/L76GNSS.py','wb').write(open('/flash/end-device/lib/L76GNSS.py','rb').read())
    open('/flash/lib/pycoproc_1.py','wb').write(open('/flash/end-device/lib/pycoproc_1.py','rb').read())

Chaque ligne affiche le nombre d'octets ecrits : 4126 puis 10622.

Pour faire le menage ensuite, `uos.remove()` supprime un fichier et
`uos.rmdir()` un dossier vide.

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

**Verifier que le recepteur est vivant.**
Si aucun fix n'arrive et que vous doutez du cablage, affichez les trames
brutes depuis le REPL :

    import main_gnss
    main_gnss.debug_nmea()

Des lignes `$GNGGA`, `$GNGLL`, `$GPGSV` doivent defiler. Dans ce cas le
recepteur fonctionne et il cherche seulement les satellites : le champ qui
suit l'heure dans `$GNGGA` vaut 0 tant qu'il n'y a pas de fix.

Si rien ne s'affiche, le probleme est materiel : module mal enfonce sur la
Pytrack, ou carte d'extension qui n'est pas une Pytrack.

`Ctrl+C` pour sortir.

**Sauvegarder ce qui est deja sur la carte.**
Le bouton Upload de Pymakr ecrase les fichiers de meme nom. Si un programme
a ete laisse sur la carte par quelqu'un d'autre, recuperez-le d'abord avec
le bouton **Download** de Pymakr, qui rapatrie tout le contenu de `/flash`.

Pour voir ce qu'il y a dessus :

    import os
    print(os.listdir('/flash'))
