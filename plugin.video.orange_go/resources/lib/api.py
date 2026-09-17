# -*- coding: utf-8 -*-
"""
Cała komunikacja z Orange GO: sesja, logowanie, kanały, EPG, resolve streamu + DRM.
Zero xbmcgui/xbmcplugin tutaj - tylko dane. UI/Kodi-specific rzeczy zostają
w addon.py (resolver) i service.py.
"""
import base64
import hashlib
import random
import time
from urllib.parse import urlencode, quote

import requests
import xbmc

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0'
BASE_URL = 'https://tvgo.orange.pl/'
API_URL = 'https://tvgo.orange.pl/gpapi2/'
API_URL_OLD = 'https://tvgo.orange.pl/gpapi/'
DEVICE_TYPE = 'web_otf'
DEVICE_CAT = 'otg'

TOKEN_REFRESH_AFTER = 24 * 60 * 60       # odśwież po 24h
TOKEN_EXPIRE_AFTER = 14 * 24 * 60 * 60   # refreshToken wygasa po 14 dniach


def _log(msg):
    xbmc.log('[orange_go] ' + msg, level=xbmc.LOGINFO)


class AuthError(Exception):
    pass


class OrangeGoClient:
    """Trzyma sesję (przez Store) i wystawia proste metody: login, get_channels, resolve_stream itd."""

    def __init__(self, store):
        self.store = store

    # ---------- nagłówki / cookies ----------

    def _device_info(self):
        data = {
            'dev_type': DEVICE_TYPE,
            'app_version': '1.21.1',
            'web_native': UA,
            'hh_tech': '',
            'serial_number': '',
            'offer': ''
        }
        if self.store.get_bool('logged'):
            data['hh_tech'] = self.store.get('hhTech')
            data['serial_number'] = 'FIREFOX_WEB_TERMINAL_1' + self.store.get('householdExtId')
        return urlencode(data)

    def _headers(self):
        return {
            'Origin': BASE_URL[:-1],
            'Referer': BASE_URL,
            'User-Agent': UA,
            'OtvDeviceInfo2': self._device_info(),
            'Accept': 'application/json;ver=1'
        }

    def _bootstrap_cookies(self):
        """
        Pobiera stronę główną i wyciąga ciastka I12 + AnalyticsData wymagane
        do przejścia przez podstawową weryfikację "przeglądarki".
        AnalyticsData powstaje z JS zaszytego w HTML - wykonujemy go lokalnie
        przez js2py. Jeśli się nie uda, NIE wysyłamy kodu do żadnego
        zewnętrznego serwisu (jak robił oryginał z w3schools) - to był
        niepotrzebny i kruchy hack. Po prostu logujemy błąd i jedziemy dalej
        bez tego ciastka; część requestów może wtedy dostać 403/412.
        """
        import re
        resp = requests.get(BASE_URL, headers={'User-Agent': UA}).text

        ci_match = re.compile(r'I12=([^;]+?);').findall(resp)
        ci = ci_match[0] if ci_match else ''

        ca = ''
        scripts = re.compile(r'<script>((?:(?!</script>).)*?)</script>').findall(resp)
        analytics_scripts = [s for s in scripts if 'AnalyticsData' in s]
        if analytics_scripts:
            code = re.sub(r'document\[([^]]+?)\]', 'var result', analytics_scripts[0])
            try:
                import js2py
                payload = 'function x(){%s\nreturn result}' % code
                x = js2py.eval_js(payload)
                cont = x()
                ca_match = re.compile(r'AnalyticsData=([^;]+?);').findall(cont)
                ca = ca_match[0] if ca_match else ''
            except Exception as e:
                _log('bootstrap_cookies: nie udało się wykonać JS lokalnie (%s)' % e)

        return ci, ca

    def _cookies(self):
        if self.store.get('ci') == '' or self.store.get('ca') == '':
            ci, ca = self._bootstrap_cookies()
            if ci:
                self.store.set('ci', ci)
            if ca:
                self.store.set('ca', ca)

        cookies = {
            'AnalyticsData': self.store.get('ca'),
            'I12': self.store.get('ci'),
        }
        if self.store.get_bool('logged'):
            cookies.update({
                'Token': self.store.get('Token'),
                'TokenId': self.store.get('TokenId'),
                'Authenticated': 'true',
            })
        return cookies

    @staticmethod
    def _params():
        return {'deviceCat': DEVICE_CAT}

    # ---------- auth ----------

    @staticmethod
    def _hash_pin(pin):
        salt = ('MDAxMTAxMDAgMDAxMTAwMTEgMDAxMTAxMTEgMDAxMTAxMTAgMDAxMTAxMTAg'
                'MDAxMTEwMTEgMDAxMTExMDAgMDAxMTAxMTEgMDAxMTAxMTE=')
        h1 = hashlib.sha384(pin.encode('utf-8')).hexdigest()
        return hashlib.sha384((h1 + salt).encode('utf-8')).hexdigest()

    def login(self):
        login = self.store.get('login')
        pin = self.store.get('pin')
        if not login or not pin:
            raise AuthError('Brak danych logowania w ustawieniach')

        hashed_pin = self._hash_pin(pin)

        url = API_URL + 'auth/login'
        params = self._params()
        params['deviceType'] = DEVICE_TYPE
        headers = self._headers()
        headers['Accept'] = 'application/json;ver=2'
        headers['Content-Type'] = 'application/json;ver=1'

        resp = requests.post(url, headers=headers, params=params,
                              cookies=self._cookies(),
                              json={'login': login, 'password': hashed_pin})

        cookies = dict(resp.cookies)
        if 'Token' not in cookies:
            raise AuthError('Logowanie odrzucone: ' + resp.text)

        self.store.set('Token', cookies['Token'])
        self.store.set('TokenId', cookies['TokenId'])
        self.store.set('refreshToken', resp.json()['refreshToken'])
        self.store.set('tokenTime', str(int(time.time())))

        hh_url = API_URL + 'core/household/household'
        hh_cookies = self._cookies()
        hh_cookies['Token'] = self.store.get('Token')
        hh_cookies['TokenId'] = self.store.get('TokenId')
        hh_resp = requests.get(hh_url, headers=self._headers(), params=self._params(),
                                cookies=hh_cookies).json()
        if 'householdExtId' not in hh_resp:
            raise AuthError('Nie udało się pobrać danych household: ' + str(hh_resp))

        self.store.set('householdExtId', hh_resp['householdExtId'])
        self.store.set('hhTech', hh_resp['hhTech'])
        self.store.set('logged', 'true')
        _log('login: zalogowano')

    def logout(self):
        url = API_URL + 'auth/logout'
        resp = requests.get(url, headers=self._headers(), cookies=self._cookies(),
                             params=self._params())
        self._clear_session()
        _log('logout: status %s' % resp.status_code)

    def _clear_session(self):
        for key in ('logged', 'Token', 'TokenId', 'refreshToken', 'tokenTime',
                    'householdExtId', 'hhTech', 'prevC'):
            self.store.set(key, '' if key != 'logged' else 'false')

    def ensure_logged_in(self):
        """Loguje / odświeża token w razie potrzeby. Rzuca AuthError jeśli się nie uda."""
        if not self.store.get_bool('logged'):
            self.login()
            return

        now = int(time.time())
        token_time = self.store.get_int('tokenTime', 0)
        age = now - token_time

        if age >= TOKEN_EXPIRE_AFTER:
            _log('ensure_logged_in: refreshToken wygasł, relogin')
            self._clear_session()
            self.login()
            return

        if age >= TOKEN_REFRESH_AFTER:
            url = API_URL + 'auth/refresh'
            headers = self._headers()
            headers['Content-Type'] = 'application/json;ver=1'
            resp = requests.post(url, headers=headers, cookies=self._cookies(),
                                  params=self._params(),
                                  json={'refreshToken': self.store.get('refreshToken')})
            cookies = dict(resp.cookies)
            if 'Token' in cookies:
                self.store.set('Token', cookies['Token'])
                self.store.set('TokenId', cookies['TokenId'])
                self.store.set('refreshToken', resp.json()['refreshToken'])
                self.store.set('tokenTime', str(now))
                _log('ensure_logged_in: token odświeżony')
            else:
                _log('ensure_logged_in: refresh nieudany, relogin (%s)' % resp.text)
                self._clear_session()
                self.login()

    # ---------- kanały / EPG ----------

    def get_channels(self):
        """Zwraca listę surowych dictów kanałów, tylko subskrybowane."""
        url = API_URL + 'live/channel/all'
        resp = requests.get(url, headers=self._headers(), cookies=self._cookies(),
                             params=self._params()).json()
        if 'channelList' not in resp:
            _log('get_channels: brak channelList w odpowiedzi: %s' % str(resp)[:300])
            return []
        return [c for c in resp['channelList'] if c.get('isSubscribed')]

    def get_epg(self, date_yyyy_mm_dd):
        """EPG dla danego dnia (i dnia poprzedniego, bo API tak zwraca). Surowy dict z API."""
        import datetime
        url = API_URL + 'core/tvguide/epg'
        d1 = datetime.datetime.strptime(date_yyyy_mm_dd + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
        d0 = d1 - datetime.timedelta(days=1)

        epg = {}
        for d in (d0, d1):
            ts = str(int(d.timestamp()))
            params = self._params()
            params['date'] = ts
            resp = requests.get(url, headers=self._headers(), cookies=self._cookies(),
                                 params=params).json()
            epg[ts] = resp.get('guide', {})
        return epg

    # ---------- odtwarzanie ----------

    def _register_terminal(self):
        url = API_URL + 'core/device/register'
        headers = self._headers()
        headers['Content-Type'] = 'application/json;ver=1'
        data = {
            'deviceManufacture': 'web',
            'deviceModel': 'web',
            'deviceType': DEVICE_TYPE,
            'name': 'FIREFOX',
            'serialNumber': 'FIREFOX_WEB_TERMINAL_1' + self.store.get('householdExtId'),
        }
        return requests.post(url, headers=headers, cookies=self._cookies(),
                              params=self._params(), json=data)

    def _delete_session(self, cid):
        url = API_URL + 'live/channel/' + cid + '/session'
        resp = requests.delete(url, headers=self._headers(), cookies=self._cookies(),
                                params=self._params())
        _log('delete_session(%s): %s' % (cid, resp.status_code))

    def resolve_stream(self, cid, pid=None, is_catchup=False, ts=None, te=None, tvreg=None):
        """
        Zwraca dict:
            {'stream_url', 'license_url', 'license_headers', 'server_certificate_b64'}
        albo None jeśli się nie udało (przyczyna trafia do logu).
        """
        prev_c = self.store.get('prevC')
        if prev_c:
            self._delete_session(prev_c)

        url = API_URL + 'live/channel/' + cid
        if is_catchup:
            url += '/' + pid + '/catchup'

        resp = requests.get(url, headers=self._headers(), cookies=self._cookies(),
                             params=self._params())

        if resp.status_code == 412:
            reg = self._register_terminal()
            if reg.status_code != 200:
                _log('resolve_stream: rejestracja terminala nieudana: %s' % reg.text)
                return None
            resp = requests.get(url, headers=self._headers(), cookies=self._cookies(),
                                 params=self._params())
            if resp.status_code == 412:
                _log('resolve_stream: sesja nadal odrzucona po rejestracji: %s' % resp.text)
                return None

        data = resp.json()
        if 'casToken' not in data:
            _log('resolve_stream: brak casToken w odpowiedzi: %s' % str(data)[:300])
            return None

        self.store.set('prevC', cid)
        cas_token = data['casToken']
        stream_url = data['streamUrl']

        # TVP3 regionalizacja
        if cid == '14215' and tvreg:
            url_reg = API_URL + 'live/regional-tv/all'
            resp_reg = requests.get(url_reg, headers=self._headers(), cookies=self._cookies(),
                                     params=self._params()).json()
            packages = resp_reg.get('regionalTvPackageList', [])
            matches = [p['regionalTvList'] for p in packages if p.get('channelExtId') == cid]
            if matches:
                variants = [v for v in matches[0] if tvreg in v['channelName']]
                if variants:
                    stream_url = stream_url.replace(cid, cid + variants[0]['liveUrlSuffix'])

        if is_catchup and ts is not None and te is not None:
            stream_url += '&begin=%s&end=%s' % (int(ts), int(te))

        cert_resp = requests.get(
            'https://cps.purpledrm.com/wv_certificate/cert_license_widevine_com.bin',
            headers={'User-Agent': UA, 'Origin': BASE_URL[:-1], 'Referer': BASE_URL}
        ).content
        cert_b64 = base64.b64encode(cert_resp).decode('utf-8')

        lic_url = BASE_URL + 'RTEFacade_RIGHTV/widevinedrm?token=' + quote(cas_token)
        lic_headers = {'User-Agent': UA, 'Origin': BASE_URL[:-1], 'Referer': BASE_URL}
        cookies = self._cookies()
        lic_headers['Cookie'] = '; '.join('%s=%s' % (k, v) for k, v in cookies.items())

        return {
            'stream_url': stream_url,
            'license_url': lic_url,
            'license_headers': lic_headers,
            'server_certificate_b64': cert_b64,
        }
