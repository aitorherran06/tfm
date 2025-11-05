import requests
import time
from pymongo import MongoClient
from datetime import datetime, timezone

# === CONFIGURACIÓN ===
AEMET_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhaXRvcmhlcnJhbjA2QGdtYWlsLmNvbSIsImp0aSI6ImViN2QwMTc3LTA5NTItNDVlMS1iNTQxLWE0NjE1NGE0ODI2NSIsImlzcyI6IkFFTUVUIiwiaWF0IjoxNzYxOTA2OTg3LCJ1c2VySWQiOiJlYjdkMDE3Ny0wOTUyLTQ1ZTEtYjU0MS1hNDYxNTRhNDgyNjUiLCJyb2xlIjoiIn0.H6qykz_KfzUA8nxkHjoLch0N8V2P1yhYztWupxNEkZ0"
MONGO_URI = "mongodb+srv://aitorherran:pEPEgOTIlIO@tfm.jwpe2w1.mongodb.net/?appName=tfm"

client = MongoClient(MONGO_URI)
db = client["incendios_espana"]
collection = db["aemet_predicciones"]

# === LISTA COMPLETA DE MUNICIPIOS (50 provincias españolas) ===
municipios = {
    "01059": "Álava", "02003": "Albacete", "03014": "Alicante", "04013": "Almería",
    "05019": "Ávila", "06015": "Badajoz", "07040": "Islas Baleares", "08019": "Barcelona",
    "09059": "Burgos", "10037": "Cáceres", "11012": "Cádiz", "12040": "Castellón",
    "13034": "Ciudad Real", "14021": "Córdoba", "15030": "A Coruña", "16078": "Cuenca",
    "17079": "Girona", "18087": "Granada", "19075": "Guadalajara", "20069": "Guipúzcoa",
    "21041": "Huelva", "22059": "Huesca", "23050": "Jaén", "24089": "León",
    "25038": "Lleida", "26089": "La Rioja", "27028": "Lugo", "28079": "Madrid",
    "29067": "Málaga", "30030": "Murcia", "31076": "Navarra", "32054": "Ourense",
    "33044": "Asturias", "34004": "Palencia", "35016": "Las Palmas", "36038": "Pontevedra",
    "37085": "Salamanca", "38023": "Santa Cruz de Tenerife", "39075": "Cantabria",
    "40004": "Segovia", "41091": "Sevilla", "42059": "Soria", "43047": "Tarragona",
    "44069": "Teruel", "45081": "Toledo", "46085": "Valencia", "47053": "Valladolid",
    "48020": "Bizkaia", "49021": "Zamora", "50297": "Zaragoza"
}


def obtener_prediccion(codigo, nombre):
    """Descarga e inserta la predicción de una provincia."""
    print(f"🌤️ Solicitando predicción para {nombre} ({codigo})...")
    url = f"https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/diaria/{codigo}?api_key={AEMET_API_KEY}"

    for intento in range(5):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                contenido = resp.json()
                datos_url = contenido.get("datos")
                if not datos_url:
                    print(f"⚠️ Sin enlace 'datos' para {nombre}. Saltando.")
                    return

                datos_resp = requests.get(datos_url, timeout=10)
                if datos_resp.status_code == 200 and datos_resp.text.strip():
                    try:
                        datos = datos_resp.json()
                    except ValueError:
                        print(f"⚠️ Datos no válidos para {nombre}.")
                        return

                    if isinstance(datos, list) and len(datos) > 0:
                        pred = datos[0].get("prediccion", {}).get("dia", [])
                        if pred:
                            for p in pred:
                                p["provincia"] = nombre
                                p["codigo"] = codigo
                                p["fecha_descarga"] = datetime.now(timezone.utc)
                            collection.insert_many(pred)
                            print(f"✅ {len(pred)} predicciones insertadas para {nombre}.")
                            return
                    print(f"⚠️ No hay predicciones disponibles para {nombre}.")
                    return
            elif resp.status_code == 429:
                espera = (intento + 1) * 10
                print(f"⚠️ Demasiadas peticiones (429). Esperando {espera}s...")
                time.sleep(espera)
            else:
                print(f"❌ Error {resp.status_code} en {nombre}.")
                return
        except Exception as e:
            print(f"❌ Error al procesar {nombre}: {e}")
            time.sleep(3)
    print(f"❌ Error persistente en {nombre} tras varios intentos.")


# === EJECUCIÓN PRINCIPAL ===
print(f"🕘 Iniciando actualización AEMET {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
print(f"🧹 Limpiando datos antiguos...")

# Borrar predicciones más viejas de 24h
hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

# Eliminar predicciones de días que ya han pasado (fecha < hoy)
borradas = collection.delete_many({"fecha": {"$lt": hoy.isoformat()}})
print(f"🗑️ {borradas.deleted_count} registros antiguos eliminados.")

print(f"🌍 Obteniendo predicciones para {len(municipios)} provincias...")

contador = 0
for codigo, nombre in municipios.items():
    obtener_prediccion(codigo, nombre)
    contador += 1
    if contador % 10 == 0:
        print("⏸️ Pausa de 30 segundos entre lotes...")
        time.sleep(30)
    else:
        time.sleep(8)

print("✅ Actualización AEMET completada correctamente.")

