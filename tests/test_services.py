import unittest
from unittest.mock import Mock, patch

import requests

from services.pdf_generator import generar_recibo_pdf
from services.rates import obtener_tasas_con_estado


class ServiceRegressionTests(unittest.TestCase):
    def test_pdf_supports_the_receipt_content(self):
        content = generar_recibo_pdf(
            {
                "cliente": "Ana",
                "producto": "Perfume",
                "monto_bs": 4000,
                "tasa_bcv": 100,
                "monto_usd": 40,
                "saldo_usd": 0,
                "estatus": "YA PAGO",
            }
        )
        self.assertTrue(content.startswith(b"%PDF"))

    def test_rates_report_fallback_sources(self):
        live_response = Mock()
        live_response.raise_for_status.return_value = None
        live_response.json.return_value = {
            "data": {
                "bcv": {"rate": 752.09},
                "binance": {"buy_rate": 846.55},
                "best": {"buy_rate": 847.10},
            }
        }

        obtener_tasas_con_estado.clear()
        with patch(
            "services.rates.requests.get",
            side_effect=[live_response, requests.exceptions.SSLError("unavailable")],
        ):
            rates, fallback_rates = obtener_tasas_con_estado()

        self.assertEqual(rates[0], 752.09)
        self.assertEqual(fallback_rates, ("Euro BCV",))


if __name__ == "__main__":
    unittest.main()
