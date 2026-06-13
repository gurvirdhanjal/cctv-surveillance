"""Site Readiness Report -- generates a one-page PDF per site."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_TIER_COLOURS = {
    "FULL": colors.HexColor("#28a745"),
    "MID": colors.HexColor("#ffc107"),
    "LOW": colors.HexColor("#dc3545"),
}


def generate_readiness_report(
    camera_rows: list[dict[str, Any]],
    site_name: str = "Plant Site",
) -> bytes:
    """Return a PDF bytes object -- the Site Readiness Report.

    *camera_rows* is a list of dicts with keys:
      camera_id, name, capability_tier, shutter_type, tier_reason, profile_data
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph("<b>VMS Site Readiness Report</b>", styles["Title"]))
    story.append(Paragraph(f"Site: {site_name} · Generated: {now}", styles["Normal"]))
    story.append(Spacer(1, 8 * mm))

    tiers = [r.get("capability_tier", "FULL") for r in camera_rows]
    full_n = tiers.count("FULL")
    mid_n = tiers.count("MID")
    low_n = tiers.count("LOW")
    story.append(
        Paragraph(
            f"<b>Summary:</b> {len(camera_rows)} cameras -- "
            f"FULL: {full_n} | MID: {mid_n} | LOW: {low_n}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 5 * mm))

    header = ["Camera", "Tier", "Resolution", "FPS", "Focus", "Shutter", "Why"]
    table_data: list[list[str]] = [header]

    for row in camera_rows:
        pd = row.get("profile_data")
        resolution = (
            f"{pd.resolution_w}x{pd.resolution_h}"
            if pd and pd.resolution_w and pd.resolution_h
            else "--"
        )
        fps_str = f"{pd.fps_measured:.1f}" if pd and pd.fps_measured is not None else "--"
        focus_str = f"{pd.focus_score:.0f}" if pd and pd.focus_score is not None else "--"
        tier = str(row.get("capability_tier", "FULL"))
        table_data.append(
            [
                str(row.get("name", "")),
                tier,
                resolution,
                fps_str,
                focus_str,
                str(row.get("shutter_type", "unknown")),
                str(row.get("tier_reason", ""))[:60],
            ]
        )

    col_widths = [45 * mm, 14 * mm, 28 * mm, 14 * mm, 14 * mm, 20 * mm, None]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    tier_style: list[Any] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#343a40")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dee2e6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, row in enumerate(camera_rows, start=1):
        tier = str(row.get("capability_tier", "FULL"))
        tier_col = _TIER_COLOURS.get(tier, colors.grey)
        tier_style.append(("BACKGROUND", (1, i), (1, i), tier_col))
        tier_style.append(("TEXTCOLOR", (1, i), (1, i), colors.white))
        tier_style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))

    tbl.setStyle(TableStyle(tier_style))
    story.append(tbl)

    story.append(Spacer(1, 15 * mm))
    story.append(
        Paragraph(
            "Customer acceptance: by signing below you confirm this report "
            "reflects the actual camera deployment at your site.",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 8 * mm))
    sig_data = [
        ["Customer Signature:", "_" * 40, "Date:", "_" * 20],
        ["Print Name:", "_" * 40, "Role:", "_" * 20],
    ]
    sig_tbl = Table(sig_data, colWidths=[35 * mm, 75 * mm, 20 * mm, 45 * mm])
    sig_tbl.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(sig_tbl)

    doc.build(story)
    return buffer.getvalue()
