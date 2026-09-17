# -*- coding: utf-8 -*-
"""
Background service: co N godzin loguje się (jeśli trzeba), pobiera kanały + EPG,
zapisuje M3U i XMLTV oraz epg_index.json (potrzebny resolverowi do catchup).
Uruchamiany automatycznie przez Kodi (extension point xbmc.service).
"""
import datetime
import os
import sys

import xbmc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'resources', 'lib'))
from store import Store          # noqa: E402
from api import OrangeGoClient, AuthError  # noqa: E402
from writers import build_m3u, build_xmltv, write_text_file  # noqa: E402

ADDON_BASE_URL = 'plugin://plugin.video.orange_go'


def _log(msg):
    xbmc.log('[orange_go/service] ' + msg, level=xbmc.LOGINFO)


def run_cycle(store, client):
    client.ensure_logged_in()

    channels = client.get_channels()
    if not channels:
        _log('run_cycle: brak kanałów, przerywam ten cykl')
        return

    epg_by_channel = {}
    days_ahead = store.get_int('epg_days_ahead', 2)
    today = datetime.datetime.now()
    seen_dates = set()

    for offset in range(0, days_ahead + 1):
        date_str = (today + datetime.timedelta(days=offset)).strftime('%Y-%m-%d')
        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)

        raw_epg = client.get_epg(date_str)  # {ts: {channelExtId: ..., programs: [...]}} per dzień
        for _, guide in raw_epg.items():
            if not guide:
                continue
            for entry in guide:
                cid = entry.get('channelExtId')
                if not cid:
                    continue
                epg_by_channel.setdefault(cid, []).extend(entry.get('programs', []))

    m3u_content = build_m3u(channels, ADDON_BASE_URL)
    xmltv_content, epg_index = build_xmltv(channels, epg_by_channel)

    # zawsze w profilu addonu - to nie jest przeznaczone do użytku poza Kodi
    m3u_path = os.path.join(store.profile_dir, 'orange_go.m3u')
    xmltv_path = os.path.join(store.profile_dir, 'orange_go.xml')

    write_text_file(m3u_path, m3u_content)
    write_text_file(xmltv_path, xmltv_content)
    store.save_json('epg_index.json', epg_index)

    _log('run_cycle: zapisano M3U (%d kanałów) i XMLTV (%d kanałów z EPG)'
         % (len(channels), len(epg_by_channel)))


def main():
    store = Store()
    client = OrangeGoClient(store)
    monitor = xbmc.Monitor()

    _log('start service')

    while not monitor.abortRequested():
        try:
            run_cycle(store, client)
        except AuthError as e:
            _log('run_cycle: błąd logowania: %s' % e)
        except Exception as e:  # celowo szeroko - to pętla w tle, nie chcemy jej ubić
            _log('run_cycle: nieoczekiwany błąd: %s' % e)

        interval_hours = max(1, store.get_int('refresh_hours', 6))
        if monitor.waitForAbort(interval_hours * 3600):
            break

    _log('stop service')


if __name__ == '__main__':
    main()
