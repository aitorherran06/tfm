import requests
import pandas as pd
from pymongo import MongoClient
import os

# === 1. CONEXIÓN A MONGODB ===
# Render tomará la URI desde una variable de entorno
uri = os.getenv("MONGO_URI")

if not uri:
    raise ValueError("❌ Error: La variable de entorno MONGO_URI no está definida.")

client = MongoClient(uri)
db = client["incendios_espana"]
collection = db["firms_espana"]

# === 2. DESCARGA DE DATOS NASA FIRMS (MODIS, últimas 24h, Europa) ===
data_url = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Europe_24h.csv"

print("📡 Descargando datos FIRMS (Europa)...")
try:
    df = pd.read_csv(data_url)
    print(f"✅ {len(df)} registros descargados en total.")
except Exception as e:
    print("❌ Error al descargar los datos:", e)
    exit()

# === 3. FILTRADO GEOGRÁFICO: SOLO ESPAÑA ===
lat_min, lat_max = 36.0, 44.5
lon_min, lon_max = -10.0, 5.0

df_espana = df[
    (df["latitude"] >= lat_min) & (df["latitude"] <= lat_max) &
    (df["longitude"] >= lon_min) & (df["longitude"] <= lon_max)
]

print(f"🇪🇸 {len(df_espana)} registros dentro de España.")

if df_espana.empty:
    print("⚠️ No se encontraron puntos dentro de España.")
    exit()

# === 4. LIMPIEZA Y RENOMBRADO ===
df_espana = df_espana.rename(columns={
    "latitude": "latitud",
    "longitude": "longitud",
    "acq_date": "fecha",
    "acq_time": "hora",
    "frp": "potencia_radiativa",
    "confidence": "confianza"
})

df_espana["fuente"] = "MODIS"
df_espana["region"] = "España"

# === 5. CARGA EN MONGODB ===
records = df_espana.to_dict(orient="records")
collection.insert_many(records)
print(f"💾 {len(records)} registros insertados en MongoDB en 'firms_espana'.")
