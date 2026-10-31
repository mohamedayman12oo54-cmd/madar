// The date-time picker works in local "YYYY-MM-DDTHH:MM" strings; the API takes ISO instants.
export const toIso = (local) => new Date(local).toISOString();
export const toLocalInput = (iso) => {
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};
export const inHours = (h) => toLocalInput(new Date(Date.now() + h * 3600 * 1000).toISOString());
