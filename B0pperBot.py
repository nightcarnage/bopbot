
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
import readline

cfg = configparser.ConfigParser()
try:
    cfg.read("config.ini")

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
    SIGNAL_BOT = cfg["b0pperbot"]["signal_bot"]
except:
    print("Cannot read 'config.ini'.")
    print("Exiting...")
    exit(-1)

app_name = "B0pperBot"
donor_list = []
sp = 0
playlist_tracks = []
playlist_ids = []
bot_ready = False
ci_inc = 0

def cache_playlist():
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
    
    cache_playlist()

    print(app_name, "is ready.\n")
    global bot_ready
    bot_ready = True
    help()
    await ready_event.chat.join_room(TARGET_CHANNEL)

async def on_message(msg: ChatMessage):
    #print(f"in {msg.room.name}, {msg.user.name} said: {msg.text}")

    global donor_list
    global playlist_tracks

    print(msg.user.name, SIGNAL_BOT)
    if msg.user.name.lower() == SIGNAL_BOT.lower():
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
            donor_list.append(donor.lower())

    if msg.text.startswith("!sr"):
        if msg.user.name.lower() in donor_list:

            print(msg.user.name, "had one occurence removed from dono list")
            donor_list.remove(msg.user.name.lower())

            tr = sp.currently_playing()
            ci = 0
            for track in playlist_tracks:
                ci += 1
                if track["track"]["id"] == tr["item"]["id"]:
                    break
            
            global ci_inc

            results = sp.search(q=" ".join(msg.text.split()[1:]), limit=1)
            track_uris = []
            for idx, track in enumerate(results["tracks"]["items"]):
                track_uris.append(track["uri"])

                nt = {}
                nt["uri"] = track["uri"]
                nt["bopped"] = True
                nt["id"] = track["id"]
                nt["pos"] = ci + ci_inc
                playlist_tracks.append({"track": nt})

            print("Adding requested track to position", str(ci+ci_inc))
            sp.playlist_add_items(SPOTIFY_PLAYLIST_URI, track_uris,ci + ci_inc)
            ci_inc += 1


def help(command = ""):
    if command == "":
        print("Commands: donors, reset, help, quit. For further help, type 'help <command>'.")
    if command == "quit":
        print("The 'quit' command deactivates", app_name, "and exits the program.")
    if command == "help":
        print("The 'help' command provides... help.")
    if command == "donors":
        print("The 'donors' command shows the list of users who have access to the \
song request chat command (default: '!sr') currently. To search for a user in the \
list: 'donors <user>'.")
    if command == "reset":
        print("The 'reset' command reverts", app_name, "back to the startup state.")

def clean_playlist():
    print("Removing requested songs from playlist...")

    i = 0
    for track in playlist_tracks:

        if track["track"]["bopped"]:
            tid = track["track"]["id"]
            pos = track["track"]["pos"] - i
            track_ids = []
            track_ids.append({"uri": tid, "positions": [int(pos)]})
            sp.playlist_remove_specific_occurrences_of_items(
            SPOTIFY_PLAYLIST_URI, track_ids
            )
            i+=1

async def run():

    global donor_list
    global playlist_tracks

    twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_SECRET)
    auth = UserAuthenticator(twitch, USER_SCOPE)
    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)

    chat = await Chat(twitch)
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_event(ChatEvent.MESSAGE, on_message)

    chat.start()

    print()
    print(
"""
┌┐ ┌─┐┌─┐┌─┐┌─┐┬─┐┌┐ ┌─┐┌┬┐
├┴┐│ │├─┘├─┘├┤ ├┬┘├┴┐│ │ │ 
└─┘└─┘┴  ┴  └─┘┴└─└─┘└─┘ ┴ 
"""
)
    #try:
    quit = False
    while not quit:

        if not bot_ready: continue

        line = input("cmd: ")
        line = line.split()

        if len(line) >= 1:
            cmd = line[0]

            if cmd == "help":
                if len(line) >= 2:
                    help(line[1])
                else:
                    help()
            if cmd == "quit" or cmd == "exit":
                quit = True

            if cmd == "donors":
                if len(line) >= 2:
                    print(line[1] in donor_list)
                else:
                    print(list(set(donor_list)))
            
            if cmd == "reset":
                print("Clearing donor list...")
                donor_list = []
                
                clean_playlist()

                print("Clearing playlist cache...")
                playlist_tracks = []

                print("Caching playlist..")
                cache_playlist()

    #finally:

    print("Leaving Twitch...")
    chat.stop()
    await twitch.close()

    clean_playlist()

    print("Exiting...")

asyncio.run(run())