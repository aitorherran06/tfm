# 🔥 TFM – Análisis y predicción de riesgo de incendios en España

Este repositorio contiene el código fuente desarrollado para el Trabajo de Fin de Máster (TFM), cuyo objetivo es el análisis, integración y modelado de datos de incendios forestales y variables meteorológicas en España, así como la construcción de modelos de aprendizaje automático para la predicción del riesgo de incendio a nivel provincia–día.

El proyecto integra datos procedentes de distintas fuentes públicas y ofrece una aplicación interactiva desarrollada con **Streamlit** para la visualización y análisis de resultados.

---

## 📁 Estructura del repositorio

```
tfm/
├── notebooks/              # Notebooks de análisis, pipeline y modelado
│   ├── 00_pipeline_*.ipynb
│   ├── 01_dataset_ml.ipynb
│   ├── 02_modelado_ml.ipynb
│   └── ...
│
├── cron/                   # Scripts ejecutados mediante cron
│   ├── update_firms.py     # Actualización automática de datos FIRMS
│   └── update_aemet.py     # Actualización automática de datos meteorológicos
│
├── models/                 # Modelos de ML entrenados
│   ├── modelo_rf_riesgo_aemet.joblib
│   └── ...
│
├── app/                    # Aplicación Streamlit
│   └── app.py
│
├── data/                   # Algunos ficheros de datos utilizados en el desarrollo
│
├── requirements.txt        # Dependencias del proyecto
└── README.md
```

---

## 🔄 Pipeline de datos

El proyecto implementa un pipeline completo que incluye:

1. **Obtención de datos** desde fuentes externas públicas:
   - Incendios forestales (FIRMS, Copernicus / EFFIS)
   - Información meteorológica histórica y de predicción (AEMET, Open-Meteo)

2. **Integración espacial y temporal**:
   - Asignación de incendios a provincias
   - Agregación diaria a nivel provincia–día

3. **Limpieza y transformación de datos**:
   - Tratamiento de valores nulos
   - Normalización de variables
   - Construcción de variables derivadas (lags y ventanas temporales)

4. **Construcción del dataset de aprendizaje automático**, listo para entrenamiento y evaluación de modelos.

Todo este proceso se documenta paso a paso en los notebooks incluidos en el repositorio.

---

## ⏱️ Actualización automática de datos (cron jobs)

El repositorio incluye scripts que se ejecutan de forma periódica mediante tareas programadas (*cron jobs*), con el objetivo de mantener actualizados los datos utilizados en el proyecto.

Estos scripts permiten:
- Actualizar automáticamente los datos de incendios procedentes del sistema FIRMS.
- Actualizar la información meteorológica y de predicción futura proporcionada por AEMET.
- Almacenar los datos actualizados en la base de datos en la nube utilizada por el proyecto.

De este modo, tanto el pipeline de procesamiento como la aplicación de visualización trabajan siempre con información actualizada.

---

## 🤖 Modelos de aprendizaje automático

Se han entrenado distintos modelos de clasificación binaria para la predicción del riesgo de incendio a nivel provincia–día, utilizando principalmente **Random Forest**.

Los modelos entrenados se incluyen en el repositorio dentro de la carpeta `models/`.  
La selección del modelo de aprendizaje automático a utilizar se realiza dinámicamente desde la aplicación desplegada en **Streamlit Cloud**, mediante su configuración, sin necesidad de modificar el código fuente.

---

## 🌐 Aplicación Streamlit

El repositorio incluye el código completo de una aplicación desarrollada con **Streamlit**, que constituye la principal herramienta de visualización del proyecto.

La aplicación permite:
- Explorar los datos de incendios y meteorología.
- Visualizar resultados agregados por provincia y fecha.
- Aplicar modelos de aprendizaje automático y analizar predicciones.

La aplicación actúa como **capa de servicio y control**, gestionando la selección del modelo de ML y el acceso a los datos almacenados en la nube de forma segura.

---

## 🗄️ Datos

Los datos utilizados en el proyecto proceden de fuentes externas públicas.

Los datasets finales empleados tanto en el análisis como en el modelado se almacenan principalmente en una base de datos en la nube (**MongoDB**), desde donde son consumidos por el pipeline de procesamiento y por la aplicación de visualización, incluyéndose también una parte de los mismos en el repositorio del proyecto.

Todos los conjuntos de datos finales pueden reproducirse ejecutando el pipeline de preprocesado descrito en los notebooks, a partir de las fuentes de datos originales.

---


## 📌 Autor

**Aitor Herran**  
Trabajo de Fin de Máster – Visual Analytics and Big Data

---

## 🟢 Estado del proyecto

- Pipeline completo
- Actualización automática de datos
- Modelos entrenados
- Aplicación de visualización
- Proyecto reproducible
