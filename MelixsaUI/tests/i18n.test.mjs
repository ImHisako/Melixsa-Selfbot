import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const catalog = JSON.parse(readFileSync(new URL('../src/i18n/en.json', import.meta.url), 'utf8'));
const source = readFileSync(new URL('../src/i18n/core.ts', import.meta.url), 'utf8');
// Use the project's TypeScript compiler without requiring another test dependency.
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
const moduleSource = outputText.replace("import english from './en.json';", `const english = ${JSON.stringify(catalog)};`);
const { languageStorageKey, locales, localizeMessage, readLanguage, resolveLanguage, translate } = await import(`data:text/javascript;base64,${Buffer.from(moduleSource).toString('base64')}`);

test('saved language takes priority; invalid preferences fall back to browser language', () => {
  assert.equal(resolveLanguage('it', 'en-US'), 'it');
  assert.equal(resolveLanguage('en', 'it-IT'), 'en');
  assert.equal(resolveLanguage('fr', 'en-GB'), 'en');
  assert.equal(resolveLanguage(null, 'EN-us'), 'en');
  assert.equal(resolveLanguage(null, 'it-IT'), 'it');
  assert.equal(resolveLanguage(null, 'fr-FR'), 'it');
  assert.equal(resolveLanguage(null, 'enochian'), 'it');
  assert.deepEqual(locales, { it: 'it-IT', en: 'en-GB' });
});

test('unavailable storage does not prevent language selection', () => {
  assert.equal(readLanguage({ getItem(key) { assert.equal(key, languageStorageKey); return 'en'; } }, 'it-IT'), 'en');
  assert.equal(readLanguage({ getItem() { throw new Error('Storage blocked'); } }, 'en-US'), 'en');
});

test('every catalog entry is translated and preserves interpolation parameters', () => {
  const params = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
  for (const [italian, english] of Object.entries(catalog)) {
    assert.ok(english.trim(), italian);
    assert.equal(translate('it', italian), italian);
    assert.equal(translate('en', italian), english);
    assert.deepEqual(params(italian), params(english), italian);
  }
});

test('interpolation inserts values literally without reinterpreting user content', () => {
  assert.equal(translate('en', 'Foto profilo di {name}', { name: 'Mario {count} $&' }), 'Profile photo of Mario {count} $&');
  assert.equal(translate('it', '{count} reazioni', { count: 3 }), '3 reazioni');
  assert.equal(translate('en', '{count} reazioni', { count: 3 }), '3 reactions');
});

test('bridge messages and dynamic errors change language without altering raw data', () => {
  assert.equal(localizeMessage('en', 'Modifiche salvate. Tutto aggiornato.'), 'Changes saved. Everything is up to date.');
  assert.equal(localizeMessage('en', 'Telegram: PhoneCodeInvalid. Controlla i dati e riprova.'), 'Telegram: PhoneCodeInvalid. Check your details and try again.');
  assert.equal(localizeMessage('en', 'delete_after: scegli un numero da 0 a 3600.'), 'delete_after: choose a number from 0 to 3600.');
  assert.equal(localizeMessage('en', 'Monitoraggio del gruppo -100123 attivato.'), 'Monitoring enabled for group -100123.');
  assert.equal(localizeMessage('en', 'Monitoraggio del gruppo -100123 fermato.'), 'Monitoring stopped for group -100123.');
  assert.equal(localizeMessage('en', 'Monitoraggio Stalk dell’utente 123 attivato.'), 'Stalk monitoring enabled for user 123.');
  assert.equal(localizeMessage('en', 'Monitoraggio Stalk dell’utente 123 fermato.'), 'Stalk monitoring stopped for user 123.');
  assert.equal(localizeMessage('en', 'Formato non valido per TELEGRAM_API_ID nel file .env.'), 'Invalid format for TELEGRAM_API_ID in the .env file.');
  assert.equal(localizeMessage('it', 'Telegram: PhoneCodeInvalid. Controlla i dati e riprova.'), 'Telegram: PhoneCodeInvalid. Controlla i dati e riprova.');
  const unknown = 'socket error: custom diagnostic {name}';
  assert.equal(localizeMessage('en', unknown), unknown);
});
