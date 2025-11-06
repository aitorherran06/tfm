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
collection = db["firms_actualizado"]  # ✅ Nueva colección

print("📚 Base de datos conectada:", db.name)

# === 2. DESCARGA DE DATOS NASA FIRMS (MODIS, últimas 24h, Europa) ===
data_url = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Europe_24h.csv"

print("\n📡 Descargando datos FIRMS (Europa)...")
try:
    df = pd.read_csv(data_url)
except Exception as e:
    print("❌ Error al descargar los datos:", e)
    exit()

print(f"✅ {len(df)} registros descargados en total.")

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

# === 5. COMBINAR FECHA Y HORA EN UN DATETIME ===
def parse_datetime(row):
    try:
        return datetime.strptime(f"{row['fecha']} {str(row['hora']).zfill(4)}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
    except Exception:
        return pd.NaT

df_espana["datetime"] = df_espana.apply(parse_datetime, axis=1)
df_espana = df_espana.dropna(subset=["datetime"])

# === 6. FILTRAR SOLO ÚLTIMAS 24 HORAS ===
limite_tiempo = datetime.now(timezone.utc) - timedelta(hours=24)
df_24h = df_espana[df_espana["datetime"] >= limite_tiempo]

print(f"🕒 {len(df_24h)} registros dentro de las últimas 24 horas.")

if df_24h.empty:
    print("⚠️ No hay registros dentro de las últimas 24 horas.")
    exit()

# === 7. BORRAR TODO EL CONTENIDO ANTERIOR DE LA COLECCIÓN ===
borrados = collection.delete_many({}).deleted_count
print(f"🧹 Se eliminaron {borrados} registros antiguos de 'firms_actualizado'.")

# === 8. INSERTAR LOS NUEVOS REGISTROS ===
records = df_24h.to_dict(orient="records")

try:
    collection.insert_many(records)
    print(f"💾 {len(records)} registros insertados en MongoDB en 'firms_actualizado'.")
except Exception as e:
    print("❌ Error al insertar los datos en MongoDB:", e)
    exit()

# === 9. CREAR ÍNDICE EN CAMPO datetime (si no existe) ===
collection.create_index("datetime")
print("⚙️ Índice en 'datetime' creado o ya existente.")

# === 10. VERIFICAR INSERCIÓN ===
count = collection.count_documents({})
if count > 0:
    print(f"✅ La colección 'firms_actualizado' ahora contiene {count} documentos.")
    muestra = list(collection.find({}, {"_id": 0}).limit(3))
    print("\n📄 Ejemplo de registros insertados:")
    for doc in muestra:
        print(doc)
else:
    print("⚠️ No se insertaron datos en la colección.")

print("\n🏁 Proceso completado correctamente.")
