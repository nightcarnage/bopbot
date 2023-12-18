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

from twisted.web import server, resource, static
from twisted.internet import reactor
from twisted.web.util import redirectTo

import html
import json

from jinja2 import Environment, FileSystemLoader

from markdown import markdown

import bcrypt
from getpass import getpass

#global variables
app_name = 'BopBot'
tippers = {}
playlist_tracks = []
sp = 0
env = Environment(loader=FileSystemLoader('templates/'))
cfg = configparser.ConfigParser()
error = None
quit = False
auth_sessions = []

BOPBOT_WEB = False
TWITCH_CLIENT_ID = ''
TWITCH_SECRET = ''
TARGET_CHANNEL = ''
SPOTIFY_CLIENT_ID = ''
SPOTIFY_SECRET = ''
SPOTIFY_PLAYLIST_URL = ''
SPOTIFY_PLAYLIST_URI = ''
SPOTIFY_REQUEST_URI = ''
GIFTED_REGEX = ''
BITS_REGEX = ''
TIP_REGEX = ''
SIGNAL_BOT =''
TWITCH_REQUEST_URI = ''
AMOUNT_BITS = 0
AMOUNT_GIFTED_TIER1 = 0
AMOUNT_GIFTED_TIER2 = 0
AMOUNT_GIFTED_TIER3 = 0
AMOUNT_TIP = 0.0
CLEAN_PLAYLIST = False
REQUEST_CMD = ''
SONG_CMD = ''
CREDIT_CMD = ''
DISABLE_CREDIT_CMD = False
DISABLE_SONG_CMD = False
DISABLE_REQUEST_CMD = False
CUMULATIVE_CREDIT = True
CREDIT_MESSAGE = ''
SONG_MESSAGE = ''
NO_SONG_MESSAGE = ''
REQUEST_MESSAGE = ''
NOTIFY_MESSAGE = ''

def fail(*args):
    global error
    er = ' '.join(map(str,args))
    error = er
    print(er)
    return er
    #print('Exiting...')
    #exit(-1)

#read from config.ini
def read_conf():

    global BOPBOT_WEB
    global TWITCH_CLIENT_ID
    global TWITCH_SECRET
    global TARGET_CHANNEL
    global SPOTIFY_CLIENT_ID
    global SPOTIFY_SECRET
    global SPOTIFY_PLAYLIST_URL
    global SPOTIFY_PLAYLIST_URI
    global SPOTIFY_REQUEST_URI
    global GIFTED_REGEX
    global BITS_REGEX
    global TIP_REGEX
    global SIGNAL_BOT
    global TWITCH_REQUEST_URI
    global AMOUNT_BITS
    global AMOUNT_GIFTED_TIER1
    global AMOUNT_GIFTED_TIER2
    global AMOUNT_GIFTED_TIER3
    global AMOUNT_TIP
    global CLEAN_PLAYLIST
    global REQUEST_CMD
    global SONG_CMD
    global CREDIT_CMD
    global DISABLE_CREDIT_CMD
    global DISABLE_SONG_CMD
    global DISABLE_REQUEST_CMD
    global CUMULATIVE_CREDIT
    global CREDIT_MESSAGE
    global SONG_MESSAGE
    global NO_SONG_MESSAGE
    global REQUEST_MESSAGE
    global NOTIFY_MESSAGE

    try:
        cfg.read('config.ini')

        BOPBOT_WEB = cfg.getboolean('bopbot', 'bopbot_web', fallback=False)

        TWITCH_CLIENT_ID = cfg['twitch']['client_id']
        TWITCH_SECRET = cfg['twitch']['secret_key']
        TARGET_CHANNEL = cfg['twitch']['channel']

        SPOTIFY_CLIENT_ID = cfg['spotify']['client_id']
        SPOTIFY_SECRET = cfg['spotify']['secret_key']
        SPOTIFY_PLAYLIST_URL = cfg['spotify']['playlist_url']
        SPOTIFY_PLAYLIST_URI = ''
    except Exception as r:
        return fail('Error reading from "config.ini".', str(r))
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

        CLEAN_PLAYLIST = cfg.getboolean('bopbot', 'clean_playlist', fallback=True)
        REQUEST_CMD = cfg.get('bopbot', 'request_cmd', fallback='request')
        SONG_CMD = cfg.get('bopbot', 'song_cmd', fallback='song')
        CREDIT_CMD = cfg.get('bopbot', 'credit_cmd', fallback='credit')
        DISABLE_CREDIT_CMD = cfg.getboolean('bopbot', 'disable_credit_cmd', fallback=False)
        DISABLE_SONG_CMD = cfg.getboolean('bopbot', 'disable_song_cmd', fallback=False)
        DISABLE_REQUEST_CMD = cfg.getboolean('bopbot', 'disable_request_cmd', fallback=False)
        CUMULATIVE_CREDIT = cfg.getboolean('bopbot', 'cumulative_credit', fallback=True)

        CREDIT_MESSAGE = cfg.get('messages', 'credit_message', fallback="f'@{username}, you have {credit} song request credit(s).")
        SONG_MESSAGE = cfg.get('messages', 'song_message', fallback="f'@{username}, current song is {name} by {artist}.'")
        NO_SONG_MESSAGE = cfg.get('messages', 'no_song_message', fallback="f'@{username}, there is currently no song playing.'")
        REQUEST_MESSAGE = cfg.get('messages', 'request_message', fallback="f'@{username}, added {name} by {artist} to the playlist.'")
        NOTIFY_MESSAGE = cfg.get('messages', 'notify_message', fallback="f'@{username}, you now have {credit} song request credit(s).'")

def save_conf(request):

    global TWITCH_CLIENT_ID
    global TWITCH_SECRET
    global TARGET_CHANNEL
    global SPOTIFY_CLIENT_ID
    global SPOTIFY_SECRET
    global SPOTIFY_PLAYLIST_URL
    global SPOTIFY_PLAYLIST_URI
    global SPOTIFY_REQUEST_URI
    global GIFTED_REGEX
    global BITS_REGEX
    global TIP_REGEX
    global SIGNAL_BOT
    global TWITCH_REQUEST_URI
    global AMOUNT_BITS
    global AMOUNT_GIFTED_TIER1
    global AMOUNT_GIFTED_TIER2
    global AMOUNT_GIFTED_TIER3
    global AMOUNT_TIP
    global CLEAN_PLAYLIST
    global REQUEST_CMD
    global SONG_CMD
    global CREDIT_CMD
    global DISABLE_CREDIT_CMD
    global DISABLE_SONG_CMD
    global DISABLE_REQUEST_CMD
    global CUMULATIVE_CREDIT
    global CREDIT_MESSAGE
    global SONG_MESSAGE
    global NO_SONG_MESSAGE
    global REQUEST_MESSAGE
    global NOTIFY_MESSAGE

    if BOPBOT_WEB:
            inputs = request.args#[]
            #for x in request.args:
             #   inputs.append(html.escape(x).decode('utf-8'))

            TWITCH_CLIENT_ID = inputs[b'twitch_client_id'][0].decode('utf-8')
            TWITCH_SECRET = inputs[b'twitch_secret'][0].decode('utf-8')
            TARGET_CHANNEL = inputs[b'target_channel'][0].decode('utf-8')
            SPOTIFY_CLIENT_ID = inputs[b'spotify_client_id'][0].decode('utf-8')
            SPOTIFY_SECRET = inputs[b'spotify_secret'][0].decode('utf-8')
            SPOTIFY_PLAYLIST_URL = inputs[b'playlist_url'][0].decode('utf-8')
            SPOTIFY_REQUEST_URI = inputs[b'spotify_request_uri'][0].decode('utf-8')
            GIFTED_REGEX = inputs[b'gifted_regex'][0].decode('utf-8')
            BITS_REGEX = inputs[b'bits_regex'][0].decode('utf-8')
            TIP_REGEX = inputs[b'tip_regex'][0].decode('utf-8')
            SIGNAL_BOT = inputs[b'signal_bot'][0].decode('utf-8')
            TWITCH_REQUEST_URI = inputs[b'twitch_request_uri'][0].decode('utf-8')
            AMOUNT_BITS = inputs[b'amount_bits'][0].decode('utf-8')
            AMOUNT_GIFTED_TIER1 = inputs[b'amount_gifted_tier1'][0].decode('utf-8')
            AMOUNT_GIFTED_TIER2 = inputs[b'amount_gifted_tier2'][0].decode('utf-8')
            AMOUNT_GIFTED_TIER3 = inputs[b'amount_gifted_tier3'][0].decode('utf-8')
            AMOUNT_TIP = inputs[b'amount_tip'][0].decode('utf-8')
            REQUEST_CMD = inputs[b'request_cmd'][0].decode('utf-8')
            SONG_CMD = inputs[b'song_cmd'][0].decode('utf-8')
            CREDIT_CMD = inputs[b'credit_cmd'][0].decode('utf-8')

            if not b'clean_playlist' in inputs.keys():
                CLEAN_PLAYLIST = False
            else:
                CLEAN_PLAYLIST = True
            if not b'disable_credit_cmd' in inputs.keys():
                DISABLE_CREDIT_CMD = False
            else:
                DISABLE_CREDIT_CMD = True
            if not b'disable_song_cmd' in inputs.keys():
                DISABLE_SONG_CMD = False
            else:
                DISABLE_SONG_CMD = True
            if not b'disable_request_cmd' in inputs.keys():
                DISABLE_REQUEST_CMD = False
            else:
                DISABLE_REQUEST_CMD = True
            if not b'cumulative_credit' in inputs.keys():
                CUMULATIVE_CREDIT = False
            else:
                CUMULATIVE_CREDIT = True

            CREDIT_MESSAGE = inputs[b'credit_message'][0].decode('utf-8')
            SONG_MESSAGE = inputs[b'song_message'][0].decode('utf-8')
            NO_SONG_MESSAGE = inputs[b'no_song_message'][0].decode('utf-8')
            REQUEST_MESSAGE = inputs[b'request_message'][0].decode('utf-8')
            NOTIFY_MESSAGE = inputs[b'notify_message'][0].decode('utf-8')

    cfg.set('twitch', 'client_id', str(TWITCH_CLIENT_ID))
    cfg.set('twitch', 'secret_key', str(TWITCH_SECRET))
    cfg.set('twitch', 'channel', str(TARGET_CHANNEL))
    cfg.set('spotify', 'client_id', str(SPOTIFY_CLIENT_ID))
    cfg.set('spotify', 'secret_key', str(SPOTIFY_SECRET))
    cfg.set('spotify', 'playlist_url', str(SPOTIFY_PLAYLIST_URL))
    cfg.set('twitch', 'request_uri', str(SPOTIFY_REQUEST_URI))
    cfg.set('twitch', 'gifted_regex', str(GIFTED_REGEX))
    cfg.set('twitch', 'bits_regex', str(BITS_REGEX))
    cfg.set('twitch', 'tip_regex', str(TIP_REGEX))
    cfg.set('twitch', 'signal_bot', str(SIGNAL_BOT))
    cfg.set('twitch', 'request_uri', str(TWITCH_REQUEST_URI))
    cfg.set('cost', 'amount_bits', str(AMOUNT_BITS))
    cfg.set('cost', 'amount_gifted_tier1', str(AMOUNT_GIFTED_TIER1))
    cfg.set('cost', 'amount_gifted_tier2', str(AMOUNT_GIFTED_TIER2))
    cfg.set('cost', 'amount_gifted_tier3', str(AMOUNT_GIFTED_TIER3))
    cfg.set('cost', 'amount_tip', str(AMOUNT_TIP))
    cfg.set('bopbot', 'clean_playlist', str(CLEAN_PLAYLIST))
    cfg.set('bopbot', 'request_cmd', str(REQUEST_CMD))
    cfg.set('bopbot', 'song_cmd', str(SONG_CMD))
    cfg.set('bopbot', 'credit_cmd', str(CREDIT_CMD))
    cfg.set('bopbot', 'disable_credit_cmd', str(DISABLE_CREDIT_CMD))
    cfg.set('bopbot', 'disable_song_cmd', str(DISABLE_SONG_CMD))
    cfg.set('bopbot', 'disable_request_cmd', str(DISABLE_REQUEST_CMD))
    cfg.set('bopbot', 'cumulative_credit', str(CUMULATIVE_CREDIT))
    cfg.set('messages', 'credit_message', str(CREDIT_MESSAGE))
    cfg.set('messages', 'song_message', str(SONG_MESSAGE))
    cfg.set('messages', 'no_song_message', str(NO_SONG_MESSAGE))
    cfg.set('messages', 'request_message', str(REQUEST_MESSAGE))
    cfg.set('messages', 'notify_message', str(NOTIFY_MESSAGE))

    try:
        f = open('config.ini', 'w')
        cfg.write(f)
        f.close()
    except Exception as r:
        return fail('Error writing to "config.ini".', str(r))


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
        return fail('Error getting Spotify playlist.', str(r))

async def room_join(chn): 
    print('Joining channel:', chn)
    await ready_event.chat.join_room(chn)

#setup playlist when Twitch is ready and Spotify connection established
async def on_ready(ready_event: EventData):

    print(app_name, 'is ready.')
    print()
    help()

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
            await msg.chat.send_message(TARGET_CHANNEL, \
                env.fromg_string(NOTIFY_MESSAGE).render(username=username,credit=credit))

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

    await cmd.reply(env.from_string(CREDIT_MESSAGE).render(username=username,credit=credit))

#bot will reply with currently playing song
async def song_command(cmd: ChatCommand):

    if DISABLE_SONG_CMD: return

    tr = sp.currently_playing()

    username = cmd.user.name

    if tr == None:
        await cmd.reply(env.from_string(NO_SONG_MESSAGE).render(username=username))
        return

    name = tr['item']['name']
    artist = tr['item']['artists'][0]['name']

    await cmd.reply(env.from_string(SONG_MESSAGE).\
        render(username=username,name=name,artist=artist))

#bot will add song to playlist if tipper has credit
async def request_command(cmd: ChatCommand):

    if DISABLE_REQUEST_CMD: return

    if cmd.user.name.lower() in tippers.keys():
        if tippers[cmd.user.name.lower()] >= 1:

            tr = sp.currently_playing()

            if tr == None:
                print('Song cannot be added because there is no song from the playlist in the queue.')
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
                artist = track['artists'][0]['name']
                username = cmd.user.name

                await cmd.reply(env.from_string(REQUEST_MESSAGE).\
                    render(name=name,artist=artist,username=username))

                print(username, 'added', name, 'by', artist, 'to position', str(ci+1), 'in the playlist.')

            sp.playlist_add_items(SPOTIFY_PLAYLIST_URI, track_uris,ci)

def request_start():
    global DISABLE_REQUEST_CMD
    global DISABLE_CREDIT_CMD
    DISABLE_REQUEST_CMD = False
    DISABLE_CREDIT_CMD = cfg.getboolean('bopbot', 'disable_credit_cmd')
    print('Requests are enabled.')

def request_stop():
    global DISABLE_REQUEST_CMD
    global DISABLE_CREDIT_CMD
    DISABLE_REQUEST_CMD = True
    DISABLE_CREDIT_CMD = True
    print('Requests are disabled.')

async def authenticate():
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
        return fail('Error connecting to Spotify.', str(r))
    
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
                    return fail('Invalid playlist URL.')
    else:
        print()
        print('Using config playlist URL:', SPOTIFY_PLAYLIST_URL)
        r = re.match(rp,SPOTIFY_PLAYLIST_URL)
        if r:
            SPOTIFY_PLAYLIST_URI = r.groups()[0]
        else:
            return fail('Invalid playlist URL.')
    print()


    try:
        print('Authenticating with Twitch...')
        twitch_scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
        twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_SECRET)
        auth = UserAuthenticator(twitch, twitch_scope)

        token, refresh_token = await auth.authenticate()
        await twitch.set_user_authentication(token, twitch_scope, refresh_token)
    except Exception as r:
        return fail('Error connecting to Twitch.', str(r))


    try:
        chat = await Chat(twitch)
        chat.register_event(ChatEvent.READY, on_ready)
        chat.register_event(ChatEvent.MESSAGE, on_message)
        chat.register_command(REQUEST_CMD, request_command)
        chat.register_command(SONG_CMD, song_command)
        chat.register_command(CREDIT_CMD, credit_command)

        chat.start()
    except Exception as r:
        return fail('Error enterting chat and registering commands.', str(r))
    
    cache_playlist()

async def run_command(line):

    global tippers
    global playlist_tracks
    global quit

    line = line.split()
    cmd = line[0].encode('utf-8')

    #commands that can be used while there is an error
    if cmd == b'reset':
        print('Clearing tippers list...')
        tippers = {}
        
        clean_playlist()

        print('Clearing playlist cache...')
        playlist_tracks = []

        await run()
        
    if cmd == b'refresh':
        clean_playlist()
        print('Clearing playlist cache...')
        playlist_tracks = []

        cache_playlist()
    
    if cmd == b'quit' or cmd == b'exit' and not BOPBOT_WEB:
            quit = True
    
    #commands that cannot be used if there is an error
    if not error:

        if cmd == b'help' and not BOPBOT_WEB:
            if len(line) >= 2:
                help(line[1])
            else:
                help()

        if cmd == b'give':
            if len(line) >= 2:
                give(line[1])
            else:
                print('No <username> specified.')
        
        if cmd == b'tippers':
            pprint(tippers)
        
        if cmd == b'playlist':
            pprint(playlist_tracks)
        
        if cmd == b'start':
            request_start()
        
        if cmd == b'stop':
            request_stop()

    return b''

#set up twitch and spotify interface and main program loop
async def run():

    global tippers
    global playlist_tracks
    
    read_conf()

    print()
    print(
'''
 ██▄ ▄▀▄ █▀▄ ██▄ ▄▀▄ ▀█▀
 █▄█ ▀▄▀ █▀  █▄█ ▀▄▀  █ 
'''
)
    print()

    print(app_name, 'has started.')

    #await authenticate()
    #await room_join(TARGET_CHANNEL)

    if BOPBOT_WEB:
        site = server.Site(root)
        reactor.listenTCP(8080, site)
        reactor.startRunning(False)

    while not quit:

        if BOPBOT_WEB:
            reactor.iterate()
        else:
            line = input()
            if len(line.split()) >= 1:
                if error:
                    print('Error requires correction:', str(error))
                await run_command(line)

    print('Leaving Twitch...')
    chat.stop()
    await twitch.close()

    clean_playlist()

    print('Exiting...')

template = dict(
    header = dict(title=app_name),
    content = {},
    footer = {},
)

def show_content(tmp):

    header = env.get_template('header.html')
    content = env.get_template(tmp)
    footer = env.get_template('footer.html')

    data = header.render(**template['header'])
    data += content.render(**template['content'])
    data += footer.render(**template['footer'])

    return data.encode('utf-8')

def custom402(request):
    request.setHeader('Content-Type', 'text/html; charset=utf-8')
    request.setResponseCode(402)
    template['content']['message'] = markdown('#Not Authorized\n\nThe page requires authorization.')
    return show_content('message.html')

def needs_auth(session):
    if session.uid in auth_sessions:
        return False
    return True

class start(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        if needs_auth(request.getSession()): return custom402(request)
        request.setHeader('Content-Type', 'text/html; charset=utf-8')
        template['header']['title'] = app_name + ' - start'
        return show_content('start.html')

def configure_get(request):
    request.setHeader('Content-Type', 'text/html; charset=utf-8')
    template['header']['title']  = app_name + ' - configure'

    template['content']['BOPBOT_WEB'] = BOPBOT_WEB 
    template['content']['TWITCH_CLIENT_ID'] = TWITCH_CLIENT_ID
    template['content']['TWITCH_SECRET'] = TWITCH_SECRET
    template['content']['TARGET_CHANNEL'] = TARGET_CHANNEL
    template['content']['SPOTIFY_CLIENT_ID'] = SPOTIFY_CLIENT_ID
    template['content']['SPOTIFY_SECRET'] = SPOTIFY_SECRET
    template['content']['SPOTIFY_PLAYLIST_URL'] = SPOTIFY_PLAYLIST_URL
    template['content']['SPOTIFY_PLAYLIST_URI'] = SPOTIFY_PLAYLIST_URI
    template['content']['SPOTIFY_REQUEST_URI'] = SPOTIFY_REQUEST_URI
    template['content']['GIFTED_REGEX'] = GIFTED_REGEX
    template['content']['BITS_REGEX'] = BITS_REGEX
    template['content']['TIP_REGEX'] = TIP_REGEX
    template['content']['SIGNAL_BOT'] = SIGNAL_BOT
    template['content']['TWITCH_REQUEST_URI'] = TWITCH_REQUEST_URI
    template['content']['AMOUNT_BITS'] = AMOUNT_BITS
    template['content']['AMOUNT_GIFTED_TIER1'] = AMOUNT_GIFTED_TIER1
    template['content']['AMOUNT_GIFTED_TIER2'] = AMOUNT_GIFTED_TIER2
    template['content']['AMOUNT_GIFTED_TIER3'] = AMOUNT_GIFTED_TIER3
    template['content']['AMOUNT_TIP'] = AMOUNT_TIP
    template['content']['REQUEST_CMD'] = REQUEST_CMD
    template['content']['SONG_CMD'] = SONG_CMD
    template['content']['CREDIT_CMD'] = CREDIT_CMD

    template['content']['CLEAN_PLAYLIST'] = ''
    template['content']['DISABLE_CREDIT_CMD'] = ''
    template['content']['DISABLE_SONG_CMD'] = ''
    template['content']['DISABLE_REQUEST_CMD'] = ''
    template['content']['CUMULATIVE_CREDIT'] = ''

    ch = 'checked'
    if CLEAN_PLAYLIST:
        template['content']['CLEAN_PLAYLIST'] = ch
    if DISABLE_CREDIT_CMD:
        template['content']['DISABLE_CREDIT_CMD'] = ch
    if DISABLE_SONG_CMD:
        template['content']['DISABLE_SONG_CMD'] = ch
    if DISABLE_REQUEST_CMD:
        template['content']['DISABLE_REQUEST_CMD'] = ch
    if CUMULATIVE_CREDIT:
        template['content']['CUMULATIVE_CREDIT'] = ch

    template['content']['CREDIT_MESSAGE'] = CREDIT_MESSAGE
    template['content']['SONG_MESSAGE'] = SONG_MESSAGE
    template['content']['NO_SONG_MESSAGE'] = NO_SONG_MESSAGE
    template['content']['REQUEST_MESSAGE'] = REQUEST_MESSAGE
    template['content']['NOTIFY_MESSAGE'] = NOTIFY_MESSAGE

    return show_content('configure.html')

def configure_post(request):
    save_conf(request)

class configure(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        if needs_auth(request.getSession()): return custom402(request)
        return configure_get(request)

    def render_POST(self, request):
        if needs_auth(request.getSession()): return custom402(request)

        configure_post(request)

        return configure_get(request)
    
class login(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        request.setHeader('Content-Type', 'text/html; charset=utf-8')
        template['header']['title'] = app_name + ' - login'
        return show_content('login.html')
    def render_POST(self, request):
        
        username = request.args[b'username'][0].decode('utf-8')
        password = request.args[b'password'][0].decode('utf-8')

        username = html.escape(username)
        password = html.escape(password)

        salt = ''
        hashed_pass = ''
        passwd = json.loads(open('passwd.json').read())

        if username in passwd.keys():
            salt = passwd[username]['salt']
            hashed_pass = passwd[username]['pass'].encode('utf-8')
        else:
            return custom402(request)
        
        test = password + salt
        test_hash = bcrypt.hashpw(test.encode('utf-8'), salt.encode('utf-8'))

        if hashed_pass == test_hash:
            global auth_sessions
            if not request.getSession().uid in auth_sessions:
                auth_sessions.append(request.getSession().uid)
            return redirectTo(b'/app/start', request)

        return custom402(request)

class logout(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        if needs_auth(request.getSession()): return custom402(request)
        global auth_sessions
        if request.getSession().uid in auth_sessions:
            auth_sessions.remove(request.getSession().uid)
        request.getSession().expire()
        request.setHeader('Content-Type', 'text/html; charset=utf-8')
        template['header']['title'] = app_name + ' - logout'
        template['content']['message'] = 'You are now logged out.'
        return show_content('message.html')

class main(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        request.setHeader('Content-Type', 'text/html; charset=utf-8')
        template['header']['title'] = app_name
        template['content']['message'] = markdown(open('README.md').read(),\
                extensions=['extra','codehilite'], output_format='html5')
        return show_content('message.html')

class api(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        if needs_auth(request.getSession()): return custom402(request)
        request.setHeader('Content-Type', 'text/html; charset=utf-8')
        if b'cmd' in request.args:
            r = run_command(request.args[b'cmd'][0])
            return r
        else:
            return b''

class custom404(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        request.setHeader('Content-Type', 'text/html; charset=utf-8')
        request.setResponseCode(404)
        template['header']['title'] = app_name + ' - Not Found'
        template['content']['message'] = markdown('#Not Found\n\nThe page could not be found.')
        return show_content('message.html')

class _root(resource.Resource):
    def getChild(self, path, request):
        return custom404()

class _auth(resource.Resource):
    def getChild(self, path, request):
        return custom404()

root = _root()
root.putChild(b'', main())
root.putChild(b'static', static.File('./static'))
app = _root()
app.putChild(b'start', start())
app.putChild(b'configure', configure())
app.putChild(b'api', api())
root.putChild(b'app', app)
auth = _root()
auth.putChild(b'login', login())
auth.putChild(b'logout', logout())
root.putChild(b'auth', auth)


if __name__ == '__main__':
    asyncio.run(run())