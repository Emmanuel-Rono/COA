"""Automatic local demo sessions. Service keys stay on the server.

This is for a loopback-only workspace, not a replacement for hosted staff login.
"""
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit

from .errors import AppError

LIFETIME = 8 * 60 * 60


def same_origin(request):
    origin = request.headers.get('origin')
    return bool(origin and origin == str(request.base_url).rstrip('/'))


def session_value(settings, app_name):
    value = f'{int(time.time())}:{secrets.token_hex(16)}'
    return value + ':' + signature(value, settings, app_name)


def signature(value, settings, app_name):
    message = f'{app_name}:{settings.store_id}:{value}'.encode()
    return hmac.new(settings.api_token.encode(), message, hashlib.sha256).hexdigest()


def valid_session(cookie, settings, app_name):
    try:
        timestamp, nonce, supplied = cookie.split(':')
        age = time.time() - int(timestamp)
        return 0 <= age < LIFETIME and len(nonce) == 32 and hmac.compare_digest(
            supplied, signature(f'{timestamp}:{nonce}', settings, app_name))
    except (ValueError, AttributeError):
        return False


def require_local_browser(request, settings):
    host = urlsplit(str(request.base_url)).hostname
    peer = request.client.host if request.client else ''
    if (not settings.local_demo_access or host not in {'localhost', '127.0.0.1', '::1'}
            or peer not in {'127.0.0.1', '::1'} or not same_origin(request)):
        raise AppError('local_access_only', 'This workspace opens locally. Hosted access requires staff sign-in to be configured.', 403)
