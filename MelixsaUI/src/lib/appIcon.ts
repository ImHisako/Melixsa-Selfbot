export type AppIcon = 'default' | 'egirl';
export const appIconStorageKey = 'melixsa.appIcon';
export const appIconAssets = {
  default: { src: '/mark.svg', type: 'image/svg+xml' },
  egirl: { src: '/icons/e-girl.png', type: 'image/png' },
} as const;

export function readAppIcon(storage: Pick<Storage, 'getItem'>): AppIcon {
  try {
    return storage.getItem(appIconStorageKey) === 'egirl' ? 'egirl' : 'default';
  } catch {
    return 'default';
  }
}
