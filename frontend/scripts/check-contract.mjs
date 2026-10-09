/**
 * Contract check (docs/TEST_PLAN.md 9): every route the dashboard calls must exist, with the same
 * method, in the gateway's OpenAPI schema (docs/api/openapi.json, exported by
 * scripts/export_openapi.py). Fails with exit code 1 on drift.
 *
 *     npm run check:contract
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const schemaPath = resolve(here, '../../docs/api/openapi.json');

// endpoints.js imports client.js, which only touches browser APIs when a request is made.
const { ROUTES } = await import('../src/api/endpoints.js');

let schema;
try {
  schema = JSON.parse(readFileSync(schemaPath, 'utf8'));
} catch (e) {
  console.error(`[FAIL] cannot read ${schemaPath}: ${e.message}`);
  console.error('       run: python scripts/export_openapi.py');
  process.exit(1);
}

const problems = [];
for (const [name, [method, path]] of Object.entries(ROUTES)) {
  const ops = schema.paths[`/api${path}`];
  if (!ops) problems.push(`${name}: ${method} /api${path} is not in the schema`);
  else if (!ops[method.toLowerCase()]) problems.push(`${name}: /api${path} has no ${method} (has ${Object.keys(ops).join(', ').toUpperCase()})`);
}

if (problems.length) {
  console.error(`[FAIL] ${problems.length} dashboard route(s) do not match the gateway schema:`);
  problems.forEach((p) => console.error(`  - ${p}`));
  process.exit(1);
}
console.log(`[OK] all ${Object.keys(ROUTES).length} dashboard routes exist in docs/api/openapi.json`);
