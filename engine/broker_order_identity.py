"""Canonical broker-side identity markers for LGE-created orders.

The marker is intentionally stored in broker-visible metadata while UI-facing
text stays clean. SQLite ``source`` remains the authoritative origin; the
broker marker is an additional recovery and diagnostics hint.
"""

from __future__ import annotations

import re

ORDER_CONTROL_MODE_MANUAL = "MANUAL"
ORDER_CONTROL_MODE_SEMI = "SEMI"
ORDER_CONTROL_MODE_AUTO = "AUTO"
ORDER_CONTROL_MODES = frozenset(
    {
        ORDER_CONTROL_MODE_MANUAL,
        ORDER_CONTROL_MODE_SEMI,
        ORDER_CONTROL_MODE_AUTO,
    }
)

_ORDER_MODE_CODE = {
    ORDER_CONTROL_MODE_MANUAL: "M",
    ORDER_CONTROL_MODE_SEMI: "S",
    ORDER_CONTROL_MODE_AUTO: "A",
}
_ORDER_MODE_BY_CODE = {code: mode for mode, code in _ORDER_MODE_CODE.items()}
_ORDER_PREFIX_RE = re.compile(
    r"^\[LGE:(?P<code>[MSA])](?:\s+(?P<display>.*))?$",
    re.DOTALL,
)
_ORDER_LEGACY_SUFFIX_RE = re.compile(
    r"^(?P<display>.*?)\s*\[LGE:(?P<code>[MSA])]\s*$",
    re.DOTALL,
)


def normalize_order_control_mode(
    control_mode: str | None,
    *,
    default: str = ORDER_CONTROL_MODE_MANUAL,
) -> str:
    """Return one canonical order control mode or raise for an unsafe value."""
    default_norm = str(default or "").strip().upper()

    if default_norm not in ORDER_CONTROL_MODES:
        raise ValueError(f"Unsupported default order control mode: {default}")

    mode = str(control_mode or default_norm).strip().upper()

    if mode not in ORDER_CONTROL_MODES:
        raise ValueError(f"Unsupported order control mode: {control_mode}")

    return mode


def parse_broker_order_comment(
    broker_comment: str | None,
) -> tuple[str, str | None]:
    """Return ``(display_comment, control_mode)`` from broker metadata.

    New orders use the canonical prefix. The previous suffix form is accepted
    only for backward-compatible recovery and is normalized to the prefix when
    the comment is written again.
    """
    text = str(broker_comment or "").strip()
    prefix_match = _ORDER_PREFIX_RE.fullmatch(text)

    if prefix_match is not None:
        display_comment = str(prefix_match.group("display") or "").strip()
        control_mode = _ORDER_MODE_BY_CODE[prefix_match.group("code")]
        return display_comment, control_mode

    suffix_match = _ORDER_LEGACY_SUFFIX_RE.fullmatch(text)

    if suffix_match is not None:
        display_comment = str(suffix_match.group("display") or "").rstrip()
        control_mode = _ORDER_MODE_BY_CODE[suffix_match.group("code")]
        return display_comment, control_mode

    return text, None


def strip_broker_order_identity(broker_comment: str | None) -> str:
    """Remove one recognized LGE identity marker for UI display."""
    display_comment, _control_mode = parse_broker_order_comment(broker_comment)
    return display_comment


def get_broker_order_control_mode(
    broker_comment: str | None,
) -> str | None:
    """Extract the canonical mode from one recognized LGE identity marker."""
    _display_comment, control_mode = parse_broker_order_comment(broker_comment)
    return control_mode


def build_broker_order_comment(
    display_comment: str | None,
    control_mode: str = ORDER_CONTROL_MODE_MANUAL,
) -> str:
    """Prepend an idempotent, explicit LGE mode prefix to a user comment."""
    mode = normalize_order_control_mode(control_mode)
    clean_comment = strip_broker_order_identity(display_comment)
    prefix = f"[LGE:{_ORDER_MODE_CODE[mode]}]"

    if not clean_comment:
        return prefix

    return f"{prefix} {clean_comment}"


def build_broker_operation_comment(
    broker_comment: str | None,
    operation: str,
    *,
    default_control_mode: str = ORDER_CONTROL_MODE_MANUAL,
) -> str:
    """Append one idempotent broker-operation marker to LGE metadata.

    The canonical mode prefix remains first so broker-side ownership and
    control mode stay machine-readable. The operation marker is diagnostic
    metadata and is not stored in the clean user comment.
    """
    operation_clean = str(operation or "").strip().upper()

    if not operation_clean or re.fullmatch(r"[A-Z0-9_]+", operation_clean) is None:
        raise ValueError(f"Unsupported broker order operation: {operation}")

    display_comment, parsed_mode = parse_broker_order_comment(broker_comment)
    mode = normalize_order_control_mode(
        parsed_mode,
        default=default_control_mode,
    )
    operation_suffix = f" | {operation_clean}"

    if display_comment.endswith(operation_suffix):
        clean_display = display_comment
    elif display_comment:
        clean_display = f"{display_comment}{operation_suffix}"
    else:
        clean_display = operation_clean

    return build_broker_order_comment(clean_display, mode)


def build_ctrader_order_label(
    control_mode: str = ORDER_CONTROL_MODE_MANUAL,
) -> str:
    """Return a stable cTrader label aligned with the broker comment marker."""
    mode = normalize_order_control_mode(control_mode)
    return f"LGE_{mode}"
