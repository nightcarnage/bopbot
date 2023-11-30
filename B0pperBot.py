import spotipy
from spotipy.oauth2 import SpotifyOAuth

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.oauth import UserAuthenticationStorageHelper
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand
USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]

from sys import exit
import configparser

from pprint import pprint

import asyncio
import requests
import readline
import re

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
    CLEAN_PLAYLIST = bool(cfg['b0pperbot']['clean_playlist'])
    SIGNAL_BOT = cfg['b0pperbot']['signal_bot']
    REQUEST_CMD = cfg['b0pperbot']['request_cmd']
    SONG_CMD = cfg['b0pperbot']['song_cmd']
    CREDIT_CMD = cfg['b0pperbot']['credit_cmd']
except:
    print('Cannot read "config.ini".')
    print('Exiting...')
    exit(-1)

app_name = 'B0pperBot'
donors = {}
playlist_tracks = []
bot_ready = False
sp = 0
#last_ci = -1
#ci_inc = 0

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
        track['track']['bopped'] = False

async def on_ready(ready_event: EventData):

    global sp
    scope = 'user-read-currently-playing user-library-read \
            playlist-modify-private playlist-modify-public'
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_SECRET,
        redirect_uri=SPOTIFY_REQUEST_URI,
        scope=scope
        ))
    
    cache_playlist()

    print(app_name, 'is ready.\n')
    global bot_ready
    bot_ready = True
    help()
    await ready_event.chat.join_room(TARGET_CHANNEL)

async def on_message(msg: ChatMessage):
    #print(f'in {msg.room.name}, {msg.user.name} said: {msg.text}')

    global donors
    global playlist_tracks

    if msg.user.name.lower() == SIGNAL_BOT.lower():

        #Parsing streamlabs chat notifications, for example:
        #   Thank you username for donating 100 bits
        #   username just gifted 1 Tier 1 subscriptions!
        #   Thank you username for tipping $1.00!

        donor = ''
        amount = 0
        credit = donors.get(msg.user.name.lower(),0)

        if re.match(TIP_MESSAGE, msg.text):
            line = msg.text.split()
            amount = float(line[5][1:-1])
            print("dollar amount", amount)
            donor = line[2]
            if amount >= AMOUNT_TIP:
                #TODO currency conversion
                if line[5].startswith('$'):
                    credit += round(amount/AMOUNT_TIP)

        if re.match(BITS_MESSAGE, msg.text):
            line = msg.text.split()
            amount = int(line[5])
            donor = line[2]
            if amount >= AMOUNT_BITS:
                credit += round(amount/AMOUNT_BITS)
        
        if re.match(GIFTED_MESSAGE, msg.text):
            line = msg.text.split()
            amount = int(line[3])
            donor = line[0]
            tier = 1
            if int(line[5]) == 1 and amount >= AMOUNT_GIFTED_TIER1:
                credit += round(amount/AMOUNT_GIFTED_TIER1)
            if int(line[5]) == 2 and amount >= AMOUNT_GIFTED_TIER2:
                credit += round(amount/AMOUNT_GIFTED_TIER2)
            if int(line[5]) == 3 and amount >= AMOUNT_GIFTED_TIER3:
                credit += round(amount/AMOUNT_GIFTED_TIER3)

        donors[donor.lower()] = round(credit)
        if donor: print(donor+'\'s credit is now', str(credit))

def help(command = ''):
    if command == '':
        print('Commands: playlist, donors, refresh, reset, help, quit. For further help, type \
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
        print('The "refresh" command is like reset but keeps the donor list and \
credit associated with each donor.')
    if command == 'donors':
        print('The "donors" command prints the donor\'s twitch username and their credit')

def clean_playlist():


    global CLEAN_PLAYLIST
    if not CLEAN_PLAYLIST: return

    print('Removing requested songs from playlist...')

    i = 0
    for track in playlist_tracks:

        if track['track']['bopped']:
            tid = track['track']['id']
            pos = track['track']['pos'] - i
            track_ids = []
            track_ids.append({'uri': tid, 'positions': [int(pos)]})
            sp.playlist_remove_specific_occurrences_of_items(
            SPOTIFY_PLAYLIST_URI, track_ids
            )
            i+=1


async def credit_command(cmd: ChatCommand):

    credit = donors.get(cmd.user.name.lower(), 0)
    await cmd.reply(f'@{cmd.user.name}, you have {credit} credit.')

async def song_command(cmd: ChatCommand):

    tr = sp.currently_playing()

    if tr == None:
        await cmd.reply("There is currently no song playing.")
        return
    
    name = tr['item']['name']
    artist = tr['item']['artists'][0]["name"]

    await cmd.reply(f'@{cmd.user.name}, Current song is {name} by {artist}.')


async def request_command(cmd: ChatCommand):
    if cmd.user.name.lower() in donors.keys():
        if donors[cmd.user.name.lower()] >= 1:
            donors[cmd.user.name.lower()] -= 1

            tr = sp.currently_playing()

            if tr == None:
                print("There is currently no song playing.")
                return

            ci = 0
            #offset = 0
            #global last_ci
            #global ci_inc

            for track in playlist_tracks:
                ci += 1
                if track['track']['id'] == tr['item']['id']:
                    break
            
            for idx, track in enumerate(playlist_tracks):
                if idx >= ci and track['track']['bopped']:
                    ci += 1

                
            '''
            if ci == last_ci:
                offset += ci_inc
            else:
                offset = 0
                last_ci = ci
                ci_inc = 0
            
            ci = ci + offset
            '''

            results = sp.search(q=cmd.parameter, limit=1)
            track_uris = []
            for idx, track in enumerate(results['tracks']['items']):
                track_uris.append(track['uri'])

                nt = {}
                nt['uri'] = track['uri']
                nt['bopped'] = True
                nt['id'] = track['id']
                nt['pos'] = ci
                playlist_tracks.insert(ci, {'track': nt})

                name = track['name']
                artist = track['artists'][0]["name"]
                await cmd.reply(f'@{cmd.user.name}, added {name} by {artist} to the playlist.')

                print('Added requested track to position', str(ci))

            sp.playlist_add_items(SPOTIFY_PLAYLIST_URI, track_uris,ci)
            #ci_inc += 1

async def run():

    global donors
    global playlist_tracks

    twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_SECRET)
    auth = UserAuthenticator(twitch, USER_SCOPE)

    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)

    chat = await Chat(twitch)
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_event(ChatEvent.MESSAGE, on_message)
    chat.register_command(REQUEST_CMD, request_command)
    chat.register_command(SONG_CMD, song_command)
    chat.register_command(CREDIT_CMD, credit_command)

    chat.start()

    print()
    print(
'''
 ┌┐ ┌─┐┌─┐┌─┐┌─┐┬─┐┌┐ ┌─┐┌┬┐
 ├┴┐│ │├─┘├─┘├┤ ├┬┘├┴┐│ │ │ 
 └─┘└─┘┴  ┴  └─┘┴└─└─┘└─┘ ┴ 
'''
)
    #try:
    quit = False
    while not quit:

        if not bot_ready: continue

        line = input('cmd: ')
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
                print('Clearing donor list...')
                donors = {}
                
                clean_playlist()

                print('Clearing playlist cache...')
                playlist_tracks = []

                cache_playlist()
            if cmd == 'refresh':
                clean_playlist()
                print('Clearing playlist cache...')
                playlist_tracks = []

                cache_playlist()
            
            if cmd == "donors":
                pprint(donors)
            
            if cmd == "playlist":
                pprint(playlist_tracks)

    #finally:

    print('Leaving Twitch...')
    chat.stop()
    await twitch.close()

    clean_playlist()

    print('Exiting...')

asyncio.run(run())