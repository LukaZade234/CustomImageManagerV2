import { describe, expect, it } from 'vitest'
import { dataTransferIsFileDrag, dedupeFilesByIdentity, isImageFileLike } from './imageFiles'

describe('isImageFileLike', () => {
  it('accepts a proper MIME type', () => {
    expect(isImageFileLike({ type: 'image/png', name: 'x' })).toBe(true)
  })

  it('accepts an image extension when the OS gave no MIME type', () => {
    // Linux drags routinely arrive with an empty type.
    expect(isImageFileLike({ type: '', name: 'art.webp' })).toBe(true)
  })

  it('rejects a non-image', () => {
    expect(isImageFileLike({ type: 'text/plain', name: 'notes.txt' })).toBe(false)
  })

  it('rejects nothing at all', () => {
    expect(isImageFileLike(null)).toBe(false)
  })
})

describe('dataTransferIsFileDrag', () => {
  it('handles a DOMStringList, which has contains but not includes', () => {
    const types = { contains: (t) => t === 'Files' }
    expect(dataTransferIsFileDrag({ types })).toBe(true)
  })

  it('handles a plain array of types', () => {
    expect(dataTransferIsFileDrag({ types: ['Files'] })).toBe(true)
  })

  it('recognises the Firefox-specific type', () => {
    expect(dataTransferIsFileDrag({ types: ['application/x-moz-file'] })).toBe(true)
  })

  it('falls back to inspecting items', () => {
    expect(dataTransferIsFileDrag({ types: [], items: [{ kind: 'file' }] })).toBe(true)
  })

  it('is false for a dragged web image rather than a file', () => {
    expect(dataTransferIsFileDrag({ types: ['text/uri-list'], items: [{ kind: 'string' }] })).toBe(
      false,
    )
  })

  it('never throws on a hostile object', () => {
    expect(
      dataTransferIsFileDrag({
        get types() {
          throw new Error('nope')
        },
      }),
    ).toBe(false)
  })
})

describe('dedupeFilesByIdentity', () => {
  it('drops a file listed twice in one drop', () => {
    const f = { name: 'a.png', size: 10, lastModified: 1 }
    expect(dedupeFilesByIdentity([f, { ...f }])).toHaveLength(1)
  })

  it('keeps files that only share a name', () => {
    const a = { name: 'a.png', size: 10, lastModified: 1 }
    const b = { name: 'a.png', size: 20, lastModified: 2 }
    expect(dedupeFilesByIdentity([a, b])).toHaveLength(2)
  })
})
