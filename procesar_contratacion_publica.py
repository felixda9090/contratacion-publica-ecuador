"""
Pipeline de limpieza y agregación - Contratación Pública Ecuador (OCDS/SERCOP)
--------------------------------------------------------------------------------
Objetivo: unir los archivos awards + tender de cada mes de 2025, extraer la
provincia de la entidad contratante (a partir del RUC) y generar:
  1) Un dataset detallado del mes elegido (para el análisis profundo)
  2) Un resumen mensual agregado de los 12 meses (para la serie temporal)

Estructura de carpetas esperada:
    data/raw/
        awards_2025_enero.csv
        tender_2025_enero.csv
        awards_2025_febrero.csv
        tender_2025_febrero.csv
        ... (y así para cada mes)

Ajustá MESES y RUTA_DATOS según tu caso.
"""

import pandas as pd
import glob
import os

# ---------------------------------------------------------------------------
# 1. CONFIGURACIÓN
# ---------------------------------------------------------------------------

RUTA_DATOS = "data/raw"  # carpeta donde están los 24 CSV (12 awards + 12 tender)

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

# Tabla oficial de códigos de provincia según los 2 primeros dígitos del RUC (SRI)
CODIGOS_PROVINCIA = {
    "01": "Azuay", "02": "Bolívar", "03": "Cañar", "04": "Carchi",
    "05": "Cotopaxi", "06": "Chimborazo", "07": "El Oro", "08": "Esmeraldas",
    "09": "Guayas", "10": "Imbabura", "11": "Loja", "12": "Los Ríos",
    "13": "Manabí", "14": "Morona Santiago", "15": "Napo", "16": "Pastaza",
    "17": "Pichincha", "18": "Tungurahua", "19": "Zamora Chinchipe",
    "20": "Galápagos", "21": "Sucumbíos", "22": "Orellana",
    "23": "Santo Domingo de los Tsáchilas", "24": "Santa Elena",
    "30": "Ecuatorianos en el exterior",
}

# --- NUEVO: diccionario para ordenar los meses cronológicamente ---
NUMERO_MES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}


def extraer_provincia(ruc_id):
    """
    Extrae el código de provincia a partir de un campo tipo 'EC-RUC-1360008290001-2703'.
    Devuelve el nombre de la provincia o 'Desconocido' si no matchea el formato esperado.
    """
    if not isinstance(ruc_id, str) or "RUC-" not in ruc_id:
        return "Desconocido"
    try:
        ruc_numero = ruc_id.split("RUC-")[1]          # "1360008290001-2703"
        codigo = ruc_numero[:2]                        # "13"
        return CODIGOS_PROVINCIA.get(codigo, "Desconocido")
    except (IndexError, ValueError):
        return "Desconocido"


def cargar_mes(mes):
    """
    Carga awards_2025_<mes>.csv y tender_2025_<mes>.csv, los une por 'ocid'
    y devuelve un DataFrame limpio con las columnas que necesitamos.
    """
    ruta_awards = os.path.join(RUTA_DATOS, f"awards_2025_{mes}.csv")
    ruta_tender = os.path.join(RUTA_DATOS, f"tender_2025_{mes}.csv")

    if not (os.path.exists(ruta_awards) and os.path.exists(ruta_tender)):
        print(f"⚠️  Archivos de {mes} no encontrados, se omite.")
        return None

    awards = pd.read_csv(ruta_awards, dtype=str)
    tender = pd.read_csv(ruta_tender, dtype=str)

    # --- Limpieza de awards ---
    # Nos quedamos solo con filas donde 'amount' sea un número válido
    awards["amount"] = pd.to_numeric(awards["amount"], errors="coerce")
    awards = awards.dropna(subset=["amount"])
    print(f"Filas en awards ({mes}): {len(awards)}")
    print(f"OCIDs únicos en awards ({mes}): {awards['ocid'].nunique()}")
    # La columna 'date' viene vacía; la fecha real está embebida en 'release_id'
    # (ej: "CE-20250002767675-88059-2025-01-07T04:00:37.718Z")
    awards["date"] = awards["release_id"].str.extract(r"(\d{4}-\d{2}-\d{2}T[\d:.]+Z)")
    awards["date"] = pd.to_datetime(awards["date"], errors="coerce", format="ISO8601")

    awards_cols = awards[["ocid", "date", "amount", "status"]]

    # --- Limpieza de tender ---
    tender_cols = tender[["ocid", "procuringEntity_id", "procuringEntity_name",
                           "mainProcurementCategory", "procurementMethodDetails"]].copy()
    tender_cols["provincia"] = tender_cols["procuringEntity_id"].apply(extraer_provincia)

    # --- Unión por ocid ---
    print(f"Filas en tender ({mes}): {len(tender_cols)}")
    print(f"OCIDs únicos en tender ({mes}): {tender_cols['ocid'].nunique()}")
    tender_cols = tender_cols.drop_duplicates(subset="ocid", keep="first")
    df = awards_cols.merge(tender_cols, on="ocid", how="inner")
    df["mes"] = mes
    df["mes_numero"] = NUMERO_MES[mes]
    df["anio"] = 2025

    return df


def main():
    dataframes_mensuales = []

    for mes in MESES:
        print(f"Procesando {mes}...")
        df_mes = cargar_mes(mes)
        if df_mes is not None:
            dataframes_mensuales.append(df_mes)

    if not dataframes_mensuales:
        print("No se encontró ningún archivo. Revisá RUTA_DATOS.")
        return

    # --- Dataset completo (los 12 meses unidos) ---
    df_completo = pd.concat(dataframes_mensuales, ignore_index=True)
    print(df_completo["date"].isna().sum(), "de", len(df_completo), "fechas vacías")   # ← nueva línea
    os.makedirs("data/processed", exist_ok=True)
    df_completo.to_csv("data/processed/contratacion_2025_completo.csv", index=False)
    print(f"\n✅ Dataset completo guardado: {len(df_completo):,} filas")

    # --- Resumen agregado por mes y provincia (para la serie temporal) ---
    resumen_mensual = (
        df_completo
        .groupby(["mes", "mes_numero", "provincia"], as_index=False)
        .agg(monto_total=("amount", "sum"), num_procesos=("ocid", "count"))
    )
    resumen_mensual.to_csv("data/processed/resumen_mensual_por_provincia.csv", index=False)
    print(f"✅ Resumen mensual por provincia guardado: {len(resumen_mensual)} filas")

    # --- Resumen agregado por institución (para el top 10 del dashboard) ---
    resumen_instituciones = (
        df_completo
        .groupby("procuringEntity_name", as_index=False)
        .agg(monto_total=("amount", "sum"), num_procesos=("ocid", "count"))
        .sort_values("monto_total", ascending=False)
    )
    resumen_instituciones.to_csv("data/processed/resumen_por_institucion.csv", index=False)
    print(f"✅ Resumen por institución guardado: {len(resumen_instituciones)} instituciones")

    # --- Vistazo rápido en consola ---
    print("\nTop 5 provincias por monto adjudicado (todo 2025):")
    top_provincias = (
        df_completo.groupby("provincia")["amount"].sum()
        .sort_values(ascending=False).head(5)
    )
    print(top_provincias)

    print("\nConteo de filas por provincia (para verificar el mapeo):")
    print(df_completo["provincia"].value_counts())


if __name__ == "__main__":
    main()