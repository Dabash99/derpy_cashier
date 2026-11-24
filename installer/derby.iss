; Derby installer (Part B4). Compile with Inno Setup 6:
;   ISCC.exe installer\derby.iss
; (run tools\write_installer_version.py first if the app version changed --
; tools\build_installer.py does both steps for you.)
;
; Requires Inno Setup 6 (not 5): https://jrsoftware.org/isdl.php
;
; 64-bit only, Windows 7 SP1 minimum. Installs to {autopf}\Derby (so
; %ProgramFiles%, never a per-user folder -- shared machine, one install).
; The uninstaller NEVER touches %APPDATA%\Derby or Documents\Derby --
; only files this installer itself placed under {app} are ever removed;
; see the UninstallDataNotice message shown on the uninstall confirm step.

#include "version.iss"

#define MyAppName "Derby"
#define MyAppPublisher "Derby"
#define MyAppExeName "Derby.exe"
; Fixed for the lifetime of this product -- changing it breaks in-place
; upgrades (Inno Setup/Windows would see it as a different product).
; Generated once; never regenerate.
#define MyAppId "{83A362E7-54D0-4B04-88A5-DB9E45992C5A}"

[Setup]
; {#MyAppId} already includes its own enclosing braces (it's the GUID
; literal "{83A362E7-...}") -- the runtime constant parser needs the
; leading "{" doubled ("{{") to treat it as a literal brace rather than
; the start of an (unknown) named constant. See docs/RELEASING.md.
AppId={{#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Derby
DefaultGroupName=Derby
DisableProgramGroupPage=yes
; Default (admin, per-machine Program Files install, one shared copy)
; is unchanged for a real end user -- they still get the normal UAC
; prompt. "commandline" lets tools/build_installer.py's automated
; silent-install verification pass /CURRENTUSER to install into a temp
; directory WITHOUT requesting elevation, since that verification must
; never depend on a UAC consent prompt being clickable (there is no one
; there to click it in an automated/headless run).
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
; No ArchitecturesAllowed/ArchitecturesInstallIn64BitMode: the app is
; built as a 32-bit binary (venv32, see tools/build.py) so it runs
; unmodified on both Windows 7 SP1 32-bit and 64-bit, and on Windows 10
; 64-bit under WOW64 -- a 32-bit-only installer needs neither directive.
MinVersion=6.1sp1
OutputDir=..\release
OutputBaseFilename=Derby-Setup-{#MyAppVersion}
SetupIconFile=..\assets\derby.ico
WizardImageFile=wizard-image.bmp
WizardSmallImageFile=wizard-small-image.bmp
WizardImageStretch=no
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
; No code signing certificate available in this environment -- the
; owner/publisher can add SignTool=... here if/when they get one.

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
; Arabic.isl is NOT bundled with a base Inno Setup 6 install (it is an
; "unofficial" translation, normally fetched from the Inno Setup
; Translations project) -- this build never fetches it (no network
; access anywhere in this project). If you want the installer's own
; chrome (not the app itself, which is already Arabic-only) in Arabic:
;   1. Download Arabic.isl from the Inno Setup Translations project.
;   2. Place it at installer\Languages\Arabic.isl.
;   3. Uncomment the line below.
;Name: "ar"; MessagesFile: "Languages\Arabic.isl"

; Values below are deliberately Arabic even though the "en" wizard
; language is English -- the spec asks for a clear Arabic message on
; these two failure paths and on the uninstall data-safety notice
; specifically, regardless of installer chrome language (Arabic.isl is
; not bundled -- see the [Languages] section above).
[CustomMessages]
en.UninstallDataNotice=إلغاء تثبيت ديربي لن يحذف بياناتك: قاعدة البيانات والنسخ الاحتياطية والصور والإيصالات تبقى في مكانها (مجلد %APPDATA%\Derby ومجلد Documents\Derby). فقط ملفات البرنامج نفسها سيتم حذفها.
en.UCRTWarning=هذا جهاز يعمل بنظام Windows 7، وتعذّر التأكد من وجود تحديث Universal C Runtime (KB2999226) ومن ملفات التشغيل المرفقة مع البرنامج في نفس الوقت. سيتم إكمال التثبيت، ولو واجهت مشكلة عند تشغيل ديربي فثبّت KB2999226 (أو تحديث تراكمي أحدث يتضمنه) من Windows Update.
en.AddDllDirectoryWarning=هذا جهاز يعمل بنظام Windows 7، ويبدو أن تحديث AddDllDirectory (KB2533623) غير مثبّت على هذا الجهاز. سيتم إكمال التثبيت، ولكن لتشغيل ديربي بشكل موثوق من فضلك ثبّت KB2533623 (النسخة المناسبة x86 أو x64) من Windows Update قبل تشغيل البرنامج.

[Tasks]
; Tasks are checked by default unless "unchecked" is given -- there is
; no "checked" flag (an earlier version of this line used one, which
; Inno Setup 6.7.4's compiler rejects as an unknown Tasks flag).
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Derby\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Derby"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,Derby}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Derby"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,Derby}"; Flags: nowait postinstall skipifsilent

; -- Uninstall never deletes %APPDATA%\Derby or Documents\Derby: there is
; deliberately no [UninstallDelete] entry for either, and nothing in
; [Files] installs anything there in the first place -- only {app}
; (the Program Files install folder) is ever touched by uninstall.

[Code]
function IsWindows7(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := (Version.Major = 6) and (Version.Minor = 1);
end;

function IsUCRTAvailable(): Boolean;
(* The frozen build (tools/build.py) bundles api-ms-win-crt-runtime-l1-1-0.dll
   and the rest of the UCRT forwarder DLLs directly next to Derby.exe, so the
   app works even on a Windows 7 box that never got KB2999226 -- Windows 7
   has no API Set resolver, so these are just plain DLLs resolved from the
   app's own install directory first. That install directory is still empty
   at this point (this runs before the Files section copies anything), so
   the check below looks at the installer's own source payload instead -- it
   tells us whether this exact build carries its own copy. It falls back to
   the Windows system directory copy, in case this build somehow didn't
   bundle them, so an already-updated Windows 7 machine is still recognized
   as fine. Registry-based detection of KB2999226 itself is not used here
   because it is unreliable across cumulative updates -- this DLL-presence
   check is what actually determines whether the app can start. *)
var
  SourceDllPath, SystemDllPath: string;
begin
  SourceDllPath := ExpandConstant('{src}\..\dist\Derby\api-ms-win-crt-runtime-l1-1-0.dll');
  SystemDllPath := ExpandConstant('{sys}\api-ms-win-crt-runtime-l1-1-0.dll');
  Result := FileExists(SourceDllPath) or FileExists(SystemDllPath);
end;

function AddDllDirectory(const NewDirectory: string): Longint;
  external 'AddDllDirectory@kernel32.dll stdcall delayload';

function IsAddDllDirectoryAvailable(): Boolean;
(* AddDllDirectory() itself only exists in kernel32.dll on Windows 7 once
   KB2533623 is installed (it ships natively from Windows 8 on). The
   "delayload" import above means the function is resolved the first time
   it is actually called, not at process start -- so calling it here, in a
   try/except, is the only way in Pascal Script to detect whether the
   export exists without crashing the installer outright on a Windows 7
   box that is missing it. Passing a real, harmless directory ({sys}) means
   a genuinely available API call succeeds normally. *)
begin
  Result := True;
  try
    AddDllDirectory(ExpandConstant('{sys}'));
  except
    Result := False;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;

  { Both checks below are non-blocking: a heads-up only, never a reason to
    refuse to install -- derby/__main__.py's own os.add_dll_directory
    fallback (see docs/WIN7-CHECKLIST.md) means the app can still start
    without either update, and the app almost always carries its own UCRT
    DLLs regardless of what Windows Update has applied. }
  if IsWindows7() and not IsUCRTAvailable() then
    MsgBox(CustomMessage('UCRTWarning'), mbInformation, MB_OK);

  if IsWindows7() and not IsAddDllDirectoryAvailable() then
    MsgBox(CustomMessage('AddDllDirectoryWarning'), mbInformation, MB_OK);
end;

procedure InitializeUninstallProgressForm();
begin
  { Guarded: a silent uninstall (/VERYSILENT, used by this project's own
    automated installer verification -- see docs/WIN7-CHECKLIST.md) must
    never block on a MsgBox with nobody there to click it. }
  if not UninstallSilent() then
    MsgBox(CustomMessage('UninstallDataNotice'), mbInformation, MB_OK);
end;
