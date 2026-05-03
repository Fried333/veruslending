// localStorage-backed position store.
// Each position is a JSON blob keyed by id.
//
// Long-lived state (templates, history) belongs in the user's own VerusID
// multimap (encrypted). This is just a fast cache for the dashboard.

const KEY = "vl.positions.v1";
const SETTINGS_KEY = "vl.settings.v1";

export function listPositions() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

export function getPosition(id) {
  return listPositions().find((p) => p.id === id) || null;
}

export function savePosition(p) {
  const all = listPositions();
  const i = all.findIndex((x) => x.id === p.id);
  const now = Date.now();
  const merged = { ...p, updated_at: now, created_at: p.created_at || now };
  if (i >= 0) all[i] = merged;
  else all.unshift(merged);
  localStorage.setItem(KEY, JSON.stringify(all));
  return merged;
}

export function deletePosition(id) {
  const all = listPositions().filter((p) => p.id !== id);
  localStorage.setItem(KEY, JSON.stringify(all));
}

export function getSettings() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
  } catch {
    return {};
  }
}

export function saveSettings(s) {
  const cur = getSettings();
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...cur, ...s }));
}
