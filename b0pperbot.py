#!/usr/bin/env python3
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.oauth import UserAuthenticationStorageHelper
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand
USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
import configparser

from sys import exit
from pprint import pprint

import asyncio
import requests
import re

def fail(code = -1):
    print('Exiting...')
    exit(code)


#read from config.ini
cfg = configparser.ConfigParser()

try:
    cfg.read('config.ini')

    TWITCH_CLIENT_ID = cfg['twitch']['client_id']
    TWITCH_SECRET = cfg['twitch']['secret_key']
    TARGET_CHANNEL = cfg['twitch']['channel']
    GIFTED_MESSAGE = cfg['twitch']['gifted_message']
    BITS_MESSAGE = cfg['twitch']['bits_message']
    TIP_MESSAGE = cfg['twitch']['tip_message']

    SPOTIFY_CLIENT_ID = cfg['spotify']['client_id']
    SPOTIFY_SECRET = cfg['spotify']['secret_key']
    SPOTIFY_PLAYLIST_URI = cfg['spotify']['playlist_uri']
    SPOTIFY_REQUEST_URI = cfg['spotify']['request_uri']

    AMOUNT_BITS = int(cfg['b0pperbot']['amount_bits'])
    AMOUNT_GIFTED_TIER1 = int(cfg['b0pperbot']['amount_gifted_tier1'])
    AMOUNT_GIFTED_TIER2 = int(cfg['b0pperbot']['amount_gifted_tier2'])
    AMOUNT_GIFTED_TIER3 = int(cfg['b0pperbot']['amount_gifted_tier3'])
    AMOUNT_TIP = float(cfg['b0pperbot']['amount_tip'])
    DO_CLEAN_PLAYLIST = bool(cfg['b0pperbot']['clean_playlist'])
    SIGNAL_BOT = cfg['b0pperbot']['signal_bot']
    REQUEST_CMD = cfg['b0pperbot']['request_cmd']
    SONG_CMD = cfg['b0pperbot']['song_cmd']
    CREDIT_CMD = cfg['b0pperbot']['credit_cmd']
    DISABLE_CREDIT_CMD = bool(cfg['b0pperbot']['disable_credit_cmd'])
    CUMULATIVE_CREDIT = bool(cfg['b0pperbot']['cumulative_credit'])
except Exception:
    print('Error reading "config.ini".')
    fail()

#global variables
app_name = 'B0pperBot'
tippers = {}
playlist_tracks = []
sp = 0

#cache the playlist into a list
def cache_playlist():

    print('Caching playlist...')

    global playlist_tracks
    offset = 0
    while True:
        response = sp.playlist_items(SPOTIFY_PLAYLIST_URI,
                offset=offset,
                fields='items.track.id,items.track.uri,total',
                additional_types=['track'])

        if len(response['items']) == 0:
            break
        
        playlist_tracks.append(response['items'])

        offset = offset + len(response['items'])

    playlist_tracks = playlist_tracks[0]
    for track in playlist_tracks:
        track['track']['requested'] = False

#setup playlist when Twitch is ready and Spotify connection established
async def on_ready(ready_event: EventData):

    cache_playlist()

    print(app_name, 'is ready.\n')
    help()
    await ready_event.chat.join_room(TARGET_CHANNEL)

#parse signal bot chat notifications and calculate
#tippers credit for song requests
async def on_message(msg: ChatMessage):

    global tippers
    global playlist_tracks

    if msg.user.name.lower() == SIGNAL_BOT.lower():

        #Parsing streamlabs chat notifications, for example:
        #   Thank you username for donating 100 bits
        #   username just gifted 1 Tier 1 subscriptions!
        #   Thank you username for tipping $1.00!

        tipper = ''
        amount = 0
        credit = tippers.get(msg.user.name.lower(),0)

        if re.match(TIP_MESSAGE, msg.text):
            line = msg.text.split()
            amount = float(line[5][1:-1])
            print("dollar amount", amount)
            tipper = line[2]
            if amount >= AMOUNT_TIP:
                if CUMULATIVE_CREDIT:
                    #TODO currency conversion
                    if line[5].startswith('$'):
                        credit += round(amount/AMOUNT_TIP)
                else:
                    credit = 1

        if re.match(BITS_MESSAGE, msg.text):
            line = msg.text.split()
            amount = int(line[5])
            tipper = line[2]
            if amount >= AMOUNT_BITS:
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_BITS)
                else:
                    credit = 1
        
        if re.match(GIFTED_MESSAGE, msg.text):
            line = msg.text.split()
            amount = int(line[3])
            tipper = line[0]
            tier = 1
            if int(line[5]) == 1 and amount >= AMOUNT_GIFTED_TIER1:
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_GIFTED_TIER1)
                else:
                    credit = 1
            if int(line[5]) == 2 and amount >= AMOUNT_GIFTED_TIER2:
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_GIFTED_TIER2)
                else:
                    credit = 1
            if int(line[5]) == 3 and amount >= AMOUNT_GIFTED_TIER3:
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_GIFTED_TIER3)
                else:
                    credit = 1

        tippers[tipper.lower()] = round(credit)
        if tipper: print(tipper+'\'s credit is now', str(credit))

#display help
def help(command = ''):
    if command == '':
        print('Commands: playlist, tippers, refresh, reset, help, quit (or exit). For further help, type \
"help <command>".')
    if command == 'playlist':
        print('The "playlist" command prints the cachced playlist.')
    if command == 'quit':
        print('The "quit" command deactivates', app_name, 'and exits the program.')
    if command == 'help':
        print('The "help" command provides... help.')
    if command == 'reset':
        print('The "reset" command reverts', app_name, 'back to the startup state.')
    if command == 'refresh':
        print('The "refresh" command is like reset but keeps the tippers list and \
credit associated with each tipper.')
    if command == 'tippers':
        print('The "tippers" command prints the tipper\'s twitch username and their credit')


#if clean_playlist is specificed in config.ini
#then when program is reset or exited it will
#remove all the requested songs from the playlist
#to preserve the original curated playlist
def clean_playlist():

    global DO_CLEAN_PLAYLIST
    if not DO_CLEAN_PLAYLIST: return

    print('Removing requested songs from playlist...')

    i = 0
    for track in playlist_tracks:

        if track['track']['requested']:
            tid = track['track']['id']
            pos = track['track']['pos'] - i
            track_ids = []
            track_ids.append({'uri': tid, 'positions': [int(pos)]})
            sp.playlist_remove_specific_occurrences_of_items(
            SPOTIFY_PLAYLIST_URI, track_ids
            )
            i+=1


#bot will reply with how much credit tipper has
async def credit_command(cmd: ChatCommand):
    if not DISABLE_CREDIT_CMD: return
    credit = tippers.get(cmd.user.name.lower(), 0)
    await cmd.reply(f'@{cmd.user.name}, you have {credit} song request credit(s).')

#bot will reply with currently playing song
async def song_command(cmd: ChatCommand):

    tr = sp.currently_playing()

    if tr == None:
        await cmd.reply("There is currently no song playing.")
        return
    
    name = tr['item']['name']
    artist = tr['item']['artists'][0]["name"]

    await cmd.reply(f'@{cmd.user.name}, Current song is {name} by {artist}.')

#bot will add song to playlist if tipper has credit
async def request_command(cmd: ChatCommand):
    if cmd.user.name.lower() in tippers.keys():
        if tippers[cmd.user.name.lower()] >= 1:
            tippers[cmd.user.name.lower()] -= 1

            tr = sp.currently_playing()

            if tr == None:
                print("There is currently no song playing.")
                return

            ci = 0

            for track in playlist_tracks:
                ci += 1
                if track['track']['id'] == tr['item']['id']:
                    break
            
            for idx, track in enumerate(playlist_tracks):
                if idx >= ci and track['track']['requested']:
                    ci += 1

            results = sp.search(q=cmd.parameter, limit=1)
            track_uris = []
            for idx, track in enumerate(results['tracks']['items']):
                track_uris.append(track['uri'])

                nt = {}
                nt['uri'] = track['uri']
                nt['requested'] = True
                nt['id'] = track['id']
                nt['pos'] = ci
                playlist_tracks.insert(ci, {'track': nt})

                name = track['name']
                artist = track['artists'][0]["name"]
                await cmd.reply(f'@{cmd.user.name}, added {name} by {artist} to the playlist.')

                print('Added requested track to position', str(ci))

            sp.playlist_add_items(SPOTIFY_PLAYLIST_URI, track_uris,ci)

#set up twitch interface and main program loop
async def run():

    global tippers
    global playlist_tracks

    try:
        twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_SECRET)
        auth = UserAuthenticator(twitch, USER_SCOPE)

        token, refresh_token = await auth.authenticate()
        await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)
    except Exception:
        print('Error connecting to Twitch.')
        fail()

    global sp
    try:
        scope = 'user-read-currently-playing user-library-read \
                playlist-modify-private playlist-modify-public'
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_SECRET,
            redirect_uri=SPOTIFY_REQUEST_URI,
            scope=scope
            ))
    except Exception:
        print('Error connecting to Spotify.')
        fail()

    try:
        chat = await Chat(twitch)
        chat.register_event(ChatEvent.READY, on_ready)
        chat.register_event(ChatEvent.MESSAGE, on_message)
        chat.register_command(REQUEST_CMD, request_command)
        chat.register_command(SONG_CMD, song_command)
        chat.register_command(CREDIT_CMD, credit_command)

        chat.start()
    except Exception:
        print('Error enterting chat and registering commands.')
        fail()

    print()
    print(
'''
 ██▄ █▀█ █▀▄ █▀▄ ██▀ █▀▄ ██▄ ▄▀▄ ▀█▀
 █▄█ █▄█ █▀  █▀  █▄▄ █▀▄ █▄█ ▀▄▀  █ 
'''
)

    global tippers
    global playlist_tracks

    quit = False
    while not quit:

        line = input()
        line = line.split()
        
        if len(line) >= 1:
            cmd = line[0]

            if cmd == 'help':
                if len(line) >= 2:
                    help(line[1])
                else:
                    help()
            if cmd == 'quit' or cmd == 'exit':
                quit = True
            
            if cmd == 'reset':
                print('Clearing tippers list...')
                tippers = {}
                
                clean_playlist()

                print('Clearing playlist cache...')
                playlist_tracks = []

                cache_playlist()
            if cmd == 'refresh':
                clean_playlist()
                print('Clearing playlist cache...')
                playlist_tracks = []

                cache_playlist()
            
            if cmd == "tippers":
                pprint(tippers)
            
            if cmd == "playlist":
                pprint(playlist_tracks)

    print('Leaving Twitch...')
    chat.stop()
    await twitch.close()

    clean_playlist()

    print('Exiting...')

asyncio.run(run())