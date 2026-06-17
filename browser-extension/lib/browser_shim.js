// browser-extension/lib/browser_shim.js
// Minimal cross-browser bridge. Firefox exposes promise-based `browser.*`;
// Chrome exposes callback-based `chrome.*`. We expose a promise API as `xb`.
(function (root) {
  const api = (typeof browser !== "undefined") ? browser : chrome;
  const isFirefox = (typeof browser !== "undefined");

  function promisify(fn, ctx) {
    return (...args) =>
      isFirefox
        ? fn.apply(ctx, args)
        : new Promise((resolve, reject) =>
            fn.call(ctx, ...args, (res) =>
              chrome.runtime.lastError ? reject(new Error(chrome.runtime.lastError.message)) : resolve(res)
            )
          );
  }

  root.xb = {
    storage: {
      local: {
        get: promisify(api.storage.local.get, api.storage.local),
        set: promisify(api.storage.local.set, api.storage.local),
        remove: promisify(api.storage.local.remove, api.storage.local),
      },
    },
    identity: {
      launchWebAuthFlow: promisify(api.identity.launchWebAuthFlow, api.identity),
      getRedirectURL: (...a) => api.identity.getRedirectURL(...a),
    },
    runtime: {
      sendMessage: promisify(api.runtime.sendMessage, api.runtime),
      onMessage: api.runtime.onMessage,
    },
  };
})(typeof self !== "undefined" ? self : window);
