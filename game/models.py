import secrets
import string

from django.utils import timezone
from django.db import models


def generate_room_code():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


class Room(models.Model):
    code = models.CharField(max_length=6, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class Player(models.Model):
    DETECTIVE = "detective"
    AGENT = "agent"
    ROLE_CHOICES = [
        (DETECTIVE, "Detective"),
        (AGENT, "Agent"),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="players")
    session_token = models.CharField(max_length=64)
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        null=True,
        blank=True,
    )
    is_ready = models.BooleanField(default=False)
    is_connected = models.BooleanField(default=True)
    last_seen = models.DateTimeField(default=timezone.now)
    ping_until = models.DateTimeField(null=True, blank=True)
    game_state = models.JSONField(default=dict)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "session_token"],
                name="one_player_session_per_room",
            )
        ]
