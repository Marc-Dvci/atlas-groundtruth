"""Headless screenshot of the running web app.

usage: python scripts/shot.py <url> <out.png> [--wait ms] [--click "text"]... [--js "expr"] [--size 1920x1080]
Steps run in order: wait, then each --click / --js / --sleep in the order given.
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright


def main(argv: list[str]) -> None:
    url, out = argv[0], argv[1]
    w, h = 1920, 1080
    steps: list[tuple[str, str]] = []
    wait = 4000
    i = 2
    while i < len(argv):
        a = argv[i]
        if a == "--size":
            w, h = map(int, argv[i + 1].split("x"))
        elif a == "--wait":
            wait = int(argv[i + 1])
        elif a in ("--click", "--js", "--sleep"):
            steps.append((a[2:], argv[i + 1]))
        i += 2
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        logs: list[str] = []
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        pg.goto(url, wait_until="domcontentloaded")
        pg.wait_for_timeout(wait)
        for kind, arg in steps:
            if kind == "click":
                pg.get_by_text(arg, exact=False).first.click()
            elif kind == "js":
                pg.evaluate(arg)
            elif kind == "sleep":
                pg.wait_for_timeout(int(arg))
        pg.screenshot(path=out)
        b.close()
    for line in logs[-15:]:
        print(line[:300])


if __name__ == "__main__":
    main(sys.argv[1:])
