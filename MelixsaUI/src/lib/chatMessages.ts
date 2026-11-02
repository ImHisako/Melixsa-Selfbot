import type { ChatMessage } from '../types';

export function mergeMessages(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const messages = new Map(current.map(item => [item.id, item]));
  incoming.forEach(item => messages.set(item.id, item));
  return [...messages.values()].sort((a, b) => a.id - b.id);
}

// Replace the newest window so edits and deletions are reflected, preserving older pages.
export function syncLatest(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  if (!incoming.length) return [];
  const oldest = Math.min(...incoming.map(item => item.id));
  return mergeMessages(current.filter(item => item.id < oldest), incoming);
}
