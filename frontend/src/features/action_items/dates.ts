/**
 * Bridging `<input type="date">` (a calendar day) and the API (a UTC instant).
 */

/** API timestamp -> the YYYY-MM-DD a date input expects. */
export function toDateInput(value: string | null): string {
  return value ? value.slice(0, 10) : ''
}

/**
 * A picked day -> a timestamp.
 *
 * Anchored to 17:00 local rather than midnight: "due Friday" means by the end
 * of Friday, and midnight would mark it overdue for the whole working day.
 */
export function fromDateInput(value: string): string | null {
  if (!value) return null
  return new Date(`${value}T17:00:00`).toISOString()
}
