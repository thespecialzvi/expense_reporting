from django.shortcuts import render
import json
from django.http import JsonResponse
from engine.models import Empleado, Gasto
from engine.validator import validar_gasto
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime

@csrf_exempt
def validar_gasto_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Solo método POST permitido"}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8'))
    except ValueError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    # Extraer campos de datos del gasto desde JSON
    try:
        gasto_id = data["gasto_id"]
        monto = float(data["monto"])
        moneda = data["moneda"]
        fecha_str = data["fecha"] # Formato esperado: "YYYY-MM-DD"
        categoria = data["categoria"]
        empleado_id = data["empleado_id"]
        nombre = data.get("empleado_nombre", "")
        apellido = data.get("empleado_apellido", "")
        cost_center = data.get("empleado_cost_center")
    except KeyError as e:
        return JsonResponse({"error": f"Falta campo requerido: {e}"}, status=400)
    # Construir objetos Empleado y Gasto
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except Exception:
        return JsonResponse({"error": "Formato de fecha inválido, se espera YYYY-MM-DD"}, status=400)
    emp = Empleado(id=empleado_id, nombre=nombre, apellido=apellido, cost_center=cost_center)
    gs = Gasto(id=gasto_id, monto=monto, moneda=moneda, fecha=fecha, categoria=categoria, empleado=emp)
    # Validar gasto usando la función del validador
    resultado = validar_gasto(gs)
    return JsonResponse(resultado)

