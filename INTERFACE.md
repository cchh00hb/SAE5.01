# Contrat d'interface — SAE5.01 Traçage de véhicule par GNSS

Ce document fige le **format des données échangées** entre les trois pôles du projet
(End-Device embarqué, TTN/LoRaWAN, serveur Node-RED).

Il doit être lu avant d'écrire la moindre ligne de code, et respecté au caractère près.
Toute modification suit la procédure décrite en fin de document.

**Version : 1.0 — dernière mise à jour : 2026-09-22**

---

## 0. Paramètres communs

| Élément | Valeur | À compléter par |
|---|---|---|
| Identifiant de groupe | `groupeX` | tous — remplacer `X` partout |
| IP fixe du Raspberry Pi | `192.168.X.X` | pôle Node-RED |
| Broker MQTT local | `mosquitto` sur le RPi, port `1883` | pôle TTN 2 |
| Application TTN | `sae501-groupeX` | pôle TTN 1 |
| Device ID TTN | `end-device-groupeX` | pôle TTN 1 |

Convention de nommage générale : **minuscules, sans accent, séparateur `-` ou `/`**.

---

## 1. Topics MQTT

### 1.1 Liaison directe WiFi (étapes 1 et 2)

Le End-Device publie directement sur le broker Mosquitto du RPi.

| Sens | Topic | Publié par | Consommé par |
|---|---|---|---|
| Montant | `sae501/groupeX/position` | End-Device | Node-RED, MQTT Box |

### 1.2 Liaison LoRaWAN via TTN (étapes 6, 7, 10, 11)

Node-RED se connecte au broker MQTT fourni par TTN (`Integrations > MQTT`).

| Sens | Topic | Publié par | Consommé par |
|---|---|---|---|
| Montant | `v3/sae501-groupeX@ttn/devices/end-device-groupeX/up` | TTN | Node-RED |
| Descendant | `v3/sae501-groupeX@ttn/devices/end-device-groupeX/down/push` | Node-RED | TTN → End-Device |

> Le nom du tenant est `ttn` pour un compte The Things Network communautaire.
> Il est visible en clair dans l'onglet `Integrations > MQTT` de l'application.

---

## 2. Payload JSON — liaison WiFi (étapes 1 et 2)

Message publié sur `sae501/groupeX/position` :

```json
{
  "lat": 48.0794,
  "lon": 7.3585,
  "alt": 200,
  "ts": 1234567890
}
```

| Champ | Type | Unité | Obligatoire | Remarque |
|---|---|---|---|---|
| `lat` | nombre | degrés décimaux | oui | positif = Nord |
| `lon` | nombre | degrés décimaux | oui | positif = Est |
| `alt` | nombre entier | mètres | non | `0` si indisponible |
| `ts` | nombre entier | secondes Unix | non | horloge du End-Device |

**Règles impératives**

- Les valeurs sont des **nombres JSON**, jamais des chaînes : `48.0794` et non `"48.0794"`.
- Le format est le **degré décimal**, pas le format NMEA (`4804.764,N`).
  La conversion est faite côté End-Device.
- En l'absence de fix GNSS, **aucun message n'est publié**. Pas de `null`, pas de `0.0`.

---

## 3. Payload binaire LoRa — trame montante (étape 8)

Contrainte : la couche physique LoRa impose de réduire la taille utile.
Latitude et longitude sont codées **sur 3 octets chacune**.

### 3.1 Structure — 7 octets

| Offset | Taille | Champ | Encodage |
|---|---|---|---|
| 0 | 3 octets | latitude | entier **signé**, big-endian, complément à 2 |
| 3 | 3 octets | longitude | entier **signé**, big-endian, complément à 2 |
| 6 | 1 octet | flags | voir 3.3 |

### 3.2 Facteur d'échelle

```
valeur_entiere = round(degres * 10000)
degres         = valeur_entiere / 10000
```

| | Plage en degrés | Plage entière | Capacité 3 octets signés |
|---|---|---|---|
| Latitude | -90 à +90 | -900 000 à +900 000 | -8 388 608 à +8 388 607 |
| Longitude | -180 à +180 | -1 800 000 à +1 800 000 | idem |

Résolution obtenue : `0.0001°`, soit environ **11 mètres**. Suffisant pour un suivi de véhicule.

> Ne pas utiliser un facteur `100000` : la latitude atteindrait 9 000 000 et
> **déborderait** la capacité de 3 octets signés.

### 3.3 Octet de flags (offset 6)

| Bit | Nom | Signification |
|---|---|---|
| 0 | `moving` | 1 = véhicule en mouvement (interruption accéléromètre) |
| 1 | `fix` | 1 = fix GNSS valide |
| 2-7 | réservés | mis à 0 |

### 3.4 Encodage — End-Device (MicroPython)

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

### 3.5 Décodage — TTN (Payload formatter > Uplink)

```javascript
function decodeUplink(input) {
  var b = input.bytes;

  function toInt24(hi, mid, lo) {
    var v = (hi << 16) | (mid << 8) | lo;
    if (v & 0x800000) { v -= 0x1000000; }   // complément à 2
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

**Le champ `data` produit ici doit porter les mêmes noms `lat` / `lon` que la section 2.**
C'est ce qui permet au flow Node-RED de fonctionner à l'identique en WiFi et en LoRaWAN.

---

## 4. Payload binaire LoRa — trame descendante (étapes 10 et 11)

Commande envoyée depuis la page web vers le End-Device. **1 octet.**

| Valeur | Nom | Effet sur le End-Device |
|---|---|---|
| `0x00` | `SLEEP` | passage en mode faible consommation (deep sleep) |
| `0x01` | `WAKE` | reprise du suivi, réactivation GNSS + LoRaWAN |

### 4.1 Paramètres d'envoi

| Paramètre | Valeur |
|---|---|
| Port LoRaWAN (`f_port`) | `1` |
| Priorité | `NORMAL` |
| Mode | non confirmé (`confirmed: false`) |

### 4.2 Décodage — TTN (Payload formatter > Downlink)

```javascript
function encodeDownlink(input) {
  return {
    bytes:  [input.data.cmd === "sleep" ? 0x00 : 0x01],
    fPort:  1,
    warnings: []
  };
}
```

> Un downlink n'est transmis qu'**après un uplink** du End-Device (classe A).
> Le délai peut donc atteindre plusieurs minutes. Ce n'est pas un bug.

---

## 5. Format attendu par Node-RED (worldmap)

Le nœud `worldmap` n'accepte pas le JSON des sections 2 et 3 tel quel.
Un nœud `function` fait la conversion :

```javascript
msg.payload = {
    name: "Vehicule groupeX",
    lat:  msg.payload.lat,
    lon:  msg.payload.lon,
    icon: "car",
    iconColor: msg.payload.moving ? "red" : "gray"
};
return msg;
```

Carte accessible sur `http://<ip-rpi>:1880/worldmap`.

---

## 6. Contrainte de duty cycle — à respecter dans tout code d'émission

La réglementation EU868 impose un duty cycle de **1 %** : après chaque émission,
le End-Device doit rester silencieux pendant **99 fois** la durée de cette émission.

```
temps_attente = temps_emission * 99
```

| Spreading Factor | Temps d'émission (7 octets) | Attente minimale |
|---|---|---|
| SF7 | ~50 ms | ~5 s |
| SF9 | ~185 ms | ~18 s |
| SF12 | ~1 400 ms | ~2 min 20 s |

Vérifier avant d'écrire la boucle d'envoi :
https://avbentem.github.io/airtime-calculator/ttn/eu868

La pile LoRa du module **bloque d'elle-même** les émissions trop rapprochées.
Un `send()` qui semble ne rien faire vient presque toujours de là.

---

## 7. Procédure de modification

Ce contrat est partagé : le modifier unilatéralement casse le travail des autres pôles.

1. Annoncer le changement au groupe **avant** de coder.
2. Mettre à jour ce fichier et incrémenter la version.
3. Commiter le fichier **seul**, avec un message `interface: <description>`.
4. Prévenir les pôles impactés.

### Journal des versions

| Version | Date | Modification | Auteur |
|---|---|---|---|
| 1.0 | 2026-09-22 | Création — topics, JSON, trames montante et descendante | équipe |
