# services/article_parser.py - KORJATTU BeautifulSoup-versio

import logging
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import trafilatura
from bs4 import BeautifulSoup
from schemas.parsed_article import NewsContact, ParsedArticle

# --- Logging-konfiguraatio ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- VAKIOT ---
CONTACT_KEYWORDS = [
    "lisätietoja",
    "lisätiedot",
    "yhteystiedot",
    "tiedustelut",
    "contact",
    "media contact",
    "press contact",
    "for more information",
    "weitere informationen",
]

TITLE_KEYWORDS = [
    "toimitusjohtaja",
    "johtaja",
    "päällikkö",
    "vastaava",
    "asiantuntija",
    "koordinaattori",
    "manager",
    "director",
    "CEO",
    "communications",
    "viestintä",
    "spokesperson",
    "partner",
    "founder",
    "osakas",
]

COMPANY_KEYWORDS_FILTER = [
    "oy",
    "ab",
    "ltd",
    "inc",
    "corp",
    "communications",
    "viestintä",
    "rakentaminen",
    "kiinteistö",
    "group",
    "konserni",
    "suomi",
    "finland",
    "consti",
    "afry",
    "osg",
    "korjausrakentaminen",
]

# OPTIMOIDUT regex-patternit (käytetään vain pienille tekstimäärille)
NAME_PATTERN = re.compile(
    r"([A-ZÅÄÖ][a-zåäö]+[ -]?[A-ZÅÄÖ]?[a-zåäö]* [A-ZÅÄÖ][a-zåäö]+)"
)
PHONE_PATTERN = re.compile(
    r"(?:puh\.?|tel\.?|phone)\s*:?\s*([0-9\s\-+()]+)", re.IGNORECASE
)
EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")

# --- APUFUNKTIOT ---


def normalize_phone_number(phone_str: Optional[str]) -> Optional[str]:
    """Siistii puhelinnumeron ja muuttaa sen kansainväliseen +358-muotoon."""
    if not phone_str:
        return None
    cleaned = re.sub(r"[^\d+]", "", phone_str.strip())
    if cleaned.startswith("0"):
        cleaned = "+358" + cleaned[1:]
    return cleaned if cleaned else None


def decode_cloudflare_email(encoded_string: str) -> str:
    """Dekoodaa Cloudflaren suojaaman sähköpostiosoitteen."""
    try:
        key = int(encoded_string[:2], 16)
        return "".join(
            chr(int(encoded_string[i : i + 2], 16) ^ key)
            for i in range(2, len(encoded_string), 2)
        )
    except (ValueError, TypeError, IndexError):
        return ""


def is_valid_person_name(name: str) -> bool:
    """Tarkistaa, onko tunnistettu nimi todennäköisesti henkilön nimi."""
    if len(name) < 5 or len(name) > 50:  # Järkevät rajat
        return False

    name_lower = name.lower()
    parts = name_lower.split()

    # Tarkista että on vähintään 2 sanaa
    if len(parts) < 2:
        return False

    # Ei numeroita
    if re.search(r"\d", name):
        return False

    # Ei yritysavainsanoja
    if any(keyword in parts for keyword in COMPANY_KEYWORDS_FILTER):
        return False

    # Pitää sisältää vokaaleja
    if not re.search(r"[aeiouyåäö]", name_lower):
        return False

    return True


def smart_match_emails_to_names(
    all_names: List[str], all_emails: List[str]
) -> List[NewsContact]:
    """PARANNETTU email-nimi yhdistäminen."""
    contacts = []
    used_emails = set()

    # Suodata kelvolliset nimet
    valid_names = [name for name in all_names if is_valid_person_name(name)]
    valid_names = list(dict.fromkeys(valid_names))  # Poista duplikaatit

    logging.info(f"Kelvolliset nimet: {valid_names}")
    logging.info(f"Emailit: {all_emails}")

    # Yhdistä nimet emaileihin
    for name in valid_names:
        name_parts = name.lower().split()
        if len(name_parts) < 2:
            continue

        first_name, last_name = name_parts[0], name_parts[-1]
        best_email = None

        # Etsi sopiva email
        for email in all_emails:
            if email in used_emails:
                continue

            email_local = email.lower().split("@")[0]

            # Tarkista erilaisia muotoja
            if (
                f"{first_name}.{last_name}" in email_local
                or f"{last_name}.{first_name}" in email_local
                or (first_name in email_local and last_name in email_local)
            ):
                best_email = email
                logging.info(f"✅ Yhdistetty: {name} -> {email}")
                break

        if best_email:
            used_emails.add(best_email)
            contacts.append(
                NewsContact(name=name, email=best_email, contact_type="spokesperson")
            )

    # Jos jäi nimiä ilman emailia ja emaileja ilman nimeä, yhdistä ne
    remaining_names = [
        name for name in valid_names if not any(c.name == name for c in contacts)
    ]
    unused_emails = [email for email in all_emails if email not in used_emails]

    for i, email in enumerate(unused_emails):
        name = remaining_names[i] if i < len(remaining_names) else None
        contacts.append(
            NewsContact(
                name=name,
                email=email,
                contact_type="spokesperson" if name else "general",
            )
        )

    return contacts


def extract_contacts_with_beautifulsoup(
    html_content: str, main_text_content: str
) -> List[NewsContact]:
    """
    NOPEA yhteystietojen poiminta BeautifulSoup:lla.
    Käsittelee vain pieniä, kohdennetuja tekstiosia.
    """
    logging.info("🔍 Aloitetaan BeautifulSoup-pohjainen yhteystietojen poiminta...")

    # 1. Käytä BeautifulSoup:ia löytääksesi contact-sektiot
    soup = BeautifulSoup(html_content, "lxml")
    candidate_texts = []

    # Etsi spesifiset contact-sektiot (nopea DOM-haku)
    contact_selectors = [
        '[id*="contact" i]',  # i = case-insensitive
        '[class*="contact" i]',
        '[id*="yhteys" i]',
        '[class*="yhteys" i]',
        "footer",
        '[id*="info" i]',
        '[class*="info" i]',
    ]

    for selector in contact_selectors:
        elements = soup.select(selector)
        for element in elements:
            text = element.get_text(separator=" ", strip=True)
            if len(text) > 20:  # Vain merkityksellisen kokoiset tekstit
                candidate_texts.append(text)
                logging.debug(f"Löytyi kontaktiosio: {text[:100]}...")

    # 2. Lisää Trafilaturan pääsisältö (tärkeää!)
    if main_text_content:
        candidate_texts.append(main_text_content)

    # 3. Jos ei löytynyt tarpeeksi, etsi nimien ympäriltä
    if len(candidate_texts) < 2:
        logging.info("Vähän kontaktiosioita, etsitään nimien ympäriltä...")
        text_content = soup.get_text(separator=" ", strip=True)

        # Etsi nimet ja ota konteksti niiden ympäriltä (turvallinen tekstimäärä)
        for match in NAME_PATTERN.finditer(text_content):
            start = max(0, match.start() - 100)
            end = min(len(text_content), match.end() + 200)
            context = text_content[start:end]

            # Lisää vain jos sisältää yhteystietoja
            if re.search(r"[@]|puh|tel|phone", context, re.IGNORECASE):
                candidate_texts.append(context)

    # 4. Yhdistä tekstit ja poista duplikaatit
    search_text = "\n".join(set(candidate_texts))  # set() poistaa duplikaatit

    if not search_text:
        logging.warning("Ei löytynyt yhteystietosektioita.")
        return []

    logging.info(
        f"Käsitellään {len(search_text)} merkkiä tekstiä (vs. {len(html_content)} alkuperäistä)"
    )

    # 5. NOPEA regex-haku pienestä tekstimäärästä
    all_emails = list(dict.fromkeys(EMAIL_PATTERN.findall(search_text)))
    all_names = list(dict.fromkeys(NAME_PATTERN.findall(search_text)))
    all_phones = list(dict.fromkeys(PHONE_PATTERN.findall(search_text)))

    # 6. Cloudflare-emailit (nopea haku koko HTML:stä, koska pattern on yksinkertainen)
    cf_pattern = re.compile(r'data-cfemail="([^"]+)"')
    cf_emails = []
    for encoded in cf_pattern.findall(html_content):
        decoded = decode_cloudflare_email(encoded)
        if decoded and "@" in decoded:
            cf_emails.append(decoded)

    all_emails.extend(email for email in cf_emails if email not in all_emails)

    logging.info(
        f"Löydettiin: {len(all_names)} nimeä, {len(all_emails)} emailia, {len(all_phones)} puhelinta"
    )

    if not all_emails:
        logging.warning("Ei emaileja löytynyt.")
        return []

    # 7. Yhdistä tiedot
    contacts = smart_match_emails_to_names(all_names, all_emails)

    # 8. Lisää puhelinnumerot
    for i, contact in enumerate(contacts):
        if i < len(all_phones):
            contact.phone = normalize_phone_number(all_phones[i])

    # 9. Merkitse ensimmäinen primary-kontaktiksi
    if contacts:
        contacts[0].is_primary_contact = True

    logging.info(f"✅ BeautifulSoup-haku valmis: {len(contacts)} kontaktia")
    return contacts


def deduplicate_contacts(contacts: List[NewsContact]) -> List[NewsContact]:
    """Poistaa duplikaatit älykkäästi."""
    unique_contacts = {}

    for contact in contacts:
        key = (contact.email or "noemail").lower().strip()
        if key not in unique_contacts:
            unique_contacts[key] = contact
        else:
            # Yhdistä tiedot
            existing = unique_contacts[key]
            existing.name = existing.name or contact.name
            existing.phone = existing.phone or contact.phone
            existing.title = existing.title or contact.title

    return list(unique_contacts.values())


# --- PÄÄFUNKTIO ---


def to_structured_article(
    url: str, check_contact: bool = False
) -> Optional[ParsedArticle]:
    """NOPEA artikkelin käsittely BeautifulSoup:lla."""
    logging.info(f"🚀 Käsitellään artikkeli: {url}")

    # 1. Nouda HTML
    downloaded_html = trafilatura.fetch_url(url)
    if not downloaded_html:
        logging.error(f"❌ Artikkelin nouto epäonnistui: {url}")
        return None

    # 2. Trafilatura-käsittely
    main_content_text = trafilatura.extract(downloaded_html)
    metadata = trafilatura.extract_metadata(downloaded_html)

    if not main_content_text and not metadata:
        logging.error(f"❌ Trafilatura ei löytänyt sisältöä: {url}")
        return None

    # 3. Luo Markdown
    final_markdown = ""
    if metadata and metadata.title:
        final_markdown = f"# {metadata.title}\n\n"
    if main_content_text:
        # Escapeta Markdown-merkit
        cleaned_text = main_content_text.replace("*", "\\*").replace("_", "\\_")
        final_markdown += cleaned_text.strip()

    # 4. Yhteystiedot (vain jos pyydetty)
    unique_contacts = []
    if check_contact:
        logging.info("🔍 check_contact=True, etsitään yhteystietoja...")
        all_contacts = extract_contacts_with_beautifulsoup(
            downloaded_html, main_content_text
        )
        unique_contacts = deduplicate_contacts(all_contacts)

        logging.info(f"🎉 LOPULLINEN TULOS: {len(unique_contacts)} kontaktia!")
        for i, contact in enumerate(unique_contacts):
            logging.info(f"  {i+1}: {contact.name} - {contact.email} - {contact.phone}")
    else:
        logging.info("ℹ️ check_contact=False, yhteystietojen haku ohitettu.")

    # 5. Julkaisupäivä
    published_dt = None
    if metadata and metadata.date:
        try:
            published_dt = datetime.fromisoformat(metadata.date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            logging.warning(f"⚠️ Päivämäärän käsittely epäonnistui: {metadata.date}")

    return ParsedArticle(
        domain=urlparse(url).netloc.replace("www.", ""),
        published=published_dt,
        markdown=final_markdown.strip(),
        contacts=unique_contacts,
    )
