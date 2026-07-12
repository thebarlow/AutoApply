// Server statuses: 'applied' | 'scraped' | 'none'. Client overlay: viewed.
// Precedence (highest wins): applied > scraped > viewed > none.
export function effectiveStatus(serverStatus, viewed) {
  if (serverStatus === 'applied') return 'applied'
  if (serverStatus === 'scraped') return 'scraped'
  if (viewed) return 'viewed'
  return 'none'
}

export const BORDER_CLASS = {
  applied: 'border-green-500/60',
  scraped: 'border-yellow-500/60',
  viewed: 'border-gray-500/60',
  none: 'border-blue-500/60',
}
