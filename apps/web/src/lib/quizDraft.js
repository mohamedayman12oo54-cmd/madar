// In-progress quiz answers, kept in sessionStorage so an accidental refresh does not lose them.
//
// This is the ONLY module besides lib/parentApi.js allowed to touch sessionStorage (enforced by
// lib/security.static.test.mjs). What lives here is a list of answer indexes — never a token or any
// personal data — and it is wiped on sign-out so a shared device does not keep a previous student's
// half-finished answers. Storage can be unavailable (private mode, blocked site data), so every access
// is guarded and a failure just means "no draft".
const PREFIX = "madar.quiz.draft.";
const draftKey = (id) => `${PREFIX}${id}`;

export function readDraft(id, length) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(draftKey(id)) || "null");
    if (Array.isArray(saved) && saved.length === length) return saved;
  } catch {
    /* an unreadable draft is simply ignored */
  }
  return null;
}

export function writeDraft(id, answers) {
  try {
    if (answers.every((a) => a === null)) sessionStorage.removeItem(draftKey(id));
    else sessionStorage.setItem(draftKey(id), JSON.stringify(answers));
  } catch {
    /* in-progress answers are a convenience only */
  }
}

export function clearDraft(id) {
  try {
    sessionStorage.removeItem(draftKey(id));
  } catch {
    /* nothing to clear */
  }
}

/** Remove every draft (called on sign-out). */
export function clearAllDrafts() {
  try {
    const stale = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key && key.startsWith(PREFIX)) stale.push(key);
    }
    stale.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    /* nothing to clear */
  }
}
