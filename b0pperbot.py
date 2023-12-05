#!/usr/bin/env python3
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.oauth import UserAuthenticationStorageHelper
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand
import configparser

from sys import exit
from pprint import pprint

import asyncio
import requests
import re

#global variables
app_name = 'B0pperBot'
tippers = {}
playlist_tracks = []
sp = 0

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

    AMOUNT_BITS = cfg.getint('b0pperbot', 'amount_bits')
    AMOUNT_GIFTED_TIER1 = cfg.getint('b0pperbot', 'amount_gifted_tier1')
    AMOUNT_GIFTED_TIER2 = cfg.getint('b0pperbot','amount_gifted_tier2')
    AMOUNT_GIFTED_TIER3 = cfg.getint('b0pperbot', 'amount_gifted_tier3')
    AMOUNT_TIP = cfg.getfloat('b0pperbot', 'amount_tip')
    DO_CLEAN_PLAYLIST = cfg.getboolean('b0pperbot', 'clean_playlist')
    SIGNAL_BOT = cfg.get('b0pperbot', 'signal_bot')
    REQUEST_CMD = cfg.get('b0pperbot', 'request_cmd')
    SONG_CMD = cfg.get('b0pperbot', 'song_cmd')
    CREDIT_CMD = cfg.get('b0pperbot', 'credit_cmd')
    DISABLE_CREDIT_CMD = cfg.getboolean('b0pperbot', 'disable_credit_cmd')
    DISABLE_SONG_CMD = cfg.getboolean('b0pperbot', 'disable_song_cmd')
    DISABLE_REQUEST_CMD = cfg.getboolean('b0pperbot', 'disable_request_cmd')
    CUMULATIVE_CREDIT = cfg.getboolean('b0pperbot', 'cumulative_credit')
except Exception:
    print('Error reading "config.ini".')
    fail()

#cache the playlist into a list
def cache_playlist():

    print('Caching playlist...')

    global playlist_tracks
    offset = 0
    try:
        while True:
            response = sp.playlist_items('spotify:playlist:' + SPOTIFY_PLAYLIST_URI,
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
    except Exception:
        print('Error getting Spotify playlist.')
        fail()

#setup playlist when Twitch is ready and Spotify connection established
async def on_ready(ready_event: EventData):

    cache_playlist()

    print(app_name, 'is ready.\n')
    help()
    await ready_event.chat.join_room(TARGET_CHANNEL)

#parse signal bot chat notifications and calculate
#tippers credit for song requests
async def on_message(msg: ChatMessage):

    if DISABLE_REQUEST_CMD: return

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
            if amount >= AMOUNT_TIP:
                tipper = line[2]
                if CUMULATIVE_CREDIT:
                    #TODO currency conversion
                    if line[5].startswith('$'):
                        credit += round(amount/AMOUNT_TIP)
                else:
                    credit = 1

        if re.match(BITS_MESSAGE, msg.text):
            line = msg.text.split()
            amount = int(line[5])
            if amount >= AMOUNT_BITS:
                tipper = line[2]
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_BITS)
                else:
                    credit = 1
        
        if re.match(GIFTED_MESSAGE, msg.text):
            line = msg.text.split()
            amount = int(line[3])
            tier = 1
            if int(line[5]) == 1 and amount >= AMOUNT_GIFTED_TIER1:
                tipper = line[0]
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_GIFTED_TIER1)
                else:
                    credit = 1
            if int(line[5]) == 2 and amount >= AMOUNT_GIFTED_TIER2:
                tipper = line[0]
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_GIFTED_TIER2)
                else:
                    credit = 1
            if int(line[5]) == 3 and amount >= AMOUNT_GIFTED_TIER3:
                tipper = line[0]
                if CUMULATIVE_CREDIT:
                    credit += round(amount/AMOUNT_GIFTED_TIER3)
                else:
                    credit = 1

        if tipper:
            tippers[tipper.lower()] = round(credit)
            print(tipper + '\'s credit is now', str(credit))

#display help
def help(command = ''):
    if command == '':
        print('Commands: stop, start, tippers, refresh, reset, help, quit (or exit). For further help, type \
"help <command>".')
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
    if command == 'start':
        print('The "start" command enables song requests.')
    if command == 'stop':
        print('The "stop" command disables song requests. Also disables credit command.')

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
    if DISABLE_CREDIT_CMD: return
    credit = tippers.get(cmd.user.name.lower(), 0)
    await cmd.reply(f'@{cmd.user.name}, you have {credit} song request credit(s).')

#bot will reply with currently playing song
async def song_command(cmd: ChatCommand):

    if DISABLE_SONG_CMD: return

    tr = sp.currently_playing()

    if tr == None:
        await cmd.reply("There is currently no song playing.")
        return
    
    name = tr['item']['name']
    artist = tr['item']['artists'][0]["name"]

    await cmd.reply(f'@{cmd.user.name}, current song is {name} by {artist}.')

#bot will add song to playlist if tipper has credit
async def request_command(cmd: ChatCommand):

    if DISABLE_REQUEST_CMD: return

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

def request_start():
    global DISABLE_REQUEST_CMD
    global DISABLE_CREDIT_CMD
    DISABLE_REQUEST_CMD = False
    DISABLE_CREDIT_CMD = cfg.getboolean('b0pperbot', 'disable_credit_cmd')
    print('Requests are enabled.')

def request_stop():
    global DISABLE_REQUEST_CMD
    global DISABLE_CREDIT_CMD
    DISABLE_REQUEST_CMD = True
    DISABLE_CREDIT_CMD = True
    print('Requests are disabled.')

#set up twitch interface and main program loop
async def run():

    global tippers
    global playlist_tracks

    print()
    print(
'''
 ██▄ █▀█ █▀▄ █▀▄ ██▀ █▀▄ ██▄ ▄▀▄ ▀█▀
 █▄█ █▄█ █▀  █▀  █▄▄ █▀▄ █▄█ ▀▄▀  █ 
'''
)
    print()

    print(app_name, 'is starting...')

    try:
        print('Authenticating with Twitch...')
        twitch_scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
        twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_SECRET)
        auth = UserAuthenticator(twitch, twitch_scope)

        token, refresh_token = await auth.authenticate()
        await twitch.set_user_authentication(token, twitch_scope, refresh_token)
    except Exception:
        print('Error conneceting to Twitch.')
        fail()

    global sp
    try:
        print('Authenticating with Spotify...')
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
    
    print()
    pl = input('Playlist ID: ')
    if pl:
        SPOTIFY_PLAYLIST_URI = pl

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
            
            if cmd == 'tippers':
                pprint(tippers)
            
            if cmd == 'playlist':
                pprint(playlist_tracks)
            
            if cmd == 'start':
                request_start()
            
            if cmd == 'stop':
                request_stop()

    print('Leaving Twitch...')
    chat.stop()
    await twitch.close()

    clean_playlist()

    print('Exiting...')

asyncio.run(run())