Orbit 0.1.0 — Steam and custom games in one console-style launcher.

Downloads (x86_64):
- Windows 10/11: `Orbit-0.1.0-windows-x64-setup.exe`. Per-user installer; Python is included.
- Debian/Ubuntu with glibc 2.35+: `.deb` (`sudo apt install ./orbit-launcher_0.1.0_amd64.deb`).
- Fedora and compatible systems with glibc 2.35+: `.rpm` (`sudo dnf install ./orbit-launcher-0.1.0-1.x86_64.rpm`).
- Arch Linux: `.pkg.tar.zst` (`sudo pacman -U ./orbit-launcher-0.1.0-1-x86_64.pkg.tar.zst`).

Features: automatic Steam library discovery, saved Steam accounts, custom executables, editable launch parameters, favorites, keyboard/gamepad navigation and optional Steam shader pre-cache bypass.

The Windows installer is unsigned. Windows may show a reputation warning. Saves and settings remain in the user's data directory when upgrading or uninstalling. Steam/Steam Guard still handles authentication.

SHA-256 checksum lists are included. Native builds and automated startup smoke tests run on Linux and Windows before publication. Actual games and physical controllers are not tested by CI.
