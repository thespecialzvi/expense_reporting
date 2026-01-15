# ANALISIS - Desafío Técnico Xpendit (Parte 3)

## 1) Desglose de gastos por estado

- APROBADOS: 0
- PENDIENTES: 9
- RECHAZADOS: 41

## 2) Anomalías detectadas

### 2.1 Duplicados exactos (monto, moneda, fecha idénticos)

- 2025-10-20 | 50.00 USD | ids: g_001, g_011
- 2025-10-19 | 120.00 USD | ids: g_002, g_012
- 2025-09-15 | 120.00 USD | ids: g_025, g_029
- 2025-08-15 | 80.00 USD | ids: g_027, g_030
- 2025-10-20 | 70.00 USD | ids: g_034, g_035, g_036

### 2.2 Montos negativos

Ejemplos (ids): g_031, g_032, g_033

## 3) (Bonus) Optimización para evitar N+1 requests

En lugar de pedir una tasa por cada fila del CSV (N+1), agrupé los gastos por fecha y realicé **una llamada a Open Exchange Rates por cada fecha única**, solicitando solo los símbolos de moneda necesarios para esa fecha.
