# test.py - Tallenna tämä juurihakemistoon newsroom_production/
if __name__ == "__main__":
    from services.article_parser import to_structured_article
    from agents.article_content_extractor_agent import ArticleContentExtractorAgent

    url = input("Anna URL: ").strip()
    if not url:
        url = "https://www.epressi.com/tiedotteet/kaupungit-ja-kunnat/ui-mis-ta-kehotetaan-valt-ta-maan-har-via-lan-ui-ma-pai-kal-la-ja-nak-ka-las-sa.html"  # Oletus
        # url = "https://www.epressi.com/tiedotteet/rakentaminen/turun-jyrkkalassa-kaynnistyy-mittava-koti-kuntoon-saneeraushanke-satsaus-asumisviihtyvyyteen-ja-ekologisuuteen.html"  # Oletus
        # url = "https://yle.fi/a/74-20172180"  # Oletus

    print(f"Testaan URL: {url}")

    # 1. Testaa parsing
    print("1. Parsitaan artikkeli...")
    parsed = to_structured_article(url, check_contact=True)
    if not parsed:
        print("❌ Parsing epäonnistui!")
        exit()

    print(parsed)

    print(f"✅ Parsing onnistui!")
    print(f"   Sisällön pituus: {len(parsed.markdown)} merkkiä")
    print(f"   Domain: {parsed.domain}")
    print(f"   Julkaistu: {parsed.published}")

    # 2. Testaa agentin toiminnot
    print("\n2. Testaan agentin luokittelua...")
    agent = ArticleContentExtractorAgent()
    language = agent._detect_language(parsed.markdown)
    article_type = agent._classify_article_type(url, "Test title", parsed.markdown)

    print(f"   Kieli: {language}")
    print(f"   Tyyppi: {article_type}")

    # 3. Näytä sisältö
    print(f"\n3. Sisällön alku:\n{parsed.markdown[:500]}...")

    print("\n✅ Testi valmis!")
