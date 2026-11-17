"""
Monitoreo Transaccional — transacciones de los clientes que operan con AdamoPay.

Origen: proyecto AdamoPay_Analisis-ReporteTX (portal v3.2), integrado en
Compliance360 Hub. Las capas se conservan:

    domain/            entidades, errores y cálculos (KPIs, series); sin BD ni Streamlit
    characterization/  perfil GAFI, métricas de comportamiento y banderas de riesgo
    risk_analysis/     scoring GAFI/UIAF/operativo, alertas y recomendaciones
    etl/               lectura del Excel/CSV de AdamoPay y sincronización con la BD
    tablas.py          definición SQLAlchemy Core de las tablas tx_* (creadas por la migración 035)
    repositorio.py     única capa que ejecuta SQL
    servicio.py        reglas de negocio y caché
    ui/                páginas Streamlit del módulo
"""
