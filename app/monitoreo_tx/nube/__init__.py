"""
Carga automática de los reportes de AdamoPay desde una carpeta en la nube.

Estructura esperada (la misma que en el procedimiento de carga):

    AdamoPay_Datos/
        <Nombre exacto de la empresa>/
            AAAA-MM-DD_historial-de-pagos.csv

fuentes.py         dónde están los archivos: OneDrive (Microsoft Graph) o una carpeta local
sincronizacion.py  revisa la fuente, carga lo nuevo y deja trazabilidad
"""
