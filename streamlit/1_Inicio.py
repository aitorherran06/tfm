import streamlit as st

# =========================================================
# CONFIGURACIÓN
# =========================================================
st.set_page_config(
    page_title="Incendios en España – Análisis y Predicción",
    page_icon="🔥",
    layout="wide",
)

# ---------- CSS (tema + cards + botones) ----------
st.markdown(
    """
    <style>
    /* Layout */
    .block-container { padding-top: 3.5rem; padding-bottom: 1.5rem; }
    .hero {
        border-radius: 18px;
        padding: 26px 26px 22px 26px;
        background: radial-gradient(1200px 500px at 20% 10%, rgba(255, 140, 0, 0.30), transparent 60%),
                    radial-gradient(1200px 500px at 80% 20%, rgba(255, 0, 0, 0.18), transparent 55%),
                    linear-gradient(135deg, rgba(18,18,18,0.78), rgba(18,18,18,0.55));
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    }
    .hero h1 { margin: 0; font-size: 2.6rem; line-height: 1.1; }
    .hero h2 { margin: 0.4rem 0 0 0; font-weight: 600; color: rgba(255,255,255,0.88); }
    .muted { color: rgba(255,255,255,0.70); }
    .pill {
        display:inline-block; padding: 6px 10px; border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.04);
        margin-right: 8px; margin-top: 8px;
        font-size: 0.85rem;
    }
    .section-title { margin-top: 0.3rem; margin-bottom: 0.6rem; font-size: 1.35rem; font-weight: 750; }
    .card {
        border-radius: 16px;
        padding: 16px 16px 14px 16px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 6px 18px rgba(0,0,0,0.22);
        height: 100%;
    }
    .card h3 { margin: 0 0 6px 0; font-size: 1.1rem; }
    .card p { margin: 0.25rem 0 0.7rem 0; color: rgba(255,255,255,0.75); }
    .card ul { margin: 0.3rem 0 0 1.1rem; color: rgba(255,255,255,0.75); }
    .card li { margin-bottom: 4px; }
    .small { font-size: 0.9rem; color: rgba(255,255,255,0.70); }
    .divider {
        height: 1px; background: rgba(255,255,255,0.08); margin: 16px 0 14px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# HERO
# =========================================================
st.markdown(
    """
    <div class="hero">
        <div style="display:flex; justify-content:space-between; gap:16px; align-items:flex-start; flex-wrap:wrap;">
            <div style="min-width:280px; flex: 1;">
                <h1>🔥 Incendios en España</h1>
                <h2>Panel interactivo de análisis, visualización y predicción</h2>
                <div class="muted" style="margin-top:10px; max-width: 900px;">
                    Integra detecciones satelitales, meteorología y severidad para explorar patrones históricos,
                    monitorizar actividad reciente y estimar riesgo por provincia.
                </div>
                <div style="margin-top:10px;">
                    <span class="pill">🛰️ NASA FIRMS</span>
                    <span class="pill">🌦️ Open-Meteo</span>
                    <span class="pill">🔥 Copernicus EFFIS</span>
                    <span class="pill">📡 AEMET</span>
                    <span class="pill">🧠 Random Forest</span>
                </div>
            </div>
            <div style="min-width:260px;">
                <div class="small">Qué puedes hacer aquí</div>
                <ul class="small" style="margin-top:8px; margin-bottom:0;">
                    <li>Explorar históricos (evento / provincia–día)</li>
                    <li>Monitorizar puntos calientes recientes</li>
                    <li>Mapas y rankings por provincia</li>
                    <li>Predicción diaria de riesgo (AEMET + ML)</li>
                </ul>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)



# =========================================================
# SECCIONES PRINCIPALES (cards + CTA)
# =========================================================
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">🧭 Secciones principales</div>', unsafe_allow_html=True)

# Helper para CTA con switch_page (si no existe, mostramos aviso)
def go(page_path: str):
    try:
        st.switch_page(page_path)
    except Exception:
        st.info(
            f"No puedo navegar a `{page_path}` con `st.switch_page()`.\n"
            "Asegúrate de que el nombre de la página coincide con el archivo en `pages/`."
        )

c1, c2 = st.columns(2, gap="large")
with c1:
    st.markdown(
        """
        <div class="card">
            <h3>📚 Datos del proyecto</h3>
            <p>Documentación y exploración rápida de todas las fuentes y equivalencias.</p>
            <ul>
                <li>Estructura de columnas y significado</li>
                <li>Rangos temporales disponibles</li>
                <li>Equivalencias entre datasets (AEMET ↔ Open-Meteo, FIRMS hist ↔ operativo)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir datos del proyecto →", use_container_width=True):
        go("pages/01_Datos.py")  # <-- ajusta al nombre real


with c2:
    st.markdown(
        """
        <div class="card">
            <h3>📊 Histórico multifuente</h3>
            <p>Análisis principal combinando FIRMS + Open-Meteo + EFFIS.</p>
            <ul>
                <li>Vista evento: detección satelital enriquecida</li>
                <li>Vista provincia–día: tendencias, estacionalidad y clima vs fuego</li>
                <li>Mapas, rankings y severidad (área quemada)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir histórico →", use_container_width=True):
        go("pages/02_Historico.py")  # <-- ajusta al nombre real

st.markdown("", unsafe_allow_html=True)

c3, c4 = st.columns(2, gap="large")
with c3:
    st.markdown(
        """
        <div class="card">
            <h3>🌡️ Puntos calientes FIRMS (reciente)</h3>
            <p>Monitorización casi en tiempo real de detecciones FIRMS operativas.</p>
            <ul>
                <li>Heatmap + puntos</li>
                <li>Filtros 24h / 48h / 7 días + rango personalizado</li>
                <li>Descarga del CSV filtrado</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir puntos calientes →", use_container_width=True):
        go("pages/03_Puntos_calientes.py")  # <-- ajusta al nombre real

with c4:
    st.markdown(
        """
        <div class="card">
            <h3>🔥 Predicción de riesgo (AEMET + ML)</h3>
            <p>Estimación diaria por provincia de probabilidad de riesgo alto.</p>
            <ul>
                <li>Ranking provincial y KPIs</li>
                <li>Mapa coroplético por día</li>
                <li>Semáforo de interpretación (bajo / moderado / alto)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir predicción →", use_container_width=True):
        go("pages/04_Prediccion.py")  # <-- ajusta al nombre real



