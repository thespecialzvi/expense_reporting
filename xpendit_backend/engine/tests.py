from django.test import TestCase
from datetime import datetime, timedelta
from engine.models import Empleado, Gasto
from engine import validator


class TestValidacionGastos(TestCase):
    def setUp(self):
        # Objetos comunes / configuración de tests
        self.empleado_ventas = Empleado(id="e_sales", nombre="John", apellido="Doe", cost_center="sales_team")
        self.empleado_ingenieria = Empleado(id="e_eng", nombre="John", apellido="Smith", cost_center="core_engineering")

        # Definir fecha actual (today) de referencia para tests consistentes
        self.today = datetime.now().date()

    def test_antiguedad_aprobada(self):
        """
        Gastos de hasta 30 días de antigüedad -> APROBADOS
        """
        fecha_reciente = self.today - timedelta(days=10) # 10 días atrás
        gasto = Gasto(id="g_reciente", monto=100, moneda="USD", fecha=fecha_reciente, categoria="food", empleado=self.empleado_ventas)
        resultado = validator.validar_gasto(gasto)
        self.assertEqual(resultado["status"], "APROBADO")
        # No se espera ninguna alerta
        self.assertEqual(resultado["alertas"], [])

    def test_antiguedad_pendiente(self):
        """
        Gastos de antigüedad (30d < X <= 60d) => PENDIENTE con alerta de LIMITE_ANTIGUEDAD.
        """
        fecha_45_dias = self.today - timedelta(days=45)
        gasto = Gasto(id="g_intermedio", monto=50, moneda="USD", fecha=fecha_45_dias, categoria="food", empleado=self.empleado_ventas)
        resultado = validator.validar_gasto(gasto)
        self.assertEqual(resultado["status"], "PENDIENTE")
        # Debería dar una alerta por LIMITE_ANTIGUEDAD
        codigos_alerta = [alerta["codigo"] for alerta in resultado["alertas"]]
        self.assertIn("LIMITE_ANTIGUEDAD", codigos_alerta)

    def test_antiguedad_rechazada(self):
        """
        Todos los gastos superiores a 60 días serán rechazados.
        Se emitirá una alerta por LIMITE_ANTIGUEDAD
        """
        fecha_90_dias = self.today - timedelta(days=90)
        gasto = Gasto(id="g_viejo", monto=20, moneda="USD", fecha=fecha_90_dias, categoria="food", empleado=self.empleado_ventas)
        resultado = validator.validar_gasto(gasto)
        self.assertEqual(resultado["status"], "RECHAZADO")
        # Emitir alerta por LIMITE_ANTIGUEDAD
        codigos_alerta = [alerta["codigo"] for alerta in resultado["alertas"]]
        self.assertIn("LIMITE_ANTIGUEDAD", codigos_alerta)

    def test_limite_categoria_food(self):
        """
        Límite categoría 'food':
            <= 100 USD APROBADO,
            > 100 USD y <= 150 PENDIENTE,
            > 150 USD RECHAZADO.
        """
        fecha_base = self.today

        # 80 USD -> APROBADO
        gs1 = Gasto(id="g_food_ok", monto=80, moneda="USD", fecha=fecha_base, categoria="food", empleado=self.empleado_ventas)
        res1 = validator.validar_gasto(gs1)
        self.assertEqual(res1["status"], "APROBADO")

        # 120 USD -> PENDIENTE (excede 100)
        gs2 = Gasto(id="g_food_med", monto=120, moneda="USD", fecha=fecha_base, categoria="food", empleado=self.empleado_ventas)
        res2 = validator.validar_gasto(gs2)
        self.assertEqual(res2["status"], "PENDIENTE")
        self.assertTrue(any(alerta["codigo"] == "LIMITE_CATEGORIA" for alerta in res2["alertas"]))

        # 160 USD -> RECHAZADO (excede 150)
        gs3 = Gasto(id="g_food_alto", monto=160, moneda="USD", fecha=fecha_base, categoria="food", empleado=self.empleado_ventas)
        res3 = validator.validar_gasto(gs3)
        self.assertEqual(res3["status"], "RECHAZADO")
        self.assertTrue(any(alerta["codigo"] == "LIMITE_CATEGORIA" for alerta in res3["alertas"]))


    def test_centro_costos_prohibiciones(self):
        """
        Cost center 'core_engineering' reportando 'food' -> siempre RECHAZADO.
        """
        fecha_base = self.today
        gasto = Gasto(id="g_prohibido", monto=50, moneda="USD", fecha=fecha_base, categoria="food", empleado=self.empleado_ingenieria)
        result = validator.validar_gasto(gasto)
        self.assertEqual(result["status"], "RECHAZADO")
        codigos_alerta = [alerta["codigo"] for alerta in result["alertas"]]
        self.assertIn("POLITICA_CENTRO_COSTO", codigos_alerta)

    def test_multiples_infracciones(self):
        """
        Gasto que infringe varias reglas: se deben agregar alertas y el estado de máxima severidad.
        Por ejemplo., core_engineering, "food", 200 USD. -> Infringe límite de categoría y cost_center
        """
        fecha_expirada = self.today - timedelta(days=100) # fuera de fecha
        gasto = Gasto(id="g_multi", monto=200, moneda="USD", fecha=fecha_expirada, categoria="food", empleado=self.empleado_ingenieria)
        resultado = validator.validar_gasto(gasto)
        # Espere RECHAZO por múltiples razones
        self.assertEqual(resultado["status"], "RECHAZADO")
        codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
        # Debe contener todas las alertas relevantes
        self.assertTrue({"LIMITE_ANTIGUEDAD", "LIMITE_CATEGORIA", "POLITICA_CENTRO_COSTO"}.issubset(codigos))


