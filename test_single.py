#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
단일 게시글 수동 전송 스크립트

사용법:
    python test_single.py <POST_ID 또는 URL>

예시:
    python test_single.py 111555915
    python test_single.py https://pf.kakao.com/_FNHuG/111555915
"""

import sys
import re
sys.stdout.reconfigure(encoding='utf-8')

from crawler import crawl_post_detail, send_slack, save_last_post
from playwright.sync_api import sync_playwright


def parse_post_id(arg):
    """POST_ID 또는 URL에서 ID 추출"""
    # URL인 경우: https://pf.kakao.com/_FNHuG/111555915
    match = re.search(r'/(\d+)$', arg)
    if match:
        return match.group(1)
    # 숫자만 입력한 경우
    if arg.isdigit():
        return arg
    return None


def main():
    if len(sys.argv) < 2:
        print("사용법: python test_single.py <POST_ID 또는 URL>")
        print("예시: python test_single.py 111555915")
        print("      python test_single.py https://pf.kakao.com/_FNHuG/111555915")
        sys.exit(1)

    POST_ID = parse_post_id(sys.argv[1])
    if not POST_ID:
        print(f"오류: 유효하지 않은 입력입니다: {sys.argv[1]}")
        sys.exit(1)

    POST_URL = f"https://pf.kakao.com/_FNHuG/{POST_ID}"

    print("=" * 50)
    print(f"수동 전송: {POST_URL}")
    print("=" * 50)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 상세 크롤링
        detail = crawl_post_detail(page, POST_ID)

        print(f"\n[크롤링 결과]")
        print(f"  제목: {detail.get('title', 'N/A')}")
        print(f"  본문: {detail.get('content', 'N/A')[:100]}...")
        print(f"  메뉴: {len(detail.get('menu_names', []))}개")
        print(f"  이미지: {len(detail.get('image_urls', []))}개")

        if detail.get('image_urls'):
            for i, url in enumerate(detail['image_urls']):
                print(f"    [{i+1}] {url[:80]}...")

        browser.close()

    # Slack 전송
    print(f"\n[Slack 전송 중...]")
    send_slack(
        title=detail.get("title") or "새 게시글",
        link=POST_URL,
        content=detail.get("content", ""),
        menu_names=detail.get("menu_names", []),
        image_urls=detail.get("image_urls", [])
    )

    # last_post.txt 업데이트
    save_last_post(POST_ID)
    print(f"\nlast_post.txt 업데이트: {POST_ID}")
    print("완료!")

if __name__ == "__main__":
    main()
