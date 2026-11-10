#!/bin/sh
# Jelly Leon — Docker-healthcheck van de alles-in-één image (contract 1.3 §2.2; ADR-0014, ADR-0028).
#
# Docker start de healthcheck (net als elke `docker exec`) als de containergebruiker, buiten de procesboom van PID 1:
# bij een Custom App zonder "Custom User" is dat root, mét de standaard-capabilities en zonder no_new_privs (het formulier
# zet die niet). Daarom is de rechtenwissel de eerste handeling, vóór elke controle:
#   * als root: bounding set legen, aanvullende groepen weg, naar 568:568, geen inheritable of ambient capabilities en
#     no_new_privs, in één setpriv-aanroep; daarna start dit script zichzelf opnieuw met precies die rechten (altijd,
#     ook als iemand het interne fase-argument meegeeft);
#   * al niet-root (Custom User) zonder no_new_privs: alleen no_new_privs en geen inheritable capabilities (zonder
#     CAP_SETPCAP kan een niet-root-proces de bounding set niet legen); staat no_new_privs na die wissel nog uit, dan
#     rood (geen tweede poging, geen lus);
#   * pas ná de wissel controleert het script zijn eigen rechten in /proc/self/status — Uid 568 (of de Custom User,
#     nooit 0), CapPrm/CapEff/CapAmb 0 en NoNewPrivs 1; na een start als root ook Gid 568, geen groepen en CapBnd 0 —
#     en daarna pas /health. Mislukt de controle of /health, dan exitcode 1 (rood); nooit stil doorgaan.
# Vóór de wissel gebruikt het script alleen ingebouwde shellopdrachten (read, case, export): er start geen ander
# programma als root. Het korte venster waarin de shell zelf nog als root draait, is het gemelde restrisico van §2.2.
# Weigert setpriv de wissel, dan eindigt het met de foutcode van setpriv: ook dat telt voor Docker als ongezond (elke
# exitcode behalve 0), en er draait daarna geen root-proces meer. Geen geheimen, geen netwerk buiten de container.
#
#   jelly-leon-healthcheck                → GET http://localhost:8096/health (0 = gezond, 1 = ongezond)
#   jelly-leon-healthcheck --toon-rechten → controlevlag voor de rooktest (tools/jelly-leon/e2e/image_lifecycle.py,
#                                           healthcheck_proef.py): dezelfde wissel en controle, daarna /proc/self/status
#                                           van een proces met precies die rechten (0 = rechten in orde, 1 = niet)
# Het tweede argument (--na-wissel, --na-wissel-root) is intern: dit script geeft het zichzelf mee na de wissel. Het
# formulier kan het niet zetten (Docker start de healthcheck zonder argumenten) en het slaat niets over: als root
# wordt altijd gewisseld, en de controle leest de echte rechten.
set -eu
set -f

APP_UID=568
APP_GID=568
NUL=0000000000000000

gebruik() {
  printf 'jelly-leon-healthcheck: %s (gebruik: jelly-leon-healthcheck [--toon-rechten])\n' "$*" >&2
  exit 2
}
[ "$#" -le 2 ] || gebruik "te veel argumenten"
modus=${1:-}
fase=${2:-}
case "$modus" in
  "" | --toon-rechten) ;;
  *) gebruik "onbekende optie $modus" ;;
esac
case "$fase" in
  "" | --na-wissel | --na-wissel-root) ;;
  *) gebruik "onbekende optie $fase" ;;
esac

fout() {
  printf 'jelly-leon-healthcheck: %s\n' "$*" >&2
  exit 1
}

# Eigen rechten uit /proc/self/status, alleen met ingebouwde opdrachten (geen extra proces, ook niet vóór de wissel).
lees_rechten() {
  R_UID='' R_GID='' R_GROUPS='' R_CAPPRM='' R_CAPEFF='' R_CAPAMB='' R_CAPBND='' R_NNP=''
  while IFS= read -r regel; do
    sleutel=${regel%%:*}
    # shellcheck disable=SC2086 # bewust splitsen op witruimte: de velden van /proc/self/status
    set -- ${regel#*:}
    case "$sleutel" in
      Uid) R_UID="$*" ;;
      Gid) R_GID="$*" ;;
      Groups) R_GROUPS="$*" ;;
      CapPrm) R_CAPPRM="$*" ;;
      CapEff) R_CAPEFF="$*" ;;
      CapAmb) R_CAPAMB="$*" ;;
      CapBnd) R_CAPBND="$*" ;;
      NoNewPrivs) R_NNP="$*" ;;
    esac
  done < /proc/self/status
}

lees_rechten
[ -n "$R_UID" ] || fout "eigen rechten onleesbaar (/proc/self/status)"

case " $R_UID " in
  *" 0 "*)
    exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups --inh-caps=-all --bounding-set=-all \
      --no-new-privs -- /bin/sh "$0" "$modus" --na-wissel-root ;;
esac
if [ "$R_NNP" != 1 ]; then
  [ -z "$fase" ] || fout "rechtenwissel niet in orde: NoNewPrivs ${R_NNP:-?} na de wissel; /health niet gecontroleerd"
  exec setpriv --no-new-privs --inh-caps=-all -- /bin/sh "$0" "$modus" --na-wissel
fi

# ---------------------------------------------------------------- na de wissel: eerst de eigen rechten controleren
problemen=''
probleem() { problemen="${problemen:+$problemen; }$*"; }
# shellcheck disable=SC2086 # bewust splitsen: vier uid-velden (echt, effectief, bewaard, bestandssysteem)
set -- $R_UID
if [ "$#" -ne 4 ] || [ "$1" = 0 ] || [ "$1" != "$2" ] || [ "$1" != "$3" ] || [ "$1" != "$4" ]; then
  probleem "Uid $R_UID"
fi
[ "$R_CAPPRM" = "$NUL" ] || probleem "CapPrm $R_CAPPRM"
[ "$R_CAPEFF" = "$NUL" ] || probleem "CapEff $R_CAPEFF"
[ "$R_CAPAMB" = "$NUL" ] || probleem "CapAmb ${R_CAPAMB:-?}"
[ "$R_NNP" = 1 ] || probleem "NoNewPrivs ${R_NNP:-?}"
if [ "$fase" = --na-wissel-root ]; then
  [ "$R_UID" = "$APP_UID $APP_UID $APP_UID $APP_UID" ] || probleem "Uid $R_UID (verwacht $APP_UID)"
  [ "$R_GID" = "$APP_GID $APP_GID $APP_GID $APP_GID" ] || probleem "Gid $R_GID (verwacht $APP_GID)"
  [ -z "$R_GROUPS" ] || probleem "Groups $R_GROUPS"
  [ "$R_CAPBND" = "$NUL" ] || probleem "CapBnd $R_CAPBND"
fi

if [ "$modus" = --toon-rechten ]; then
  cat /proc/self/status
  [ -z "$problemen" ] || fout "rechtenwissel niet in orde: $problemen"
  exit 0
fi
[ -z "$problemen" ] || fout "rechtenwissel niet in orde ($problemen); /health niet gecontroleerd"
curl --noproxy localhost -fsS --max-time 8 -o /dev/null http://localhost:8096/health || fout "/health antwoordt niet met 200"
exit 0
