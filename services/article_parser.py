# services/article_parser.py

import logging
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import trafilatura  # type: ignore
from schemas.parsed_article import NewsContact, ParsedArticle

# --- Logging-konfiguraatio ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# THIS TRY TO USE TRAFILATURA TO PARSE ARTICLES
# FOR CONTACT EXTRACTION WE USE CUSTOM LOGIC
# I THINK THERE I STILL IMPROVEMENTS TO DO FOR CONTACTS...
# TODO:: TEST CONTACT EXTRACTION WITH DIFFERENT ARTICLES!

# --- VAKIOT (Constants) ---
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

# Suodatetaan pois yleisiä yritysten nimiin liittyviä sanoja
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

# Paremmat regex-patternit
NAME_PATTERN = re.compile(r"([A-ZÅÄÖ][a-zåäö]+ [A-ZÅÄÖ][a-zåäö]+)")
TITLE_PATTERN = re.compile(
    r"\b((?:" + "|".join(TITLE_KEYWORDS) + r")[\w\s,-]*?)\b", re.IGNORECASE
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
            [
                chr(int(encoded_string[i : i + 2], 16) ^ key)
                for i in range(2, len(encoded_string), 2)
            ]
        )
    except (ValueError, TypeError, IndexError) as e:
        logging.warning(f"Cloudflare-sähköpostin dekoodaus epäonnistui: {e}")
        return ""


def is_valid_person_name(name: str) -> bool:
    """Tarkistaa, onko tunnistettu nimi todennäköisesti henkilön nimi eikä yrityksen nimi."""
    name_lower = name.lower()
    if any(keyword in name_lower.split() for keyword in COMPANY_KEYWORDS_FILTER):
        logging.debug(f"Hylättiin nimi '{name}' yritysavainsanan perusteella.")
        return False
    if not re.search(r"[aeiouyåäö]", name_lower):
        logging.debug(f"Hylättiin nimi '{name}', koska se ei sisällä vokaaleja.")
        return False
    return True


def find_contact_sections_html(html_content: str) -> List[str]:
    """Etsi yhteystieto-osiot HTML:stä - ALKUPERÄINEN TOIMIVA LOGIIKKA!"""
    contact_sections = []

    # 1. Etsi spesifiset yhteystietosektiot
    for keyword in CONTACT_KEYWORDS:
        # Etsi keyword ja sen jälkeen kaikki yhteystiedot
        pattern = rf'({keyword}.*?)(?=<(?:footer|div class="[^"]*footer|div id="[^"]*footer)|$)'
        matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)

        for match in matches:
            person_patterns = [
                r"([A-ZÅÄÖ][a-zåäö]+ [A-ZÅÄÖ][a-zåäö]+[^<]*?(?:puh|tel|email|@)[^<]*?)(?=\n[A-ZÅÄÖ][a-zåäö]+ [A-ZÅÄÖ][a-zåäö]+|\n\n|$)",
                r"([A-ZÅÄÖ][a-zåäö]+ [A-ZÅÄÖ][a-zåäö]+[^<]*?(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[^<]*?)(?=\n[A-ZÅÄÖ]|$)",
            ]

            for person_pattern in person_patterns:
                person_matches = re.findall(
                    person_pattern, match, re.IGNORECASE | re.DOTALL
                )
                contact_sections.extend(person_matches)

            # Jos ei löytynyt henkilöitä, ota koko sektio
            if not any(
                re.findall(pattern, match, re.IGNORECASE | re.DOTALL)
                for pattern in person_patterns
            ):
                contact_sections.append(match)

    p_tags = re.findall(r"<p[^>]*>(.*?)</p>", html_content, re.IGNORECASE | re.DOTALL)
    for p_content in p_tags:
        # Jos <p> sisältää sekä nimen että yhteystiedon
        if re.search(r"[A-ZÅÄÖ][a-zåäö]+ [A-ZÅÄÖ][a-zåäö]+", p_content) and (
            re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", p_content)
            or re.search(r"(?:puh\.?|tel\.?|phone)\s*[0-9]", p_content, re.IGNORECASE)
        ):
            contact_sections.append(p_content)

    logging.info(f"Löydettiin {len(contact_sections)} yhteystietosektiota HTML:stä")
    return contact_sections


def find_contact_sections_text(text: str) -> List[str]:
    """Etsi yhteystieto-osiot tekstistä."""
    contact_sections = []

    # Etsi osiot jotka alkavat yhteystietosanoilla
    for keyword in CONTACT_KEYWORDS:
        pattern = rf"((?:{keyword})[^\n]*(?:\n[^\n]*){{0,10}})"
        sections = re.findall(pattern, text, re.IGNORECASE)
        contact_sections.extend(sections)

    # Varmuuskopio: etsi emailien ympäriltä
    if not contact_sections:
        logging.info(
            "Tekstihaussa ei löytynyt avainsanapohjaisia osioita, käytetään email-kontekstihakua."
        )
        for match in EMAIL_PATTERN.finditer(text):
            start = max(0, match.start() - 200)
            end = min(len(text), match.end() + 200)
            context = text[start:end]
            if any(
                kw in context.lower() for kw in ["puh", "tel", "johtaja", "contact"]
            ):
                contact_sections.append(context)

    logging.info(f"Löydettiin {len(contact_sections)} yhteystietosektiota tekstistä")
    return contact_sections[:2]  # Max 2 sektiota tekstistä


def smart_match_emails_to_names(
    all_names: List[str], all_emails: List[str]
) -> List[NewsContact]:
    """ÄLYKÄS email-nimi yhdistäminen - meidän paras innovaatio!"""
    contacts = []
    used_emails = []

    # Suodata ja deduplikoi nimet
    valid_names = []
    for name in all_names:
        if is_valid_person_name(name) and name not in valid_names:
            valid_names.append(name)
            logging.info(f"Hyväksytty nimi: {name}")

    logging.info(
        f"Aloitetaan älykäs yhdistäminen: {len(valid_names)} nimeä + {len(all_emails)} emailia"
    )

    # 1. Yhdistä nimet emaileihin älykkäästi
    for name in valid_names:
        best_email = None
        name_parts = name.lower().split()

        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = name_parts[-1]

            # Etsi email joka sopii henkilön nimeen
            for email in all_emails:
                if email not in used_emails:
                    email_lower = email.lower()
                    if (
                        (first_name in email_lower and last_name in email_lower)
                        or f"{first_name}.{last_name}" in email_lower
                        or f"{first_name}{last_name}" in email_lower
                    ):
                        best_email = email
                        used_emails.append(email)
                        logging.info(
                            f"✅ Löytyi sopiva email {email} henkilölle {name}"
                        )
                        break

        # Jos ei löytynyt nimiperusteista, ota ensimmäinen käyttämätön
        if not best_email and len(used_emails) < len(all_emails):
            for email in all_emails:
                if email not in used_emails:
                    best_email = email
                    used_emails.append(email)
                    logging.info(
                        f"Käytetään ensimmäistä käyttämätöntä emailia {email} henkilölle {name}"
                    )
                    break

        # Luo kontakti jos on email
        if best_email:
            contacts.append(
                NewsContact(name=name, email=best_email, contact_type="spokesperson")
            )

    # 2. Varmista että kaikki emailit käytetään
    unused_emails = [email for email in all_emails if email not in used_emails]
    for email in unused_emails:
        contacts.append(
            NewsContact(name=None, email=email, contact_type="spokesperson")
        )
        logging.info(f"Luotu kontakti käyttämättömälle emailille: {email}")

    logging.info(f"Älykäs yhdistäminen valmis: {len(contacts)} kontaktia luotu")
    return contacts


def extract_contacts_smart(content: str, is_html: bool) -> List[NewsContact]:
    """Älykkäästi optimoitu yhteystietojen poiminta - KORJATTU!"""

    # 1. Etsi yhteystieto-osiot - käytä alkuperäistä toimivaa logiikkaa
    if is_html:
        contact_sections = find_contact_sections_html(content)
    else:
        contact_sections = find_contact_sections_text(content)

    if not contact_sections:
        logging.warning("Ei löytynyt yhteystietosektioita!")
        return []

    # 2. Kerää kaikki tiedot kaikista sektioista
    all_names = []
    all_emails = []
    all_phones = []

    for section in contact_sections:
        # Siivoa HTML jos tarpeen
        clean_section = re.sub(r"<[^>]+>", " ", section) if is_html else section
        clean_section = re.sub(r"\s+", " ", clean_section).strip()

        if len(clean_section) < 15:
            continue

        # Poimii tiedot
        names = NAME_PATTERN.findall(clean_section)
        emails = EMAIL_PATTERN.findall(clean_section)
        phones = PHONE_PATTERN.findall(clean_section)

        if is_html:
            cf_emails = [
                decode_cloudflare_email(e)
                for e in re.findall(r'data-cfemail="([^"]+)"', section)
            ]
            emails.extend(cf for cf in cf_emails if cf and "@" in cf)

        all_names.extend(names)
        all_emails.extend(emails)
        all_phones.extend(phones)

        logging.debug(
            f"Sektiosta löytyi: {len(names)} nimeä, {len(emails)} emailia, {len(phones)} puhelinta"
        )

    # Poista duplikaatit säilyttäen järjestys
    all_emails = list(dict.fromkeys(all_emails))
    all_names = list(dict.fromkeys(all_names))
    all_phones = list(dict.fromkeys(all_phones))

    logging.info(
        f"Yhteensä löytyi: {len(all_names)} nimeä, {len(all_emails)} emailia, {len(all_phones)} puhelinta"
    )

    # Jos ei löytynyt mitään, kokeile backup-strategiaa
    if not all_emails and not all_names:
        logging.warning(
            "Ei löytynyt emaileja eikä nimiä - kokeillaan backup-strategiaa!"
        )

        # Backup: etsi kaikki emailit ja nimet koko sisällöstä
        if is_html:
            # Siivoa HTML ja etsi kaikki emailit
            clean_content = re.sub(r"<[^>]+>", " ", content)
            clean_content = re.sub(r"\s+", " ", clean_content)

            all_emails = EMAIL_PATTERN.findall(clean_content)
            all_names = NAME_PATTERN.findall(clean_content)

            # Lisää Cloudflare emailit
            cf_emails = [
                decode_cloudflare_email(e)
                for e in re.findall(r'data-cfemail="([^"]+)"', content)
            ]
            all_emails.extend(cf for cf in cf_emails if cf and "@" in cf)

            # Poista duplikaatit
            all_emails = list(dict.fromkeys(all_emails))
            all_names = list(dict.fromkeys(all_names))

            logging.info(
                f"Backup-haku löysi: {len(all_names)} nimeä, {len(all_emails)} emailia"
            )

        if not all_emails:
            logging.error("Ei löytynyt yhtään emailia edes backup-haulla!")
            return []

    contacts = smart_match_emails_to_names(all_names, all_emails)

    # 4. Lisää puhelinnumerot kontakteille
    for i, contact in enumerate(contacts):
        if i < len(all_phones):
            contact.phone = normalize_phone_number(all_phones[i])

    # 5. Merkitse ensimmäinen primary-kontaktiksi
    if contacts:
        contacts[0].is_primary_contact = True

    logging.info(f"Luotu {len(contacts)} kontaktia älykkäällä haulla")
    return contacts


def deduplicate_contacts(contacts: List[NewsContact]) -> List[NewsContact]:
    """Poistaa duplikaatit älykkäästi."""
    unique_contacts = {}

    for contact in contacts:
        # Käytä emailia avaimena, tai nimeä jos ei emailia
        key = contact.email or contact.name or "unknown"
        key = key.lower().strip()

        if key not in unique_contacts:
            unique_contacts[key] = contact
        else:
            # Yhdistä tiedot
            existing = unique_contacts[key]
            existing.name = existing.name or contact.name
            existing.phone = existing.phone or contact.phone
            existing.title = existing.title or contact.title

    result = list(unique_contacts.values())
    logging.info(f"Duplikaattien poiston jälkeen: {len(result)} kontaktia")
    return result


# --- PÄÄFUNKTIO ---


def to_structured_article(url: str) -> Optional[ParsedArticle]:
    """Noutaa, jäsentää ja poimii tiedot artikkelista, mukaan lukien yhteystiedot."""
    logging.info(f"\n*** ALOITETAAN ARTIKKELIN KÄSITTELY ***\nURL: {url}")

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        logging.error(f"Artikkelin nouto epäonnistui: {url}")
        return None

    metadata = trafilatura.extract_metadata(downloaded)
    main_content_markdown = trafilatura.extract(
        downloaded, include_formatting=True, include_links=False
    )

    if not main_content_markdown and not metadata:
        logging.error(f"Trafilatura ei löytänyt sisältöä: {url}")
        return None

    # Luo markdown sisältö
    final_markdown = ""
    if metadata and metadata.title:
        final_markdown = f"# {metadata.title}\n\n"
    if main_content_markdown:
        final_markdown += main_content_markdown.strip()

    logging.info("Aloitetaan yhteystietojen poiminta...")

    # 1. Yritä poimia yhteystiedot raa'asta HTML-datasta (paras tapa)
    html_contacts = extract_contacts_smart(downloaded, is_html=True)

    # 2. Jos HTML-tulos on heikko, yritä myös tekstituloksista
    text_contacts = []
    if not any(c.email and c.name for c in html_contacts) and main_content_markdown:
        logging.info(
            "HTML-haku oli puutteellinen, ajetaan lisäksi tekstipohjainen haku."
        )
        text_contacts = extract_contacts_smart(main_content_markdown, is_html=False)

    # 3. Yhdistä kaikki kontaktit ja poista duplikaatit
    all_contacts = deduplicate_contacts(html_contacts + text_contacts)

    logging.info(
        f"🎉 LOPULLINEN TULOS: {len(all_contacts)} uniikkia kontaktia löydetty!"
    )
    for i, contact in enumerate(all_contacts):
        logging.info(f"  {i+1}: {contact.name} - {contact.email} - {contact.phone}")

    # Käsittele julkaisupäivä
    published_dt = None
    if metadata and metadata.date:
        try:
            published_dt = datetime.fromisoformat(metadata.date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            logging.warning(f"⚠️ Päivämäärän '{metadata.date}' jäsennys epäonnistui.")

    return ParsedArticle(
        domain=urlparse(url).netloc.replace("www.", ""),
        published=published_dt,
        markdown=final_markdown.strip(),
        contacts=all_contacts,
    )
