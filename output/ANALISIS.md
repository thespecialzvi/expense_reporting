# ANALISIS - Desafío Técnico Xpendit (Parte 3)

## 1) Desglose de gastos por estado

- APROBADOS: 0
- PENDIENTES: 0
- RECHAZADOS: 50

## 2) Anomalías detectadas

### 2.1 Duplicados exactos (monto, moneda, fecha idénticos)

- 2025-10-20 | 50.00 USD | ids: g_001, g_011
- 2025-10-19 | 120.00 USD | ids: g_002, g_012
- 2025-09-15 | 120.00 USD | ids: g_025, g_029
- 2025-08-15 | 80.00 USD | ids: g_027, g_030
- 2025-10-20 | 70.00 USD | ids: g_034, g_035, g_036

### 2.2 Montos negativos

Ejemplos (ids): g_031, g_032, g_033

## 3) (Bonus) Optimización para evitar N+1 requests (Open Exchange Rates)

### Problema
Una implementación ingenua consulta Open Exchange Rates **por cada gasto no-USD** del CSV. Eso genera el anti-patrón **N+1**: si hay `N` filas no-USD, haces `N` llamadas de red, repitiendo trabajo (muchos gastos comparten fecha) y aumentando latencia y puntos de falla.

### Solución aplicada
Se implementó **prefetch por fecha**:

1) Se agrupan gastos no-USD por **fecha** y se reúnen las **monedas** necesarias por día: `needed_by_date[fecha] = {monedas}`.
2) Se hace **1 request por fecha única** a OXR solicitando solo los `symbols` requeridos.
3) Se cachean tasas en memoria (`tasas_por_fecha`) y cada conversión posterior es O(1) (lookup en diccionario).

### Beneficios
- Menos round trips: `N → D` llamadas (N=no-USD=10, D=fechas únicas no-USD=10).
- Menos variabilidad: menos chances de fallar por red/TLS/quotas.
- Mejor performance y resultados más consistentes.

### Fallback
Si falla la obtención de tasas para una fecha (sin tasa o error de red), se agrega alerta `TASA_CAMBIO_NO_DISPONIBLE`. El gasto queda **PENDIENTE** solo si no existe una razón más severa (por ejemplo, reglas determinísticas que lo lleven a **RECHAZADO**, como antigüedad).

## 4) Datos del lote

- Total gastos: 50
- Distribución monedas: {'USD': 40, 'CLP': 5, 'MXN': 3, 'EUR': 2}
- Requests OXR ejecutadas (en esta corrida): 10
