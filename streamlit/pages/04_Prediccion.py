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
# 2) CARGA DEL MODELO (cache_resource)
# =========================================================
@st.cache_resource(show_spinner=True)
def cargar_modelo():
    modelo = joblib.load(MODEL_PATH)
    return modelo

modelo = cargar_modelo()

# =========================================================
# 3) CONEXIÓN A MONGO (cache_resource)
# =========================================================
@st.cache_resource(show_spinner=True)
def conectar_mongo():
    client = MongoClient(MONGO_URI)
    db = client["incendios_espana"]
    col = db["aemet_predicciones"]
    return col

col_aemet = conectar_mongo()

# =========================================================
# 4) CARGA Y TRANSFORMACIÓN AEMET → DATAFRAME
# =========================================================
def extraer_max(arr, campo=None):
    """Extrae máximo de array de dicts o lista de números."""
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
            "fecha": pd.to_datetime(d.get("fecha"), errors="coerce")
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

if len(df_aemet) == 0:
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

# Convertir a numérico
for c in feat_cols:
    df_pred[c] = pd.to_numeric(df_pred[c], errors="coerce")

df_pred = df_pred.dropna(subset=feat_cols)

if df_pred.empty:
    st.error("❌ Tras limpiar datos, no quedan filas válidas para el modelo.")
    st.stop()

# Predicciones
probas = modelo.predict_proba(df_pred[feat_cols])[:, 1]
df_pred["prob_riesgo_alto"] = probas

# Umbral de alerta
umbral_alerta = 0.60
df_pred["alerta_incendio"] = (df_pred["prob_riesgo_alto"] >= umbral_alerta).astype(int)

# =========================================================
# 6) FILTRO POR FECHA (SOLO UNO → visión de predicción diaria)
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

if df_f.empty:
    st.warning("No hay predicciones para la fecha seleccionada.")
    st.stop()

# =========================================================
# 7) KPIs RÁPIDOS
# =========================================================
c1, c2, c3 = st.columns(3)

c1.metric("Provincias con predicción", df_f["provincia"].nunique())

c2.metric(
    "Provincias en alerta (prob ≥ 0.60)",
    int(df_f["alerta_incendio"].sum())
)

c3.metric(
    "Probabilidad media nacional",
    f"{df_f['prob_riesgo_alto'].mean():.3f}"
)

st.caption(
    "El umbral de alerta se ha fijado en **0.60**: por encima de este valor se considera *riesgo alto*."
)

# =========================================================
# 8) RANKING POR PROVINCIA
# =========================================================
st.subheader("🏅 Ranking de provincias por probabilidad de riesgo alto")

agg_prov = (
    df_f.groupby("provincia", as_index=False)
    .agg(
        prob_media=("prob_riesgo_alto", "mean"),   # aquí será el valor del día
        prob_max=("prob_riesgo_alto", "max"),
        alerta=("alerta_incendio", "max"),
    )
    .sort_values("prob_media", ascending=False)
)

st.dataframe(agg_prov, use_container_width=True)

n_provincias = len(agg_prov)
n_top = min(20, n_provincias)

st.markdown(f"### 📈 Probabilidad de riesgo alto por provincia (top {n_top})")

df_top = agg_prov.head(n_top)

chart = (
    alt.Chart(df_top)
    .mark_bar()
    .encode(
        x=alt.X("prob_media:Q", title="Probabilidad de riesgo alto"),
        y=alt.Y(
            "provincia:N",
            sort="-x",
            title="Provincia",
            axis=alt.Axis(labelOverlap=False),
        ),
        color=alt.condition(
            alt.datum.alerta == 1,
            alt.value("#ff4b4b"),  # en alerta
            alt.value("#1f77b4"),  # sin alerta
        ),
        tooltip=[
            "provincia:N",
            alt.Tooltip("prob_media:Q", format=".3f", title="Prob. media"),
            alt.Tooltip("prob_max:Q", format=".3f", title="Prob. máx."),
            "alerta:Q",
        ],
    )
    .properties(height=n_top * 25)
)

st.altair_chart(chart, use_container_width=True)

# =========================================================
# 9) MAPA DE RIESGO POR PROVINCIA
# =========================================================
st.markdown("---")
st.subheader("🗺️ Mapa de riesgo medio por provincia (día seleccionado)")


@st.cache_data(show_spinner=True)
def cargar_provincias_geometria():
    GADM_PATH = r"C:\Users\aitor.herran\Desktop\incendios\gadm41_ESP_2.json"
    gdf = gpd.read_file(GADM_PATH)[["NAME_2", "geometry"]]
    gdf = gdf.rename(columns={"NAME_2": "provincia"})

    def norm(s):
        return (
            s.astype(str)
            .str.normalize("NFKD")
            .str.encode("ascii", errors="ignore")
            .str.decode("utf-8")
            .str.lower()
            .str.strip()
        )

    gdf["provincia_norm"] = norm(gdf["provincia"])
    return gdf


gdf = cargar_provincias_geometria()


def norm(s):
    return (
        s.astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.lower()
        .str.strip()
    )


agg_prov_mapa = agg_prov.copy()
agg_prov_mapa["provincia_norm"] = norm(agg_prov_mapa["provincia"])

gdfm = gdf.merge(
    agg_prov_mapa[["provincia_norm", "prob_media"]],
    on="provincia_norm",
    how="left",
)

gdfm["prob_media"] = gdfm["prob_media"].fillna(0)
gdfm = gdfm.to_crs(epsg=4326)

max_prob = gdfm["prob_media"].max()
gdfm["prob_norm"] = gdfm["prob_media"] / max_prob if max_prob > 0 else 0

geojson = gdfm.__geo_interface__

layer = pdk.Layer(
    "GeoJsonLayer",
    data=geojson,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="[255 * prob_norm, (1 - prob_norm) * 255, 0, 150]",
    get_line_color=[50, 50, 50],
    line_width_min_pixels=1,
)

view = pdk.ViewState(latitude=40.0, longitude=-3.7, zoom=5)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view,
    tooltip={
        "html": "<b>{provincia}</b><br/>Probabilidad media: {prob_media}",
        "style": {"color": "white"},
    },
)

st.pydeck_chart(deck)

st.caption(
    f"Colores calculados para la fecha **{fecha_seleccionada.strftime('%Y-%m-%d')}**. "
    "Rojo = mayor riesgo relativo según las predicciones del modelo."
)
