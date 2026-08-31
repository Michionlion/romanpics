import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const temporary = await mkdtemp(join(tmpdir(), 'romanpics-openapi-'));
const bundledPath = join(temporary, 'documented.json');

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', ...options });
  if (result.status !== 0) {
    throw new Error(`${command} failed:\n${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

function operations(schema) {
  const result = new Map();
  for (const [path, pathValue] of Object.entries(schema.paths ?? {})) {
    for (const method of ['get', 'put', 'post', 'patch', 'delete']) {
      const operation = pathValue?.[method];
      if (!operation) continue;
      result.set(`${method.toUpperCase()} ${path}`, operation.operationId ?? '');
    }
  }
  return result;
}

try {
  const runtimeText = run('uv', [
    'run',
    '--project',
    'services/api',
    'python',
    '-c',
    'import json; from romanpics_api.main import app; print(json.dumps(app.openapi()))',
  ]);
  run('npx', [
    '--yes',
    '@redocly/cli@2.49.0',
    'bundle',
    'docs/openapi.yaml',
    '--ext',
    'json',
    '--output',
    bundledPath,
  ]);
  const runtime = JSON.parse(runtimeText);
  const documented = JSON.parse(await readFile(bundledPath, 'utf8'));
  const actualOperations = operations(runtime);
  const documentedOperations = operations(documented);
  const failures = [];
  for (const [key, operationId] of actualOperations) {
    if (!documentedOperations.has(key)) failures.push(`missing documented operation ${key}`);
    else if (documentedOperations.get(key) !== operationId) {
      failures.push(`${key} operationId is ${documentedOperations.get(key)}, expected ${operationId}`);
    }
  }
  for (const key of documentedOperations.keys()) {
    if (!actualOperations.has(key)) failures.push(`documented operation has no runtime route: ${key}`);
  }
  if (failures.length > 0) throw new Error(`OpenAPI drift:\n- ${failures.join('\n- ')}`);
  console.log(`OpenAPI routes aligned: ${actualOperations.size} operations.`);
} finally {
  await rm(temporary, { recursive: true, force: true });
}
