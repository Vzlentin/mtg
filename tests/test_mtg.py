# Run from the repository root: python3 tests/test_mtg.py

import functools
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MTG = Path(__file__).resolve().parent.parent / "bin" / "mtg"
FIRST_DATA = "2026-10-09T21:00:00.000+00:00"
SECOND_DATA = "2026-10-10T09:00:00.000+00:00"
SWORDS_TEXT = "Exile target creature. Its controller gains life equal to its power."
FEATHER_TEXT = (
    "Flying\nWhenever you cast an instant or sorcery spell that targets a creature you control, exile that card "
    "instead of putting it into your graveyard as it resolves. If you do, return it to your hand at the beginning "
    "of the next end step."
)
FORMATS = (
    "standard",
    "pioneer",
    "modern",
    "legacy",
    "vintage",
    "pauper",
    "commander",
    "duel",
    "alchemy",
    "historic",
    "future",
    "brawl",
    "oathbreaker",
    "paupercommander",
)
ETERNAL = ("modern", "legacy", "vintage", "commander", "duel")


class FixtureHandler(SimpleHTTPRequestHandler):
    """Serves the fixture directory. POST answers with the file at the path and keeps the request body."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        path = Path(self.translate_path(self.path))
        (path.parent / "last_request.json").write_bytes(body)
        answer = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, format, *args):
        pass


def legal(*formats, banned=(), restricted=()):
    states = dict.fromkeys(FORMATS, "not_legal")
    states.update(dict.fromkeys(formats, "legal"))
    states.update(dict.fromkeys(banned, "banned"))
    states.update(dict.fromkeys(restricted, "restricted"))
    return states


def fixture_legalities(version):
    if version == 1:
        crypt = legal(banned=("legacy", "commander", "duel"), restricted=("vintage",))
        swords = legal("legacy", "vintage", "pauper", "commander", "duel")
    else:
        crypt = legal("commander", banned=("legacy", "duel"), restricted=("vintage",))
        swords = legal("modern", "legacy", "vintage", "pauper", "commander", "duel")
    return {
        "jinnie": legal("pioneer", "historic", *ETERNAL),
        "feather": legal("pioneer", "historic", "brawl", "oathbreaker", *ETERNAL),
        "expedite": legal(
            "pioneer",
            "pauper",
            "historic",
            "brawl",
            "oathbreaker",
            "paupercommander",
            *ETERNAL,
            # Future Standard flips with every set and must not show as a change.
            *(("future",) if version == 2 else ()),
        ),
        "gandalf": legal(*ETERNAL),
        "witch": legal(*ETERNAL),
        "wear": legal("pioneer", "historic", *ETERNAL),
        "mountain": legal(*FORMATS),
        "plains": legal(*FORMATS),
        "gamble": legal("legacy", "vintage", "commander", "duel"),
        "crypt": crypt,
        "swords": swords,
        "counterspell": legal("pauper", *ETERNAL),
        "treasure": legal(),
        "dain": legal("modern", "legacy", "vintage", "commander", restricted=("duel",)),
        "rats": legal(*ETERNAL),
        "shields": legal(),
        "mesa": legal(*ETERNAL),
        "speedy": legal("alchemy", "historic"),
        "honor": legal("standard", "pioneer", "pauper", *ETERNAL),
        "chandra": legal("pioneer", "brawl", "oathbreaker", *ETERNAL),
        "kediss": legal(*ETERNAL),
        "bruse": legal(*ETERNAL),
        "legionnaire": legal("paupercommander", *ETERNAL),
        "dwarves": legal("pioneer", *ETERNAL),
        "ornithopter": legal("pauper", *ETERNAL),
        "ornithopter-token": legal(),
    }


def printing(oracle_id, name, set_code, released, **fields):
    card = {
        "object": "card",
        "id": f"{oracle_id}-{set_code}",
        "oracle_id": oracle_id,
        "name": name,
        "lang": "en",
        "released_at": released,
        "layout": "normal",
        "mana_cost": "",
        "cmc": 0.0,
        "type_line": "",
        "oracle_text": "",
        "colors": [],
        "color_identity": [],
        "keywords": [],
        "legalities": legal(*ETERNAL),
        "game_changer": False,
        "reserved": False,
        "digital": False,
        "promo": False,
        "set": set_code,
        "set_type": "expansion",
        "collector_number": "1",
        "rarity": "common",
        "prices": {"eur": None, "eur_foil": None, "usd": None, "usd_foil": None},
        "edhrec_rank": None,
    }
    card.update(fields)
    return card


def reversible_printing():
    face = {
        "oracle_id": "jinnie",
        "name": "Jinnie Fay, Jetmir's Second",
        "mana_cost": "{R/G}{G}{G/W}",
        "cmc": 3.0,
        "type_line": "Legendary Creature — Elf Druid",
        "oracle_text": "If you would create one or more tokens, you may instead create that many 2/2 Cat tokens.",
        "power": "3",
        "toughness": "3",
        "colors": ["G", "R", "W"],
    }
    card = printing(
        "jinnie",
        "Jinnie Fay, Jetmir's Second // Jinnie Fay, Jetmir's Second",
        "sld",
        "2023-01-01",
    )
    for field in (
        "oracle_id",
        "mana_cost",
        "cmc",
        "type_line",
        "oracle_text",
        "colors",
    ):
        del card[field]
    card.update(
        {
            "layout": "reversible_card",
            "color_identity": ["G", "R", "W"],
            "card_faces": [face, dict(face)],
        }
    )
    return card


def fixture_cards(version):
    swords_text = SWORDS_TEXT if version == 1 else SWORDS_TEXT + " Draw a card."
    cards = [
        reversible_printing(),
        printing(
            "jinnie",
            "Jinnie Fay, Jetmir's Second",
            "snc",
            "2022-04-29",
            mana_cost="{R/G}{G}{G/W}",
            cmc=3.0,
            type_line="Legendary Creature — Elf Druid",
            oracle_text="If you would create one or more tokens, you may instead create that many 2/2 Cat tokens.",
            power="3",
            toughness="3",
            color_identity=["G", "R", "W"],
        ),
        # A promo set released the same day must not count as the first printing.
        printing(
            "feather",
            "Feather, the Redeemed",
            "pwar",
            "2019-05-03",
            set_type="promo",
            rarity="rare",
            mana_cost="{R}{W}{W}",
            cmc=3.0,
            type_line="Legendary Creature — Angel",
            oracle_text=FEATHER_TEXT,
            power="3",
            toughness="4",
            color_identity=["R", "W"],
        ),
        printing(
            "feather",
            "Feather, the Redeemed",
            "war",
            "2019-05-03",
            rarity="rare",
            mana_cost="{R}{W}{W}",
            cmc=3.0,
            type_line="Legendary Creature — Angel",
            oracle_text=FEATHER_TEXT,
            power="3",
            toughness="4",
            colors=["R", "W"],
            color_identity=["R", "W"],
            prices={"eur": "0.48", "eur_foil": "2.00", "usd": "1.06", "usd_foil": None},
            edhrec_rank=5656,
        ),
        printing(
            "expedite",
            "Expedite",
            "ymid",
            "1999-01-01",
            digital=True,
            mana_cost="{R}",
            cmc=1.0,
            type_line="Instant",
            oracle_text="Target creature gains haste until end of turn.\nDraw a card.",
            color_identity=["R"],
        ),
        printing(
            "expedite",
            "Expedite",
            "pls",
            "2001-02-05",
            mana_cost="{R}",
            cmc=1.0,
            type_line="Instant",
            oracle_text="Target creature gains haste until end of turn.\nDraw a card.",
            color_identity=["R"],
            prices={"eur": "0.20", "eur_foil": None, "usd": "0.30", "usd_foil": None},
            edhrec_rank=1212,
        ),
        printing(
            "expedite",
            "Expedite",
            "ogw",
            "2016-01-22",
            mana_cost="{R}",
            cmc=1.0,
            type_line="Instant",
            oracle_text="Target creature gains haste until end of turn.\nDraw a card.",
            color_identity=["R"],
            prices={"eur": "0.10", "eur_foil": "0.50", "usd": "0.24", "usd_foil": None},
            edhrec_rank=1212,
        ),
        printing(
            "gandalf",
            "Gandalf, Goblins' Bane // Flameshape",
            "hob",
            "2026-08-14",
            layout="adventure",
            mana_cost="{2}{R} // {1}{R}",
            cmc=3.0,
            type_line="Legendary Creature — Avatar Wizard // Sorcery — Adventure",
            color_identity=["R"],
            card_faces=[
                {
                    "name": "Gandalf, Goblins' Bane",
                    "mana_cost": "{2}{R}",
                    "type_line": "Legendary Creature — Avatar Wizard",
                    "oracle_text": "Whenever you cast a noncreature spell, Gandalf deals 1 damage to each opponent.",
                    "power": "2",
                    "toughness": "3",
                },
                {
                    "name": "Flameshape",
                    "mana_cost": "{1}{R}",
                    "type_line": "Sorcery — Adventure",
                    "oracle_text": "Look at the top two cards of your library and exile them face down.",
                },
            ],
        ),
        printing(
            "witch",
            "Witch Enchanter // Witch-Blessed Meadow",
            "mh3",
            "2024-06-14",
            layout="modal_dfc",
            cmc=4.0,
            type_line="Creature — Human Warlock // Land",
            color_identity=["W"],
            card_faces=[
                {
                    "name": "Witch Enchanter",
                    "mana_cost": "{3}{W}",
                    "type_line": "Creature — Human Warlock",
                    "oracle_text": "When this creature enters, destroy target artifact or enchantment.",
                    "power": "2",
                    "toughness": "2",
                    "colors": ["W"],
                },
                {
                    "name": "Witch-Blessed Meadow",
                    "mana_cost": "",
                    "type_line": "Land",
                    "oracle_text": "{T}: Add {W}.",
                    "colors": [],
                },
            ],
        ),
        printing(
            "wear",
            "Wear // Tear",
            "dgm",
            "2013-05-03",
            layout="split",
            mana_cost="{1}{R} // {W}",
            cmc=3.0,
            type_line="Instant // Instant",
            color_identity=["R", "W"],
            card_faces=[
                {
                    "name": "Wear",
                    "mana_cost": "{1}{R}",
                    "type_line": "Instant",
                    "oracle_text": "Destroy target artifact.",
                },
                {
                    "name": "Tear",
                    "mana_cost": "{W}",
                    "type_line": "Instant",
                    "oracle_text": "Destroy target enchantment.",
                },
            ],
        ),
        printing(
            "mountain",
            "Mountain",
            "lea",
            "1993-08-05",
            type_line="Basic Land — Mountain",
            oracle_text="({T}: Add {R}.)",
            color_identity=["R"],
        ),
        printing(
            "plains",
            "Plains",
            "lea",
            "1993-08-05",
            type_line="Basic Land — Plains",
            oracle_text="({T}: Add {W}.)",
            color_identity=["W"],
        ),
        printing(
            "gamble",
            "Gamble",
            "uma",
            "2018-12-07",
            mana_cost="{R}",
            cmc=1.0,
            type_line="Sorcery",
            oracle_text="Search your library for a card, put that card into your hand, discard a card at random.",
            color_identity=["R"],
            game_changer=version == 1,
        ),
        printing(
            "crypt",
            "Mana Crypt",
            "mps",
            "2016-09-30",
            mana_cost="{0}",
            type_line="Artifact",
            oracle_text="{T}: Add {C}{C}.",
        ),
        printing(
            "swords",
            "Swords to Plowshares",
            "lea",
            "1993-08-05",
            mana_cost="{W}",
            cmc=1.0,
            type_line="Instant",
            oracle_text=swords_text,
            color_identity=["W"],
        ),
        printing(
            "counterspell",
            "Counterspell",
            "lea",
            "1993-08-05",
            mana_cost="{U}{U}",
            cmc=2.0,
            type_line="Instant",
            oracle_text="Counter target spell.",
            color_identity=["U"],
        ),
        printing(
            "treasure",
            "Treasure",
            "txln",
            "2017-09-29",
            layout="token",
            set_type="token",
            type_line="Token Artifact — Treasure",
            oracle_text="{T}, Sacrifice this token: Add one mana of any color.",
        ),
        printing(
            "dain",
            "Dáin Ironfoot",
            "hob",
            "2026-08-14",
            mana_cost="{2}{R}",
            cmc=3.0,
            type_line="Legendary Creature — Dwarf Warrior",
            oracle_text="Whenever Dáin attacks, each equipped attacking creature gains double strike until end of turn.",
            power="1",
            toughness="4",
            color_identity=["R"],
        ),
        printing(
            "rats",
            "Relentless Rats",
            "m11",
            "2010-07-16",
            mana_cost="{1}{B}{B}",
            cmc=3.0,
            type_line="Creature — Rat",
            oracle_text="A deck can have any number of cards named Relentless Rats.",
            color_identity=["B"],
        ),
        printing(
            "shields",
            "Shields Up!",
            "trk",
            "2099-11-13",
            mana_cost="{1}{W}",
            cmc=2.0,
            type_line="Instant",
            oracle_text="Target artifact or creature you control gains hexproof and indestructible until end of turn.",
            color_identity=["W"],
        ),
        printing(
            "speedy",
            "A-Speedy Strike",
            "yone",
            "2023-03-21",
            digital=True,
            mana_cost="{R}",
            cmc=1.0,
            type_line="Instant",
            oracle_text="Target creature gets +2/+0 and gains haste until end of turn.",
            color_identity=["R"],
        ),
        printing(
            "mesa",
            "Arid Mesa",
            "zen",
            "2009-10-02",
            type_line="Land",
            oracle_text="{T}, Pay 1 life, Sacrifice this land: Search your library for a Mountain or Plains card.",
            prices={"eur": None, "eur_foil": "30.00", "usd": None, "usd_foil": "35.00"},
        ),
        printing(
            "chandra",
            "Chandra, Torch of Defiance",
            "kld",
            "2016-09-30",
            rarity="mythic",
            mana_cost="{2}{R}{R}",
            cmc=4.0,
            type_line="Legendary Planeswalker — Chandra",
            oracle_text="+1: Add {R}{R}.",
            loyalty="4",
            color_identity=["R"],
        ),
        printing(
            "kediss",
            "Kediss, Emberclaw Familiar",
            "c20",
            "2020-04-17",
            rarity="uncommon",
            mana_cost="{1}{R}",
            cmc=2.0,
            type_line="Legendary Creature — Elemental Lizard",
            oracle_text="Partner (You can have two commanders if both have partner.)",
            color_identity=["R"],
        ),
        printing(
            "bruse",
            "Bruse Tarl, Boorish Herder",
            "cm2",
            "2016-11-11",
            rarity="mythic",
            mana_cost="{2}{R}{W}",
            cmc=4.0,
            type_line="Legendary Creature — Human Ally",
            oracle_text="Partner (You can have two commanders if both have partner.)",
            color_identity=["R", "W"],
        ),
        printing(
            "legionnaire",
            "Tenth District Legionnaire",
            "gtc",
            "2019-05-03",
            rarity="uncommon",
            mana_cost="{R}{W}",
            cmc=2.0,
            type_line="Creature — Human Soldier",
            oracle_text="Haste",
            color_identity=["R", "W"],
        ),
        printing(
            "dwarves",
            "Seven Dwarves",
            "eld",
            "2019-10-04",
            mana_cost="{1}{R}",
            cmc=2.0,
            type_line="Creature — Dwarf",
            oracle_text="A deck can have up to seven cards named Seven Dwarves.",
            color_identity=["R"],
        ),
        # The token comes first in the file, the card must still win the name.
        printing(
            "ornithopter-token",
            "Ornithopter",
            "tdmu",
            "2022-09-09",
            layout="token",
            set_type="token",
            type_line="Token Artifact Creature — Thopter",
            oracle_text="Flying",
        ),
        printing(
            "ornithopter",
            "Ornithopter",
            "atq",
            "1994-03-01",
            type_line="Artifact Creature — Thopter",
            oracle_text="Flying",
        ),
    ]
    if version == 2:
        cards.append(
            printing(
                "honor",
                "Honor",
                "hob",
                "2026-08-14",
                mana_cost="{W}",
                cmc=1.0,
                type_line="Sorcery",
                oracle_text="Put a +1/+1 counter on target creature.\nDraw a card.",
                color_identity=["W"],
            )
        )
    if version == 2:
        cards = [card for card in cards if card.get("oracle_id") != "shields"]
    legalities = fixture_legalities(version)
    for card in cards:
        oracle_id = card.get("oracle_id") or card["card_faces"][0]["oracle_id"]
        card["legalities"] = legalities[oracle_id]
        if not card.get("colors") and "Land" not in card.get("type_line", ""):
            card["colors"] = card["color_identity"]
    return cards


def tag(tag_id, slug, parents=(), children=(), taggings=()):
    return {
        "object": "tag",
        "id": tag_id,
        "label": slug,
        "slug": slug,
        "type": "oracle",
        "description": None,
        "parent_ids": list(parents),
        "child_ids": list(children),
        "taggings": [
            {"oracle_id": oracle_id, "weight": "median"} for oracle_id in taggings
        ],
    }


def fixture_tags():
    return [
        tag("t-removal", "removal", children=["t-removal-creature"]),
        tag(
            "t-removal-creature",
            "removal-creature",
            parents=["t-removal"],
            taggings=["swords"],
        ),
        tag(
            "t-tutor", "tutor", children=["t-tutor-card", "t-tutor-land", "t-tutor-to"]
        ),
        tag("t-tutor-card", "tutor-card", parents=["t-tutor"], taggings=["gamble"]),
        tag("t-tutor-land", "tutor-land", parents=["t-tutor"], taggings=["mesa"]),
        tag(
            "t-tutor-to", "tutor-to", parents=["t-tutor"], children=["t-tutor-to-hand"]
        ),
        tag(
            "t-tutor-to-hand",
            "tutor-to-hand",
            parents=["t-tutor-to"],
            taggings=["gamble", "mesa"],
        ),
        tag("t-extra-turn", "extra-turn"),
        tag("t-mld", "mass-land-denial"),
    ]


def fixture_sets(version):
    sets = [
        ("lea", "Limited Edition Alpha", "core", "1993-08-05", 295),
        ("pls", "Planeshift", "expansion", "2001-02-05", 143),
        ("dgm", "Dragon's Maze", "expansion", "2013-05-03", 156),
        ("war", "War of the Spark", "expansion", "2019-05-03", 264),
        ("mh3", "Modern Horizons 3", "draft_innovation", "2024-06-14", 303),
        ("hob", "The Hobbit", "expansion", "2026-08-14", 321 if version == 1 else 322),
        ("trk", "Star Trek", "expansion", "2099-11-13", 135),
    ]
    if version == 2:
        sets.append(("nau", "Nauctis: The Sunken Realm", "expansion", "2099-02-05", 3))
    return [
        {
            "object": "set",
            "code": code,
            "name": name,
            "set_type": set_type,
            "released_at": released,
            "card_count": count,
            "digital": False,
            "parent_set_code": None,
        }
        for code, name, set_type, released, count in sets
    ]


def write_gzip_lines(path, items):
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item) + "\n")


def write_fixtures(root, base_url, version, broken=False, cards=None):
    (root / "api").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "spellbook").mkdir(parents=True, exist_ok=True)
    if cards is None:
        cards = fixture_cards(version)
    write_gzip_lines(root / "data" / "default_cards.jsonl.gz", cards)
    if broken:
        (root / "data" / "default_cards.jsonl.gz").write_bytes(
            b"\x1f\x8bnot really gzip"
        )
    write_gzip_lines(
        root / "data" / "rulings.jsonl.gz",
        [
            {
                "object": "ruling",
                "oracle_id": "feather",
                "source": "wotc",
                "published_at": "2019-05-03",
                "comment": "Feather returns the card only if it was exiled this way.",
            }
        ],
    )
    write_gzip_lines(root / "data" / "oracle_tags.jsonl.gz", fixture_tags())
    updated = FIRST_DATA if version == 1 else SECOND_DATA
    bulk = {
        "object": "list",
        "data": [
            {
                "object": "bulk_data",
                "type": name,
                "updated_at": updated,
                "jsonl_download_uri": f"{base_url}/data/{name}.jsonl.gz",
                "compressed_size": 30_000_000,
            }
            for name in ("default_cards", "rulings", "oracle_tags", "all_cards")
        ],
    }
    (root / "api" / "bulk-data").write_text(json.dumps(bulk), encoding="utf-8")
    (root / "api" / "sets").write_text(
        json.dumps({"data": fixture_sets(version)}), encoding="utf-8"
    )
    combos = {
        "results": {
            "included": [
                {
                    "id": "1-2",
                    "uses": [
                        {"card": {"name": "Gamble"}},
                        {"card": {"name": "Expedite"}},
                    ],
                    "produces": [{"feature": {"name": "Infinite fun"}}],
                }
            ],
            "almostIncluded": [],
        }
    }
    (root / "spellbook" / "find-my-combos").write_text(
        json.dumps(combos), encoding="utf-8"
    )


def valid_deck():
    lines = [
        "Commander",
        "1 Feather, the Redeemed (WAR) 197 *F*",
        "",
        "Deck",
        "1 Expedite (OGW) 106",
        "1 Gamble",
        "1 Wear // Tear",
        "1 Witch Enchanter",
        "1 Gandalf, Goblins' Bane",
        "1 Swords to Plowshares",
        "1 Arid Mesa",
        "1x Dain Ironfoot [Creature]",
        "45 Mountain",
        "46 Plains",
        "",
        "Maybeboard",
        "1 Counterspell",
    ]
    return "\n".join(lines) + "\n"


def commander_list(commanders, cards=(), size=100):
    lines = ["Commander", *(f"1 {name}" for name in commanders), "Deck"]
    lines += [f"1 {name}" for name in cards]
    lines.append(f"{size - len(commanders) - len(cards)} Mountain")
    return "\n".join(lines) + "\n"


def start_server(root):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(FixtureHandler, directory=str(root))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def mtg_environment(home, base_url):
    environment = dict(os.environ)
    environment.update(
        {
            "MTG_HOME": str(home),
            "MTG_SCRYFALL_API": f"{base_url}/api",
            "MTG_SPELLBOOK_API": f"{base_url}/spellbook",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    return environment


def run_mtg(environment, *args, stdin=None):
    return subprocess.run(
        [sys.executable, str(MTG), *args],
        env=environment,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


class CardDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="mtg-test-"))
        cls.root = cls.directory / "remote"
        cls.server, base_url = start_server(cls.root)
        write_fixtures(cls.root, base_url, version=1)
        cls.environment = mtg_environment(cls.directory / "home", base_url)
        cls.first_update = run_mtg(cls.environment, "update")
        cls.first_upgrade = run_mtg(cls.environment, "upgrade")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.directory, ignore_errors=True)

    def mtg(self, *args, stdin=None):
        return run_mtg(self.environment, *args, stdin=stdin)

    def test_update_without_data_asks_for_an_upgrade(self):
        self.assertEqual(self.first_update.returncode, 0, self.first_update.stderr)
        self.assertIn("No local card data. Run `mtg upgrade`", self.first_update.stdout)

    def test_upgrade_builds_the_database(self):
        self.assertEqual(self.first_upgrade.returncode, 0, self.first_upgrade.stderr)
        self.assertIn("Database ready:", self.first_upgrade.stdout)
        status = self.mtg("status")
        self.assertIn("Data:     2026-10-09 21:00 UTC", status.stdout)
        self.assertIn("up to date", status.stdout)
        self.assertEqual(
            self.mtg("upgrade").stdout.strip(),
            "Already up to date. Data from 2026-10-09 21:00 UTC.",
        )

    def test_card_prints_exact_oracle_text(self):
        result = self.mtg("card", "feather, the redeemed", "--rulings")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "Feather, the Redeemed {R}{W}{W}\nLegendary Creature — Angel 3/4\n"
            + FEATHER_TEXT,
            result.stdout,
        )
        self.assertIn("first printed 2019-05-03 (war)", result.stdout)
        self.assertIn(
            "legal in pioneer, modern, legacy, vintage, commander", result.stdout
        )
        self.assertIn(
            "Feather returns the card only if it was exiled this way.", result.stdout
        )

    def test_card_finds_faces_accents_and_reversible_cards(self):
        result = self.mtg(
            "card", "Flameshape", "Dain Ironfoot", "Jinnie Fay, Jetmir's Second"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "Gandalf, Goblins' Bane // Flameshape\nGandalf, Goblins' Bane {2}{R}",
            result.stdout,
        )
        self.assertIn("//\nFlameshape {1}{R}\nSorcery — Adventure", result.stdout)
        self.assertIn("Dáin Ironfoot {2}{R}", result.stdout)
        self.assertIn(
            "Jinnie Fay, Jetmir's Second {R/G}{G}{G/W}\nLegendary Creature — Elf Druid 3/3",
            result.stdout,
        )
        self.assertNotIn("Jinnie Fay, Jetmir's Second //", result.stdout)

    def test_card_shows_bans_and_restrictions(self):
        result = self.mtg("card", "Mana Crypt")
        self.assertIn(
            "not legal in the main formats, banned in legacy, commander, "
            "restricted in vintage",
            result.stdout,
        )

    def test_card_prefers_a_card_over_a_token_with_the_same_name(self):
        result = self.mtg("card", "Ornithopter")
        self.assertIn("Ornithopter\nArtifact Creature — Thopter", result.stdout)

    def test_card_price_falls_back_to_foil(self):
        payload = json.loads(self.mtg("card", "Arid Mesa", "--json").stdout)[0]
        self.assertEqual((payload["eur"], payload["usd"]), (30.0, 35.0))

    def test_card_suggests_a_name_for_a_typo(self):
        result = self.mtg("card", "Feathre the Redemed")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Did you mean Feather, the Redeemed?", result.stderr)

    def test_card_json_uses_first_paper_printing_and_cheapest_price(self):
        result = self.mtg("card", "Expedite", "--json", "--prints")
        payload = json.loads(result.stdout)[0]
        self.assertEqual(
            (payload["first_released"], payload["first_set"]), ("2001-02-05", "pls")
        )
        self.assertEqual(payload["eur"], 0.10)
        self.assertEqual(
            [printing["set_code"] for printing in payload["printings"]],
            ["pls", "ogw", "ymid"],
        )

    def search_names(self, *args):
        result = self.mtg("search", *args, "--sort", "name", "--limit", "0", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return [card["name"] for card in json.loads(result.stdout)]

    def test_search_filters(self):
        self.assertEqual(
            self.search_names(
                "--ci", "rw", "--type", "instant", "--mv", "<=1", "--legal", "commander"
            ),
            ["Expedite", "Swords to Plowshares"],
        )
        self.assertEqual(
            self.search_names("--tag", "removal"), ["Swords to Plowshares"]
        )
        self.assertEqual(self.search_names("--gc"), ["Gamble"])
        self.assertEqual(
            self.search_names("--since", "2026-01-01"),
            ["Dáin Ironfoot", "Gandalf, Goblins' Bane // Flameshape", "Shields Up!"],
        )
        self.assertEqual(
            self.search_names("--since", "2026-01-01", "--legal", "commander"),
            ["Dáin Ironfoot", "Gandalf, Goblins' Bane // Flameshape"],
        )
        self.assertEqual(self.search_names("--name", "treasure"), [])
        self.assertEqual(
            self.search_names("--name", "treasure", "--all-layouts"), ["Treasure"]
        )
        self.assertEqual(
            self.search_names(
                "--regex", r"destroy target (artifact|enchantment)", "--type", "instant"
            ),
            ["Wear // Tear"],
        )
        self.assertEqual(
            self.mtg("search", "--text", "draw a card", "--count").stdout.strip(), "1"
        )
        self.assertEqual(
            self.search_names("--colors", "u", "--type", "instant"), ["Counterspell"]
        )
        self.assertEqual(
            self.search_names("--legal", "modern", "--type", "instant"),
            ["Counterspell", "Expedite", "Wear // Tear"],
        )
        self.assertEqual(
            self.search_names("--legal", "vintage", "--name", "crypt"), ["Mana Crypt"]
        )
        self.assertEqual(self.search_names("--legal", "EDH", "--gc"), ["Gamble"])

    def test_search_full_text_and_strict_since(self):
        self.assertEqual(
            self.search_names("--fts", '"exile target creature"'),
            ["Swords to Plowshares"],
        )
        self.assertEqual(self.search_names("--since", "2026-08-14"), ["Shields Up!"])

    def test_search_by_set_and_sort_by_price(self):
        self.assertEqual(self.search_names("--set", "pls"), ["Expedite"])
        cheapest = self.mtg("search", "--sort", "price", "--limit", "3", "--json")
        names = [card["name"] for card in json.loads(cheapest.stdout)]
        self.assertEqual(names, ["Expedite", "Feather, the Redeemed", "Arid Mesa"])
        dearest = self.mtg(
            "search", "--sort", "price", "--reverse", "--limit", "3", "--json"
        )
        names = [card["name"] for card in json.loads(dearest.stdout)]
        self.assertEqual(names, ["Arid Mesa", "Feather, the Redeemed", "Expedite"])

    def test_search_includes_digital_cards_for_digital_formats(self):
        self.assertEqual(self.search_names("--name", "speedy strike"), [])
        self.assertEqual(
            self.search_names("--name", "speedy strike", "--legal", "alchemy"),
            ["A-Speedy Strike"],
        )

    def test_search_rejects_an_unknown_format(self):
        result = self.mtg("search", "--legal", "moden")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown format 'moden'. Did you mean modern?", result.stderr)

    def test_search_rejects_an_unknown_tag(self):
        result = self.mtg("search", "--tag", "removel")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown tag 'removel'", result.stderr)
        self.assertIn("removal", result.stderr)

    def test_deck_accepts_a_valid_commander_list(self):
        result = self.mtg("deck", "-", stdin=valid_deck())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "Format: Commander\nCommander: Feather, the Redeemed (WR)", result.stdout
        )
        self.assertIn("Cards: 100 (1 commander + 99)", result.stdout)
        self.assertIn("(+1 land backs on double-faced cards)", result.stdout)
        self.assertIn("Game Changers: 1 (Gamble)", result.stdout)
        self.assertIn("Tutors: 1 (Gamble)", result.stdout)
        self.assertIn("Not counted: 1 in maybe", result.stdout)
        self.assertIn("Problems: none", result.stdout)

    def test_deck_reports_problems(self):
        deck = (
            "2 Expedite\n"
            "1 Counterspell\n"
            "1 Mana Crypt\n"
            "1 Shields Up!\n"
            "3 Relentless Rats\n"
            "1 Feathre the Redemed\n"
            "SB: 1 Swords to Plowshares\n"
        )
        result = self.mtg(
            "deck", "-", "--commander", "Feather, the Redeemed", stdin=deck
        )
        self.assertEqual(result.returncode, 1)
        problems = result.stdout.split("Problems (")[1]
        for expected in (
            "line 6: no card named 'Feathre the Redemed'. Did you mean Feather, the Redeemed?",
            "the deck has 9 cards. Commander needs exactly 100, commander included.",
            "Expedite: 2 copies, the limit is 1.",
            "Counterspell has identity U, outside the commander's WR.",
            "Relentless Rats has identity B, outside the commander's WR.",
            "Mana Crypt is banned in Commander.",
            "Shields Up! is not released yet (2099-11-13).",
        ):
            self.assertIn(expected, problems)
        self.assertNotIn("Relentless Rats: 3 copies", problems)
        self.assertIn("Not counted: 1 in side", result.stdout)

    def test_deck_checks_combos_and_prints_json(self):
        result = self.mtg("deck", "-", "--combos", "--json", stdin=valid_deck())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            report["combos"]["included"][0]["cards"], ["Gamble", "Expedite"]
        )
        self.assertEqual(report["signals"]["game_changers"], ["Gamble"])
        request = json.loads(
            (self.root / "spellbook" / "last_request.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            request["commanders"], [{"card": "Feather, the Redeemed", "quantity": 1}]
        )
        self.assertIn({"card": "Mountain", "quantity": 45}, request["main"])

    def test_deck_prints_oracle_text_by_type(self):
        result = self.mtg("deck", "-", "--md", stdin=valid_deck())
        self.assertIn("## Commander (1)\n\n### Feather, the Redeemed", result.stdout)
        self.assertIn("### 45x Mountain", result.stdout)
        self.assertIn("**Witch-Blessed Meadow** | Land", result.stdout)

    def test_deck_checks_a_constructed_list(self):
        deck = "Deck\n4 Counterspell\n4 Expedite\n52 Mountain\n\nSideboard\n15 Plains\n"
        result = self.mtg("deck", "-", "--format", "modern", stdin=deck)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Format: Modern\nMain: 60, sideboard: 15", result.stdout)
        self.assertIn("Average MV without lands: 1.5", result.stdout)
        self.assertIn("Curve: 0: 0 | 1: 4 | 2: 4 | 3: 0", result.stdout)
        self.assertNotIn("Game Changers", result.stdout)
        self.assertIn("Problems: none", result.stdout)

    def test_deck_reports_constructed_problems(self):
        deck = (
            "4 Counterspell\n4 Expedite\n1 Mana Crypt\n50 Mountain\n\n"
            "Sideboard\n1 Expedite\n2 Swords to Plowshares\n13 Plains\n"
        )
        result = self.mtg("deck", "-", "--format", "modern", stdin=deck)
        self.assertEqual(result.returncode, 1)
        problems = result.stdout.split("Problems (")[1]
        for expected in (
            "the main deck has 59 cards. Modern needs at least 60.",
            "the sideboard has 16 cards. The maximum is 15.",
            "Expedite: 5 copies, the limit is 4.",
            "Mana Crypt is not legal in Modern.",
            "Swords to Plowshares is not legal in Modern.",
        ):
            self.assertIn(expected, problems)

    def test_deck_limits_restricted_cards_to_one(self):
        one = self.mtg(
            "deck", "-", "--format", "vintage", stdin="1 Mana Crypt\n59 Mountain\n"
        )
        self.assertEqual(one.returncode, 0, one.stdout)
        two = self.mtg(
            "deck", "-", "--format", "vintage", stdin="2 Mana Crypt\n58 Mountain\n"
        )
        self.assertEqual(two.returncode, 1)
        self.assertIn(
            "Mana Crypt: 2 copies, the limit is 1 (restricted in Vintage).", two.stdout
        )

    def test_deck_reads_an_mtgo_sideboard(self):
        deck = "4 Counterspell\n4 Expedite\n52 Mountain\n\n15 Plains\n"
        result = self.mtg("deck", "-", "--format", "modern", stdin=deck)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Main: 60, sideboard: 15", result.stdout)

    def test_deck_without_a_format_checks_nothing_format_specific(self):
        result = self.mtg(
            "deck", "-", stdin="4 Counterspell\n4 Mana Crypt\n52 Mountain\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Format: not given\nMain: 60, sideboard: 0", result.stdout)
        self.assertIn("Warning: no format given", result.stdout)

    def test_deck_allows_up_to_seven_seven_dwarves(self):
        seven = self.mtg(
            "deck", "-", "--format", "modern", stdin="7 Seven Dwarves\n53 Mountain\n"
        )
        self.assertEqual(seven.returncode, 0, seven.stdout)
        eight = self.mtg(
            "deck", "-", "--format", "modern", stdin="8 Seven Dwarves\n52 Mountain\n"
        )
        self.assertIn("Seven Dwarves: 8 copies, the limit is 7.", eight.stdout)

    def test_deck_brawl_accepts_a_planeswalker_commander(self):
        deck = commander_list(["Chandra, Torch of Defiance"])
        brawl = self.mtg("deck", "-", "--format", "brawl", stdin=deck)
        self.assertEqual(brawl.returncode, 0, brawl.stdout)
        commander = self.mtg("deck", "-", stdin=deck)
        self.assertIn(
            "Chandra, Torch of Defiance can't be a commander in Commander.",
            commander.stdout,
        )

    def test_deck_oathbreaker_takes_a_planeswalker_and_a_signature_spell(self):
        deck = commander_list(["Chandra, Torch of Defiance", "Expedite"], size=60)
        result = self.mtg("deck", "-", "--format", "oathbreaker", stdin=deck)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Cards: 60 (2 commander + 58)", result.stdout)

    def test_deck_pauper_commander_needs_an_uncommon_creature(self):
        good = commander_list(["Tenth District Legionnaire"])
        result = self.mtg("deck", "-", "--format", "paupercommander", stdin=good)
        self.assertEqual(result.returncode, 0, result.stdout)
        bad = commander_list(["Feather, the Redeemed"])
        result = self.mtg("deck", "-", "--format", "pauper commander", stdin=bad)
        self.assertIn(
            "Feather, the Redeemed can't be a commander in Pauper Commander.",
            result.stdout,
        )

    def test_deck_duel_rejects_a_restricted_commander(self):
        restricted = commander_list(["Dáin Ironfoot"])
        result = self.mtg("deck", "-", "--format", "duel", stdin=restricted)
        self.assertIn(
            "Dáin Ironfoot can't be a commander in Duel Commander (restricted).",
            result.stdout,
        )
        in_the_deck = commander_list(["Feather, the Redeemed"], ["Dáin Ironfoot"])
        result = self.mtg("deck", "-", "--format", "duel", stdin=in_the_deck)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_deck_checks_partner_commanders(self):
        partners = commander_list(
            ["Kediss, Emberclaw Familiar", "Bruse Tarl, Boorish Herder"]
        )
        result = self.mtg("deck", "-", stdin=partners)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Warning", result.stdout)
        no_partners = commander_list(["Feather, the Redeemed", "Dáin Ironfoot"])
        result = self.mtg("deck", "-", stdin=no_partners)
        self.assertIn(
            "Warning: two commanders, but not both have a partner or background ability.",
            result.stdout,
        )

    def test_deck_commander_flag_takes_one_copy_from_the_list(self):
        deck = "2 Feather, the Redeemed\n97 Mountain\n"
        result = self.mtg(
            "deck", "-", "--commander", "Feather, the Redeemed", stdin=deck
        )
        self.assertIn("Cards: 99 (1 commander + 98)", result.stdout)
        self.assertIn("Feather, the Redeemed: 2 copies, the limit is 1.", result.stdout)

    def test_sql_is_read_only(self):
        result = self.mtg("sql", "SELECT name FROM cards WHERE game_changer = 1")
        self.assertEqual(result.stdout, "name\nGamble\n")
        result = self.mtg("sql", "DELETE FROM cards")
        self.assertEqual(result.returncode, 2)
        self.assertIn("readonly", result.stderr)

    def test_sets_by_type(self):
        result = self.mtg("sets", "--type", "core,draft_innovation")
        self.assertEqual(
            [line.split()[1] for line in result.stdout.splitlines()], ["lea", "mh3"]
        )

    def test_update_json_when_up_to_date(self):
        report = json.loads(self.mtg("update", "--json").stdout)
        self.assertEqual(
            (report["has_data"], report["upgrade_available"]), (True, False)
        )

    def test_network_error_is_a_short_message(self):
        environment = dict(self.environment, MTG_SCRYFALL_API="http://127.0.0.1:9/api")
        result = run_mtg(environment, "update")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("mtg: network error:"), result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_sets_since_a_date(self):
        result = self.mtg("sets", "--since", "2026-01-01")
        self.assertEqual(
            [line.split()[1] for line in result.stdout.splitlines()], ["hob", "trk"]
        )


class RealScryfallDataTest(unittest.TestCase):
    """Builds the database from real Scryfall objects, cut down to the fields mtg reads."""

    @classmethod
    def setUpClass(cls):
        sample = Path(__file__).resolve().parent / "fixtures" / "scryfall_cards.jsonl"
        cards = [
            json.loads(line) for line in sample.read_text(encoding="utf-8").splitlines()
        ]
        cls.directory = Path(tempfile.mkdtemp(prefix="mtg-test-"))
        root = cls.directory / "remote"
        cls.server, base_url = start_server(root)
        write_fixtures(root, base_url, version=1, cards=cards)
        cls.environment = mtg_environment(cls.directory / "home", base_url)
        cls.upgrade = run_mtg(cls.environment, "upgrade")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.directory, ignore_errors=True)

    def card(self, name):
        result = run_mtg(self.environment, "card", name, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)[0]

    def test_upgrade_reads_real_objects(self):
        self.assertEqual(self.upgrade.returncode, 0, self.upgrade.stderr)

    def test_modal_double_faced_card(self):
        card = self.card("Witch-Blessed Meadow")
        self.assertEqual(card["name"], "Witch Enchanter // Witch-Blessed Meadow")
        self.assertEqual(
            [face["name"] for face in card["faces"]],
            ["Witch Enchanter", "Witch-Blessed Meadow"],
        )
        self.assertEqual(
            (card["colors"], card["color_identity"], card["mv"]), ("W", "W", 4.0)
        )

    def test_adventure_split_and_flip_cards(self):
        self.assertEqual(
            self.card("Flameshape")["name"], "Gandalf, Goblins' Bane // Flameshape"
        )
        self.assertEqual(self.card("Tear")["mana_cost"], "{1}{R} // {W}")
        flip = self.card("Erayo's Essence")
        self.assertEqual(
            [face["type_line"] for face in flip["faces"]][1], "Legendary Enchantment"
        )

    def test_reversible_card_has_a_single_name(self):
        card = self.card("Jinnie Fay, Jetmir's Second")
        self.assertEqual(
            (card["name"], card["faces"], card["first_set"]),
            ("Jinnie Fay, Jetmir's Second", [], "snc"),
        )

    def test_card_wins_over_token(self):
        self.assertEqual(
            self.card("Ornithopter")["type_line"], "Artifact Creature — Thopter"
        )

    def test_up_to_seven_copies(self):
        result = run_mtg(
            self.environment,
            "deck",
            "-",
            "--format",
            "modern",
            stdin="8 Seven Dwarves\n",
        )
        self.assertIn("Seven Dwarves: 8 copies, the limit is 7.", result.stdout)


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="mtg-test-"))
        self.root = self.directory / "remote"
        self.server, self.base_url = start_server(self.root)
        write_fixtures(self.root, self.base_url, version=1)
        self.environment = mtg_environment(self.directory / "home", self.base_url)
        result = run_mtg(self.environment, "upgrade")
        self.assertEqual(result.returncode, 0, result.stderr)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_update_then_upgrade_lists_the_changes(self):
        write_fixtures(self.root, self.base_url, version=2)
        update = run_mtg(self.environment, "update")
        self.assertEqual(update.returncode, 0, update.stderr)
        self.assertIn("Scryfall:   2026-10-10 09:00 UTC", update.stdout)
        report = json.loads(run_mtg(self.environment, "update", "--json").stdout)
        self.assertTrue(report["upgrade_available"])
        self.assertRegex(
            update.stdout, r"nau +Nauctis: The Sunken Realm +new set, 3 cards"
        )
        self.assertRegex(update.stdout, r"hob +The Hobbit +\+1 cards")
        self.assertIn("Run `mtg upgrade` to download about 90 MB.", update.stdout)

        upgrade = run_mtg(self.environment, "upgrade")
        self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
        self.assertIn("New cards: 1 (hob 1)", upgrade.stdout)
        self.assertIn("Oracle text changes: 1 (Swords to Plowshares)", upgrade.stdout)
        self.assertIn(
            "Legality changes: 2 cards (commander 1, modern 1)", upgrade.stdout
        )
        self.assertIn("Game Changer changes: 1 (Gamble)", upgrade.stdout)
        self.assertIn("Removed cards: 1 (Shields Up!)", upgrade.stdout)

        changes = run_mtg(self.environment, "changes", "--full").stdout
        self.assertIn("hob The Hobbit (1): Honor", changes)
        self.assertIn("after:  " + SWORDS_TEXT + " Draw a card.", changes)
        self.assertIn("Commander: Mana Crypt banned -> legal", changes)
        self.assertIn("Modern: 1 card became legal: Swords to Plowshares", changes)
        self.assertIn("Game Changers: Gamble removed from the list", changes)
        self.assertIn("Removed: Shields Up!", changes)
        self.assertNotIn("Expedite", changes)
        self.assertEqual(run_mtg(self.environment, "search", "--gc").stdout, "")

    def test_new_mtg_version_rebuilds_the_database(self):
        database = sqlite3.connect(self.directory / "home" / "cards.sqlite")
        database.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
        database.commit()
        database.close()
        card = run_mtg(self.environment, "card", "Feather, the Redeemed")
        self.assertEqual(card.returncode, 2)
        self.assertIn("another mtg version. Run `mtg upgrade`.", card.stderr)
        update = run_mtg(self.environment, "update")
        self.assertIn(
            "comes from an older mtg version. Run `mtg upgrade`", update.stdout
        )
        upgrade = run_mtg(self.environment, "upgrade")
        self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
        card = run_mtg(self.environment, "card", "Feather, the Redeemed")
        self.assertEqual(card.returncode, 0, card.stderr)

    def test_failed_upgrade_keeps_the_old_data(self):
        write_fixtures(self.root, self.base_url, version=2, broken=True)
        upgrade = run_mtg(self.environment, "upgrade")
        self.assertEqual(upgrade.returncode, 2)
        self.assertIn(
            "the upgrade failed and the old data is unchanged", upgrade.stderr
        )
        card = run_mtg(self.environment, "card", "Feather, the Redeemed")
        self.assertEqual(card.returncode, 0, card.stderr)
        self.assertIn(
            "Data:     2026-10-09 21:00 UTC", run_mtg(self.environment, "status").stdout
        )
        self.assertEqual(
            sorted(path.name for path in (self.directory / "home").iterdir()),
            ["cards.sqlite", "index.json"],
        )


if __name__ == "__main__":
    unittest.main()
