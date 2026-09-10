/**
 * Adding images, from a picker, a file drop, or a web drag.
 *
 * What matters here is failure behaviour, which is easy to get wrong and hard to
 * notice: a batch where some files fail must still add the rest, the lock must
 * be released whatever happens, and a second upload must not start on top of a
 * running one.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { addCustomImage, importCustomImagesFromUrls } = vi.hoisted(() => ({
  addCustomImage: vi.fn(),
  importCustomImagesFromUrls: vi.fn(),
}))

vi.mock('../api', () => ({
  apiClient: { addCustomImage, importCustomImagesFromUrls },
}))

import { useCustomImageUpload } from './useCustomImageUpload'

const file = (name = 'a.png', size = 1000) => ({
  name,
  size,
  type: 'image/png',
  lastModified: size,
})

function setup() {
  const addToast = vi.fn()
  const onUploaded = vi.fn().mockResolvedValue(undefined)
  const view = renderHook(() =>
    useCustomImageUpload({
      characterName: 'Rem',
      onUploaded,
      addToast,
      fileInputRef: { current: null },
    }),
  )
  return { view, addToast, onUploaded }
}

beforeEach(() => {
  addCustomImage.mockReset().mockResolvedValue({ links: ['https://cdn/a.png'] })
  importCustomImagesFromUrls.mockReset().mockResolvedValue({ links: ['https://cdn/b.png'] })
})

describe('uploading files', () => {
  it('sends each file and merges the new URLs', async () => {
    const { view, onUploaded } = setup()
    await act(async () => {
      await view.result.current.onFileInputChange({ target: { files: [file('a.png')] } })
    })
    expect(addCustomImage).toHaveBeenCalledTimes(1)
    expect(onUploaded).toHaveBeenCalledWith('Rem', ['https://cdn/a.png'])
  })

  it('keeps going when one file fails, and still adds the others', async () => {
    addCustomImage
      .mockRejectedValueOnce(new Error('ImgChest said no'))
      .mockResolvedValueOnce({ links: ['https://cdn/b.png'] })
    const { view, onUploaded } = setup()
    await act(async () => {
      await view.result.current.onFileInputChange({
        target: { files: [file('a.png'), file('b.png', 2000)] },
      })
    })
    expect(onUploaded).toHaveBeenCalledWith('Rem', ['https://cdn/b.png'])
  })

  it('collects failures into one copyable report rather than a wall of toasts', async () => {
    addCustomImage.mockRejectedValue(new Error('ImgChest said no'))
    const { view } = setup()
    await act(async () => {
      await view.result.current.onFileInputChange({ target: { files: [file('a.png')] } })
    })
    await waitFor(() => expect(view.result.current.errorReport).toContain('ImgChest said no'))
    expect(view.result.current.errorReport).toContain('a.png')
  })

  it('dismisses the report', async () => {
    addCustomImage.mockRejectedValue(new Error('nope'))
    const { view } = setup()
    await act(async () => {
      await view.result.current.onFileInputChange({ target: { files: [file('a.png')] } })
    })
    act(() => view.result.current.dismissErrorReport())
    expect(view.result.current.errorReport).toBeNull()
  })

  it('rejects a file over the size limit without calling the API', async () => {
    const { view } = setup()
    await act(async () => {
      await view.result.current.onFileInputChange({
        target: { files: [file('huge.png', 40 * 1024 * 1024)] },
      })
    })
    expect(addCustomImage).not.toHaveBeenCalled()
  })

  it('clears progress once finished, whatever happened', async () => {
    addCustomImage.mockRejectedValue(new Error('nope'))
    const { view } = setup()
    await act(async () => {
      await view.result.current.onFileInputChange({ target: { files: [file('a.png')] } })
    })
    expect(view.result.current.progress).toBeNull()
  })

  it('ignores a picker that yields no files', async () => {
    const { view } = setup()
    await act(async () => {
      await view.result.current.onFileInputChange({ target: { files: [] } })
    })
    expect(addCustomImage).not.toHaveBeenCalled()
  })
})

describe('dropping', () => {
  const dropEvent = (files = [], uriList = '') => ({
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
    dataTransfer: {
      files,
      types: files.length ? ['Files'] : ['text/uri-list'],
      getData: () => uriList,
      items: [],
    },
  })

  it('uploads dropped files', async () => {
    const { view } = setup()
    await act(async () => {
      await view.result.current.onDrop(dropEvent([file('a.png')]))
    })
    expect(addCustomImage).toHaveBeenCalled()
  })

  it('imports an image dragged in from a web page', async () => {
    const { view } = setup()
    await act(async () => {
      await view.result.current.onDrop(dropEvent([], 'https://example.com/pic.png'))
    })
    expect(importCustomImagesFromUrls).toHaveBeenCalledWith('Rem', ['https://example.com/pic.png'])
  })

  it('says something useful when the drop was not an image', async () => {
    const { addToast, view } = setup()
    await act(async () => {
      await view.result.current.onDrop(
        dropEvent([{ name: 'notes.txt', size: 1, type: 'text/plain' }]),
      )
    })
    expect(addToast).toHaveBeenCalledWith(expect.stringContaining('image files only'), 'info')
  })

  it('tracks drag-over state so the drop zone can highlight', () => {
    const { view } = setup()
    act(() =>
      view.result.current.onDragOver({
        preventDefault: vi.fn(),
        dataTransfer: { dropEffect: '' },
      }),
    )
    expect(view.result.current.dragOver).toBe(true)
  })
})
