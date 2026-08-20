# -*- coding: utf-8 -*-
"""系统声音采集辅助：发现 VB-CABLE/立体声混音，切换/恢复默认播放设备。"""
import os
import subprocess
import winreg

_MM_RENDER = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
_FRIENDLY = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
_RENDER_PREFIX = "{0.0.0.00000000}."


def _ps1_path():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "tools", "set_default_audio.ps1")


def render_endpoints():
    """返回 {friendly_name: endpoint_guid}（仅 ACTIVE 状态）。"""
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _MM_RENDER) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(k, sub) as sk:
                        state, _ = winreg.QueryValueEx(sk, "DeviceState")
                        if state != 1:
                            continue
                        with winreg.OpenKey(sk, "Properties") as pk:
                            name, _ = winreg.QueryValueEx(pk, _FRIENDLY)
                        out[name] = sub
                except OSError:
                    continue
    except OSError:
        pass
    return out


def find_cable_input_guid():
    for name, guid in render_endpoints().items():
        if "cable input" in name.lower():
            return guid
    return None


def get_default_render_id():
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", _ps1_path(), "-GetDefault"],
            capture_output=True, text=True, timeout=40)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def set_default_render_id(device_id):
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", _ps1_path(), "-DeviceId", device_id],
            capture_output=True, text=True, timeout=40)
    except Exception:
        pass


def ensure_cable_default(log=print):
    """若默认播放设备不是 CABLE Input，则切换过去并返回 (原设备ID, cableID) 供恢复；已满足则返回 None。"""
    guid = find_cable_input_guid()
    if not guid:
        return None
    cable_id = _RENDER_PREFIX + guid
    default_id = get_default_render_id()
    if not default_id or default_id == cable_id:
        return None
    log("默认播放设备不是 CABLE Input，已临时切换到虚拟声卡（停止投屏后自动恢复）")
    set_default_render_id(cable_id)
    return (default_id, cable_id)


def restore_default(original_id):
    if original_id:
        set_default_render_id(original_id)