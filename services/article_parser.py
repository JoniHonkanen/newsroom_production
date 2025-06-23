from datetime import datetime
from urllib.parse import urlparse
from schemas.content_block import ContentBlockWeb
from schemas.news_draft import StructuredSourceArticle
import requests
from bs4 import BeautifulSoup, Tag
from typing import List, Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def is_valid_image(src: str) -> bool:
    blacklist = [
        "logo",
        "footer",
        "facebook",
        "x-logo",
        "deloitte",
        "suomen-yrittajat",
        "iab",
    ]
    return src and not any(word in src.lower() for word in blacklist)


def extract_blocks_in_order(main_block: Tag) -> List[ContentBlockWeb]:
    """Extracts content blocks from the main block in a structured order."""
    blocks: List[ContentBlockWeb] = []

    # we dont want to include the footer in the article content
    footer = main_block.find("footer")
    if footer:
        footer.decompose()

    for elem in main_block.descendants:
        if not isinstance(elem, Tag):
            continue

        if elem.name == "h1":
            text = elem.get_text(strip=True)
            if text:
                blocks.append(ContentBlockWeb(type="title", content=text))

        elif elem.name in ["h2", "h3", "h4", "h5", "h6"]:
            text = elem.get_text(strip=True)
            if text:
                blocks.append(ContentBlockWeb(type="subheading", content=text))

        elif elem.name == "p":
            text = elem.get_text(strip=True)
            if text:
                blocks.append(ContentBlockWeb(type="text", content=text))

        elif elem.name in ("ul", "ol"):
            items = [
                li.get_text(strip=True) for li in elem.find_all("li", recursive=False)
            ]
            items = [i for i in items if i]
            if items:
                blocks.append(
                    ContentBlockWeb(type="list", content="\n".join(items), items=items)
                )

        elif elem.name == "img":
            src = elem.get("src", "")
            if is_valid_image(src):
                # Kuvateksti (figcaption), jos kuva on <figure>-elementissä
                figcaption = None
                parent = elem.find_parent("figure")
                if parent:
                    caption_tag = parent.find("figcaption")
                    if caption_tag:
                        figcaption = caption_tag.get_text(strip=True)
                blocks.append(
                    ContentBlockWeb(type="image", content=src, caption=figcaption)
                )

        elif elem.name == "blockquote":
            text = elem.get_text(strip=True)
            if text:
                blocks.append(ContentBlockWeb(type="quote", content=text))

    return blocks


def extract_main_block(soup: BeautifulSoup) -> Tag:
    """Extracts the main content block from the BeautifulSoup object."""
    # 1. Yritä löytää <article>
    main_block = soup.find("article")
    # 2. Jos ei löydy, etsi isoin <div> jossa paljon <p>-tageja
    if not main_block:
        divs = soup.find_all("div")
        if divs:
            main_block = max(divs, key=lambda d: len(d.find_all("p")), default=None)
            if main_block and len(main_block.find_all("p")) < 2:
                main_block = None
    # 3. Fallback: käytä koko soupia
    if not main_block:
        main_block = soup
    return main_block


def to_structured_article(url: str) -> Optional[StructuredSourceArticle]:
    """Fetches an article from the given URL and returns a structured representation."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

    main_block = extract_main_block(soup)
    blocks = extract_blocks_in_order(main_block)

    domain = urlparse(url).netloc.replace("www.", "")
    published = extract_published_time(soup)

    print("\n***MUUTETAAN MARKDOWNIKSI****")
    print(f"URL: {url}")
    print(f"Domain: {domain}")
    markdown = render_article_as_markdown(blocks)
    print("MARKDOWN:")
    print(markdown)

    content_blocks = [b.model_dump() for b in blocks]

    return StructuredSourceArticle(
        url=url,
        domain=domain,
        published=published,
        content_blocks=content_blocks,
        markdown=markdown,
    )


def render_article_as_markdown(blocks: List[ContentBlockWeb]) -> str:
    lines: List[str] = []
    for b in blocks:
        t, c = b.type, b.content
        if t == "title":
            lines.append(f"# {c}")
        elif t == "subheading":
            lines.append(f"## {c}")
        elif t == "text":
            lines.append(c)
        elif t == "list":
            # Oletus: items on annettu, muuten jaetaan rivinvaihoista
            items = b.items or c.split("\n")
            for item in items:
                lines.append(f"- {item}")
        elif t == "quote":
            lines.append("> " + c)
        elif t == "image":
            if isinstance(c, str) and c.startswith("http"):
                if b.caption:
                    lines.append(f"![{b.caption}]({c})")
                else:
                    lines.append(f"![Image]({c})")
            else:
                lines.append(f"*{c}*")
    return "\n\n".join(lines).strip()


def extract_published_time(soup: BeautifulSoup) -> Optional[datetime]:
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        try:
            return datetime.fromisoformat(time_tag["datetime"])
        except ValueError:
            return None
    return None
