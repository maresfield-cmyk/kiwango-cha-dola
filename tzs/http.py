"""Small HTTP layer: retries with backoff, optional cookie jar."""
import http.cookiejar
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")


class FetchError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


def opener(cookies=False):
    handlers = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())] if cookies else []
    return urllib.request.build_opener(*handlers)


def fetch(url, data=None, op=None, retries=3, timeout=30, headers=None):
    op = op or urllib.request.build_opener()
    hdr = {"User-Agent": UA, "Accept-Encoding": "identity"}
    hdr.update(headers or {})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdr)
            with op.open(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = FetchError(f"HTTP {e.code} for {url}", e.code)
            if e.code < 500 and e.code != 429:
                raise last
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = FetchError(f"{type(e).__name__}: {e} for {url}")
        time.sleep(2 * (attempt + 1))
    raise last
