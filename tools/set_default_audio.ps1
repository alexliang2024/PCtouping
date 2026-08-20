param(
    [Parameter(Mandatory = $false)][string]$DeviceId = "",
    [switch]$GetDefault
)
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int dataFlow, int dwStateMask, out IMMDeviceCollection devices);
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
    int GetDevice(string id, out IMMDevice deviceName);
    int RegisterEndpointNotificationCallback(object client);
    int UnregisterEndpointNotificationCallback(object client);
}

[Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceCollection {
    int GetCount(out int count);
    int Item(int index, out IMMDevice device);
}

[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
    int Activate(ref Guid id, int clsCtx, IntPtr activationParams, out object iface);
    int OpenPropertyStore(int stgmAccess, out IntPtr properties);
    int GetId(out IntPtr id);
    int GetState(out int state);
}

[Guid("F8679F50-850A-41CF-9C72-430F290290C8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPolicyConfig {
    int GetMixFormat(string pszDeviceName, IntPtr ppFormat);
    int GetDeviceFormat(string pszDeviceName, int bDefault, IntPtr ppFormat);
    int ResetDeviceFormat(string pszDeviceName);
    int SetDeviceFormat(string pszDeviceName, IntPtr pEndpointFormat, IntPtr mixFormat);
    int GetProcessingPeriod(string pszDeviceName, int bDefault, IntPtr pmftDefaultPeriod, IntPtr pmftMinimumPeriod);
    int SetProcessingPeriod(string pszDeviceName, IntPtr pmftPeriod);
    int GetShareMode(string pszDeviceName, IntPtr pMode);
    int SetShareMode(string pszDeviceName, IntPtr mode);
    int GetPropertyValue(string pszDeviceName, int bFxStore, IntPtr key, IntPtr pv);
    int SetPropertyValue(string pszDeviceName, int bFxStore, IntPtr key, IntPtr pv);
    int SetDefaultEndpoint(string pszDeviceName, int role);
    int SetEndpointVisibility(string pszDeviceName, int bVisible);
}

public class AudioDevice {
    private static readonly Guid CLSID_MMDeviceEnumerator = new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E");
    private static readonly Guid CLSID_CPolicyConfigClient = new Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9");

    public static string GetDefaultId() {
        IMMDeviceEnumerator enumerator =
            (IMMDeviceEnumerator)Activator.CreateInstance(Type.GetTypeFromCLSID(CLSID_MMDeviceEnumerator));
        IMMDevice def;
        enumerator.GetDefaultAudioEndpoint(0, 0, out def);
        IntPtr idPtr;
        def.GetId(out idPtr);
        string id = Marshal.PtrToStringUni(idPtr);
        Marshal.FreeCoTaskMem(idPtr);
        return id;
    }

    public static void SetDefault(string deviceId) {
        IPolicyConfig pc =
            (IPolicyConfig)Activator.CreateInstance(Type.GetTypeFromCLSID(CLSID_CPolicyConfigClient));
        for (int role = 0; role <= 2; role++) {
            pc.SetDefaultEndpoint(deviceId, role);
        }
    }
}
"@

if ($GetDefault) {
    [AudioDevice]::GetDefaultId()
    exit 0
}
if ($DeviceId) {
    [AudioDevice]::SetDefault($DeviceId)
    Write-Output "OK"
    exit 0
}
Write-Output "usage: -GetDefault | -DeviceId <endpoint-id>"
exit 1