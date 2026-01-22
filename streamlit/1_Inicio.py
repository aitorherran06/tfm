import streamlit as st

# =========================================================
# CONFIGURACIÓN
# =========================================================
st.set_page_config(
    page_title="Incendios en España – Análisis y Predicción",
    page_icon="🔥",
    layout="wide",
)

# =========================================================
# CSS (tema + cards + botones alineados)
# =========================================================
st.markdown(
    """
    <style>
    .block-container { padding-top: 3.5rem; padding-bottom: 1.5rem; }

    .hero {
        border-radius: 18px;
        padding: 26px;
        background: radial-gradient(1200px 500px at 20% 10%, rgba(255,140,0,0.30), transparent 60%),
                    radial-gradient(1200px 500px at 80% 20%, rgba(255,0,0,0.18), transparent 55%),
                    linear-gradient(135deg, rgba(18,18,18,0.78), rgba(18,18,18,0.55));
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    }

    .hero h1 { margin: 0; font-size: 2.6rem; }
    .hero h2 { margin-top: 0.4rem; color: rgba(255,255,255,0.85); }

    .muted { color: rgba(255,255,255,0.7); }

    .pill {
        display:inline-block;
        padding:6px 10px;
        border-radius:999px;
        border:1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.04);
        margin-right:6px;
        margin-top:6px;
        font-size:0.85rem;
    }

    .section-title {
        margin: 1rem 0 0.6rem 0;
        font-size: 1.35rem;
        font-weight: 700;
    }

    .card {
        border-radius: 16px;
        padding: 16px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 6px 18px rgba(0,0,0,0.22);
        height: 100%;
    }

    .card-wrapper {
        display: flex;
        flex-direction: column;
        height: 100%;
    }

    .card-content {
        flex-grow: 1;
    }

    .divider {
        height:1px;
        background:rgba(255,255,255,0.08);
        margin:16px 0;
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
        <h1>🔥 Incendios en España</h1>
        <h2>Panel interactivo de análisis, visualización y predicción</h2>
        <p class="muted">
            Integración de datos satelitales, meteorología y severidad
            para explorar históricos, actividad reciente y riesgo futuro.
        </p>
        <div>
            <span class="pill">🛰️ NASA FIRMS</span>
            <span class="pill">🌦️ Open-Meteo</span>
            <span class="pill">🔥 Copernicus EFFIS</span>
            <span class="pill">📡 AEMET</span>
            <span class="pill">🧠 Random Forest</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# ROUTER SEGURO
# =========================================================
PAGES = {
    "datos": "pages/01_Datos.py",
    "historico": "pages/02_Historico_FIRMS_OpenMeteo_EFFIS.py",
    "puntos": "pages/03_Puntos_calientes.py",
    "prediccion": "pages/04_Prediccion.py",
}

def go(page_key: str):
    try:
        st.switch_page(PAGES[page_key])
    except Exception as e:
        st.error(f"No puedo navegar a `{PAGES.get(page_key)}`\n\n{e}")

# =========================================================
# SECCIONES PRINCIPALES
# =========================================================
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">🧭 Secciones principales</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2, gap="large")

with c1:
    st.markdown(
        """
        <div class="card card-wrapper">
            <div class="card-content">
                <h3>📚 Datos del proyecto</h3>
                <p>Descripción de datasets, variables y equivalencias.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir datos →", use_container_width=True):
        go("datos")

with c2:
    st.markdown(
        """
        <div class="card card-wrapper">
            <div class="card-content">
                <h3>📊 Histórico multifuente</h3>
                <p>FIRMS + Open-Meteo + EFFIS (evento y provincia-día).</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir histórico →", use_container_width=True):
        go("historico")

c3, c4 = st.columns(2, gap="large")

with c3:
    st.markdown(
        """
        <div class="card card-wrapper">
            <div class="card-content">
                <h3>🌡️ Puntos calientes FIRMS</h3>
                <p>Monitorización casi en tiempo real.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir puntos calientes →", use_container_width=True):
        go("puntos")

with c4:
    st.markdown(
        """
        <div class="card card-wrapper">
            <div class="card-content">
                <h3>🔥 Predicción de riesgo</h3>
                <p>AEMET + Random Forest por provincia.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir predicción →", use_container_width=True):
        go("prediccion")
