"""Manifest volgens contract 1.3 §9 (C1.3-JL-04): geen HUB_*-namen, monitorplan op /health, de open startwizard als
post_install_check en geaccepteerde waarschuwingen alleen met reden in het manifest (geen losse lijst in de CI)."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_fork_consistency

REPO = Path(__file__).resolve().parents[3]
MANIFEST = (REPO / "deploy/manifest/jelly-leon.manifest.yaml").read_text(encoding="utf-8")
WORKFLOW = (REPO / ".github/workflows/jelly-leon-ci.yml").read_text(encoding="utf-8")
MONITOR = "  monitor: {pad: /health, verwachte_status: 200, timeout_s: 10, interval_s: 60}\n"
HUB_PARAMETER = """parameters:
  - name: HUB_URL
    type: string
    source: wizard
    required: false
    description_nl: Mag niet (gereserveerd).
"""


def test_real_manifest_follows_contract_1_3():
    assert check_fork_consistency.check_manifest_1_3(MANIFEST) == []


def test_real_manifest_has_monitor_plan_on_upstream_health_route():
    assert MONITOR in MANIFEST
    healthcheck = check_fork_consistency.top_level_block(MANIFEST, "healthcheck")
    assert check_fork_consistency._scalar(healthcheck, "path") == "/health"  # upstream-conventie, §2.3 regel 9


def test_real_manifest_has_no_reserved_hub_names_and_no_env():
    assert "HUB_" not in MANIFEST.replace("HUB_*", "")  # alleen de uitleg in het commentaar noemt HUB_*
    custom_app = check_fork_consistency.top_level_block(MANIFEST, "custom_app")
    assert check_fork_consistency._scalar(custom_app, "env") == "[]"


def test_real_manifest_names_the_open_startup_wizard_as_manual_check():
    checks = check_fork_consistency.top_level_block(MANIFEST, "post_install_checks")
    assert checks is not None and "- id: startwizard_afronden" in checks and "soort: handmatig" in checks
    assert "beheerdersaccount" in checks
    assert "Emby blijft" in checks  # besluit: Emby blijft ongewijzigd draaien


def test_real_manifest_accepts_only_the_pending_digest_with_reason():
    accepted = check_fork_consistency.top_level_block(MANIFEST, "accepted_findings")
    assert accepted is not None and accepted.count("- code:") == 1
    assert "- code: digest_pending_release" in accepted and "reden_nl:" in accepted
    image = check_fork_consistency.top_level_block(MANIFEST, "image")
    assert check_fork_consistency._scalar(image, "digest") == "null"  # nog geen release (ADR-0005)


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda t: t.replace("platformcontract 1.3 §9", "platformcontract 1.2 §9", 1), "kopregel"),
        (lambda t: t.replace("parameters:\n", HUB_PARAMETER, 1), "HUB_URL in parameters"),
        (lambda t: t.replace("  env: []\n", "  env:\n    - name: HUB_KEY_FINGERPRINT\n      value: x\n"),
         "HUB_KEY_FINGERPRINT in custom_app"),
        (lambda t: t.replace("  env: []\n", "  env:\n    - name: hub_url\n      value: x\n"), "hub_url in custom_app"),
        (lambda t: t.replace(MONITOR, ""), "healthcheck.monitor ontbreekt"),
        (lambda t: t.replace("{pad: /health,", "{pad: /System/Info/Public,"), "monitor.pad moet /health"),
        (lambda t: t.replace("  path: /health\n", "  path: /healthz\n"), "gelijk aan healthcheck.path"),
        (lambda t: t.replace("verwachte_status: 200", "verwachte_status: 204"), "verwachte_status moet 200"),
        (lambda t: t.replace("timeout_s: 10, interval_s: 60}", "timeout_s: 10, interval_s: 0}"),
         "monitor.interval_s moet een positief geheel getal"),
        (lambda t: t.replace(", interval_s: 60}", "}"), "moet precies pad, verwachte_status, timeout_s, interval_s"),
        (lambda t: t.replace("  - id: startwizard_afronden\n", "  - id: iets_anders\n"), "mist 'startwizard_afronden'"),
        (lambda t: t.replace("    soort: handmatig\n", "    soort: automatisch\n"), "soort moet http of handmatig"),
        (lambda t: t.replace("  - code: digest_pending_release\n", "  - code: deprecated_field\n"),
         "staat niet in de vaste lijst"),
        (lambda t: t.replace("  - code: digest_pending_release\n", "  - code: backup_db_export_none\n"),
         "image.digest is nog leeg"),
        (lambda t: t.replace("  digest: null\n", '  digest: "sha256:' + "a" * 64 + '"\n'), "image.digest is ingevuld"),
    ],
)
def test_contract_1_3_violations_are_detected(mutate, fragment):
    mutated = mutate(MANIFEST)
    assert mutated != MANIFEST, "mutatie moet het manifest veranderen"
    errors = check_fork_consistency.check_manifest_1_3(mutated)
    assert any(fragment in e for e in errors), errors


def test_missing_reason_and_duplicate_code_are_detected():
    start = MANIFEST.index("accepted_findings:")
    end = MANIFEST.index("compatibility:")
    zonder_reden = MANIFEST[:start] + "accepted_findings:\n  - code: digest_pending_release\n" + MANIFEST[end:]
    assert any("reden_nl ontbreekt" in e for e in check_fork_consistency.check_manifest_1_3(zonder_reden))
    dubbel = MANIFEST[:end] + "  - code: digest_pending_release\n    reden_nl: nog een keer\n" + MANIFEST[end:]
    assert any("dubbel" in e for e in check_fork_consistency.check_manifest_1_3(dubbel))


def test_released_manifest_without_accepted_findings_is_allowed():
    start = MANIFEST.index("accepted_findings:")
    end = MANIFEST.index("compatibility:")
    released = (MANIFEST[:start] + MANIFEST[end:]).replace("  digest: null\n", '  digest: "sha256:' + "b" * 64 + '"\n')
    assert check_fork_consistency.check_manifest_1_3(released) == []


def test_ci_validates_strict_without_a_separate_exception_list():
    """De CI-job `manifest` draait de validator van de eigenaar met --strict op een commit die contract 1.3 kent, en
    kent geen eigen lijst met toegestane waarschuwingen meer (contract 1.3 §9)."""
    job = WORKFLOW[WORKFLOW.index("\n  manifest:\n") : WORKFLOW.index("\n  server:\n")]
    assert "appstore.manifest.cli validate --strict" in job
    assert "manifest_rapport.py --rapport" in job
    assert "--toegestaan" not in WORKFLOW
    assert "APPSTORE_COMMIT: bd33052cd0174be08fbf6324f1caf296257182d3" not in WORKFLOW  # validator van vóór 1.3
    assert 'test "$validator_rc" -eq 0' in job  # ook de exitcode van de validator telt


def _form_row(document: str, field: str) -> str | None:
    """De tabelregel van het formulier in deploy/truenas/CUSTOM_APP.md waarin dit veld staat (of None)."""
    for line in document.splitlines():
        if line.startswith("|") and field in line:
            return line
    return None


def test_install_document_has_the_form_fields_that_the_translation_fills():
    """CUSTOM_APP.md zegt "dezelfde velden" te beschrijven als de vertaling van het manifest naar het formulier
    (appstore-en-fork, docs/TRUENAS_APP_VALUES.md: Portals uit custom_app.portal, Disable Builtin Healthcheck altijd
    false). Wie het document handmatig volgt, mag geen van beide missen (review S-P2-800, R-MANIFEST-2)."""
    document = (REPO / "deploy/truenas/CUSTOM_APP.md").read_text(encoding="utf-8")
    healthcheck_row = _form_row(document, "Disable Builtin Healthcheck")
    assert healthcheck_row is not None, "rij 'Disable Builtin Healthcheck' ontbreekt"
    assert "**uit**" in healthcheck_row and "ADR-0014" in healthcheck_row

    custom_app = check_fork_consistency.top_level_block(MANIFEST, "custom_app")
    portal = custom_app[custom_app.index("\n  portal:\n") :] if custom_app else ""
    name = check_fork_consistency._scalar(portal, "name", indent=4)
    scheme = check_fork_consistency._scalar(portal, "scheme", indent=4)
    path = check_fork_consistency._scalar(portal, "path", indent=4)
    assert (name, scheme, path) == ("Jelly Leon", "http", "/"), "manifest custom_app.portal veranderd: document nalopen"
    portal_row = _form_row(document, "Portal Configuration")
    assert portal_row is not None, "rij 'Portal Configuration' ontbreekt"
    assert f"Name `{name}`" in portal_row and f"Path `{path}`" in portal_row
    assert f"Protocol *{scheme.upper()}*" in portal_row and "Host Port" in portal_row


def test_gpu_texts_name_every_device_group_the_entrypoint_adds():
    """De entrypoint voegt de groep toe van elk aanwezig /dev/dri-apparaat uit zijn lus (renderD* én card*). Het
    manifest (privilege_reason), het installatiedocument (rij GPU Configuration) en de kop van de entrypoint zelf
    moeten elk patroon noemen, zodat niemand denkt dat alleen de render-node rechten krijgt (S-P2-800, KLEIN-74)."""
    entrypoint = (REPO / "deploy/allinone/entrypoint.sh").read_text(encoding="utf-8")
    lus = next(line for line in entrypoint.splitlines() if line.startswith("for node in /dev/dri/"))
    patronen = [woord.rstrip(";") for woord in lus.split() if woord.startswith("/dev/dri/")]
    assert patronen == ["/dev/dri/renderD*", "/dev/dri/card*"], "lus veranderd: teksten nalopen"

    reden = " ".join(check_fork_consistency.top_level_block(MANIFEST, "privilege_reason").split())
    document = (REPO / "deploy/truenas/CUSTOM_APP.md").read_text(encoding="utf-8")
    gpu_rij = _form_row(document, "GPU Configuration")
    assert gpu_rij is not None, "rij 'GPU Configuration' ontbreekt"
    kop = " ".join(line.lstrip("# ") for line in entrypoint.split("\nset ", 1)[0].splitlines())
    for patroon in patronen:
        assert patroon in reden, f"manifest privilege_reason noemt {patroon} niet"
        assert patroon in gpu_rij, f"CUSTOM_APP.md (GPU Configuration) noemt {patroon} niet"
        assert patroon in kop, f"kopcommentaar van entrypoint.sh noemt {patroon} niet"
