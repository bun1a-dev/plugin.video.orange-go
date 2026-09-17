# -*- coding: utf-8 -*-
"""
Resolver wywoływany przez PVR IPTV Simple Client (plugin://plugin.video.orange_go?mode=play...).
Nie ma tu żadnego menu/przeglądania - jedyne zadanie to zwrócić setResolvedUrl.

Oczekiwane parametry:
  mode=play&cid=<channelExtId>                         -> live
  mode=play&cid=<channelExtId>&s=<...>&e=<...>          -> catchup (czasy doklejone
                                                            przez catchup-source z M3U)
  mode=refresh_now                                       -> wymuszenie jednego cyklu service (z Ustawień)
"""
import os
import sys
from urllib.parse import parse_qsl

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'resources', 'lib'))
from store import Store            # noqa: E402
from api import OrangeGoClient, AuthError  # noqa: E402
from writers import find_pid_for_catchup  # noqa: E402

addon_handle = int(sys.argv[1])
params = dict(parse_qsl(sys.argv[2][1:]))
addon = xbmcaddon.Addon(id='plugin.video.orange_go')


def _notify(msg):
    xbmcgui.Dialog().notification('Orange Go', msg, xbmcgui.NOTIFICATION_INFO)


def _fail():
    xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())


def _play_via_inputstream(resolved):
    import inputstreamhelper
    helper = inputstreamhelper.Helper('mpd', drm='com.widevine.alpha')
    if not helper.check_inputstream():
        _notify('Brak wsparcia InputStream Adaptive/Widevine')
        _fail()
        return

    item = xbmcgui.ListItem(path=resolved['stream_url'])
    item.setMimeType('application/xml+dash')
    item.setContentLookup(False)
    item.setProperty('inputstream', helper.inputstream_addon)
    item.setProperty('IsPlayable', 'true')
    item.setProperty('inputstream.adaptive.manifest_type', 'mpd')

    from urllib.parse import urlencode
    from api import UA, BASE_URL
    basic_headers = urlencode({'User-Agent': UA, 'Origin': BASE_URL[:-1]})
    item.setProperty('inputstream.adaptive.stream_headers', basic_headers)
    item.setProperty('inputstream.adaptive.manifest_headers', basic_headers)

    kodi_major = int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0])
    if kodi_major < 22:
        lic_key = '%s|%s|R{SSM}|' % (resolved['license_url'], urlencode(resolved['license_headers']))
        item.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
        item.setProperty('inputstream.adaptive.license_key', lic_key)
        item.setProperty('inputstream.adaptive.server_certificate', resolved['server_certificate_b64'])
    else:
        import json
        drm_conf = {
            'com.widevine.alpha': {
                'license': {
                    'server_url': resolved['license_url'],
                    'req_headers': urlencode(resolved['license_headers']),
                    'server_certificate': resolved['server_certificate_b64'],
                }
            }
        }
        item.setProperty('inputstream.adaptive.drm', json.dumps(drm_conf))

    xbmcplugin.setResolvedUrl(addon_handle, True, listitem=item)


def handle_play(store, client):
    cid = params.get('cid')
    if not cid:
        _notify('Brak cid w żądaniu odtwarzania')
        _fail()
        return

    s = params.get('s')
    e = params.get('e')
    is_catchup = s is not None and e is not None

    pid = None
    ts = te = None
    if is_catchup:
        import datetime
        ts = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S').timestamp()
        te = datetime.datetime.strptime(e, '%Y-%m-%d %H:%M:%S').timestamp()

        epg_index = store.load_json('epg_index.json', {})
        pid = find_pid_for_catchup(epg_index, cid, ts)
        if not pid:
            _notify('Nie znaleziono programu w indeksie EPG dla catchup')
            _fail()
            return

    tvreg = store.get('tvreg')
    resolved = client.resolve_stream(cid, pid=pid, is_catchup=is_catchup, ts=ts, te=te, tvreg=tvreg)
    if not resolved:
        _notify('Nie udało się pobrać źródła streamu')
        _fail()
        return

    _play_via_inputstream(resolved)


def main():
    store = Store()
    client = OrangeGoClient(store)
    mode = params.get('mode')

    try:
        if mode == 'play':
            client.ensure_logged_in()
            handle_play(store, client)
        elif mode == 'refresh_now':
            import service
            service.run_cycle(store, client)
            _notify('Odświeżono M3U/XMLTV')
        else:
            # addon wywołany bez trybu (np. przypadkowe przeglądanie) - nic tu nie ma
            xbmcplugin.endOfDirectory(addon_handle, succeeded=True)
    except AuthError as e:
        _notify('Błąd logowania: %s' % e)
        _fail()


if __name__ == '__main__':
    main()
