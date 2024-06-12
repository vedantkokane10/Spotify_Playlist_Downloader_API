import datetime
from flask import Flask, redirect, request, jsonify, session, Response , url_for
import requests
import urllib.parse
from yt_dlp import YoutubeDL
from flask_cors import CORS
import re
import os
from dotenv import load_dotenv
load_dotenv()

# Flask App setup
app = Flask(__name__) 
app.secret_key = '53d355f8-571a-4590-a310-1f9579440851'
CORS(app)  # CORS - cross-origin requests/Resource Sharing (allows your API to be accessed from different domains).

# Spotify API Credentials
SPOTIFY_CLIENT_ID = '42227dfaa2ae4abd836d04442c718c9d'
SPOTIFY_CLIENT_SECRET = '767f523ab80f4b1788c56c9b0226cc06'
SPOTIPY_REDIRECT_URI = 'https://spotify-playlist-downloader-api-3.onrender.com/callback'

# URLS fo the Spotify API
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_BASE_URL = 'https://api.spotify.com/v1/'


@app.route('/')
def index():
    return redirect('login')

# login to user's Spotify account 
@app.route('/login')
def login():
    scope = 'user-read-private user-read-email playlist-read-private'
    params = {
        'client_id': SPOTIFY_CLIENT_ID,
        'response_type': 'code',
        'scope': scope,
        'redirect_uri': SPOTIPY_REDIRECT_URI,
        'show_dialog': True
    }
    auth_url = f'{AUTH_URL}?{urllib.parse.urlencode(params)}'
    return redirect(auth_url)

# to get the data from Spotify and store it as a session
@app.route('/callback')
def callback():
    if 'error' in request.args:
        return jsonify({'error': request.args['error']})

    if 'code' in request.args:
        requestBody = {
            'code': request.args['code'],
            'grant_type': 'authorization_code',
            'redirect_uri': SPOTIPY_REDIRECT_URI,
            'client_id': SPOTIFY_CLIENT_ID,
            'client_secret': SPOTIFY_CLIENT_SECRET
        }
        response = requests.post(TOKEN_URL, data=requestBody)
        tokenInfo = response.json()

        if response.status_code != 200:
            return jsonify({'error': 'Failed to get token', 'details': tokenInfo})

        if 'access_token' in tokenInfo:
            session["access_token"] = tokenInfo['access_token']
            session["expires_at"] = datetime.datetime.now().timestamp() + tokenInfo['expires_in']
            return redirect('/playlist')
        else:
            return jsonify({'error': 'No access token found', 'details': tokenInfo})


# to retrieve the access token and fetch user playlists using Spotipy, and returns them as a JSON response.
@app.route('/playlist')
def playlists():
    if 'access_token' not in session:
        return redirect('/login')

    if datetime.datetime.now().timestamp() > session['expires_at']:
        return redirect('/login')

    headers = {
        'Authorization': f"Bearer {session['access_token']}"
    }
    response = requests.get(API_BASE_URL + 'me/playlists', headers=headers)
    playlists = response.json()

    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch playlists', 'details': playlists})

    playlistsInfo = playlists['items']
    playlistsID = {}
    for playlist in playlistsInfo:
        playlistsID[playlist['name']] = playlist['id']
    return jsonify(playlistsID)


# to retrieve the access token and fetch tracks for the given playlist ID using Spotipy, and returns them as a JSON response.
@app.route('/playlist/<playlist_id>')
def get_playlist_tracks(playlist_id):
    if 'access_token' not in session:
        return redirect('/login')

    if datetime.datetime.now().timestamp() > session['expires_at']:
        return redirect('/login')

    headers = {
        'Authorization': f"Bearer {session['access_token']}"
    }
    response = requests.get(API_BASE_URL + f'playlists/{playlist_id}/tracks', headers=headers)
    tracks = response.json()

    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch tracks', 'details': tracks})

    tracksInfo = tracks['items']
    trackData = {}
    for item in tracksInfo:
        track = item.get('track', {})
        track_name = track.get('name', 'Unknown Track')
        artists = track.get('artists', [])
        if artists:
            artist_name = artists[0].get('name', 'Unknown Artist')
        else:
            artist_name = 'Unknown Artist'
        trackData[track_name] = artist_name

    download_links = []
    for track_name, artist_name in trackData.items():
        download_result = get_video_url(track_name, artist_name)
        if 'status' in download_result and download_result['status'] == 'success':
            file_url = url_for('stream_audio', video_id=download_result['video_id'], _external=True)
            download_links.append({'track': track_name, 'artist': artist_name, 'download_url': file_url})
        else:
            download_links.append({'track': track_name, 'artist': artist_name, 'error': download_result['error']})

    return jsonify(download_links)





# a window where the user can download or stream audio file
# a window where the user can download or stream audio file
@app.route('/stream_audio/<video_id>')
def stream_audio(video_id):
    url = f'http://www.youtube.com/watch?v={video_id}'
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'extract_audio': True,
        'audioformat': 'mp3',
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            mp3_url = info_dict['url']
            return redirect(mp3_url)  # Redirect to the direct MP3 download URL
    except Exception as e:
        return jsonify({'error': str(e)})


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

# to get the video URL for the given song name and artist name using Youtube-DL, and returns it as a JSON response.
def get_video_url(song_name, artist_name):
    song_name = sanitize_filename(song_name)
    artist_name = sanitize_filename(artist_name)
    query = f'{song_name} {artist_name} audio lyrics'

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(f"ytsearch:{query}", download=False)
            print(info_dict['entries'][0]['id'])
            if 'entries' not in info_dict or not info_dict['entries']:
                return {'error': 'No results found'}
            video_id = info_dict['entries'][0]['id']
            return {'status': 'success', 'video_id': video_id}
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    app.run(debug=True)


