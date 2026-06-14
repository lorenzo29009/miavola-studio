<#
  Create (or overwrite) ONE Windows .lnk shortcut for Mariposa Studio, with the
  app icon AND an explicit System.AppUserModel.ID set on it.

  Why the AppUserModelID matters: the app launches through pythonw.exe. Without
  a matching AppUserModelID on an installed shortcut, Windows identifies the
  running app as "Python" — so pinning the taskbar button pins Python, not
  Mariposa Studio. Stamping the SAME id the app sets at runtime
  (SetCurrentProcessExplicitAppUserModelID) onto this shortcut makes the taskbar
  show the real app name + icon and makes "Pin to taskbar" work correctly.

  Invoked per-shortcut by install-windows.ps1 and by the app itself on launch
  (src/core.py:ensure_windows_shortcut) so existing installs self-heal.
#>
param(
    [Parameter(Mandatory=$true)][string]$LnkPath,
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$Arguments = "",
    [string]$WorkDir   = "",
    [string]$Icon      = "",
    [string]$Desc      = "Mariposa Studio",
    [Parameter(Mandatory=$true)][string]$AppId
)

$ErrorActionPreference = 'Stop'

# COM interop: build the shortcut via IShellLinkW, stamp the AppUserModelID via
# IPropertyStore (PKEY_AppUserModel_ID), then persist with IPersistFile.
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace MariposaShortcut {
  [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder n, int c);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string n);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder d, int c);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string d);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder a, int c);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string a);
    void GetHotkey(out short k);
    void SetHotkey(short k);
    void GetShowCmd(out int s);
    void SetShowCmd(int s);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int c, out int i);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string p, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string r, uint res);
    void Resolve(IntPtr hwnd, uint fl);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string f);
  }

  [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPersistFile {
    void GetClassID(out Guid id);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint mode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string f, [MarshalAs(UnmanagedType.Bool)] bool remember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string f);
  }

  [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPropertyStore {
    void GetCount(out uint c);
    void GetAt(uint i, out PropertyKey key);
    void GetValue(ref PropertyKey key, out PropVariant pv);
    void SetValue(ref PropertyKey key, ref PropVariant pv);
    void Commit();
  }

  [StructLayout(LayoutKind.Sequential)] struct PropertyKey { public Guid fmtid; public uint pid; }
  [StructLayout(LayoutKind.Explicit)]   struct PropVariant {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr p;
  }

  [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class CShellLink {}

  public static class Lnk {
    public static void Create(string lnk, string target, string args, string workDir,
                              string icon, string desc, string appId) {
      var link = (IShellLinkW)new CShellLink();
      link.SetPath(target);
      if (!string.IsNullOrEmpty(args))    link.SetArguments(args);
      if (!string.IsNullOrEmpty(workDir)) link.SetWorkingDirectory(workDir);
      if (!string.IsNullOrEmpty(icon))    link.SetIconLocation(icon, 0);
      if (!string.IsNullOrEmpty(desc))    link.SetDescription(desc);

      var store = (IPropertyStore)link;
      // PKEY_AppUserModel_ID = {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, pid 5
      var key = new PropertyKey { fmtid = new Guid("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), pid = 5 };
      var pv  = new PropVariant { vt = 31 /* VT_LPWSTR */, p = Marshal.StringToCoTaskMemUni(appId) };
      store.SetValue(ref key, ref pv);
      store.Commit();
      Marshal.FreeCoTaskMem(pv.p);

      ((IPersistFile)link).Save(lnk, true);
    }
  }
}
"@

# Make sure the parent folder exists (Desktop always does; Start Menu usually).
$dir = Split-Path $LnkPath -Parent
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

[MariposaShortcut.Lnk]::Create($LnkPath, $Target, $Arguments, $WorkDir, $Icon, $Desc, $AppId)
Write-Host "shortcut: $LnkPath"
