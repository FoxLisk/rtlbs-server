from decimal import Decimal

from rest_framework import serializers

from .models import Room, RoomTime
from .utils import save_uploaded_media


class RoomSerializer(serializers.ModelSerializer):
    segment = serializers.CharField(source='segment.slug', read_only=True)

    class Meta:
        model = Room
        fields = [
            'id',
            'segment',
            'name',
            'slug',
            'sort',
        ]


class RoomSummarySerializer(RoomSerializer):
    roomtime = serializers.SerializerMethodField()
    num_roomtimes = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = RoomSerializer.Meta.fields + [
            'roomtime',
            'num_roomtimes',
        ]

    def get_roomtime(self, obj):
        roomtimes = self.context['stats']['room_lbs'].get(obj.slug, [])
        return roomtimes[0] if roomtimes else {}

    def get_num_roomtimes(self, obj):
        return len(self.context['stats']['room_lbs'].get(obj.slug, []))


class RoomDetailSerializer(RoomSerializer):
    roomtimes = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = RoomSerializer.Meta.fields + [
            'roomtimes',
        ]

    def get_roomtimes(self, obj):
        context = {'stats': self.context['stats']}
        roomtimes = RoomTime.objects.filter(room=obj).select_related('player', 'room', 'room__segment')
        return [RoomTimeSerializer(rt, context=context).data for rt in roomtimes]


class RoomTimeSerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    shared_ranks = serializers.SerializerMethodField()
    player = serializers.CharField(source='player.username', read_only=True)
    room = serializers.CharField(source='room.slug')
    segment = serializers.CharField(source='room.segment.slug', read_only=True)

    class Meta:
        model = RoomTime
        fields = [
            'id',

            'player',
            'room',
            'segment',

            'description',
            'frames',
            'lag',
            'idle',
            'menues',
            'lttphack_version',
            'media',
            'twitch_url',

            'datetime_created',
            'datetime_updated',

            'rank',
            'shared_ranks'
        ]

    def create(self, validated_data):
        room = Room.objects.get(slug=validated_data.pop('room')['slug'])
        media = self.initial_data.get('media', None)
        player = self.context['request'].user

        rt = RoomTime(
            room=room,
            player=player,
            **validated_data
        )

        if media:
            save_uploaded_media(rt, media)

        rt.save()
        return rt

    def update(self, obj, validated_data):
        media = self.initial_data.get('media', None)
        remove_media = self.initial_data.get('remove_media', None)

        if media:
            validated_data.pop('twitch_url', None)
            obj.twitch_url = ''
            save_uploaded_media(obj, media)
        elif remove_media:
            obj.media.delete(save=False)

        if validated_data.get('twitch_url', '') and obj.media:
            obj.media.delete(save=False)

        return super().update(obj, validated_data)

    def get_shared_ranks(self, obj):
        for rt in self.context['stats']['room_lbs'].get(obj.room.slug, []):
            if rt['id'] == obj.id:
                return rt['shared_ranks']

    def get_rank(self, obj):
        stats = self.context['stats']

        rank = stats['player_data'][obj.player.username]['rank_per_room'].get(obj.room.slug, None)
        if not rank:
            return

        # Make sure the rank corresponds to _this_ roomtime
        roomtimes = stats['room_lbs'].get(obj.room.slug, [])
        my_roomtimes = [rt for rt in roomtimes if rt['player'] == obj.player.username]
        if not my_roomtimes:
            return
        if obj.frames != Decimal(str(my_roomtimes[0]['frames'])):
            return

        return rank

    def get_media(self, obj):
        return obj.get_media()
