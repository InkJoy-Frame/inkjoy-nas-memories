/* Seal same-origin JSON bodies before they leave the browser.
   tweetnacl 1.0.3 (nacl.min.js) works on http://<lan-ip>, where Web Crypto is unavailable.
   HTTPS already encrypts the request, so this layer stays off there. */
(function () {
  var pageIsHttps = window.location.protocol === 'https:';

  function u8ToB64(u8) {
    var s = '';
    for (var i = 0; i < u8.length; i += 0x8000) {
      s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    }
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  }

  function b64ToU8(value) {
    var s = String(value).replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    var bin = atob(s);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function cacheKeyBytes(create) {
    var existing = null;
    try { existing = sessionStorage.getItem('inkjoy_cache_key'); } catch (e) { return null; }
    if (existing) return b64ToU8(existing);
    if (!create) return null;
    var key = nacl.randomBytes(nacl.secretbox.keyLength);
    try { sessionStorage.setItem('inkjoy_cache_key', u8ToB64(key)); } catch (e) { return null; }
    return key;
  }

  if (window.nacl && window.TextEncoder) {
    window.inkjoySealJson = function (obj) {
      var key = cacheKeyBytes(true);
      if (!key) return '';
      var nonce = nacl.randomBytes(nacl.secretbox.nonceLength);
      var boxed = nacl.secretbox(new TextEncoder().encode(JSON.stringify(obj)), nonce, key);
      return JSON.stringify({ v: 1, n: u8ToB64(nonce), c: u8ToB64(boxed) });
    };

    window.inkjoyOpenJson = function (text) {
      var key = cacheKeyBytes(false);
      if (!key) return null;
      var env;
      try { env = JSON.parse(text); } catch (e) { return null; }
      if (!env || env.v !== 1 || !env.c || !env.n) return null;
      var opened = nacl.secretbox.open(b64ToU8(env.c), b64ToU8(env.n), key);
      if (!opened) return null;
      return JSON.parse(new TextDecoder().decode(opened));
    };
  }

  if (pageIsHttps) return;

  if (!window.nacl || !window.INKJOY_BOX_PK || !window.TextEncoder) {
    window.fetch = function () {
      return Promise.reject(new Error('secure transport unavailable'));
    };
    return;
  }

  var serverPk = b64ToU8(window.INKJOY_BOX_PK);
  var pageKp = nacl.box.keyPair();
  var nativeFetch = window.fetch.bind(window);

  document.cookie = 'inkjoy_box_pk=' + u8ToB64(pageKp.publicKey) + '; path=/; SameSite=Lax';

  function isAppRequest(input) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    if (!url || url.charAt(0) === '/') return true;
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  function seal(obj) {
    var nonce = nacl.randomBytes(nacl.box.nonceLength);
    var msg = new TextEncoder().encode(JSON.stringify(obj));
    var boxed = nacl.box(msg, nonce, serverPk, pageKp.secretKey);
    return {
      v: 1,
      pk: u8ToB64(pageKp.publicKey),
      n: u8ToB64(nonce),
      c: u8ToB64(boxed),
    };
  }

  function prepare(input, init) {
    var next = init ? Object.assign({}, init) : {};
    var headers = new Headers(next.headers || {});
    headers.set('X-Inkjoy-Pk', u8ToB64(pageKp.publicKey));

    if (next.body instanceof FormData) {
      var src = next.body;
      var fd = new FormData();
      src.forEach(function (value, key) {
        if (key !== 'device_id' && key !== 'email' && key !== 'password' && key !== 'deviceId') {
          fd.append(key, value);
        }
      });
      var secret = {};
      ['device_id', 'deviceId', 'email', 'password'].forEach(function (key) {
        if (src.has(key)) secret[key] = String(src.get(key));
      });
      if (Object.keys(secret).length) {
        fd.append('payload', JSON.stringify(seal(secret)));
      }
      next.body = fd;
      headers.delete('Content-Type');
    } else if (typeof next.body === 'string' && next.body.charAt(0) === '{') {
      next.body = JSON.stringify(seal(JSON.parse(next.body)));
      headers.set('Content-Type', 'application/json');
    }

    next.headers = headers;
    return { input: input, init: next };
  }

  function openResponse(resp) {
    var ctype = resp.headers.get('content-type') || '';
    if (ctype.indexOf('json') === -1) return Promise.resolve(resp);
    return resp.text().then(function (text) {
      var data;
      try { data = JSON.parse(text); } catch (e) { data = null; }
      if (!data || data.v !== 1 || !data.c || !data.n) {
        return new Response(text, {
          status: resp.status,
          statusText: resp.statusText,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      var opened = nacl.box.open(b64ToU8(data.c), b64ToU8(data.n), serverPk, pageKp.secretKey);
      if (!opened) {
        return new Response(JSON.stringify({ success: false, error: 'decrypt failed' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(new TextDecoder().decode(opened), {
        status: resp.status,
        statusText: resp.statusText,
        headers: { 'Content-Type': 'application/json' },
      });
    });
  }

  window.fetch = function (input, init) {
    if (!isAppRequest(input)) return nativeFetch(input, init);
    var prepared = prepare(input, init);
    return nativeFetch(prepared.input, prepared.init).then(function (resp) {
      return openResponse(resp);
    });
  };
})();
