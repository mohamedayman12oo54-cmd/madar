// A promise that never settles (a stalled network call, a service worker that never became ready) must not be
// able to freeze an action the user needs — above all signing out. `withTimeout` gives up waiting after `ms`.

/** Resolves with `promise`'s value, or with `fallback` (default undefined) once `ms` have passed. Never rejects
 *  because of the timeout; a rejection of `promise` itself still rejects. */
export const withTimeout = (promise, ms, fallback = undefined) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve(fallback), ms);
    Promise.resolve(promise).then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      }
    );
  });
