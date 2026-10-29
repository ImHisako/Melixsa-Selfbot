import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const read = file => readFileSync(new URL(file, import.meta.url), 'utf8');
const catalog = JSON.parse(read('../src/catalog/commands.json'));
async function load(file, replacements = []) {
  let { outputText } = ts.transpileModule(read(file), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  for (const [before, after] of replacements) outputText = outputText.replace(before, after);
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
}
const { commandText, hasCommandTranslation } = await load('../src/i18n/commandText.ts', [
  ["import english from './commands-en.json';", `const english = ${read('../src/i18n/commands-en.json')};`],
]);
const { commandSyntax, findCommands, parseFavorites } = await load('../src/lib/commands.ts');
const search = (query, overrides = {}) => findCommands(catalog, {
  query, prefix: '!', category: 'all', favoritesOnly: false, favorites: new Set(), localize: text => commandText('en', text), ...overrides,
});
const flatten = sections => sections.flatMap(section => section.commands);

test('every category, description, syntax and help detail has an English translation', () => {
  for (const section of catalog.categories) {
    assert.ok(hasCommandTranslation(section.title), section.title);
    for (const command of section.commands) {
      for (const field of ['description', 'details', 'usage']) {
        assert.ok(hasCommandTranslation(command[field]), `${command.name}: ${command[field]}`);
        assert.equal(commandText('it', command[field]), command[field]);
        if (command[field]) assert.ok(commandText('en', command[field]).trim());
      }
    }
  }
});

test('empty search includes the complete canonical catalog without duplicating aliases', () => {
  assert.equal(flatten(search('')).length, catalog.categories.reduce((count, section) => count + section.commands.length, 0));
  assert.equal(new Set(flatten(search('')).map(command => command.name)).size, flatten(search('')).length);
});

test('search resolves aliases, configured prefixes and special help aliases', () => {
  assert.equal(search('!morse').find(section => section.id === 'text').commands[0].name, 'encodemorsecode');
  assert.equal(search('!?').find(section => section.id === 'settings').commands[0].name, 'help');
  assert.ok(flatten(search('?scpause', { prefix: '?' })).some(command => command.name === 'scpause'));
  assert.ok(flatten(search('javascript')).some(command => command.name === 'js'));
});

test('search covers translated and original descriptions, categories and accents', () => {
  assert.ok(flatten(search('automatic reactions')).some(command => command.name === 'autoreact'));
  assert.ok(flatten(search('reazioni automatiche')).some(command => command.name === 'autoreact'));
  assert.ok(search('administràtion').find(section => section.id === 'admin'));
  assert.ok(search('utilita').find(section => section.id === 'misc'));
  assert.ok(flatten(search('Morse Decode')).some(command => command.name === 'decodemorsecode'));
});

test('category and favourites filters combine with search', () => {
  const results = flatten(search('', { category: 'text', favoritesOnly: true, favorites: new Set(['reverse', 'scpause']) }));
  assert.deepEqual(results.map(command => command.name), ['reverse']);
  assert.deepEqual(search('not-a-real-command-999999'), []);
  assert.deepEqual(search('', { favoritesOnly: true }), []);
});

test('syntax uses the current prefix and preserves literal command and alias names', () => {
  const all = flatten(search(''));
  const ping = all.find(command => command.name === 'ping');
  const morse = all.find(command => command.name === 'encodemorsecode');
  assert.equal(commandSyntax(ping, '>'), '>ping');
  assert.equal(commandSyntax(morse, '!', 'morse'), '!morse <testo o risposta>');
  assert.equal(commandSyntax({ ...morse, usage: commandText('en', morse.usage) }, '?'), '?encodemorsecode <text or reply>');
});

test('malformed stored favourites are ignored and valid names are deduplicated', () => {
  for (const raw of [null, '{bad', '{}', 'true']) assert.equal(parseFavorites(raw).size, 0);
  assert.deepEqual([...parseFavorites('["ping", "ping", 1, null, "../.env", "anti-login", "8ball"]')], ['ping', 'anti-login', '8ball']);
});

test('unknown catalog text remains readable if a newer engine introduces a command', () => {
  assert.equal(commandText('en', 'A new command description'), 'A new command description');
});
