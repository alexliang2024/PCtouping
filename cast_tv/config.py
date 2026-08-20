# -*- coding: utf-8 -*-
"""Global configuration."""

DEFAULT_TARGET_IP = "192.168.5.6"   # 机顶盒 IP
DEFAULT_PORT = 8090                 # PC 端 HTTP 服务端口
MAX_PORT_TRIES = 10                 # 端口被占用时最多向后尝试几个

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900

UPNP_NS = "urn:schemas-upnp-org:device-1-0"
AVT = "urn:schemas-upnp-org:service:AVTransport:1"
CM = "urn:schemas-upnp-org:service:ConnectionManager:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"

DLNA_HEADERS = {
    "contentFeatures.dlna.org": "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000",
    "transferMode.dlna.org": "Streaming",
}

MIME_MAP = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".mkv": "video/x-matroska", ".webm": "video/webm",
    ".avi": "video/x-msvideo", ".wmv": "video/x-ms-wmv", ".asf": "video/x-ms-asf",
    ".mpg": "video/mpeg", ".mpeg": "video/mpeg", ".vob": "video/mpeg",
    ".flv": "video/x-flv", ".f4v": "video/x-flv", ".3gp": "video/3gpp",
    ".ts": "video/mp2t", ".m2ts": "video/mp2t", ".mts": "video/mp2t",
    ".rmvb": "video/vnd.rn-realvideo-vb", ".rm": "video/vnd.rn-realvideo",
    ".mp3": "audio/mpeg", ".wav": "audio/x-wav", ".flac": "audio/flac",
    ".aac": "audio/aac", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".wma": "audio/x-ms-wma",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
    ".m3u8": "video/m3u8",
}