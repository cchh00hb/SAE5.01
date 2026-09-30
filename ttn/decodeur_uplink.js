/*
 * SAE5.01 - Etape 5 et 8 - Formateur de charge utile montante pour TTN.
 *
 * A coller dans la console TTN : Application > Payload formatters > Uplink,
 * type "Custom Javascript formatter".
 *
 * Decode les 7 octets produits par encoder_position() de main_ttn.py.
 * La structure est celle d'INTERFACE.md section 4 :
 *
 *     octets 0-2  latitude   entier signe, big-endian, complement a deux
 *     octets 3-5  longitude  idem
 *     octet  6    flags      bit 0 = mouvement, bit 1 = fix valide
 *
 * Facteur d'echelle : degres * 10000, soit 0.0001 degre de resolution,
 * environ 11 metres.
 */

function decodeUplink(input) {
  var b = input.bytes;

  if (b.length < 7) {
    return {
      data: {},
      errors: ["trame de " + b.length + " octets, 7 attendus"]
    };
  }

  function toInt24(hi, mid, lo) {
    var v = (hi << 16) | (mid << 8) | lo;
    // Complement a deux : au-dela de 0x7FFFFF la valeur est negative.
    if (v & 0x800000) {
      v -= 0x1000000;
    }
    return v;
  }

  var lat = toInt24(b[0], b[1], b[2]) / 10000;
  var lon = toInt24(b[3], b[4], b[5]) / 10000;
  var flags = b[6];

  var warnings = [];
  if ((flags & 0x02) === 0) {
    warnings.push("le End-Device signale un fix GNSS invalide");
  }

  return {
    data: {
      // Noms imposes par INTERFACE.md section 3 : le flow Node-RED ecrit
      // pour l'etape 2 fonctionne alors a l'identique en WiFi et en LoRaWAN.
      lat: lat,
      lon: lon,
      moving: (flags & 0x01) !== 0,
      fix: (flags & 0x02) !== 0,

      // Doublons pour mqtt_ttn.py, qui lit latitude / longitude.
      latitude: lat,
      longitude: lon
    },
    warnings: warnings
  };
}
