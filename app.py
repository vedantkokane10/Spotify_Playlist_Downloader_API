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
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI')

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
@app.route('/stream_audio/<video_id>')
def stream_audio(video_id):
    url = f'http://www.youtube.com/watch?v={video_id}'
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
    }
    def generate():
        try:
            with YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=True)
                audio_url = result['url']
                with requests.get(audio_url, stream=True) as r:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:
                            yield chunk
        except Exception as e:
            yield str(e)

    return Response(generate(), content_type='audio/mpeg')

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
            if 'entries' not in info_dict or not info_dict['entries']:
                return {'error': 'No results found'}

            video_id = info_dict['entries'][0]['id']
            return {'status': 'success', 'video_id': video_id}
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    app.run(debug=True)
