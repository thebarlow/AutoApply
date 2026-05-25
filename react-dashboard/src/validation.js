export function validateProvider(p) {
  const errors = {}
  if (!p.api_key?.trim()) errors.api_key = 'API key is required'
  const model = p.default_model ?? p.model
  if (!model?.trim()) errors.model = 'Model is required'
  return errors
}

export function validatePrompt(p) {
  const errors = {}
  if (!p.name?.trim()) errors.name = 'Name is required'
  return errors
}
