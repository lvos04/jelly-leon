"""Manifest volgens contract 1.2 §9 (JL2): poorten alleen in network.ports, geen joins_platform_network,
GPU als optionele wizardparameter met D08 en privileges.gpu als maximum."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_fork_consistency

REPO = Path(__file__).resolve().parents[3]
MANIFEST = (REPO / "deploy/manifest/jelly-leon.manifest.yaml").read_text(encoding="utf-8")


def test_real_manifest_follows_contract_1_2():
    assert check_fork_consistency.check_manifest_1_2(MANIFEST) == []


def test_real_manifest_has_gpu_as_optional_wizard_parameter():
    custom_app = check_fork_consistency.top_level_block(MANIFEST, "custom_app")
    assert check_fork_consistency._scalar(custom_app, "gpu") == "{param: gpu}"
    gpu = check_fork_consistency.parameter_block(MANIFEST, "gpu")
    assert gpu is not None and "default:" not in gpu, "wizardparameter zonder default (ontbreekt → none)"
    privileges = check_fork_consistency.top_level_block(MANIFEST, "privileges")
    assert check_fork_consistency._scalar(privileges, "gpu") == "intel_render"
    assert "privileged: false" in privileges and "cap_add: []" in privileges and "devices: []" in privileges


def test_real_manifest_keeps_existing_jellyfin_untouched_and_uses_no_example_values():
    assert "/mnt/" not in MANIFEST and "tank" not in MANIFEST.lower()
    assert "D07" in MANIFEST  # een eventuele stock-Jellyfin meet de wizard (D07); die blijft op zijn eigen poort
    host_port = check_fork_consistency.parameter_block(MANIFEST, "host_port")
    assert host_port is not None and "default: 30460" in host_port


LEGACY_PORTS = """custom_app:
  ports:
    - name: web
      container_port: 8096
      host_port: {param: host_port}
      protocol: tcp
"""


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda t: t.replace("  host_network_reason: null\n", "  host_network_reason: null\n  joins_platform_network: false\n"),
         "joins_platform_network is vervallen"),
        (lambda t: t.replace("custom_app:\n", LEGACY_PORTS, 1), "custom_app.ports is vervallen"),
        (lambda t: t.replace("  # Maximum:", "  # Maximum (test):").replace("  gpu: intel_render\n", "  gpu: none\n"),
         "privileges.gpu (het maximum) is niet intel_render"),
        (lambda t: t.replace("decisions_required: [D01, D02, D03, D07, D08, D15, D16]",
                             "decisions_required: [D01, D02, D03, D07, D15, D16]"), "vereist D08"),
        (lambda t: t.replace("    decision: D08\n    required: false\n", "    decision: D08\n    required: true\n"),
         "GPU-parameter 'gpu' moet"),
        (lambda t: t.replace("    type: gpu\n    source: wizard\n", "    type: gpu\n    source: default\n"),
         "GPU-parameter 'gpu' moet"),
        (lambda t: t.replace("  gpu: {param: gpu}\n", "  gpu: {param: grafisch}\n"), "geen parameter"),
        (lambda t: t.replace("  gpu: {param: gpu}\n", "  gpu: nvidia\n"), "moet none, intel_render"),
        (lambda t: t.replace("  gpu: intel_render\n", "  gpu: all\n"), "privileges.gpu moet none of intel_render"),
    ],
)
def test_contract_1_2_violations_are_detected(mutate, fragment):
    mutated = mutate(MANIFEST)
    assert mutated != MANIFEST, "mutatie moet het manifest veranderen"
    errors = check_fork_consistency.check_manifest_1_2(mutated)
    assert any(fragment in e for e in errors), errors


def test_gpu_none_without_parameter_is_allowed():
    text = MANIFEST.replace("  gpu: {param: gpu}\n", "  gpu: none\n")
    assert check_fork_consistency.check_manifest_1_2(text) == []
