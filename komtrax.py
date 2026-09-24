# -*- coding: utf-8 -*-
"""Komtrax reusable source module (READ-ONLY).

Sections:
  errores: KomtraxFleetError (RATE_LIMITED / HTTP_ERROR / NON_XML_RESPONSE).
  autenticacion: password-grant token + file cache con TTL.
  adquisicion: Fleet snapshot por URL con validacion XML estricta.
  paginacion: recorrido de links next con proteccion anti-ciclos.
  parsing: namespace-agnostic, CumulativeOperatingHours + datetime.
  normalizacion: serial como identidad, espacios en codigos.
  decisiones: comparacion valor + temporal.

Sin PUT/PATCH/DELETE. Importar este modulo no ejecuta red.
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import requests
from mydevelon import parse_fleet_xml, FleetEmptyError
from mydevelon import get_cached_token, is_fetch_allowed, record_fetch


class KomtraxFleetError(RuntimeError):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


KOMTRAX_HOST = "https://isoapi.komtrax.komatsu"
KOMTRAX_SUBSCRIBER = "385177"
KOMTRAX_TOKEN_CACHE = ".komtrax_token.txt"
KOMTRAX_TOKEN_TTL_SECONDS = int(os.getenv("KOMTRAX_TOKEN_TTL_SECONDS", "7000"))
KOMTRAX_FLEET_STATE = ".komtrax_fleet_state.txt"
KOMTRAX_FLEET_MIN_INTERVAL_SECONDS = int(
    os.getenv("KOMTRAX_FLEET_MIN_INTERVAL_SECONDS", "300")
)
KOMTRAX_CLIENT_ID = os.getenv("KOMTRAX_CLIENT_ID")
KOMTRAX_CLIENT_SECRET = os.getenv("KOMTRAX_CLIENT_SECRET")


def get_komtrax_token():
    resp = requests.post(f"{KOMTRAX_HOST}/provider/token",
        data={"grant_type": "password", "username": KOMTRAX_CLIENT_ID, "password": KOMTRAX_CLIENT_SECRET},
        timeout=15)
    if not resp.ok:
        raise RuntimeError(f"Komtrax auth failed: HTTP {resp.status_code}: {resp.text[:100]}")
    return resp.json()["access_token"]

def get_komtrax_token_cached(now=None):
    return get_cached_token(
        KOMTRAX_TOKEN_CACHE,
        KOMTRAX_TOKEN_TTL_SECONDS,
        get_komtrax_token,
        now=now,
    )

def _fleet_link_urls(xml_text, rel):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    wanted = str(rel).strip().lower()
    urls = []
    for child in root:
        if child.tag.split("}")[-1] != "Links":
            continue
        found_rel = ""
        href = ""
        for node in child:
            local = node.tag.split("}")[-1]
            if local == "rel":
                found_rel = (node.text or "").strip().lower()
            elif local == "href":
                href = (node.text or "").strip()
        if found_rel == wanted and href:
            urls.append(href)
    return urls

def _fetch_fleet_url(token, url):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/xml",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            detail = f"Retry-After: {retry_after}"
        else:
            try:
                detail = str(resp.json().get("message", ""))
            except (ValueError, AttributeError):
                detail = ""
        message = f"RATE_LIMITED: {detail}" if detail else "RATE_LIMITED"
        raise KomtraxFleetError(message, retry_after=retry_after)
    if not resp.ok:
        raise KomtraxFleetError(f"HTTP_ERROR: {resp.status_code}")

    content_type = str(resp.headers.get("Content-Type", "unknown"))
    content_type = content_type.split(";", 1)[0].strip().lower()
    body_length = len(resp.text.encode("utf-8", errors="replace"))

    if content_type in {"application/json", "application/problem+json", "text/html"}:
        raise KomtraxFleetError(
            f"NON_XML_RESPONSE: content_type={content_type}, body_length={body_length}"
        )

    try:
        ET.fromstring(resp.text)
    except ET.ParseError as error:
        raise KomtraxFleetError(
            f"NON_XML_RESPONSE: content_type={content_type}, body_length={body_length}"
        ) from error

    return resp.text

def get_komtrax_fleet(token, now=None):
    check_now = now or datetime.now(timezone.utc)
    if not is_fetch_allowed(
        KOMTRAX_FLEET_STATE,
        KOMTRAX_FLEET_MIN_INTERVAL_SECONDS,
        now=check_now,
    ):
        raise KomtraxFleetError(
            "RATE_LIMITED_LOCAL: "
            f"wait {KOMTRAX_FLEET_MIN_INTERVAL_SECONDS}s between Fleet fetches"
        )
    url = f"{KOMTRAX_HOST}/provider/v1/{KOMTRAX_SUBSCRIBER}/Fleet/1"
    text = _fetch_fleet_url(token, url)
    record_fetch(KOMTRAX_FLEET_STATE, now=check_now)
    return text

def get_komtrax_fleet_all(token, now=None, max_pages=10):
    check_now = now or datetime.now(timezone.utc)
    if not is_fetch_allowed(
        KOMTRAX_FLEET_STATE,
        KOMTRAX_FLEET_MIN_INTERVAL_SECONDS,
        now=check_now,
    ):
        raise KomtraxFleetError(
            "RATE_LIMITED_LOCAL: "
            f"wait {KOMTRAX_FLEET_MIN_INTERVAL_SECONDS}s between Fleet fetches"
        )
    pages = []
    seen = set()
    url = f"{KOMTRAX_HOST}/provider/v1/{KOMTRAX_SUBSCRIBER}/Fleet/1"
    while url is not None and len(pages) < max_pages and url not in seen:
        seen.add(url)
        text = _fetch_fleet_url(token, url)
        pages.append(text)
        next_urls = _fleet_link_urls(text, "next")
        url = next_urls[0] if next_urls else None
    record_fetch(KOMTRAX_FLEET_STATE, now=check_now)
    return pages

def normalize_unit(value):
    if value is None:
        return None
    return str(value).replace(" ", "").strip().upper() or None

def parse_komtrax_hours(xml_text):
    try:
        fleet = parse_fleet_xml(xml_text)
    except FleetEmptyError:
        return {}
    result = {}
    for eq in fleet:
        serial = eq.get("serial_number")
        if serial:
            result[str(serial).strip()] = {
                "hours": eq.get("operating_hours"),
                "datetime": eq.get("operating_hours_datetime"),
                "_parse_error": eq.get("_parse_error"),
            }
    return result

def classify_komtrax_gap(kt):
    if kt is None:
        return "ABSENT"
    if kt.get("hours") is not None:
        return "OK"
    if kt.get("_parse_error") is not None:
        return "PARSE_ERROR"
    return "NO_HOURS"

def _coerce_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip())
        except (ValueError, TypeError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed

def decide_comparison(kt_val, ft_val, kt_dt=None, ft_dt=None):
    delta = round(kt_val - ft_val, 2)
    if abs(delta) < 0.01:
        return "SKIP_EQUAL"
    if delta < 0:
        return "REVIEW_OLD_SOURCE"
    kt_parsed = _coerce_dt(kt_dt)
    ft_parsed = _coerce_dt(ft_dt)
    if kt_parsed is not None and ft_parsed is not None and kt_parsed <= ft_parsed:
        return "REVIEW_OLD_SOURCE"
    return "UPDATE"
