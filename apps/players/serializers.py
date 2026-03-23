from rest_framework import serializers

from server.apps.rooms.stats_cache import rebuild_stats
from .models import Player


class PlayerSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    rank = serializers.SerializerMethodField()
    num_roomtimes = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    avg_score = serializers.SerializerMethodField()
    best_room = serializers.SerializerMethodField()
    worst_room = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = [
            'id',
            'username',
            'description',
            'password',

            'rank',
            'num_roomtimes',
            'score',
            'avg_score',
            'best_room',
            'worst_room',
        ]

    def create(self, validated_data):
        username = validated_data['username']
        if Player.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError('Username is already in use!')

        password = validated_data.pop('password')
        player = super().create(validated_data)
        player.set_password(password)
        player.save()
        self.context['stats'] = rebuild_stats()
        return player

    def get_rank(self, obj):
        ps = self.context['stats']['player_data']
        return ps[obj.username]['rank']

    def get_num_roomtimes(self, obj):
        ps = self.context['stats']['player_data']
        return ps[obj.username]['num_roomtimes']

    def get_score(self, obj):
        ps = self.context['stats']['player_data']
        return ps[obj.username]['score']

    def get_avg_score(self, obj):
        ps = self.context['stats']['player_data']
        if ps[obj.username]['num_roomtimes']:
            return int(ps[obj.username]['score'] / ps[obj.username]['num_roomtimes'])

    def get_best_room(self, obj):
        ps = self.context['stats']['player_data']
        return ps[obj.username]['best']

    def get_worst_room(self, obj):
        ps = self.context['stats']['player_data']
        return ps[obj.username]['worst']
