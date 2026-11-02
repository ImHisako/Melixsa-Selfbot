import catalog from '../catalog/text-styles.json';

export const textStyles = catalog;
export const messageLimit = 4096;
const letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';

export function transformText(value: string, styleId = 'plain'): string {
  const style = textStyles.find(item => item.id === styleId);
  if (!style) throw new Error('Stile del testo non valido.');
  const alphabet = Array.from((style.lower ?? '') + (style.upper ?? ''));
  return Array.from(value, char => {
    const code = char.codePointAt(0)!;
    if (style.full_width && code >= 0x21 && code <= 0x7e) return String.fromCodePoint(code + 0xfee0);
    const index = letters.indexOf(char);
    return index < 0 ? char : (alphabet[index] ?? char) + (style.suffix ?? '');
  }).join('');
}
