from flask import Flask, redirect
from flask import render_template
from flask import request, url_for, session

import time
import random
from decimal import Decimal

from models import dynamo

app = Flask(__name__)

app.secret_key = 'Is this some random string?'

# TODO:
# 1. Voting system
# 2. Calculate adjusted KDA
# 3. Add password for log in
# 4. Store match result (requires KDA calculation)
# 5. Leaderboard: Needs to store each match result

# Long term features:
# Connect with Riot backend so you can get the match result after it's done. This also
# allow other analysis after a user's match history.

# Maybe:
# 1. Allow user to select team1 or team2


@app.route('/')
def home():
    return render_template('home.html', username=session.get('username'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', warn=False)
    session['username'] = request.form['username']
    return redirect(url_for('home'))


@app.route('/logout', methods=['GET'])
def logout():
    if 'username' in session:
        session.pop('username')
    return redirect(url_for('home'))


@app.route('/join_game', methods=['POST', 'GET'])
def join_game():
    if request.method == 'GET':
        return render_template('join.html', username=session.get('username'))
    if request.method == 'POST':
        game_id = request.form['game_id']
        item = dynamo.tables['actor_game'].get_item(Key={'game_id': game_id})
        if 'Item' not in item:
            return render_template('join.html', not_found=True, username=session.get('username'))
        else:
            item = item['Item']
            if item['game_state'] == 'waiting':
                if session['username'] not in [_[0] for _ in item['player_list']]:
                    item['player_list'].append((session['username'], 'Random'))
                    dynamo.tables['actor_game'].put_item(Item=item)
                return redirect(f'games/{game_id}')
            else:
                if session['username'] not in [_[0] for _ in item['player_list']]:
                    return render_template('join.html', not_found=True, username=session.get('username'))
                return redirect(f'games/{game_id}')


@app.route('/create_game', methods=['GET'])
def create_game():
    game_id = ''.join(str(random.randint(0, 9)) for _ in range(6))  # Generate 6 digit id

    # If ID exists, keep randomly generating game_ids
    while 'Item' in dynamo.tables['actor_game'].get_item(Key={'game_id': game_id}):
        game_id = ''.join(str(random.randint(0, 9)) for _ in range(6))

    item = {
        'game_id': game_id,
        'creation_time': Decimal(time.time()),
        # 'player_list': [('Starry', 'Random'), ('MQ0', 'Random'), ('Kiwi', 'Random')], # Uncomment for testing
        'player_list': [],
        'team1': [],
        'team2': [],
        'game_state': 'waiting',
        'team1_actor_idx': 0,
        'team2_actor_idx': 0,
        'winning_team': 'team1',
    }
    item['player_list'].append((session['username'], 'Random'))
    dynamo.tables['actor_game'].put_item(Item=item)
    return redirect(f'games/{game_id}')


@app.route('/games/<game_id>', methods=['GET'])
def games(game_id):
    if 'username' not in session:
        return render_template('login.html', warn=True, username=session.get('username'))
    item = dynamo.tables['actor_game'].get_item(Key={'game_id': game_id})['Item']
    game_state = item['game_state']
    player_list = item['player_list']
    dynamo.tables['actor_game'].put_item(Item=item)

    # Check which team the logged in user belongs to
    team_belonging = None
    if session['username'] in item['team1']:
        team_belonging = 'team1'
    if session['username'] in item['team2']:
        team_belonging = 'team2'

    # Check if the user is an actor
    if (session['username'] in item['team1'] and item['team1'][int(item['team1_actor_idx'])] == session['username']) or \
            (session['username'] in item['team2'] and item['team2'][int(item['team2_actor_idx'])] == session['username']):
        role = 'actor'
    else:
        role = 'non-actor'

    return render_template('game.html', game_id=game_id, state=game_state, players=player_list,
                           team1=item['team1'],
                           team2=item['team2'],
                           role=role,
                           team_belonging=team_belonging,
                           winning_team=item['winning_team'],
                           team1_actor_idx=int(item['team1_actor_idx']),
                           team2_actor_idx=int(item['team2_actor_idx']),
                           username=session.get('username'))


@app.route('/games/<game_id>/start', methods=['GET', 'POST'])
def start_game(game_id):
    item = dynamo.tables['actor_game'].get_item(Key={'game_id': game_id})['Item']
    if request.method == 'POST' and item['game_state'] == 'waiting' and len(item['player_list']) > 1:
        item['game_state'] = 'started'
        player_list = item['player_list'].copy()
        random.shuffle(player_list)
        for i in range(len(player_list) // 2):
            item['team1'].append(player_list.pop()[0])
        item['team2'] = [_[0] for _ in player_list]
        item['team1_actor_idx'] = random.randint(0, len(item['team1']) - 1)
        item['team2_actor_idx'] = random.randint(0, len(item['team2']) - 1)
        dynamo.tables['actor_game'].put_item(Item=item)
    return redirect(f'/games/{game_id}')


@app.route('/games/<game_id>/start_vote', methods=['GET', 'POST'])
def start_vote(game_id):
    item = dynamo.tables['actor_game'].get_item(Key={'game_id': game_id})['Item']
    if request.method == 'POST' and item['game_state'] == 'started':
        item['game_state'] = 'voting'
        item['winning_team'] = request.form['won']
        if item['winning_team'] == 'team1':
            item['votes'] = [None for _ in range(len(item['team2']))]
        else:
            item['votes'] = [None for _ in range(len(item['team1']))]
    dynamo.tables['actor_game'].put_item(Item=item)
    return redirect(f'/games/{game_id}')


@app.route('/games/<game_id>/end_game', methods=['GET', 'POST'])
def end_game(game_id):
    item = dynamo.tables['actor_game'].get_item(Key={'game_id': game_id})['Item']
    if request.method == 'POST' and item['game_state'] == 'started':
        item['game_state'] = 'ended'
        dynamo.tables['actor_game'].put_item(Item=item)
    return redirect(f'/games/{game_id}')


if __name__ == '__main__':
    app.run()
