import { afterEach, describe, expect, it, vi } from 'vitest'

/**
 * These pin the deployment contract. Getting any of it wrong fails quietly in
 * production rather than loudly: the wrong credentials mode means cookies are
 * silently not sent, so every visitor looks like a new person instead of
 * producing an error.
 */

async function loadConfig(env = {}) {
  vi.resetModules()
  for (const [k, v] of Object.entries(env)) vi.stubEnv(k, v)
  return import('./config.js')
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('credentials mode', () => {
  it("is 'include', so cookies survive the move to a separate API origin", async () => {
    const { CREDENTIALS } = await loadConfig()
    expect(CREDENTIALS).toBe('include')
  })
})

describe('API_BASE', () => {
  it('is empty when unset, keeping requests same-origin for local dev', async () => {
    const { API_BASE, IS_CROSS_ORIGIN } = await loadConfig({ VITE_API_BASE_URL: '' })
    expect(API_BASE).toBe('')
    expect(IS_CROSS_ORIGIN).toBe(false)
  })

  it('is used when set, and a trailing slash does not produce a double slash', async () => {
    const { apiUrl, IS_CROSS_ORIGIN } = await loadConfig({
      VITE_API_BASE_URL: 'https://api.example.com/',
    })
    expect(apiUrl('/api/saved')).toBe('https://api.example.com/api/saved')
    expect(IS_CROSS_ORIGIN).toBe(true)
  })
})

describe('imageUrl', () => {
  it('passes absolute URLs through untouched (ImgChest links)', async () => {
    const { imageUrl } = await loadConfig({ VITE_IMAGE_BASE_URL: 'https://img.example.com' })
    expect(imageUrl('https://cdn.imgchest.com/files/a.png')).toBe(
      'https://cdn.imgchest.com/files/a.png',
    )
    expect(imageUrl('//cdn.example/a.png')).toBe('//cdn.example/a.png')
  })

  it('prefixes stored filenames with the configured image origin', async () => {
    const { imageUrl } = await loadConfig({ VITE_IMAGE_BASE_URL: 'https://img.example.com' })
    expect(imageUrl('Zero_Two.png')).toBe('https://img.example.com/character_images/Zero_Two.png')
  })

  it('falls back to a same-origin path when no image origin is set', async () => {
    const { imageUrl } = await loadConfig({ VITE_IMAGE_BASE_URL: '' })
    expect(imageUrl('Zero_Two.png')).toBe('/character_images/Zero_Two.png')
  })

  it('returns empty for empty input rather than a broken URL', async () => {
    const { imageUrl } = await loadConfig()
    expect(imageUrl('')).toBe('')
    expect(imageUrl(undefined)).toBe('')
  })
})
