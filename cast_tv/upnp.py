# -*- coding: utf-8 -*-
"""UPnP / DLNA 发现与控制 (SSDP + SOAP)，纯标准库实现。"""
import html
import http.client
import re
import socket
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .config import SSDP_ADDR, SSDP_PORT, AVT, CM, RC

SEARCH_ST = [
    "ssdp:all",
    "upnp:rootdevice",
    "urn:schemas-upnp-org:device:MediaRenderer:1",
    "urn:schemas-upnp-org:device:MediaServer:1",
]


class UPnPError(Exception):
    """UPnP SOAP 错误。code 为 UPnPErrorCode，或 -1 表示其它错误。"""

    def __init__(self, code, description=""):
        self.code = code
        self.description = description or _err_text(code)
        super().__init__(f"UPnP 错误 {code}: {self.description}")


_ERR_TEXT = {
    401: "无效动作 (Invalid Action)",
    402: "参数错误 (Invalid Args)",
    501: "动作失败 (Action Failed)",
    701: "没有此对象 (No such object)",
    711: "无效 URL (Invalid URL)",
    714: "非法的 MIME 类型 (Illegal MIME-type)",
    715: "内容忙 (Content Busy)",
    716: "无法处理请求 (Cannot process the request)",
    718: "无法解析媒体 (Cannot parse the media)",
}


def _err_text(code):
    return _ERR_TEXT.get(code, "")


def _decode_xml(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class RenderDevice:
    """一个 UPnP MediaRenderer 设备。"""

    def __init__(self, name, model, udn, base_url, services):
        self.name = (name or "未知设备").strip()
        self.model = (model or "").strip()
        self.udn = udn
        self.base_url = base_url
        self.services = services or {}
        self._sink_cache = None

    def __repr__(self):
        return f"<RenderDevice {self.name} {self.base_url}>"

    # ---------- 基础信息 ----------
    def control_url(self, service_type: str):
        for st, cu in self.services.items():
            if service_type in st:
                return urllib.parse.urljoin(self.base_url, cu)
        return None

    def has_service(self, service_type: str) -> bool:
        return any(service_type in st for st in self.services)

    def supports(self, mime_substr: str) -> bool:
        """按 GetProtocolInfo 的 Sink 列表判断是否支持某类型 (大小写不敏感)。"""
        sink = self.protocol_sink()
        m = mime_substr.lower()
        return any(m in s.lower() for s in sink)

    # ---------- SOAP ----------
    def soap(self, service_type, action, args=None, timeout=6):
        url = self.control_url(service_type)
        if not url:
            raise UPnPError(-1, f"该设备没有 {service_type} 服务")
        argstr = "".join(
            f"<{k}>{_esc(v)}</{k}>" for k, v in (args or {}).items()
        )
        body = (
            '<?xml version="1.0"?>\n'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\n'
            f'<s:Body><u:{action} xmlns:u="{service_type}">{argstr}</u:{action}></s:Body>'
            "</s:Envelope>"
        )
        body_bytes = body.encode("utf-8")   # 必须显式 UTF-8，http.client 默认按 latin-1 编码字符串
        u = urllib.parse.urlsplit(url)
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
        try:
            conn.request(
                "POST", urllib.parse.urlunsplit(("", "", u.path, u.query, "")),
                body=body_bytes,
                headers={
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": f'"{service_type}#{action}"',
                    "User-Agent": "PC2TV/1.0 UPnP/1.0",
                },
            )
            resp = conn.getresponse()
            data = resp.read()
        finally:
            conn.close()
        text = _decode_xml(data)
        fault = re.search(r"<faultstring>(.*?)</faultstring>", text, re.S)
        code_m = re.search(r"<errorCode>(.*?)</errorCode>", text, re.S)
        desc_m = re.search(r"<errorDescription>(.*?)</errorDescription>", text, re.S)
        if fault or code_m:
            code = int(code_m.group(1)) if code_m else -1
            desc = desc_m.group(1).strip() if desc_m else (fault.group(1).strip() if fault else "")
            raise UPnPError(code, desc)
        return _strip_ns(text)

    # ---------- AVTransport ----------
    def set_av_transport_uri(self, uri, metadata="", instance=0):
        return self.soap(AVT, "SetAVTransportURI", {
            "InstanceID": str(instance),
            "CurrentURI": uri,
            "CurrentURIMetaData": metadata,
        })

    def play(self, instance=0, speed="1"):
        return self.soap(AVT, "Play", {"InstanceID": str(instance), "Speed": str(speed)})

    def pause(self, instance=0):
        return self.soap(AVT, "Pause", {"InstanceID": str(instance)})

    def stop(self, instance=0):
        try:
            return self.soap(AVT, "Stop", {"InstanceID": str(instance)})
        except UPnPError:
            return None  # 已经停止等情况下忽略

    def seek(self, target, unit="REL_TIME", instance=0):
        return self.soap(AVT, "Seek", {"InstanceID": str(instance), "Unit": unit, "Target": target})

    def get_transport_info(self, instance=0):
        xml = self.soap(AVT, "GetTransportInfo", {"InstanceID": str(instance)})
        return {
            "state": _extract(xml, "CurrentTransportState") or "",
            "status": _extract(xml, "CurrentTransportStatus") or "",
            "speed": _extract(xml, "CurrentSpeed") or "",
        }

    def get_media_info(self, instance=0):
        xml = self.soap(AVT, "GetMediaInfo", {"InstanceID": str(instance)})
        return {
            "uri": _extract(xml, "CurrentURI") or "",
            "duration": _extract(xml, "MediaDuration") or "",
        }

    # ---------- RenderingControl ----------
    def get_volume(self, channel="Master", instance=0):
        xml = self.soap(RC, "GetVolume", {"InstanceID": str(instance), "Channel": channel})
        return int(_extract(xml, "CurrentVolume") or 0)

    def set_volume(self, level, channel="Master", instance=0):
        level = max(0, min(100, int(level)))
        self.soap(RC, "SetVolume", {"InstanceID": str(instance), "Channel": channel,
                                    "DesiredVolume": str(level)})
        return level

    # ---------- ConnectionManager ----------
    def protocol_sink(self):
        """GetProtocolInfo 的 Sink 协议列表（缓存）。"""
        if self._sink_cache is not None:
            return self._sink_cache
        try:
            xml = self.soap(CM, "GetProtocolInfo")
            sink = _extract(xml, "Sink") or ""
        except Exception:
            sink = ""
        self._sink_cache = [s for s in sink.split(",") if s.strip()]
        return self._sink_cache

    # ---------- 便捷判断 ----------
    def is_media_renderer(self):
        return self.has_service(AVT)

    def friendly(self):
        extra = f" [{self.model}]" if self.model else ""
        return f"{self.name}{extra} ({self.base_url})"


def _esc(v):
    return html.escape(str(v), quote=True)


def _strip_ns(text: str) -> str:
    return re.sub(r"</?[\w.]+:", "<", text)


def _extract(xml_text: str, tag: str) -> str:
    m = re.search(rf"<[^>]*{re.escape(tag)}[^>]*>(.*?)</[^>]*{re.escape(tag)}[^>]*>", xml_text, re.S)
    return m.group(1).strip() if m else ""


def build_didl_lite(uri, title, mime, protocol_info=None):
    """构造 DIDL-Lite 元数据，供 SetAVTransportURI 的 CurrentURIMetaData 使用。"""
    if mime.startswith("image/"):
        cls = "object.item.imageItem"
    elif mime.startswith("audio/"):
        cls = "object.item.audioItem"
    else:
        cls = "object.item.videoItem"
    pif = protocol_info or f"http-get:*:{mime}:*"
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
        f'xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">'
        f'<item id="0" parentID="-1" restricted="1">'
        f"<dc:title>{_esc(title)}</dc:title>"
        f"<upnp:class>{cls}</upnp:class>"
        f'<res protocolInfo="{_esc(pif)}">{_esc(uri)}</res>'
        "</item></DIDL-Lite>"
    )


# ---------------------------------------------------------------- 发现
def _msearch(st, target=None, ttl=2.5, timeout=0.5):
    """发送一条 M-SEARCH，返回收集到的 LOCATION 集合。"""
    msg = (
        f"M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        f"MX: {max(1, int(ttl))}\r\n"
        f"ST: {st}\r\n\r\n"
    ).encode()
    locations = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(timeout)
        dests = [(SSDP_ADDR, SSDP_PORT)]
        if target:
            dests.append((target, SSDP_PORT))
        # 设备对 M-SEARCH 的响应时好时坏，重复发送提高命中率
        end = time.time() + ttl
        sent = 0
        while time.time() < end:
            for d in dests:
                try:
                    s.sendto(msg, d)
                except OSError:
                    pass
            sent += 1
            # 每次发送后监听一小段
            listen_until = time.time() + 0.8
            while time.time() < listen_until and time.time() < end:
                try:
                    data, _addr = s.recvfrom(65535)
                except socket.timeout:
                    break
                txt = data.decode(errors="replace")
                m = re.search(r"(?im)^LOCATION:\s*(\S+)\s*$", txt)
                if m:
                    locations.add(m.group(1).strip())
            if sent >= 3:
                # 已发 3 轮，剩下的时间继续收
                while time.time() < end:
                    try:
                        data, _addr = s.recvfrom(65535)
                    except socket.timeout:
                        break
                    txt = data.decode(errors="replace")
                    m = re.search(r"(?im)^LOCATION:\s*(\S+)\s*$", txt)
                    if m:
                        locations.add(m.group(1).strip())
        s.close()
    except OSError:
        pass
    return locations


def _fetch(loc, timeout=4):
    req = urllib.request.Request(loc, headers={"User-Agent": "PC2TV/1.0 UPnP/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _local(tag):
    """去掉 XML 命名空间前缀，只取本地名。"""
    return tag.rsplit("}", 1)[-1]


def parse_description(xml_text, location):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    dev = None
    for el in root.iter():
        if _local(el.tag) == "device":
            dev = el
            break
    if dev is None:
        return None

    def txt(tag):
        for el in dev.iter():
            if _local(el.tag) == tag and el.text and el.text.strip():
                return el.text.strip()
        return ""

    services = {}
    for sv in root.iter():
        if _local(sv.tag) != "service":
            continue
        st = cu = None
        for ch in sv:
            ln = _local(ch.tag)
            if ln == "serviceType" and ch.text and ch.text.strip():
                st = ch.text.strip()
            elif ln == "controlURL" and ch.text and ch.text.strip():
                cu = ch.text.strip()
        if st and cu:
            services[st] = cu
    return RenderDevice(
        name=txt("friendlyName"),
        model=txt("modelName") or txt("modelDescription"),
        udn=txt("UDN"),
        base_url=location,
        services=services,
    )


def discover(target=None, timeout=3.5, progress=None):
    """在局域网发现 UPnP 设备。target 可指定机顶盒 IP 以加速/定向发现。"""
    locations = set()
    for st in SEARCH_ST:
        if progress:
            progress(f"搜索 {st} ...")
        locations |= _msearch(st, target=target, ttl=timeout)
    devices, seen = [], set()
    for loc in sorted(locations):
        if progress:
            progress(f"读取设备描述 {loc}")
        try:
            xml_text = _decode_xml(_fetch(loc))
            dev = parse_description(xml_text, loc)
        except Exception:
            continue
        if dev and dev.udn and dev.udn not in seen:
            seen.add(dev.udn)
            devices.append(dev)
    renderers = [d for d in devices if d.is_media_renderer()]
    others = [d for d in devices if not d.is_media_renderer()]
    return renderers + others


def find_renderer_by_base(devices, base_substr):
    for d in devices:
        if base_substr and base_substr.lower() in d.base_url.lower():
            return d
    return None


def find_renderer_by_name(devices, name_substr):
    for d in devices:
        if name_substr and (name_substr.lower() in d.name.lower()
                            or name_substr.lower() in d.model.lower()
                            or name_substr.lower() in d.base_url.lower()):
            return d
    return None


def pick_best_renderer(devices):
    """挑选最适合投屏的渲染器：优先同时支持 mp4 + mp2t/m3u8 的。"""
    renderers = [d for d in devices if d.is_media_renderer()]
    if not renderers:
        return None
    scored = []
    for d in renderers:
        try:
            sink = " ".join(d.protocol_sink()).lower()
        except Exception:
            sink = ""
        score = 0
        if "video/mp4" in sink:
            score += 10
        if "video/mp2t" in sink or "video/vnd.dlna.mpeg-tts" in sink or "video/ts" in sink:
            score += 8
        if "video/m3u8" in sink or "mpegurl" in sink:
            score += 5
        if "video/x-matroska" in sink or "video/mkv" in sink:
            score += 3
        # 乐播系(HappyCast/多屏互动)实测对实时流兼容性最好，优先选
        nm = f"{d.name} {d.model}".lower()
        if any(k in nm for k in ("happycast", "hpplay", "乐播", "多屏互动")):
            score += 20
        scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]