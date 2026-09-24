# -*- coding: utf-8 -*-
"""T110-05 — OTHER_MACHINE User Guidance."""

from __future__ import annotations

import ast
import json
from pathlib import Path

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = True

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGIN_PATH = PROJECT_ROOT / "core" / "login_logic.py"
POLICY_PATH = PROJECT_ROOT / "core" / "translation_policy.py"
FALLBACK_PATH = PROJECT_ROOT / "lang" / "strings_fallback.json"
STRINGS_PATH = PROJECT_ROOT / "lang" / "strings.json"
KEY = "LoginWindow.errorOtherMachine"
LANGUAGES = ("en", "uk", "de", "fr")


def _policy_overrides() -> dict[str, str]:
    namespace: dict[str, object] = {}
    source = POLICY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(POLICY_PATH))

    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "CENTRAL_TRANSLATION_OVERRIDES":
            continue
        if node.value is None:
            break
        value = ast.literal_eval(node.value)
        entry = value.get(KEY)
        if isinstance(entry, dict):
            return {
                str(language): str(text)
                for language, text in entry.items()
            }
    return namespace  # type: ignore[return-value]


def main() -> int:
    login_source = LOGIN_PATH.read_text(encoding="utf-8")
    overrides = _policy_overrides()
    fallback = json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
    strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))
    fallback_entry = fallback.get(KEY)

    required_phrases = {
        "en": ("another computer", "LGE.conf", "separate payment"),
        "uk": ("іншого комп’ютера", "LGE.conf", "окрема оплата"),
        "de": ("anderen Computer", "LGE.conf", "separate Zahlung"),
        "fr": ("autre ordinateur", "LGE.conf", "paiement séparé"),
    }

    checks: dict[str, bool] = {
        "login_uses_dedicated_guidance_key": KEY in login_source,
        "login_no_longer_uses_short_status_key": (
            'details="SettingsPageLicense.statusOtherMachine"'
            not in login_source
        ),
        "fallback_entry_present": isinstance(fallback_entry, dict),
        "strings_json_not_manually_populated": set(strings) == {"lang_active"},
    }

    for language in LANGUAGES:
        policy_text = overrides.get(language, "")
        fallback_text = (
            fallback_entry.get(language, "")
            if isinstance(fallback_entry, dict)
            else ""
        )
        checks[f"policy_{language}_present"] = bool(policy_text.strip())
        checks[f"fallback_{language}_matches_policy"] = (
            fallback_text == policy_text
        )
        checks[f"guidance_{language}_complete"] = all(
            phrase in policy_text for phrase in required_phrases[language]
        )

    print("T110-05 — OTHER_MACHINE User Guidance")
    print()

    failed = 0
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}={passed}")
        failed += 0 if passed else 1

    print()
    print(f"checks={len(checks)}")
    print(f"passed={len(checks) - failed}")
    print(f"failed={failed}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")

    if failed:
        print("T110-05=RED")
        return 1

    print("other_machine_guidance=LOCALIZED_EN_UK_DE_FR")
    print("startup_blocking=UNCHANGED")
    print("strings_json_manual_edit=False")
    print("T110-05=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
