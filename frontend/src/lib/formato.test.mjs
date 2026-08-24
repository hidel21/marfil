import assert from "node:assert/strict";
import test from "node:test";
import { contar, fecha, telefonoLegible } from "./formato.ts";

test("presenta fechas en el orden venezolano", () => {
  assert.equal(fecha("2026-08-22"), "22/08/2026");
});

test("formatea móviles venezolanos y plurales", () => {
  assert.equal(telefonoLegible("+584121234567"), "0412-1234567");
  assert.equal(contar(1, "venta"), "1 venta");
  assert.equal(contar(2, "venta"), "2 ventas");
});
