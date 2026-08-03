// Static builds may override this to point at an independently secured API.
// The bundled web_lilith.py server is loopback-only and must not be exposed by
// a public tunnel or reverse proxy. Leave empty for same-origin requests.
window.API_BASE_URL = "";
