import assert from "node:assert/strict";
import test from "node:test";
import { bs, repartir, sumar, usd } from "./dinero.ts";

test("suma dinero sin introducir errores de punto flotante", () => {
  assert.equal(sumar(["0.10", "0.20"]).toFixed(2), "0.30");
});

test("reparte el centavo restante en la última cuota", () => {
  assert.deepEqual(repartir("10.00", 3).map(String), ["3.33", "3.33", "3.34"]);
});

test("mantiene las convenciones distintas de USD y VES", () => {
  assert.equal(usd("15679.22"), "$15,679.22");
  assert.equal(bs("15679.22"), "Bs. 15.679,22");
});
