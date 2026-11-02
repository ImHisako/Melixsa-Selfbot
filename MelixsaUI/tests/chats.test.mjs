import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

async function loadModule(file, replace = value => value) {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  return import(`data:text/javascript;base64,${Buffer.from(replace(outputText)).toString('base64')}`);
}
const catalog = JSON.parse(readFileSync(new URL('../src/catalog/text-styles.json', import.meta.url), 'utf8'));
const { transformText, messageLimit } = await loadModule('../src/lib/textStyles.ts', source =>
  source.replace("import catalog from '../catalog/text-styles.json';", `const catalog = ${JSON.stringify(catalog)};`));
const { mergeMessages, syncLatest } = await loadModule('../src/lib/chatMessages.ts');

test('preview transforms Latin letters while preserving emoji, accents and line breaks', () => {
  assert.equal(transformText('Abc è 😀\n<>', 'fraktur'), '𝔄𝔟𝔠 è 😀\n<>');
  assert.equal(transformText('Abc!', 'circled'), 'Ⓐⓑⓒ!');
  assert.equal(transformText('Abc!', 'squared'), '🅰🅱🅲!');
  assert.equal(transformText('Abc!', 'boldItalic'), '𝘼𝙗𝙘!');
  assert.equal(transformText('Abc! 123', 'fullWidth'), 'Ａｂｃ！ １２３');
  assert.equal(transformText('Hi!', 'strikethrough'), 'H\u0336i\u0336!');
  assert.equal(transformText('Ab', 'invisibleSeparator'), 'A\u2060b\u2060');
  assert.equal(transformText('Abc è 😀'), 'Abc è 😀');
  assert.throws(() => transformText('abc', 'missing'));
});

test('the transformed preview length accounts for UTF-16 and combining marks', () => {
  assert.equal(transformText('a'.repeat(2048), 'fraktur').length, messageLimit);
  assert.ok(transformText('a'.repeat(2049), 'fraktur').length > messageLimit);
  assert.equal(transformText('a', 'zalgo').length, 7);
  assert.equal(transformText('😀').length, 2);
});

test('older pages merge in chronological order without duplicate messages', () => {
  const current = [{ id: 4, text: 'four' }, { id: 5, text: 'five' }];
  assert.deepEqual(mergeMessages(current, [{ id: 3, text: 'three' }, { id: 4, text: 'edit' }]), [
    { id: 3, text: 'three' }, { id: 4, text: 'edit' }, { id: 5, text: 'five' },
  ]);
  assert.equal(current[0].text, 'four');
});

test('refresh applies edits, removes deleted messages and preserves loaded older history', () => {
  const current = [1, 2, 3, 4, 5].map(id => ({ id, text: String(id) }));
  assert.deepEqual(syncLatest(current, [{ id: 3, text: 'edited' }, { id: 5, text: '5' }, { id: 6, text: '6' }]), [
    { id: 1, text: '1' }, { id: 2, text: '2' }, { id: 3, text: 'edited' }, { id: 5, text: '5' }, { id: 6, text: '6' },
  ]);
  assert.deepEqual(syncLatest(current, []), []);
});
