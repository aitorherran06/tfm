import requests
import pandas as pd
from pymongo import MongoClient
import os
from datetime import datetime, timedelta

# === CONFIGURACIÓN ===
AEMET_API_KEY = os.getenv("AEMET_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# Conexión a MongoDB
client = MongoClient(MONGO_URI)
db = client["aemet_espana"]
collection = db["historico"]

# Fecha de ayer (últimos datos disponibles)
fecha_fin = datetime.utcnow().date() - timedelta(days=1)
fecha_ini = fecha_fin - timedelta(days=1)  # 1 día antes

# Estación meteorológica (Madrid-Retiro por ejemplo)
# Código oficial AEMET: 3195
estacion = "3195"

url = f"https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos/fechaini/{fecha_ini}/fechafin/{fecha_fin}/estacion/{estacion}"
headers = {"api_key": AEMET_API_KEY}

print(f"🌦️ Solicitando datos históricos AEMET de {fecha_ini} a {fecha_fin}...")

response = requests.get(url, headers=headers)
if response.status_code != 200:
    print(f"❌ Error al consultar AEMET: {response.status_code}")
    exit()

data_url = response.json()["datos"]
data = requests.get(data_url).json()

if not data:
    print("⚠️ No se recibieron datos.")
    exit()

print(f"✅ {len(data)} registros recibidos, procesando...")

# Convertir a DataFrame
df = pd.DataFrame(data)

# Limpiar y seleccionar campos relevantes
df = df.rename(columns={
    "fecha": "fecha",
    "tmax": "tmax",
    "tmin": "tmin",
    "prec": "precipitacion",
    "hr": "humedad_relativa",
    "vv": "velocidad_viento",
    "nombre": "estacion"
})

df["fecha_insercion"] = datetime.utcnow()
registros = df.to_dict(orient="records")

collection.insert_many(registros)
print(f"💾 {len(registros)} registros insertados en MongoDB en 'aemet_espana.historico'.")
