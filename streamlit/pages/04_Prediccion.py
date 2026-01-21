import os
import numpy as np
import pandas as pd
import streamlit as st
from pymongo import MongoClient
import joblib
import altair as alt
import geopandas as gpd
import pydeck as pdk

# =========================================================
# RUTAS BASE (PORTABLES PARA STREAMLIT CLOUD)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(
    page_title="Predicción de Riesgo AEMET",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Predicción de riesgo de incendio (AEMET + Random Forest)")
st.markdown(
    """
Este panel utiliza las **predicciones meteorológicas de AEMET** guardadas en MongoDB  
y un modelo de **Random Forest** para estimar la probabilidad de que haya  
**riesgo alto de incendio** en cada provincia y día.

**Interpretación de la probabilidad (`prob_riesgo_alto`):**

- `0.00 – 0.33` → 🟩 **Riesgo bajo**  
- `0.34 – 0.59` → 🟨 **Riesgo moderado**  
- `≥ 0.60`     → 🟥 **Riesgo alto / alerta**  

El umbral actual de alerta está fijado en **0.60**.
"""
)

# =========================================================
# 1) CARGA DE SECRETS (Mongo y modelo)
# =========================================================
try:
    MONGO_URI = st.secrets["MONGO"]["URI"]
    MODEL_PATH = st.secrets["MODELO"]["RUTA_MODELO"]
except Exception:
    st.error("❌ No se pudieron cargar los secrets. Configura .streamlit/secrets.toml")
    st.stop()

# =========================================================
# 2) CARGA DEL MODELO
# =========================================================
@st.cache_resource(show_spinner=True)
def cargar_modelo():
    return joblib.load(MODEL_PATH)

modelo = cargar_modelo()

# =========================================================
# 3) CONEXIÓN A MONGO
# =========================================================
@st.cache_resource(show_spinner=True)
def conectar_mongo():
    client = MongoClient(MONGO_URI)
    db = client["incendios_espana"]
    return db["aemet_predicciones"]

col_aemet = conectar_mongo()

# =========================================================
# 4) CARGA Y TRANSFORMACIÓN AEMET → DATAFRAME
# =========================================================
def extraer_max(arr, campo=None):
    if not isinstance(arr, list) or len(arr) == 0:
        return np.nan
    if campo and isinstance(arr[0], dict):
        vals = [pd.to_numeric(x.get(campo), errors="coerce") for x in arr]
    else:
        vals = pd.to_numeric(arr, errors="coerce")
    return np.nanmax(vals)


@st.cache_data(show_spinner=True)
def cargar_aemet_df():
    docs = list(col_aemet.find({}))
    filas = []

    for d in docs:
        fila = {
            "provincia": d.get("provincia"),
            "fecha": pd.to_datetime(d.get("fecha"), errors="coerce"),
        }

        temp = d.get("temperatura", {}) or {}
        hum = d.get("humedadRelativa", {}) or {}

        fila["meteo_temp_max"] = temp.get("maxima")
        fila["meteo_temp_min"] = temp.get("minima")
        fila["meteo_humidity_max"] = hum.get("maxima")
        fila["meteo_humidity_min"] = hum.get("minima")

        fila["meteo_wind_max"] = extraer_max(d.get("viento", []), "velocidad")
        fila["meteo_precip_sum"] = extraer_max(d.get("probPrecipitacion", []), "value")

        filas.append(fila)

    df = pd.DataFrame(filas)
    df["provincia"] = df["provincia"].astype(str)
    df = df.dropna(subset=["fecha"])
    return df


df_aemet = cargar_aemet_df()

if df_aemet.empty:
    st.error("❌ No hay datos en MongoDB para `aemet_predicciones`.")
    st.stop()

st.caption(f"📂 Registros AEMET en Mongo: **{len(df_aemet):,}** filas (provincia–fecha).")

# =========================================================
# 5) PREPROCESAMIENTO Y PREDICCIÓN
# =========================================================
feat_cols = [
    "meteo_temp_max",
    "meteo_temp_min",
    "meteo_precip_sum",
    "meteo_wind_max",
    "meteo_humidity_max",
    "meteo_humidity_min",
]

df_pred = df_aemet.copy()

for c in feat_cols:
    df_pred[c] = pd.to_numeric(df_pred[c], errors="coerce")

df_pred = df_pred.dropna(subset=feat_cols)

if df_pred.empty:
    st.error("❌ Tras limpiar datos, no quedan filas válidas para el modelo.")
    st.stop()

df_pred["prob_riesgo_alto"] = modelo.predict_proba(df_pred[feat_cols])[:, 1]
df_pred["alerta_incendio"] = (df_pred["prob_riesgo_alto"] >= 0.60).astype(int)

# =========================================================
# 6) FILTRO POR FECHA
# =========================================================
st.sidebar.header("📅 Filtros de predicción")

fechas_disp = sorted(df_pred["fecha"].dt.date.unique())
ultima_fecha = max(fechas_disp)

fecha_seleccionada = st.sidebar.selectbox(
    "Fecha a mostrar:",
    fechas_disp,
    index=fechas_disp.index(ultima_fecha),
    format_func=lambda d: d.strftime("%Y-%m-%d")
)

df_f = df_pred[df_pred["fecha"].dt.date == fecha_seleccionada].copy()

st.markdown(
    f"### 🔍 Predicción seleccionada para el día **{fecha_seleccionada.strftime('%Y-%m-%d')}**"
)

# =========================================================
# 7) KPIs
# =========================================================
c1, c2, c3 = st.columns(3)

c1.metric("Provincias con predicción", df_f["provincia"].nunique())
c2.metric("Provincias en alerta (prob ≥ 0.60)", int(df_f["alerta_incendio"].sum()))
c3.metric("Probabilidad media nacional", f"{df_f['prob_riesgo_alto'].mean():.3f}")

st.caption("El umbral de alerta se ha fijado en **0.60**.")

# =========================================================
# 8) RANKING + GRÁFICO
# =========================================================
st.subheader("🏅 Ranking de provincias por probabilidad de riesgo alto")

agg_prov = (
    df_f.groupby("provincia", as_index=False)
    .agg(
        prob_media=("prob_riesgo_alto", "mean"),
        prob_max=("prob_riesgo_alto", "max"),
        alerta=("alerta_incendio", "max"),
    )
    .sort_values("prob_media", ascending=False)
)

st.dataframe(agg_prov, use_container_width=True)

chart = (
    alt.Chart(agg_prov)
    .mark_bar()
    .encode(
        x=alt.X("prob_media:Q", title="Probabilidad de riesgo alto"),
        y=alt.Y("provincia:N", sort="-x", title="Provincia"),
        color=alt.condition(
            alt.datum.alerta == 1,
            alt.value("#ff4b4b"),
            alt.value("#1f77b4"),
        ),
        tooltip=[
            "provincia:N",
            alt.Tooltip("prob_media:Q", format=".3f"),
            alt.Tooltip("prob_max:Q", format=".3f"),
            "alerta:Q",
        ],
    )
    .properties(height=min(600, len(agg_prov) * 25))
)

st.altair_chart(chart, use_container_width=True)

# =========================================================
# 9) MAPA DE RIESGO POR PROVINCIA
# =========================================================
st.markdown("---")
st.subheader("🗺️ Mapa de riesgo medio por provincia")

@st.cache_data(show_spinner=True)
def cargar_provincias_geometria():
    shp_path = os.path.join(DATA_DIR, "gadm41_ESP_2.shp")

    if not os.path.exists(shp_path):
        raise FileNotFoundError(f"No se encuentra el shapefile: {shp_path}")

    gdf = gpd.read_file(shp_path)[["NAME_2", "geometry"]]
    gdf = gdf.rename(columns={"NAME_2": "provincia"})

    gdf["provincia_norm"] = (
        gdf["provincia"]
        .astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.lower()
        .str.strip()
    )

    return gdf





def norm(s):
    return (
        s.astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.lower()
        .str.strip()
    )


gdf = cargar_provincias_geometria()
agg_prov["provincia_norm"] = norm(agg_prov["provincia"])

gdfm = gdf.merge(
    agg_prov[["provincia_norm", "prob_media"]],
    on="provincia_norm",
    how="left",
).fillna({"prob_media": 0})

gdfm = gdfm.to_crs(epsg=4326)

max_prob = gdfm["prob_media"].max()
gdfm["prob_norm"] = gdfm["prob_media"] / max_prob if max_prob > 0 else 0

layer = pdk.Layer(
    "GeoJsonLayer",
    data=gdfm.__geo_interface__,
    pickable=True,
    filled=True,
    stroked=True,
    get_fill_color="[255 * prob_norm, (1 - prob_norm) * 255, 0, 150]",
    get_line_color=[50, 50, 50],
    line_width_min_pixels=1,
)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=pdk.ViewState(latitude=40.0, longitude=-3.7, zoom=5),
    tooltip={
        "html": "<b>{provincia}</b><br/>Probabilidad media: {prob_media}",
        "style": {"color": "white"},
    },
)

st.pydeck_chart(deck)

st.caption(
    f"Colores calculados para la fecha **{fecha_seleccionada.strftime('%Y-%m-%d')}**. "
    "Rojo = mayor riesgo relativo según el modelo."
)



