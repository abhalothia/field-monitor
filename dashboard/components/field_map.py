"""Folium map component with field polygon overlay."""

import folium
import streamlit as st
from streamlit_folium import st_folium


def render_field_map(
    center_lat: float,
    center_lon: float,
    polygon_geojson: dict,
    field_name: str,
    health_score: float | None = None,
    height: int = 400,
) -> None:
    """Render a Folium map with the field polygon overlay."""
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=17,
        tiles="Esri.WorldImagery",
        attr="Esri",
    )

    # Color based on health score
    if health_score is not None:
        if health_score < 25:
            color = "#2ca02c"  # green
        elif health_score < 50:
            color = "#f0ad4e"  # yellow-orange
        elif health_score < 75:
            color = "#d9534f"  # red
        else:
            color = "#8b0000"  # dark red
    else:
        color = "#1f77b4"  # default blue

    # Wrap as FeatureCollection for GeoJson layer
    geojson_feature = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": polygon_geojson,
            "properties": {"name": field_name},
        }],
    }

    folium.GeoJson(
        geojson_feature,
        name=field_name,
        style_function=lambda _: {
            "fillColor": color,
            "color": color,
            "weight": 3,
            "fillOpacity": 0.25,
        },
        tooltip=field_name,
    ).add_to(m)

    st_folium(m, width=None, height=height, returned_objects=[])
