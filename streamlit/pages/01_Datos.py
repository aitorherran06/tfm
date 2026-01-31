import os
from datetime import datetime

import streamlit as st
import pandas as pd
import altair as alt
from pymongo import MongoClient
import geopandas as gpd  # Para Copernicus (más adelante)

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
# 2) TAB COPERNICUS EFFIS (shapefile en carpeta copernicus)
# =========================================================
with tab_cop:
    st.header("🔥 Copernicus EFFIS – Severidad y área quemada")

    st.markdown(
        """
Copernicus **EFFIS** (European Forest Fire Information System) proporciona 
los **perímetros oficiales de incendios** en Europa.  
En este dataset, **cada fila representa un polígono de área quemada**, con atributos 
sobre su extensión, fecha y localización administrativa.
"""
    )

    @st.cache_data(show_spinner=True)
    def load_copernicus(path: str) -> gpd.GeoDataFrame:
        gdf_ = gpd.read_file(path)
        return gdf_

    try:
        gdf_effis = load_copernicus(COPERNICUS_SHP)
    #    st.caption(f"📂 Shapefile cargado: `{COPERNICUS_SHP}`")
        st.success(f"Polígonos quemados: **{len(gdf_effis):,}**")
    except Exception as e:
        st.error(f"❌ No se pudo cargar Copernicus EFFIS: {e}")
        st.stop()

    # Rango temporal: intentamos detectar columna de fecha o de año
    date_cols = [c for c in gdf_effis.columns if "date" in c.lower()]
    year_cols = [c for c in gdf_effis.columns if "year" in c.lower()]

    rango_str = None
    if date_cols:
        col = date_cols[0]
        gdf_effis[col] = pd.to_datetime(gdf_effis[col], errors="coerce")
        if gdf_effis[col].notna().any():
            min_d = gdf_effis[col].min()
            max_d = gdf_effis[col].max()
            rango_str = f"{min_d:%d/%m/%Y} – {max_d:%d/%m/%Y}"
    elif year_cols:
        col = year_cols[0]
        min_y = gdf_effis[col].min()
        max_y = gdf_effis[col].max()
        rango_str = f"{int(min_y)} – {int(max_y)}"

    if rango_str:
        st.caption(f"🗓️ Periodo disponible Copernicus EFFIS: **{rango_str}**")
    else:
        st.caption(
            "🗓️ Periodo disponible Copernicus EFFIS: no se ha encontrado columna de fecha/año."
        )

    # Explicación de columnas
    with st.expander("ℹ️ ¿Qué significan las columnas principales de EFFIS?"):
        st.markdown(
            """
Aunque los nombres pueden variar según la versión del shapefile, normalmente encontrarás:

- **geometry**: polígono geoespacial que delimita el área quemada.  
- **AREA_HA / BA_HA / BURN_AREA**: superficie quemada en hectáreas.  
- **YEAR / BA_YEAR / FIRE_YEAR**: año del incendio.  
- **NUTS_ID / NUTS_NAME**: código/nombre de la unidad administrativa europea (región).  
- **ADM_NAME / provincia / municipio**: nombre de la unidad administrativa (según país).  

En esta página nos centramos sobre todo en:
- **el área quemada (ha)** → para medir la severidad,  
- **las columnas de tipo texto** → para agrupar por región, provincia, etc.
"""
        )

    st.subheader("📋 Muestra de datos EFFIS (atributos no geométricos)")
    attrs = gdf_effis.drop(columns=["geometry"], errors="ignore")
    st.dataframe(attrs.head(20), use_container_width=True)

    # Detectar columna de área en hectáreas
    area_candidates = [
        c for c in attrs.columns if "area" in c.lower() and "ha" in c.lower()
    ]
    if not area_candidates:
        for cand in ["AREA_HA", "BA_HA", "BURN_AREA", "BAAREA"]:
            if cand in attrs.columns:
                area_candidates = [cand]
                break
    area_col = area_candidates[0] if area_candidates else None

    # Métricas básicas
    c1, c2 = st.columns(2)
    if area_col:
        area_numeric = pd.to_numeric(attrs[area_col], errors="coerce")
        area_total = area_numeric.sum()
        c1.metric("Área total quemada (ha)", f"{area_total:,.1f}")
    else:
        c1.metric("Área total quemada (ha)", "N/D")

    c2.metric("Número de polígonos", f"{len(attrs):,}")

    # Ranking por entidad
    st.subheader("🏅 Entidades con mayor área quemada (Copernicus)")

    if area_col:
        cat_cols = attrs.select_dtypes(include="object").columns.tolist()

        if cat_cols:
            candidatos_nombre = [
                "NAME",
                "name",
                "NUTS_NAME",
                "NUTS_ID",
                "ADM_NAME",
                "provincia",
                "municipio",
            ]
            default_col = None
            for cand in candidatos_nombre:
                if cand in cat_cols:
                    default_col = cand
                    break
            if default_col is None:
                default_col = cat_cols[0]

            group_col = st.selectbox(
                "Agrupar por:",
                options=cat_cols,
                index=cat_cols.index(default_col),
                help="Columna categórica usada para agrupar el área quemada.",
            )

            area_numeric = pd.to_numeric(attrs[area_col], errors="coerce")

            ranking = (
                attrs.assign(_area=area_numeric)
                .groupby(group_col, as_index=False)
                .agg(area_total=("_area", "sum"))
                .sort_values("area_total", ascending=False)
            )

            chart_rank = (
                alt.Chart(ranking.head(15))
                .mark_bar()
                .encode(
                    x=alt.X("area_total:Q", title="Área quemada total (ha)"),
                    y=alt.Y(f"{group_col}:N", sort="-x", title=group_col),
                    tooltip=[group_col, "area_total"],
                )
                .properties(height=400)
            )
            st.altair_chart(chart_rank, use_container_width=True)
        else:
            st.info(
                "No se han encontrado columnas de texto para agrupar (nombre de provincia, NUTS, etc.)."
            )
    else:
        st.info(
            "No se ha identificado una columna de área en hectáreas, por lo que no se puede construir el ranking."
        )

# =========================================================
# 3) TAB OPEN-METEO HISTÓRICO (openmeteo_historico.csv)
# =========================================================
with tab_openmeteo:
    st.header("🌦️ Open-Meteo – Meteorología histórica")

    st.markdown(
        """
Open-Meteo proporciona **series históricas de meteorología** a partir de coordenadas.  
En este dataset, los datos ya están **agregados por provincia y día**, 
de forma que cada fila representa el clima diario de una provincia.
"""
    )

    @st.cache_data(show_spinner=True)
    def load_openmeteo(path: str) -> pd.DataFrame:
        # Leemos usando la columna 'time' como fecha
        df_ = pd.read_csv(path, parse_dates=["time"])

        # Renombramos a los nombres que usa el resto del panel
        df_ = df_.rename(
            columns={
                "time": "date",
                "temperature_2m_max": "meteo_temp_max",
                "temperature_2m_min": "meteo_temp_min",
                "relative_humidity_2m_min": "meteo_humidity_min",
                "windspeed_10m_max": "meteo_wind_max",
            }
        )
        return df_

    try:
        df_met = load_openmeteo(OPENMETEO_CSV)
    #    st.caption(f"📂 Archivo cargado: `{OPENMETEO_CSV}`")
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
        st.stop()

    with st.expander("ℹ️ ¿Qué significan las columnas de Open-Meteo?"):
        st.markdown(
            """
- **date**: día al que corresponde la predicción/observación.  
- **provincia**: provincia asociada a las coordenadas usadas.  
- **meteo_temp_max / meteo_temp_min**: temperatura máxima y mínima diarias (°C).  
- **meteo_humidity_min**: humedad relativa mínima del día (%); valores bajos indican sequedad.  
- **meteo_wind_max**: velocidad máxima del viento (10 m) durante el día.  
"""
        )

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
    st.dataframe(df_met[cols_met_sample].head(20), use_container_width=True)

    c1, c2, c3, c4 = st.columns(4)
    if "meteo_temp_max" in df_met.columns:
        c1.metric("Temp. máxima media", f"{df_met['meteo_temp_max'].mean():.1f} °C")
    else:
        c1.metric("Temp. máxima media", "N/D")

    if "meteo_temp_min" in df_met.columns:
        c2.metric("Temp. mínima media", f"{df_met['meteo_temp_min'].mean():.1f} °C")
    else:
        c2.metric("Temp. mínima media", "N/D")

    if "meteo_humidity_min" in df_met.columns:
        c3.metric(
            "Humedad mínima media", f"{df_met['meteo_humidity_min'].mean():.1f} %"
        )
    else:
        c3.metric("Humedad mínima media", "N/D")

    if "meteo_wind_max" in df_met.columns:
        c4.metric("Viento máx. medio", f"{df_met['meteo_wind_max'].mean():.1f} km/h")
    else:
        c4.metric("Viento máx. medio", "N/D")

    # Temperatura máxima media por mes
    if "meteo_temp_max" in df_met.columns:
        st.subheader("📈 Temperatura máxima media por mes (promedio de todos los años)")

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
                        "Jan",
                        "Feb",
                        "Mar",
                        "Apr",
                        "May",
                        "Jun",
                        "Jul",
                        "Aug",
                        "Sep",
                        "Oct",
                        "Nov",
                        "Dec",
                    ],
                ),
                y=alt.Y("temp_max_mean:Q", title="Temp. máxima media (°C)"),
                tooltip=[
                    alt.Tooltip("month_name:N", title="Mes"),
                    alt.Tooltip(
                        "temp_max_mean:Q", title="Temp. media máx.", format=".1f"
                    ),
                ],
            )
            .properties(height=300)
            .interactive()
        )

        st.altair_chart(chart_month, use_container_width=True)

        st.markdown("---")

        # Temperatura máxima media por año
        st.subheader("📈 Temperatura máxima media por año")

        df_met["year"] = df_met["date"].dt.year

        yearly_temp = (
            df_met.groupby("year", as_index=False)
            .agg(temp_max_mean=("meteo_temp_max", "mean"))
            .sort_values("year")
        )

        chart_year_temp = (
            alt.Chart(yearly_temp)
            .mark_line(point=True)
            .encode(
                x=alt.X("year:O", title="Año"),
                y=alt.Y("temp_max_mean:Q", title="Temp. máxima media (°C)"),
                tooltip=[
                    alt.Tooltip("year:O", title="Año"),
                    alt.Tooltip(
                        "temp_max_mean:Q", title="Temp. media máx.", format=".1f"
                    ),
                ],
            )
            .properties(height=300)
            .interactive()
        )
        st.altair_chart(chart_year_temp, use_container_width=True)
    else:
        st.info(
            "La columna 'meteo_temp_max' no está disponible; no se generan las series de temperatura."
        )

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










