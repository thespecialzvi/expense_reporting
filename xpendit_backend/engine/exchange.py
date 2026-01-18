import os, requests
from datetime import date

OXR_APP_ID = os.getenv("OXR_APP_ID") # Acceso al App ID de OpenExchangeRates desde .env
MONEDA_BASE = "USD" # La moneda base de la política con la que estamos trabajando

def get_tasa_cambio(moneda: str, fecha: date = None) -> float:
    """
    Obtener el tipo de cambio de 1 unidad de 'moneda' a 'USD'.
    Si se especifica 'fecha', obtener el tipo de cambio histórico para esa fecha, de lo contrario, el más reciente.
    Retorna el valor del tipo de cambio (1 USD por 1 unidad de 'moneda').
    """
    if moneda.upper() == MONEDA_BASE:
        return 1.0
    if OXR_APP_ID is None:
        raise RuntimeError("La API Key de Open Exchange Rates no ha sido configurada.")
    try:
        if fecha:
            # Endpoint de tipos de cambio históricos
            datestr = fecha.strftime("%Y-%m-%d")
            url = f"https://openexchangerates.org/api/historical/{datestr}.json?app_id={OXR_APP_ID}&base={MONEDA_BASE}&symbols={moneda}"
        else:
            # Endpoint de tasas más recientes
            url = f"https://openexchangerates.org/api/latest.json?app_id={OXR_APP_ID}&base={MONEDA_BASE}&symbols={moneda}"
        response = requests.get(url)
        data = response.json()
        # La API retornará el valor de las tasas como un diccionario dentro de 'rates'
        tasa = data["rates"].get(moneda.upper())
        if tasa is None:
            raise ValueError(f"No existe la tasa de cambio para la moneda {moneda}")
        return tasa
    except Exception as e:
        # Handling de errores de red o errores en JSON
        print(f"Se produjo un error al consultar la tasa de cambio para {moneda}: {e}")
        return None


