from server.apps.rooms.stats_cache import get_stats, rebuild_stats


class StatsView(object):
    def get_serializer_context(self):
        ret = super().get_serializer_context()
        ret['stats'] = get_stats()
        return ret

    def perform_create(self, serializer):
        serializer.save()
        serializer.context['stats'] = rebuild_stats()

    def perform_update(self, serializer):
        serializer.save()
        serializer.context['stats'] = rebuild_stats()

    def perform_destroy(self, instance):
        instance.delete()
        rebuild_stats()
