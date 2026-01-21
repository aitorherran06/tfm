import streamlit as st
from pymongo import MongoClient
import pandas as pd
from datetime import datetime, timedelta
import pydeck as pdk
import altair as alt

# =========================================================
#   CONFIGURACIÓN (MONGO DESDE SECRETS)
# =========================================================
try:
    mongo_uri = st.secrets["MONGO"]["URI"]
    client = MongoClient(mongo_uri)
    db = client["incendios_espana"]
    collection = db["firms_actualizado"]
except Exception as e:
    st.error(f"❌ No se pudo conectar a MongoDB (revisa MONGO.URI): {e}")
    st.stop()

st.set_page_config(
    page_title="Puntos calientes FIRMS (España)",
    layout="wide"
)

st.title("🔥 Puntos calientes FIRMS — España")
st.markdown(
    """
Mapa interactivo de los **puntos calientes** detectados por FIRMS  
almacenados en la colección **`firms_actualizado`** de MongoDB  
(últimos 7 días, solo España según el script de ingesta).
"""
)

# =========================================================
#   CARGA DE DATOS DESDE MONGO
# =========================================================
st.info("Cargando datos desde MongoDB... ⏳")

try:
    cursor = collection.find({}, {"_id": 0})
    docs = list(cursor)
except Exception as e:
    st.error(f"❌ Error al cargar datos: {e}")
    st.stop()

if not docs:
    st.warning("⚠️ La colección 'firms_actualizado' está vacía.")
    st.stop()

df = pd.DataFrame(docs)
st.success(f"✅ Datos cargados: **{len(df):,}** registros totales (últimos 7 días, España)")

# =========================================================
#   DETECCIÓN DE COLUMNAS CLAVE
# =========================================================

# Lat / Lon
lat_cols = [c for c in df.columns if any(x in c.lower() for x in ["lat", "latitud"])]
lon_cols = [c for c in df.columns if any(x in c.lower() for x in ["lon", "lng", "long", "longitud"])]

col_lat = lat_cols[0] if lat_cols else None
col_lon = lon_cols[0] if lon_cols else None

if not col_lat or not col_lon:
    st.error("❌ No se han detectado columnas de latitud/longitud en la colección.")
    st.write("Columnas disponibles:", list(df.columns))
    st.stop()

# Fecha / hora
fecha_cols = [c for c in df.columns if any(x in c.lower() for x in ["fecha", "date", "time", "datetime"])]
if "datetime" in df.columns:
    col_fecha = "datetime"
elif fecha_cols:
    col_fecha = fecha_cols[0]
else:
    col_fecha = None

if col_fecha:
    df[col_fecha] = (
        pd.to_datetime(df[col_fecha], errors="coerce", utc=True)
        .dt.tz_convert(None)
    )
    fecha_min = df[col_fecha].dropna().min()
    fecha_max = df[col_fecha].dropna().max()
else:
    fecha_min = fecha_max = None

# Provincia
prov_cols = [c for c in df.columns if "prov" in c.lower()]
col_prov = prov_cols[0] if prov_cols else None

# =========================================================
#   SIDEBAR: FILTROS TEMPORALES
# =========================================================
st.sidebar.header("🧰 Filtros")

opcion_tiempo = st.sidebar.selectbox(
    "Rango temporal:",
    ["Últimas 24h", "Últimas 48h", "Últimos 7 días", "Rango personalizado"],
    index=2,
)

now = datetime.utcnow()

if col_fecha and pd.notnull(fecha_min) and pd.notnull(fecha_max):
    if opcion_tiempo == "Últimas 24h":
        desde = now - timedelta(days=1)
        hasta = now
    elif opcion_tiempo == "Últimas 48h":
        desde = now - timedelta(days=2)
        hasta = now
    elif opcion_tiempo == "Últimos 7 días":
        desde = now - timedelta(days=7)
        hasta = now
    else:
        st.sidebar.markdown("### 📅 Rango personalizado")
        rango = st.sidebar.date_input(
            "Selecciona el rango de fechas:",
            (fecha_min.date(), fecha_max.date())
        )
        if isinstance(rango, tuple) and len(rango) == 2:
            d1, d2 = rango
            desde = datetime.combine(d1, datetime.min.time())
            hasta = datetime.combine(d2, datetime.max.time())
        else:
            desde = fecha_min
            hasta = fecha_max

    mask_t = (df[col_fecha] >= desde) & (df[col_fecha] <= hasta)
    df_filtrado = df.loc[mask_t].copy()
else:
    st.sidebar.info("No se detectó una columna de fecha válida. Se mostrarán todos los datos.")
    df_filtrado = df.copy()

st.subheader(f"📁 Registros filtrados: **{len(df_filtrado):,}**")

cols_preview = [c for c in [col_fecha, col_lat, col_lon, col_prov] if c in df_filtrado.columns]
st.dataframe(df_filtrado[cols_preview].head(20), use_container_width=True)

# =========================================================
#   RESUMEN BÁSICO
# =========================================================
st.markdown("## 📊 Resumen de los datos filtrados")

c1, c2 = st.columns(2)
c1.metric("Nº detecciones FIRMS", f"{len(df_filtrado):,}")

if col_fecha and not df_filtrado[col_fecha].dropna().empty:
    fmin = df_filtrado[col_fecha].dropna().min()
    fmax = df_filtrado[col_fecha].dropna().max()
    c2.metric("Desde / hasta", f"{fmin.date()} → {fmax.date()}")
else:
    c2.metric("Desde / hasta", "N/D")

# =========================================================
#   DISTRIBUCIÓN POR PROVINCIA
# =========================================================
if col_prov and not df_filtrado.empty:
    st.markdown("### 🏅 Detecciones por provincia")

    prov_counts = (
        df_filtrado.groupby(col_prov, as_index=False)
        .size()
        .rename(columns={"size": "n_detecciones"})
        .sort_values("n_detecciones", ascending=False)
        .head(15)
    )

    chart_prov = (
        alt.Chart(prov_counts)
        .mark_bar()
        .encode(
            x=alt.X("n_detecciones:Q", title="Nº detecciones"),
            y=alt.Y(f"{col_prov}:N", sort="-x", title="Provincia"),
            tooltip=[col_prov, "n_detecciones"],
        )
        .properties(height=400)
    )

    st.altair_chart(chart_prov, use_container_width=True)

st.markdown("---")

# =========================================================
#   MAPA DE PUNTOS CALIENTES
# =========================================================
st.markdown("## 🗺️ Mapa de puntos calientes FIRMS (solo España)")

if df_filtrado.empty:
    st.warning("⚠️ No hay datos para el rango seleccionado.")
else:
    df_map = df_filtrado[[col_lat, col_lon]].dropna().copy()
    df_map.rename(columns={col_lat: "lat", col_lon: "lon"}, inplace=True)

    center_lat = df_map["lat"].mean()
    center_lon = df_map["lon"].mean()

    layer_heat = pdk.Layer(
        "HeatmapLayer",
        data=df_map,
        get_position=["lon", "lat"],
        aggregation="SUM",
        threshold=0.3,
        radius_pixels=40,
    )

    layer_scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position=["lon", "lat"],
        get_radius=800,
        get_fill_color=[255, 140, 0, 80],
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=5,
        pitch=0
    )

    r = pdk.Deck(
        layers=[layer_heat, layer_scatter],
        initial_view_state=view_state,
        tooltip={"text": "Punto FIRMS\nLat: {lat}\nLon: {lon}"}
    )

    st.pydeck_chart(r)

# =========================================================
#   EXPORTAR CSV FILTRADO
# =========================================================
st.markdown("## 💾 Exportar datos filtrados")

csv = df_filtrado.to_csv(index=False).encode("utf-8")

st.download_button(
    "💾 Descargar CSV filtrado",
    csv,
    "firms_actualizado_espana_filtrado.csv",
    "text/csv"
)
