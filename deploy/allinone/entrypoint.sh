#!/bin/sh
# Jelly Leon — start van de alles-in-één container (ADR-0008; contract 1.3 §2.2).
#
#  * Start de container als root (standaard bij een TrueNAS Custom App zonder "Custom User"), dan:
#      - /config en /cache moeten bestaan (opslag uit het formulier); alleen DIE mappen krijgen eigenaar 568:568,
#        en alleen recursief als de bovenste map nog niet van 568 is (eerste start / migratie). Mediamappen worden
#        nooit aangeraakt (die horen read-only gemount te zijn).
#      - een datamap via JELLYFIN_DATA_DIR/JELLYFIN_CACHE_DIR buiten /config of /cache (of een symlink daarheen)
#        wordt als root geweigerd: nooit `chown -R` op systeem- of mediamappen (fail-closed).
#      - voor elk aanwezig /dev/dri/renderD*- én /dev/dri/card*-apparaat (optionele GPU) wordt de groep ervan als
#        aanvullende groep meegegeven (alleen als het apparaat in de container bestaat; groep 0 nooit), zodat
#        QSV/VAAPI als 568 werkt zonder privileged-modus;
#      - daarna draait alles als 568:568 zonder capabilities (setpriv): dit script start zichzelf opnieuw als 568 en
#        werkt pas dán de eigen pluginmap bij (geen schrijfacties als root in de datamap behalve chown).
#  * Altijd (ook als niet-root): datamap en instellingenmap moeten op blijvende, lokale opslag uit het formulier
#    staan — geen anoniem Docker-volume, geen tmpfs, niet in de container zelf, geen NFS/SMB-share — en padopties
#    (--datadir, --configdir, …) in het veld Command worden geweigerd. Anders zou de database bij een herstart of
#    update verdwijnen en de startwizard weer anoniem openstaan (fail-closed, review P0-afronding).
#  * Start de container al als niet-root (Custom User), dan wordt niets gewijzigd behalve de eigen pluginmap; zijn
#    /config of /cache niet schrijfbaar, dan een NL-fout; daarna no_new_privs (setpriv) vóór de server start.
#  * Opslaggrens (ADR-0032, deel 1c): vóór elke schrijfactie (als root vóór de eigenaarswissel, als app-gebruiker vóór
#    het vastleggen) weigert de start een data- of cachemap, een ouder daarvan, jelly-leon/ of plugins/ die een
#    symbolische koppeling is of voor groep of anderen beschrijfbaar; als app-gebruiker ook een map van een andere
#    eigenaar. NL-melding, er is niets gewijzigd. Anders kan een andere gebruiker de start via een koppeling laten
#    schrijven in bijvoorbeeld de database met kijkgegevens. Deel 1e/1f: een ingang in een eigen pluginmap die geen gewoon
#    bestand met één naam is, verwijdert de app-fase zelf vóór vergelijken, vastleggen of schrijven (unlink volgt niets;
#    alleen een map met inhoud wordt geweigerd), en de DLL wordt als nieuw bestand naast het doel geschreven en dan
#    hernoemd (nooit door een bestaande ingang heen). Deel 1f:
#    ook plugins/configurations en daarin Jellyfin.Plugin.JellyLeon.xml (de server leest en schrijft dat bestand). Een
#    /cache die een tmpfs is met /cache als eigen koppelpunt en bij de start leeg (own_tmpfs) wordt aanvaard met de eigenaar
#    en modus van Docker of TrueNAS; de image zet /cache op 1777, zodat ook een Custom User erin schrijft. Deel 1g: een lege
#    tmpfs van de NAS (Host Path /dev/shm) is daar niet sluitend van te onderscheiden; daarom wijzigt de start een
#    tmpfs-/cache nooit (ook als root geen eigenaarswissel) en verbiedt CUSTOM_APP.md (Verplicht 3) zo'n gedeelde /cache.
#  * De meegeleverde Jelly Leon-plugin wordt in <datamap>/plugins/JellyLeon_<versie> gezet; andere plugins blijven
#    onaangeroerd. Geen geheimen, geen netwerkaanroepen, geen shell voor iets anders dan deze start.
#  * Downgradeweigering (B03-014, JLT-61 b): <datamap>/jelly-leon/datamap-versie onthoudt de hoogste forkversie die de
#    datamap heeft gestart. Is die nieuwer dan deze image, dan stopt de container vóór elke schrijfactie met een
#    NL-melding: een oudere server op een al gemigreerde database kan kijkgegevens beschadigen (gemeten: 10.11.11 op
#    een 12.4-database start 'gezond', maar aanmelden geeft HTTP 500). Terugzetten = snapshot én vorige image samen;
#    de snapshot bevat dan ook de oude datamap-versie, zodat dat pad gewoon start.
set -eu

APP_UID=568
APP_GID=568
DATA_DIR="${JELLYFIN_DATA_DIR:-/config}"
CACHE_DIR="${JELLYFIN_CACHE_DIR:-/cache}"
BUNDLED_PLUGINS=/usr/share/jelly-leon/plugins
IMAGE_VERSION_FILE=/usr/share/doc/jelly-leon/VERSION
MOUNTINFO=/proc/self/mountinfo
SELF=$(readlink -f -- "$0")

log() { printf '%s jelly-leon: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FOUT: $*"; exit 1; }

# Map met instellingen (o.a. system.xml: "startwizard afgerond") — zelfde standaard als upstream (StartupHelpers).
CONFIG_DIR="${JELLYFIN_CONFIG_DIR:-$DATA_DIR/config}"

# Padopties op de opdrachtregel (veld Entrypoint/Command in het formulier) zouden de controles hieronder omzeilen.
for arg in "$@"; do
  case "$arg" in
    -d | -d* | --datadir | --datadir=* | -c | -c* | --configdir | --configdir=* | -C | -C* | --cachedir | --cachedir=* | \
    -l | -l* | --logdir | --logdir=* | -w | -w* | --webdir | --webdir=*)
      fail "opdrachtregeloptie '$arg' verplaatst een datamap of de web-client; laat Entrypoint/Command in het Custom App-formulier leeg" ;;
  esac
done

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  [ -d "$dir" ] || fail "$dir bestaat niet: voeg in het Custom App-formulier opslag toe met Mount Path $dir"
done

# Mount waarop een pad ligt (langste mountpoint-voorvoegsel in /proc/self/mountinfo; bij gestapelde mounts de
# bovenste): "<bestandssysteemtype> <root binnen de bron> <mountpoint>".
mount_of() {
  target=$(readlink -f -- "$1") || return 1
  awk -v p="$target" '
    {
      fs = ""
      for (i = 7; i <= NF; i++) if ($i == "-") { fs = $(i + 1); break }
      m = $5
      if (m == p || m == "/" || index(p, m "/") == 1) {
        if (length(m) >= best) { best = length(m); out = fs " " $4 " " m }
      }
    }
    END { if (out != "") print out }' "$MOUNTINFO"
}

# Deel 1f (BN-1): een tmpfs zoals het opslagtype tmpfs van het formulier hem geeft. Vastgesteld uit de mounttabel, niet uit de
# naam: de map is zelf het koppelpunt van een heel tmpfs-bestandssysteem (wortel "/", dus geen gekoppelde map daarin) en is
# bij de start leeg (Docker maakt een tmpfs bij elke start nieuw en leeg). Grens (deel 1g, R-VEILIG-1f-1): de héle wortel
# van een tmpfs van de NAS (Host Path /dev/shm) die toevallig leeg is, of een met een andere app gedeelde lege tmpfs, ziet er
# hier precies zo uit; daar kan een ander tijdens de looptijd wel iets in neerleggen. Daarom wijzigt de start een tmpfs-/cache
# nooit en verbiedt CUSTOM_APP.md (Verplicht 3) zo'n opzet.
own_tmpfs() {
  info=$(mount_of "$1") || return 1
  rest=${info#* }
  [ "${info%% *}" = tmpfs ] && [ "${rest%% *}" = / ] && [ "${rest#* }" = "$(readlink -f -- "$1")" ] || return 1
  entries=$(ls -A -- "$1") || return 1
  [ -z "$entries" ]
}

# Datamap en instellingen moeten op blijvende, lokale opslag uit het formulier staan; anders verdwijnen database en
# "startwizard afgerond" (bij herstart, update of herinstallatie) en staat de startwizard weer anoniem open
# — de eerste bezoeker wordt dan beheerder. Onduidelijke datamap = no-go (fasering P0) → weigeren (fail-closed).
#  * anoniem Docker-volume: de basisimage declareert VOLUME /config en /cache. Zonder opslagregel maakt Docker er één.
#    Mountinfo toont /…/volumes/<64 hex>/_data, of /<64 hex>/_data als de volumemap een eigen bestandssysteem is;
#  * tmpfs/ramfs (opslagtype tmpfs in het formulier): leeg na elke herstart;
#  * de container zelf (geen eigen mount): weg bij elke update of herinstallatie;
#  * netwerkshare (opslagtype NFS/SMB): de SQLite-database van Jellyfin is daar niet betrouwbaar (vergrendeling).
# Voor /cache (opnieuw op te bouwen) geldt alleen de controle op een anoniem volume.
assert_persistent() {
  info=$(mount_of "$1") || fail "$1 kan niet worden opgelost; laat JELLYFIN_*-variabelen leeg in het formulier"
  [ -n "$info" ] || fail "$1: geen mount gevonden in /proc/self/mountinfo"
  fstype=${info%% *}
  rest=${info#* }
  root=${rest%% *}
  mnt=${rest#* }
  if printf '%s\n' "$root" | grep -Eq '(^|/volumes)/[0-9a-f]{64}/_data$'; then
    fail "$mnt is een anoniem Docker-volume, geen gekozen dataset: voeg in het Custom App-formulier opslag (Host Path of ixVolume) toe met Mount Path $mnt"
  fi
  [ "$2" = "cache" ] && return 0
  if [ "$mnt" = "/" ]; then
    fail "$1 staat niet op eigen opslag maar in de container zelf (weg bij elke update): laat JELLYFIN_*-variabelen leeg en gebruik de opslagregel met Mount Path /config"
  fi
  case "$fstype" in
    tmpfs | ramfs)
      fail "$1 staat in het werkgeheugen ($fstype): database en instellingen verdwijnen bij elke herstart en de startwizard staat dan weer open. Kies voor Mount Path $mnt het opslagtype Host Path of ixVolume" ;;
    nfs | nfs4 | cifs | smb3 | smbfs)
      fail "$1 staat op een netwerkshare ($fstype): de SQLite-database van Jellyfin is daar niet betrouwbaar. Kies voor Mount Path $mnt een Host Path of ixVolume op de NAS zelf" ;;
  esac
}
# Deel 1g (R-VEILIG-1f-2): de server weigert te starten met minder dan 2 GiB vrij in /cache (StorageHelper.TwoGigabyte,
# 2147483647 bytes), gemeten nadat hij er zelf CACHEDIR.TAG in heeft gezet (op tmpfs één pagina, 4 KiB); een tmpfs van precies
# 2048 MiB start daardoor niet, 2049 MiB wel (gemeten met de echte server). Bij een tmpfs dan liever direct één Nederlandse
# regel dan een Engelse fout met herstartlus. Een dataset met te weinig ruimte meldt de server zelf. Leest alleen.
assert_cache_space() {
  [ "$(mount_of "$CACHE_DIR" | cut -d ' ' -f 1)" = tmpfs ] || return 0
  free=$(stat -f -c '%a %S' -- "$CACHE_DIR")
  free=$((${free% *} * ${free#* }))
  need=$((2147483647 + 4096))
  [ "$free" -lt "$need" ] || return 0
  fail "$CACHE_DIR is werkgeheugen (tmpfs) met $((free / 1048576)) MiB vrij; de server start pas met meer dan 2048 MiB vrij (hij eist 2 GiB vrij nadat hij er zelf een bestand in heeft gezet). Er is niets gewijzigd. Zet in het Custom App-formulier bij de opslag voor $CACHE_DIR (opslagtype tmpfs) de grootte op minstens 2560 MiB en start de app opnieuw"
}

assert_persistent "$DATA_DIR" data
assert_persistent "$CONFIG_DIR" data
assert_persistent "$CACHE_DIR" cache
assert_cache_space

# ---------------------------------------------------------------- downgradeweigering (JLT-61 b)
DATAMAP_VERSION_FILE="$DATA_DIR/jelly-leon/datamap-versie"

# "<a>.<b>.<c>-jl.<n>" → "a b c n" (leeg bij een onbekende vorm).
version_fields() {
  printf '%s\n' "$1" | sed -n 's/^\([0-9][0-9]*\)\.\([0-9][0-9]*\)\.\([0-9][0-9]*\)-jl\.\([0-9][0-9]*\)$/\1 \2 \3 \4/p'
}

# Exitcode 0 als versie $1 nieuwer is dan $2 (beide "a b c n" uit version_fields).
version_newer() {
  # shellcheck disable=SC2086 # bewust splitsen in vier getallen per versie
  set -- $1 $2
  for pair in "$1 $5" "$2 $6" "$3 $7" "$4 $8"; do
    left=${pair% *}
    right=${pair#* }
    if [ "$left" -gt "$right" ]; then return 0; fi
    if [ "$left" -lt "$right" ]; then return 1; fi
  done
  return 1
}

image_version() {
  [ -r "$IMAGE_VERSION_FILE" ] || fail "$IMAGE_VERSION_FILE ontbreekt: deze image is niet volgens deploy/allinone/Dockerfile gebouwd"
  head -n 1 "$IMAGE_VERSION_FILE"
}

# Leest alleen; schrijft niets. Weigert een datamap die al door een nieuwere Jelly Leon is gestart.
assert_not_downgrade() {
  # Ook vóór de eerste leesactie: geen gedeelde ouder, mapkoppeling, bestandskoppeling of FIFO volgen.
  # Root mag hier nog een vreemde eigenaar aantreffen (de eenmalige eigenaarswissel volgt pas na deze weigering).
  check_uid=$(id -u)
  [ "$check_uid" != 0 ] || check_uid=""
  assert_private_storage "$check_uid"
  if [ -L "$DATAMAP_VERSION_FILE" ] || { [ -e "$DATAMAP_VERSION_FILE" ] && [ ! -f "$DATAMAP_VERSION_FILE" ]; }; then
    fail "datamap-versie is geen gewoon bestand zonder koppeling. Er is niets gewijzigd. Dit bestand onthoudt alleen de hoogste Jelly Leon-versie, geen kijkgegevens. Veilige weg: controleer in TrueNAS bij Apps → Edit → Storage de eigen config-opslag en bij je andere apps dat geen andere app de config-dataset gekoppeld heeft; laat daarna alleen dit ene bestand weghalen (bijvoorbeeld via de Hub; start daarna alleen de nieuwste Jelly Leon-image die je gebruikte). Zet een snapshot van de config-dataset (Datasets → Snapshots) alleen terug als je accepteert dat de kijkgegevens van na die snapshot verloren gaan"
  fi
  assert_private_dir "$DATAMAP_VERSION_FILE" "$check_uid"
  own=$(image_version)
  own_fields=$(version_fields "$own")
  [ -n "$own_fields" ] || fail "forkversie van deze image ('$own') heeft geen geldige vorm <x.y.z>-jl.<n>"
  [ -e "$DATAMAP_VERSION_FILE" ] || return 0
  recorded=$(sed -n 's/^fork_version=//p' "$DATAMAP_VERSION_FILE" | head -n 1)
  recorded_fields=$(version_fields "$recorded")
  if [ -z "$recorded_fields" ]; then
    fail "$DATAMAP_VERSION_FILE is onleesbaar (verwacht fork_version=<x.y.z>-jl.<n>); er is niets gewijzigd. Dit bestand onthoudt alleen de hoogste Jelly Leon-versie, geen kijkgegevens. Veilige weg: laat alleen dit ene bestand weghalen (bijvoorbeeld via de Hub; start daarna alleen de nieuwste Jelly Leon-image die je gebruikte). Zet een snapshot van de config-dataset (Datasets → Snapshots) alleen terug als je accepteert dat de kijkgegevens van na die snapshot verloren gaan"
  fi
  if version_newer "$recorded_fields" "$own_fields"; then
    fail "deze datamap is al gestart door Jelly Leon $recorded, nieuwer dan deze image ($own). Een oudere server op een al gemigreerde database kan kijkgegevens beschadigen, daarom start deze image niet; er is niets gewijzigd. Veilige weg: kies weer de nieuwere image. Terugzetten kan alleen met de snapshot van de config-dataset van vóór de update én de vorige image samen (deploy/truenas/CUSTOM_APP.md, 'Updaten en terugdraaien'); dan gaan de kijkgegevens van na die snapshot verloren"
  fi
}

# Alleen als 568 vlak vóór de start: hoogste forkversie vastleggen (atomair; nooit verlagen).
record_datamap_version() {
  own=$(image_version)
  if [ -e "$DATAMAP_VERSION_FILE" ]; then
    recorded=$(sed -n 's/^fork_version=//p' "$DATAMAP_VERSION_FILE" | head -n 1)
    [ "$recorded" = "$own" ] && return 0
  fi
  mkdir -p "$DATA_DIR/jelly-leon" || fail "$DATA_DIR/jelly-leon kan niet worden aangemaakt"
  assert_private_dir "$DATA_DIR/jelly-leon" "$(id -u)"
  # Exclusief nieuw, willekeurige naam, 0600: een vooraf gelegde koppeling op een voorspelbare naam wordt nooit gevolgd.
  tmp=$(mktemp "$DATAMAP_VERSION_FILE.tmp.XXXXXXXXXX") || fail "$DATAMAP_VERSION_FILE kan niet worden geschreven"
  if ! {
    printf '# Hoogste Jelly Leon-versie die deze datamap heeft gestart (downgradeweigering, JLT-61 b). Niet bewerken.\n'
    printf 'fork_version=%s\n' "$own"
  } > "$tmp" || ! mv -f "$tmp" "$DATAMAP_VERSION_FILE"; then
    rm -f "$tmp"
    fail "$DATAMAP_VERSION_FILE kan niet worden geschreven"
  fi
  log "datamap-versie vastgelegd: $own"
}

# Opslaggrens (ADR-0032, "Opslagdreigingen, deel 1c"): een map waarin de start schrijft of eigenaarschap doorgeeft, mag
# geen symbolische koppeling zijn en niet voor groep of anderen beschrijfbaar; met $2 (de app-gebruiker) moet hij ook
# van die gebruiker zijn. Anders kan een andere gebruiker of app er een koppeling neerleggen waarlangs de start een ander
# bestand overschrijft, zoals de database met kijkgegevens. Met $3 (een ouder) mag ook root eigenaar zijn en mag een
# map met sticky-bit (zoals /tmp) voor iedereen beschrijfbaar zijn: daarin kan niemand anders de eigen map vervangen.
# Leest alleen.
assert_private_dir() {
  if [ -L "$1" ]; then
    fail "$1 is een symbolische koppeling: daarlangs kan de start buiten de eigen opslag schrijven, bijvoorbeeld in de database met kijkgegevens. Er is niets gewijzigd. Veilige weg: controleer in TrueNAS bij de app (Edit → Storage) dat /config en /cache op de eigen datasets staan, en bij je andere apps dat geen andere app de config-dataset gekoppeld heeft; laat daarna alleen deze koppeling weghalen (bijvoorbeeld via de Hub). Zet een snapshot van de config-dataset (Datasets → Snapshots) alleen terug als je accepteert dat de kijkgegevens van na die snapshot verloren gaan"
  fi
  [ -e "$1" ] || return 0
  perm=$(stat -c '%a' -- "$1")
  owner=$(stat -c '%u' -- "$1")
  # Een tmpfs is geen dataset: dan geen verwijzing naar Datasets → Permissions (deel 1f, R-HARDE-EIS-1).
  tmpfs_fix="$1 staat in werkgeheugen (tmpfs) dat niet alleen van deze container is (geen eigen koppelpunt, of al gevuld bij de start); het is geen dataset. Kies in TrueNAS in het Custom App-formulier voor deze opslag een eigen dataset (Host Path of ixVolume) of, alleen voor /cache, het opslagtype tmpfs (de container krijgt dan bij elke start een eigen, lege tmpfs), en start de app opnieuw"
  if [ $((0$perm & 022)) -ne 0 ] && { [ -z "${3:-}" ] || [ $((0$perm & 01000)) -eq 0 ]; }; then
    if [ "$(mount_of "$1" | cut -d ' ' -f 1)" = tmpfs ]; then
      fail "$1 is voor groep of anderen beschrijfbaar (modus $perm). Er is niets gewijzigd. $tmpfs_fix"
    fi
    fail "$1 is voor groep of anderen beschrijfbaar (modus $perm): een andere gebruiker of app kan daar een koppeling neerleggen waarlangs de start een ander bestand overschrijft, bijvoorbeeld de database met kijkgegevens. Er is niets gewijzigd. Zet in TrueNAS bij Datasets → de dataset van deze map → Permissions → Edit de schrijfrechten voor groep, anderen en extra ACL-regels uit, ook voor de onderliggende mappen (alleen de eigenaar apps, 568, schrijft), en start de app opnieuw"
  fi
  if [ -n "${2:-}" ] && [ "$owner" != "$2" ] && { [ -z "${3:-}" ] || [ "$owner" != 0 ]; }; then
    if [ "$(mount_of "$1" | cut -d ' ' -f 1)" = tmpfs ]; then
      fail "$1 is van gebruiker $owner, niet van $2. Er is niets gewijzigd. $tmpfs_fix"
    fi
    fail "$1 is van gebruiker $owner, niet van $2: die gebruiker kan de map vervangen of er een koppeling in neerleggen. Er is niets gewijzigd. Maak in TrueNAS bij Datasets → de dataset van deze map → Permissions → Edit de gebruiker apps (568) eigenaar, ook van de onderliggende mappen, en start de app opnieuw"
  fi
}

# Deel 1g (vervolgpunt van de herreview): een eigen pluginmap is <naam>_<versie> van een plugin die de image zelf meelevert
# (exacte naam uit BUNDLED_PLUGINS, elke versie: alleen cijfers en punten). Een andere map, ook JellyLeon_Extra_2.0.0.0 van een
# andere plugin, hoort niet bij de start: die wordt niet gecontroleerd, hersteld of verwijderd.
own_plugin_dir() {
  pd_name=${1##*/}
  pd_version=${pd_name##*_}
  case $pd_version in '' | *[!0-9.]*) return 1 ;; esac
  for pd_src in "$BUNDLED_PLUGINS"/*; do
    pd_bundled=${pd_src##*/}
    [ -d "$pd_src" ] && [ "${pd_bundled%_*}" = "${pd_name%_*}" ] && return 0
  done
  return 1
}

# De data- en cachemap met hun ouders tot / (die komt uit de image), de mappen waarin de start zelf schrijft, de map van
# de pluginconfiguraties met het eigen bestand daarin (de server schrijft dat), en in een eigen pluginmap een map met inhoud
# (de andere vreemde ingangen daar herstelt repair_plugin_dirs).
# $1 = de app-gebruiker; leeg als root vóór de eenmalige eigenaarswissel.
assert_private_storage() {
  for top in "$DATA_DIR" "$CACHE_DIR"; do
    # Deel 1f (BN-1): een eigen tmpfs als cache aanvaarden met de eigenaar en modus die Docker of TrueNAS geeft (ook 1777).
    if [ "$top" != "$CACHE_DIR" ] || ! own_tmpfs "$top"; then
      top_uid=${1:-}
      # Deel 1g: een tmpfs krijgt ook als root nooit een andere eigenaar (zie de eigenaarswissel), dus moet hij al van de
      # app-gebruiker zijn; anders hier weigeren, vóór de eigenaarswissel van /config.
      if [ -z "$top_uid" ] && [ "$top" = "$CACHE_DIR" ] && [ "$(mount_of "$top" | cut -d ' ' -f 1)" = tmpfs ]; then
        top_uid=$APP_UID
      fi
      assert_private_dir "$top" "$top_uid"
    fi
    parent=$(dirname -- "$top")
    while [ "${#parent}" -gt 1 ]; do # stopt bij / (en bij . voor een relatief pad)
      assert_private_dir "$parent" "${1:-}" ouder
      parent=$(dirname -- "$parent")
    done
  done
  for dir in "$DATA_DIR/jelly-leon" "$DATA_DIR/plugins" "$DATA_DIR/plugins/configurations" "$DATA_DIR"/plugins/JellyLeon_*; do
    case $dir in "$DATA_DIR"/plugins/JellyLeon_*) own_plugin_dir "$dir" || continue ;; esac
    assert_private_dir "$dir" "${1:-}"
  done
  # Deel 1f (R-VEILIG-1): de server leest de eigen pluginconfiguratie en schrijft er bij een mislukte lezing een nieuwe in
  # (FileMode.Create volgt een koppeling). Bestanden van andere plugins in dezelfde map blijven buiten beschouwing. Deel 1g
  # (besluit 4): een gewoon bestand met meer namen tot 1 MiB laten beide fasen door; de app-fase maakt er een eigen kopie van
  # (separate_plugin_config). stat leest alleen de inode: een FIFO wordt nooit geopend.
  xml="$DATA_DIR/plugins/configurations/Jellyfin.Plugin.JellyLeon.xml"
  if [ -L "$xml" ] || { [ -e "$xml" ] && { [ ! -f "$xml" ] || { [ "$(stat -c '%h' -- "$xml")" != 1 ] \
    && [ "$(stat -c '%s' -- "$xml")" -gt 1048576 ]; }; }; }; then
    fail "$xml is geen gewoon bestand met één naam (een symbolische koppeling, een map, een bijzonder bestand of een harde koppeling groter dan 1 MiB): daarlangs kan de server bij het lezen of opslaan van de Jelly Leon-instellingen een ander bestand overschrijven, bijvoorbeeld de database met kijkgegevens. Er is niets gewijzigd. Dit bestand bevat alleen de moduleschakelaars van Jelly Leon, geen kijkgegevens. Veilige weg: controleer bij Apps → Edit → Storage van je andere apps dat geen andere app de config-dataset of een map daarin gekoppeld heeft, laat daarna alleen dit ene bestand weghalen (bijvoorbeeld via de Hub; Jelly Leon start dan met standaardinstellingen, alle modules uit) en start de app opnieuw. Zet een snapshot van de config-dataset (Datasets → Snapshots) alleen terug als je accepteert dat de kijkgegevens van na die snapshot verloren gaan"
  fi
  # Eigen pluginmappen (ADR-0032, deel 1e en 1f): een vreemde ingang (koppeling, harde koppeling, FIFO, lege map) herstelt de
  # app-fase zelf (repair_plugin_dirs). Alleen een map met inhoud kan zij niet veilig opruimen: dan weigeren, vóór alles.
  for dir in "$DATA_DIR"/plugins/JellyLeon_*; do
    { [ -d "$dir" ] && own_plugin_dir "$dir"; } || continue
    odd=$(find "$dir" -mindepth 1 -maxdepth 1 -type d ! -empty -print -quit) \
      || fail "$dir kan niet worden gecontroleerd. Er is niets gewijzigd. Controleer in TrueNAS bij Datasets → de config-dataset → Permissions → Edit dat de gebruiker apps (568) eigenaar is, en start de app opnieuw"
    if [ -n "$odd" ]; then
      fail "$odd is een map met inhoud in de eigen pluginmap; die kan de start niet veilig opruimen. Er is niets gewijzigd. De pluginmap bevat alleen de meegeleverde Jelly Leon-plugin, geen kijkgegevens. Veilige weg: laat alleen deze map weghalen (bijvoorbeeld via de Hub); de start zet de plugin daarna zelf terug. Zet een snapshot van de config-dataset (Datasets → Snapshots) alleen terug als je accepteert dat de kijkgegevens van na die snapshot verloren gaan"
    fi
  done
}

# Deel 1f (R-VEILIG-3): een overerfbare ACL-regel (POSIX default-ACL of NFSv4-overerving) geeft een nieuwe map schrijfrecht
# voor groep of anderen, ook met umask 022, en de modus van de bestaande map verraadt dat niet. Vóór elke wijziging (als root
# vóór de eigenaarswissel, als app-gebruiker vóór herstel en vastleggen) maakt de start daarom in elke map waarin zij zelf een
# map gaat aanmaken één proefmap met een onvoorspelbare naam, leest de modus en verwijdert haar direct (alleen de
# wijzigingstijd van die map verandert). Zo weigert zij voordat er iets is gewijzigd.
probe_new_dir() {
  probe=$(mktemp -u "$1/.jelly-leon-proef.XXXXXXXXXX") || return 0
  mkdir -- "$probe" 2>/dev/null || return 0 # lukt dat niet, dan faalt straks de echte mkdir met zijn eigen melding
  perm=$(stat -c '%a' -- "$probe")
  rmdir -- "$probe" || fail "proefmap $probe kan niet worden verwijderd; controleer in TrueNAS bij Datasets → de config-dataset → Permissions → Edit dat de gebruiker apps (568) eigenaar is"
  [ $((0$perm & 022)) -eq 0 ] || fail "nieuwe mappen in $1 krijgen schrijfrecht voor groep of anderen (modus $perm), door een overerfbare ACL-regel van die map: dan kan een andere gebruiker of app er een koppeling neerleggen waarlangs de start of de server een ander bestand overschrijft, bijvoorbeeld de database met kijkgegevens. Er is niets gewijzigd (alleen een proefmap is gemaakt en direct weer verwijderd). Zet in TrueNAS bij Datasets → de dataset van deze map → Permissions → Edit de ACL-regels voor onderliggende mappen (overerving) zonder schrijfrecht voor groep, anderen of extra gebruikers (alleen de eigenaar apps, 568, schrijft), en start de app opnieuw"
}
assert_new_dirs_private() {
  if [ ! -e "$DATA_DIR/jelly-leon" ] || [ ! -e "$DATA_DIR/plugins" ]; then
    probe_new_dir "$DATA_DIR"
  fi
  for src in "$BUNDLED_PLUGINS"/JellyLeon_*; do
    if [ -d "$src" ] && [ -d "$DATA_DIR/plugins" ] && [ ! -e "$DATA_DIR/plugins/$(basename -- "$src")" ]; then
      probe_new_dir "$DATA_DIR/plugins"
    fi
  done
}

# Deel 1g (R-VEILIG-1f-3): een start die precies tussen mkdir en rmdir van probe_new_dir werd afgebroken, liet een lege proefmap
# achter (ook een van root). Na alle weigeringen verwijdert de app-fase alleen een lege, echte map met precies dat naampatroon
# direct in de gecontroleerde map (find -type d volgt geen koppeling; -delete is rmdir, dus nooit inhoud).
remove_probe_leftovers() {
  x='[0-9A-Za-z]'
  for dir in "$DATA_DIR" "$DATA_DIR/plugins"; do
    [ -d "$dir" ] || continue
    gone=$(find "$dir" -mindepth 1 -maxdepth 1 -type d -empty -name ".jelly-leon-proef.$x$x$x$x$x$x$x$x$x$x" -print -delete) \
      || log "waarschuwing: niet elke achtergebleven proefmap in $dir kon worden verwijderd"
    [ -z "$gone" ] || log "achtergebleven lege proefmap verwijderd: $(printf '%s' "$gone" | tr '\n' ' ')"
  done
}

# Deel 1f (BN-2): in een eigen pluginmap (door de image beheerd) verwijdert de app-fase elke ingang die geen gewoon bestand met
# één naam is: unlink en rmdir volgen niets, dus het doel van een koppeling en een andere naam van hetzelfde bestand blijven
# ongemoeid. De DLL komt daarna als nieuw bestand; meta.json schrijft de server opnieuw. Eén logregel per herstelde map.
repair_plugin_dirs() {
  for dir in "$DATA_DIR"/plugins/JellyLeon_*; do
    { [ -d "$dir" ] && own_plugin_dir "$dir"; } || continue
    gone=$(find "$dir" -mindepth 1 -maxdepth 1 \( ! -type f -o -links +1 \) -print -delete) \
      || fail "$dir: niet elke vreemde ingang kon worden verwijderd (wel verwijderd: ${gone:-niets}). De database met kijkgegevens is niet aangeraakt. Controleer in TrueNAS bij Datasets → de config-dataset → Permissions → Edit dat de gebruiker apps (568) eigenaar is met schrijfrecht, en start de app opnieuw"
    [ -z "$gone" ] || log "eigen pluginmap $(basename -- "$dir") hersteld zonder een koppeling te volgen; verwijderd: $(printf '%s' "$gone" | tr '\n' ' ')"
  done
}

# Deel 1g (besluit 4): een harde koppeling op de eigen pluginconfiguratie (ontdubbelen, terugzetten met behoud van koppelingen)
# wordt een eigen kopie. Alleen als app-gebruiker, na assert_private_storage (plugins/configurations van deze gebruiker en niet
# gedeeld; het bestand een gewoon bestand van hooguit 1 MiB). place_file leest de inhoud, schrijft een nieuw bestand naast de
# ingang (mktemp) en hernoemt dat over de ingang: er wordt nooit door de koppeling geschreven, de andere naam blijft gelijk.
separate_plugin_config() {
  xml="$DATA_DIR/plugins/configurations/Jellyfin.Plugin.JellyLeon.xml"
  { [ -f "$xml" ] && [ ! -L "$xml" ] && [ "$(stat -c '%h' -- "$xml")" != 1 ]; } || return 0
  place_file "$xml" "$xml" \
    || fail "$xml (een harde koppeling) kon niet als eigen kopie worden neergezet. De andere naam en de database met kijkgegevens zijn niet aangeraakt. Controleer in TrueNAS bij Datasets → de config-dataset → Permissions → Edit dat de gebruiker apps (568) eigenaar is met schrijfrecht, en start de app opnieuw"
  log "pluginconfiguratie $(basename -- "$xml") had meer namen (harde koppeling): eigen kopie neergezet zonder door de koppeling te schrijven; de andere naam is ongewijzigd"
}

# Zet bestand $1 neer als $2 zonder een bestaande ingang te volgen: eerst een nieuw bestand naast het doel (mktemp:
# exclusief, willekeurige naam), dan hernoemen. Een (harde) koppeling op $2 wordt zo vervangen, nooit beschreven.
place_file() {
  tmp=$(mktemp "$2.tmp.XXXXXXXXXX") || return 1
  if cp "$1" "$tmp" && mv -f -T "$tmp" "$2"; then
    return 0
  fi
  rm -f "$tmp"
  return 1
}

assert_not_downgrade

# Alleen /config, /cache en mappen daaronder mogen als root van eigenaar wisselen (na het oplossen van symlinks).
assert_owned_mount() {
  resolved=$(readlink -f -- "$1") || fail "$1 kan niet worden opgelost"
  case "$resolved" in
    /config | /config/* | /cache | /cache/*) ;;
    *) fail "$1 (werkelijk pad $resolved) ligt buiten /config of /cache; als root wordt hier niets aangepast. Laat JELLYFIN_DATA_DIR/JELLYFIN_CACHE_DIR leeg in het formulier." ;;
  esac
}

install_plugins() {
  [ -d "$BUNDLED_PLUGINS" ] || return 0
  if ! mkdir -p "$DATA_DIR/plugins" 2>/dev/null; then
    log "waarschuwing: $DATA_DIR/plugins niet schrijfbaar; Jelly Leon-plugin niet bijgewerkt"
    return 0
  fi
  assert_private_dir "$DATA_DIR/plugins" "$(id -u)"
  for src in "$BUNDLED_PLUGINS"/JellyLeon_*; do
    [ -d "$src" ] || continue
    name=$(basename "$src")
    # Alleen eigen pluginmappen van een andere versie opruimen (own_plugin_dir: niet die van een andere plugin, deel 1g).
    for old in "$DATA_DIR/plugins"/JellyLeon_*; do
      { [ -d "$old" ] && own_plugin_dir "$old"; } || continue
      [ "$(basename "$old")" = "$name" ] && continue
      if rm -rf -- "$old"; then
        log "oude Jelly Leon-plugin $(basename "$old") verwijderd"
      else
        log "waarschuwing: oude Jelly Leon-plugin $(basename "$old") kon niet worden verwijderd"
      fi
    done
    if ! cmp -s "$src/Jellyfin.Plugin.JellyLeon.dll" "$DATA_DIR/plugins/$name/Jellyfin.Plugin.JellyLeon.dll" 2>/dev/null; then
      if mkdir -p "$DATA_DIR/plugins/$name" && assert_private_dir "$DATA_DIR/plugins/$name" "$(id -u)" \
        && place_file "$src/Jellyfin.Plugin.JellyLeon.dll" "$DATA_DIR/plugins/$name/Jellyfin.Plugin.JellyLeon.dll"; then
        log "Jelly Leon-plugin $name geïnstalleerd"
      else
        log "waarschuwing: Jelly Leon-plugin $name kon niet worden geïnstalleerd (zie GET /media/v1/version)"
      fi
    fi
  done
}

if [ "$(id -u)" != "0" ]; then
  # JELLY_LEON_ENTRYPOINT_STAGE markeert de tweede fase na setpriv (geen geheim). Alleen geloofwaardig als
  # no_new_privs echt aan staat: een in het formulier gezette variabele kan de stap hieronder niet overslaan.
  nnp=$(awk '/^NoNewPrivs:/ { print $2 }' /proc/self/status)
  if [ "${JELLY_LEON_ENTRYPOINT_STAGE:-}" = "app" ] && [ "$nnp" = "1" ]; then
    log "draait als $(id -u):$(id -g) (groepen $(id -G | tr ' ' ',')), zonder capabilities, no_new_privs"
    unset JELLY_LEON_ENTRYPOINT_STAGE
    # Deel 1h (R-EERLIJK-5): een tmpfs-/cache wisselt nooit van eigenaar of modus (deel 1g); met een eigen modus (bijvoorbeeld
    # 0755 van root) kan de server er dan niet in schrijven en stopt hij met een Engelse fout. Liever één Nederlandse regel.
    if [ "$(mount_of "$CACHE_DIR" | cut -d ' ' -f 1)" = tmpfs ] && { [ ! -w "$CACHE_DIR" ] || [ ! -x "$CACHE_DIR" ]; }; then
      fail "$CACHE_DIR is werkgeheugen (tmpfs) waarin de app-gebruiker $(id -u):$(id -g) niet mag schrijven (eigenaar $(stat -c '%u:%g' -- "$CACHE_DIR"), modus $(stat -c '%a' -- "$CACHE_DIR")); de server kan daar zijn cache niet aanmaken. Er is niets gewijzigd (de start wijzigt een tmpfs nooit). Kies in het Custom App-formulier voor Mount Path $CACHE_DIR het opslagtype tmpfs met alleen een grootte (de image geeft dan modus 1777) of zet de modus op 1777, en start de app opnieuw"
    fi
    assert_private_storage "$(id -u)"
    assert_new_dirs_private
    remove_probe_leftovers
    repair_plugin_dirs
    separate_plugin_config
    record_datamap_version
    install_plugins
    exec /jellyfin/jellyfin "$@"
  fi
  # Custom User in het formulier: geen eigenaarschapsstap, dus de opslag moet al van deze gebruiker zijn. Niet
  # schrijfbaar → NL-melding en stoppen (healthcheck rood), nooit stil doorstarten (contract 1.3 §2.2).
  for dir in "$DATA_DIR" "$CACHE_DIR"; do
    if [ ! -w "$dir" ] || [ ! -x "$dir" ]; then
      if [ "$(mount_of "$dir" | cut -d ' ' -f 1)" = tmpfs ]; then
        fail "$dir is werkgeheugen (tmpfs) waarin gebruiker $(id -u):$(id -g) (Custom User in het formulier) niet mag schrijven: zet Custom User uit, of kies voor Mount Path $dir het opslagtype tmpfs zonder eigen modus of een eigen dataset (Host Path of ixVolume) van deze gebruiker"
      fi
      fail "$dir is niet schrijfbaar voor gebruiker $(id -u):$(id -g) (Custom User in het formulier): zet Custom User uit (de container maakt dan zelf 568:568 eigenaar van /config en /cache) of maak de dataset eerst van deze gebruiker"
    fi
  done
  log "start als gebruiker $(id -u):$(id -g) (Custom User; geen eigenaarschap aangepast)"
  # Het formulier zet geen no-new-privileges (contract 1.3 §2.2): zelf zetten vóór de eerste execve van de server.
  # (Zonder CAP_SETPCAP kan een niet-root-proces de bounding-set niet legen; met no_new_privs en CapEff 0 kan het
  # ook via setuid-bestanden geen rechten meer krijgen.)
  export JELLY_LEON_ENTRYPOINT_STAGE=app
  exec setpriv --no-new-privs --inh-caps=-all -- "$SELF" "$@"
fi

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  assert_owned_mount "$dir"
done
# Vóór de eigenaarswissel: een gedeelde map, koppeling of overerfbare ACL weigeren zonder iets te wijzigen (eigenaar pas als
# app-gebruiker).
assert_private_storage
assert_new_dirs_private

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  # Deel 1g (R-VEILIG-1f-1): een tmpfs-/cache nooit van eigenaar of modus wisselen; het kan per vergissing een tmpfs van de
  # NAS zijn (Host Path /dev/shm). Een tmpfs uit het formulier heeft modus 1777 van de image en is zo ook voor 568 schrijfbaar.
  [ "$dir" = "$CACHE_DIR" ] && [ "$(mount_of "$dir" | cut -d ' ' -f 1)" = tmpfs ] && continue
  owner=$(stat -c '%u' "$dir")
  if [ "$owner" != "$APP_UID" ]; then
    log "$dir is van uid $owner; eigenaar wordt $APP_UID:$APP_GID (eenmalig, alleen deze map)"
    chown -R "$APP_UID:$APP_GID" "$dir"
  fi
done

groups="$APP_GID"
for node in /dev/dri/renderD* /dev/dri/card*; do
  [ -e "$node" ] || continue
  gid=$(stat -c '%g' "$node")
  if [ "$gid" = "0" ]; then
    log "waarschuwing: $node hoort bij groep 0 (root); die groep wordt niet toegevoegd — GPU mogelijk niet bruikbaar"
    continue
  fi
  case ",$groups," in
    *",$gid,"*) ;;
    *) groups="$groups,$gid" ;;
  esac
done
if [ "$groups" != "$APP_GID" ]; then
  log "GPU-apparaten gevonden; aanvullende groepen: $groups"
else
  log "geen /dev/dri-apparaten: transcoderen alleen via CPU (hardwareversnelling uit)"
fi

# Tweede fase: hetzelfde script als 568 zonder capabilities; dat werkt de pluginmap bij en start Jellyfin.
export JELLY_LEON_ENTRYPOINT_STAGE=app
exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --groups="$groups" --inh-caps=-all --bounding-set=-all \
  --no-new-privs -- "$SELF" "$@"
