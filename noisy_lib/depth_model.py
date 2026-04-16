# depth_model.py - Modele probabiliste de profondeur de crawl
# IN: rng, is_mobile, max_depth | OUT: int session_depth | MODIFIE: rien
# APPELE PAR: crawler.py | APPELLE: rien

import random


def pick_session_depth(rng: random.Random, is_mobile: bool, configured_max: int) -> int:
    """Choisit la profondeur max pour une session de crawl (visite root URL).

    Distribution realiste :
      60% bounce   (depth=1)
      25% short    (depth=2-3)
      15% deep     (depth=4-configured_max)

    Mobile cap a min(3, result).
    """
    roll = rng.random()
    if roll < 0.60:
        depth = 1
    elif roll < 0.85:
        depth = rng.randint(2, min(3, configured_max))
    else:
        depth = rng.randint(min(4, configured_max), configured_max)

    if is_mobile:
        depth = min(3, depth)
    return max(1, depth)
