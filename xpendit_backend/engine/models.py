from django.db import models
from dataclasses import dataclass
from datetime import date

# Create your models here.
@dataclass
class Empleado:
    id: str
    nombre: str
    apellido: str
    cost_center: str


@dataclass
class Gasto:
    id: str
    monto: float        # valor del gasto
    moneda: str         # currency / moneda (e.g., "USD", "CLP", "ARS")
    fecha: date         
    categoria: str
    empleado: Empleado  # empleado que reporta el gasto


