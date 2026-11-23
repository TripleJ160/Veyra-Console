# Play capture-card video from an Odin through Artemis

The HDMI/USB capture card carries video and audio, not controller commands. Use two independent routes:

```
Picture: PS5 HDMI -> Elgato -> Veyra effects/FG -> Sunshine encode -> Artemis -> Odin
Input:   Odin -> Artemis -> Sunshine virtual gamepad -> Veyra -> PS5 Remote Play
```

Veyra already implements this capture-plus-controller mode. The older Console build disabled it at compile time. The updated private build enables native PS5 Remote Play; Veyra's Moonlight source client is unnecessary for this direction and stays off.

## First setup at home

1. On PS5, enable Settings -> System -> Remote Play -> Enable Remote Play. Use Link Device when Veyra asks for the console's eight-digit registration code. The PC and PS5 should be on the same home network for this initial registration.
2. Open **Open Veyra - Odin Artemis.cmd**. Connect the usual capture card and HDMI audio. In Capture card -> PS5 controller control, choose Pair and use the existing PS5 pairing dialog. It requests a PSN account ID / supported sign-in flow and the registration code; enter credentials only through the application/Sony flow. Pairing is stored locally with the existing protection. Never publish pairing files.
3. Enable **Control PS5 using Remote Play** and **Forward controller in background** in the capture panel. Select the paired console. Expect **Connected**, plus the actual detected gamepad name once Artemis sends input. A missing pairing, login PIN request, failed connection or missing controller is shown separately. Background mode also forwards pad presses when another PC window is focused; switch it off when not wanted.
4. Connect Artemis to the PC's existing Sunshine host. Keep controller/gamepad forwarding enabled in Artemis and the host; avoid a mouse-only controller mode. Veyra follows the most recently pressed gamepad, including a virtual gamepad that appears after streaming begins.
5. The installed host is **Apollo** (its service runs sunshine.exe). Use its **Always use Virtual Display** option for the Veyra app and a16:9 client mode, for example1920x1080 at120Hz if supported. Move Veyra onto that display and press F11 for fullscreen Fit. Fullscreen on the physical5120x1440 desktop still leaves side bars in a whole-desktop stream. Keep the physical monitor at120Hz. A60fps encoded stream cannot carry120 distinct output pictures. No host/display/driver settings are changed by this package. See [Apollo documentation](https://github.com/ClassicOldSong/Apollo) and [virtual-display FAQ](https://github.com/ClassicOldSong/Apollo/wiki/FAQ).

Also check the Odin client's **Gamepad Input** permission in Apollo. A client may have permission to view a stream while input is disabled.

The Remote Play side receives/discards a small keepalive video stream (720p30 requested, 5 Mbps) to maintain a real control session. Veyra continues displaying Elgato video and audio; it does not switch the picture to Remote Play. This has network/CPU overhead and may affect console behavior. Its real end-to-end cost is not measured in this build.

For away-from-home play, keep the PC/Sunshine and PS5 reachable at home, and use your existing secured remote-access/VPN arrangement to reach the PC. Veyra-to-PS5 control stays on the home LAN. No router rules, firewall changes, new drivers or VPN installation are performed by this update. First-time setup requires the pairing code; subsequent launches reuse the protected pairing.

## Frame generation and limits

Use the viewing preset **DLSS 2× — transport**, standard mode, Performance/Lite off, and only one FG system. NR is optional and independent. For a spatial reference use **Originals** and **NR off / Reference**, AA/SR off. Capture delivery FPS is not game-engine FPS. Interpolation can add displayed pictures and improve apparent motion but cannot double PS5 simulation or input response. The capture, interpolation wait, host encoding, WAN transport and handheld decoding/display delays all remain. GTA 6's eventual modes and cadence are unknown until measured.

## If input still does not arrive

- **Unavailable**: this executable was built without native Remote Play; use the updated private package.
- **No paired PS5**: complete registration in the PS5 dialog.
- **Connected, no gamepad**: verify Artemis/Sunshine is exposing a Windows gamepad and press an Odin button. The detected name should appear in Veyra. The installed Windows ViGEm bus was reported OK during preparation; this does not prove a particular Artemis session has created a pad.
- **Connected and gamepad present**: verify background forwarding or focus Veyra, check login-PIN status, and use Reconnect if the control session failed. Do not enable view-only Remote Play as the input route.

Offline virtual-gamepad and encrypted-loopback checks validate software boundaries. A successful PS5 pairing, live Odin input, WAN delivery cadence and controller-to-photon latency remain user/hardware validation boundaries, not claimed test results.
