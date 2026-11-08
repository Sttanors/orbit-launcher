"""Offline evening picks using explicit player tags and Orbit launch history."""
import random
from datetime import datetime

DURATIONS = (20, 60, 240)
MOODS = {'relax': 'Расслабиться', 'action': 'Экшен', 'think': 'Подумать', 'friends': 'С друзьями'}


def validate_profile(minutes, moods):
    if type(minutes) is not int or minutes not in DURATIONS:
        raise ValueError('Выбери длительность сессии: 20 минут, час или весь вечер.')
    if not isinstance(moods, list) or not moods or any(not isinstance(m, str) or m not in MOODS for m in moods):
        raise ValueError('Выбери хотя бы одно настроение.')
    return {'minutes': minutes, 'moods': list(dict.fromkeys(moods))}


def recommend(games, profiles, minutes=60, mood='relax', surprise=False, exclude=(), rng=None):
    if type(minutes) is not int or minutes not in DURATIONS or not isinstance(mood, str) or mood not in MOODS:
        raise ValueError('Неизвестные параметры вечера.')
    rng = rng or random.SystemRandom()
    ready = [g for g in games if g.get('installed') and not g.get('needsSetup')]
    eligible = ready if surprise else [g for g in ready if profiles.get(g['id'], {}).get('minutes', 999) <= minutes and mood in profiles.get(g['id'], {}).get('moods', [])]
    # Shuffle ties, then prioritize games not offered in the previous draw and
    # those least recently launched. Unknown history is treated as never played.
    rng.shuffle(eligible)
    eligible.sort(key=lambda g: (g['id'] in exclude, g.get('lastPlayed') or 0))
    picks = []
    for game in eligible[:1 if surprise else 3]:
        profile = profiles.get(game['id'])
        reason = 'Ещё не запускалась через Orbit' if not game.get('lastPlayed') else 'Последний запуск через Orbit: ' + datetime.fromtimestamp(game['lastPlayed']).strftime('%d.%m.%Y')
        if not surprise:
            reason = f"{MOODS[mood]} · сессия от {profile['minutes']} мин · {reason.lower()}"
        picks.append({'game': game, 'reason': reason})
    return {'picks': picks, 'matching': len(eligible), 'ready': len(ready),
            'tagged': sum(g['id'] in profiles for g in ready), 'surprise': surprise}
