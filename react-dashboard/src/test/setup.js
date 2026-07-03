import '@testing-library/jest-dom'

// Mock IntersectionObserver for framer-motion whileInView
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  takeRecords() {
    return []
  }
  unobserve() {}
}
