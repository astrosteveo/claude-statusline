"""The kitty picture of game mode's scene, composited the way kitty plays it.

The engine's uploader (quest/art/scene.py) sends kitty, for each situation, a
still backdrop and a strip of small frames that kitty lays over it in turn,
every `gap` milliseconds. Here the same frames, from the same code, are laid
over the same backdrop at time `t`.
"""
import cairo

from claude_statusline.quest import items
from claude_statusline.quest.art import scene

LOOK = ("drake", {"head": items.ITEMS["wizard_hat"]["visual"], "hand": items.ITEMS["excalibash"]["visual"],
                  "back": items.ITEMS["dotfiles_robe"]["visual"], "form": "ember"})
HARVEST = ("drake", dict(LOOK[1], head=items.ITEMS["pumpkin_helm"]["visual"]))

_PNG = {}


def _png(path):
    s = _PNG.get(path)
    if s is None:
        s = _PNG[path] = cairo.ImageSurface.create_from_png(path)
    return s


def picture(situation, w, h, t, tod="night", boss=None, raid=False, dungeon=False, party=0, season=None,
            goblin=False, look=LOOK):
    """The scene at `t` seconds into the situation's loop, as a surface w x h."""
    scene.LOOK = look
    scene.PARTY = party
    scene.EXTRAS = {"season": season, "goblin": goblin}
    bg, patches, gap = scene.frames_for(situation, w, h, tod, boss, raid, dungeon)
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(out)
    cr.set_source_surface(_png(bg), 0, 0)
    cr.paint()
    if patches:
        x, path = patches[int(t * 1000 / gap) % len(patches)]
        cr.set_source_surface(_png(path), x, 0)
        cr.paint()
    out.flush()
    return out
