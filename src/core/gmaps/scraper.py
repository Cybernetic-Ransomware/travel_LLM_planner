import json
import os
import re
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from src.config.config import settings
from src.core.gmaps.models import ScrapedPlace

_COORDS_IN_AT = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
_COORDS_IN_BANG = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")


def _extract_coords(url: str | None) -> tuple[float | None, float | None]:
    if not url:
        return None, None

    match = _COORDS_IN_AT.search(url)
    if match:
        return float(match.group(1)), float(match.group(2))

    match = _COORDS_IN_BANG.search(url)
    if match:
        return float(match.group(1)), float(match.group(2))

    return None, None


async def _collect_items(page) -> list[ScrapedPlace]:
    items = await page.evaluate(
        """
        () => {
            const cards = Array.from(document.querySelectorAll('div[role="article"]'));
            return cards.map(card => {
                const name = card.querySelector('div[role="heading"]')?.textContent?.trim() || null;
                const address = card.querySelector('div[role="note"]')?.textContent?.trim() || null;
                const link = card.querySelector('a[href*="/maps/"]')?.href || null;
                return { name, address, maps_url: link };
            });
        }
        """
    )

    results: list[ScrapedPlace] = []
    for item in items:
        lat, lng = _extract_coords(item.get("maps_url"))
        results.append(
            ScrapedPlace(
                name=item.get("name"),
                address=item.get("address"),
                maps_url=item.get("maps_url"),
                lat=lat,
                lng=lng,
                raw=item,
            )
        )
    return results


async def _scroll_to_end(page) -> None:
    await page.wait_for_timeout(1200)
    last_count = 0
    stagnation = 0

    for _ in range(60):
        await page.evaluate(
            """
            () => {
                const candidates = Array.from(document.querySelectorAll('*'))
                    .filter(el => el.scrollHeight > el.clientHeight + 10);
                if (candidates.length === 0) return;
                candidates.sort((a, b) => b.scrollHeight - a.scrollHeight);
                const target = candidates[0];
                target.scrollTop = target.scrollHeight;
            }
            """
        )
        await page.wait_for_timeout(800)
        items = await _collect_items(page)
        if len(items) == last_count:
            stagnation += 1
        else:
            stagnation = 0
            last_count = len(items)
        if stagnation >= 3:
            break


async def scrape_public_list(list_url: str) -> tuple[list[ScrapedPlace], str | None]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.goto(list_url, wait_until="domcontentloaded")

        await _accept_consent_if_present(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeoutError:
            await _dump_debug_artifacts(page)
        await _scroll_to_end(page)

        places, list_name = await _collect_from_entitylist(page)
        if not places:
            raw_places = await _collect_items(page)
            places = _dedupe_places(raw_places)

        if not places:
            await _dump_debug_artifacts(page)
        await browser.close()

    return list(places), list_name


async def _accept_consent_if_present(page) -> None:
    # Try common Google consent flows (EU). Best-effort; ignore if not present.
    selectors = [
        'button:has-text("Odrzuć wszystko")',
        'button:has-text("Zaakceptuj wszystko")',
        'button:has-text("Reject all")',
        'button:has-text("Accept all")',
        'form[action*="consent"] button',
    ]

    try:
        for selector in selectors:
            loc = page.locator(selector)
            if await loc.count():
                await loc.first.click(timeout=2000)
                await page.wait_for_timeout(800)
                return
        # Sometimes consent is inside iframe
        for frame in page.frames:
            for selector in selectors:
                loc = frame.locator(selector)
                if await loc.count():
                    await loc.first.click(timeout=2000)
                    await page.wait_for_timeout(800)
                    return
    except Exception:
        return


def _dedupe_places(raw_places: Iterable[ScrapedPlace]) -> list[ScrapedPlace]:
    seen: set[str] = set()
    places: list[ScrapedPlace] = []
    for place in raw_places:
        key = place.gmaps_cid or place.gmaps_place_id or place.maps_url or f"{place.name}|{place.address}"
        if key in seen:
            continue
        seen.add(str(key))
        places.append(place)
    return places


async def _collect_from_entitylist(page) -> tuple[list[ScrapedPlace], str | None]:
    url = await _find_entitylist_url(page)
    if not url:
        return [], None

    response = await page.request.get(url)
    if not response.ok:
        return [], None

    text = await response.text()
    text = text.lstrip(")]}'\n\ufeff")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        await _dump_debug_artifacts(page)
        return [], None

    list_name = _extract_list_name(data)
    places: list[ScrapedPlace] = []

    def walk(node):
        if isinstance(node, list):
            if len(node) > 2 and isinstance(node[1], list):
                try:
                    coords = node[1][5]
                    ids = node[1][6] if len(node[1]) > 6 else None
                    gmaps_place_id = None
                    gmaps_cid = None
                    if isinstance(ids, list):
                        if len(ids) >= 1 and isinstance(ids[0], str):
                            gmaps_place_id = ids[0]
                        if len(ids) >= 2 and isinstance(ids[1], str):
                            gmaps_cid = ids[1]

                    if (
                        isinstance(coords, list)
                        and len(coords) >= 4
                        and isinstance(coords[2], (int, float))
                        and isinstance(coords[3], (int, float))
                    ):
                        name = node[2] if isinstance(node[2], str) else None
                        lat = coords[2]
                        lng = coords[3]
                        if gmaps_cid:
                            maps_url = f"https://www.google.com/maps?cid={gmaps_cid}"
                        else:
                            maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
                        places.append(
                            ScrapedPlace(
                                name=name,
                                address=None,
                                maps_url=maps_url,
                                lat=lat,
                                lng=lng,
                                gmaps_place_id=gmaps_place_id,
                                gmaps_cid=gmaps_cid,
                                raw={"node": node},
                            )
                        )
                except Exception:
                    pass
            for item in node:
                walk(item)

    walk(data)
    return _dedupe_places(places), list_name


async def _find_entitylist_url(page) -> str | None:
    locator = page.locator('link[rel="preload"][href*="entitylist/getlist"]')
    if await locator.count() == 0:
        return None

    href = await locator.first.get_attribute("href")
    if not href:
        return None

    if href.startswith("/"):
        return f"https://www.google.com{href.replace('&amp;', '&')}"
    return href.replace("&amp;", "&")


def _extract_list_name(data: list) -> str | None:
    if not data or not isinstance(data, list):
        return None
    if isinstance(data[0], list) and len(data[0]) > 4 and isinstance(data[0][4], str):
        return data[0][4]
    return None


async def _dump_debug_artifacts(page) -> None:
    if os.getenv("SCRAPER_DEBUG", "0") != "1":
        return

    out_dir = Path(os.getenv("SCRAPER_ARTIFACT_DIR", settings.log_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    with suppress(Exception):
        await page.screenshot(path=str(out_dir / "gmaps_debug.png"), full_page=True)

    with suppress(Exception):
        content = await page.content()
        (out_dir / "gmaps_debug.html").write_text(content, encoding="utf-8")
