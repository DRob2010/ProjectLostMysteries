import secrets
import json
from datetime import timedelta
from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Player, Room, generate_room_code

ALLOW_SINGLE_PLAYER_START = True


def player_token_for(request):
    return (
        request.GET.get("player")
        or request.POST.get("player")
        or request.session.get("player_token")
    )


def opposite_role(role):
    if role == Player.DETECTIVE:
        return Player.AGENT
    if role == Player.AGENT:
        return Player.DETECTIVE
    return None


def room_ready_to_start(game_room):
    connected_players = list(
        game_room.players.filter(is_connected=True).order_by("joined_at")
    )
    if not connected_players:
        return False
    if len(connected_players) == 1:
        return ALLOW_SINGLE_PLAYER_START and connected_players[0].is_ready
    return all(player.is_ready for player in connected_players)


def reconnect_player(game_room, player_token, now=None):
    if not player_token:
        return None
    now = now or timezone.now()
    player = game_room.players.filter(session_token=player_token).first()
    if player is None:
        return None
    if not player.is_connected:
        active_count = game_room.players.filter(is_connected=True).count()
        if active_count >= 2:
            return None
        player.is_connected = True
    player.last_seen = now
    player.save(update_fields=["is_connected", "last_seen"])
    return player


def room(request):
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            code = generate_room_code()
            while Room.objects.filter(code=code).exists():
                code = generate_room_code()

            game_room = Room.objects.create(code=code)
            session_token = secrets.token_urlsafe(32)
            Player.objects.create(
                room=game_room,
                session_token=session_token,
                role=Player.DETECTIVE,
            )
            request.session["room_code"] = game_room.code
            request.session["player_token"] = session_token
            query = urlencode({"player": session_token})
            return redirect(f"/room/{game_room.code}/?{query}")

        if action == "join":
            code = request.POST.get("code", "").strip().upper()
            game_room = Room.objects.filter(code=code).first()

            if game_room is None:
                return render(request, "room.html", {"error": "Room code not found."})

            if game_room.players.filter(is_connected=True).count() >= 2:
                return render(request, "room.html", {"error": "That room is already full."})

            session_token = secrets.token_urlsafe(32)
            host = game_room.players.filter(is_connected=True).order_by("joined_at").first()
            open_player = game_room.players.filter(is_connected=False).order_by("joined_at").first()
            if open_player is not None:
                open_player.session_token = session_token
                open_player.role = opposite_role(host.role) if host else None
                open_player.is_ready = False
                open_player.is_connected = True
                open_player.last_seen = timezone.now()
                open_player.save(update_fields=["session_token", "role", "is_ready", "is_connected", "last_seen"])
            else:
                Player.objects.create(
                    room=game_room,
                    session_token=session_token,
                    role=opposite_role(host.role) if host else None,
                )
            request.session["room_code"] = game_room.code
            request.session["player_token"] = session_token
            query = urlencode({"player": session_token})
            return redirect(f"/room/{game_room.code}/?{query}")

    return render(request, "room.html")


def room_detail(request, code):
    game_room = get_object_or_404(Room, code=code.upper())
    now = timezone.now()
    game_room.players.filter(
        is_connected=True,
        last_seen__lt=now - timedelta(seconds=6),
    ).update(is_connected=False)
    host = game_room.players.order_by("joined_at").first()
    player_token = player_token_for(request)
    players = list(game_room.players.order_by("joined_at"))
    current_player = reconnect_player(game_room, player_token, now)
    player_number = next(
        (index + 1 for index, player in enumerate(players) if player.pk == getattr(current_player, "pk", None)),
        "",
    )
    player_1_role = players[0].role if len(players) > 0 else None
    player_2_role = players[1].role if len(players) > 1 else opposite_role(player_1_role)
    player_1_ready = players[0].is_ready if len(players) > 0 and players[0].is_connected else False
    player_2_ready = players[1].is_ready if len(players) > 1 and players[1].is_connected else False
    ready_to_start = room_ready_to_start(game_room)

    if request.method == "POST" and current_player is not None:
        if request.POST.get("action") == "leave":
            current_player.is_connected = False
            current_player.is_ready = False
            current_player.save(update_fields=["is_connected", "is_ready"])
            request.session.pop("room_code", None)
            request.session.pop("player_token", None)
            return redirect("home")

        if request.POST.get("action") == "ready":
            current_player.is_ready = not current_player.is_ready
            current_player.save(update_fields=["is_ready"])
            query = urlencode({"player": player_token})
            return redirect(f"/room/{game_room.code}/?{query}")

        role = request.POST.get("role")
        if role in {Player.DETECTIVE, Player.AGENT}:
            current_player.role = role
            current_player.is_ready = False
            current_player.save(update_fields=["role", "is_ready"])

            other_player = game_room.players.filter(is_connected=True).exclude(pk=current_player.pk).first()
            if other_player is not None:
                other_player.role = opposite_role(role)
                other_player.is_ready = False
                other_player.save(update_fields=["role", "is_ready"])

            query = urlencode({"player": player_token})
            return redirect(f"/room/{game_room.code}/?{query}")

    return render(
        request,
        "room.html",
        {
            "game_room": game_room,
            "player_count": game_room.players.filter(is_connected=True).count(),
            "is_host": host is not None
            and host.session_token == player_token,
            "player_role": current_player.get_role_display() if current_player else "",
            "player_token": player_token,
            "player_number": player_number,
            "player_1_role": dict(Player.ROLE_CHOICES).get(player_1_role, "Not selected"),
            "player_2_role": dict(Player.ROLE_CHOICES).get(player_2_role, "Not selected"),
            "player_1_role_value": player_1_role,
            "player_2_role_value": player_2_role,
            "player_ready": current_player.is_ready if current_player else False,
            "player_1_ready": player_1_ready,
            "player_2_ready": player_2_ready,
            "both_ready": ready_to_start,
            "player_1_connected": len(players) > 0 and players[0].is_connected,
            "player_2_connected": len(players) > 1 and players[1].is_connected,
        },
    )


def room_status(request, code):
    game_room = get_object_or_404(Room, code=code.upper())
    now = timezone.now()
    game_room.players.filter(
        is_connected=True,
        last_seen__lt=now - timedelta(seconds=6),
    ).update(is_connected=False)
    player_token = player_token_for(request)
    players = list(game_room.players.order_by("joined_at"))
    current_player = reconnect_player(game_room, player_token, now)
    player_1_role = players[0].role if len(players) > 0 else None
    player_2_role = players[1].role if len(players) > 1 else opposite_role(player_1_role)
    player_1_ready = players[0].is_ready if len(players) > 0 and players[0].is_connected else False
    player_2_ready = players[1].is_ready if len(players) > 1 and players[1].is_connected else False
    ready_to_start = room_ready_to_start(game_room)
    return JsonResponse(
        {
            "player_count": game_room.players.filter(is_connected=True).count(),
            "your_role": current_player.role if current_player else None,
            "player_1_role": players[0].role if len(players) > 0 else None,
            "player_2_role": player_2_role,
            "your_ready": current_player.is_ready if current_player else False,
            "player_1_ready": player_1_ready,
            "player_2_ready": player_2_ready,
            "both_ready": ready_to_start,
            "player_1_connected": len(players) > 0 and players[0].is_connected,
            "player_2_connected": len(players) > 1 and players[1].is_connected,
            "ping_active": current_player is not None
            and current_player.ping_until is not None
            and current_player.ping_until > now,
        }
    )


def ping_player(request, code):
    game_room = get_object_or_404(Room, code=code.upper())
    player_token = player_token_for(request)
    current_player = game_room.players.filter(
        session_token=player_token,
        is_connected=True,
    ).first()
    other_player = game_room.players.filter(is_connected=True).exclude(
        pk=getattr(current_player, "pk", None)
    ).first()

    if request.method == "POST" and current_player is not None and other_player is not None:
        ping_until = timezone.now() + timedelta(seconds=5)
        current_player.ping_until = ping_until
        current_player.save(update_fields=["ping_until"])
        other_player.ping_until = ping_until
        other_player.save(update_fields=["ping_until"])
        return JsonResponse({"success": True})

    return JsonResponse({"success": False}, status=400)


def role_page(request, code):
    game_room = get_object_or_404(Room, code=code.upper())
    player_token = player_token_for(request)
    current_player = reconnect_player(game_room, player_token)

    both_ready = room_ready_to_start(game_room)

    if current_player is None or not both_ready:
        return redirect(f"/room/{game_room.code}/?{urlencode({'player': player_token})}")

    template = "detective.html" if current_player.role == Player.DETECTIVE else "agent.html"
    return render(request, template, {"game_room": game_room, "player": current_player})


def win_page(request, code):
    game_room = get_object_or_404(Room, code=code.upper())
    return render(request, "win.html", {"game_room": game_room})


def player_state(request, code):
    game_room = get_object_or_404(Room, code=code.upper())
    player_token = player_token_for(request)
    current_player = reconnect_player(game_room, player_token)
    if current_player is None:
        return JsonResponse({"error": "Player could not reconnect."}, status=403)

    if request.method == "POST":
        try:
            state = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid state."}, status=400)
        if not isinstance(state, dict):
            return JsonResponse({"error": "Invalid state."}, status=400)
        current_player.game_state = state
        current_player.save(update_fields=["game_state"])

    detective = game_room.players.filter(role=Player.DETECTIVE).first()
    shared_state = detective.game_state if detective is not None else {}
    agent = game_room.players.filter(role=Player.AGENT).first()
    opponent_state = agent.game_state if agent is not None else {}
    return JsonResponse({
        "state": current_player.game_state,
        "shared_state": shared_state,
        "opponent_state": opponent_state,
    })

# Create your views here.
