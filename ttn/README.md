# Formateurs de charge utile TTN

Ces fichiers ne partent pas sur la carte. Ils se collent dans la console
The Things Network, rubrique **Payload formatters** de l'application.

## `decodeur_uplink.js`

Onglet **Uplink**, type *Custom Javascript formatter*.

Decode les 7 octets envoyes par `encoder_position()` de
`end-device/main_ttn.py` : latitude et longitude sur 3 octets chacune, plus
un octet de flags. Voir `INTERFACE.md` section 4.

Il expose les coordonnees sous deux jeux de noms :

- `lat` et `lon`, ceux du contrat d'interface, utilises par le flow
  Node-RED de l'etape 2 ;
- `latitude` et `longitude`, lus par `end-device/mqtt_ttn.py`.

C'est un doublon assume : il evite d'avoir a modifier l'un ou l'autre des
deux consommateurs.

## Verifier sans carte

La console TTN permet de tester un formateur sans attendre un vrai uplink.
Sous l'editeur, champ **Test**, coller en hexadecimal :

    07 56 1A 01 1F 71 03

Resultat attendu :

    lat    48.0794
    lon    7.3585
    moving true
    fix    true

C'est la position de Colmar, celle qui sert de reference dans tout le
projet.

## Descendant

Le formateur **Downlink** de l'etape 10 reste a ecrire. Sa structure est
decrite dans `INTERFACE.md` section 5 : un seul octet, `0x00` pour la mise
en veille, `0x01` pour le reveil.
