#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
카카오톡 채널 소식 크롤러 - Slack 알림 발송
주식회사 밥스토리 채널 (https://pf.kakao.com/_FNHuG)
"""

import os
import sys
import io
import math
import requests
from PIL import Image
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


def download_image(url):
    """URL에서 이미지 다운로드"""
    try:
        # http -> https 변환
        if url.startswith("http://"):
            url = url.replace("http://", "https://")

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return Image.open(io.BytesIO(response.content))
    except Exception as e:
        print(f"    이미지 다운로드 실패: {e}")
    return None


def create_image_collage(image_urls, thumb_size=150, max_cols=4):
    """여러 이미지를 하나의 콜라주로 합성"""
    images = []

    # 이미지 다운로드
    for url in image_urls:
        img = download_image(url)
        if img:
            # RGB로 변환 (RGBA인 경우)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            # 썸네일 크기로 리사이즈
            img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
            images.append(img)

    if not images:
        return None

    # 그리드 계산
    num_images = len(images)
    cols = min(num_images, max_cols)
    rows = math.ceil(num_images / cols)

    # 캔버스 생성 (흰색 배경)
    canvas_width = cols * thumb_size
    canvas_height = rows * thumb_size
    collage = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))

    # 이미지 배치
    for idx, img in enumerate(images):
        row = idx // cols
        col = idx % cols

        # 이미지 중앙 정렬
        x_offset = (thumb_size - img.width) // 2
        y_offset = (thumb_size - img.height) // 2

        x = col * thumb_size + x_offset
        y = row * thumb_size + y_offset

        collage.paste(img, (x, y))

    return collage


def upload_image_to_host(image):
    """이미지를 0x0.st에 업로드하고 URL 반환"""
    try:
        # 이미지를 바이트로 변환
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=85)
        img_byte_arr.seek(0)

        # 0x0.st에 업로드
        response = requests.post(
            'https://0x0.st',
            files={'file': ('collage.jpg', img_byte_arr, 'image/jpeg')},
            timeout=30
        )

        if response.status_code == 200:
            url = response.text.strip()
            print(f"    이미지 업로드 성공: {url}")
            return url
        else:
            print(f"    이미지 업로드 실패: {response.status_code}")
    except Exception as e:
        print(f"    이미지 업로드 오류: {e}")

    return None


def send_slack(title, link, content="", menu_names=None, image_urls=None):
    """Slack 알림 보내기 (전체 내용 + 메뉴 이미지 콜라주 포함)"""
    if menu_names is None:
        menu_names = []
    if image_urls is None:
        image_urls = []

    # Block Kit 형식으로 메시지 구성
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📢 {title}",
                "emoji": True
            }
        }
    ]

    # 본문 내용 추가
    if content:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": content
            }
        })

    # 메뉴 목록 텍스트로 표시
    if menu_names:
        blocks.append({"type": "divider"})
        menu_text = "*🍽️ 오늘의 메뉴*\n"
        menu_text += " • ".join(menu_names)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": menu_text
            }
        })

    # 이미지 처리 (개수에 따라 다르게)
    if image_urls:
        blocks.append({"type": "divider"})
        num_images = len(image_urls)

        # 1~2개: 원본 이미지 직접 사용
        if num_images <= 2:
            print(f"    이미지 {num_images}개 - 원본 URL 사용")
            for i, image_url in enumerate(image_urls):
                # http -> https 변환
                if image_url.startswith("http://"):
                    image_url = image_url.replace("http://", "https://")
                blocks.append({
                    "type": "image",
                    "image_url": image_url,
                    "alt_text": f"메뉴 이미지 {i+1}"
                })

        # 3개 이상: 콜라주로 합성
        else:
            print(f"    이미지 {num_images}개로 콜라주 생성 중...")

            # 콜라주 생성
            collage = create_image_collage(image_urls)

            if collage:
                # 콜라주 업로드
                collage_url = upload_image_to_host(collage)

                if collage_url:
                    # 단일 콜라주 이미지 블록 추가
                    blocks.append({
                        "type": "image",
                        "image_url": collage_url,
                        "alt_text": f"메뉴 이미지 ({num_images}개)"
                    })
                else:
                    # 업로드 실패 시 텍스트로 대체
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"_이미지 {num_images}개 (업로드 실패)_"
                        }
                    })
            else:
                # 콜라주 생성 실패 시 텍스트로 대체
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"_이미지 {num_images}개 (콜라주 생성 실패)_"
                    }
                })

    # 구분선
    blocks.append({"type": "divider"})

    # 링크 버튼 추가
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "전체 보기",
                    "emoji": True
                },
                "url": link,
                "style": "primary"
            }
        ]
    })

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


def crawl_post_detail(page, post_id):
    """게시글 상세 페이지에서 전체 내용과 이미지 크롤링"""
    detail_url = f"https://pf.kakao.com/{CHANNEL_ID}/{post_id}"
    print(f"  상세 페이지 크롤링: {detail_url}")

    page.goto(detail_url)
    page.wait_for_timeout(3000)

    result = {
        "title": "",
        "content": "",
        "menu_names": [],
        "image_urls": []
    }

    try:
        # 게시글 본문 영역에서 제목과 내용 가져오기
        post_data = page.evaluate("""() => {
            // 제외할 키워드 목록
            const excludeKeywords = ['QR', '프로필', '댓글', '소식', '채널홈',
                                      '폰으로', '접속해보세요', '고정됨', '공유하기',
                                      '좋아요', '카카오톡', '더보기'];

            const shouldExclude = (text) => {
                return excludeKeywords.some(keyword => text.includes(keyword));
            };

            let title = '';
            let content = '';

            // 방법 1: article 내부의 strong 태그에서 제목 찾기
            const article = document.querySelector('article');
            if (article) {
                const strong = article.querySelector('strong');
                if (strong) {
                    const text = strong.innerText.trim();
                    if (text && !shouldExclude(text)) {
                        title = text;
                    }
                }

                // article 내부의 텍스트 수집 (이미지, 제목 제외)
                const textNodes = [];
                const walker = document.createTreeWalker(
                    article,
                    NodeFilter.SHOW_TEXT,
                    null,
                    false
                );
                while (walker.nextNode()) {
                    const text = walker.currentNode.textContent.trim();
                    if (text && text.length > 2 &&
                        text !== title && !shouldExclude(text)) {
                        textNodes.push(text);
                    }
                }
                if (textNodes.length > 0) {
                    content = textNodes.slice(0, 5).join('\\n');
                }
            }

            // 방법 2: article이 없으면 main에서 찾기
            if (!title) {
                const main = document.querySelector('main');
                if (main) {
                    const strongs = main.querySelectorAll('strong');
                    for (const strong of strongs) {
                        const text = strong.innerText.trim();
                        if (text && !shouldExclude(text) && text.length > 1) {
                            title = text;
                            break;
                        }
                    }
                }
            }

            return { title, content };
        }""")

        result["title"] = post_data.get("title", "")
        result["content"] = post_data.get("content", "")

        # 메뉴 이름들 가져오기 (p 태그에서)
        menu_names = page.evaluate("""() => {
            const names = [];
            const paragraphs = document.querySelectorAll('p');

            for (const p of paragraphs) {
                const text = p.innerText.trim();
                // 짧은 메뉴 이름만 (1~10자)
                if (text && text.length >= 1 && text.length <= 15 &&
                    !text.includes('채널') && !text.includes('댓글') &&
                    !text.includes('접속') && !text.includes('폰으로')) {
                    // 중복 체크
                    if (!names.includes(text)) {
                        names.push(text);
                    }
                }
            }
            return names;
        }""")

        result["menu_names"] = menu_names

        # 이미지 URL들 가져오기 (중복 제거)
        image_urls = page.evaluate("""() => {
            const urls = [];
            const seenUrls = new Set();
            const images = document.querySelectorAll('img[alt="이미지"]');

            for (const img of images) {
                const src = img.src;
                if (src && !seenUrls.has(src)) {
                    seenUrls.add(src);
                    urls.push(src);
                }
            }
            return urls;
        }""")

        result["image_urls"] = image_urls

    except Exception as e:
        print(f"  상세 크롤링 오류: {e}")

    return result


def crawl_latest_posts():
    """카카오톡 최신 게시글 목록 크롤링 (Playwright 사용)"""
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

                    # 고정 게시글인지 확인
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
                        "is_pinned": is_pinned
                    })

        # ID 기준 내림차순 정렬 (최신순)
        posts.sort(key=lambda x: int(x["id"]), reverse=True)

        browser.close()

    return posts


def crawl_and_send_new_posts(new_posts):
    """새 게시글 상세 크롤링 후 Slack 전송"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for post in new_posts:
            print(f"  - [{post['id']}] {post['title']}")

            # 상세 페이지 크롤링
            detail = crawl_post_detail(page, post["id"])

            # 디버깅 출력
            print(f"    제목: {detail.get('title', 'N/A')}")
            print(f"    본문: {detail.get('content', 'N/A')[:50]}...")
            print(f"    메뉴: {len(detail.get('menu_names', []))}개")
            print(f"    이미지: {len(detail.get('image_urls', []))}개")

            # Slack 전송
            send_slack(
                title=detail.get("title") or post["title"],
                link=post["link"],
                content=detail.get("content", ""),
                menu_names=detail.get("menu_names", []),
                image_urls=detail.get("image_urls", [])
            )

        browser.close()


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

    # 상세 크롤링 및 Slack 전송
    crawl_and_send_new_posts(new_posts)

    # 가장 최신 ID 저장
    latest_id = max(int(p["id"]) for p in posts)
    save_last_post(str(latest_id))
    print(f"최신 게시글 ID 저장: {latest_id}")

    print("=" * 50)
    print("크롤링 완료!")


if __name__ == "__main__":
    main()
