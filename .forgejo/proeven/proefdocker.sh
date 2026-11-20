#!/bin/sh
# Met dit label kan een afgebroken proef uitsluitend haar eigen containers terugvinden.
set -eu
case "$1" in
    run|create) opdracht=$1; shift; exec /usr/bin/docker "$opdracht" --label "nl.medialeon.jelly-leon.proef=$JL_PROEFVOLUME" "$@" ;;
    rm) shift; exec /usr/bin/docker rm -v "$@" ;;
    *) exec /usr/bin/docker "$@" ;;
esac
