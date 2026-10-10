# mtg

A local copy of every Magic: The Gathering card, built from [Scryfall bulk data](https://scryfall.com/docs/api/bulk-data), and a command line tool to read exact card text, search cards, and check decklists for any format.

It is one Python file with no dependencies. The database takes about 170 MB in `~/.cache/mtg`.

## Install

You need Python 3.9 or newer. The system Python of macOS and most Linux distributions works.

```sh
git clone https://github.com/Vzlentin/mtg.git
cd mtg
./install.sh    # links bin/mtg into ~/.local/bin, so git pull updates it
mtg upgrade     # downloads about 90 MB of card data
```

Without a clone, the installer downloads `bin/mtg`:

```sh
curl -fsSL https://raw.githubusercontent.com/Vzlentin/mtg/main/install.sh | sh
```

Set `PREFIX` to install somewhere else than `~/.local`.

## Use

```sh
mtg update                       # check Scryfall for newer data and new cards, no download
mtg upgrade                      # download the newer data and rebuild the database
mtg changes                      # what the last upgrade changed: new cards, text changes, bans
mtg card "Lightning Bolt" --rulings
mtg search --legal pauper --colors r --type instant --mv 1 --text damage
mtg search --ci rw --legal commander --tag removal --sort edhrec
mtg deck burn.txt --format modern
mtg deck https://archidekt.com/decks/872380
mtg deck feather.txt --commander "Feather, the Redeemed" --combos
mtg sql "SELECT name FROM cards WHERE json_extract(legalities, '$.modern') = 'banned'"
```

`mtg <command> --help` lists the options. Most commands take `--json`, and `card`, `search` and `deck` take `--md`.

`mtg card` finds a card by its full name or by one face, and ignores case and accents. It prints the Oracle text, the legality in the main formats, the first printing, the lowest price, and on request the rulings and all printings.

`mtg search` filters on name, Oracle text (plain text, regular expression or full-text query), type, colors, color identity, mana value, format, first printing date, set, Game Changers, and [Scryfall Tagger](https://tagger.scryfall.com/) tags such as `removal` or `ramp`.

## Decks

`mtg deck` reads Moxfield, Archidekt, MTGA, MTGO and plain text lists, and public Archidekt links. `--format` sets the rules:

- Standard, Pioneer, Modern, Legacy, Vintage, Pauper, Premodern, Old School, Penny Dreadful, Historic, Timeless, Alchemy: 60 cards or more, a sideboard of 15 or fewer, 4 copies across main deck and sideboard, restricted cards, legality.
- Commander, Duel Commander, PreDH, Pauper Commander, Brawl, Standard Brawl, Oathbreaker: deck size, singleton, color identity, and which cards can be the commander.
- Gladiator: 100 cards, singleton.
- Other Scryfall formats: legality only.

A Commander section or `--commander` means Commander. For Commander the report also lists the Game Changers, tutors, extra turns and mass land denial that the brackets look at. `--combos` asks [Commander Spellbook](https://commanderspellbook.com/) for combos, online. The exit status is 1 when the deck has problems.

Limits: tutors come from Scryfall Tagger tags, which are community work. For Pauper Commander, any creature with an uncommon printing counts as a valid commander. Companion conditions are not checked.

## Data

`mtg upgrade` downloads three Scryfall bulk files (every printing, the rulings and the Tagger oracle tags) and the set list, then builds an SQLite database. A failed upgrade keeps the old database. `mtg update` makes 2 small API calls. Only `mtg update`, `mtg upgrade`, `mtg deck --combos` and `mtg deck` with an Archidekt link use the network.

| Variable | Default |
| --- | --- |
| `MTG_HOME` | `$XDG_CACHE_HOME/mtg`, or `~/.cache/mtg` |
| `MTG_SCRYFALL_API` | `https://api.scryfall.com` |
| `MTG_SPELLBOOK_API` | `https://backend.commanderspellbook.com` |
| `MTG_ARCHIDEKT_API` | `https://archidekt.com/api` |

## Tests

```sh
python3 tests/test_mtg.py
```

The tests run `bin/mtg` against a local fake Scryfall, Commander Spellbook and Archidekt, so they need no network. GitHub Actions runs them on Python 3.9 and on the latest Python for each push and pull request. `tests/fixtures/scryfall_cards.jsonl` holds a few real Scryfall card objects to check the data shape.

## Uninstall

```sh
rm ~/.local/bin/mtg
rm -r ~/.cache/mtg
```

## License

MIT, see [LICENSE](LICENSE). Magic: The Gathering and its card text belong to Wizards of the Coast. The card data comes from Scryfall. This project is not affiliated with Wizards of the Coast, Scryfall or Commander Spellbook.
