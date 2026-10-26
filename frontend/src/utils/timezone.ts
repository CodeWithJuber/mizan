/** The browser's IANA timezone, so MIZAN states dates in the user's own day. */
export function browserTimeZone(
  resolve: () => string | undefined = () => Intl.DateTimeFormat().resolvedOptions().timeZone,
): string | undefined {
  try {
    const zone = resolve();
    return zone && /^[A-Za-z0-9_+\-/]{1,64}$/.test(zone) ? zone : undefined;
  } catch {
    return undefined;
  }
}

/** Request-body fields for the timezone, empty when the browser does not report one. */
export function timeZoneField(zone: string | null | undefined = browserTimeZone()): { timezone?: string } {
  return zone ? { timezone: zone } : {};
}
