import os
from datetime import datetime

import streamlit as st
import pandas as pd
import altair as alt
from pymongo import MongoClient
import geopandas as gpd  
import json
import pydeck as pdk
from shapely.geometry import shape   

# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(
    page_title="Datos del proyecto – Incendios España",
    layout="wide",
)

st.title("📚 Datos del proyecto")
st.markdown(
    """
Esta página resume los distintos datasets usados en el proyecto y permite
explorar rápidamente la información de cada fuente:

- 🛰️ **FIRMS** (detecciones satelitales históricas)  
- 🔥 **Copernicus EFFIS** (severidad y área quemada)  
- 🌦️ **Open-Meteo** (meteorología histórica)  
- ⏱️ **Datos operativos generados por _cronjobs_ (AEMET + FIRMS actualizado)**  
- 🔄 **Equivalencias de variables entre datasets**  
"""
)

# =========================================================
# TABS PRINCIPALES
# =========================================================
(
    tab_firms,
    tab_cop,
    tab_openmeteo,
    tab_cronjobs,
    tab_equiv,
) = st.tabs(
    [
        "🛰️ FIRMS",
        "🔥 Copernicus EFFIS",
        "🌦️ Open-Meteo histórico",
        "⏱️ Datos cronjobs",
        "🔄 Equivalencias",
    ]
)

# =========================================================
# CARGA FIRMS DESDE MONGO (FUENTE ÚNICA)
# =========================================================
@st.cache_data(show_spinner=True)
def load_firms_from_mongo() -> pd.DataFrame:
    """
    Carga el histórico FIRMS desde MongoDB.
    Colección esperada: incendios_espana.firms_historico
    """

    client = MongoClient(st.secrets["MONGO"]["URI"])
    db = client["incendios_espana"]
    col = db["firms_historico"]

    docs = list(col.find({}, {"_id": 0}))
    df = pd.DataFrame(docs)

    if df.empty:
        return df

    # Tipos y limpieza mínima
    df["firms_date"] = pd.to_datetime(df["firms_date"], errors="coerce")
    df["provincia"] = df["provincia"].astype(str).str.strip()

    return df


# =========================================================
# 1) TAB FIRMS
# =========================================================
with tab_firms:
    st.header("🛰️ FIRMS – Detecciones históricas de incendios")

    try:
        df_firms_full = load_firms_from_mongo()
    except Exception as e:
        st.error(f"❌ No se pudo cargar FIRMS desde MongoDB: {e}")
        st.stop()

    st.success(f"Registros FIRMS: **{len(df_firms_full):,}**")

    if df_firms_full["firms_date"].notna().any():
        min_date_global = df_firms_full["firms_date"].min()
        max_date_global = df_firms_full["firms_date"].max()
        st.caption(
            f"🗓️ Periodo disponible FIRMS: "
            f"**{min_date_global:%d/%m/%Y} – {max_date_global:%d/%m/%Y}**"
        )
    else:
        st.caption("🗓️ Periodo disponible FIRMS: no hay fechas válidas.")

    # ---------- Filtros SOLO para FIRMS ----------
    st.markdown("### 🔍 Filtros FIRMS")

    df_firms = df_firms_full.copy()

    col_f1, col_f2 = st.columns(2)

    # Filtro por fechas
    with col_f1:
        if min_date_global and max_date_global:
            date_min = min_date_global.date()
            date_max = max_date_global.date()
            date_range = st.date_input(
                "Rango de fechas",
                value=(date_min, date_max),
                min_value=date_min,
                max_value=date_max,
            )

            if isinstance(date_range, tuple) and len(date_range) == 2:
                dmin, dmax = date_range
                mask_date = (
                    (df_firms["firms_date"].dt.date >= dmin)
                    & (df_firms["firms_date"].dt.date <= dmax)
                )
                df_firms = df_firms[mask_date]
        else:
            st.caption("No se puede filtrar por fecha (no hay fechas válidas).")



    st.markdown(
        f"📁 **Registros mostrados en esta vista (con filtros):** {len(df_firms):,}"
    )

    # ---------- Explicación de columnas ----------
    with st.expander("ℹ️ ¿Qué significan las columnas principales de FIRMS?"):
        st.markdown(
            """
- **latitude / longitude / firms_latitude / firms_longitude**: posición geográfica exacta de la detección.  
- **firms_date / acq_date + acq_time**: fecha (y hora) en la que el satélite detecta el punto caliente.  
- **brightness / firms_brightness**: temperatura aparente del fuego (Kelvin); a mayor valor, mayor intensidad térmica.  
- **frp / firms_frp**: _Fire Radiative Power_ (MW), una medida de la energía radiada por el fuego.  
- **provincia**: provincia española asignada a la detección tras el cruce espacial.  
"""
        )

    # ---------- Muestra de datos ----------
    st.subheader("📋 Muestra de datos FIRMS (con filtros aplicados)")
    possible_cols = [
        "firms_date",
        "provincia",
        "latitude",
        "longitude",
        "firms_latitude",
        "firms_longitude",
        "brightness",
        "firms_brightness",
        "frp",
        "firms_frp",
    ]
    sample_cols = [c for c in possible_cols if c in df_firms.columns]
    st.dataframe(df_firms[sample_cols].head(20), use_container_width=True)

    # ---------- KPIs sobre la vista filtrada ----------
    st.subheader("📊 Indicadores básicos (vista filtrada)")
    c1, c3, c4 = st.columns(3)

    c1.metric("Nº detecciones", f"{len(df_firms):,}")

    brightness_col = (
        "firms_brightness"
        if "firms_brightness" in df_firms.columns
        else "brightness"
        if "brightness" in df_firms.columns
        else None
    )
    if brightness_col:
        c3.metric("Brightness medio", f"{df_firms[brightness_col].mean():.1f}")
    else:
        c3.metric("Brightness medio", "N/D")

    frp_col = (
        "firms_frp"
        if "firms_frp" in df_firms.columns
        else "frp"
        if "frp" in df_firms.columns
        else None
    )
    if frp_col:
        c4.metric("FRP medio (MW)", f"{df_firms[frp_col].mean():.2f}")
    else:
        c4.metric("FRP medio (MW)", "N/D")


    # ---------- Serie anual (vista filtrada) ----------
    st.subheader("📈 Evolución anual del número de detecciones (vista filtrada)")
    if df_firms["firms_date"].notna().any():
        df_firms["year"] = df_firms["firms_date"].dt.year
        count_col = brightness_col or "firms_date"
        yearly = (
            df_firms.groupby("year", as_index=False)
            .agg(n_fires=(count_col, "count"))
            .sort_values("year")
        )

        chart_year = (
            alt.Chart(yearly)
            .mark_bar()
            .encode(
                x=alt.X("year:O", title="Año"),
                y=alt.Y("n_fires:Q", title="Nº detecciones FIRMS"),
                tooltip=["year:O", "n_fires:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart_year, use_container_width=True)
    else:
        st.info("No hay fechas válidas para construir la serie anual.")

# =========================================================
# 2) TAB COPERNICUS EFFIS
# =========================================================

@st.cache_data(show_spinner=True)
def load_copernicus_spain() -> gpd.GeoDataFrame:
    client = MongoClient(st.secrets["MONGO"]["URI"])
    db = client["incendios_espana"]
    col = db["copernicus_effis"]

    docs = list(col.find({}, {"_id": 0}))
    if not docs:
        return gpd.GeoDataFrame()

    geometries = [shape(d.pop("geometry")) for d in docs]

    return gpd.GeoDataFrame(
        docs,
        geometry=geometries,
        crs="EPSG:4326",
    )


with tab_cop:
    st.header("🔥 Copernicus EFFIS – Incendios forestales en España")

    st.markdown(
        """
        Perímetros oficiales de incendios forestales (**Copernicus EFFIS**).

        - 🇪🇸 Dataset limitado a España  
        - 🗺️ Polígonos reales  
        - ⚡ Geometría simplificada
        """
    )

    

    # ---------- CARGA DATASET ----------
    gdf = load_copernicus_spain()

    if gdf.empty:
        st.warning("No hay datos Copernicus en MongoDB.")
    else:
        # resto del código Copernicus

        st.success(f"Incendios cargados: **{len(gdf):,}**")
    
        # ---------- NORMALIZACIÓN ----------
        gdf["YEAR"] = pd.to_numeric(gdf["YEAR"], errors="coerce")
        gdf["AREA_HA"] = pd.to_numeric(gdf["AREA_HA"], errors="coerce")
    
      # ---------- FILTROS ----------
        st.subheader("🔎 Filtros (opcionales)")
        
        col1, col2 = st.columns(2)
        
        # Valores posibles
        years = sorted(gdf["YEAR"].dropna().unique())
        provs = sorted(gdf["PROVINCE"].dropna().unique())
        
        with col1:
            year_sel = st.selectbox(
                "Año",
                ["Todos"] + years,
                index=0,   # 👈 por defecto TODOS
            )
        
        with col2:
            prov_sel = st.selectbox(
                "Provincia",
                ["Todas"] + provs,
                index=0,   # 👈 por defecto TODAS
            )
        
        # ---------- APLICAR FILTROS SOLO SI CAMBIAN ----------
        gdf_filt = gdf.copy()
        
        if year_sel != "Todos":
            gdf_filt = gdf_filt[gdf_filt["YEAR"] == year_sel]
        
        if prov_sel != "Todas":
            gdf_filt = gdf_filt[gdf_filt["PROVINCE"] == prov_sel]
        
        st.caption(f"Incendios mostrados: **{len(gdf_filt):,}**")
            
        # ---------- MÉTRICAS ----------
        c1, c2 = st.columns(2)
    
        c1.metric(
            "Área total quemada (ha)",
            f"{gdf_filt['AREA_HA'].sum():,.0f}",
        )
    
        c2.metric(
            "Número de incendios",
            f"{len(gdf_filt):,}",
        )
    
        # ---------- MAPA ----------
        st.subheader("🗺️ Mapa de perímetros quemados")
    
        if not gdf_filt.empty:
            gdf_map = gdf_filt.copy()
    
            for col in ["FIREDATE", "LASTUPDATE"]:
                if col in gdf_map.columns:
                    gdf_map[col] = gdf_map[col].astype(str)
    
            geojson = json.loads(gdf_map.to_json())
    
            layer = pdk.Layer(
                "GeoJsonLayer",
                geojson,
                pickable=True,
                filled=True,
                stroked=True,
                get_fill_color=[220, 20, 20, 140],
                get_line_color=[120, 0, 0, 220],
                line_width_min_pixels=1,
            )
    
            centroid = gdf_map.geometry.unary_union.centroid
    
            view_state = pdk.ViewState(
                latitude=centroid.y,
                longitude=centroid.x,
                zoom=6,
            )
    
            deck = pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                tooltip={
                    "html": """
                    <b>Provincia:</b> {PROVINCE}<br/>
                    <b>Año:</b> {YEAR}<br/>
                    <b>Área quemada (ha):</b> {AREA_HA}<br/>
                    <b>Fecha:</b> {FIREDATE}
                    """
                },
            )
    
            st.pydeck_chart(deck, use_container_width=True)
    
        # ---------- TABLA ----------
        with st.expander("📋 Ver tabla de atributos"):
            st.dataframe(
                gdf_filt
                .drop(columns="geometry")
                .sort_values("AREA_HA", ascending=False),
                use_container_width=True,
            )
        
        


# =========================================================
# 3) TAB OPEN-METEO HISTÓRICO
# =========================================================
@st.cache_data(show_spinner=True, ttl=0)
def load_openmeteo(path: str) -> pd.DataFrame:
    df_ = pd.read_csv(path)

    # --- limpiar nombres de columnas (BOM, espacios, etc.) ---
    df_.columns = (
        df_.columns
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )

    # --- detectar columna de fecha ---
    if "time" in df_.columns:
        df_["date"] = pd.to_datetime(df_["time"], errors="coerce")
    elif "date" in df_.columns:
        df_["date"] = pd.to_datetime(df_["date"], errors="coerce")
    elif "datetime" in df_.columns:
        df_["date"] = pd.to_datetime(df_["datetime"], errors="coerce")
    elif "fecha" in df_.columns:
        df_["date"] = pd.to_datetime(df_["fecha"], errors="coerce")
    else:
        raise ValueError(
            f"No se encontró columna de fecha. Columnas disponibles: {list(df_.columns)}"
        )

    # --- renombrado estándar ---
    df_ = df_.rename(
        columns={
            "temperature_2m_max": "meteo_temp_max",
            "temperature_2m_min": "meteo_temp_min",
            "relative_humidity_2m_min": "meteo_humidity_min",
            "windspeed_10m_max": "meteo_wind_max",
        }
    )

    return df_



OPENMETEO_CSV = (
    "https://github.com/aitorherran06/tfm/blob/main/data/openmeteo_historico.csv"
)


with tab_openmeteo:
    st.header("🌦️ Open-Meteo – Meteorología histórica")

    st.markdown(
        """
Open-Meteo proporciona **series históricas de meteorología** a partir de coordenadas.  
En este dataset, los datos ya están **agregados por provincia y día**, 
de forma que cada fila representa el clima diario de una provincia.
"""
    )

    # ---------- CARGA DATASET ----------
    try:
        df_met = load_openmeteo(OPENMETEO_CSV)

        st.success(f"Registros provincia–día: **{len(df_met):,}**")

        if df_met["date"].notna().any():
            min_date_met = df_met["date"].min()
            max_date_met = df_met["date"].max()
            st.caption(
                f"🗓️ Periodo disponible Open-Meteo: "
                f"**{min_date_met:%d/%m/%Y} – {max_date_met:%d/%m/%Y}**"
            )
        else:
            st.caption("🗓️ Periodo disponible Open-Meteo: no hay fechas válidas.")

    except Exception as e:
        st.error(f"❌ No se pudo cargar Open-Meteo: {e}")
        st.info("Revisa el CSV y el nombre de la columna de fecha.")
        st.stop()

    # ---------- EXPLICACIÓN ----------
    with st.expander("ℹ️ ¿Qué significan las columnas de Open-Meteo?"):
        st.markdown(
            """
- **date**: día al que corresponde la observación.  
- **provincia**: provincia asociada a las coordenadas.  
- **meteo_temp_max / meteo_temp_min**: temperatura máxima y mínima diarias (°C).  
- **meteo_humidity_min**: humedad relativa mínima del día (%).  
- **meteo_wind_max**: velocidad máxima del viento (10 m).
"""
        )

    # ---------- TABLA ----------
    st.subheader("📋 Muestra de datos meteorológicos")

    cols_met_sample = [
        "date",
        "provincia",
        "meteo_temp_max",
        "meteo_temp_min",
        "meteo_humidity_min",
        "meteo_wind_max",
    ]
    cols_met_sample = [c for c in cols_met_sample if c in df_met.columns]

    st.dataframe(
        df_met[cols_met_sample].head(20),
        use_container_width=True,
    )

    # ---------- MÉTRICAS ----------
    st.subheader("📊 Indicadores básicos")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Temp. máxima media",
        f"{df_met['meteo_temp_max'].mean():.1f} °C"
        if "meteo_temp_max" in df_met.columns
        else "N/D",
    )

    c2.metric(
        "Temp. mínima media",
        f"{df_met['meteo_temp_min'].mean():.1f} °C"
        if "meteo_temp_min" in df_met.columns
        else "N/D",
    )

    c3.metric(
        "Humedad mínima media",
        f"{df_met['meteo_humidity_min'].mean():.1f} %"
        if "meteo_humidity_min" in df_met.columns
        else "N/D",
    )

    c4.metric(
        "Viento máx. medio",
        f"{df_met['meteo_wind_max'].mean():.1f} km/h"
        if "meteo_wind_max" in df_met.columns
        else "N/D",
    )

    # ---------- SERIE MENSUAL ----------
    if "meteo_temp_max" in df_met.columns:
        st.subheader("📈 Temperatura máxima media por mes")

        df_met["month"] = df_met["date"].dt.month
        df_met["month_name"] = df_met["date"].dt.strftime("%b")

        monthly = (
            df_met.groupby(["month", "month_name"], as_index=False)
            .agg(temp_max_mean=("meteo_temp_max", "mean"))
            .sort_values("month")
        )

        chart_month = (
            alt.Chart(monthly)
            .mark_line(point=True)
            .encode(
                x=alt.X(
                    "month_name:N",
                    title="Mes",
                    sort=[
                        "Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec",
                    ],
                ),
                y=alt.Y(
                    "temp_max_mean:Q",
                    title="Temp. máxima media (°C)",
                ),
            )
            .properties(height=300)
        )

        st.altair_chart(chart_month, use_container_width=True)



# =========================================================
# 4) TAB DATOS CRONJOBS (AEMET + FIRMS actualizado)
# =========================================================
with tab_cronjobs:
    st.header("⏱️ Datos operativos generados por cronjobs")
    st.markdown(
        """
Esta sección resume los **datasets operativos** que se actualizan automáticamente 
mediante _cronjobs_ y alimentan:

- el panel de **puntos calientes FIRMS recientes**, y  
- el panel de **predicción de riesgo a partir de AEMET**.
"""
    )

    # Conexión a Mongo
    try:
        mongo_uri = st.secrets["MONGO"]["URI"]
        client = MongoClient(mongo_uri)
        db = client["incendios_espana"]
    except Exception as e:
        db = None
        st.error(f"❌ No se pudo conectar a MongoDB (revisa `MONGO.URI`): {e}")

    if db is not None:
        # ---------- AEMET PREDICCIONES ----------
        st.subheader("🌦️ Colección `aemet_predicciones`")
        st.markdown(
            """
Contiene las **predicciones meteorológicas oficiales de AEMET** para los próximos días
en cada provincia. Se genera diariamente mediante un proceso automático.
"""
        )

        col_aemet = db["aemet_predicciones"]
        count_aemet = col_aemet.count_documents({})
        st.write(f"📄 **Documentos totales:** {count_aemet}")

        # Rango de fechas AEMET
        try:
            doc_min_aemet = col_aemet.find_one(sort=[("fecha", 1)])
            doc_max_aemet = col_aemet.find_one(sort=[("fecha", -1)])
            if doc_min_aemet and doc_max_aemet:
                st.caption(
                    f"🗓️ Periodo disponible AEMET: "
                    f"**{doc_min_aemet.get('fecha')} – {doc_max_aemet.get('fecha')}**"
                )
        except Exception:
            st.caption("🗓️ Periodo disponible AEMET: no se pudo calcular.")

        docs_aemet = list(col_aemet.find({}, {"_id": 0}).limit(20))

        filas = []
        for d in docs_aemet:
            temp = d.get("temperatura", {}) or {}
            hum = d.get("humedadRelativa", {}) or {}

            fila = {
                "provincia": d.get("provincia"),
                "fecha": d.get("fecha"),
                "tmax": temp.get("maxima"),
                "tmin": temp.get("minima"),
                "humedad_max": hum.get("maxima"),
                "humedad_min": hum.get("minima"),
                "uvMax": d.get("uvMax"),
            }
            filas.append(fila)

        if filas:
            df_aemet_sample = pd.DataFrame(filas)
            df_aemet_sample["fecha"] = pd.to_datetime(
                df_aemet_sample["fecha"], errors="coerce"
            )
            st.dataframe(df_aemet_sample, use_container_width=True)
        else:
            st.info("No hay documentos que mostrar en la muestra.")

        st.markdown("---")

        # ---------- FIRMS ACTUALIZADO ----------
        st.subheader("🔥 Colección `firms_actualizado`")
        st.markdown(
            """
Contiene las **detecciones FIRMS más recientes** (últimos días) ya filtradas a España.  
Se actualiza automáticamente cada pocas horas mediante un _cronjob_.
"""
        )

        col_firms = db["firms_actualizado"]
        count_firms = col_firms.count_documents({})
        st.write(f"📄 **Documentos totales:** {count_firms}")

        # Rango de fechas FIRMS actualizado
        try:
            doc_min_firms = col_firms.find_one(
                {"fecha": {"$exists": True}}, sort=[("fecha", 1)]
            ) or col_firms.find_one(sort=[("datetime", 1)])

            doc_max_firms = col_firms.find_one(
                {"fecha": {"$exists": True}}, sort=[("fecha", -1)]
            ) or col_firms.find_one(sort=[("datetime", -1)])

            if doc_min_firms and doc_max_firms:
                vmin = doc_min_firms.get("fecha") or doc_min_firms.get("datetime")
                vmax = doc_max_firms.get("fecha") or doc_max_firms.get("datetime")
                st.caption(
                    f"🗓️ Periodo disponible FIRMS actualizado: **{vmin} – {vmax}**"
                )
        except Exception:
            st.caption(
                "🗓️ Periodo disponible FIRMS actualizado: no se pudo calcular."
            )

        docs_firms = list(col_firms.find({}, {"_id": 0}).limit(20))

        if docs_firms:
            df_firms_sample = pd.DataFrame(docs_firms)
            st.dataframe(df_firms_sample, use_container_width=True)
        else:
            st.info("No hay documentos que mostrar en la muestra.")

    st.success("✅ Información de cronjobs mostrada correctamente.")

# =========================================================
# 5) TAB EQUIVALENCIAS
# =========================================================
with tab_equiv:
    st.header("🔄 Equivalencias de variables entre datasets")
    st.markdown(
        """
Esta sección muestra cómo se corresponden las columnas entre distintas fuentes, 
lo que permite **unificar los datos** para análisis y modelado.
"""
    )

    tab1, tab2 = st.tabs(["🛰️ FIRMS Histórico ↔ Actualizado", "🌦️ AEMET ↔ Open-Meteo"])

    # -----------------------------------------------------
    #   TAB 1 : FIRMS
    # -----------------------------------------------------
    with tab1:
        st.header("🛰️ Equivalencias FIRMS — Histórico ↔ Actualizado")
        st.markdown(
            """
Los ficheros de FIRMS antiguos y los más recientes usan nombres de columnas distintos, 
aunque representan la misma información.  
Esta tabla resume las equivalencias usadas en el proyecto.
"""
        )

        equivalencias_firms = pd.DataFrame(
            {
                "FIRMS Histórico": [
                    "latitude",
                    "longitude",
                    "brightness",
                    "scan",
                    "track",
                    "acq_date",
                    "acq_time",
                    "satellite",
                    "instrument",
                ],
                "FIRMS Actualizado": [
                    "latitud",
                    "longitud",
                    "brightness",
                    "scan",
                    "track",
                    "fecha",
                    "hora",
                    "satellite",
                    "confianza",
                ],
                "Descripción": [
                    "Latitud del punto detectado",
                    "Longitud del punto detectado",
                    "Brillo (temperatura aparente del fuego, Kelvin)",
                    "Tamaño del píxel en dirección de escaneo",
                    "Tamaño del píxel en dirección de la trayectoria del satélite",
                    "Fecha de adquisición",
                    "Hora de adquisición (UTC)",
                    "Satélite utilizado",
                    "Nivel de confianza en la detección",
                ],
            }
        )

        st.subheader("📑 Tabla comparativa FIRMS")
        st.dataframe(equivalencias_firms, use_container_width=True)

        st.info(
            """
➤ Los datasets contienen la misma información esencial, aunque con ajustes en nombres.  
➤ El campo **confianza** aparece en versiones actualizadas.  
"""
        )

        st.subheader("🔄 Diccionario de renombrado FIRMS")
        diccionario_firms = {
            "latitude": "latitud",
            "longitude": "longitud",
            "acq_date": "fecha",
            "acq_time": "hora",
            "instrument": "instrumento",
        }
        st.code(diccionario_firms, language="python")
        st.caption("Aplicación en pandas:")
        st.code("df.rename(columns=diccionario_firms, inplace=True)", language="python")

    # -----------------------------------------------------
    #   TAB 2 : AEMET ↔ Open-Meteo
    # -----------------------------------------------------
    with tab2:
        st.header("🌦️ Equivalencias entre AEMET y Open-Meteo")
        st.markdown(
            """
AEMET y Open-Meteo describen fenómenos meteorológicos similares, 
pero con **nombres de columnas y estructuras distintas**.  
Esta tabla resume cómo se han alineado en el proyecto.
"""
        )

        equivalencias = pd.DataFrame(
            {
                "AEMET": [
                    "fecha",
                    "municipio",
                    "provincia",
                    "tmax",
                    "tmin",
                    "humedad_max",
                    "humedad_min",
                    "viento",
                    "fuente",
                ],
                "Open-Meteo": [
                    "time",
                    None,
                    "provincia",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "relative_humidity_2m_max",
                    "relative_humidity_2m_min",
                    "windspeed_10m_max",
                    None,
                ],
                "Descripción": [
                    "Fecha de observación o predicción",
                    "Municipio o estación meteorológica",
                    "Provincia o región administrativa",
                    "Temperatura máxima diaria (°C)",
                    "Temperatura mínima diaria (°C)",
                    "Humedad relativa máxima (%)",
                    "Humedad relativa mínima (%)",
                    "Velocidad máxima del viento",
                    "Fuente de los datos",
                ],
            }
        )

        st.subheader("📑 Tabla comparativa AEMET ↔ Open-Meteo")
        st.dataframe(equivalencias, use_container_width=True)

        st.info(
            """
➤ Open-Meteo usa coordenadas (lat/lon) en lugar de municipios.  
➤ Incluye más variables como precipitación total o radiación solar.  
"""
        )

        st.subheader("🔄 Diccionario de renombrado AEMET → Open-Meteo")
        diccionario_renombrado = {
            "fecha": "time",
            "tmax": "temperature_2m_max",
            "tmin": "temperature_2m_min",
            "humedad_max": "relative_humidity_2m_max",
            "humedad_min": "relative_humidity_2m_min",
            "viento": "windspeed_10m_max",
            "provincia": "provincia",
        }
        st.code(diccionario_renombrado, language="python")
        st.caption("Aplicación en pandas:")
        st.code("df.rename(columns=diccionario_renombrado, inplace=True)", language="python")

    st.success("✅ Bloque de equivalencias cargado correctamente.")









