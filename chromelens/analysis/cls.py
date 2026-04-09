"""Best-effort CLS culprit extraction helpers."""

from __future__ import annotations

from chromelens.artifacts.models import CLSCulpritArtifact, CLSShiftArtifact


def build_cls_shift_artifacts(raw_shifts: list[dict]) -> list[CLSShiftArtifact]:
    """Convert browser-collected layout shift payloads into stable artifacts."""
    shifts: list[CLSShiftArtifact] = []
    for raw_shift in raw_shifts:
        culprits: list[CLSCulpritArtifact] = []
        for raw_culprit in raw_shift.get("sources", []):
            selector = str(raw_culprit.get("selector", "") or "")
            tag_name = str(raw_culprit.get("tag_name", "") or "")
            node_id = str(raw_culprit.get("node_id", "") or "")
            element_id = str(raw_culprit.get("element_id", "") or "")
            classes = [str(value) for value in raw_culprit.get("classes", [])]
            confidence = "high" if selector else "medium" if tag_name or element_id or node_id or classes else "low"
            reason = "selector available from LayoutShift source" if selector else "partial node metadata only" if (tag_name or element_id or node_id or classes) else "no culprit metadata available"
            culprits.append(
                CLSCulpritArtifact(
                    selector=selector,
                    node_id=node_id,
                    tag_name=tag_name,
                    element_id=element_id,
                    classes=classes,
                    previous_rect=_coerce_rect(raw_culprit.get("previous_rect")),
                    current_rect=_coerce_rect(raw_culprit.get("current_rect")),
                    confidence=confidence,
                    reason=reason,
                )
            )

        shifts.append(
            CLSShiftArtifact(
                timestamp_ms=float(raw_shift.get("timestamp_ms", 0.0)),
                score=float(raw_shift.get("value", 0.0)),
                had_recent_input=bool(raw_shift.get("had_recent_input", False)),
                culprits=culprits,
            )
        )

    return sorted(shifts, key=lambda item: item.score, reverse=True)


def _coerce_rect(raw_rect: object) -> dict[str, float]:
    if not isinstance(raw_rect, dict):
        return {}
    return {
        "x": float(raw_rect.get("x", 0.0) or 0.0),
        "y": float(raw_rect.get("y", 0.0) or 0.0),
        "width": float(raw_rect.get("width", 0.0) or 0.0),
        "height": float(raw_rect.get("height", 0.0) or 0.0),
    }
