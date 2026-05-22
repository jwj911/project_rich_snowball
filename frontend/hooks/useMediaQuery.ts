import { useEffect, useState } from 'react'

export function useMediaQuery(query: string, defaultMatches = false) {
  const [matches, setMatches] = useState(() => getMatches(query, defaultMatches))

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      setMatches(defaultMatches)
      return
    }

    const mediaQuery = window.matchMedia(query)
    const handleChange = () => setMatches(mediaQuery.matches)
    handleChange()

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }

    mediaQuery.addListener(handleChange)
    return () => mediaQuery.removeListener(handleChange)
  }, [defaultMatches, query])

  return matches
}

function getMatches(query: string, defaultMatches: boolean) {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return defaultMatches
  }
  return window.matchMedia(query).matches
}
