#!/usr/bin/env python3
from sys import exit
from pprint import pprint

import pyperclip
import configparser
import asyncio
import time
import math
import re

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.oauth import UserAuthenticationStorageHelper
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand

#global variables
app_name = 'B0pperBot'
tippers = {}
playlist_tracks = []
sp = 0
chat = 0

def fail(*args):
    print( ' '.join(map(str,args)))
    print('Exiting...')
    exit(-1)

#read from config.ini
cfg = configparser.ConfigParser()

try:
    cfg.read('config.ini')

    TWITCH_CLIENT_ID = cfg['twitch']['client_id']
    TWITCH_SECRET = cfg['twitch']['secret_key']
    TARGET_CHANNEL = cfg['twitch']['channel']

    SPOTIFY_CLIENT_ID = cfg['spotify']['client_id']
    SPOTIFY_SECRET = cfg['spotify']['secret_key']
    SPOTIFY_PLAYLIST_URL = cfg['spotify']['playlist_url']
    SPOTIFY_PLAYLIST_URI = ''
except Exception as r:
    fail('Error reading "config.ini".', str(r))
else:
    SPOTIFY_REQUEST_URI = cfg.get('spotify', 'request_uri', fallback='http://localhost:3000')

    GIFTED_REGEX = cfg.get('twitch', 'gifted_regex', fallback='.* just gifted [1-9][0-9]* Tier [1-3]? subscriptions!')
    BITS_REGEX = cfg.get('twitch', 'bits_regex', fallback='Thank you .* for donating [1-9][0-9]* bits')
    TIP_REGEX = cfg.get('twitch', 'tip_regex', fallback='Thank you .* for tipping \$(0|[1-9][0-9])*\.(0|[0-9][0-9])??!')

    SIGNAL_BOT = cfg.get('twitch', 'signal_bot', fallback='Streamlabs')
    TWITCH_REQUEST_URI = cfg.get('twitch', 'request_uri', fallback='http://localhost:17563')

    AMOUNT_BITS = cfg.getint('cost', 'amount_bits', fallback=10000)
    AMOUNT_GIFTED_TIER1 = cfg.getint('cost', 'amount_gifted_tier1', fallback=20)
    AMOUNT_GIFTED_TIER2 = cfg.getint('cost','amount_gifted_tier2', fallback=10)
    AMOUNT_GIFTED_TIER3 = cfg.getint('cost', 'amount_gifted_tier3', fallback=5)
    AMOUNT_TIP = cfg.getfloat('cost', 'amount_tip', fallback=100.00)

    CLEAN_PLAYLIST = cfg.getboolean('b0pperbot', 'clean_playlist', fallback=True)
    REQUEST_CMD = cfg.get('b0pperbot', 'request_cmd', fallback='request')
    SONG_CMD = cfg.get('b0pperbot', 'song_cmd', fallback='song')
    CREDIT_CMD = cfg.get('b0pperbot', 'credit_cmd', fallback='credit')
    DISABLE_CREDIT_CMD = cfg.getboolean('b0pperbot', 'disable_credit_cmd', fallback=False)
    DISABLE_SONG_CMD = cfg.getboolean('b0pperbot', 'disable_song_cmd', fallback=False)
    DISABLE_REQUEST_CMD = cfg.getboolean('b0pperbot', 'disable_request_cmd', fallback=False)
    CUMULATIVE_CREDIT = cfg.getboolean('b0pperbot', 'cumulative_credit', fallback=True)

    CREDIT_MESSAGE = cfg.get('messages', 'credit_message', fallback="f'@{username}, you have {credit} song request credit(s).")
    SONG_MESSAGE = cfg.get('messages', 'song_message', fallback="f'@{username}, current song is {name} by {artist}.'")
    NO_SONG_MESSAGE = cfg.get('messages', 'no_song_message', fallback="f'@{username}, there is currently no song playing.'")
    REQUEST_MESSAGE = cfg.get('messages', 'request_message', fallback="f'@{username}, added {name} by {artist} to the playlist.'")
    NOTIFY_MESSAGE = cfg.get('messages', 'notify_message', fallback="f'@{username}, you now have {credit} song request credit(s).'")

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
    except Exception as r:
        fail('Error getting Spotify playlist.', str(r))

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

        r = re.match(TIP_REGEX, msg.text)
        if r:
            amount = float(r.groups()[1])
            print("dollar amount", amount)
            if amount >= AMOUNT_TIP:
                tipper = r.groups()[0]
                if CUMULATIVE_CREDIT:
                    #TODO currency conversion
                    credit += math.floor(amount/AMOUNT_TIP)
                else:
                    credit = 1

        r = re.match(BITS_REGEX, msg.text)
        if r:
            amount = int(r.groups()[1])
            if amount >= AMOUNT_BITS:
                tipper = r.groups()[0]
                if CUMULATIVE_CREDIT:
                    credit += math.floor(amount/AMOUNT_BITS)
                else:
                    credit = 1

        r = re.match(GIFTED_REGEX, msg.text)
        if r:
            tier = r.groups()[2]
            amount = int(r.groups()[1])
            if int(tier) == 1 and amount >= AMOUNT_GIFTED_TIER1:
                tipper = r.groups()[0]
                if CUMULATIVE_CREDIT:
                    credit += math.floor(amount/AMOUNT_GIFTED_TIER1)
                else:
                    credit = 1
            if int(tier) == 2 and amount >= AMOUNT_GIFTED_TIER2:
                tipper = r.groups()[0]
                if CUMULATIVE_CREDIT:
                    credit += math.floor(amount/AMOUNT_GIFTED_TIER2)
                else:
                    credit = 1
            if int(tier) == 3 and amount >= AMOUNT_GIFTED_TIER3:
                tipper = r.groups()[0]
                if CUMULATIVE_CREDIT:
                    credit += math.floor(amount/AMOUNT_GIFTED_TIER3)
                else:
                    credit = 1

        if tipper:
            tippers[tipper.lower()] = math.floor(credit)
            credit = str(credit)
            username = tipper
            print(username, 'now has', credit,'song request credit(s)')
            await chat.send_message(TARGET_CHANNEL, eval(NOTIFY_MESSAGE))

#give 1 credit to user
def give(username = ''):
    if username:
        if username.lower() in tippers.keys():
            tippers[username.lower()] += 1
        else:
            tippers[username.lower()] = 1


#display help
def help(command = ''):
    if command == '':
        print('Commands: stop, start, tippers, refresh, reset, give, help, quit (or exit). For further help, type \
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
        print('The "stop" command disables song requests.')
    if command == 'give':
        print('The "give <username>" command will give 1 credit to <username>.')

#if clean_playlist is specificed in config.ini
#then when program is reset or exited it will
#remove all the requested songs from the playlist
#to preserve the original curated playlist
def clean_playlist():

    global CLEAN_PLAYLIST
    if not CLEAN_PLAYLIST: return

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
            print('Removing track', tid)
            time.sleep(0.3)
            i+=1


#bot will reply with how much credit tipper has
async def credit_command(cmd: ChatCommand):
    if DISABLE_CREDIT_CMD: return
    
    username = cmd.user.name
    credit = 0
    if username.lower() in tippers.keys():
        credit = tippers[username.lower()]

    await cmd.reply(eval(CREDIT_MESSAGE))

#bot will reply with currently playing song
async def song_command(cmd: ChatCommand):

    if DISABLE_SONG_CMD: return

    tr = sp.currently_playing()

    username = cmd.user.name

    if tr == None:
        await cmd.reply(eval(NO_SONG_MESSAGE))
        return

    name = tr['item']['name']
    artist = tr['item']['artists'][0]['name']

    await cmd.reply(eval(SONG_MESSAGE))

#bot will add song to playlist if tipper has credit
async def request_command(cmd: ChatCommand):

    if DISABLE_REQUEST_CMD: return

    if cmd.user.name.lower() in tippers.keys():
        if tippers[cmd.user.name.lower()] >= 1:

            tr = sp.currently_playing()

            if tr == None:
                print("There is currently no song playing.")
                return
                
            tippers[cmd.user.name.lower()] -= 1

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
                username = cmd.user.name

                await cmd.reply(eval(REQUEST_MESSAGE))

                print(username, 'added', name, 'by', artist, 'to position', str(ci+1), 'in the playlist.')

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

#set up twitch and spotify interface and main program loop
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
    except Exception as r:
        fail('Error connecting to Spotify.', str(r))
    
    global SPOTIFY_PLAYLIST_URL
    global SPOTIFY_PLAYLIST_URI

    rp = 'https://open.spotify.com/playlist/(.*)\?si=(.*)'

    if not SPOTIFY_PLAYLIST_URL:

        cd = pyperclip.paste()
        r = re.match(rp,cd)
        if r:
            print()
            print('Using copied playlist URL:', cd)
            SPOTIFY_PLAYLIST_URL = cd
            SPOTIFY_PLAYLIST_URI = r.groups()[0]
        else:

            print()
            pl = input('Playlist URL: ')
            if pl:
                SPOTIFY_PLAYLIST_URL = pl
                r = re.match(rp,pl)
                if r:
                    SPOTIFY_PLAYLIST_URI = r.groups()[0]
                else:
                    fail('Invalid playlist URL.')
    else:
        print()
        print('Using config playlist URL:', SPOTIFY_PLAYLIST_URL)
        r = re.match(rp,SPOTIFY_PLAYLIST_URL)
        if r:
            SPOTIFY_PLAYLIST_URI = r.groups()[0]
        else:
            fail('Invalid playlist URL.')
    print()
    

    try:
        print('Authenticating with Twitch...')
        twitch_scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
        twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_SECRET)
        auth = UserAuthenticator(twitch, twitch_scope)

        token, refresh_token = await auth.authenticate()
        await twitch.set_user_authentication(token, twitch_scope, refresh_token)
    except Exception as r:
        fail('Error conneceting to Twitch.', str(r))


    try:
        global chat
        chat = await Chat(twitch)
        chat.register_event(ChatEvent.READY, on_ready)
        chat.register_event(ChatEvent.MESSAGE, on_message)
        chat.register_command(REQUEST_CMD, request_command)
        chat.register_command(SONG_CMD, song_command)
        chat.register_command(CREDIT_CMD, credit_command)

        chat.start()
    except Exception as r:
        fail('Error enterting chat and registering commands.', str(r))

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
            
            if cmd == 'give':
                if len(line) >= 2:
                    give(line[1])
                else:
                    print('No <username> specified.')
            
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

if __name__ == '__main__':
    asyncio.run(run())