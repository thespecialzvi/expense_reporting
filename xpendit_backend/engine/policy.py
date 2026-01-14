POLITICA = {
    "moneda_base": "USD",
    "limite_antiguedad": {
        "pendiente_dias": 30,
        "rechazado_dias": 60,
    },
    "limites_por_categoria": {
        "food": { "aprobado_hasta": 100, "pendiente_hasta": 150 },
        "transport": { "aprobado_hasta": 200, "pendiente_hasta": 200 },
        # otras categorías pueden ser agregadas acá si es necesario
    },
    "reglas_centro_costo": [
        {  "cost_center": "core_engineering", "categoria_prohibida": "food" },
        # reglas adicionales del centro de costo pueden ser agregadas acá
    ]
}
