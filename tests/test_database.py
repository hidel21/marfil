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

    def test_purchase_increases_stock_updates_cost_and_creates_payable(self):
        product = db.create_product("Perfume prueba", 10, 20, 19, 3)
        proveedor = db.create_proveedor(nombre="Distribuidora XYZ")

        compra = db.register_purchase(
            fecha=date.today(),
            proveedor_id=proveedor.id,
            proveedor_nombre=proveedor.nombre,
            producto_id=product.id,
            producto_nombre=product.nombre,
            cantidad=5,
            costo_unitario=12.0,
            monto_pagado=30.0,
        )

        with self.Session() as session:
            self.assertEqual(session.get(db.Producto, product.id).stock, 8)
            self.assertEqual(float(session.get(db.Producto, product.id).costo), 12.0)

        self.assertEqual(compra.estatus, "PENDIENTE")
        self.assertEqual(float(compra.saldo), 30.0)
        payables = db.load_pending_payables_dataframe()
        self.assertEqual(len(payables), 1)
        self.assertEqual(float(payables.iloc[0]["saldo"]), 30.0)

    def test_payable_payment_rejects_overpayment_and_completes_debt(self):
        product = db.create_product("Perfume prueba", 10, 20, 19, 1)
        proveedor = db.create_proveedor(nombre="Distribuidora XYZ")
        compra = db.register_purchase(
            fecha=date.today(),
            proveedor_id=proveedor.id,
            proveedor_nombre=proveedor.nombre,
            producto_id=product.id,
            producto_nombre=product.nombre,
            cantidad=1,
            costo_unitario=100.0,
            monto_pagado=0.0,
        )

        with self.assertRaises(Exception):
            db.register_payable_payment(compra_id=compra.id, fecha=date.today(), monto=150.0)

        nuevo_saldo, estatus = db.register_payable_payment(
            compra_id=compra.id, fecha=date.today(), monto=100.0, referencia="OK"
        )
        self.assertEqual((nuevo_saldo, estatus), (0.0, "PAGADO"))
        self.assertTrue(db.load_pending_payables_dataframe().empty)

    def test_socios_investment_dataframe_computes_participation_and_roi(self):
        db.seed_default_socios()
        socios_df = db.load_socios_dataframe()
        socios_df.loc[socios_df["nombre"] == "Gregory", "capital_invertido"] = 300.0
        socios_df.loc[socios_df["nombre"] == "Hidelberg", "capital_invertido"] = 100.0
        db.save_socio_changes(socios_df)

        product = db.create_product("Perfume prueba", 10, 20, 19, 5)
        db.register_sale(
            fecha=date.today(),
            cliente="Ana",
            vendedor="Gregory",
            producto_nombre=product.nombre,
            producto_id=product.id,
            cantidad=1,
            precio_venta=40,
            costo_total=10,
            ganancia=30,
            deuda=0,
            estatus="YA PAGO",
        )

        inversion_df = db.load_socios_investment_dataframe()
        gregory_row = inversion_df[inversion_df["socio"] == "Gregory"].iloc[0]
        hidelberg_row = inversion_df[inversion_df["socio"] == "Hidelberg"].iloc[0]

        self.assertAlmostEqual(gregory_row["participacion_pct"], 75.0)
        self.assertAlmostEqual(hidelberg_row["participacion_pct"], 25.0)
        self.assertAlmostEqual(gregory_row["ganancia_atribuida"], 22.5)
        self.assertAlmostEqual(hidelberg_row["ganancia_atribuida"], 7.5)

    def test_weekly_profitability_groups_by_week(self):
        product = db.create_product("Perfume prueba", 10, 20, 19, 10)
        db.register_sale(
            fecha=date(2026, 1, 5),
            cliente="Ana",
            vendedor="Gregory",
            producto_nombre=product.nombre,
            producto_id=product.id,
            cantidad=1,
            precio_venta=40,
            costo_total=10,
            ganancia=30,
            deuda=0,
            estatus="YA PAGO",
        )
        db.register_sale(
            fecha=date(2026, 1, 6),
            cliente="Luis",
            vendedor="Gregory",
            producto_nombre=product.nombre,
            producto_id=product.id,
            cantidad=1,
            precio_venta=40,
            costo_total=10,
            ganancia=50,
            deuda=0,
            estatus="YA PAGO",
        )

        semanal_df = db.load_weekly_profitability_dataframe()
        self.assertEqual(len(semanal_df), 1)
        self.assertAlmostEqual(float(semanal_df.iloc[0]["ganancia_total"]), 80.0)

    def test_product_margin_dataframe_computes_margin_percentage(self):
        product = db.create_product("Perfume prueba", 10, 20, 19, 10)
        db.register_sale(
            fecha=date.today(),
            cliente="Ana",
            vendedor="Gregory",
            producto_nombre=product.nombre,
            producto_id=product.id,
            cantidad=2,
            precio_venta=100,
            costo_total=20,
            ganancia=80,
            deuda=0,
            estatus="YA PAGO",
        )

        margen_df = db.load_product_margin_dataframe()
        row = margen_df[margen_df["producto"] == product.nombre].iloc[0]
        self.assertEqual(row["unidades_vendidas"], 2)
        self.assertAlmostEqual(row["margen_pct"], 80.0)

    def test_gasto_general_reflected_in_utilidad_neta_real(self):
        product = db.create_product("Perfume prueba", 10, 20, 19, 10)
        db.register_sale(
            fecha=date.today(),
            cliente="Ana",
            vendedor="Gregory",
            producto_nombre=product.nombre,
            producto_id=product.id,
            cantidad=1,
            precio_venta=100,
            costo_total=20,
            ganancia=80,
            deuda=0,
            estatus="YA PAGO",
        )
        db.create_gasto(fecha=date.today(), categoria="Alquiler", descripcion="Local", monto=30.0)

        metrics = db.load_financial_metrics()
        total_gastos = metrics[6]
        utilidad_neta_real = metrics[7]
        self.assertEqual(total_gastos, 30.0)
        self.assertEqual(utilidad_neta_real, 50.0)

    def test_out_of_stock_demand_only_returns_zero_stock_ranked_by_demand(self):
        agotado = db.create_product("Agotado Alta Demanda", 10, 20, 19, 3)
        disponible = db.create_product("Disponible", 10, 20, 19, 5)

        db.register_sale(
            fecha=date.today(),
            cliente="Ana",
            vendedor="Gregory",
            producto_nombre=agotado.nombre,
            producto_id=agotado.id,
            cantidad=3,
            precio_venta=100,
            costo_total=30,
            ganancia=70,
            deuda=0,
            estatus="YA PAGO",
        )
        db.register_sale(
            fecha=date.today(),
            cliente="Luis",
            vendedor="Gregory",
            producto_nombre=disponible.nombre,
            producto_id=disponible.id,
            cantidad=1,
            precio_venta=40,
            costo_total=10,
            ganancia=30,
            deuda=0,
            estatus="YA PAGO",
        )

        agotados_df = db.load_out_of_stock_demand_dataframe()
        self.assertEqual(list(agotados_df["nombre"]), ["Agotado Alta Demanda"])
        self.assertEqual(int(agotados_df.iloc[0]["demanda_historica"]), 3)


if __name__ == "__main__":
    unittest.main()
