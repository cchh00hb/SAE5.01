# Contrat d'interface — SAE5.01 Tracage de vehicule par GNSS

Ce document fige le format des donnees echangees entre les trois poles du projet :
End-Device embarque, TTN/LoRaWAN, serveur Node-RED.

A lire avant d'ecrire la moindre ligne de code, et a respecter au caractere pres.
Toute modification suit la procedure decrite en section 7.

Version : 1.1 — derniere mise a jour : 2026-09-22


---

## 1. Parametres communs

A completer en debut de projet, puis ne plus y toucher.

- **Identifiant de groupe** : `groupeX`
  A remplacer partout dans ce fichier et dans le code.

- **IP fixe du Raspberry Pi** : `192.168.X.X`
  Responsable : pole Node-RED.

- **Broker MQTT local** : Mosquitto sur le RPi, port `1883`
  Responsable : pole TTN 2.

- **Nom de l'application TTN** : `sae501-groupeX`
  Responsable : pole TTN 1.

- **Device ID TTN** : `end-device-groupeX`
  Responsable : pole TTN 1.

Convention de nommage generale : minuscules, sans accent, separateur `-` ou `/`.


---

## 2. Topics MQTT

### 2.1 Liaison directe WiFi (etapes 1 et 2)

Le End-Device publie directement sur le broker Mosquitto du RPi.

Topic montant :

    sae501/groupeX/position

- Publie par : le End-Device
- Consomme par : Node-RED et MQTT Box

### 2.2 Liaison LoRaWAN via TTN (etapes 6, 7, 10, 11)

Node-RED se connecte au broker MQTT fourni par TTN, onglet `Integrations > MQTT`.

Topic montant :

    v3/sae501-groupeX@ttn/devices/end-device-groupeX/up

- Publie par : TTN
- Consomme par : Node-RED

Topic descendant :

    v3/sae501-groupeX@ttn/devices/end-device-groupeX/down/push

- Publie par : Node-RED
- Consomme par : TTN, qui transmet au End-Device

Le nom du tenant est `ttn` pour un compte The Things Network communautaire.
Il est visible en clair dans l'onglet `Integrations > MQTT` de l'application.


---

## 3. Payload JSON — liaison WiFi (etapes 1 et 2)

Message publie sur `sae501/groupeX/position` :

```json
{
  "lat": 48.0794,
  "lon": 7.3585,
  "alt": 200,
  "ts": 1234567890
}
```

Description des champs :

- `lat` — nombre, degres decimaux, **obligatoire**
  Positif vers le Nord.

- `lon` — nombre, degres decimaux, **obligatoire**
  Positif vers l'Est.

- `alt` — nombre entier, metres, optionnel
  Mettre `0` si l'altitude n'est pas disponible.

- `ts` — nombre entier, secondes Unix, optionnel
  Horloge du End-Device.

Regles imperatives :

- Les valeurs sont des **nombres JSON**, jamais des chaines.
  Ecrire `48.0794` et non `"48.0794"`.

- Le format est le **degre decimal**, pas le format NMEA brut (`4804.764,N`).
  La conversion est faite cote End-Device.

- En l'absence de fix GNSS, **aucun message n'est publie**.
  Pas de `null`, pas de `0.0`, pas de message vide.


---

## 4. Payload binaire LoRa — trame montante (etape 8)

La couche physique LoRa impose de reduire la taille utile.
Latitude et longitude sont codees sur 3 octets chacune.

### 4.1 Structure de la trame — 7 octets

- Octets 0 a 2 : **latitude**
  Entier signe, big-endian, complement a 2.

- Octets 3 a 5 : **longitude**
  Entier signe, big-endian, complement a 2.

- Octet 6 : **flags**
  Voir section 4.3.

### 4.2 Facteur d'echelle

    valeur_entiere = round(degres * 10000)
    degres         = valeur_entiere / 10000

Verification des plages :

- Latitude : -90 a +90 degres, soit -900 000 a +900 000 en entier.
- Longitude : -180 a +180 degres, soit -1 800 000 a +1 800 000 en entier.
- Capacite d'un entier signe sur 3 octets : -8 388 608 a +8 388 607.

Les deux tiennent largement. Resolution obtenue : `0.0001` degre,
soit environ **11 metres**. Suffisant pour un suivi de vehicule.

Attention : ne pas utiliser un facteur `100000`. La latitude atteindrait
9 000 000 et **deborderait** la capacite de 3 octets signes.

### 4.3 Octet de flags (offset 6)

- Bit 0 — `moving` : 1 = vehicule en mouvement (interruption accelerometre)
- Bit 1 — `fix` : 1 = fix GNSS valide
- Bits 2 a 7 — reserves, mis a 0

### 4.4 Encodage cote End-Device (MicroPython)

```python
import struct

def encode_position(lat, lon, moving=1, fix=1):
    lat_i = round(lat * 10000)
    lon_i = round(lon * 10000)
    flags = (fix << 1) | moving
    return (
        struct.pack('>i', lat_i)[1:] +   # on retire l'octet de poids fort
        struct.pack('>i', lon_i)[1:] +
        bytes([flags])
    )
```

### 4.5 Decodage cote TTN (Payload formatters > Uplink)

```javascript
function decodeUplink(input) {
  var b = input.bytes;

  function toInt24(hi, mid, lo) {
    var v = (hi << 16) | (mid << 8) | lo;
    if (v & 0x800000) { v -= 0x1000000; }   // complement a 2
    return v;
  }

  var lat   = toInt24(b[0], b[1], b[2]) / 10000;
  var lon   = toInt24(b[3], b[4], b[5]) / 10000;
  var flags = b[6];

  return {
    data: {
      lat: lat,
      lon: lon,
      moving: (flags & 0x01) !== 0,
      fix:    (flags & 0x02) !== 0
    }
  };
}
```

Point important : le champ `data` produit ici porte les memes noms `lat` et `lon`
que le JSON de la section 3. C'est volontaire. Cela permet au flow Node-RED ecrit
pour l'etape 2 de fonctionner a l'identique a l'etape 7, quand les donnees
arriveront par LoRaWAN au lieu du WiFi. Aucune reecriture necessaire.


---

## 5. Payload binaire LoRa — trame descendante (etapes 10 et 11)

Commande envoyee depuis la page web vers le End-Device. Un seul octet.

- `0x00` — `SLEEP` : passage en mode faible consommation (deep sleep)
- `0x01` — `WAKE` : reprise du suivi, reactivation GNSS et LoRaWAN

Parametres d'envoi :

- Port LoRaWAN (`f_port`) : `1`
- Priorite : `NORMAL`
- Mode : non confirme, `confirmed: false`

Encodage cote TTN (Payload formatters > Downlink) :

```javascript
function encodeDownlink(input) {
  return {
    bytes:    [input.data.cmd === "sleep" ? 0x00 : 0x01],
    fPort:    1,
    warnings: []
  };
}
```

A savoir : un downlink n'est transmis qu'**apres un uplink** du End-Device,
car celui-ci est en classe A. Le delai peut donc atteindre plusieurs minutes.
Ce n'est pas un bug, ne cherchez pas.


---

## 6. Format attendu par Node-RED (worldmap)

Le noeud `worldmap` n'accepte pas le JSON des sections 3 et 4 tel quel.
Un noeud `function` fait la conversion :

```javascript
msg.payload = {
    name:      "Vehicule groupeX",
    lat:       msg.payload.lat,
    lon:       msg.payload.lon,
    icon:      "car",
    iconColor: msg.payload.moving ? "red" : "gray"
};
return msg;
```

Carte accessible sur :

    http://<ip-rpi>:1880/worldmap


---

## 7. Contrainte de duty cycle

A respecter dans tout code d'emission.

La reglementation EU868 impose un duty cycle de **1 %** : apres chaque emission,
le End-Device doit rester silencieux pendant **99 fois** la duree de cette emission.

    temps_attente = temps_emission * 99

Ordres de grandeur pour une trame de 7 octets :

- SF7 : environ 50 ms d'emission, donc environ 5 s d'attente
- SF9 : environ 185 ms d'emission, donc environ 18 s d'attente
- SF12 : environ 1 400 ms d'emission, donc environ 2 min 20 s d'attente

A verifier avant d'ecrire la boucle d'envoi :
https://avbentem.github.io/airtime-calculator/ttn/eu868

La pile LoRa du module bloque d'elle-meme les emissions trop rapprochees.
Un `send()` qui semble ne rien faire vient presque toujours de la.


---

## 8. Procedure de modification

Ce contrat est partage. Le modifier unilateralement casse le travail des autres poles.

1. Annoncer le changement au groupe **avant** de coder.
2. Mettre a jour ce fichier et incrementer le numero de version.
3. Commiter le fichier **seul**, avec un message `interface: <description>`.
4. Prevenir les poles impactes.

Journal des versions :

- **1.1** — 2026-09-22 — Suppression des tableaux, passage en listes pour la
  lisibilite dans l'editeur VS Code. Contenu technique inchange.

- **1.0** — 2026-09-22 — Creation. Topics MQTT, payload JSON, trame montante
  sur 7 octets, trame descendante, format worldmap, duty cycle.
