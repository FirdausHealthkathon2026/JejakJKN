import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createPrivateKey, createPublicKey, generateKeyPairSync, randomBytes } from 'node:crypto';

export function bootstrap(projectDir, stateDir, hasInitializedDatabase = false) {
  const envFile = path.join(projectDir, '.env');
  const savedEnv = path.join(stateDir, '.env');
  const secretsDir = path.join(projectDir, '.secrets');
  fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });

  function writePrivate(filename, content, local = false) {
    fs.writeFileSync(`${filename}.tmp`, content, { mode: 0o600 });
    fs.renameSync(`${filename}.tmp`, filename);
    if (local && process.env.LOCAL_UID && process.env.LOCAL_GID) {
      fs.chownSync(filename, Number(process.env.LOCAL_UID), Number(process.env.LOCAL_GID));
    }
  }

  if (!fs.existsSync(envFile)) {
    if (fs.existsSync(savedEnv)) {
      writePrivate(envFile, fs.readFileSync(savedEnv), true);
      console.log('[bootstrap] Konfigurasi dipulihkan otomatis dari Docker.');
    } else {
      const secrets = new Map();
      let env = fs.readFileSync(path.join(projectDir, '.env.example'), 'utf8');
      env = env.replace(/^([A-Z0-9_]+)=change-me-local-only\r?$/gm, (_, key) => {
        const secret = randomBytes(24).toString('hex');
        secrets.set(key, secret);
        return `${key}=${secret}`;
      });
      for (const name of ['ENCOUNTER', 'EVIDENCE', 'VERIFICATION', 'REVIEW', 'SIMRS_A', 'SIMRS_B']) {
        const expression = new RegExp(`^${name}_DATABASE_URL=(.*):change-me-local-only@`, 'm');
        env = env.replace(expression, `${name}_DATABASE_URL=$1:${secrets.get(`${name}_DB_PASSWORD`)}@`);
      }
      // Synthetic benchmark SQL is encrypted and indexed with these demo-only keys.
      env = env.replace('PARTICIPANT_LOOKUP_HMAC_KEY=replace-with-64-hex-characters',
        'PARTICIPANT_LOOKUP_HMAC_KEY=0d70fe6c79ac335cbf6894b35f18c20a470000094d55f8a85ee7b937359baa8c');
      env = env.replace('FIELD_ENCRYPTION_MASTER_KEY=replace-with-64-hex-characters',
        'FIELD_ENCRYPTION_MASTER_KEY=76e615c41c9303747950656b727151dc65aced28b91aa891429beca78a695b7c');
      if (env.includes('change-me-local-only') || env.includes('replace-with-64-hex-characters')) {
        throw new Error('Template konfigurasi belum lengkap; .env tidak ditulis.');
      }
      if (hasInitializedDatabase) {
        // Unknown database credentials and encryption keys cannot be reconstructed safely.
        env += `\nDEMO_DATA_SUFFIX=-demo-${randomBytes(6).toString('hex')}\n`;
        console.log('[bootstrap] Data lama tetap disimpan; menyiapkan penyimpanan demo baru otomatis.');
      }
      writePrivate(envFile, env, true);
    }
  }

  fs.mkdirSync(secretsDir, { recursive: true, mode: 0o700 });
  if (process.env.LOCAL_UID && process.env.LOCAL_GID) {
    fs.chownSync(secretsDir, Number(process.env.LOCAL_UID), Number(process.env.LOCAL_GID));
  }
  for (const name of ['qr-signing', 'release-signing']) {
    const privateFile = path.join(secretsDir, `${name}-private.pem`);
    const publicFile = path.join(secretsDir, `${name}-public.pem`);
    const savedPrivate = path.join(stateDir, `${name}-private.pem`);
    if (!fs.existsSync(privateFile)) {
      const privateKey = fs.existsSync(savedPrivate)
        ? fs.readFileSync(savedPrivate)
        : generateKeyPairSync('ed25519').privateKey.export({ type: 'pkcs8', format: 'pem' });
      writePrivate(privateFile, privateKey, true);
    }
    const privateKey = createPrivateKey(fs.readFileSync(privateFile));
    const publicKey = createPublicKey(privateKey).export({ type: 'spki', format: 'pem' });
    writePrivate(publicFile, publicKey, true);
    writePrivate(savedPrivate, fs.readFileSync(privateFile));
  }
  writePrivate(savedEnv, fs.readFileSync(envFile));
  console.log('[bootstrap] Konfigurasi dan kunci siap; backup tersimpan di volume Docker.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  bootstrap(process.cwd(), '/state', fs.existsSync('/database/PG_VERSION'));
}
