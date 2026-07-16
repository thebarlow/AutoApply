// Mirrors core/pricing.py DEFAULT_PRICES — display only; the server is authoritative.
export const PRICES = {
  intake: 2,
  generate_fresh: 4,
  regenerate: 2,
  score: 1,
  extract: 1,
  resume_parse: 1,
  ats: 1,
  rematch: 1,
  draft: 1,
}

export const priceLabel = (action) =>
  PRICES[action] != null ? `${PRICES[action]}⚡` : ''
