import os.path
import tempfile
from collections import defaultdict

from django.core.files import File
from django.core.cache import cache

from server.apps.players.models import Player
from server.core.utils import delta_frames

from .models import RoomTime


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


def _get_stats():
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


def get_stats():
    with cache.lock('stats-lock', timeout=60, blocking_timeout=2):
        stats = cache.get('stats')
        if stats is None:
            stats = _get_stats()
            cache.set('stats', stats)

    return stats


def rebuild_stats():
    with cache.lock('stats-lock', timeout=60, blocking_timeout=2):
        stats = _get_stats()
        cache.set('stats', stats)
        return stats


def _save_uploaded_image(rt, uploaded_f, ext):
    rt.media.save(uploaded_f.name, File(uploaded_f), save=False)


def _save_uploaded_video(rt, uploaded_f, ext):
    if ext != 'mp4':
        stored_f = tempfile.NamedTemporaryFile(suffix='.' + ext)
        stored_f.write(uploaded_f.read())
        stored_f.flush()

        converted_f = tempfile.NamedTemporaryFile(suffix='.mp4')

        ret = os.system("""
            ffmpeg -i "{fname_in}" \
                -c:v libx264 \
                -preset slow \
                -crf 18 \
                -bf 2 \
                -flags +cgop \
                -pix_fmt yuv420p \
                -sws_flags neighbor \
                -s:v 512x448 \
                -c:a aac \
                -b:a 160k \
                -movflags faststart \
                -y \
                "{fname_out}"
        """.format(fname_in=stored_f.name, fname_out=converted_f.name))
        assert ret == 0, ret
        filename = uploaded_f.name.rsplit('.', 1)[0] + '.mp4'
    else:
        converted_f = uploaded_f
        filename = uploaded_f.name

    rt.media.save(filename, File(converted_f), save=False)


def save_uploaded_media(rt, f):
    filename = os.path.basename(f.name).lower()
    if '.' not in filename:
        raise Exception('No extension?')

    ext = filename.rsplit('.', 1)[-1]

    if ext in 'jpg|jpeg|png|bmp|gif'.split('|'):
        _save_uploaded_image(rt, f, ext)
    elif ext in 'webm|mkv|flv|vob|ogg|ogv|avi|mov|wmv|mp4|m4p|m4v|mpg|mp2|mpeg|mpv'.split('|'):
        _save_uploaded_video(rt, f, ext)
    else:
        raise Exception('Unknown extension')
