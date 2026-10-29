import type { CommandCatalog, SelfbotCommand } from '../types';

export const favoritesStorageKey = 'melixsa.command-favorites';

export function parseFavorites(raw: string | null): Set<string> {
  try {
    const values: unknown = JSON.parse(raw || '[]');
    return new Set(Array.isArray(values) ? values.filter((value): value is string =>
      typeof value === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(value)).slice(0, 500) : []);
  } catch {
    return new Set();
  }
}

export function commandSyntax(command: SelfbotCommand, prefix: string, name = command.name): string {
  return `${prefix}${name}${command.usage ? ` ${command.usage}` : ''}`;
}

export const normaliseSearch = (value: string) => value.normalize('NFKD').replace(/\p{Diacritic}/gu, '').toLowerCase();

interface SearchOptions {
  query: string;
  prefix: string;
  category: string;
  favoritesOnly: boolean;
  favorites: ReadonlySet<string>;
  localize: (text: string) => string;
}

export function findCommands(catalog: CommandCatalog, options: SearchOptions) {
  const entered = options.query.trim();
  const query = normaliseSearch(options.prefix && entered.startsWith(options.prefix) ? entered.slice(options.prefix.length) : entered);
  const terms = query.split(/\s+/).filter(Boolean);
  const rank = (command: SelfbotCommand) => {
    const names = [command.name, ...command.aliases];
    if (names.some(name => normaliseSearch(name) === query)) return 0;
    return names.some(name => normaliseSearch(name).startsWith(query)) ? 1 : 2;
  };
  return catalog.categories.filter(category => options.category === 'all' || category.id === options.category).map(category => ({
    ...category,
    commands: category.commands.filter(command => {
      if (options.favoritesOnly && !options.favorites.has(command.name)) return false;
      const text = normaliseSearch([category.id, category.title, options.localize(category.title), ...category.aliases,
        command.name, ...command.aliases, command.usage, options.localize(command.usage), command.description, options.localize(command.description),
        command.details, options.localize(command.details)].join(' '));
      return terms.every(term => text.includes(term));
    }).sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name)),
  })).filter(category => category.commands.length > 0);
}
