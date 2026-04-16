# depth_model.py - Modele probabiliste de profondeur de crawl
# IN: rng, is_mobile, max_depth | OUT: int session_depth | MODIFIE: rien
# APPELE PAR: crawler.py | APPELLE: rien

import random


def pick_session_depth(rng: random.Random, is_mobile: bool, configured_max: int) -> int:
    """Choisit la profondeur max pour une session de crawl (visite root URL).

    Distribution realiste avec fourchettes (re-tirees par session) :
      bounce  50-70%  (depth=1)
      short   20-30%  (depth=2-3)
      deep    remainder (~10-25%) (depth=4-configured_max)

    Mobile cap a min(3, result).
    """
    bounce_thr = rng.uniform(0.50, 0.70)
    short_thr = bounce_thr + rng.uniform(0.20, 0.30)
    roll = rng.random()
    if roll < bounce_thr:
        depth = 1
    elif roll < short_thr:
        depth = rng.randint(2, min(3, configured_max))
    else:
        depth = rng.randint(min(4, configured_max), configured_max)

    if is_mobile:
        depth = min(3, depth)
    return max(1, depth)
