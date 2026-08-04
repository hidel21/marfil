import unittest
from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import database as db


class DatabaseRegressionTests(unittest.TestCase):
    def setUp(self):
        self.original_get_session = db.get_session
        engine = create_engine("sqlite+pysqlite:///:memory:")
        db.Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        db.get_session = self.Session

    def tearDown(self):
        db.get_session = self.original_get_session

    def test_sale_persists_quantity_and_updates_stock_atomically(self):
        product = db.create_product("Perfume prueba", 10, 20, 19, 3)

        sale = db.register_sale(
            fecha=date.today(),
            cliente="Ana",
            vendedor="Gregory",
            producto_nombre=product.nombre,
            producto_id=product.id,
            cantidad=2,
            precio_venta=40,
            costo_total=20,
            ganancia=20,
            deuda=40,
            estatus="PENDIENTE",
        )

        with self.Session() as session:
            self.assertEqual(session.get(db.Producto, product.id).stock, 1)
            self.assertEqual(session.get(db.Venta, sale.id).cantidad, 2)

        with self.assertRaises(Exception):
            db.register_sale(
                fecha=date.today(),
                cliente="Luis",
                vendedor="Gregory",
                producto_nombre=product.nombre,
                producto_id=product.id,
                cantidad=2,
                precio_venta=40,
                costo_total=20,
                ganancia=20,
                deuda=40,
                estatus="PENDIENTE",
            )

        with self.Session() as session:
            self.assertEqual(session.get(db.Producto, product.id).stock, 1)
            self.assertEqual(session.scalar(select(func.count(db.Venta.id))), 1)

    def test_payment_rejects_overpayment_and_completes_debt(self):
        product = db.create_product("Perfume prueba", 10, 20, 19, 1)
        sale = db.register_sale(
            fecha=date.today(),
            cliente="Ana",
            vendedor="Gregory",
            producto_nombre=product.nombre,
            producto_id=product.id,
            cantidad=1,
            precio_venta=40,
            costo_total=10,
            ganancia=30,
            deuda=40,
            estatus="PENDIENTE",
        )

        with self.assertRaises(Exception):
            db.register_payment(
                venta_id=sale.id,
                fecha=date.today(),
                cliente="Ana",
                producto=product.nombre,
                monto_bs=5000,
                monto_usd=50,
                referencia="OVER",
                tasa_bcv=100,
                nro_cuota=1,
            )

        result = db.register_payment(
            venta_id=sale.id,
            fecha=date.today(),
            cliente="Ana",
            producto=product.nombre,
            monto_bs=4000,
            monto_usd=40,
            referencia="OK",
            tasa_bcv=100,
            nro_cuota=1,
        )

        self.assertEqual(result, (0.0, "YA PAGO"))
        self.assertEqual(db.load_payment_metrics(), (4000.0, 40.0, 1))
        self.assertTrue(db.load_pending_sales_dataframe().empty)

    def test_empty_commission_report_has_expected_columns(self):
        report = db.load_commission_dataframe()
        self.assertTrue(report.empty)
        self.assertIn("comision_usd", report.columns)


if __name__ == "__main__":
    unittest.main()
