"""Safe helper tool implementations used before arbitrary generated Python."""

from __future__ import annotations

from . import live_preview


def nudge_selected_up(context, distance=0.25):
    return live_preview.apply_location_delta(
        context,
        (0.0, 0.0, float(distance)),
        label="Nudge selected objects up",
    )


HELPER_TOOLS = {
    "nudge_selected_up": {
        "description": "Move selected objects upward immediately with preview rollback support",
        "live_preview": True,
        "function": nudge_selected_up,
    }
}


def register():
    pass


def unregister():
    pass

