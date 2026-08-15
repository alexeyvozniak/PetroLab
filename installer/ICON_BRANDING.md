PetroLab Windows branding

- `petrolab-icon.svg` is the source artwork for the main application/shortcut icon.
- `petrolab-installer-icon.svg` is the matching installer artwork with the install badge.
- The Windows build generates `PetroLab.ico` and `PetroLab-Installer.ico` from those sources at 256, 128, 64, 48, 32, 24 and 16 px.
- `PetroLab.exe` embeds the application icon. Inno Setup embeds the dedicated installer icon in the setup executable and uses the application icon for installed shortcuts and the uninstall entry.
