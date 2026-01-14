from datetime import datetime
from engine.models import Gasto
from engine import policy

def validar_gasto(gasto: Gasto) -> dict:
    """
    Valida un gasto individual según las reglas de la política (engine.policy).
    Devuelve un dict. de resultados con estado y alertas.
    """
    alertas = [] # recopila cualquier alerta de violación de reglas
    estados = [] # recopila estados intermedios sugeridos por las reglas

    ##########################################
    ##### 1. Regla – Antigüedad del gasto ####
    ##########################################
    today = datetime.now().date()
    diferencia_dias = (today - gasto.fecha).days
    # Comprobar plazos dispuestos en la política
    max_dias_pendientes = policy.POLITICA["limite_antiguedad"]["pendiente_dias"]
    max_dias_rechazados = policy.POLITICA["limite_antiguedad"]["rechazado_dias"]
    if diferencia_dias > max_dias_rechazados:
        estados.append("RECHAZADO")
        alertas.append({
            "codigo": "LIMITE_ANTIGUEDAD",
            "mensaje": f"Gasto excede los {max_dias_rechazados} días. No es reembolsable."
        })
    elif diferencia_dias > max_dias_pendientes:
        estados.append("PENDIENTE")
        alertas.append({
            "codigo": "LIMITE_ANTIGUEDAD",
            "mensaje": f"Gasto excede los {max_dias_pendientes} días. Requiere revisión."
        })
    else:
        estados.append("APROBADO")
        # No se emiten alertas si la antiguedad es de hasta 30 días (gasto compliant)

    #####################################################
    ##### 2. Regla - Límites de gasto por categoría #####
    #####################################################
    moneda_base = policy.POLITICA["moneda_base"] # "USD"
    mnt_en_usd = gasto.monto
    if gasto.moneda != moneda_base:
        # Dado que en esta primera parte no debemos llamar a una API externa,
        # simulamos las tasas de conversión.
        # Por ejemplo: 1 USD = 800 CLP = 20 MXN = 0.85 EUR
        tasas_conversion = {"CLP": 1/800, "MXN": 1/20, "EUR": 1/0.85}
        if gasto.moneda in tasas_conversion:
            mnt_en_usd = gasto.monto * tasas_conversion[gasto.moneda]
        else:
            # Si la moneda es desconocida, por seguridad marcar como pendiente de revisión
            estados.append("PENDIENTE")
            alertas.append({
                "codigo": "MONEDA_DESCONOCIDA",
                "mensaje": f"Moneda {gasto.moneda} desconocida, no se puede convertir a USD"
            })
    # Aplicación de límites por categoría a través de mnt_en_usd
    limites_cat = policy.POLITICA["limites_por_categoria"]
    if gasto.categoria in limites_cat:
        limites = limites_cat[gasto.categoria]
        aprobado_hasta = limites["aprobado_hasta"]
        pendiente_hasta = limites["pendiente_hasta"]
        if mnt_en_usd > pendiente_hasta:
            # supera el límite "PENDIENTE" -> rechazar
            estados.append("RECHAZADO")
            alertas.append({
                "codigo": "LIMITE_CATEGORIA",
                "mensaje": f"El gasto de '{gasto.categoria}' excede el límite permitido."
            })
        elif mnt_en_usd > aprobado_hasta:
            # está dentro del rango "PENDIENTE"
            estados.append("PENDIENTE")
            alertas.append({
                "codigo": "LIMITE_CATEGORIA",
                "mensaje": f"El gasto de '{gasto.categoria}' excede el límite aprobado; requiere revisión."
            })
        else:
            # está dentro del rango de aprobación
            estados.append("APROBADO")
            # no se emite ninguna alerta al estar aprobado
    else:
        # La categoría del gasto no está en la política,
        # No se aplicará ninguna regla específica
        pass

    ################################################################
    ##### 3. Regla - Categoría prohibida para centro de costos #####
    ################################################################
    for regla in policy.POLITICA.get("reglas_centro_costo", []):
        if (
            gasto.empleado.cost_center == regla["cost_center"]
            and gasto.categoria == regla["categoria_prohibida"]
        ):
            estados.append("RECHAZADO")
            alertas.append({
                "codigo": "POLITICA_CENTRO_COSTO",
                "mensaje": f"El C.C. '{regla['cost_center']}' no puede reportar a '{gasto.categoria}'."
            })

    # Determinar estado final por prioridad
    if "RECHAZADO" in estados:
        estado_final = "RECHAZADO"
    elif "PENDIENTE" in estados:
        estado_final = "PENDIENTE"
    elif "APROBADO" in estados:
        estado_final = "APROBADO"
    else:
        estado_final = "PENDIENTE"

    return {
        "gasto_id": gasto.id,
        "status": estado_final,
        "alertas": alertas,
    }
