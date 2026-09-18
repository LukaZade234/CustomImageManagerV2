/**
 * The API client's request contract.
 *
 * `api()` passes `options` straight to `fetch`, so it does not add a
 * `Content-Type` of its own -- every JSON caller must set it. That is a sharp
 * edge: forget it and the server's `request.get_json(silent=True)` returns
 * None, so the route sees an empty body and fails validation with a confusing
 * message rather than a clear "wrong content type".
 *
 * It bit the ownership-claim endpoints exactly that way, and the component
 * tests could not catch it because they mock the api client wholesale. These
 * tests call the real module against a stubbed `fetch`, which is the only place
 * the header is visible.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from './api'

let calls

beforeEach(() => {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options = {}) => {
      calls.push({ url, options })
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      }
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function lastCall() {
  return calls[calls.length - 1]
}

describe('json request bodies', () => {
  // Every client method that sends a JSON body, so a new one cannot be added
  // without a header and go unnoticed the way claimCharacter did.
  const jsonPosts = {
    claimCharacter: () => apiClient.claimCharacter('Rem'),
    decideModerationClaim: () => apiClient.decideModerationClaim(7, { approve: true, reason: '' }),
  }

  for (const [name, invoke] of Object.entries(jsonPosts)) {
    it(`${name} sends JSON so the server can read it`, async () => {
      await invoke()
      const { options } = lastCall()
      expect(options.method).toBe('POST')
      expect(options.headers['Content-Type']).toBe('application/json')
      // The body has to be parseable, or the header would be a lie.
      expect(() => JSON.parse(options.body)).not.toThrow()
    })
  }

  it('claimCharacter sends the character name', async () => {
    await apiClient.claimCharacter('Rem')
    expect(JSON.parse(lastCall().options.body)).toEqual({ character_name: 'Rem' })
  })

  it('decideModerationClaim sends the decision and reason', async () => {
    await apiClient.decideModerationClaim(7, { approve: false, reason: 'not yours' })
    expect(JSON.parse(lastCall().options.body)).toEqual({ approve: false, reason: 'not yours' })
  })

  it('approve-all sends no body, so it needs no content type', async () => {
    await apiClient.approveAllModerationClaims('ref-ada')
    expect(lastCall().options.method).toBe('POST')
    expect(lastCall().options.body).toBeUndefined()
  })
})
