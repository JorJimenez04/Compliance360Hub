"""
Catálogo estandarizado de cumplimiento (compliance como servicio).

Objetivo: que al vincular un cliente nuevo, la documentación e información que se
le pide salga de una sola fuente, según:
  - su(s) modelo(s) de negocio,
  - su nivel de riesgo (Alto / Medio / Bajo; enfoque basado en riesgo),
  - el tipo de persona (jurídica / natural).

Es un catálogo de REFERENCIA: el oficial de cumplimiento valida la aplicabilidad y la
vigencia de cada requisito frente a la norma de su supervisor (las autoridades cambian
anexos y umbrales; p. ej. la Circular Externa 100-000020 de 2026 de Supersociedades
reemplazó el SAGRILAFT y el PTEE por el Capítulo IX de la Circular Básica Jurídica).

Todo vive en código (no en la base) para que los cambios queden versionados y revisados
en git. La base solo guarda los códigos elegidos para cada organización.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NIVELES = ("Alto", "Medio", "Bajo")
PJ, PN = "juridica", "natural"


# =========================
# Servicios que presta el oficial / la plataforma
# =========================
@dataclass(frozen=True)
class Servicio:
    codigo: str
    nombre: str
    descripcion: str


SERVICIOS: tuple[Servicio, ...] = (
    Servicio("oficial_cumplimiento", "Oficial de cumplimiento designado",
             "Oficial principal o suplente: ejecución del sistema, reportes a la UIAF e informes al máximo órgano social."),
    Servicio("diseno_sistema", "Diseño e implementación del sistema",
             "Manual SAGRILAFT/SARLAFT/PTEE (Capítulo IX), políticas, matriz de riesgo, procedimientos y señales de alerta."),
    Servicio("kyc_kyb", "Debida diligencia KYC / KYB",
             "Vinculación y actualización de clientes, contrapartes y beneficiarios finales; expediente documental."),
    Servicio("screening", "Listas restrictivas, sanciones y medios adversos",
             "OFAC, ONU, UE, listas nacionales, PEP y adverse media, al vincular y en forma periódica."),
    Servicio("monitoreo_fiat", "Monitoreo transaccional fiat",
             "Análisis de operaciones en moneda legal: perfil vs. comportamiento, alertas y casos."),
    Servicio("monitoreo_cripto", "Monitoreo transaccional cripto",
             "Análisis de wallets y transacciones con activos virtuales (KYT, origen y uso de fondos)."),
    Servicio("reporteria_uiaf", "Reportería UIAF",
             "ROS, ausencias de reporte y reportes objetivos según el régimen; calendario y evidencias."),
    Servicio("requerimientos_bancarios", "Atención de requerimientos de bancos y rieles",
             "Preparación de paquetes de información para bancos corresponsales y proveedores de pago."),
    Servicio("auditoria", "Auditoría del sistema de cumplimiento",
             "Evaluación independiente del diseño y la efectividad del sistema; informe y plan de acción."),
    Servicio("capacitacion", "Capacitación",
             "Programa anual para empleados, junta y terceros; evaluaciones y constancias."),
)


# =========================
# Regímenes / supervisores
# =========================
@dataclass(frozen=True)
class Regimen:
    codigo: str
    nombre: str
    supervisor: str
    sistema: str
    reportes_uiaf: tuple[str, ...]
    nota: str = ""


REGIMENES: tuple[Regimen, ...] = (
    Regimen("supersociedades_integral", "Supersociedades — sistema completo (Capítulo IX)", "Superintendencia de Sociedades",
            "Sistema de Autocontrol y Gestión de Riesgos LA/FT/FP y C/ST",
            ("ROS (inmediato)", "Ausencia de ROS (AROS)"),
            "Circular Externa 100-000020 de 2026. Umbral general por ingresos o activos (UVB) o por pertenecer a un sector de mayor exposición."),
    Regimen("supersociedades_rmm", "Supersociedades — régimen de medidas mínimas", "Superintendencia de Sociedades",
            "Régimen de Medidas Mínimas (RMM)", ("ROS (inmediato)", "Ausencia de ROS (AROS)"),
            "Requisitos proporcionales al perfil de riesgo del sector."),
    Regimen("psav", "Proveedor de servicios de activos virtuales (PSAV)", "Superintendencia de Sociedades / UIAF",
            "Capítulo IX + Resolución UIAF 314 de 2021",
            ("ROS (inmediato)", "Ausencia de ROS", "Transacciones con activos virtuales (mensual)",
             "Ausencia de transacciones con activos virtuales", "Reporte de clientes")),
    Regimen("superfinanciera", "Entidad vigilada por la Superintendencia Financiera", "Superintendencia Financiera de Colombia",
            "SARLAFT (Circular Básica Jurídica SFC)",
            ("ROS (inmediato)", "Ausencia de ROS", "Reportes objetivos según anexo (efectivo, productos, transferencias…)")),
    Regimen("supersolidaria", "Sector solidario (cooperativas, fondos de empleados)", "Superintendencia de la Economía Solidaria",
            "SARLAFT solidario", ("ROS (inmediato)", "Ausencia de ROS", "Reportes objetivos según anexo")),
    Regimen("supersalud", "Agentes del sistema de salud", "Superintendencia Nacional de Salud",
            "SARLAFT salud", ("ROS (inmediato)", "Ausencia de ROS")),
    Regimen("supertransporte", "Empresas de transporte", "Superintendencia de Transporte",
            "SARLAFT / Régimen de Medidas Simplificadas", ("ROS (inmediato)", "Ausencia de ROS (trimestral)",
                                                            "Reportes objetivos de carga según anexo")),
    Regimen("coljuegos", "Juegos de suerte y azar", "Coljuegos / Supersalud (según el juego)",
            "SIPLAFT", ("ROS (inmediato)", "Ausencia de ROS", "Reportes objetivos según anexo")),
    Regimen("mindeporte", "Clubes deportivos profesionales", "Ministerio del Deporte",
            "SARLAFT deportivo", ("ROS (inmediato)", "Ausencia de ROS")),
    Regimen("dian", "Cambiario y aduanero", "DIAN",
            "SAGRLAFT DIAN", ("ROS (inmediato)", "Ausencia de ROS", "Operaciones de cambio según anexo"),
            "Profesionales de compra y venta de divisas, usuarios aduaneros y de zonas francas."),
    Regimen("notariado", "Notarías", "Superintendencia de Notariado y Registro",
            "SIPLAFT notarial", ("ROS (inmediato)", "Ausencia de ROS", "Reportes objetivos de actos notariales")),
    Regimen("no_obligado", "No obligado (programa voluntario)", "—",
            "Programa de cumplimiento voluntario",
            (), "Lo exigen bancos, rieles o socios comerciales aunque la norma no obligue a la empresa."),
    Regimen("extranjero", "Entidad del exterior", "Regulador del país de origen",
            "Programa AML/CFT local", (), "Debida diligencia de corresponsalía; no reporta a la UIAF."),
)


# =========================
# Documentos
# =========================
# Carpeta del expediente en el Drive (decisión de arquitectura: Compliance360/{Org}/{Cliente}/…)
C_KYC, C_SCREENING, C_CONTRATOS, C_FONDOS, C_ACTIVIDAD, C_TRANSACCIONAL = (
    "01_KYC", "02_Screening", "03_Contratos", "04_Fuente_de_fondos", "05_Verificacion_actividad", "06_Perfil_transaccional")

# Vigencia en meses por nivel de riesgo. None = no vence (se reemplaza solo si cambia).
POR_RIESGO = {"Alto": 12, "Medio": 24, "Bajo": 36}
ANUAL = {"Alto": 12, "Medio": 12, "Bajo": 12}
SIN_VENCIMIENTO = {"Alto": None, "Medio": None, "Bajo": None}


@dataclass(frozen=True)
class Documento:
    codigo: str
    nombre: str
    carpeta: str
    aporta: str                                 # "cliente" | "oficial" | "ambos"
    vigencia: dict = field(default_factory=lambda: dict(POR_RIESGO))
    aplica_a: tuple[str, ...] = (PJ, PN)
    nivel_minimo: str = "Bajo"                  # desde qué nivel se exige
    nota: str = ""

    def vigencia_meses(self, nivel: str) -> int | None:
        return self.vigencia.get(nivel)


def _d(*args, **kw) -> Documento:
    return Documento(*args, **kw)


DOCUMENTOS: dict[str, Documento] = {d.codigo: d for d in (
    # ---- Base: identidad y existencia (KYC/KYB)
    _d("formulario_vinculacion", "Formulario de vinculación (KYC/KYB) firmado", C_KYC, "cliente"),
    _d("camara_comercio", "Certificado de existencia y representación legal", C_KYC, "cliente", aplica_a=(PJ,),
       nota="Expedición no mayor a 30 días al vincular; se renueva con cada actualización."),
    _d("rut", "RUT actualizado", C_KYC, "cliente"),
    _d("documento_identidad", "Documento de identidad (representante legal o titular)", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO)),
    _d("composicion_accionaria", "Composición accionaria y beneficiario final", C_KYC, "cliente", aplica_a=(PJ,),
       nota="Hasta la persona natural que controla; certificada por representante legal o revisor fiscal."),
    _d("documentos_beneficiarios", "Documentos de identidad de beneficiarios finales", C_KYC, "cliente",
       aplica_a=(PJ,), nivel_minimo="Medio"),
    _d("certificacion_bancaria", "Certificación bancaria", C_KYC, "cliente"),
    # ---- Screening
    _d("screening_listas", "Consulta de listas restrictivas y sanciones (empresa, socios, administradores, BF)",
       C_SCREENING, "oficial"),
    _d("screening_pep", "Verificación PEP y vínculos", C_SCREENING, "oficial"),
    _d("medios_adversos", "Búsqueda de medios adversos (adverse media)", C_SCREENING, "oficial"),
    # ---- Contractual
    _d("contrato", "Contrato firmado y anexos", C_CONTRATOS, "ambos", vigencia=dict(SIN_VENCIMIENTO),
       nota="Hasta su vencimiento o terminación."),
    _d("terminos_condiciones", "Términos y condiciones / política de privacidad del servicio", C_CONTRATOS, "cliente",
       vigencia=dict(ANUAL)),
    # ---- Fuente de fondos y perfil financiero
    _d("declaracion_origen_fondos", "Declaración de origen de fondos", C_FONDOS, "cliente"),
    _d("estados_financieros", "Estados financieros del último cierre", C_FONDOS, "cliente", vigencia=dict(ANUAL),
       aplica_a=(PJ,)),
    _d("declaracion_renta", "Declaración de renta del último año", C_FONDOS, "cliente", vigencia=dict(ANUAL),
       nivel_minimo="Medio"),
    _d("extractos_bancarios", "Extractos bancarios de los últimos 3 meses", C_FONDOS, "cliente", vigencia=dict(ANUAL),
       nivel_minimo="Alto"),
    _d("certificacion_contador", "Certificación de ingresos / revisor fiscal o contador", C_FONDOS, "cliente",
       vigencia=dict(ANUAL), nivel_minimo="Alto"),
    # ---- Verificación de la actividad
    _d("descripcion_negocio", "Descripción del modelo de negocio y flujo de fondos", C_ACTIVIDAD, "cliente",
       nota="Productos, canales, países, clientes objetivo y diagrama de cómo entra y sale el dinero."),
    _d("verificacion_actividad", "Verificación de la actividad (sitio web, visita o videollamada)", C_ACTIVIDAD, "oficial"),
    _d("evidencia_clientes", "Evidencia de operación real (facturas, contratos con clientes)", C_ACTIVIDAD, "cliente",
       vigencia=dict(ANUAL), nivel_minimo="Alto"),
    _d("visita_presencial", "Constancia de visita presencial", C_ACTIVIDAD, "oficial", nivel_minimo="Alto"),
    # ---- Perfil transaccional
    _d("perfil_transaccional", "Perfil transaccional declarado (volumen, montos, países, canales)", C_TRANSACCIONAL,
       "cliente"),
    _d("reporte_monitoreo", "Informe de monitoreo del periodo", C_TRANSACCIONAL, "oficial", vigencia=dict(ANUAL)),
    # ---- Programa de cumplimiento propio (regulados o alto riesgo)
    _d("manual_cumplimiento", "Manual / políticas AML-CFT propias (SAGRILAFT, SARLAFT o equivalente)", C_KYC, "cliente",
       vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("certificacion_oficial", "Designación y certificación del oficial de cumplimiento", C_KYC, "cliente",
       vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("cuestionario_wolfsberg", "Cuestionario Wolfsberg CBDDQ (o equivalente AML)", C_KYC, "cliente",
       vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("informe_auditoria_aml", "Último informe de auditoría del sistema AML", C_KYC, "cliente", vigencia=dict(ANUAL),
       aplica_a=(PJ,), nivel_minimo="Medio"),
    # ---- Licencias y registros por actividad
    _d("autorizacion_sfc", "Autorización / licencia de la Superintendencia Financiera", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO), aplica_a=(PJ,)),
    _d("autorizacion_supersolidaria", "Inscripción / autorización ante la Supersolidaria", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO), aplica_a=(PJ,)),
    _d("contrato_concesion_juegos", "Contrato de concesión o autorización de Coljuegos", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO), aplica_a=(PJ,)),
    _d("registro_cambiario", "Registro como profesional de compra y venta de divisas (DIAN)", C_KYC, "cliente",
       vigencia=dict(ANUAL)),
    _d("pci_dss", "Certificación PCI-DSS (o del procesador que la tenga)", C_ACTIVIDAD, "cliente", vigencia=dict(ANUAL),
       aplica_a=(PJ,)),
    _d("listado_comercios", "Listado de comercios / submerchants con su actividad", C_ACTIVIDAD, "cliente",
       vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("politica_aceptacion_comercios", "Política de aceptación y monitoreo de comercios", C_ACTIVIDAD, "cliente",
       vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("wallets_declaradas", "Wallets declaradas (direcciones y redes)", C_TRANSACCIONAL, "cliente", vigencia=dict(ANUAL)),
    _d("reporte_kyt", "Reporte de análisis de wallets (KYT / blockchain analytics)", C_TRANSACCIONAL, "oficial",
       vigencia=dict(ANUAL)),
    _d("politica_travel_rule", "Política de regla de viaje (Travel Rule) y custodia", C_KYC, "cliente",
       vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("proof_of_reserves", "Prueba de reservas o conciliación de custodia", C_FONDOS, "cliente", vigencia=dict(ANUAL),
       aplica_a=(PJ,), nivel_minimo="Medio"),
    _d("rucom", "Inscripción en el RUCOM (comercializadores de minerales)", C_KYC, "cliente", vigencia=dict(ANUAL)),
    _d("origen_mineral", "Certificado de origen del mineral y cadena de suministro", C_FONDOS, "cliente",
       vigencia=dict(ANUAL)),
    _d("titulo_minero", "Título minero y licencia ambiental", C_KYC, "cliente", vigencia=dict(SIN_VENCIMIENTO)),
    _d("habilitacion_transporte", "Habilitación de la Superintendencia de Transporte", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO), aplica_a=(PJ,)),
    _d("registro_turismo", "Registro Nacional de Turismo (RNT)", C_KYC, "cliente", vigencia=dict(ANUAL)),
    _d("registro_invima", "Registro sanitario / habilitación INVIMA", C_KYC, "cliente", vigencia=dict(SIN_VENCIMIENTO)),
    _d("control_sustancias", "Certificado de control de sustancias y productos químicos", C_KYC, "cliente",
       vigencia=dict(ANUAL), nota="Para actividades con sustancias químicas controladas."),
    _d("licencia_vigilancia", "Licencia de la Superintendencia de Vigilancia y Seguridad Privada", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO), aplica_a=(PJ,)),
    _d("habilitacion_salud", "Habilitación / autorización de funcionamiento en salud", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO), aplica_a=(PJ,)),
    _d("tarjeta_profesional", "Tarjeta profesional (abogado, contador u otra profesión regulada)", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO)),
    _d("registro_aduanero", "Registro aduanero / calificación como usuario de zona franca", C_KYC, "cliente",
       vigencia=dict(ANUAL)),
    _d("declaraciones_importacion", "Declaraciones de importación / exportación de muestra", C_TRANSACCIONAL, "cliente",
       vigencia=dict(ANUAL), nivel_minimo="Medio"),
    _d("rup", "Registro Único de Proponentes (contratistas del Estado)", C_KYC, "cliente", vigencia=dict(ANUAL)),
    _d("matricula_arrendador", "Matrícula de arrendador / afiliación gremial inmobiliaria", C_KYC, "cliente",
       vigencia=dict(ANUAL)),
    _d("licencia_construccion", "Licencias de construcción y fiducia de los proyectos", C_ACTIVIDAD, "cliente",
       vigencia=dict(ANUAL), nivel_minimo="Medio"),
    _d("verificacion_edad_consentimiento", "Política de verificación de edad y consentimiento de creadores", C_ACTIVIDAD,
       "cliente", vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("certificado_esal", "Certificado de existencia ESAL y régimen tributario especial", C_KYC, "cliente",
       vigencia=dict(ANUAL), aplica_a=(PJ,)),
    _d("donantes_principales", "Relación de donantes y destino de los recursos", C_FONDOS, "cliente", vigencia=dict(ANUAL),
       aplica_a=(PJ,)),
    _d("licencia_remesas", "Autorización como operador / corresponsal de remesas o giros", C_KYC, "cliente",
       vigencia=dict(SIN_VENCIMIENTO), aplica_a=(PJ,)),
    _d("licencia_software_juego", "Certificación de la plataforma de juego y del proveedor de software", C_ACTIVIDAD,
       "cliente", vigencia=dict(ANUAL), aplica_a=(PJ,)),
)}

# Lo que se pide SIEMPRE, sea cual sea el modelo (filtrado luego por persona y nivel)
DOCUMENTOS_BASE: tuple[str, ...] = (
    "formulario_vinculacion", "camara_comercio", "rut", "documento_identidad", "composicion_accionaria",
    "documentos_beneficiarios", "certificacion_bancaria", "screening_listas", "screening_pep", "medios_adversos",
    "contrato", "declaracion_origen_fondos", "estados_financieros", "declaracion_renta", "extractos_bancarios",
    "certificacion_contador", "descripcion_negocio", "verificacion_actividad", "evidencia_clientes",
    "visita_presencial", "perfil_transaccional",
)


# =========================
# Modelos de negocio
# =========================
@dataclass(frozen=True)
class ModeloNegocio:
    codigo: str
    grupo: str
    nombre: str
    riesgo_sugerido: str                        # riesgo inherente de partida (Alto/Medio/Bajo)
    regimenes: tuple[str, ...]                  # regímenes habituales (el oficial confirma)
    documentos: tuple[str, ...]                 # adicionales a DOCUMENTOS_BASE
    monitoreo: tuple[str, ...]                  # "fiat" y/o "cripto"
    senales_alerta: tuple[str, ...]
    por_que: str                                # justificación del riesgo sugerido


def _m(codigo, grupo, nombre, riesgo, regimenes, documentos, monitoreo, senales, por_que) -> ModeloNegocio:
    return ModeloNegocio(codigo, grupo, nombre, riesgo, tuple(regimenes), tuple(documentos), tuple(monitoreo),
                         tuple(senales), por_que)


G_PAGOS = "Pagos y fintech"
G_CRIPTO = "Activos virtuales"
G_FIN = "Sector financiero regulado"
G_JUEGO = "Juego, entretenimiento y contenido"
G_COMERCIO = "Comercio y sector real"
G_RIESGO = "Sectores de mayor exposición LA/FT"
G_SERVICIOS = "Servicios profesionales y empresariales"
G_SOCIAL = "Sector social, salud y público"

_PROGRAMA = ("manual_cumplimiento", "certificacion_oficial")
_REGULADO = ("manual_cumplimiento", "certificacion_oficial", "cuestionario_wolfsberg", "informe_auditoria_aml")
_SOC = ("supersociedades_integral", "supersociedades_rmm", "no_obligado")

MODELOS: tuple[ModeloNegocio, ...] = (
    # ---------------- Pagos y fintech
    _m("pasarela_pagos", G_PAGOS, "Pasarela / agregador de pagos (PSP)", "Alto", _SOC,
       ("pci_dss", "listado_comercios", "politica_aceptacion_comercios", "terminos_condiciones", *_PROGRAMA),
       ("fiat",), ("Comercios con actividad distinta a la declarada", "Contracargos o devoluciones anómalas",
                   "Fraccionamiento de pagos", "Comercios de alto riesgo sin aprobación"),
       "Procesa fondos de terceros a gran escala; riesgo de comercios fachada (transaction laundering)."),
    _m("dispersion_pagos", G_PAGOS, "Dispersión de pagos y nómina", "Alto", _SOC,
       ("listado_comercios", "terminos_condiciones", *_PROGRAMA), ("fiat",),
       ("Beneficiarios que reciben de muchos pagadores", "Pagos a cuentas recién abiertas",
        "Fondeo y dispersión el mismo día sin justificación", "Beneficiarios en listas o jurisdicciones de riesgo"),
       "Mueve dinero a muchos beneficiarios; riesgo de pagos a terceros no identificados."),
    _m("monetizacion", G_PAGOS, "Monetización / recaudo (cash-in, adquirencia)", "Alto", _SOC,
       ("pci_dss", "listado_comercios", "politica_aceptacion_comercios", *_PROGRAMA), ("fiat",),
       ("Recaudo en efectivo superior al perfil", "Picos atípicos de recaudo", "Pagadores repetidos en múltiples comercios"),
       "Puerta de entrada de efectivo y fondos de terceros al sistema."),
    _m("billetera_digital", G_PAGOS, "Billetera digital / dinero electrónico (SEDPE)", "Alto",
       ("superfinanciera", "no_obligado"), ("autorizacion_sfc", "terminos_condiciones", *_REGULADO), ("fiat",),
       ("Muchas cuentas por dispositivo o identidad", "Carga y retiro inmediato", "Transferencias circulares entre usuarios"),
       "Alto volumen de usuarios con onboarding digital simplificado."),
    _m("remesas", G_PAGOS, "Remesas y giros internacionales", "Alto", ("superfinanciera", "dian"),
       ("licencia_remesas", *_REGULADO), ("fiat",),
       ("Un remitente con muchos beneficiarios", "Envíos justo por debajo de umbrales", "Corredores de alto riesgo"),
       "Flujos transfronterizos frecuentes y de bajo monto; tipología clásica de fraccionamiento."),
    _m("casa_cambio", G_PAGOS, "Compra y venta de divisas (profesional de cambio)", "Alto", ("dian",),
       ("registro_cambiario", *_PROGRAMA), ("fiat",),
       ("Operaciones repetidas justo bajo el umbral de registro", "Clientes ocasionales de alto monto", "Billetes en mal estado o de alta denominación"),
       "Uso intensivo de efectivo y divisas."),
    _m("credito_digital", G_PAGOS, "Crédito digital / fintech lending / BNPL", "Medio", _SOC,
       ("terminos_condiciones", *_PROGRAMA), ("fiat",),
       ("Prepagos totales anticipados", "Desembolsos a cuentas de terceros", "Solicitudes masivas con datos similares"),
       "Riesgo de prepago con fondos ilícitos y suplantación."),
    _m("crowdfunding", G_PAGOS, "Financiación colaborativa (crowdfunding)", "Medio", ("superfinanciera", "no_obligado"),
       ("autorizacion_sfc", "terminos_condiciones", *_PROGRAMA), ("fiat",),
       ("Aportantes concentrados en un proyecto vinculado", "Aportes desde jurisdicciones de riesgo"),
       "Captación de muchos aportantes hacia proyectos de terceros."),
    _m("factoring", G_PAGOS, "Factoring y descuento de facturas", "Medio", _SOC, (*_PROGRAMA,), ("fiat",),
       ("Facturas entre partes vinculadas", "Pagadores sin relación con el emisor", "Facturas sobrevaloradas"),
       "Riesgo de facturas ficticias y comercio simulado."),
    _m("banking_as_a_service", G_PAGOS, "Cuentas de pago / Banking-as-a-Service / open banking", "Alto",
       ("superfinanciera", "no_obligado"), ("terminos_condiciones", *_REGULADO), ("fiat",),
       ("Subcuentas que operan como un tercero no declarado", "Nested accounts", "Volumen fuera del perfil del programa"),
       "Ofrece infraestructura financiera a terceros (riesgo de anidamiento)."),
    # ---------------- Activos virtuales
    _m("exchange_cripto", G_CRIPTO, "Exchange / plataforma de intercambio de activos virtuales", "Alto", ("psav",),
       ("wallets_declaradas", "reporte_kyt", "politica_travel_rule", "proof_of_reserves", *_REGULADO), ("fiat", "cripto"),
       ("Depósitos desde mixers o mercados darknet", "Cambio rápido cripto-fiat sin justificación",
        "Wallets vinculadas a sanciones", "Uso de privacy coins"),
       "Conversión entre activos virtuales y moneda legal; anonimato y transfronterizo."),
    _m("otc_cripto", G_CRIPTO, "Mesa OTC de activos virtuales", "Alto", ("psav",),
       ("wallets_declaradas", "reporte_kyt", "politica_travel_rule", *_REGULADO), ("fiat", "cripto"),
       ("Grandes montos de contraparte poco conocida", "Liquidación a terceros", "Pagos en efectivo"),
       "Operaciones de alto monto fuera de libro de órdenes."),
    _m("on_off_ramp", G_CRIPTO, "Rampa de entrada / salida cripto (on/off-ramp)", "Alto", ("psav",),
       ("wallets_declaradas", "reporte_kyt", "politica_travel_rule", *_PROGRAMA), ("fiat", "cripto"),
       ("Retiros fiat a cuentas de terceros", "Wallets de destino de alto riesgo"),
       "Puente directo entre el sistema financiero y los activos virtuales."),
    _m("custodia_cripto", G_CRIPTO, "Custodia / billetera custodial de activos virtuales", "Alto", ("psav",),
       ("wallets_declaradas", "reporte_kyt", "proof_of_reserves", "politica_travel_rule", *_REGULADO), ("cripto",),
       ("Retiros a wallets no verificadas", "Concentración en pocas direcciones"), "Control de activos de terceros."),
    _m("emisor_tokens", G_CRIPTO, "Emisión de tokens / stablecoins / tokenización", "Alto", ("psav", "no_obligado"),
       ("wallets_declaradas", "reporte_kyt", "proof_of_reserves", *_PROGRAMA), ("fiat", "cripto"),
       ("Compradores iniciales concentrados", "Redención hacia jurisdicciones de riesgo"),
       "Creación de activos con circulación global."),
    _m("mineria_cripto", G_CRIPTO, "Minería de activos virtuales", "Medio", _SOC,
       ("wallets_declaradas", "reporte_kyt"), ("fiat", "cripto"),
       ("Ingresos sin consumo energético coherente", "Venta inmediata a terceros no identificados"),
       "Origen de activos difícil de verificar sin soporte de consumo."),
    _m("aportes_cripto", G_CRIPTO, "Empresa que recibe pagos o aportes en activos virtuales", "Medio", _SOC,
       ("wallets_declaradas", "reporte_kyt"), ("fiat", "cripto"),
       ("Pagos desde wallets de alto riesgo", "Aportes de capital en cripto sin origen claro"),
       "Exposición a activos virtuales sin ser proveedor."),
    # ---------------- Sector financiero regulado
    _m("establecimiento_credito", G_FIN, "Banco / compañía de financiamiento", "Medio", ("superfinanciera",),
       ("autorizacion_sfc", *_REGULADO), ("fiat",),
       ("Corresponsales anidados", "Cuentas de paso"), "Regulado y supervisado; riesgo de corresponsalía."),
    _m("fiduciaria_valores", G_FIN, "Fiduciaria / comisionista / gestor de inversiones", "Medio", ("superfinanciera",),
       ("autorizacion_sfc", *_REGULADO), ("fiat",),
       ("Fideicomisos de administración de pagos opacos", "Cambio frecuente de beneficiarios"),
       "Vehículos que pueden ocultar al beneficiario real."),
    _m("aseguradora", G_FIN, "Aseguradora / intermediario de seguros", "Medio", ("superfinanciera",),
       ("autorizacion_sfc", *_REGULADO), ("fiat",),
       ("Cancelaciones anticipadas con reembolso a terceros", "Primas pagadas en efectivo"),
       "Productos con valor de rescate."),
    _m("cooperativa", G_FIN, "Cooperativa de ahorro y crédito / fondo de empleados", "Medio", ("supersolidaria",),
       ("autorizacion_supersolidaria", *_REGULADO), ("fiat",),
       ("Asociados sin vínculo real", "Aportes extraordinarios en efectivo"), "Captación del público en el sector solidario."),
    # ---------------- Juego, entretenimiento y contenido
    _m("juegos_azar", G_JUEGO, "Juegos de suerte y azar (casinos, apuestas, en línea)", "Alto", ("coljuegos",),
       ("contrato_concesion_juegos", "licencia_software_juego", "terminos_condiciones", *_REGULADO), ("fiat", "cripto"),
       ("Depósitos y retiros sin juego real", "Premios cobrados por terceros", "Múltiples cuentas por jugador"),
       "Sector clásico de lavado: efectivo, premios y alta rotación."),
    _m("contenido_adultos", G_JUEGO, "Plataformas de contenido para adultos", "Alto", _SOC,
       ("verificacion_edad_consentimiento", "terminos_condiciones", "listado_comercios", *_PROGRAMA), ("fiat", "cripto"),
       ("Creadores no verificados", "Pagos de fans concentrados", "Contenido o pagos desde jurisdicciones de riesgo"),
       "Riesgo reputacional y de explotación; los bancos exigen controles reforzados."),
    _m("clubes_deportivos", G_JUEGO, "Clubes deportivos profesionales", "Alto", ("mindeporte",),
       (*_PROGRAMA,), ("fiat",),
       ("Transferencias de jugadores sobrevaloradas", "Patrocinios de origen poco claro", "Pagos a intermediarios"),
       "Transferencias de alto valor y difícil valoración."),
    _m("eventos_espectaculos", G_JUEGO, "Eventos, espectáculos y boletería", "Medio", _SOC,
       ("terminos_condiciones",), ("fiat",),
       ("Ventas en efectivo superiores al aforo", "Eventos cancelados con fondos no devueltos"),
       "Ingresos en efectivo difíciles de verificar."),
    # ---------------- Comercio y sector real
    _m("ecommerce", G_COMERCIO, "Comercio electrónico", "Medio", _SOC,
       ("terminos_condiciones",), ("fiat",),
       ("Ventas a precios fuera de mercado", "Devoluciones a medios de pago distintos"), "Canal no presencial."),
    _m("marketplace", G_COMERCIO, "Marketplace (vendedores de terceros)", "Medio", _SOC,
       ("listado_comercios", "politica_aceptacion_comercios", "terminos_condiciones"), ("fiat",),
       ("Vendedores con ventas ficticias", "Compras entre partes vinculadas"),
       "Intermedia pagos entre terceros."),
    _m("comercio_general", G_COMERCIO, "Comercio al por mayor y al por menor", "Bajo", _SOC, (), ("fiat",),
       ("Ventas en efectivo inusuales", "Proveedores sin capacidad operativa"), "Actividad tradicional con soportes contables."),
    _m("comercio_exterior", G_COMERCIO, "Importación / exportación (comercio exterior)", "Medio", ("dian", *_SOC),
       ("registro_aduanero", "declaraciones_importacion"), ("fiat",),
       ("Sobre o subfacturación", "Pagos a terceros distintos del proveedor", "Mercancía sin coherencia con el giro"),
       "Lavado basado en comercio (TBML)."),
    _m("zona_franca", G_COMERCIO, "Usuario de zona franca", "Medio", ("dian",), ("registro_aduanero",
       "declaraciones_importacion"), ("fiat",), ("Movimientos de mercancía sin soporte",), "Régimen aduanero especial."),
    _m("vehiculos", G_COMERCIO, "Compraventa de vehículos", "Medio", _SOC, (), ("fiat",),
       ("Pagos en efectivo de alto valor", "Vehículos registrados a nombre de terceros"), "Bienes de alto valor fácilmente transferibles."),
    _m("transporte_carga", G_COMERCIO, "Transporte de carga y logística", "Medio", ("supertransporte",),
       ("habilitacion_transporte",), ("fiat",), ("Fletes pagados por terceros", "Rutas inconsistentes con la carga"),
       "Riesgo de contrabando y transporte de mercancía ilícita."),
    _m("transporte_pasajeros", G_COMERCIO, "Transporte de pasajeros", "Bajo", ("supertransporte",),
       ("habilitacion_transporte",), ("fiat",), ("Ingresos en efectivo fuera de la capacidad",), "Ingresos en efectivo."),
    _m("turismo", G_COMERCIO, "Agencias de viajes y turismo / hotelería", "Medio", _SOC, ("registro_turismo",), ("fiat",),
       ("Pagos de paquetes por terceros", "Cancelaciones con reembolso a otra cuenta"), "Pagos transfronterizos y anticipados."),
    _m("agroindustria", G_COMERCIO, "Agroindustria y producción agropecuaria", "Medio", _SOC, (), ("fiat",),
       ("Producción inconsistente con el área", "Compradores sin trazabilidad"), "Zonas con presencia de economías ilícitas."),
    _m("farmaceutico_quimico", G_COMERCIO, "Farmacéutico y químico", "Medio", _SOC,
       ("registro_invima", "control_sustancias"), ("fiat",),
       ("Compras de precursores sin justificación", "Clientes sin licencia"), "Desvío de sustancias controladas."),
    _m("energia_hidrocarburos", G_COMERCIO, "Energía, minería e hidrocarburos", "Alto", _SOC,
       ("titulo_minero",), ("fiat",),
       ("Pagos a funcionarios o intermediarios", "Contratistas sin capacidad"), "Riesgo de corrupción y soborno transnacional."),
    # ---------------- Sectores de mayor exposición LA/FT (Supersociedades)
    _m("metales_preciosos", G_RIESGO, "Comercialización de metales y piedras preciosas (oro)", "Alto",
       ("supersociedades_integral",), ("rucom", "origen_mineral", "titulo_minero", *_PROGRAMA), ("fiat",),
       ("Mineral sin trazabilidad", "Exportaciones sin coherencia con la producción", "Pagos en efectivo a mineros"),
       "Tipología de minería ilegal y exportaciones ficticias."),
    _m("inmobiliario", G_RIESGO, "Agentes inmobiliarios", "Alto", ("supersociedades_integral",),
       ("matricula_arrendador", *_PROGRAMA), ("fiat",),
       ("Compras en efectivo", "Precio muy distinto al avalúo", "Compradores sin capacidad económica"),
       "Inversión de capitales ilícitos en bienes raíces."),
    _m("construccion", G_RIESGO, "Construcción de edificios y obras civiles", "Alto", ("supersociedades_integral",),
       ("licencia_construccion", *_PROGRAMA), ("fiat",),
       ("Separaciones y cuotas en efectivo", "Cesión de derechos fiduciarios a terceros"),
       "Ventas sobre planos y alta rotación de compradores."),
    _m("servicios_juridicos", G_RIESGO, "Servicios jurídicos", "Medio", ("supersociedades_integral",),
       ("tarjeta_profesional", *_PROGRAMA), ("fiat",),
       ("Constitución de sociedades para terceros", "Manejo de fondos de clientes"), "Facilitadores (gatekeepers)."),
    _m("servicios_contables", G_RIESGO, "Servicios contables y revisoría fiscal", "Medio", ("supersociedades_integral",),
       ("tarjeta_profesional", *_PROGRAMA), ("fiat",),
       ("Clientes con contabilidad inconsistente", "Manejo de cuentas de clientes"), "Facilitadores (gatekeepers)."),
    # ---------------- Servicios profesionales y empresariales
    _m("bpo_outsourcing", G_SERVICIOS, "BPO, outsourcing y call centers", "Bajo", _SOC, (), ("fiat",),
       ("Clientes que pagan desde terceros", "Servicios sin entregables"), "Servicios con soportes verificables."),
    _m("tecnologia_saas", G_SERVICIOS, "Tecnología, software y SaaS", "Bajo", _SOC, ("terminos_condiciones",), ("fiat",),
       ("Licencias sobrevaloradas a partes vinculadas",), "Ingresos recurrentes con soporte contractual."),
    _m("marketing_afiliados", G_SERVICIOS, "Publicidad, marketing digital y afiliados", "Medio", _SOC,
       ("terminos_condiciones", "listado_comercios"), ("fiat", "cripto"),
       ("Pagos de comisiones a terceros no identificados", "Promoción de juegos o cripto no autorizados"),
       "Pagos de comisiones a muchos terceros, a menudo transfronterizos."),
    _m("consultoria", G_SERVICIOS, "Consultoría y servicios profesionales", "Bajo", _SOC, (), ("fiat",),
       ("Honorarios sin entregables", "Pagos a paraísos fiscales"), "Riesgo de servicios ficticios para justificar pagos."),
    _m("seguridad_privada", G_SERVICIOS, "Vigilancia y seguridad privada", "Medio", _SOC, ("licencia_vigilancia",), ("fiat",),
       ("Contratos con partes no identificadas",), "Sector regulado con riesgo de uso indebido."),
    _m("telecomunicaciones", G_SERVICIOS, "Telecomunicaciones y recargas", "Medio", _SOC, ("terminos_condiciones",), ("fiat",),
       ("Recargas masivas en efectivo", "Revendedores sin trazabilidad"), "Recargas prepago como medio de valor."),
    _m("educacion", G_SERVICIOS, "Educación y formación", "Bajo", _SOC, (), ("fiat",),
       ("Matrículas pagadas por terceros en efectivo",), "Actividad regulada con soportes."),
    # ---------------- Sector social, salud y público
    _m("esal", G_SOCIAL, "Fundaciones, ONG y entidades sin ánimo de lucro", "Alto", _SOC,
       ("certificado_esal", "donantes_principales", *_PROGRAMA), ("fiat", "cripto"),
       ("Donantes anónimos o del exterior", "Destino de recursos hacia zonas de conflicto"),
       "Riesgo de financiación del terrorismo (Recomendación 8 GAFI)."),
    _m("salud", G_SOCIAL, "Prestadores y aseguradores en salud (EPS, IPS)", "Medio", ("supersalud",),
       ("habilitacion_salud", *_PROGRAMA), ("fiat",),
       ("Recobros inusuales", "Proveedores vinculados a directivos"), "Riesgo de corrupción con recursos públicos."),
    _m("contratista_estatal", G_SOCIAL, "Contratistas del Estado", "Alto", _SOC, ("rup", *_PROGRAMA), ("fiat",),
       ("Pagos a funcionarios o intermediarios", "Subcontratistas sin capacidad", "Anticipos desviados"),
       "Riesgo de corrupción y soborno (C/ST)."),
    _m("otro", G_SERVICIOS, "Otro modelo de negocio", "Medio", _SOC, (), ("fiat",), (),
       "Clasificar con el oficial de cumplimiento."),
)

_MODELOS = {m.codigo: m for m in MODELOS}
_SERVICIOS = {s.codigo: s for s in SERVICIOS}
_REGIMENES = {r.codigo: r for r in REGIMENES}

_ORDEN_NIVEL = {"Bajo": 0, "Medio": 1, "Alto": 2}


def servicio(codigo: str) -> Servicio | None:
    return _SERVICIOS.get(codigo)


def regimen(codigo: str) -> Regimen | None:
    return _REGIMENES.get(codigo)


def modelo(codigo: str) -> ModeloNegocio | None:
    return _MODELOS.get(codigo)


def riesgo_sugerido(modelos: list[str] | tuple[str, ...]) -> str | None:
    """El más alto de los modelos elegidos (enfoque conservador). None si no hay modelos."""
    niveles = [_MODELOS[m].riesgo_sugerido for m in modelos if m in _MODELOS]
    return max(niveles, key=_ORDEN_NIVEL.__getitem__) if niveles else None


@dataclass(frozen=True)
class Requisito:
    documento: Documento
    vigencia_meses: int | None
    origen: tuple[str, ...]                     # "base" y/o códigos de modelo que lo exigen


def requisitos(modelos: list[str] | tuple[str, ...], nivel: str, tipo_persona: str = PJ) -> list[Requisito]:
    """
    Paquete estandarizado de vinculación: documentos base + los de cada modelo, filtrados
    por tipo de persona y nivel de riesgo (nivel_minimo), sin duplicados y con su vigencia.
    """
    if nivel not in NIVELES:
        raise ValueError(f"Nivel de riesgo no válido: {nivel!r}")
    origen: dict[str, list[str]] = {}
    for codigo in DOCUMENTOS_BASE:
        origen.setdefault(codigo, []).append("base")
    for m in modelos:
        mod = _MODELOS.get(m)
        if mod is None:
            raise ValueError(f"Modelo de negocio desconocido: {m!r}")
        for codigo in mod.documentos:
            origen.setdefault(codigo, []).append(m)
    salida = []
    for codigo, de_donde in origen.items():
        doc = DOCUMENTOS[codigo]
        if tipo_persona not in doc.aplica_a:
            continue
        # Lo que un modelo pide explícitamente se exige siempre; lo base respeta el nivel mínimo
        exigido_por_modelo = any(o != "base" for o in de_donde)
        if not exigido_por_modelo and _ORDEN_NIVEL[nivel] < _ORDEN_NIVEL[doc.nivel_minimo]:
            continue
        salida.append(Requisito(doc, doc.vigencia_meses(nivel), tuple(dict.fromkeys(de_donde))))
    orden_carpeta = {c: i for i, c in enumerate((C_KYC, C_SCREENING, C_CONTRATOS, C_FONDOS, C_ACTIVIDAD, C_TRANSACCIONAL))}
    return sorted(salida, key=lambda r: (orden_carpeta[r.documento.carpeta], r.documento.nombre))


def monitoreo_sugerido(modelos: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    tipos = {t for m in modelos if m in _MODELOS for t in _MODELOS[m].monitoreo}
    return tuple(t for t in ("fiat", "cripto") if t in tipos)


def como_dict() -> dict:
    """Todo el catálogo en un formato apto para JSON (lo usa la API)."""
    return {
        "niveles": list(NIVELES),
        "servicios": [s.__dict__ for s in SERVICIOS],
        "regimenes": [{**r.__dict__, "reportes_uiaf": list(r.reportes_uiaf)} for r in REGIMENES],
        "modelos": [{**m.__dict__, "regimenes": list(m.regimenes), "documentos": list(m.documentos),
                     "monitoreo": list(m.monitoreo), "senales_alerta": list(m.senales_alerta)} for m in MODELOS],
        "documentos": [{"codigo": d.codigo, "nombre": d.nombre, "carpeta": d.carpeta, "aporta": d.aporta,
                        "vigencia": d.vigencia, "aplica_a": list(d.aplica_a), "nivel_minimo": d.nivel_minimo,
                        "nota": d.nota} for d in DOCUMENTOS.values()],
        "documentos_base": list(DOCUMENTOS_BASE),
    }
