import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { sign, verify } from 'node:crypto';
import { test } from 'node:test';
import { bootstrap } from './bootstrap-dev.mjs';

test('fresh ZIP, rerun, and re-extracted ZIP keep working credentials and signing keys', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jejakjkn-bootstrap-'));
  try {
    const project = path.join(root, 'first zip');
    const state = path.join(root, 'docker-state');
    fs.mkdirSync(project);
    fs.copyFileSync(new URL('../.env.example', import.meta.url), path.join(project, '.env.example'));
    bootstrap(project, state);
    const env = fs.readFileSync(path.join(project, '.env'), 'utf8');
    const values = Object.fromEntries(env.split(/\r?\n/).filter(line => /^[A-Z0-9_]+=/.test(line))
      .map(line => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]));
    assert(!env.includes('change-me-local-only'));
    assert(!env.includes('replace-with-'));
    assert.equal(values.GROQ_API_KEY, '');
    assert.equal(values.NARRATIVE_PROVIDER, 'template');
    const passwords = Object.entries(values).filter(([key]) => key.endsWith('_PASSWORD'));
    assert.equal(new Set(passwords.map(([, value]) => value)).size, passwords.length);
    for (const name of ['ENCOUNTER', 'EVIDENCE', 'VERIFICATION', 'REVIEW', 'SIMRS_A', 'SIMRS_B']) {
      assert.equal(new URL(values[`${name}_DATABASE_URL`]).password, values[`${name}_DB_PASSWORD`]);
    }
    const privateKey = fs.readFileSync(path.join(project, '.secrets/qr-signing-private.pem'));
    const publicKey = fs.readFileSync(path.join(project, '.secrets/qr-signing-public.pem'));
    assert(verify(null, Buffer.from('demo QR'), publicKey, sign(null, Buffer.from('demo QR'), privateKey)));
    assert.equal(fs.statSync(path.join(project, '.env')).mode & 0o777, 0o600);
    assert.equal(fs.statSync(path.join(project, '.secrets')).mode & 0o777, 0o700);

    fs.unlinkSync(path.join(project, '.secrets/qr-signing-public.pem'));
    bootstrap(project, state, true);
    assert.equal(fs.readFileSync(path.join(project, '.env'), 'utf8'), env);
    assert.deepEqual(fs.readFileSync(path.join(project, '.secrets/qr-signing-public.pem')), publicKey);

    const extractedAgain = path.join(root, 'second zip');
    fs.mkdirSync(extractedAgain);
    bootstrap(extractedAgain, state, true);
    assert.equal(fs.readFileSync(path.join(extractedAgain, '.env'), 'utf8'), env);
    assert.deepEqual(fs.readFileSync(path.join(extractedAgain, '.secrets/qr-signing-private.pem')), privateKey);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('existing database without recoverable credentials never receives new credentials', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jejakjkn-orphan-'));
  try {
    assert.throws(() => bootstrap(root, path.join(root, 'state'), true), /Database lama/);
    assert(!fs.existsSync(path.join(root, '.env')));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
