; Go Hell Go English patch installer (NSIS 3).
; Built by `python3 -m ghg.package`, which passes PATCH_FILE, OUT_FILE, BASE_SIZE, VERSION, VI_VERSION and
; LICENSE_FILE (and MANUAL_DIR and PROJECT_URL when they exist).
;
; Finding the game: the intended use is "put this setup file in the game folder and run it". .onInit looks for
; the game's data pak in the setup file's own folder ($EXEDIR), then in up to three parent folders (in case it
; was put inside gohellgo\ or gohellgo\Content\Paks\), then in $INSTDIR (the /D= value, or C:\GoGoHellGo).
; When the game is found, the folder page is skipped. When it is not, the user picks the folder.
;
; Install: copies gohellgo\Content\Paks\gohellgo-English_P.pak next to the game's own pak, plus the
; "Manual (English)" folder and the uninstaller. No original game file is changed.
; Uninstall: deletes exactly those, and the uninstall registry entry, so the game is the Japanese original again.
;
; Silent use: Setup.exe /S [/D=C:\path\to\game]   (exit code 2 when the game is not found or is another version)

Unicode true
ManifestDPIAware true
!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef PATCH_FILE | OUT_FILE | BASE_SIZE | VERSION | VI_VERSION | LICENSE_FILE
  !error "build with: python3 -m ghg.package"
!endif
!define PATCH_NAME "gohellgo-English_P.pak"
!define BASE_PAK "gohellgo\Content\Paks\gohellgo-WindowsNoEditor.pak"
!define UNINSTALLER "GoHellGo-English-Uninstall.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\GoHellGoEnglishPatch"

Name "Go Hell Go English Patch"
Caption "Go Hell Go English Patch ${VERSION} Setup"
OutFile "${OUT_FILE}"
InstallDir "C:\GoGoHellGo"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
BrandingText "Go Hell Go English Patch ${VERSION}"

VIProductVersion "${VI_VERSION}"
VIAddVersionKey /LANG=1033 "ProductName" "Go Hell Go English Patch"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "FileDescription" "Go Hell Go English Patch Setup"
VIAddVersionKey /LANG=1033 "Comments" "Free, unofficial fan translation. Requires a full copy of goHELLgo Tsukiotoshiteko."
VIAddVersionKey /LANG=1033 "LegalCopyright" "Free fan translation. No warranty. See the license."

Var Found       ; 1 when the game folder was found without asking
Var FoundNote   ; the paragraph about the game folder on the welcome page
Var OldVersion  ; version of an English patch that is already installed, if any
Var BaseSize

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Go Hell Go English Patch ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "A free, unofficial English fan translation for goHELLgo Tsukiotoshiteko. You need a full copy of the game.$\r$\n$\r$\n$FoundNote$\r$\n$\r$\nThe English text is a machine translation, so some lines may read oddly. Uninstalling brings back the Japanese game.$\r$\n$\r$\nClose the game, then click Next."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${LICENSE_FILE}"
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipFolderPage
!define MUI_DIRECTORYPAGE_TEXT_TOP "Choose the goHELLgo game folder: the one that contains gohellgo.exe.$\r$\n$\r$\nTip: next time, put this setup file in that folder and run it from there. It then finds the game by itself."
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckGameDir
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "The English patch is installed"
!define MUI_FINISHPAGE_TEXT "Start the game the way you usually do. It is now in English.$\r$\n$\r$\nAn English copy of the manual is in the $\"Manual (English)$\" folder.$\r$\n$\r$\nTo go back to Japanese, run ${UNINSTALLER} in the game folder.$\r$\n$\r$\nGame folder:$\r$\n$INSTDIR"
!ifdef PROJECT_URL
  !define MUI_FINISHPAGE_LINK "Report a translation mistake"
  !define MUI_FINISHPAGE_LINK_LOCATION "${PROJECT_URL}"
!endif
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; True when $0 is a goHELLgo game folder.
!macro _IsGameDir _a _b _t _f
  IfFileExists "${_b}\${BASE_PAK}" `${_t}` `${_f}`
!macroend
!define IsGameDir `"" IsGameDir`

Function .onInit
  StrCpy $Found 0
  ; The setup file's own folder, then its parents.
  StrCpy $0 $EXEDIR
  StrCpy $1 0
  ${Do}
    ${If} ${IsGameDir} $0
      StrCpy $INSTDIR $0
      StrCpy $Found 1
      ${Break}
    ${EndIf}
    IntOp $1 $1 + 1
    ${If} $1 > 3
      ${Break}
    ${EndIf}
    GetFullPathName $0 "$0\.."
  ${Loop}
  ; Then the /D= folder or the default one.
  ${If} $Found == 0
  ${AndIf} ${IsGameDir} $INSTDIR
    StrCpy $Found 1
  ${EndIf}

  ${If} $Found == 1
    Call CheckVersion
    ${If} $0 != ""
      MessageBox MB_ICONSTOP|MB_OK "$0" /SD IDOK
      SetErrorLevel 2
      Quit
    ${EndIf}
    StrCpy $FoundNote "Game found in:$\r$\n$INSTDIR"
    ReadRegStr $OldVersion HKLM "${UNINST_KEY}" "DisplayVersion"
    ${If} ${FileExists} "$INSTDIR\gohellgo\Content\Paks\${PATCH_NAME}"
      ${If} $OldVersion == ""
        StrCpy $OldVersion "an earlier version"
      ${EndIf}
      StrCpy $FoundNote "$FoundNote$\r$\n(English patch $OldVersion is installed there. It will be replaced.)"
    ${EndIf}
  ${Else}
    StrCpy $FoundNote "The game was not found next to this file, so you will choose the game folder in a moment."
  ${EndIf}
FunctionEnd

Function SkipFolderPage
  ${If} $Found == 1
    Abort
  ${EndIf}
FunctionEnd

; Sets $0 to an error message, or to "" when $INSTDIR holds the game version this patch was made for.
Function CheckVersion
  ${IfNot} ${IsGameDir} $INSTDIR
    StrCpy $0 "goHELLgo was not found in:$\r$\n$INSTDIR$\r$\n$\r$\nChoose the folder that contains gohellgo.exe."
    Return
  ${EndIf}
  FileOpen $0 "$INSTDIR\${BASE_PAK}" r
  FileSeek $0 0 END $BaseSize
  FileClose $0
  ${If} $BaseSize != ${BASE_SIZE}
    StrCpy $0 "This patch was made for a different version of goHELLgo.$\r$\n$\r$\nExpected game data size: ${BASE_SIZE} bytes$\r$\nFound: $BaseSize bytes$\r$\n$\r$\nNothing was installed. Please report this on the project page, with where you bought the game."
    Return
  ${EndIf}
  StrCpy $0 ""
FunctionEnd

Function CheckGameDir
  Call CheckVersion
  ${If} $0 != ""
    MessageBox MB_ICONSTOP|MB_OK "$0" /SD IDOK
    Abort
  ${EndIf}
FunctionEnd

Section "English patch"
  Call CheckVersion
  ${If} $0 != ""
    DetailPrint "$0"
    MessageBox MB_ICONSTOP|MB_OK "$0" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  SetOutPath "$INSTDIR\gohellgo\Content\Paks"
  File "/oname=${PATCH_NAME}" "${PATCH_FILE}"
!ifdef MANUAL_DIR
  ; English copy of the game's HTML manual, next to the Japanese マニュアル folder
  RMDir /r "$INSTDIR\Manual (English)"
  SetOutPath "$INSTDIR\Manual (English)"
  File /r "${MANUAL_DIR}\*.*"
!endif
  WriteUninstaller "$INSTDIR\${UNINSTALLER}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "Go Hell Go English Patch"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "Go Hell Go English Patch (fan translation)"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\${UNINSTALLER}"'
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\${UNINSTALLER}" /S'
!ifdef PROJECT_URL
  WriteRegStr HKLM "${UNINST_KEY}" "URLInfoAbout" "${PROJECT_URL}"
!endif
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\gohellgo\Content\Paks\${PATCH_NAME}"
  RMDir /r "$INSTDIR\Manual (English)"
  Delete "$INSTDIR\${UNINSTALLER}"
  DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
