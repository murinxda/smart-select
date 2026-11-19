"""Labels a Wikimedia capture (Wikipedia, Wikivoyage, Wikibooks, Wikinews), following docs/labelling.md.

The captures were first made with every section folded under its heading (mobile Wikimedia sites
fold them), and labelled block by block. Captured again with every section unfolded, a page keeps
those labels for the blocks it had before, found by their text, and its sections' text gets labels
from the section it is in:

- article: the sections' headings and text, its lists and tables;
- optional: images' file names;
- noise: edit links, map buttons, the sections after the article ("See also", "References",
  "External links"... and their translations) and the footer, and a block read again after a scroll.

usage: uv run python tools/label_wikis.py ID [--show]
"""
import re
import sys

from first_labels import FirstLabels, blocks as page_blocks, drop_rereads, reread, texts as page_texts, write

EDIT = re.compile(r"^(edit|modifier|modifier le code|editar|modifica|modifica wikitesto|bewerken|bearbeiten|"
                  r"quelltext bearbeiten|add listing|ajouter un élément)$", re.I)
EDIT_ICON = re.compile(r"^(modifier|edit|editar|modifica|bewerken) \S+\.(svg|png)\.png\?utm_source=", re.I)
# A heading with its edit link in the same block (Wikibooks)
HEADING_EDIT = re.compile(r"^(.{1,80}) edit$")
NOISE_HEADINGS = re.compile(
    r"^(See also|References|Notes|Notes and references|External links|Further reading|Bibliography|Sources|"
    r"Citations|Footnotes|Works cited|"
    r"Voir aussi|Notes et références|Références|Liens externes|Articles connexes|Bibliographie|"
    r"Sur les autres projets Wikimedia :?|Annexes|"
    r"Siehe auch|Einzelnachweise|Weblinks|Literatur|Anmerkungen|Quellen|Belege|"
    r"Véase también|Referencias|Enlaces externos|Notas|Bibliografía|Fuentes|"
    r"Voci correlate|Note|Collegamenti esterni|Bibliografia|Altri progetti|Fonti|"
    r"Zie ook|Externe links|Externe link|Bronnen|Referenties|Noten|Bronnen, noten en/of referenties|"
    r"Ver também|Referências|Ligações externas|Fontes)$")
# A box of links to other articles, beside the article (Wikinews): it ends where the text goes on
BOX_HEADINGS = re.compile(r"^(Related articles|Related news|Articles liés|Voir aussi sur Wikinews)$")
FOOTER = re.compile(r"^(Last edited|Dernière modification|Zuletzt bearbeitet|Última edición|Ultima modifica|"
                    r"Laatst bewerkt|De inhoud is beschikbaar|Editado pela última vez|Última edição|Content is available under|"
                    r"Le contenu est disponible|Der Inhalt ist verfügbar|El contenido está disponible|"
                    r"Il contenuto è disponibile|De tekst is beschikbaar|O conteúdo está disponível|"
                    r"This page is archived|Cette page est archivée|RELATED ARTICLES|ARTICLES CONNEXES)")
IMAGE = re.compile(r"\.(png|jpe?g|gif|svg|webp|tiff?)(\?utm_source=\S+)?( .*)?$", re.I)
UI = re.compile(r"^(Zoom in|Zoom out|Zoom avant|Zoom arrière|Layers|Show in full screen|Afficher en plein écran|"
                r"Show my location|Afficher ma position|More sharing options|Share this article|"
                r"Have an opinion on this story\? Share it!|\[dismiss\]|\[fermer\]|\[ocultar\]|dismiss|fermer|ocultar|"
                r"Esta caixa:|ver ·|discutir|v · d · e|v · t · e|\[editar datos en Wikidata\])$")
# Wikivoyage's notices about the guide, its map's credits and scale, and its calls to contribute
TRAVEL_NOISE = re.compile(r"^(This [\w ]+ travel guide to .+ is |This article is partly based on|L[’']article de (cette|ce|la) \w+ est |"
                          r"Esta guía es |Liste complète des autres articles|Y tú, ¿que esperas|"
                          r"(Cartes|Mapas)( de)? Wikimedia \||Wikimedia maps \||\d+ (m|km|ft|mi)$)")
# A banner's close link, read as three blocks: "[", "dismiss", "]"
DISMISS = re.compile(r"^(dismiss|fermer|ocultar)$")


def table_cells(blocks: list[dict]) -> set[int]:
    """The cells of the page's tables: runs of narrow blocks, some of them side by side on a row. The
    body's paragraphs, lists and headings take the column's width."""
    def narrow(b: dict) -> bool:
        return b["right"] - b["left"] < 750

    def side_by_side(a: dict, b: dict) -> bool:
        return abs(a["top"] - b["top"]) <= 30 and (a["right"] <= b["left"] + 20 or b["right"] <= a["left"] + 20)

    cells: set[int] = set()
    i = 0
    while i < len(blocks):
        if not narrow(blocks[i]):
            i += 1
            continue
        j = i
        while j + 1 < len(blocks) and narrow(blocks[j + 1]):
            j += 1
        if j - i + 1 >= 4 and sum(side_by_side(blocks[k], blocks[k + 1]) for k in range(i, j)) >= 2:
            cells.update(range(i, j + 1))
        i = j + 1
    return cells


def label_page(page: str, texts: list[str], blocks: list[dict]) -> list[str]:
    known = FirstLabels(page)
    cells = table_cells(blocks)
    labels: list[str] = []
    last_seen: dict[str, int] = {}
    section, titled, started = "lead", False, False
    for i, text in enumerate(texts):
        was = known.next(text)
        # Not the page's toolbar above the title ("Edit", "Share"): a section starts after the introduction
        heading = started and ((i > 0 and EDIT.match(texts[i - 1]) is not None) or HEADING_EDIT.match(text) is not None)
        # The introduction: the first long text after the title, the first block labelled article
        started = started or (titled and len(text) > 80)
        titled = titled or was == "A"
        title = HEADING_EDIT.match(text).group(1) if HEADING_EDIT.match(text) else text
        if FOOTER.match(text):
            section = "footer"
        elif section != "footer" and (heading or len(text) < 60) and NOISE_HEADINGS.match(title):
            section = "noise"
        elif section != "footer" and len(text) < 60 and BOX_HEADINGS.match(text):
            section = "box"
        elif heading or (section in ("noise", "box") and was == "A") \
                or (section == "box" and len(text) > 150 and not text.startswith("•")):
            # A block labelled article in the first capture, or a paragraph, ends the box
            section = "article"

        if text in last_seen and last_seen[text] == i - 1:
            # Read twice in a row, like a heading and its icon: the same label
            label = labels[i - 1]
        elif text in last_seen and reread(texts, i):
            # Read again after a scroll, or a table's cell repeating another cell's text
            label = "o" if i in cells and len(text) <= 80 else "."
        elif section in ("noise", "box", "footer") or EDIT.match(text) or EDIT_ICON.match(text) or UI.match(text) \
                or (text in ("[", "]") and any(DISMISS.match(texts[j]) for j in (i - 1, i + 1) if 0 <= j < len(texts))) \
                or (page.startswith("wikivoyage-") and TRAVEL_NOISE.match(text)):
            label = "."
        elif heading:
            label = "A"
        elif was is not None:
            label = was
        elif IMAGE.search(text) and " " not in text.split("?")[0]:
            label = "o"
        elif section == "lead":
            # Around the introduction, which the first capture had: the infobox and the banners
            label = "A" if len(text) > 80 else "o"
        else:
            label = "A"
        # A paragraph whose box came out too narrow for its text is not a cell
        cell = i in cells and len(text) <= 8 * max(blocks[i]["right"] - blocks[i]["left"], 0) / 10
        if label == "A" and cell and not heading and labels.count("A") > 0:
            # A table's cells: hard to copy as text, optional (the title, read over a banner, stays)
            label = "o"
        labels.append(label)
        last_seen[text] = i

    drop_rereads(texts, labels)
    return labels


if __name__ == "__main__":
    page = sys.argv[1]
    texts = page_texts(page)
    write(page, texts, label_page(page, texts, page_blocks(page)))
