#!/usr/bin/env python3
import dateutil.parser
import requests
from datetime import datetime

from django.core.management.base import BaseCommand

from server.apps.stats.models import Run, Player, Category


def parse_date(s):
    return dateutil.parser.parse(s).date()


def parse_datetime(s):
    return dateutil.parser.parse(s)


def get_next_url(data):
    for link in data['pagination']['links']:
        if link['rel'] == 'next':
            return link['uri']


def get_category(run):
    return Category.objects.filter(id__in=run['values'].values()).first()


class Command(BaseCommand):
    help = 'Fetch data from SRC'
    fetched_players = None
    full_sync = None
    debug = False

    def __init__(self, *args, **kwargs):
        self.fetched_players = {}
        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument('--full-sync', action='store_true',
                            dest='full_sync', default=False,
                            help='Will be slow!')

        parser.add_argument('--debug', action='store_true',
                            dest='debug', default=False,
                            help='Prints some info to stdout')

    def handle(self, **options):
        self.full_sync = options['full_sync']
        self.debug = options['debug']

        self.update_categories()
        self.update_runs()

    def log(self, *args, **kwargs):
        if self.debug:
            print(datetime.now(), *args, **kwargs)

    def fetch(self, url):
        self.log(url)
        response = requests.get(url)
        return response.json()

    def update_player(self, player_id):
        player = self.fetched_players.get(player_id)
        if player:
            return player

        player = Player.objects.filter(id=player_id).first()

        if not self.full_sync and player:
            return player

        if not player:
            player = Player(id=player_id)

        data = self.fetch('https://www.speedrun.com/api/v1/users/{}'.format(player_id))['data']

        player.id = data['id']
        player.link = data['weblink']
        player.signed_up = parse_datetime(data['signup'])
        player.location = data['location']['country']['names']['international'] if data['location'] else ''
        player.name = data['names']['international']
        player.twitch_url = data['twitch']['uri'] if data['twitch'] else ''
        player.save()

        self.fetched_players[player_id] = player

        return player

    def get_player(self, players):
        if len(players) != 1:
            return

        player_data = players[0]

        if player_data.get('id'):
            player = self.update_player(player_data['id'])
        else:
            assert player_data.get('rel') == 'guest'

            player_id = 'guest-{}'.format(player_data['name'])
            player = Player.objects.filter(id=player_id).first()

            if player is None:
                player = Player.objects.create(id=player_id,
                                               name=player_data['name'],
                                               link=player_data['uri'])

            self.fetched_players[player.id] = player

        return player

    def update_run(self, data):
        player = self.get_player(data['players'])
        if not player:
            self.log(f'No player for run {data["id"]}')
            return

        moderator = None
        if data['status'].get('examiner'):
            moderator = self.update_player(data['status']['examiner'])

        run = Run.objects.filter(id=data['id']).first()

        if not self.full_sync and run:
            return run

        if run is None:
            run = Run(id=data['id'])

        run.id = data['id']
        run.link = data['weblink']
        run.category = get_category(data)
        run.comment = data['comment']
        run.status = data['status']['status']
        run.time = data['times']['primary_t']
        run.moderator = moderator
        run.player = player
        run.date = parse_date(data['date'] or data['submitted'])
        run.emulated = data['system']['emulated']
        run.save()

    def update_runs(self):
        next_url = 'https://www.speedrun.com/api/v1/runs?game=9d3rr0dl&max=200'
        while next_url:
            data = self.fetch(next_url)
            for run in data['data']:
                try:
                    self.update_run(run)
                except Exception:
                    print(run)
                    raise
            next_url = get_next_url(data)

    def update_categories(self):
        data = self.fetch('https://www.speedrun.com/api/v1/games/9d3rr0dl/variables')
        for parent in data['data']:
            self.log(f"Handling category {parent}")
            if parent['name'] != 'Sub Category':
                continue

            parent_category = self.fetch('https://www.speedrun.com/api/v1/categories/{}'.format(parent['category']))
            for cat_id, cat_data in parent['values']['values'].items():
                category = Category.objects.filter(id=cat_id).first()

                if not self.full_sync and category:
                    continue

                category = category or Category(id=cat_id)
                category.name = cat_data['label']
                category.type = parent_category['data']['name']
                category.save()
