import { useCallback, useState } from 'react'
import { apiClient } from '../api'
import { isImageFileLike } from '../utils/imageFiles'

/**
 * The character's main portrait: replacing it by file, dragged in, or refreshed
 * from Mudae.
 *
 * Split out of `CharacterPage` as the last of #3's extractions. `dragOver` here
 * is the portrait's own drop highlight, separate from the gallery's upload drop
 * zone. The sign-in rule is checked before anything is read or sent, so a
 * cookie-only visitor gets a toast rather than a failed request.
 */
export function useMainImage({ name, canAddImages, onChanged, onMudaeRefresh, addToast }) {
  const [dragOver, setDragOver] = useState(false)
  const [mudaeBusy, setMudaeBusy] = useState(false)
  const [uploading, setUploading] = useState(false)

  const upload = useCallback(
    async (file) => {
      if (!file || !isImageFileLike(file)) return
      if (!canAddImages) {
        addToast('Sign in with Discord to change the main image', 'error')
        return
      }
      const fd = new FormData()
      fd.append('file', file)
      fd.append('character_name', name)
      setUploading(true)
      try {
        const res = await apiClient.setMainImage(fd)
        onChanged(res.image_url)
        addToast('Main image updated', 'success')
      } catch (err) {
        addToast(err.message, 'error')
      } finally {
        setUploading(false)
      }
    },
    [name, canAddImages, onChanged, addToast],
  )

  const onFileInputChange = useCallback(
    (event) => {
      const file = event.target.files?.[0]
      // Clear the input so choosing the same file again still fires a change.
      event.target.value = ''
      upload(file)
    },
    [upload],
  )

  const onDrop = useCallback(
    (event) => {
      event.preventDefault()
      setDragOver(false)
      upload(event.dataTransfer.files?.[0])
    },
    [upload],
  )

  const refreshFromMudae = useCallback(async () => {
    if (!name || mudaeBusy) return
    setMudaeBusy(true)
    try {
      await onMudaeRefresh()
    } finally {
      setMudaeBusy(false)
    }
  }, [name, mudaeBusy, onMudaeRefresh])

  return {
    dragOver,
    setDragOver,
    uploading,
    mudaeBusy,
    onFileInputChange,
    onDrop,
    refreshFromMudae,
  }
}
