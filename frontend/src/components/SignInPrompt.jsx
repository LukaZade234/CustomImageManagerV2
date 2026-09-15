import { useLocation } from 'react-router-dom'
import { signInUrl } from '../config'
import { Button } from './ui'

/**
 * Shown in place of an add-image control to a visitor who has not linked
 * Discord.
 *
 * Adding an image uploads it under the site's account, so it is tied to a real
 * account; everything else works from a cookie alone. This is the explanation,
 * not the enforcement — the endpoints refuse the upload regardless.
 */
export default function SignInPrompt({ className, note = 'to add images' }) {
  const { pathname } = useLocation()
  return (
    <span className={['sign-in-prompt', className].filter(Boolean).join(' ')}>
      <Button as="a" href={signInUrl(pathname)} size="sm" variant="secondary">
        Sign in with Discord
      </Button>
      <span className="sign-in-prompt__note text-meta">{note}</span>
    </span>
  )
}
