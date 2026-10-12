import streamlit as st
import pandas as pd
import json
import time
from io import BytesIO
from google import genai
from google.genai import types

# ==========================================
# CONFIGURACIÓN DE PÁGINA & UI/UX ENGINE
# ==========================================
st.set_page_config(
    page_title="GastosSmart | Dashboard Ejecutivo",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inyección CSS Custom para estilo "SaaS Moderno"
st.markdown("""
<style>
    /* Tipografía y fondo general */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main {
        background-color: #F8FAFC;
    }
    
    /* Headers estilizados */
    h1, h2, h3 {
        color: #0F172A !important;
        font-weight: 700 !important;
    }
    
    /* Tarjetas de Métricas Personalizadas */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 18px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        color: #64748B !important;
        font-weight: 600 !important;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        color: #4F46E5 !important;
        font-weight: 700 !important;
    }

    /* Estilo de Botones Principales */
    .stButton>button {
        background-color: #4F46E5 !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 0.6rem 1.2rem !important;
        box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2) !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton>button:hover {
        background-color: #4338CA !important;
        transform: translateY(-1px);
    }

    /* Estilo para contenedores de File Uploader */
    div[data-testid="stFileUploader"] {
        background-color: #FFFFFF;
        border: 2px dashed #CBD5E1;
        border-radius: 12px;
        padding: 10px;
    }
    
    /* Ocultar barra superior por defecto de Streamlit para aspecto limpio */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# BARRA LATERAL (SETTINGS & BRANDING)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135706.png", width=50)
    st.title("GastosSmart")
    st.caption("v1.2.0 | Control Financiero Automático")
    st.markdown("---")
    
    st.subheader("🔑 Clave de Acceso API")
    api_key = st.text_input(
        "Gemini API Key", 
        type="password", 
        help="Permite la categorización automática e insights de IA"
    )
    
    st.markdown("---")
    st.markdown("### 📌 Instructivo")
    st.markdown("""
    1. Carga tu **CSV o Excel** de gastos/proveedores.
    2. El sistema filtrará errores y limpiará montos.
    3. La IA asignará categorías automáticas.
    4. Descarga el **reporte consolidado**.
    """)

# ==========================================
# ÁREA PRINCIPAL (HEADER & DRAG & DROP)
# ==========================================
st.title("💳 Control Consolidado de Gastos & Proveedores")
st.markdown("Transforma planillas desordenadas en un **dashboard financiero accionable** en segundos.")

st.markdown("### 1. Carga de Documentos")
archivos_cargados = st.file_uploader(
    "Arrastra aquí tus archivos de proveedores o resumen bancario (.xlsx o .csv)",
    type=["xlsx", "csv"],
    accept_multiple_files=True
)

# ==========================================
# LÓGICA DE PROCESAMIENTO & IA
# ==========================================
if archivos_cargados:
    dfs = []
    for archivo in archivos_cargados:
        try:
            if archivo.name.endswith('.csv'):
                temp_df = pd.read_csv(archivo)
            else:
                temp_df = pd.read_excel(archivo)
            dfs.append(temp_df)
        except Exception as e:
            st.error(f"Error al leer {archivo.name}: {e}")

    if dfs:
        # Combinar todos los archivos cargados
        df_raw = pd.concat(dfs, ignore_index=True)
        
        st.markdown("---")
        st.markdown("### 2. Configuración de Columnas")
        col_select1, col_select2, col_select3 = st.columns(3)
        
        columnas = df_raw.columns.tolist()
        
        with col_select1:
            col_concepto = st.selectbox("Columna de Descripción/Concepto", columnas, index=0)
        with col_select2:
            col_monto = st.selectbox("Columna de Monto/Importe", columnas, index=1 if len(columnas)>1 else 0)
        with col_select3:
            col_fecha = st.selectbox("Columna de Fecha (Opcional)", ["Ninguna"] + columnas)

        if st.button("🚀 Procesar y Categorizar con IA", type="primary"):
            with st.spinner("Procesando datos y consultando a la IA..."):
                
                # --- PASO A: Limpieza Tradicional Vectorial (Pandas) ---
                df_clean = df_raw.copy()
                
                # Limpieza de montos (Saca $, comas, etc)
                df_clean[col_monto] = (
                    df_clean[col_monto]
                    .astype(str)
                    .str.replace("$", "", regex=False)
                    .str.replace(",", "", regex=False)
                    .str.strip()
                )
                df_clean[col_monto] = pd.to_numeric(df_clean[col_monto], errors="coerce").fillna(0.0)
                
                # Limpieza de descripciones
                df_clean[col_concepto] = df_clean[col_concepto].astype(str).str.strip()
                
                # Eliminación de filas nulas
                df_clean = df_clean[df_clean[col_monto] > 0]
                
                # --- PASO B: Categorización con IA (Gemini) ---
                categorias_ia = []
                
                if api_key:
                    client = genai.Client(api_key=api_key)
                    
                    def categorizar_con_ia(concepto):
                        prompt = f"""
                        Clasifica el siguiente gasto de empresa: "{concepto}".
                        Devuelve un JSON con la clave "categoria", eligiendo estrictamente entre:
                        - "Insumos y Mercadería"
                        - "Servicios y Utilidades"
                        - "Marketing y Publicidad"
                        - "Infraestructura y Alquiler"
                        - "Otros Gastos"
                        """
                        config = types.GenerateContentConfig(response_mime_type="application/json")
                        try:
                            res = client.models.generate_content(
                                model="gemini-2.0-flash",
                                contents=prompt,
                                config=config
                            )
                            return json.loads(res.text).get("categoria", "Otros Gastos")
                        except Exception:
                            return "Otros Gastos"

                    # Iteración sobre los registros
                    progress_bar = st.progress(0)
                    total_filas = len(df_clean)
                    
                    for idx, (_, row) in enumerate(df_clean.iterrows()):
                        cat = categorizar_con_ia(row[col_concepto])
                        categorias_ia.append(cat)
                        progress_bar.progress((idx + 1) / total_filas)
                        time.sleep(0.1)
                        
                    df_clean["Categoría IA"] = categorias_ia
                else:
                    st.warning("⚠️ No ingresaste una API Key. Se omitió la categorización automática.")
                    df_clean["Categoría IA"] = "Sin Categorizar"

                # Save en Session State
                st.session_state["df_procesado"] = df_clean

# ==========================================
# DASHBOARD DE RESULTADOS (MÉTRICAS & VISUALES)
# ==========================================
if "df_procesado" in st.session_state:
    df_res = st.session_state["df_procesado"]
    
    st.markdown("---")
    st.markdown("### 📊 Resumen Ejecutivo")
    
    # Fila de Métricas Principales (KPIs)
    m1, m2, m3 = st.columns(3)
    
    total_gasto = df_res[col_monto].sum()
    total_operaciones = len(df_res)
    ticket_promedio = total_gasto / total_operaciones if total_operaciones > 0 else 0
    
    m1.metric("Gasto Total Consolidado", f"${total_gasto:,.2f}")
    m2.metric("Total de Transacciones", f"{total_operaciones} regs")
    m3.metric("Gasto Promedio por Ticket", f"${ticket_promedio:,.2f}")
    
    # Layout de 2 columnas para Tablas y Gráficos
    col_left, col_right = st.columns([6, 4])
    
    with col_left:
        st.markdown("#### Detalle Consolidado")
        st.dataframe(df_res, use_container_width=True, height=300)
        
    with col_right:
        st.markdown("#### Distribución por Categoría")
        resumen_cat = df_res.groupby("Categoría IA")[col_monto].sum().reset_index()
        st.bar_chart(resumen_cat, x="Categoría IA", y=col_monto)
        
    # Exportación
    st.markdown("### 📥 Exportar Resultados")
    
    @st.cache_data
    def exportar_excel(dataframe):
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            dataframe.to_excel(writer, index=False)
        return out.getvalue()
        
    st.download_button(
        label="Descargar Reporte Ejecutivo en Excel (.xlsx)",
        data=exportar_excel(df_res),
        file_name="reporte_gastos_consolidado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )