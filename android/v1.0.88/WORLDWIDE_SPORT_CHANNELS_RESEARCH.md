# EpiMediaHub — global sports-channel recognition inventory (26 Oct 2026)

## Aim and limits

This is a *curated international family taxonomy* for live TV, **not** an exhaustive
official register of every sports channel worldwide, and not a list of playable streams.
Channel availability, rights, branding and names evolve quickly. The app never
downloads or probes unapproved IPTV endpoints for catalog classification.

The implementation is in `V188WorldwideSportChannels.kt`. Keep it reviewable, and
ship future additions only with coverage and non-sports false-positive tests.

## Research basis

Official/broadcaster or distributor references checked on 2026-10-26:

- Germany: [Sky Sport](https://www.sky.de/sender/sky-sport), [Bundesliga broadcasters](https://www.bundesliga.com/de/bundesliga/info/broadcasters).
- Italy: [Sky Sport channel guide](https://assistenza.sky.it/programmazione/guida-canali-sky-sport), [Sky sport package](https://www.sky.it/tv/sky-sport).
- United Kingdom: [Sky and TNT TV channel guide](https://helpforum.sky.com/t5/What-s-On/Changes-to-the-TV-Guide-September-2026/m-p/5356945).
- Iberia: [Movistar sports channel lineup](https://www.movistarplus.es/comunicacion/notas-de-prensa/nace-vamos-2-por-m-dial-51-para-cubrir-las-necesidades-de-la-oferta-deportiva-en-movistar-plus/), [Portuguese sports operator listing](https://www.nos.pt/tv/canais/desporto).
- Eastern Europe: [Digi channel list](https://www.digi.ro/grila), [Tivibu sports](https://www.tivibu.com.tr/canli-tv/spor).
- MENA: [beIN channel list](https://www.bein.com/en/channel-list/?c=us).
- Africa: [DStv SuperSport lineup](https://www.dstv.com/en-ng/explore/dstv-channels/).
- South East Asia: [Astro channel-renaming announcement](https://corporate.astro.com.my/mediaroom-releases/astro-revamps-its-sports-channel-lineup).
- Australia/NZ: [Kayo sports live channels](https://kayo-support.zendesk.com/hc/en-au/articles/31174079599773-What-Live-Channels-are-available-on-Kayo), [Fox Sports](https://www.foxsports.com.au/about.us).
- United States and Latin America: [Sports network listings](https://www.wheresports.com/live-tv/), [ESPN international network overview](https://latinamerica.espnpressroom.com/espn-international-fact-sheet-2-2/).
- Global metadata / names and international discovery: [iptv-org/database](https://github.com/iptv-org/database), a community-maintained dataset (not an authoritative rights catalogue).

## Taxonomy and stream variant semantics

Supported families cover dedicated channel brands and feeds across
DE/AT/CH, Italy, UK/Ireland, France/Benelux, Spain/Portugal,
Eastern Europe, Türkiye, MENA, Africa, South Asia, East and Southeast Asia,
North America, Latin America/Caribbean and Australia/New Zealand.

A family is recognized via an anchored normalized station prefix, never via
a free-floating word appearing anywhere in a movie title.

Provider-specific cases:

- `DE: DB LIGA 1 4K` —> Bundesliga-labelled sports family.
- `DE: SKY SPORT BUNDESLIGA 1 FHD` —> same normalized Bundesliga
  *station identity only when provider and language tags/number match*.
- `IT: SKY CALCIO 1` and `IT: SKY SPORT CALCIO 1` —> same named channel.
- `DE: DAZN 1` and `IT: DAZN 1` stay distinct.
- `Sky Bundesliga 1` and `Sky Bundesliga 2` stay distinct.
- Quality/mode suffixes `SD HD HD+ FHD FULL HD UHD 4K 1080P HEVC BHAEVC WEB 25FPS 50FPS` are ignored for **name equivalence**, but FPS must **never** be inferred from these quality labels.
- `DB Liga` is a user-reported IPTV alias, **not a verified official broadcaster name**. It may be a provider-specific obfuscation; it must not imply Sky broadcasting rights.

Sport recommendation requires a real 25-fps PTS cadence plus a
previously PTS-verified 50-fps alternative in the *same active provider*,
with independent category lookup and sequential, single-connection
failover after opt-in. EPG current programme improves confidence but
is optional for known sport channel families. An explicitly named
documentary, movie, news or highlights programme suppresses the
automatic modal.

Never auto-switch channels when user clicks one. For all other
cases, manual alternatives remain accessible from the playback UI;
no automatic popup is shown. If no 50-fps alternate is known, do not
offer a futile sport-mode dialog.

## Maintenance

Re-evaluate channel families by country/brand quarterly, particularly
renamed or closed networks. For instance, FanDuel Sports Network was
reported closed as of 2026-09-28 by
[FanDuel support](https://support.fanduel.com/s/article/FanDuel-Sports-Network-FAQ);
legacy IPTV playlists may retain the obsolete label. Distinguish such
historical prefixes from current licensed broadcasts. Never assume
the presence of a channel name proves a live service, rights or FPS.
