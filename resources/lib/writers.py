# -*- coding: utf-8 -*-
"""
Budowanie plików M3U i XMLTV + lokalny indeks (cid, start_ts) -> pid,
potrzebny resolverowi żeby obsłużyć catchup (IPTV Simple Client przekazuje
tylko czas s/e, nie programExtId).
"""
import datetime
import xbmcvfs

API_URL_OLD = 'https://tvgo.orange.pl/gpapi/'
FANART_REL = 'resources/img/fanart.jpg'

CATCHUP_LOOKUP_TOLERANCE_SEC = 60  # TODO: przetestować czy 60s wystarcza, dostosować w razie potrzeby


def _channel_logo(channel):
    return API_URL_OLD + 'resource/image/' + channel['logoSignature']


def build_m3u(channels, addon_base_url):
    """channels: lista surowych dictów z api.get_channels()."""
    lines = ['#EXTM3U']
    for c in channels:
        play = c['playFeatures'].get('otg', {})
        if not play.get('isChannelAllowed'):
            continue

        name = c['name']
        cid = c['channelExtId']
        logo = _channel_logo(c)
        group = c.get('category', 'Orange Go')
        is_catchup = play.get('isCatchUp', False)

        extinf = '#EXTINF:-1 tvg-id="%s" tvg-logo="%s" group-title="%s"' % (cid, logo, group)
        if is_catchup:
            catchup_days = max(1, int(int(c.get('catchupDuration', 0)) / 86400))
            extinf += (' catchup="append"'
                       ' catchup-source="&s={utc:Y-m-d H:M:S}&e={utcend:Y-m-d H:M:S}"'
                       ' catchup-days="%d" catchup-correction="0.0"' % catchup_days)
        extinf += ',%s' % name

        lines.append(extinf)
        lines.append('%s?mode=play&cid=%s' % (addon_base_url, cid))

    return '\n'.join(lines) + '\n'


def _xmltv_time(dt):
    return dt.strftime('%Y%m%d%H%M%S +0000')


def build_xmltv(channels, epg_by_channel):
    """
    epg_by_channel: {cid: [program_dict, ...]}
    program_dict jak w API: name, startTimeUtc, endTimeUtc, episodeNumber, image...
    Zwraca (xml_string, epg_index) gdzie epg_index to {cid: {start_ts: pid}}.
    """
    epg_index = {}

    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="orange_go">']

    for c in channels:
        cid = c['channelExtId']
        name = c['name']
        logo = _channel_logo(c)
        out.append('  <channel id="%s"><display-name>%s</display-name><icon src="%s"/></channel>'
                    % (cid, _xml_escape(name), logo))

    for c in channels:
        cid = c['channelExtId']
        programs = epg_by_channel.get(cid, [])
        chan_index = {}
        for p in programs:
            start = datetime.datetime.fromtimestamp(p['startTimeUtc'])
            stop = datetime.datetime.fromtimestamp(p['endTimeUtc'])
            title = p.get('name', '')
            pid = p.get('programExtId', '')

            out.append('  <programme start="%s" stop="%s" channel="%s">'
                        % (_xmltv_time(start), _xmltv_time(stop), cid))
            out.append('    <title lang="pl">%s</title>' % _xml_escape(title))
            episode = p.get('episodeNumber')
            if episode not in (None, ''):
                out.append('    <episode-num system="onscreen">%s</episode-num>' % _xml_escape(str(episode)))
            out.append('  </programme>')

            chan_index[str(int(p['startTimeUtc']))] = pid

        if chan_index:
            epg_index[cid] = chan_index

    out.append('</tv>')
    return '\n'.join(out), epg_index


def _xml_escape(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
             .replace('"', '&quot;'))


def find_pid_for_catchup(epg_index, cid, start_ts):
    """Szuka pid w indeksie po (cid, start_ts) z tolerancją czasową."""
    chan_index = epg_index.get(cid, {})
    if not chan_index:
        return None
    target = int(start_ts)
    best_pid, best_diff = None, None
    for ts_str, pid in chan_index.items():
        diff = abs(int(ts_str) - target)
        if diff <= CATCHUP_LOOKUP_TOLERANCE_SEC and (best_diff is None or diff < best_diff):
            best_pid, best_diff = pid, diff
    return best_pid


def write_text_file(path, content):
    f = xbmcvfs.File(path, 'w')
    f.write(content)
    f.close()
