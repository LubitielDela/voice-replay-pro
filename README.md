**English** | [Русский](README.ru.md)

# Voice Replay PRO

> Record the audio from your headphones (for example, a game's voice chat) and replay it into a virtual microphone with one hotkey.

**Author:** [LubitielDela](https://github.com/LubitielDela) · **License:** [MIT](LICENSE) · **Platform:** Windows 10/11

Voice Replay PRO records whatever plays in your headphones and plays it back into a virtual microphone (VB-Cable). A game, Discord or any other app hears it as normal speech from your mic. Good for pranks with friends, a soundboard, and voice chat tests.

## Features

- Record and play back with one key (start/stop toggles)
- Menu with all settings, opened by a hotkey
- Always-on-top overlay: status (recording, playing, idle), selected clip, list of hotkeys
- Drag the overlay with the mouse or snap it to any screen corner
- Every hotkey can be changed in the menu
- Clip list: play, rename, delete
- Choose the recording device and the output device, volume, optional monitoring in your headphones
- Settings are saved automatically

## Ethics and rules

- Record and replay someone's voice only with their consent. Use the tool for jokes with friends, not for deception, harassment or impersonation.
- Many games and servers forbid this in their rules. You are responsible for any bans.
- Clips in `clips/` may contain other people's voices. Do not publish them (the folder is already in `.gitignore`).

## Requirements

- Windows 10 or 11
- [Python 3.9+](https://www.python.org/downloads/) (tick **Add Python to PATH** during installation)
- [VB-Cable](https://vb-audio.com/Cable/) (free virtual audio cable)

## Installation

1. Download the repository (**Code → Download ZIP**) and unzip it anywhere.
2. Install VB-Cable:
   1. Unzip the VB-Cable archive.
   2. Right-click `VBCABLE_Setup_x64.exe` and choose **Run as administrator**.
   3. Click **Install Driver** and restart your computer.
3. Install the dependencies. Open a command prompt in the project folder and run:
   ```
   pip install -r requirements.txt
   ```

## Audio setup

After VB-Cable is installed, Windows shows two new devices: **CABLE Input** (playback) and **CABLE Output** (recording).

1. **Sound settings → Output:** set your headphones as the default device. The app records exactly what plays in them.
2. **Sound settings → Input:** set **CABLE Output** as the default microphone.
3. In the game (or Discord) choose **CABLE Output** as the microphone, or "Default".
4. In Control Panel → Sound → Playback, your headphones should be both "Default Device" and "Default Communication Device".

### So people can hear you when you talk yourself

The cable is now your microphone in games, so mix your real microphone into it:

1. Control Panel → Sound → Recording.
2. Double-click your real microphone → **Listen** tab.
3. Tick "Listen to this device", choose **CABLE Input** as the playback device and click Apply.

## Running

Run **as administrator**, otherwise hotkeys may not work inside games.

Easiest way: double-click `start.bat`. It asks for administrator rights and starts the app in a minimized window.

Manually:
```
python voice_replay_pro.py
```

Connect Bluetooth headphones **before** starting the app. If you switch headphones while it runs, restart it or pick the device in Settings.

## How to use

Default hotkeys:

| Key | Action |
|-----|--------|
| F8 | Start / stop recording |
| F9 | Play / stop playback |
| F10 | Previous clip |
| F11 | Next clip |
| INSERT | Open / hide the menu |
| F7 | Show / hide the overlay |

Typical flow:

1. Someone speaks in voice chat. Press **F8** to start recording.
2. Press **F8** again to stop. The clip is saved to the `clips` folder.
3. Press **F9** and the clip plays into your virtual microphone. Press F9 again to stop.
4. If your game uses push-to-talk, hold that key while the clip plays.

Recordings longer than 120 seconds are stopped and saved automatically.

## Menu

Open it with INSERT (changeable).

- **Clips:** list, record and play buttons, rename, delete, open folder. Double-click a clip to play it.
- **Hotkeys:** click the button of an action, then press the new key or combination (for example `ctrl+f5`).
- **Settings:** devices, volume, monitoring in your headphones, overlay (on/off, opacity, position, always on top), menu always on top.

## Overlay

A small window with the status and the hotkey hints. Move it with the mouse or use the ↖ ↗ ↙ ↘ buttons in Settings.

The overlay is visible over a game only in **windowed or borderless mode** ("Fullscreen windowed"). Windows hides it in exclusive fullscreen.

## Troubleshooting

| Problem | What to do |
|---------|-----------|
| The window closes immediately | Run it from a command prompt (`python voice_replay_pro.py`) and read the error. |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt`. |
| Error about `fromstring` or `binary mode` | Run `pip install "numpy<2"`. |
| CABLE Input not found | Check the VB-Cable installation and restart the PC. You can also pick the output device in Settings. |
| Hotkeys do nothing | Run as administrator. |
| Only silence is recorded | Make sure your headphones are the default output device, or choose the device in Settings. |
| People can't hear me in the game | Make sure the microphone is CABLE Output and set up mixing of your real microphone (see above). |
| No overlay in the game | Switch the game to windowed or borderless mode. |

## Project files

| File | What it does |
|------|--------------|
| `voice_replay_pro.py` | The main program: recording, playback, hotkeys, menu and overlay. |
| `start.bat` | Launcher: asks for administrator rights, starts the app minimized. |
| `requirements.txt` | List of Python packages for `pip install -r requirements.txt`. |
| `README.md` | This documentation (English). |
| `README.ru.md` | Documentation in Russian. |
| `LICENSE` | MIT license: you may use, change and share the code. |
| `.gitignore` | Tells Git not to upload `clips/` (voices) and `config.json` (personal settings). |
| `config.json` | Created on first run. Saved settings and hotkeys. Not in the repository. |
| `clips/` | Created on first run. Your saved recordings. Not in the repository. |

## Author

Made by [LubitielDela](https://github.com/LubitielDela).

## License

[MIT](LICENSE) © LubitielDela
