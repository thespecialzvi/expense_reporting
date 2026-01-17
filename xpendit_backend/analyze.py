"""Parte 3 - Analizador de Lotes

- Lee gastos_historicos.csv
- Convierte montos a USD usando Open Exchange Rates (Parte 2)
- Aplica el motor de reglas (Parte 1)
- Detecta anomalías (2): duplicados exactos y montos negativos
- Bonus: evita N+1 agrupando llamadas por fecha (1 request por fecha)
- Escribe ANALISIS.md con hallazgos

Uso:
  python analyze.py
  python analyze.py --csv gastos_historicos.csv

Requisitos:
  - Definir OPEN_EXCHANGE_APP_ID (o OXR_APP_ID / APP_ID) en el entorno (.env)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    # opcional: si lo tienes, carga .env
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

from engine.models import Empleado, Gasto
from engine.validator import validar_gasto


OXR_BASE_URL = "https://openexchangerates.org/api"
DEFAULT_ANALYSIS_MD = "../output/ANALISIS.md"
DEFAULT_CSV_NAME = "../staticfiles/gastos_historicos.csv"


def _load_env() -> None:
    """Carga .env desde ubicaciones típicas (sin romper si no existe)."""
    if load_dotenv is None:
        return

    here = Path(__file__).resolve()
    candidates = [
        here.parent / ".env",
        here.parent.parent / ".env",
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
            gasto_id = row.get("gasto_id", "").strip()
            empleado_id = row.get("empleado_id", "").strip()
            nombre = row.get("empleado_nombre", "").strip()
            apellido = row.get("empleado_apellido", "").strip()
            cost_center = row.get("empleado_cost_center", "").strip()
            categoria = row.get("categoria", "").strip()
            moneda = row.get("moneda", "").strip()

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
    """Duplicados exactos: mismo monto, moneda y fecha (según el PDF)."""
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
    """HTTP GET sin dependencias externas (requests)."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "xpendit-challenge/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def fetch_tipos_cambio_agrupados_fecha(
    app_id: str,
    needed_by_date: Dict[date, Set[str]],
) -> Dict[date, Dict[str, Decimal]]:
    """Bonus: 1 llamada por fecha única."""
    tasas_por_fecha: Dict[date, Dict[str, Decimal]] = {}

    for d in sorted(needed_by_date.keys()):
        symbols = sorted(needed_by_date[d])
        if not symbols:
            continue

        symbols_q = ",".join(symbols)
        url = f"{OXR_BASE_URL}/historical/{d.isoformat()}.json?app_id={app_id}&symbols={symbols_q}"

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

    return tasas_por_fecha


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


def write_analysis_md(
    path: Path,
    status_counts: Dict[str, int],
    dup_groups: Dict[Tuple[str, str, str], List[str]],
    negative_ids: List[str],
) -> None:
    def fmt_counts() -> str:
        return (
            f"- APROBADOS: {status_counts.get('APROBADO', 0)}\n"
            f"- PENDIENTES: {status_counts.get('PENDIENTE', 0)}\n"
            f"- RECHAZADOS: {status_counts.get('RECHAZADO', 0)}\n"
        )

    dup_examples = list(dup_groups.items())[:5]
    neg_examples = negative_ids[:10]

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

    lines.append("\n## 3) (Bonus) Optimización para evitar N+1 requests\n\n")
    lines.append(
        "En lugar de pedir una tasa por cada fila del CSV (N+1), agrupé los gastos por fecha y "
        "realicé **una llamada a Open Exchange Rates por cada fecha única**, solicitando solo los símbolos "
        "de moneda necesarios para esa fecha.\n"
    )

    path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    _load_env()

    parser = argparse.ArgumentParser(description="Parte 3 - Analizador de Lotes")
    parser.add_argument("--csv", dest="csv_path", default=None, help="Ruta al gastos_historicos.csv")
    parser.add_argument("--analysis-md", dest="analysis_md", default=DEFAULT_ANALYSIS_MD, help="Ruta de salida ANALISIS.md")
    args = parser.parse_args()

    csv_path: Optional[Path] = Path(args.csv_path) if args.csv_path else None

    if csv_path is None:
        candidate = Path(DEFAULT_CSV_NAME)
        if candidate.exists():
            csv_path = candidate
        else:
            alt = Path("gastos_historicos (2).csv")
            if alt.exists():
                csv_path = alt

    if csv_path is None or not csv_path.exists():
        print(f"[ERROR] No se encontró CSV. Usa --csv o coloca {DEFAULT_CSV_NAME} en el directorio.")
        return 2

    gastos = leer_gastos(csv_path)

    dup_ids, dup_groups = detectar_duplicados(gastos)
    neg_ids = detectar_negativos(gastos)

    # Bonus: agrupar por fecha las monedas necesarias
    needed_by_date: Dict[date, Set[str]] = defaultdict(set)
    for exp in gastos:
        if exp.moneda and exp.moneda != "USD":
            needed_by_date[exp.fecha].add(exp.moneda)

    app_id = _get_oxr_app_id()
    rates_by_date: Dict[date, Dict[str, Decimal]] = {}

    if any(needed_by_date.values()):
        if not app_id:
            print("[WARN] Falta OPEN_EXCHANGE_APP_ID (app_id). Los gastos no-USD quedarán PENDIENTES.")
            rates_by_date = {d: {} for d in needed_by_date.keys()}
        else:
            rates_by_date = fetch_tipos_cambio_agrupados_fecha(app_id, needed_by_date)

    results: List[dict] = []
    status_counts = {"APROBADO": 0, "PENDIENTE": 0, "RECHAZADO": 0}

    for exp in gastos:
        # 1) convertir a USD si aplica
        monto_dec = Decimal(str(exp.monto))
        usd_amount = convertir_usd(monto_dec, exp.moneda, exp.fecha, rates_by_date)

        if exp.moneda != "USD" and usd_amount is None:
            result = {
                "gasto_id": exp.id,
                "status": "PENDIENTE",
                "alertas": [
                    {
                        "codigo": "TASA_CAMBIO_NO_DISPONIBLE",
                        "mensaje": f"No se pudo obtener tasa para {exp.moneda} en {exp.fecha.isoformat()}.",
                    }
                ],
            }
        else:
            # 2) valida con el motor (en USD)
            exp_usd = Gasto(
                id=exp.id,
                monto=float(usd_amount) if usd_amount is not None else exp.monto,
                moneda="USD",
                fecha=exp.fecha,
                categoria=exp.categoria,
                empleado=exp.empleado,
            )
            result = validar_gasto(exp_usd)

        # 3) anomalías (Parte 3)
        if exp.id in dup_ids:
            result.setdefault("alertas", []).append({
                "codigo": "DUPLICADO_EXACTO",
                "mensaje": "Posible gasto duplicado (monto, moneda y fecha coinciden con otro).",
            })
            if result.get("status") == "APROBADO":
                result["status"] = "PENDIENTE"

        if exp.id in neg_ids:
            result.setdefault("alertas", []).append({
                "codigo": "MONTO_NEGATIVO",
                "mensaje": "El monto del gasto es negativo; dato sospechoso/erróneo.",
            })
            if result.get("status") != "RECHAZADO":
                result["status"] = "RECHAZADO"

        status_counts[result["status"]] += 1
        results.append(result)

    print("\nDesglose por estado:")
    print(status_counts)
    print(f"Duplicados exactos: {len(dup_ids)} gastos en {len(dup_groups)} grupos")
    print(f"Montos negativos: {len(neg_ids)} gastos")

    # Entregable: ANALISIS.md
    analysis_md_path = Path(args.analysis_md)
    write_analysis_md(
        analysis_md_path,
        status_counts=status_counts,
        dup_groups=dup_groups,
        negative_ids=sorted(list(neg_ids)),
    )
    print(f"\n[OK] Escribí {analysis_md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

