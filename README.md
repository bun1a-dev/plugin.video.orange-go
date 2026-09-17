# plugin.video.orange_go

Nieoficjalny dodatek do Kodi generujący playlistę **M3U** oraz przewodnik **XMLTV** na podstawie Orange GO (tvgo.orange.pl). Nie posiada własnego menu przeglądania — pliki wczytuje `PVR IPTV Simple Client`, a samo odtwarzanie (w tym catchup/archiwum) jest resolvowane przez ten addon w tle.

> Wymaga aktywnej, płatnej subskrypcji Orange GO. To nieoficjalny klient — nie jest tworzony ani wspierany przez Orange Polska.

## Jak to działa

Addon składa się z dwóch niezależnych komponentów działających w Kodi:

- **`service.py`** — uruchamia się razem z Kodi i mieli w tle. Co ustawioną liczbę godzin: loguje się (lub odświeża sesję), pobiera listę kanałów i EPG, generuje pliki `orange_go.m3u` i `orange_go.xml` w profilu addonu.
- **`addon.py`** — resolver wywoływany wyłącznie przez `plugin://plugin.video.orange_go?mode=play...` w momencie kliknięcia kanału w `PVR IPTV Simple Client`. Ustanawia sesję DRM (Widevine) i zwraca gotowy do odtworzenia stream.

Pliki M3U/XMLTV trafiają zawsze do:
```
special://profile/addon_data/plugin.video.orange_go/orange_go.m3u
special://profile/addon_data/plugin.video.orange_go/orange_go.xml
```
i **nie są przeznaczone do użytku poza Kodi** (żaden zewnętrzny serwer/udział sieciowy).

## Wymagania

- Kodi (testowane pod kątem wersji z `inputstreamhelper`)
- Dodatki: `script.module.requests`, `script.module.inputstreamhelper`, `script.module.js2py`
- `PVR IPTV Simple Client` (wbudowany w Kodi)
- Aktywna subskrypcja Orange GO

## Instalacja

1. Pobierz `.zip` z tego repo (albo z sekcji Releases).
2. W Kodi: **Ustawienia → Dodatki → Zainstaluj z pliku ZIP** i wskaż pobrany plik.
3. Wejdź w ustawienia zainstalowanego dodatku i uzupełnij **Login** oraz **PIN** w sekcji *Konto*.
4. Poczekaj na pierwszy cykl serwisu w tle, albo w sekcji *Ogólne* kliknij **"Wygeneruj teraz"**.
5. Skonfiguruj `PVR IPTV Simple Client`:
   - **M3U Play List URL (Local path):** `special://profile/addon_data/plugin.video.orange_go/orange_go.m3u`
   - **XMLTV URL (Local path):** `special://profile/addon_data/plugin.video.orange_go/orange_go.xml`
6. Włącz/zrestartuj `PVR IPTV Simple Client`.

## Ustawienia

| Kategoria      | Opcja                          | Opis                                                        |
|----------------|--------------------------------|--------------------------------------------------------------|
| Konto          | Login / PIN                    | Dane logowania do Orange GO                                   |
| Harmonogram    | Co ile godzin odświeżać        | Częstotliwość regeneracji M3U/EPG w tle                       |
| Harmonogram    | Ile dni EPG do przodu          | Zakres przewodnika w XMLTV                                     |
| Ogólne         | Wersja TVP3                    | Region dla regionalizacji kanału TVP3                          |
| Ogólne         | Wygeneruj teraz                | Wymusza jeden cykl generowania bez czekania na harmonogram      |

## Struktura projektu

```
plugin.video.orange_go/
├── addon.xml              # deklaracja dwóch extension pointów: pluginsource + service
├── addon.py                # resolver (mode=play, mode=refresh_now) — bez menu
├── service.py               # pętla w tle: login/refresh, pobranie danych, zapis plików
└── resources/
    ├── settings.xml
    └── lib/
        ├── store.py         # wrapper na ustawienia + cache JSON w profilu
        ├── api.py            # sesja, logowanie, kanały, EPG, resolve streamu + DRM
        └── writers.py        # budowa M3U / XMLTV / indeksu catchup
```

## Znane ograniczenia / do przetestowania

- Dopasowanie programu przy catchup (`(kanał, czas startu) → programExtId`) opiera się na lokalnym indeksie budowanym przy każdej generacji EPG, z tolerancją czasową ±60s — może wymagać dostrojenia.
- Ciastko `AnalyticsData` wymagane do wstępnej weryfikacji jest generowane przez lokalne wykonanie fragmentu JS ze strony Orange (`js2py`). Jeśli się to nie uda, addon nie sięga po żaden zewnętrzny serwis jako fallback — po prostu kontynuuje bez tego ciastka, co może skutkować błędami 403/412 w niektórych requestach.

## Licencja

GNU General Public License v2.0 — patrz [LICENSE](LICENSE).
