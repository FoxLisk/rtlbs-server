import json
from collections import defaultdict

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction

from server.core.utils import delta_frames

SCORE_MAP = {
    1: 50,
    2: 40,
    3: 35,
    4: 30,
    5: 25,
    6: 20,
    7: 16,
    8: 12,
    9: 8,
    10: 4,
}

STATS_CACHE_KEY = 'room_stats'


def _roomtime_model():
    return apps.get_model('rooms', 'RoomTime')


def _stats_cache_model():
    return apps.get_model('rooms', 'StatsCache')


def _player_model():
    return apps.get_model('players', 'Player')


def _get_stats():
    Player = _player_model()
    RoomTime = _roomtime_model()

    print('generating')
    num_roomtimes = defaultdict(int)
    room_lbs = defaultdict(list)
    added_by_player = defaultdict(set)
    for rt in RoomTime.objects.select_related('room', 'room__segment', 'player'):
        if rt.room.slug in added_by_player[rt.player.username]:
            continue
        added_by_player[rt.player.username].add(rt.room.slug)

        num_roomtimes[rt.player.username] += 1
        room_lbs[rt.room.slug].append({
            'id': rt.id,
            'player': rt.player.username,
            'frames': rt.frames,
            'lag': rt.lag,
            'idle': rt.idle,
            'description': rt.description,
            'media': rt.get_media(),
            'menues': rt.menues,
            'datetime_created': rt.datetime_created,
            'datetime_updated': rt.datetime_updated,
            'room': rt.room.slug,
            'segment': rt.room.segment.slug,
        })

    player_scores = defaultdict(int)
    player_best_and_worst = defaultdict(dict)
    player_rank_per_room = defaultdict(dict)
    for room_data in room_lbs.values():
        if len(room_data) > 1:
            best = room_data[0]
            best['delta_best'] = delta_frames(room_data[1]['frames'], best['frames'])
            best_data = player_best_and_worst[best['player']]
            if 'best' not in best_data or best['delta_best'] > best_data['best']['delta_best']:
                best_data['best'] = best

            worst = room_data[-1]
            worst['delta_worst'] = delta_frames(worst['frames'], best['frames'])
            worst_data = player_best_and_worst[worst['player']]
            if 'worst' not in worst_data or worst['delta_worst'] > worst_data['worst']['delta_worst']:
                worst_data['worst'] = worst

        all_frames = list(sorted(rt['frames'] for rt in room_data))
        unique_frames = list(sorted(set(all_frames)))
        for rt in room_data:
            rank = unique_frames.index(rt['frames']) + 1
            score = SCORE_MAP.get(rank, 0)

            player_scores[rt['player']] += score
            player_rank_per_room[rt['player']][rt['room']] = {
                'rank': rank,
                'score': score,
            }
            rt['shared_ranks'] = all_frames.count(rt['frames'])

    all_scores = list(reversed(sorted(player_scores.values()))) + [0]
    player_data = {}
    for player in Player.objects.all():
        score = player_scores.get(player.username, 0)
        player_data[player.username] = {
            'rank': all_scores.index(score) + 1,
            'score': score,
            'best': player_best_and_worst[player.username].get('best', None),
            'worst': player_best_and_worst[player.username].get('worst', None),
            'num_roomtimes': num_roomtimes[player.username],
            'rank_per_room': player_rank_per_room.get(player.username, {}),
        }

    return {
        'player_data': player_data,
        'room_lbs': room_lbs,
    }


def _serialize_stats(stats):
    return json.dumps(stats, cls=DjangoJSONEncoder)


def _deserialize_stats(payload):
    return json.loads(payload)


def _get_stats_cache():
    StatsCache = _stats_cache_model()

    try:
        return StatsCache.objects.get(pk=STATS_CACHE_KEY)
    except StatsCache.DoesNotExist:
        try:
            with transaction.atomic():
                return StatsCache.objects.create(key=STATS_CACHE_KEY)
        except IntegrityError:
            return StatsCache.objects.get(pk=STATS_CACHE_KEY)


def mark_stats_dirty():
    StatsCache = _stats_cache_model()
    stats_cache = _get_stats_cache()
    if not stats_cache.dirty:
        StatsCache.objects.filter(pk=STATS_CACHE_KEY).update(dirty=True)


def get_stats():
    stats_cache = _get_stats_cache()
    if stats_cache.payload and not stats_cache.dirty:
        return _deserialize_stats(stats_cache.payload)

    return rebuild_stats()


def rebuild_stats():
    StatsCache = _stats_cache_model()
    _get_stats_cache()
    with transaction.atomic():
        stats_cache = StatsCache.objects.select_for_update().get(pk=STATS_CACHE_KEY)
        if stats_cache.payload and not stats_cache.dirty:
            return _deserialize_stats(stats_cache.payload)

        stats = _get_stats()
        stats_cache.payload = _serialize_stats(stats)
        stats_cache.dirty = False
        stats_cache.save(update_fields=['payload', 'dirty', 'updated_at'])
        return stats
