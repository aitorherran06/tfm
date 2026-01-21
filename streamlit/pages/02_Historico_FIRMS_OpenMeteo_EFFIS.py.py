import os
import json

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import pydeck as pdk
import geopandas as gpd

# =========================================================
# CONFIGURACIÓN DE RUTAS (PORTABLE – LOCAL + STREAMLIT CLOUD)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Raíz del proyecto (tfm/)
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(
    page_title="Histórico FIRMS + Open-Meteo + EFFIS – Incendios España",
    layout="wide",
)

st.title("🔥 Incendios en España – FIRMS + Open-Meteo + EFFIS")

st.markdown(
    """
Esta web combina tres fuentes:
- **FIRMS (NASA, satélite)**: detecciones térmicas (posibles focos).
- **Open-Meteo**: meteorología (temperatura, humedad, etc.).
- **EFFIS (Copernicus)**: área quemada e incendios (polígonos).

**Dos niveles de datos**:
- **Evento**: cada fila = una detección FIRMS (punto en el mapa).
- **Provincia–día**: cada fila = una provincia en un día (valores agregados).
"""
)

# =========================================================
# 📂 CARGA DE DATOS
# =========================================================
@st.cache_data(show_spinner=True)
def load_data():
    path_clean = os.path.join(DATA_DIR, "fires_openmeteo_effis_clean.csv")
    path_daily = os.path.join(DATA_DIR, "prov_daily_viz.csv")
    path_events = os.path.join(DATA_DIR, "events_viz.csv")
    path_prov_geo = os.path.join(DATA_DIR, "gadm41_ESP_2.json")

    df_clean = pd.read_csv(path_clean, low_memory=False)
    if "firms_date" in df_clean.columns:
        df_clean["firms_date"] = pd.to_datetime(df_clean["firms_date"], errors="coerce")
        df_clean["year"] = df_clean["firms_date"].dt.year
        df_clean["date_only"] = df_clean["firms_date"].dt.date
    if "provincia" in df_clean.columns:
        df_clean["provincia"] = df_clean["provincia"].astype(str).str.strip()

    df_daily = pd.read_csv(path_daily, parse_dates=["date"])
    df_daily["provincia"] = df_daily["provincia"].astype(str).str.strip()
    df_daily["year"] = df_daily["date"].dt.year
    df_daily["month"] = df_daily["date"].dt.month

    df_events = pd.read_csv(path_events, parse_dates=["firms_date"])
    df_events["provincia"] = df_events["provincia"].astype(str).str.strip()

    gdf_prov = gpd.read_file(path_prov_geo)[["NAME_2", "geometry"]]
    gdf_prov = gdf_prov.rename(columns={"NAME_2": "provincia"})

    return df_clean, df_daily, df_events, gdf_prov, path_clean


try:
    df_clean, df_daily, df_events, gdf_prov, csv_path_used = load_data()
except Exception as e:
    st.error(f"❌ Error cargando los datos:\n\n{e}")
    st.stop()


# =========================================================
# AUXILIAR: normalizar nombres de provincia
# =========================================================
def norm_nombre(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.lower()
        .str.strip()
    )


# =========================================================
# AUX: histograma agregado (server-side) para no petar Altair
# =========================================================
def hist_counts(series: pd.Series, bins: int = 50) -> pd.DataFrame:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return pd.DataFrame(columns=["bin_left", "bin_right", "count"])
    counts, edges = np.histogram(s, bins=bins)
    return pd.DataFrame({"bin_left": edges[:-1], "bin_right": edges[1:], "count": counts})


# =========================================================
# AUX: auto-elegir transformación para FRP (para que se entienda sin filtros)
# =========================================================
def choose_frp_transform(series: pd.Series):
    """
    Decide automáticamente si mostrar FRP en escala normal o log1p.
    Criterio simple: si hay mucha asimetría (cola larga), usa log1p.
    """
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return s, "FRP (MW)", "No hay valores FRP válidos."

    p50 = float(np.nanpercentile(s, 50))
    p95 = float(np.nanpercentile(s, 95))
    p99 = float(np.nanpercentile(s, 99))

    if p50 > 0 and (p99 / p50) > 20:
        return (
            np.log1p(s),
            "FRP (log1p)",
            "FRP suele tener muchos valores pequeños y pocos muy grandes; por eso se muestra en escala log para que se vea la forma.",
        )
    if p50 == 0 and p95 > 0:
        return (
            np.log1p(s),
            "FRP (log1p)",
            "FRP tiene muchos ceros/valores pequeños y algunos grandes; se muestra en escala log para que se entienda mejor.",
        )
    return s, "FRP (MW)", "FRP se muestra en escala normal."


# =========================================================
# ✅ NUEVO: bins automáticos + recorte suave de outliers
# =========================================================
def auto_bins(series: pd.Series, min_bins: int = 30, max_bins: int = 60) -> int:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 50:
        return min_bins
    edges = np.histogram_bin_edges(s, bins="fd")  # Freedman–Diaconis
    bins = max(1, len(edges) - 1)
    return int(np.clip(bins, min_bins, max_bins))


def clip_quantiles(series: pd.Series, q_low: float = 0.005, q_high: float = 0.995) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return s
    lo, hi = s.quantile([q_low, q_high]).values
    return s[(s >= lo) & (s <= hi)]


# =========================================================
# SIDEBAR – FILTROS
# =========================================================
st.sidebar.header("🔎 Filtros")

provincias = sorted(df_daily["provincia"].dropna().unique().tolist())
prov_sel = st.sidebar.multiselect("Provincias", provincias, default=provincias)

min_date = df_daily["date"].min().date()
max_date = df_daily["date"].max().date()
date_range = st.sidebar.date_input(
    "Rango de fechas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    dmin, dmax = date_range
else:
    dmin, dmax = min_date, max_date

mask_daily = (
    df_daily["provincia"].isin(prov_sel)
    & (df_daily["date"].dt.date >= dmin)
    & (df_daily["date"].dt.date <= dmax)
)
df_daily_f = df_daily.loc[mask_daily].copy()

mask_events = (
    df_events["provincia"].isin(prov_sel)
    & (df_events["firms_date"].dt.date >= dmin)
    & (df_events["firms_date"].dt.date <= dmax)
)
df_events_f = df_events.loc[mask_events].copy()

if "firms_date" in df_clean.columns:
    mask_clean = (
        df_clean["provincia"].isin(prov_sel)
        & (df_clean["firms_date"].dt.date >= dmin)
        & (df_clean["firms_date"].dt.date <= dmax)
    )
else:
    mask_clean = df_clean["provincia"].isin(prov_sel)
df_clean_f = df_clean.loc[mask_clean].copy()

st.sidebar.markdown("---")
st.sidebar.write(f"📁 Provincia–día: **{len(df_daily_f):,}**")
st.sidebar.write(f"🔥 Eventos (events_viz): **{len(df_events_f):,}**")
st.sidebar.write(f"🛰️ Eventos (clean): **{len(df_clean_f):,}**")

if df_daily_f.empty:
    st.warning("No hay datos provincia–día con los filtros seleccionados.")
    st.stop()

# Brillo (solo evento)
st.sidebar.markdown("### Brillo (evento)")
if "firms_brightness" in df_clean_f.columns and not df_clean_f.empty:
    br_min = float(df_clean_f["firms_brightness"].min())
    br_max = float(df_clean_f["firms_brightness"].max())
    br_range = st.sidebar.slider(
        "Rango de brightness",
        min_value=br_min,
        max_value=br_max,
        value=(br_min, br_max),
    )
    df_clean_f = df_clean_f[
        (df_clean_f["firms_brightness"] >= br_range[0])
        & (df_clean_f["firms_brightness"] <= br_range[1])
    ]

with st.sidebar.expander("🧾 Glosario"):
    st.markdown(
        """
- **Brightness**: intensidad térmica del píxel (temperatura de brillo en infrarrojo)
- **FRP**: potencia radiativa (MW)
- **firms_count**: nº detecciones por provincia–día
- **effis_area_ha**: severidad acumulada (polígonos)
"""
    )

# =========================================================
# PESTAÑAS PRINCIPALES
# =========================================================
tab_overview, tab_daily = st.tabs(["🛰️ Nivel evento", "📊 Provincia–día"])


# =========================================================
# 1) TAB EVENTO
# =========================================================
with tab_overview:
    st.header("🛰️ Nivel evento (detecciones FIRMS)")

    if df_clean_f.empty:
        st.warning("No hay detecciones FIRMS con los filtros actuales.")
    else:
        st.subheader("📌 Resumen rápido")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Detecciones", f"{len(df_clean_f):,}")
        c2.metric("Provincias", df_clean_f["provincia"].nunique())
        c3.metric("Brightness medio", f"{df_clean_f['firms_brightness'].mean():.1f}")
        c4.metric(
            "FRP medio (MW)",
            f"{df_clean_f['firms_frp'].mean():.2f}" if "firms_frp" in df_clean_f.columns else "N/D"
        )

        st.markdown("---")

        # =========================
        # MAPA
        # =========================
        st.subheader("🗺️ Mapa de detecciones (evento)")
        st.markdown(
            """
**Cómo leer este mapa**
- **Puntos**: cada punto es una detección del satélite (evento individual).
- **Densidad (hexágonos)**: agrupa detecciones para ver zonas con mucha concentración.
"""
        )

        map_mode = st.radio("Modo", ["Puntos (Scatter)", "Densidad (Hexagon)"], horizontal=True)

        max_points = 30000
        df_map = df_clean_f.sample(n=max_points, random_state=42) if len(df_clean_f) > max_points else df_clean_f.copy()

        required = {"firms_latitude", "firms_longitude", "firms_date"}
        if required.issubset(df_map.columns):
            keep_cols = ["firms_latitude", "firms_longitude", "provincia", "firms_brightness", "firms_date"]
            if "firms_frp" in df_map.columns:
                keep_cols.append("firms_frp")
            df_map = df_map[keep_cols].copy()
            df_map["firms_date_str"] = df_map["firms_date"].dt.strftime("%Y-%m-%d %H:%M:%S")

            mid_lat = float(df_map["firms_latitude"].mean())
            mid_lon = float(df_map["firms_longitude"].mean())
            view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=5, pitch=40)

            if map_mode == "Puntos (Scatter)":
                layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=df_map,
                    get_position=["firms_longitude", "firms_latitude"],
                    get_radius=200,
                    get_fill_color=[255, 0, 0, 160],
                    pickable=True,
                )

                tooltip_html = (
                    "<b>Provincia:</b> {provincia}<br/>"
                    "<b>Fecha:</b> {firms_date_str}<br/>"
                    "<b>Brightness:</b> {firms_brightness}"
                )
                if "firms_frp" in df_map.columns:
                    tooltip_html += "<br/><b>FRP:</b> {firms_frp}"

                st.pydeck_chart(
                    pdk.Deck(
                        layers=[layer],
                        initial_view_state=view_state,
                        tooltip={"html": tooltip_html, "style": {"color": "white"}},
                    )
                )
            else:
                st.caption(
                    "Densidad 3D (rejilla H3): columnas más altas = más detecciones. "
                    "El color indica densidad (más rojo = más detecciones)."
                )

                try:
                    import h3
                except Exception:
                    st.error("Falta la librería `h3`. Instálala con: pip install h3")
                    st.stop()

                df_hex = df_map.rename(columns={"firms_latitude": "lat", "firms_longitude": "lon"}).copy()

                h3_res = st.slider("Detalle (H3 resolution)", 3, 7, 5)
                max_cells = 4000

                @st.cache_data(show_spinner=False)
                def build_h3_grid(df_in: pd.DataFrame, res: int) -> pd.DataFrame:
                    d = df_in.dropna(subset=["lat", "lon"]).copy()
                    d["h3"] = d.apply(lambda r: h3.latlng_to_cell(r["lat"], r["lon"], res), axis=1)

                    def mode_or_na(s):
                        s = s.dropna()
                        return s.mode().iloc[0] if not s.empty else "N/D"

                    g = d.groupby("h3", as_index=False).agg(
                        n=("h3", "size"),
                        provincia=("provincia", mode_or_na),
                        mean_brightness=("firms_brightness", "mean"),
                        mean_frp=("firms_frp", "mean") if "firms_frp" in d.columns else ("h3", "size"),
                    )

                    centers = g["h3"].apply(lambda c: h3.cell_to_latlng(c))
                    g["lat"] = centers.apply(lambda x: x[0])
                    g["lon"] = centers.apply(lambda x: x[1])

                    g["n_norm"] = (g["n"] - g["n"].min()) / (g["n"].max() - g["n"].min() + 1e-9)

                    g["r"] = 255
                    g["g"] = (255 - 200 * g["n_norm"]).clip(55, 255).astype(int)
                    g["b"] = 50
                    g["a"] = 180

                    return g.sort_values("n", ascending=False)

                grid = build_h3_grid(df_hex, h3_res).head(max_cells)

                col_layer = pdk.Layer(
                    "ColumnLayer",
                    data=grid,
                    get_position=["lon", "lat"],
                    get_elevation="n",
                    elevation_scale=80,
                    radius=3500,
                    extruded=True,
                    pickable=True,
                    get_fill_color=["r", "g", "b", "a"],
                )

                view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=5, pitch=40)

                tooltip_html = (
                    "<b>Provincia (dominante):</b> {provincia}<br/>"
                    "<b>Detecciones (celda):</b> {n}<br/>"
                    "<b>Brightness media:</b> {mean_brightness}<br/>"
                )
                if "firms_frp" in df_map.columns:
                    tooltip_html += "<b>FRP media:</b> {mean_frp}<br/>"
                tooltip_html += "<b>H3:</b> {h3}"

                st.pydeck_chart(
                    pdk.Deck(
                        layers=[col_layer],
                        initial_view_state=view_state,
                        tooltip={"html": tooltip_html, "style": {"color": "white"}},
                    )
                )

        st.markdown("---")

        # =========================
        # EVOLUCIÓN ANUAL
        # =========================
        st.subheader("📈 Evolución anual de detecciones")

        if "year" not in df_clean_f.columns and "firms_date" in df_clean_f.columns:
            df_clean_f["year"] = df_clean_f["firms_date"].dt.year

        if "year" in df_clean_f.columns:
            yearly = (
                df_clean_f.groupby("year")
                .agg(n_fires=("firms_brightness", "count"), mean_brightness=("firms_brightness", "mean"))
                .reset_index()
                .sort_values("year")
            )

            st.altair_chart(
                alt.Chart(yearly).mark_line(point=True).encode(
                    x=alt.X("year:O", title="Año"),
                    y=alt.Y("n_fires:Q", title="Nº detecciones"),
                    tooltip=["year:O", "n_fires:Q", alt.Tooltip("mean_brightness:Q", format=".1f")],
                ).properties(height=300).interactive(),
                use_container_width=True
            )

        st.markdown("---")

        # =========================
        # TOP PROVINCIAS
        # =========================
        st.subheader("🏅 Provincias con más detecciones (ranking)")

        top_n = st.slider("Nº de provincias a mostrar", 3, 20, 10, key="top_prov_events")

        prov_counts = (
            df_clean_f.groupby("provincia")
            .agg(n_fires=("firms_brightness", "count"), mean_brightness=("firms_brightness", "mean"))
            .reset_index()
            .sort_values("n_fires", ascending=False)
            .head(top_n)
        )

        st.altair_chart(
            alt.Chart(prov_counts).mark_bar().encode(
                x=alt.X("n_fires:Q", title="Nº detecciones"),
                y=alt.Y("provincia:N", sort="-x", title="Provincia"),
                tooltip=["provincia", "n_fires:Q", alt.Tooltip("mean_brightness:Q", format=".1f")],
            ).properties(height=400),
            use_container_width=True
        )

        st.markdown("---")

        # =========================
        # DISTRIBUCIÓN INTENSIDAD
        # =========================
        st.subheader("📊 Distribución de intensidad")

        st.markdown(
            """
**¿Qué estás viendo aquí? (histograma)**  
Un histograma cuenta **cuántas detecciones** caen dentro de distintos rangos de intensidad.

- **Eje X**: intensidad (Brightness o FRP). Más a la derecha = señal más intensa.  
- **Eje Y**: cuántas detecciones hay en ese rango.
"""
        )

        frp_note_text = ""
        if "firms_frp" in df_clean_f.columns:
            _, _, frp_note_text = choose_frp_transform(df_clean_f["firms_frp"])
        if frp_note_text:
            st.caption(frp_note_text)

        cA, cB = st.columns(2)
        CHART_H = 260

        with cA:
            b = clip_quantiles(df_clean_f["firms_brightness"], q_low=0.005, q_high=0.995)
            if b.empty:
                st.info("Brightness no tiene valores válidos para graficar.")
            else:
                hb = hist_counts(b, bins=auto_bins(b, min_bins=30, max_bins=60))
                st.altair_chart(
                    alt.Chart(hb).mark_bar().encode(
                        x=alt.X("bin_left:Q", title="Brightness", bin=alt.Bin(binned=True)),
                        x2="bin_right:Q",
                        y=alt.Y("count:Q", title="Nº detecciones"),
                        tooltip=[
                            alt.Tooltip("bin_left:Q", title="Desde", format=".1f"),
                            alt.Tooltip("bin_right:Q", title="Hasta", format=".1f"),
                            alt.Tooltip("count:Q", title="N"),
                        ],
                    ).properties(height=CHART_H),
                    use_container_width=True
                )

        with cB:
            if "firms_frp" in df_clean_f.columns:
                frp_viz, frp_title, _ = choose_frp_transform(df_clean_f["firms_frp"])
                frp_viz = clip_quantiles(frp_viz, q_low=0.005, q_high=0.995)
                if frp_viz.empty:
                    st.info("FRP no tiene valores válidos para graficar.")
                else:
                    hf = hist_counts(frp_viz, bins=auto_bins(frp_viz, min_bins=30, max_bins=60))
                    st.altair_chart(
                        alt.Chart(hf).mark_bar().encode(
                            x=alt.X("bin_left:Q", title=frp_title, bin=alt.Bin(binned=True)),
                            x2="bin_right:Q",
                            y=alt.Y("count:Q", title="Nº detecciones"),
                            tooltip=[
                                alt.Tooltip("bin_left:Q", title="Desde", format=".2f"),
                                alt.Tooltip("bin_right:Q", title="Hasta", format=".2f"),
                                alt.Tooltip("count:Q", title="N"),
                            ],
                        ).properties(height=CHART_H),
                        use_container_width=True
                    )
            else:
                st.info("No está `firms_frp` en el dataset de evento.")

        st.markdown("---")
        st.subheader("📋 Muestra de datos (evento)")
        n_show = st.slider("Filas a mostrar", 5, 100, 20, key="n_show_events")
        st.dataframe(df_clean_f.head(n_show), use_container_width=True)

# =========================================================
# 2) TAB PROVINCIA–DÍA
# =========================================================
with tab_daily:
    st.header("📊 Provincia–día (agregación)")
    st.caption("Aquí cada fila representa **una provincia en un día**. Sirve para tendencias, estacionalidad y clima vs fuego.")

    tab_temp, tab_season, tab_maps, tab_climate, tab_lags, tab_corr_rank, tab_effis = st.tabs(
        [
            "⏱️ Temporal",
            "📅 Estacionalidad",
            "🗺️ Mapas",
            "🌡️ Clima vs fuego",
            "⏳ Lags",
            "📈 Correlaciones",
            "🔥 EFFIS – Severidad",
        ]
    )

    # -----------------------------------------------------
    # TEMPORAL
    # -----------------------------------------------------
    with tab_temp:
        st.subheader("⏱️ Evolución temporal")

        nat_daily = (
            df_daily_f.groupby("date", as_index=False)
            .agg(firms_count=("firms_count", "sum"), effis_area_ha=("effis_area_ha", "sum"))
            .sort_values("date")
        )

        c1, c2 = st.columns(2)
        with c1:
            st.altair_chart(
                alt.Chart(nat_daily).mark_line().encode(
                    x=alt.X("date:T", title="Fecha"),
                    y=alt.Y("firms_count:Q", title="Nº detecciones FIRMS"),
                    tooltip=["date:T", "firms_count:Q"],
                ).properties(height=300).interactive(),
                use_container_width=True
            )
        with c2:
            st.altair_chart(
                alt.Chart(nat_daily).mark_line().encode(
                    x=alt.X("date:T", title="Fecha"),
                    y=alt.Y("effis_area_ha:Q", title="Área quemada (ha)"),
                    tooltip=["date:T", "effis_area_ha:Q"],
                ).properties(height=300).interactive(),
                use_container_width=True
            )

        st.markdown("---")

        st.markdown("### 📆 Total por año")
        yearly = (
            df_daily_f.groupby("year", as_index=False)
            .agg(firms_count=("firms_count", "sum"), effis_area_ha=("effis_area_ha", "sum"))
            .sort_values("year")
        )

        st.altair_chart(
            alt.Chart(yearly).mark_bar().encode(
                x=alt.X("year:O", title="Año"),
                y=alt.Y("firms_count:Q", title="Nº detecciones FIRMS"),
                tooltip=["year:O", "firms_count:Q", "effis_area_ha:Q"],
            ).properties(height=300),
            use_container_width=True
        )

        st.markdown("---")
        st.markdown("### 📊 Distribuciones (para entender picos)")

        cA, cB = st.columns(2)
        with cA:
            h = hist_counts(df_daily_f["firms_count"], bins=60)
            st.altair_chart(
                alt.Chart(h).mark_bar().encode(
                    x=alt.X("bin_left:Q", title="firms_count", bin=alt.Bin(binned=True)),
                    x2="bin_right:Q",
                    y=alt.Y("count:Q", title="Nº registros"),
                    tooltip=["count:Q"],
                ).properties(height=250),
                use_container_width=True
            )
        with cB:
            h2 = hist_counts(df_daily_f["effis_area_ha"], bins=60)
            st.altair_chart(
                alt.Chart(h2).mark_bar().encode(
                    x=alt.X("bin_left:Q", title="effis_area_ha", bin=alt.Bin(binned=True)),
                    x2="bin_right:Q",
                    y=alt.Y("count:Q", title="Nº registros"),
                    tooltip=["count:Q"],
                ).properties(height=250),
                use_container_width=True
            )
    # -----------------------------------------------------
    # ESTACIONALIDAD
    # -----------------------------------------------------
    with tab_season:
        st.subheader("📅 Estacionalidad")

        # Orden correcto de los meses (para que Altair no los ordene alfabéticamente)
        month_order = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]

        # Mapeo manual (100% portable, evita problemas de locale / inglés)
        month_map = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }

        # -----------------------------
        # 1) BARRAS: total por mes (España total)
        # -----------------------------
        month_counts = (
            df_daily_f
            .assign(
                month_num=lambda x: x["date"].dt.month,
                month=lambda x: x["date"].dt.month.map(month_map)
            )
            .groupby(["month", "month_num"], as_index=False)
            .agg(firms_count=("firms_count", "sum"))
            .sort_values("month_num")
        )

        st.altair_chart(
            alt.Chart(month_counts).mark_bar().encode(
                x=alt.X("month:N", title="Mes", sort=month_order),
                y=alt.Y("firms_count:Q", title="Nº detecciones FIRMS"),
                tooltip=["month:N", "firms_count:Q"],
            ).properties(height=300),
            use_container_width=True
        )

        st.markdown("---")
        st.markdown("### 📆 Calendar heatmap (España total)")
        st.caption("Semana del año vs día de la semana para el rango temporal seleccionado (filtros del sidebar).")

        # -----------------------------
        # 2) HEATMAP CALENDARIO (semana vs día semana)
        # -----------------------------
        nat = df_daily_f.groupby("date", as_index=False).agg(firms=("firms_count", "sum"))
        nat["dow"] = nat["date"].dt.dayofweek
        nat["week"] = nat["date"].dt.isocalendar().week.astype(int)
        nat["year"] = nat["date"].dt.year  # se deja por si quieres facet por año en el futuro

        st.altair_chart(
            alt.Chart(nat).mark_rect().encode(
                x=alt.X("week:O", title="Semana"),
                y=alt.Y("dow:O", title="Día semana (0=L)"),
                color=alt.Color("firms:Q", title="FIRMS"),
                tooltip=["date:T", "firms:Q"],
            ).properties(height=220),
            use_container_width=True
        )

        st.markdown("---")
        st.markdown("### 🔥 Heatmap provincia–mes")
        st.caption("Cada celda = total de detecciones de una provincia en un mes.")

        # -----------------------------
        # 3) HEATMAP: provincia vs mes (con mes en texto)
        # -----------------------------
        df_heat = (
            df_daily_f
            .assign(
                month_num=lambda x: x["date"].dt.month,
                month=lambda x: x["date"].dt.month.map(month_map)
            )
            .groupby(["provincia", "month", "month_num"], as_index=False)
            .agg(firms_count=("firms_count", "sum"))
            .sort_values("month_num")
        )

        st.altair_chart(
            alt.Chart(df_heat).mark_rect().encode(
                x=alt.X("month:N", title="Mes", sort=month_order),
                y=alt.Y("provincia:N", title="Provincia"),
                color=alt.Color("firms_count:Q", title="Nº detecciones"),
                tooltip=["provincia:N", "month:N", "firms_count:Q"],
            ).properties(height=520),
            use_container_width=True
        )


    # -----------------------------------------------------
    # MAPAS
    # -----------------------------------------------------
    with tab_maps:
        st.subheader("🗺️ Mapas")


        st.markdown("---")
        st.markdown("### 🧩 Coroplético EFFIS (área quemada)")
        st.caption("Área total EFFIS (ha) por provincia dentro del rango filtrado.")

        prov_effis = df_daily_f.groupby("provincia", as_index=False).agg(effis_area_ha=("effis_area_ha", "sum"))
        if prov_effis["effis_area_ha"].sum() == 0:
            st.info("No hay área quemada EFFIS en el rango filtrado.")
        else:
            prov_effis["provincia_norm"] = norm_nombre(prov_effis["provincia"])
            gdf_prov["provincia_norm"] = norm_nombre(gdf_prov["provincia"])

            gdf_merged = gdf_prov.merge(
                prov_effis[["provincia_norm", "effis_area_ha"]],
                on="provincia_norm",
                how="left",
            ).fillna({"effis_area_ha": 0})

            gdf_merged_4326 = gdf_merged.to_crs(epsg=4326)
            area = gdf_merged_4326["effis_area_ha"]
            gdf_merged_4326["effis_area_ha_norm"] = (area / area.max()) if area.max() > 0 else 0.0

            geojson = json.loads(gdf_merged_4326.to_json())

            layer_poly = pdk.Layer(
                "GeoJsonLayer",
                data=geojson,
                pickable=True,
                stroked=True,
                filled=True,
                get_fill_color="[255, 255 - properties.effis_area_ha_norm * 255, 0, 160]",
                get_line_color=[80, 80, 80],
                line_width_min_pixels=1,
            )

            view_state_poly = pdk.ViewState(latitude=40.0, longitude=-3.7, zoom=5, pitch=0)

            st.pydeck_chart(
                pdk.Deck(
                    layers=[layer_poly],
                    initial_view_state=view_state_poly,
                    tooltip={
                        "html": "<b>Provincia:</b> {properties.provincia}<br/>"
                                "<b>Área EFFIS (ha):</b> {properties.effis_area_ha}",
                        "style": {"color": "white"},
                    },
                )
            )

    # -----------------------------------------------------
    # CLIMA vs FUEGO
    # -----------------------------------------------------
    with tab_climate:
        st.subheader("🌡️ Clima vs nº de detecciones")

        df_plot = df_daily_f.copy()
        if len(df_plot) > 20000:
            df_plot = df_plot.sample(20000, random_state=42)

        meteo_cols = [c for c in df_plot.columns if c.startswith("meteo_")]
        if not meteo_cols:
            st.info("No hay columnas `meteo_` en `prov_daily_viz`.")
        else:
            meteo_var = st.selectbox("Variable meteo", meteo_cols, index=0)
            use_log_y = st.checkbox("Escala log en y (firms_count)", value=False)

            sel = alt.selection_point(fields=["provincia"], toggle=True, empty=True)
            base = alt.Chart(df_plot).add_params(sel)

            y_enc = alt.Y("firms_count:Q", title="Nº detecciones FIRMS")
            if use_log_y:
                y_enc = alt.Y("firms_count:Q", title="Nº detecciones FIRMS (log)", scale=alt.Scale(type="log"))

            st.altair_chart(
                base.mark_circle(size=28, opacity=0.5).encode(
                    x=alt.X(f"{meteo_var}:Q", title=meteo_var),
                    y=y_enc,
                    color=alt.condition(sel, alt.Color("provincia:N", legend=None), alt.value("lightgray")),
                    tooltip=["provincia", "date", meteo_var, "firms_count"],
                ).properties(height=350).interactive(),
                use_container_width=True
            )

    # -----------------------------------------------------
    # LAGS
    # -----------------------------------------------------
    with tab_lags:
        st.subheader("⏳ Lags clima → fuego")

        meteo_cols = [c for c in df_daily_f.columns if c.startswith("meteo_")]
        if not meteo_cols:
            st.info("No hay columnas `meteo_` para analizar lags.")
        else:
            prov = st.selectbox("Provincia", sorted(df_daily_f["provincia"].unique()), key="lag_prov")
            var = st.selectbox("Variable meteo", meteo_cols, key="lag_var")
            max_lag = st.slider("Máximo lag (días)", 0, 14, 7, key="lag_max")

            g = df_daily_f[df_daily_f["provincia"] == prov].sort_values("date").copy()

            rows = []
            for lag in range(0, max_lag + 1):
                rows.append((lag, g["firms_count"].corr(g[var].shift(lag))))
            df_lag = pd.DataFrame(rows, columns=["lag", "corr"]).dropna()

            st.altair_chart(
                alt.Chart(df_lag).mark_line(point=True).encode(
                    x=alt.X("lag:O", title="Lag (días)"),
                    y=alt.Y("corr:Q", title="Correlación"),
                    tooltip=["lag", alt.Tooltip("corr:Q", format=".2f")],
                ).properties(height=280).interactive(),
                use_container_width=True
            )

    # -----------------------------------------------------
    # CORRELACIONES (ranking) - ✅ versión entendible (sin sliders)
    # -----------------------------------------------------
    with tab_corr_rank:
        st.subheader("📈 Correlación clima–incendios (ranking)")

        st.markdown("""
Este gráfico muestra **asociaciones estadísticas** entre variables meteorológicas y el número de detecciones FIRMS (`firms_count`), calculadas **por provincia**.

**Cómo leerlo:**
- Cada barra corresponde a una **provincia y una variable meteorológica concreta**.
- Valores **positivos** ⇒ más detecciones cuando la variable aumenta.
- Valores **negativos** ⇒ menos detecciones cuando la variable aumenta.
- Cuanto más lejos de 0 ⇒ asociación más fuerte.

⚠️ **Importante:** esto **no implica causalidad**, solo asociación lineal (correlación de Pearson).
""")

        meteo_cols = [c for c in df_daily_f.columns if c.startswith("meteo_")]
        if not meteo_cols:
            st.info("No hay columnas `meteo_`.")
        else:
            min_obs = 15   # fijo (evita correlaciones espurias por pocos datos)
            top_k = 25     # fijo (legibilidad)

            corr_rows = []
            for prov, g in df_daily_f.groupby("provincia"):
                for v in meteo_cols:
                    n_valid = g[["firms_count", v]].dropna().shape[0]
                    if n_valid >= min_obs:
                        corr = g["firms_count"].corr(g[v])
                        if pd.notna(corr):
                            corr_rows.append((prov, v, corr, n_valid))

            df_corrp = pd.DataFrame(corr_rows, columns=["provincia", "variable_meteo", "corr", "n_obs"])
            if df_corrp.empty:
                st.info("No se pudieron calcular correlaciones (quizá faltan datos tras los filtros).")
            else:
                df_corrp["abs_corr"] = df_corrp["corr"].abs()
                top = df_corrp.sort_values(["abs_corr", "n_obs"], ascending=False).head(top_k)

                st.altair_chart(
                    alt.Chart(top).mark_bar().encode(
                        x=alt.X("corr:Q", title="Correlación (Pearson)"),
                        y=alt.Y("provincia:N", sort="-x", title="Provincia"),
                        color=alt.Color("corr:Q", scale=alt.Scale(scheme="redblue", domain=(-1, 1)), title="Correlación"),
                        tooltip=[
                            "provincia",
                            "variable_meteo",
                            alt.Tooltip("corr:Q", format=".2f"),
                            alt.Tooltip("n_obs:Q", title="Observaciones"),
                        ],
                    ).properties(height=520),
                    use_container_width=True
                )

                with st.expander("📋 Ver tabla (top correlaciones)"):
                    st.dataframe(top[["provincia", "variable_meteo", "corr", "n_obs"]], use_container_width=True)

    # -----------------------------------------------------
    # EFFIS – SEVERIDAD
    # -----------------------------------------------------
    with tab_effis:
        st.subheader("🔥 EFFIS – Severidad")

        df_effis = df_daily_f.copy()

        st.markdown("### 🧪 Índice simple de severidad")
        st.caption("Ejemplo: `sev = log1p(area) * log1p(firms_count)` para resaltar días intensos.")
        df_effis["sev"] = np.log1p(df_effis["effis_area_ha"].astype(float)) * np.log1p(df_effis["firms_count"].astype(float))

        top_sev = df_effis.sort_values("sev", ascending=False).head(30)

        st.altair_chart(
            alt.Chart(top_sev).mark_bar().encode(
                x=alt.X("sev:Q", title="Índice sev"),
                y=alt.Y("provincia:N", sort="-x", title="Provincia"),
                tooltip=["provincia", "date", "sev", "effis_area_ha", "firms_count", "effis_fire_count"],
            ).properties(height=420),
            use_container_width=True
        )

        st.markdown("---")
        st.markdown("### 📋 Top 30 provincia–día por área quemada (ha)")
        df_effis_top = df_effis[df_effis["effis_area_ha"] > 0].sort_values("effis_area_ha", ascending=False).head(30)
        st.dataframe(
            df_effis_top[["provincia", "date", "effis_area_ha", "effis_fire_count", "firms_count"]],
            use_container_width=True
        )

        st.markdown("---")
        st.markdown("### 🧮 Área total quemada por provincia (subconjunto filtrado)")
        prov_tot = (
            df_effis.groupby("provincia", as_index=False)
            .agg(
                effis_area_ha=("effis_area_ha", "sum"),
                effis_fire_count=("effis_fire_count", "sum"),
                firms_count=("firms_count", "sum"),
            )
            .sort_values("effis_area_ha", ascending=False)
        )
        st.dataframe(prov_tot, use_container_width=True)

