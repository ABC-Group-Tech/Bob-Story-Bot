#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
카카오톡 채널 소식 크롤러 - Slack 알림 발송
주식회사 밥스토리 채널 (https://pf.kakao.com/_FNHuG)
"""

import os
import sys
import json
import requests
from playwright.sync_api import sync_playwright

# UTF-8 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

# 설정
CHANNEL_ID = "_FNHuG"
TARGET_URL = f"https://pf.kakao.com/{CHANNEL_ID}/posts"
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
HISTORY_FILE = "last_post.txt"


def load_last_post():
    """마지막으로 전송한 게시글 ID 로드"""
    if not os.path.exists(HISTORY_FILE):
        return None
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return content if content else None


def save_last_post(post_id):
    """새 게시글 ID 저장"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(post_id)


def send_slack(title, link, content_preview=""):
    """Slack 알림 보내기 (Block Kit 스타일)"""
    # Block Kit 형식으로 메시지 구성
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "새 카카오톡 소식이 올라왔습니다!",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}*"
            }
        }
    ]

    # 내용 미리보기가 있으면 추가
    if content_preview:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": content_preview[:300] + ("..." if len(content_preview) > 300 else "")
            }
        })

    # 링크 버튼 추가
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "게시글 보기",
                    "emoji": True
                },
                "url": link,
                "style": "primary"
            }
        ]
    })

    # 구분선
    blocks.append({"type": "divider"})

    # 채널 정보
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "주식회사 밥스토리 | 카카오톡 채널"
            }
        ]
    })

    payload = {
        "blocks": blocks,
        "text": f"새 카카오톡 소식: {title}"  # fallback text
    }

    response = requests.post(WEBHOOK_URL, json=payload)
    if response.status_code == 200:
        print(f"Slack 전송 성공: {title}")
    else:
        print(f"Slack 전송 실패: {response.status_code} - {response.text}")


def crawl_latest_posts():
    """카카오톡 최신 게시글 크롤링 (Playwright 사용)"""
    posts = []

    with sync_playwright() as p:
        # Chromium 브라우저 실행 (headless)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"페이지 로딩 중: {TARGET_URL}")
        page.goto(TARGET_URL)

        # 페이지 로딩 대기 (게시글이 나타날 때까지)
        page.wait_for_timeout(3000)

        # 모든 게시글 링크 찾기
        # URL 패턴: /_FNHuG/{post_id}
        post_links = page.query_selector_all(f'a[href^="/{CHANNEL_ID}/"]')

        seen_ids = set()
        for link in post_links:
            href = link.get_attribute("href")
            if not href:
                continue

            # post_id 추출 (예: /_FNHuG/111531719 -> 111531719)
            parts = href.split("/")
            if len(parts) >= 3:
                post_id = parts[2]

                # 숫자인지 확인 (게시글 ID)
                if post_id.isdigit() and post_id not in seen_ids:
                    seen_ids.add(post_id)

                    # 제목 찾기 (strong 태그)
                    title_elem = link.query_selector("strong")
                    title = title_elem.inner_text() if title_elem else "제목 없음"

                    # 내용 미리보기
                    content_elem = link.query_selector("div, span")
                    content_preview = ""
                    if content_elem:
                        try:
                            content_preview = content_elem.inner_text()
                        except:
                            pass

                    # 고정 게시글인지 확인
                    parent = link.evaluate("el => el.closest('div')")
                    is_pinned = False
                    try:
                        parent_text = link.evaluate("el => el.parentElement.innerText")
                        is_pinned = "고정됨" in parent_text
                    except:
                        pass

                    post_link = f"https://pf.kakao.com{href}"

                    posts.append({
                        "id": post_id,
                        "title": title,
                        "link": post_link,
                        "content_preview": content_preview,
                        "is_pinned": is_pinned
                    })

        browser.close()

    # ID 기준 내림차순 정렬 (최신순)
    posts.sort(key=lambda x: int(x["id"]), reverse=True)

    return posts


def get_latest_non_pinned_post(posts):
    """고정되지 않은 최신 게시글 반환"""
    for post in posts:
        if not post.get("is_pinned", False):
            return post
    # 모두 고정이면 첫 번째 반환
    return posts[0] if posts else None


def main():
    if not WEBHOOK_URL:
        print("ERROR: SLACK_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    print("=" * 50)
    print("카카오톡 채널 크롤러 시작")
    print(f"대상: {TARGET_URL}")
    print("=" * 50)

    # 마지막 게시글 ID 로드
    last_post_id = load_last_post()
    print(f"마지막 확인 게시글 ID: {last_post_id or '없음 (최초 실행)'}")

    # 크롤링 실행
    posts = crawl_latest_posts()

    if not posts:
        print("게시글을 찾을 수 없습니다.")
        return

    print(f"총 {len(posts)}개의 게시글 발견")

    # 새 게시글 필터링 (마지막 ID보다 큰 것들)
    new_posts = []
    if last_post_id:
        last_id_num = int(last_post_id)
        new_posts = [p for p in posts if int(p["id"]) > last_id_num]
    else:
        # 최초 실행: 가장 최신 1개만
        latest = get_latest_non_pinned_post(posts)
        if latest:
            new_posts = [latest]

    if not new_posts:
        print("새 게시글이 없습니다.")
        return

    print(f"새 게시글 {len(new_posts)}개 발견!")

    # 오래된 것부터 알림 (시간순)
    new_posts.sort(key=lambda x: int(x["id"]))

    for post in new_posts:
        print(f"  - [{post['id']}] {post['title']}")
        send_slack(
            title=post["title"],
            link=post["link"],
            content_preview=post.get("content_preview", "")
        )

    # 가장 최신 ID 저장
    latest_id = max(int(p["id"]) for p in posts)
    save_last_post(str(latest_id))
    print(f"최신 게시글 ID 저장: {latest_id}")

    print("=" * 50)
    print("크롤링 완료!")


if __name__ == "__main__":
    main()
