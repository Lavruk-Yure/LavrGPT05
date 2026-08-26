"""Synthetic broker-order comment identity check."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_order_identity import (  # noqa: E402
    ORDER_CONTROL_MODE_AUTO,
    ORDER_CONTROL_MODE_MANUAL,
    ORDER_CONTROL_MODE_SEMI,
    build_broker_operation_comment,
    build_broker_order_comment,
    build_ctrader_order_label,
    get_broker_order_control_mode,
    normalize_order_control_mode,
    parse_broker_order_comment,
    strip_broker_order_identity,
)


def main() -> int:
    manual = build_broker_order_comment("Night test", "MANUAL")
    semi = build_broker_order_comment("Night test", "SEMI")
    auto = build_broker_order_comment("Night test", "AUTO")
    empty_manual = build_broker_order_comment("", "MANUAL")
    retagged = build_broker_order_comment(manual, "AUTO")
    modified_ref = build_broker_operation_comment(manual, "SLTP_MODIFY")
    modified_ref_again = build_broker_operation_comment(
        modified_ref,
        "SLTP_MODIFY",
    )

    assert manual == "[LGE:M] Night test"
    assert semi == "[LGE:S] Night test"
    assert auto == "[LGE:A] Night test"
    assert empty_manual == "[LGE:M]"
    assert retagged == "[LGE:A] Night test"
    assert modified_ref == "[LGE:M] Night test | SLTP_MODIFY"
    assert modified_ref_again == modified_ref

    assert parse_broker_order_comment(manual) == (
        "Night test",
        ORDER_CONTROL_MODE_MANUAL,
    )
    assert parse_broker_order_comment(semi) == (
        "Night test",
        ORDER_CONTROL_MODE_SEMI,
    )
    assert parse_broker_order_comment(auto) == (
        "Night test",
        ORDER_CONTROL_MODE_AUTO,
    )
    assert parse_broker_order_comment("legacy comment") == (
        "legacy comment",
        None,
    )
    assert parse_broker_order_comment("Night test [LGE:S]") == (
        "Night test",
        ORDER_CONTROL_MODE_SEMI,
    )
    assert build_broker_order_comment("Night test [LGE:S]", "AUTO") == (
        "[LGE:A] Night test"
    )
    assert strip_broker_order_identity(auto) == "Night test"
    assert get_broker_order_control_mode(auto) == ORDER_CONTROL_MODE_AUTO
    assert normalize_order_control_mode("semi") == ORDER_CONTROL_MODE_SEMI

    assert build_ctrader_order_label("MANUAL") == "LGE_MANUAL"
    assert build_ctrader_order_label("SEMI") == "LGE_SEMI"
    assert build_ctrader_order_label("AUTO") == "LGE_AUTO"

    try:
        normalize_order_control_mode("UNKNOWN")
    except ValueError:
        invalid_mode_rejected = True
    else:
        invalid_mode_rejected = False

    assert invalid_mode_rejected

    print("Broker order identity result")
    print("  manual_prefix=[LGE:M]")
    print("  semi_prefix=[LGE:S]")
    print("  auto_prefix=[LGE:A]")
    print("  display_comment=Night test")
    print("  idempotent_retag=True")
    print(f"  modify_order_ref={modified_ref}")
    print("  idempotent_operation_marker=True")
    print("  invalid_mode_rejected=True")
    print("BROKER_ORDER_IDENTITY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
