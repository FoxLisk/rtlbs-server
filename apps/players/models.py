# coding: utf-8
from django.db import models
from django.db import transaction
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.contrib.auth.validators import ASCIIUsernameValidator

from server.apps.rooms.stats_cache import mark_stats_dirty
from server.core.validators import UnicodeUsernameValidator


class PlayerManager(BaseUserManager):
    def create_user(self, username, password=None):
        if not username:
            raise ValueError('Players must have a username')

        user = self.model(
            username=username,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    create_superuser = create_user

    def get_by_natural_key(self, username):
        return self.get(username__iexact=username)


class Player(AbstractBaseUser):
    username = models.CharField(
        'Username',
        max_length=150,
        unique=True,
        validators=[UnicodeUsernameValidator(), ASCIIUsernameValidator()],
        error_messages={
            'unique': "A player with that username already exists.",
        }
    )
    description = models.TextField('Description', blank=True)
    datetime_created = models.DateTimeField(auto_now_add=True)
    datetime_updated = models.DateTimeField(auto_now=True)
    is_active = True

    objects = PlayerManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        ret = super().save(*args, **kwargs)
        transaction.on_commit(mark_stats_dirty)
        return ret

    def delete(self, *args, **kwargs):
        ret = super().delete(*args, **kwargs)
        transaction.on_commit(mark_stats_dirty)
        return ret

    def __str__(self):
        return self.username
