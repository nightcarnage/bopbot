
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand
USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]

from pprint import pprint
import configparser

import asyncio
import requests

cfg = configparser.ConfigParser()
cfg.read("config.ini")

try:
    TWITCH_CLIENT_ID = cfg["twitch"]["client_id"]
    TWITCH_SECRET = cfg["twitch"]["secret_key"]
    TARGET_CHANNEL = cfg["twitch"]["channel"]

    SPOTIFY_CLIENT_ID = cfg["spotify"]["client_id"]
    SPOTIFY_SECRET = cfg["spotify"]["secret_key"]
    SPOTIFY_PLAYLIST_URI = cfg["spotify"]["playlist_uri"]

    AMOUNT_BITS = int(cfg["b0pperbot"]["amount_bits"])
    AMOUNT_GIFTED_TIER1 = int(cfg["b0pperbot"]["amount_gifted_tier1"])
    AMOUNT_GIFTED_TIER2 = int(cfg["b0pperbot"]["amount_gifted_tier2"])
    AMOUNT_GIFTED_TIER3 = int(cfg["b0pperbot"]["amount_gifted_tier3"])
    AMOUNT_TIP = float(cfg["b0pperbot"]["amount_tip"])
    STREAMLABS_USERNAME = cfg["b0pperbot"]["streamlabs_username"]
except:
    print("There was a 'config.ini' error.")
    exit(-1)

app_name = "B0pperBot"
dono_list = []
sp = 0
playlist_tracks = []
playlist_ids = []

async def on_ready(ready_event: EventData):

    global sp
    scope = "user-read-currently-playing user-library-read \
            playlist-modify-private playlist-modify-public"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_SECRET,
        redirect_uri="http://localhost:3000",
        scope=scope
        ))
    
    global playlist_tracks
    offset = 0
    while True:
        response = sp.playlist_items(SPOTIFY_PLAYLIST_URI,
                                    offset=offset,
                                    fields="items.track.id,items.track.uri,total",
                                    additional_types=["track"])

        if len(response["items"]) == 0:
            break
        
        playlist_tracks.append(response["items"])
        playlist_ids.append(response["items"][0]["track"]["id"])

        offset = offset + len(response["items"])

    playlist_tracks = playlist_tracks[0]
    for track in playlist_tracks:
        track["track"]["bopped"] = False

    print(app_name, "is ready.")
    await ready_event.chat.join_room(TARGET_CHANNEL)

async def on_message(msg: ChatMessage):
    #print(f"in {msg.room.name}, {msg.user.name} said: {msg.text}")

    global dono_list
    global playlist_tracks

    if msg.user.name.lower() == STREAMLABS_USERNAME.lower():
        """
        TODO parsing streamlabs in chat because streamlabs
        requires approval for API access
        """

        #Thank you username for donating 100 bits
        #username just gifted 1 Tier 1 subscriptions!
        #Thank you username for tipping $1.00!

        donor = ""
        amount = 0
        can_request = False

        if "tipping" in msg.text:
            line = msg.text.split()
            amount = float(line[5][1:-1])
            donor = line[2]
            if amount >= AMOUNT_TIP:
                #TODO currency conversion
                if line[5].startswith("$"):
                    can_request = True

        if "bits" in msg.text:
            line = msg.text.split()
            amount = int(line[5])
            donor = line[2]
            if amount >= AMOUNT_BITS:
                can_request = True
        
        if "gifted" in msg.text:
            line = msg.text.split()
            amount = int(line[3])
            donor = line[0]
            tier = 1
            if int(line[5]) == 1 and amount >= AMOUNT_GIFTED_TIER1:
                can_request = True
            if int(line[5]) == 2 and amount >= AMOUNT_GIFTED_TIER2:
                can_request = True
            if int(line[5]) == 3 and amount >= AMOUNT_GIFTED_TIER3:
                can_request = True

        if can_request:
            print(donor, "added to dono list")
            dono_list.append(donor.lower())

    if msg.text.startswith("!sr"):
        if msg.user.name.lower() in dono_list:

            print(msg.user.name, "had one occurence removed from dono list")
            dono_list.remove(msg.user.name.lower())

            tr = sp.currently_playing()
            ci = 0
            for track in playlist_tracks:
                ci += 1
                if track["track"]["id"] == tr["item"]["id"]:
                    break

            results = sp.search(q=" ".join(msg.text.split()[1:]), limit=1)
            track_uris = []
            for idx, track in enumerate(results["tracks"]["items"]):
                track_uris.append(track["uri"])

                nt = {}
                nt["uri"] = track["uri"]
                nt["bopped"] = True
                nt["id"] = track["id"]
                nt["pos"] = ci + len(dono_list)
                playlist_tracks.append({"track": nt})
            """
            for t in playlist_tracks:
                if t["track"]["uri"] in track_uris:
                    playlist_tracks[i]["track"]["bopped"] = True
                    print("bopped true")
            """

            sp.playlist_add_items(SPOTIFY_PLAYLIST_URI, track_uris,\
                ci + len(dono_list))
            
async def run():
    twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_SECRET)
    auth = UserAuthenticator(twitch, USER_SCOPE)
    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)

    chat = await Chat(twitch)
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_event(ChatEvent.MESSAGE, on_message)

    chat.start()
    try:
        input("press ENTER to stop\n")
    finally:

        for track in playlist_tracks:
            if track["track"]["bopped"]:
                tid = track["track"]["id"]
                pos = track["track"]["pos"]
                track_ids = []
                track_ids.append({"uri": tid, "positions": [int(pos)]})
                sp.playlist_remove_specific_occurrences_of_items(
                SPOTIFY_PLAYLIST_URI, track_ids
                )

        chat.stop()
        await twitch.close()

asyncio.run(run())