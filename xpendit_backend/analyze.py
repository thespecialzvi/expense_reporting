"""Parte 3 - Analizador de Lotes

- Lee gastos_historicos.csv
- Convierte montos a USD usando Open Exchange Rates (Parte 2)
- Aplica el motor de reglas (Parte 1)
- Detecta anomalías (2): duplicados exactos y montos negativos
- Bonus: evita N+1 agrupando llamadas por fecha (1 request por fecha)
- Escribe ANALISIS.md con hallazgos

Uso:
  python analyze.py
  python analyze.py --csv ../staticfiles/gastos_historicos.csv
  python analyze.py --analysis-md ../output/ANALISIS.md

Requisitos:
  - Definir OPEN_EXCHANGE_APP_ID (o OXR_APP_ID / APP_ID) en el entorno (.env)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    # Opcional: si lo tienes, carga .env
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None


# Robusto a ubicaciones típicas:
# - ejecutar desde /backend (donde vive la app engine)
# - o desde la raíz del repo (donde existe /backend/engine)
HERE = Path(__file__).resolve().parent
if (HERE / "engine").exists():
    sys.path.insert(0, str(HERE))
elif (HERE / "backend" / "engine").exists():
    sys.path.insert(0, str(HERE / "backend"))

# Nombres según la versión actual del repo (ESP)
from engine.models import Empleado, Gasto
from engine.validator import validar_gasto


OXR_BASE_URL = "https://openexchangerates.org/api"
DEFAULT_ANALYSIS_MD = "../output/ANALISIS.md"
DEFAULT_CSV_NAME = "../staticfiles/gastos_historicos.csv"


def _load_env() -> None:
    """Carga .env desde ubicaciones típicas (sin romper si no existe)."""
    if load_dotenv is None:
        return

    candidates = [
        HERE / ".env",
        HERE.parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p)
            return


def _get_oxr_app_id() -> Optional[str]:
    return (
        os.getenv("OPEN_EXCHANGE_APP_ID")
        or os.getenv("OXR_APP_ID")
        or os.getenv("APP_ID")
        or os.getenv("OPENEXCHANGERATES_APP_ID")
    )


def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_decimal(s: str) -> Optional[Decimal]:
    try:
        return Decimal(str(s).strip())
    except (InvalidOperation, ValueError):
        return None


def leer_gastos(csv_path: Path) -> List[Gasto]:
    gastos: List[Gasto] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gasto_id = (row.get("gasto_id") or "").strip()
            empleado_id = (row.get("empleado_id") or "").strip()
            nombre = (row.get("empleado_nombre") or "").strip()
            apellido = (row.get("empleado_apellido") or "").strip()
            cost_center = (row.get("empleado_cost_center") or "").strip()
            categoria = (row.get("categoria") or "").strip()
            moneda = (row.get("moneda") or "").strip()

            fecha = _parse_date(row.get("fecha", ""))
            monto = _parse_decimal(row.get("monto", ""))

            if not gasto_id or not empleado_id or fecha is None or monto is None:
                print(
                    f"[WARN] Saltando fila: gasto_id={gasto_id!r} "
                    f"fecha={row.get('fecha')!r} monto={row.get('monto')!r}"
                )
                continue

            emp = Empleado(
                id=empleado_id,
                nombre=nombre,
                apellido=apellido,
                cost_center=cost_center,
            )
            gs = Gasto(
                id=gasto_id,
                monto=float(monto),
                moneda=moneda,
                fecha=fecha,
                categoria=categoria,
                empleado=emp,
            )
            gastos.append(gs)

    return gastos


def detectar_duplicados(gastos: List[Gasto]) -> Tuple[Set[str], Dict[Tuple[str, str, str], List[str]]]:
    """Duplicados exactos: mismo monto, moneda y fecha."""
    groups: Dict[Tuple[str, str, str], List[str]] = defaultdict(list)
    for gs in gastos:
        key = (f"{round(gs.monto, 2):.2f}", gs.moneda, gs.fecha.isoformat())
        groups[key].append(gs.id)

    dup_ids: Set[str] = set()
    dup_groups: Dict[Tuple[str, str, str], List[str]] = {}
    for k, ids in groups.items():
        if len(ids) > 1:
            dup_ids.update(ids)
            dup_groups[k] = ids

    return dup_ids, dup_groups


def detectar_negativos(gastos: List[Gasto]) -> Set[str]:
    return {gs.id for gs in gastos if gs.monto < 0}


def _http_get_json(url: str) -> dict:
    """HTTP GET sin requests.

    Nota: en macOS a veces falla SSL si el Python no tiene CA bundle.
    Si certifi está disponible, lo usamos para minimizar errores por certificados.
    """
    import ssl
    import urllib.request

    try:
        import certifi  # type: ignore

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()

    req = urllib.request.Request(url, headers={"User-Agent": "xpendit-challenge/1.0"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def fetch_tipos_cambio_agrupados_fecha(
    app_id: str,
    needed_by_date: Dict[date, Set[str]],
) -> Tuple[Dict[date, Dict[str, Decimal]], int]:
    """Bonus: 1 llamada por fecha única.

    Retorna (tasas_por_fecha, numero_de_requests).
    """
    tasas_por_fecha: Dict[date, Dict[str, Decimal]] = {}
    req_count = 0

    for d in sorted(needed_by_date.keys()):
        symbols = sorted(needed_by_date[d])
        if not symbols:
            continue

        symbols_q = ",".join(symbols)
        url = f"{OXR_BASE_URL}/historical/{d.isoformat()}.json?app_id={app_id}&symbols={symbols_q}"
        req_count += 1

        try:
            payload = _http_get_json(url)
            raw_rates = payload.get("rates", {})

            parsed: Dict[str, Decimal] = {}
            for sym in symbols:
                val = raw_rates.get(sym)
                if val is None:
                    continue
                try:
                    parsed[sym] = Decimal(str(val))
                except (InvalidOperation, ValueError):
                    continue

            tasas_por_fecha[d] = parsed
        except Exception as e:
            print(f"[WARN] Failed to fetch rates for {d.isoformat()}: {e}")
            tasas_por_fecha[d] = {}

    return tasas_por_fecha, req_count


def convertir_usd(
    monto: Decimal,
    moneda: str,
    fecha: date,
    tasas_por_fecha: Dict[date, Dict[str, Decimal]],
) -> Optional[Decimal]:
    """OXR devuelve tasas vs USD (1 USD = tasa[moneda] unidades).

    Para convertir moneda -> USD: usd = monto / tasa[moneda]
    """
    if moneda == "USD":
        return monto

    rates = tasas_por_fecha.get(fecha) or {}
    rate = rates.get(moneda)
    if rate is None or rate == 0:
        return None

    return monto / rate


def _estado_por_antiguedad(fecha_gasto: date, hoy: date) -> str:
    """Regla simple de antigüedad, usada solo como fallback cuando no hay tasa."""
    dias = (hoy - fecha_gasto).days
    if dias <= 30:
        return "APROBADO"
    if dias <= 60:
        return "PENDIENTE"
    return "RECHAZADO"


def write_analysis_md(
    path: Path,
    status_counts: Dict[str, int],
    dup_groups: Dict[Tuple[str, str, str], List[str]],
    negative_ids: List[str],
    monedas_count: Dict[str, int],
    n_total: int,
    n_no_usd: int,
    d_fechas_no_usd: int,
    oxr_requests: int,
) -> None:
    def fmt_counts() -> str:
        return (
            f"- APROBADOS: {status_counts.get('APROBADO', 0)}\n"
            f"- PENDIENTES: {status_counts.get('PENDIENTE', 0)}\n"
            f"- RECHAZADOS: {status_counts.get('RECHAZADO', 0)}\n"
        )

    dup_examples = list(dup_groups.items())[:5]
    neg_examples = negative_ids[:10]

    path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("# ANALISIS - Desafío Técnico Xpendit (Parte 3)\n\n")

    lines.append("## 1) Desglose de gastos por estado\n\n")
    lines.append(fmt_counts() + "\n")

    lines.append("## 2) Anomalías detectadas\n\n")

    lines.append("### 2.1 Duplicados exactos (monto, moneda, fecha idénticos)\n\n")
    if not dup_examples:
        lines.append("No se encontraron duplicados exactos.\n")
    else:
        for (monto, moneda, fecha), ids in dup_examples:
            lines.append(f"- {fecha} | {monto} {moneda} | ids: {', '.join(ids)}\n")

    lines.append("\n### 2.2 Montos negativos\n\n")
    if not neg_examples:
        lines.append("No se encontraron montos negativos.\n")
    else:
        lines.append(f"Ejemplos (ids): {', '.join(neg_examples)}\n")

    lines.append("\n## 3) (Bonus) Optimización para evitar N+1 requests (Open Exchange Rates)\n\n")

    # Versión corta, pero defendible: Problema -> Solución aplicada -> Beneficios -> Fallback
    lines.append("### Problema\n")
    lines.append(
        "Una implementación ingenua consulta Open Exchange Rates **por cada gasto no-USD** del CSV. "
        "Eso genera el anti-patrón **N+1**: si hay `N` filas no-USD, haces `N` llamadas de red, "
        "repitiendo trabajo (muchos gastos comparten fecha) y aumentando latencia y puntos de falla.\n\n"
    )

    lines.append("### Solución aplicada\n")
    lines.append(
        "Se implementó **prefetch por fecha**:\n\n"
        "1) Se agrupan gastos no-USD por **fecha** y se reúnen las **monedas** necesarias por día: `needed_by_date[fecha] = {monedas}`.\n"
        "2) Se hace **1 request por fecha única** a OXR solicitando solo los `symbols` requeridos.\n"
        "3) Se cachean tasas en memoria (`tasas_por_fecha`) y cada conversión posterior es O(1) (lookup en diccionario).\n\n"
    )

    lines.append("### Beneficios\n")
    lines.append(
        f"- Menos round trips: `N → D` llamadas (N=no-USD={n_no_usd}, D=fechas únicas no-USD={d_fechas_no_usd}).\n"
        "- Menos variabilidad: menos chances de fallar por red/TLS/quotas.\n"
        "- Mejor performance y resultados más consistentes.\n\n"
    )

    lines.append("### Fallback\n")
    lines.append(
        "Si falla la obtención de tasas para una fecha (sin tasa o error de red), se agrega alerta `TASA_CAMBIO_NO_DISPONIBLE`. "
        "El gasto queda **PENDIENTE** solo si no existe una razón más severa (por ejemplo, reglas determinísticas que lo lleven a **RECHAZADO**, como antigüedad).\n\n"
    )

    lines.append("## 4) Datos del lote\n\n")
    lines.append(f"- Total gastos: {n_total}\n")
    lines.append(f"- Distribución monedas: {dict(monedas_count)}\n")
    lines.append(f"- Requests OXR ejecutadas (en esta corrida): {oxr_requests}\n")

    path.write_text("".join(lines), encoding="utf-8")


def _resolver_csv_path(arg_csv: Optional[str]) -> Path:
    if arg_csv:
        return Path(arg_csv)

    # default del repo
    p = Path(DEFAULT_CSV_NAME)
    if p.exists():
        return p

    # alternativas comunes
    candidates = [
        Path("gastos_historicos.csv"),
        Path("gastos_historicos (2).csv"),
        HERE / "gastos_historicos.csv",
        HERE / "gastos_historicos (2).csv",
    ]
    for c in candidates:
        if c.exists():
            return c

    # último recurso
    return p


def main() -> int:
    _load_env()

    parser = argparse.ArgumentParser(description="Parte 3 - Analizador de Lotes")
    parser.add_argument("--csv", dest="csv_path", default=None, help="Ruta al gastos_historicos.csv")
    parser.add_argument(
        "--analysis-md",
        dest="analysis_md",
        default=DEFAULT_ANALYSIS_MD,
        help="Ruta de salida ANALISIS.md",
    )
    args = parser.parse_args()

    csv_path = _resolver_csv_path(args.csv_path)
    if not csv_path.exists():
        print(f"[ERROR] No se encontró CSV. Probé: {csv_path}")
        return 2

    gastos = leer_gastos(csv_path)
    hoy = datetime.now().date()

    dup_ids, dup_groups = detectar_duplicados(gastos)
    neg_ids = detectar_negativos(gastos)

    # Bonus: agrupar por fecha las monedas necesarias (no-USD)
    needed_by_date: Dict[date, Set[str]] = defaultdict(set)
    for gs in gastos:
        if gs.moneda and gs.moneda != "USD":
            needed_by_date[gs.fecha].add(gs.moneda)

    app_id = _get_oxr_app_id()
    tasas_por_fecha: Dict[date, Dict[str, Decimal]] = {}
    oxr_requests = 0

    if any(needed_by_date.values()) and app_id:
        tasas_por_fecha, oxr_requests = fetch_tipos_cambio_agrupados_fecha(app_id, needed_by_date)
    elif any(needed_by_date.values()) and not app_id:
        print("[WARN] Falta OPEN_EXCHANGE_APP_ID. Gastos no-USD pueden quedar sin conversión.")

    resultados: List[dict] = []
    status_counts = {"APROBADO": 0, "PENDIENTE": 0, "RECHAZADO": 0}

    for gs in gastos:
        # 1) convertir a USD si aplica
        monto_dec = Decimal(str(gs.monto))
        usd_amount = convertir_usd(monto_dec, gs.moneda, gs.fecha, tasas_por_fecha)

        if gs.moneda != "USD" and usd_amount is None:
            # Fallback: no hay tasa. No dejamos que esto oculte reglas determinísticas.
            base_status = _estado_por_antiguedad(gs.fecha, hoy)
            status = base_status if base_status != "APROBADO" else "PENDIENTE"
            result = {
                "gasto_id": gs.id,
                "status": status,
                "alertas": [
                    {
                        "codigo": "TASA_CAMBIO_NO_DISPONIBLE",
                        "mensaje": f"No se pudo obtener tasa para {gs.moneda} en {gs.fecha.isoformat()}.",
                    }
                ],
            }
        else:
            gs_usd = Gasto(
                id=gs.id,
                monto=float(usd_amount) if usd_amount is not None else gs.monto,
                moneda="USD",
                fecha=gs.fecha,
                categoria=gs.categoria,
                empleado=gs.empleado,
            )
            result = validar_gasto(gs_usd)

        # 2) anomalías
        result.setdefault("alertas", [])

        if gs.id in dup_ids:
            result["alertas"].append(
                {
                    "codigo": "DUPLICADO_EXACTO",
                    "mensaje": "Posible gasto duplicado (monto, moneda y fecha coinciden con otro).",
                }
            )
            if result.get("status") == "APROBADO":
                result["status"] = "PENDIENTE"

        if gs.id in neg_ids:
            result["alertas"].append(
                {
                    "codigo": "MONTO_NEGATIVO",
                    "mensaje": "El monto del gasto es negativo; dato sospechoso/erróneo.",
                }
            )
            if result.get("status") != "RECHAZADO":
                result["status"] = "RECHAZADO"

        status_counts[result["status"]] += 1
        resultados.append(result)

    print(status_counts)

    monedas_count = Counter(gs.moneda for gs in gastos)
    n_total = len(gastos)
    n_no_usd = sum(1 for gs in gastos if gs.moneda != "USD")
    d_fechas_no_usd = len([d for d, s in needed_by_date.items() if s])

    analysis_md_path = Path(args.analysis_md)
    write_analysis_md(
        analysis_md_path,
        status_counts=status_counts,
        dup_groups=dup_groups,
        negative_ids=sorted(list(neg_ids)),
        monedas_count=dict(monedas_count),
        n_total=n_total,
        n_no_usd=n_no_usd,
        d_fechas_no_usd=d_fechas_no_usd,
        oxr_requests=oxr_requests,
    )

    print(f"[OK] Escribí {analysis_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
