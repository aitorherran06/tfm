import os
import requests
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

# === 1. CONEXIÓN A MONGODB ===
uri = os.getenv("MONGO_URI")

if not uri:
    raise ValueError("❌ No se encontró la variable MONGO_URI en el entorno de Render o local.")

print("🔗 Conectando a MongoDB...")
client = MongoClient(uri)
db = client["incendios_espana"]
collection = db["firms_actualizado"]

print("📚 Base de datos conectada:", db.name)

# === 2. DESCARGA DE DATOS NASA FIRMS (MODIS, últimos 7 días, Europa) ===
data_url = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Europe_7d.csv"

print("\n📡 Descargando datos FIRMS (Europa, últimos 7 días)...")
try:
    df = pd.read_csv(data_url)
except Exception as e:
    print("❌ Error al descargar los datos:", e)
    raise SystemExit(1)

print(f"✅ {len(df)} registros descargados en total.")

# === 3. FILTRADO GEOGRÁFICO: ÁREA ESPAÑA (bounding box simple) ===
# Aproximación: península + algo de margen
lat_min, lat_max = 36.0, 44.5
lon_min, lon_max = -10.0, 4.5

df_espana = df[
    (df["latitude"] >= lat_min) & (df["latitude"] <= lat_max) &
    (df["longitude"] >= lon_min) & (df["longitude"] <= lon_max)
].copy()

print(f"🇪🇸 {len(df_espana)} registros dentro del bounding box de España.")

if df_espana.empty:
    print("⚠️ No se encontraron puntos dentro del área España.")
    raise SystemExit(0)

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
df_espana["region"] = "España"  # área España según bounding box

# === 5. COMBINAR FECHA Y HORA EN DATETIME (UTC) ===
def parse_datetime(row):
    try:
        return datetime.strptime(
            f"{row['fecha']} {str(row['hora']).zfill(4)}",
            "%Y-%m-%d %H%M"
        ).replace(tzinfo=timezone.utc)
    except Exception:
        return pd.NaT

df_espana["datetime"] = df_espana.apply(parse_datetime, axis=1)
df_espana = df_espana.dropna(subset=["datetime"])

print(f"🕒 Tras parsear datetime: {len(df_espana)} registros válidos.")

# === 6. BORRAR DATOS ANTIGUOS (más de 7 días) ===
limite_tiempo = datetime.now(timezone.utc) - timedelta(days=7)
borrados_fecha = collection.delete_many({"datetime": {"$lt": limite_tiempo}}).deleted_count
print(f"🧹 Se eliminaron {borrados_fecha} registros antiguos (anteriores a 7 días).")

# === 7. ÍNDICE ÚNICO PARA EVITAR DUPLICADOS ===
collection.create_index(
    [("latitud", 1), ("longitud", 1), ("datetime", 1)],
    unique=True
)

# === 8. INSERTAR NUEVOS DATOS (ignorando duplicados) ===
records = df_espana.to_dict(orient="records")
insertados = 0

for record in records:
    try:
        collection.update_one(
            {
                "latitud": record["latitud"],
                "longitud": record["longitud"],
                "datetime": record["datetime"]
            },
            {"$setOnInsert": record},
            upsert=True
        )
        insertados += 1
    except Exception:
        # choque con índice único -> ya existía
        continue

print(f"💾 {insertados} registros actualizados/insertados en 'firms_actualizado'.")

# === 9. INFORME FINAL ===
total = collection.count_documents({})
print(f"✅ La colección 'firms_actualizado' contiene ahora {total} registros (últimos 7 días, área España).")
print("🏁 Actualización completada correctamente.")
