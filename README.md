

# Xpendit – Expense Policy Engine (Desafío Técnico)

Este repositorio contiene una implementación del desafío técnico de Xpendit para un **Motor de Políticas de Gastos**, que:

- **Valida gastos** contra reglas de política (Parte 1).
- **Integra tasas de cambio reales** mediante Open Exchange Rates (Parte 2).
- **Procesa un lote** desde `gastos_historicos.csv`, detecta anomalías y genera un reporte (Parte 3).
- Incluye una **UI mínima** en React (Vite + Yarn) para probar el endpoint manualmente (Parte 4).

> Nota: La UI es intencionalmente simple. El foco es netamente operacional.

---

## Requisitos

### Backend
- Python 3.10+
- Django (según `requirements.txt`)

### Frontend
- Node.js 20.19+ (recomendado)
- Yarn

---

## Configuración rápida

1) Clona el repositorio y entra al proyecto:

```bash
git clone git@github.com:thespecialzvi/expense_reporting.git
cd expense_reporting
```

2) Crea un archivo `.env` en la raíz del backend (si aplica) con tu App ID de OpenExchangeRates.org (obtenida al registrarse):

```env
OXR_APP_ID=TU_APP_ID_AQUI
```

> Importante: **no** subas `.env` al repositorio.

---

## Backend (Django)

### 1) Entorno virtual (recomendado)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3) Correr tests (Parte 1)

```bash
cd xpendit_backend
python manage.py test engine
```

### 4) Levantar API

```bash
python manage.py runserver
```

**Endpoint principal:**

- `POST /api/validate`

Ejemplo con `curl`:

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "gasto_id": "g_test",
    "monto": 120,
    "moneda": "USD",
    "fecha": "2025-10-20",
    "categoria": "food",
    "empleado_id": "e_001",
    "empleado_cost_center": "sales_team",
    "empleado_nombre": "Ana",
    "empleado_apellido": "Reyes"
  }'
```

Respuesta esperada:

- `status`: `APROBADO` | `PENDIENTE` | `RECHAZADO`
- `alertas`: lista de objetos `{ "codigo", "mensaje" }`

---

## Analizador de Lote (Parte 3)

Ejecuta el análisis sobre el CSV (dataset entregado), por ejemplo::

```bash
python analyze.py --csv ../staticfiles/gastos_historicos.csv
```

Esto:
- Procesa todos los gastos del CSV
- Convierte a USD usando Open Exchange Rates (si corresponde)
- Valida cada gasto con el motor de políticas
- Detecta anomalías (duplicados exactos y montos negativos)
- Genera `ANALISIS.md`

---

## Frontend (React + Vite + Yarn)

La UI permite ingresar un gasto manualmente y consultar el backend.

### 1) Instalar dependencias

```bash
cd xpendit_frontend
yarn
```

### 2) Ejecutar frontend

```bash
yarn dev
```

Por defecto corre en: `http://localhost:5173`

### 3) Proxy (sin CORS)

El frontend está configurado para proxyear `/api` a `http://localhost:8000` mediante `vite.config.js`.

Asegúrate de tener el backend levantado al mismo tiempo:

```bash
python manage.py runserver
```

---

## Estructura del proyecto

- `xpendit_backend/` - Backend Python (Django)
    - `xpendit_backend/urls.py` - registro rutas API de validación
    - `xpendit_backend/settings.py` - configuración del servidor
    - `analyze.py` – procesamiento batch (CSV + anomalías + reporte)
    - `engine/` – lógica principal:
        - `models.py` – modelos (Gasto/Empleado)
        - `policy.py` – definición de políticas
        - `validator.py` – motor de validación
        - `tests.py` – suite de tests
        - `views.py` - endpoint para validar gastos manualmente
- `staticfiles/gastos_historicos.csv` – dataset entregado
- `output/ANALISIS.md` – reporte generado
- `xpendit_frontend/` – UI mínima (React + Vite + Yarn)

---

