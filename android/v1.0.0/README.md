# Android 1.0.0 development

Development branch: `android-v1.0.0-dev`

This branch starts from the released 0.9.9 source reconstruction and keeps the
0.9.9 release branch untouched.

## First implementation slice

- reserve a header safe-zone so weather, clock and date sit above large skin marks
- move playlist switching out of the 2x3 grid into a round top-right quick action
- replace the old playlist tile with an internal SmartTube host tile
- keep SmartTube inside EpiMediaHub; do not launch an external APK
- surface Xtream `added` data as a dedicated **Zuletzt hinzugefügt** row for movies and series
- rotate **Heute im Fokus** through the newest items every four seconds

## Next slices

1. Connect the pinned SmartTube upstream core behind `V100SmartTubeShell`.
2. Rework Mediathek navigation to **country -> broadcaster** with broadcaster logos.
3. Tune focus/remote behaviour and pause the focus carousel while the hero itself is focused.
4. TV-device regression tests and signed 1.0.0 release only after the development branch is stable.

SmartTube upstream is tracked separately and remains subject to its upstream
license/notices. The initial upstream pin for integration work is
`yuliskov/SmartTube@a7212c531ac06ec87108180d5d8ab1bebebe528e`.
