#!/usr/bin/env python3
"""Install the exact approved V5 video and the verified Finland banner indicator."""
import hashlib
import os
import re
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
here = Path(__file__).resolve().parent
java = root / 'app/src/main/java/de/epimediahub/app'

def replace(path, old, new):
    source = path.read_text()
    if source.count(old) != 1:
        raise SystemExit(f'v161 intro/banner anchor mismatch: {path}: {old[:100]}')
    path.write_text(source.replace(old, new, 1))

video = here / 'epimedia_intro_v5.mp4'
expected = '4b3556a5da85560f2c2668f6a32b6cdafef220b535b16ae6f807684817350a51'
if hashlib.sha256(video.read_bytes()).hexdigest() != expected:
    raise SystemExit('Approved V5 video checksum mismatch')
shutil.copyfile(video, root / 'app/src/main/res/raw/epimedia_intro_v5.mp4')
for name in ('V161IntroVideo.kt', 'V161VpnBanner.kt'):
    shutil.copyfile(here / name, java / 'ui' / name)

intro = java / 'ui/V070Intro.kt'
source = intro.read_text()
start = source.index('fun V070IntroScreen(accent: Color, onFinished: () -> Unit) {')
end = source.index('\n@Composable\ninternal fun V121IntroContent', start)
intro.write_text(source[:start] + '''fun V070IntroScreen(accent: Color, onFinished: () -> Unit) {
    V161IntroVideoScreen(accent, onFinished)
}
''' + source[end:])

session = java / 'vpn/V134VpnSession.kt'
replace(session, '    fun needsDirectFallbackPrompt(context: Context, playlistId: String): Boolean =',
    '''    /** Cached verified Finland exit, tunnel and process binding; no new network request. */
    @Synchronized
    fun verifiedFinlandActive(context: Context, playlistId: String): Boolean =
        usesVpn(context, playlistId) && route == Route.FINLAND && lastExitOk &&
            tunnel?.isUp() == true && V140VpnLossMonitor.isPinned(context)

    fun needsDirectFallbackPrompt(context: Context, playlistId: String): Boolean =''')

player = java / 'ui/PlayerScreen.kt'
source = player.read_text()
anchor = '                    Surface(color = accent.copy(alpha = .18f), shape = MaterialTheme.shapes.small) {'
if source.count(anchor) != 2:
    raise SystemExit('Expected standard and VLC Live-TV banner badges')
starts = [match.start() for match in re.finditer(r'(?m)^' + re.escape(anchor), source)]
if len(starts) != 2:
    raise SystemExit('Live-TV badges must be separate top-level banner entries')
for start in reversed(starts):
    end = source.index('\n                    }', start) + len('\n                    }')
    badge = source[start:end]
    source = source[:start] + '''                    Column(horizontalAlignment = Alignment.End,
                        verticalArrangement = Arrangement.spacedBy(5.dp)) {
''' + '\n'.join('    ' + line for line in badge.splitlines()) + '''
                        V161VpnBanner(u.active?.id?.toString())
                    }''' + source[end:]
player.write_text(source)
assert source.count('V161VpnBanner(u.active?.id?.toString())') == 2
assert 'v160WarmLiveDuringIntro' in (java / 'MainViewModel.kt').read_text()
print('Approved V5 17.5s offline video installed; Finland VPN badge in standard + VLC banners.')
