; Inno Setup script for PodcastDeck-Setup.exe. GitHub builds it (.github/workflows/release.yml):
;   iscc /DVersion=1.0.5 installer\PodcastDeck.iss
; Installs for this Windows user only (no admin prompt), adds the desktop and Start menu shortcuts, and
; lets podcast-deck:// group links open the deck. Running it again updates the deck in place; config.py
; and backgrounds in the install folder are kept.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6F2C8B4E-5A1D-4C8E-9B7A-3E1F0D2C4B6A}
AppName=Podcast Deck
AppVersion={#Version}
AppPublisher=Podcast Deck
DefaultDirName={localappdata}\Programs\Podcast Deck
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PodcastDeck-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\PodcastDeck.exe
UninstallDisplayName=Podcast Deck

[Files]
Source: "..\dist\PodcastDeck\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userdesktop}\Podcast Deck"; Filename: "{app}\PodcastDeck.exe"
Name: "{userprograms}\Podcast Deck"; Filename: "{app}\PodcastDeck.exe"

[Registry]
; podcast-deck://… links (the Join button on a group link's page) open the deck with that group.
Root: HKCU; Subkey: "Software\Classes\podcast-deck"; ValueType: string; ValueName: ""; ValueData: "URL:Podcast Deck group"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\podcast-deck"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\podcast-deck\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PodcastDeck.exe"" ""%1"""

[Run]
; Also runs after a silent update, so the deck reopens by itself.
Filename: "{app}\PodcastDeck.exe"; Description: "Open Podcast Deck"; Flags: nowait postinstall
