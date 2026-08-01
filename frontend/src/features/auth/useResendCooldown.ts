import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Countdown that gates the "resend code" button.
 *
 * Supabase rate-limits OTP sends hard, and a user who taps resend three times
 * locks themselves out for far longer than they would have waited. Showing the
 * remaining seconds is what stops that.
 */
export function useResendCooldown(seconds = 60) {
  const [remaining, setRemaining] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const clear = useCallback(() => {
    if (timer.current !== null) {
      clearInterval(timer.current)
      timer.current = null
    }
  }, [])

  const start = useCallback(() => {
    clear()
    setRemaining(seconds)
    timer.current = setInterval(() => {
      setRemaining((value) => {
        if (value <= 1) {
          clear()
          return 0
        }
        return value - 1
      })
    }, 1000)
  }, [clear, seconds])

  useEffect(() => clear, [clear])

  return { remaining, active: remaining > 0, start }
}
