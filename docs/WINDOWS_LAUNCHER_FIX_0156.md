# PetroLab 0.15.6 Windows launcher fix

The previous Windows installer created PetroLab shortcuts that launched `wscript.exe` with a VBS wrapper. The release CI verified the embedded Python/Streamlit payload directly, but did not exercise the same shortcut-to-launcher path used by a real installed user. That allowed a silent launcher/browser-start failure to escape while the installer workflow remained green, and it also exposed the generic WScript icon.

This fix changes the release contract:

- installed shortcuts and post-install launch target a real `PetroLab.exe`;
- the native launcher starts the embedded Streamlit server headlessly on loopback, waits for `/_stcore/health`, then opens the browser explicitly;
- startup stdout/stderr are captured in `logs/launcher.log`, and startup failures show a visible message with the log location;
- a session mutex plus server-state file prevents double-clicks during startup from spawning duplicate servers;
- a second launch reopens the existing healthy PetroLab server;
- the legacy VBS file remains only as an updater/backward-compatibility bridge;
- app/shortcut and installer use a matched PetroLab crystal/strata icon family, with a dedicated install badge on the setup executable;
- CI installs the generated Setup EXE and launches the installed `PetroLab.exe` twice, rather than bypassing the launcher with direct Python execution;
- diagnostics now verifies the native launcher and prints recent launcher log messages.

Scientific user data remain under the user's Documents/PetroLab Data folder and are not included in installer-owned cleanup paths.
