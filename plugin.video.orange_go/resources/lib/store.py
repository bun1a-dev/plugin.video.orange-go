# -*- coding: utf-8 -*-
"""
Cienki wrapper na ustawienia addonu + prosty cache JSON w profilu.
Nic tu nie wie o Kodi UI, ani o Orange API - tylko trzymanie danych.
"""
import json
import os
import xbmcaddon
import xbmcvfs


class Store:
    def __init__(self):
        self.addon = xbmcaddon.Addon(id='plugin.video.orange_go')
        self.profile_dir = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        if not xbmcvfs.exists(self.profile_dir):
            xbmcvfs.mkdir(self.profile_dir)

    # --- ustawienia ---
    def get(self, key, default=''):
        val = self.addon.getSetting(key)
        return val if val != '' else default

    def get_int(self, key, default=0):
        val = self.get(key, '')
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def get_bool(self, key, default=False):
        val = self.get(key, '')
        if val == '':
            return default
        return val == 'true'

    def set(self, key, value):
        self.addon.setSetting(key, str(value))

    # --- json cache w profilu (np. epg_index.json) ---
    def cache_path(self, filename):
        return os.path.join(self.profile_dir, filename)

    def load_json(self, filename, default=None):
        path = self.cache_path(filename)
        if not xbmcvfs.exists(path):
            return default if default is not None else {}
        f = xbmcvfs.File(path, 'r')
        raw = f.read()
        f.close()
        try:
            return json.loads(raw) if raw else (default if default is not None else {})
        except ValueError:
            return default if default is not None else {}

    def save_json(self, filename, data):
        path = self.cache_path(filename)
        f = xbmcvfs.File(path, 'w')
        f.write(json.dumps(data))
        f.close()
