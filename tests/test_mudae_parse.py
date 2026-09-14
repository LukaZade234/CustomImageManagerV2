"""Parsing the `$im` character card.

Besides the name, series and rank, a card carries the two things worth keeping:
the gender emoji beside the series and the pool list ("Game & Animanga") under
it. The gender arrives as a custom emoji that `_strip_md` removes, so it has to
be read off the raw description.
"""

import mudae_discord


class _Image:
    def __init__(self, url):
        self.url = url


class _Author:
    def __init__(self, name):
        self.name = name


class _Footer:
    def __init__(self, text):
        self.text = text


class _Fields(list):
    pass


class FakeEmbed:
    """Only the attributes `parse_im_embed` reads."""

    def __init__(self, *, name, description, image_url="https://mudae.net/uploads/1/a~b.png"):
        self.author = _Author(name)
        self.title = None
        self.description = description
        self.image = _Image(image_url)
        self.thumbnail = None
        self.footer = None
        self.fields = _Fields()


def _lookup(name, description):
    return mudae_discord.parse_im_embed(FakeEmbed(name=name, description=description))


class TestCharacterCard:
    def test_female_card(self):
        # The example that motivated this: an all-caps series with the female
        # emoji and an "Animanga roulette" pool line.
        result = _lookup(
            "Aisha Dimoche",
            "AISHA :female:\n"
            "Animanga roulette · 27:kakera:\n"
            "Claim Rank: #53,613\n"
            "Like Rank: #53,145\n"
            "Ayeshah",
        )
        info = result.character
        assert result.type == "character"
        assert info.name == "Aisha Dimoche"
        assert info.series == "AISHA"
        assert info.is_female is True
        assert info.is_male is False
        assert info.pools == "Animanga roulette"
        assert info.rank == "53613"

    def test_male_card_with_a_game_and_animanga_pool(self):
        result = _lookup(
            "9S",
            "NieR: Automata :male:\n"
            "Game & Animanga · 201:kakera:\n"
            "Claim Rank: #622\n"
            "Like Rank: #661\n"
            "YoRHa No.9 Type S (+3)",
        )
        info = result.character
        assert info.name == "9S"
        assert info.series == "NieR: Automata"
        assert info.is_male is True
        assert info.is_female is False
        assert info.pools == "Game & Animanga"
        assert info.rank == "622"

    def test_custom_emoji_form(self):
        # A raw capture carries the gender and kakera as custom Discord emoji,
        # which `_strip_md` removes before the series is read.
        result = _lookup(
            "9S",
            "NieR: Automata <:male:123>\nGame & Animanga · 201<:kakera:456>\nClaim Rank: #622",
        )
        info = result.character
        assert info.series == "NieR: Automata"
        assert info.is_male is True
        assert info.pools == "Game & Animanga"

    def test_both_genders_is_kept(self):
        result = _lookup(
            "Truck-kun",
            "Truck <:female:1><:male:2>\nGame & Animanga · 9\nClaim Rank: #1",
        )
        info = result.character
        assert info.is_female is True
        assert info.is_male is True

    def test_no_gender_or_pool_is_empty(self):
        result = _lookup("Rem", "Re:Zero\nClaim Rank: #3")
        info = result.character
        assert info.is_female is False
        assert info.is_male is False
        assert info.pools == ""

    def test_to_dict_carries_the_new_fields(self):
        result = _lookup("9S", "NieR: Automata :male:\nGame & Animanga · 201\nClaim Rank: #622")
        body = result.to_dict()["character"]
        assert body["is_male"] is True
        assert body["is_female"] is False
        assert body["pools"] == "Game & Animanga"
