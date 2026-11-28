#!/usr/bin/env bash
# Alleen de kopie in de proefcontext verliest één hash. Een netwerk- of bouwfout telt niet als bewijs.
set -euo pipefail
werk=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:?}}/hashproef.XXXXXXXX")
trap 'rm -rf -- "$werk"' EXIT
mkdir -p "$werk/deploy/allinone" "$werk/tools"
cp deploy/allinone/Dockerfile "$werk/deploy/allinone/"
cp -R tools/analysewerker "$werk/tools/"
python3 - "$werk/tools/analysewerker/requirements.lock" <<'PY'
from pathlib import Path
import re
import sys

pad = Path(sys.argv[1])
tekst, aantal = re.subn(r" --hash=sha256:[a-f0-9]{64}", "", pad.read_text(), count=1)
if aantal != 1:
    sys.exit("Geen hash aangetroffen voor de negatieve proef.")
pad.write_text(tekst)
PY
if docker buildx build -f "$werk/deploy/allinone/Dockerfile" --target analysepython \
        --progress=plain --output=type=cacheonly "$werk" > "$werk/bouw.log" 2>&1; then
    echo 'De bouw accepteerde een distributie zonder hash.' >&2
    exit 1
fi
if ! grep -Fq 'Hashes are required in --require-hashes mode' "$werk/bouw.log"; then
    tail -n 20 "$werk/bouw.log" >&2
    exit 1
fi
echo 'De productie-Dockerfile weigert de requirements-regel zonder hash.'
