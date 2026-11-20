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
; "x64compatible" (Inno Setup 6.3+) is the recommended identifier over
; the deprecated "x64" -- matches real x64 Windows (7 SP1, 10) without
; pulling in ARM64's x64 emulation layer, which this project doesn't
; target or test.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
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
en.MissingVCRedist=برنامج ديربي يحتاج إلى Microsoft Visual C++ 2015-2019 Redistributable (x64)، ولم يتم العثور عليه على هذا الجهاز ولم يمكن تثبيته تلقائيًا. من فضلك ثبّته من https://aka.ms/vs/17/release/vc_redist.x64.exe ثم أعد تشغيل هذا المثبت.
en.MissingUCRT=هذا جهاز يعمل بنظام Windows 7، ويبدو أن تحديث Universal C Runtime (KB2999226) غير مثبّت -- برنامج ديربي لن يعمل بدونه. من فضلك ثبّت KB2999226 (أو تحديث تراكمي أحدث يتضمنه) من Windows Update، ثم أعد تشغيل هذا المثبت.

[Tasks]
; Tasks are checked by default unless "unchecked" is given -- there is
; no "checked" flag (an earlier version of this line used one, which
; Inno Setup 6.7.4's compiler rejects as an unknown Tasks flag).
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Derby\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: dontcopy skipifsourcedoesntexist

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
const
  { HKLM\...\VisualStudio\14.0\VC\Runtimes\x64 "Installed"=1 is how the
    VC++ 2015-2019 (vc14x, "Universal CRT" successor) x64 redist
    registers itself. }
  VCRedistRegKey = 'SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64';

function IsVCRedistInstalled(): Boolean;
var
  Installed: Cardinal;
begin
  Result := RegQueryDWordValue(HKEY_LOCAL_MACHINE, VCRedistRegKey, 'Installed', Installed) and (Installed = 1);
end;

function IsWindows7(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := (Version.Major = 6) and (Version.Minor = 1);
end;

function IsUCRTInstalled(): Boolean;
begin
  { KB2999226 (or a later cumulative update that folds it in) installs
    ucrtbase.dll into System32 -- its presence is a reliable, simple
    proxy for "the UCRT update is installed" without parsing the
    installed-updates list. }
  Result := FileExists(ExpandConstant('{sys}\ucrtbase.dll'));
end;

procedure TryInstallBundledVCRedist();
var
  ResultCode: Integer;
begin
  { ExtractTemporaryFile is a procedure (no return value) -- it raises an
    exception on failure rather than returning False, so this is wrapped
    in try/except and the file's actual presence is checked afterward. }
  try
    ExtractTemporaryFile('vc_redist.x64.exe');
  except
    { Fall through to the manual message below. }
  end;

  if FileExists(ExpandConstant('{tmp}\vc_redist.x64.exe')) then
    Exec(ExpandConstant('{tmp}\vc_redist.x64.exe'), '/install /quiet /norestart', '', SW_SHOW,
      ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;

  if IsWindows7() and not IsUCRTInstalled() then
  begin
    MsgBox(CustomMessage('MissingUCRT'), mbError, MB_OK);
    Result := False;
    exit;
  end;

  if not IsVCRedistInstalled() then
  begin
    { Only ever runs a redistributable that ships IN this installer's own
      source tree -- never downloads anything, per this project's
      no-networking rule. }
    if FileExists(ExpandConstant('{src}\redist\vc_redist.x64.exe')) then
      TryInstallBundledVCRedist()
    else
    begin
      MsgBox(CustomMessage('MissingVCRedist'), mbError, MB_OK);
      Result := False;
      exit;
    end;

    if not IsVCRedistInstalled() then
    begin
      MsgBox(CustomMessage('MissingVCRedist'), mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure InitializeUninstallProgressForm();
begin
  { Guarded: a silent uninstall (/VERYSILENT, used by this project's own
    automated installer verification -- see docs/WIN7-CHECKLIST.md) must
    never block on a MsgBox with nobody there to click it. }
  if not UninstallSilent() then
    MsgBox(CustomMessage('UninstallDataNotice'), mbInformation, MB_OK);
end;
