"""Satellite imagery viewer page."""

import sqlite3
from pathlib import Path

import streamlit as st
from PIL import Image

from db.repository import get_imagery
from src.models import FieldPolygon


IMAGE_TYPE_LABELS = {
    "true_color": "True color (RGB)",
    "false_color": "False color (NIR)",
    "ndvi_map": "NDVI map",
    "ndwi_map": "NDWI map",
}


def render_imagery(conn: sqlite3.Connection, field: FieldPolygon) -> None:
    st.header("Satellite imagery")

    all_images = get_imagery(conn, field.field_id)

    if not all_images:
        st.info(
            "No imagery available yet. "
            "Run a data fetch to download satellite images."
        )
        return

    # Get available dates
    dates = sorted(set(img.image_date for img in all_images), reverse=True)

    selected_date = st.selectbox("Image date", dates)

    # Filter images for selected date
    date_images = [img for img in all_images if img.image_date == selected_date]
    image_types = {img.image_type: img for img in date_images}

    # Display in 2x2 grid
    col1, col2 = st.columns(2)

    for i, (img_type, label) in enumerate(IMAGE_TYPE_LABELS.items()):
        col = col1 if i % 2 == 0 else col2

        with col:
            st.subheader(label)
            if img_type in image_types:
                img_record = image_types[img_type]
                path = Path(img_record.file_path)
                if path.exists():
                    img = Image.open(str(path))
                    st.image(img, use_container_width=True)
                else:
                    st.warning(f"Image file not found: {path.name}")
            else:
                st.info("Not available for this date")

    # Date comparison
    if len(dates) >= 2:
        st.divider()
        st.subheader("Compare dates")
        comp_col1, comp_col2 = st.columns(2)

        with comp_col1:
            date_a = st.selectbox("Date A", dates, index=0, key="date_a")
        with comp_col2:
            date_b = st.selectbox("Date B", dates, index=min(1, len(dates) - 1), key="date_b")

        if date_a != date_b:
            comp_type = st.selectbox(
                "Image type to compare",
                list(IMAGE_TYPE_LABELS.keys()),
                format_func=lambda k: IMAGE_TYPE_LABELS[k],
            )

            img_col1, img_col2 = st.columns(2)
            for col, d in [(img_col1, date_a), (img_col2, date_b)]:
                with col:
                    st.caption(d)
                    matches = [
                        img for img in all_images
                        if img.image_date == d and img.image_type == comp_type
                    ]
                    if matches and Path(matches[0].file_path).exists():
                        st.image(
                            Image.open(matches[0].file_path),
                            use_container_width=True,
                        )
                    else:
                        st.info("Not available")
