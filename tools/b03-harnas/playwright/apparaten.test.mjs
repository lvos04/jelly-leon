import assert from 'node:assert/strict';
import test from 'node:test';
import { beoordeling } from './apparaten.mjs';

const beeld = { t: 10000, ct: 2, w: 640, p: false, err: null };

test('de klik, het beeld en de voortgang moeten binnen hetzelfde venster vallen', () => {
  assert.equal(beoordeling(beeld, 10000, false), true);
  for (const wijziging of [{ t: 10001 }, { ct: 1.99 }, { w: 0 }, { p: true }, { err: 3 }]) {
    assert.equal(beoordeling({ ...beeld, ...wijziging }, 10000, false), false);
  }
});

test('een vervangen speler met beeld wist de fout of de terugval van de eerste Direct Play niet', () => {
  assert.equal(beoordeling(beeld, 10000, true), false);
  assert.equal(beoordeling(beeld, 10000, false, true), false);
  assert.equal(beoordeling({ ...beeld, t: 60000 }, 60000, false), true);
  assert.equal(beoordeling({ ...beeld, t: 60001 }, 60000, false), false);
});
