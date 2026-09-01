from pathlib import Path

from src.app.services.parser import SermonMarkdownParser

parser = SermonMarkdownParser()
ROOT = Path(__file__).resolve().parents[2]


def parse(text):
    return parser.parse_text(text)


def test_date_heading():
    chunks = parse(
        "### 8th Feb, 2026 ###\n"
        "#### Exhortation: Ps. Derrick - The Spirit of Excellence ####\n"
        " - The spirit of excellence sets a man above his fellows.\n"
    )
    assert len(chunks) == 1
    assert chunks[0].date == "2026-02-08"


def test_date_with_trailing_title():
    chunks = parse("### 5th Apr, 2026 - Praying For The Nation Ghana ###\n")
    assert chunks[0].date == "2026-04-05"


def test_missing_year_defaults():
    chunks = parse("### 8th Feb ###\n")
    assert chunks[0].date == "2026-02-08"


def test_header_type_speaker_title():
    chunks = parse(
        "### 8th Feb, 2026 ###\n"
        "#### Exhortation: Ps. Derrick - The Spirit of Excellence ####\n"
        " - note\n"
    )
    c = chunks[0]
    assert (c.topic_type, c.speaker, c.topic_title) == (
        "Exhortation", "Ps. Derrick", "The Spirit of Excellence")


def test_header_type_speaker_only():
    chunks = parse(
        "### 15th Feb, 2026 ###\n"
        "#### MOE: Elder Elvis ####\n"
        " - note\n"
    )
    c = chunks[0]
    assert (c.topic_type, c.speaker, c.topic_title) == ("MOE", "Elder Elvis", "")


def test_header_type_speaker_colon_title():
    chunks = parse(
        "### 15th Mar, 2026 ###\n"
        "#### Exhortation: Pastor Emma: The Need To Be Spiritual ####\n"
        " - note\n"
    )
    c = chunks[0]
    assert (c.topic_type, c.speaker, c.topic_title) == (
        "Exhortation", "Pastor Emma", "The Need To Be Spiritual")


def test_header_speaker_title_no_type():
    chunks = parse(
        "### 5th Apr, 2026 ###\n"
        "#### Ps. Derrick - Leaders in Ghana ####\n"
        " - note\n"
    )
    c = chunks[0]
    assert (c.topic_type, c.speaker, c.topic_title) == (
        "General", "Ps. Derrick", "Leaders in Ghana")


def test_header_speaker_only():
    chunks = parse(
        "### 5th Apr, 2026 ###\n"
        "#### Ps. Solomon ####\n"
        " - note\n"
    )
    c = chunks[0]
    assert (c.topic_type, c.speaker, c.topic_title) == ("General", "Ps. Solomon", "")


def test_header_empty_title():
    chunks = parse(
        "### 22nd Feb, 2026 ###\n"
        "#### Exhortation: Ps. Albert -  ####\n"
        " - note\n"
    )
    c = chunks[0]
    assert (c.topic_type, c.speaker, c.topic_title) == (
        "Exhortation", "Ps. Albert", "")


def test_sub_heading_stays_in_notes():
    text = (
        "### 15th Feb, 2026 ###\n"
        "#### Rhema: Ps. Richard - The Spirit of Might 1 ####\n"
        " - note one\n"
        "##### The Spirit of Might #####\n"
        " - sub note\n"
    )
    chunks = parse(text)
    assert len(chunks) == 1
    assert "The Spirit of Might" in chunks[0].text


def test_multiple_sections_same_date():
    text = (
        "### 15th Feb, 2026 ###\n"
        "#### MOE: Elder Elvis ####\n"
        " - a\n"
        "#### Exhortation: Ps. Solomon - Redeeming The Time ####\n"
        " - b\n"
        "#### Rhema: Ps. Richard - The Spirit of Might 1 ####\n"
        " - c\n"
    )
    chunks = parse(text)
    assert len(chunks) == 3
    assert [c.id for c in chunks] == [
        "2026-02-15_moe_0", "2026-02-15_exhortation_1", "2026-02-15_rhema_2"]


def test_orphan_date_block_becomes_general():
    text = (
        "### 19th July, 2026 ###\n"
        "#\n"
        "- It is literally a sin to not walk in victory.\n"
        "- Phil 3:3 - We worship God in the Spirit.\n"
    )
    chunks = parse(text)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.topic_type == "General"
    assert c.speaker == "Unknown"
    assert c.id == "2026-07-19_general_0"
    assert "sin to not walk" in c.text
    assert "#" not in c.text


def test_scripture_extraction_edge_cases():
    chunks = parse(
        "### 8th Feb, 2026 ###\n"
        "#### Rhema: Ps. Richard - T ####\n"
        " - Matth 22::37 double colon\n"
        " - Luke 17:12-> arrow\n"
        " - 1Cor 16:9 no space\n"
        " - Gen 4:1,17,25 | 1Sam 1:19 pipe\n"
        " - Dan 3:1-7 range\n"
    )
    refs = chunks[0].scriptures
    for expected in ["Matth 22:37", "Luke 17:12", "1Cor 16:9",
                     "Gen 4:1", "1Sam 1:19", "Dan 3:1-7"]:
        assert expected in refs, expected


def test_scriptures_deduplicated():
    chunks = parse(
        "### 8th Feb, 2026 ###\n"
        "#### Rhema: Ps. Richard - T ####\n"
        " - John 3:16 first\n"
        " - John 3:16 again\n"
    )
    assert chunks[0].scriptures == ["John 3:16"]


def test_full_file_all_dates_found():
    chunks = parser.parse_file(str(ROOT / "data/2026-Sermons.md"))
    dates = {c.date for c in chunks}
    assert len(chunks) > 0
    assert "2026-02-08" in dates
    assert "2026-08-30" in dates
    assert len(chunks) >= 40
