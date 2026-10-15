#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
vpn=root/"app/src/main/java/de/epimediahub/app/vpn"
tests=root/"app/src/test/java/de/epimediahub/app/vpn"

def replace(file,old,new):
    value=file.read_text()
    if value.count(old)!=1:
        raise RuntimeError("v176 patch failed: "+file.name)
    file.write_text(value.replace(old,new,1))

build=root/"app/build.gradle.kts"
replace(build,"versionCode = 1075","versionCode = 1076")
replace(build,'versionName = "1.0.75"','versionName = "1.0.76"')
shutil.copyfile(here/"V176GalaBoxMtuPilot.kt",vpn/"V176GalaBoxMtuPilot.kt")
profile=vpn/"V142VpnAutoProvision.kt"
symbol=chr(36)
marker="            IncludedApplications = "+symbol+"{application.packageName}"
replace(profile,marker,marker+symbol+"{V176GalaBoxMtuPilot.interfaceSuffix(application)}")
settings=vpn/"V141VpnSettings.kt"
marker='        V141FocusButton("Finnland-VPN verbinden / prüfen", accent, onClick = {'
insert='''        if (V176GalaBoxMtuPilot.eligible(context)) {
            V141FocusButton(
                "GalaBox MTU-Test: " + V176GalaBoxMtuPilot.description(context),
                accent, onClick = {
                    val mtu = V176GalaBoxMtuPilot.next(V176GalaBoxMtuPilot.selected(context))
                    V176GalaBoxMtuPilot.choose(context, mtu)
                    status = "Neuer MTU-Testwert: " + V176GalaBoxMtuPilot.description(context) +
                        ". Bitte VPN ausdrücklich trennen, erneut mit Finnland verbinden " +
                        "und erst danach den Speedtest wiederholen."
                }, enabled = !busy)
        }
'''
replace(settings,marker,insert+marker)
shutil.copyfile(here/"V176GalaBoxMtuPilotTest.kt",tests/"V176GalaBoxMtuPilotTest.kt")
print("GalaBox MTU experiment v176 applied. Fire TV default profile unchanged.")
