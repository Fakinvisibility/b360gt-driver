# Arch Linux installation and hardware test

## 1. Install from this source tree

Install the Arch packaging tools, prepare the local source archive, and build:

```bash
sudo pacman -S --needed base-devel python-build python-installer
bash ./packaging/arch/prepare-source.sh
cd packaging/arch
makepkg -si
```

The package pulls all runtime dependencies from Arch's official repositories.

## 2. Load device permissions

After installation:

```bash
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=usb
sudo udevadm trigger --subsystem-match=hidraw
```

Log out and back in if the current session does not receive the `uaccess` ACL.
The cooler USB cable normally does not need to be unplugged.

Verify both transports without sending display data:

```bash
b360gt probe
python -c 'import hid; print(hid.enumerate(0x345f, 0x9132))'
```

## 3. First physical test

Keep MythCool/Windows out of the way and run:

```bash
b360gt send ./test-images/orientation-pattern.png --seconds 15
```

Then test animation or video:

```bash
b360gt play ./test-images/animation.gif --seconds 15
b360gt play ./test-images/animation.mp4 --seconds 15
```

No command should require `sudo`. If access is denied, inspect:

```bash
getfacl /dev/bus/usb/BBB/DDD
getfacl /dev/hidrawN
```

Replace the placeholders with paths shown by `lsusb -d 345f:9132` and the HID
enumeration output.

## 4. Background web control panel

The installed package can run the local web UI through a systemd user service:

```bash
b360gt start
b360gt status
b360gt stop
```

The page remains available at `http://127.0.0.1:8765/` after the terminal
closes. These commands start or stop the current session only. To start the UI
automatically at login:

```bash
systemctl --user enable --now b360gt-ui.service
```

Inspect service logs with:

```bash
journalctl --user -u b360gt-ui.service
```

## 5. Optional automatic media player

Choose the file to loop by creating a symlink:

```bash
mkdir -p ~/.config/b360gt
ln -sfn /absolute/path/to/image-or-video ~/.config/b360gt/media
systemctl --user enable --now b360gt.service
```

Check status and logs:

```bash
systemctl --user status b360gt.service
journalctl --user -u b360gt.service
```

The user service starts at login. It deliberately runs without root privileges.

## 6. Persistent UI media library

Start the local UI with:

```bash
b360gt ui
```

Browser uploads are stored under `~/.local/share/b360gt/media` and survive UI
or computer restarts. To choose another location:

```bash
B360GT_MEDIA_DIR=/absolute/path/to/library b360gt ui
```

Do not point `B360GT_MEDIA_DIR` at a general-purpose media folder. The UI only
deletes validated item directories that it created itself.
