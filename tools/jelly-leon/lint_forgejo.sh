#!/usr/bin/env bash
# Actionlint herkent workflowaanroepen onder .github en actions in eigenaar/repo-notatie.
set -euo pipefail
shellcheck tools/jelly-leon/{lint_forgejo,publiceer_image,test_forktools,test_plugins}.sh
actionlint .github/workflows/jelly-leon-ci.yml .github/workflows/upstream-sync.yml
lintmap=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:?}}/workflowlint.XXXXXXXX")
trap 'rm -rf -- "$lintmap"' EXIT
git -C "$lintmap" init -q
mkdir -p "$lintmap/.github/workflows"
for workflow in .forgejo/workflows/*.yml; do
    sed -E '/uses:/ { s@https://(data\.forgejo\.org|github\.com)/@@; s@\./\.forgejo/workflows/@./.github/workflows/@; }' \
        "$workflow" > "$lintmap/.github/workflows/${workflow##*/}"
done
(cd "$lintmap" && actionlint .github/workflows/*.yml)
printf 'Bronworkflows en Forgejo-workflows gecontroleerd.\n'
