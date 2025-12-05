# nuit_info_scraper_clean.py
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import threading
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from urllib.parse import urljoin

class NuitInfoScraper:
    def __init__(self):
        self.base_url = "https://www.nuitdelinfo.com"
        self.session = requests.Session()
        self.teams_data = {}
        self.challenges_data = {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def fetch_challenges_list(self):
        try:
            url = f"{self.base_url}/inscription/defis/liste"
            resp = self.session.get(url, headers=self.headers, timeout=30)
            if resp.status_code != 200:
                print(f"Error fetching challenges: HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.content, 'html.parser')
            challenges = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/inscription/defis/' in href and href.split('/')[-1].isdigit():
                    challenge_id = href.split('/')[-1]
                    name = a.get_text(strip=True)
                    if name in ['', 'Voir', 'Détails', 'Voir plus']:
                        continue
                    challenges.append({'id': challenge_id, 'name': name, 'url': urljoin(self.base_url, href)})
            unique = {c['id']: c for c in challenges}
            return list(unique.values())
        except Exception as e:
            print("Error fetching challenges list:", e)
            return []

    def fetch_teams_for_challenge(self, challenge_id, challenge_name):
        try:
            url = f"{self.base_url}/inscription/defis/{challenge_id}"
            resp = self.session.get(url, headers=self.headers, timeout=30)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.content, 'html.parser')
            teams = set()
            container = soup.find('div', class_='list-group col-md-4 col-md-offset-4 text-center')
            if container:
                for item in container.find_all('a', class_='list-group-item'):
                    name = item.get_text(strip=True)
                    if self.is_valid_team_name(name):
                        teams.add(name)
            return [{'name': t, 'challenge_id': challenge_id, 'challenge_name': challenge_name} for t in teams]
        except Exception as e:
            print(f"Error fetching teams for challenge {challenge_id}: {e}")
            return []

    def is_valid_team_name(self, name):
        if not name or len(name) < 2 or len(name) > 50:
            return False
        name_lower = name.lower()
        junk_keywords = [
            'document', 'discord', 'conditions', 'inscription',
            'voir', 'détails', 'plus', 'page', 'défi', 'challenge', 'supprimer', 'modifier'
        ]
        if any(word in name_lower for word in junk_keywords):
            return False
        if not name[0].isupper():
            return False
        return True

    def fetch_all_data(self):
        print("Fetching all data...")
        challenges = self.fetch_challenges_list()
        self.challenges_data = {c['id']: c for c in challenges}
        all_teams = {}
        for challenge in challenges:
            teams = self.fetch_teams_for_challenge(challenge['id'], challenge['name'])
            for team in teams:
                name = team['name']
                if name not in all_teams:
                    all_teams[name] = {
                        'projects': [],
                        'total_projects': 0,
                        'completed_projects': 0,
                        'progress': 0,
                        'last_updated': datetime.now().isoformat()
                    }
                if not any(p['challenge_id'] == team['challenge_id'] for p in all_teams[name]['projects']):
                    all_teams[name]['projects'].append({
                        'name': team['challenge_name'],
                        'challenge_id': team['challenge_id'],
                        'completed': False
                    })
        for team_name, data in all_teams.items():
            data['total_projects'] = len(data['projects'])
            data['progress'] = 0
        self.teams_data = all_teams
        self.save_to_json()
        print(f"Completed fetching. Total teams: {len(all_teams)}")
        return all_teams

    def save_to_json(self):
        data = {
            'teams': self.teams_data,
            'challenges': self.challenges_data,
            'last_updated': datetime.now().isoformat()
        }
        with open('teams_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_json(self):
        if os.path.exists('teams_data.json'):
            with open('teams_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.teams_data = data.get('teams', {})
                self.challenges_data = data.get('challenges', {})

    def get_leaderboard(self):
        return dict(sorted(self.teams_data.items(), key=lambda x: x[1]['total_projects'], reverse=True))


# ---------------- Flask Setup ----------------
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)  # Enable CORS for all routes

scraper = NuitInfoScraper()
scraper.load_from_json()

# Serve static HTML/CSS/JS files
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# API routes
@app.route('/api/teams')
def api_teams():
    return jsonify({'teams': scraper.teams_data, 'challenges': scraper.challenges_data})

@app.route('/api/refresh')
def api_refresh():
    def scrape_bg():
        scraper.fetch_all_data()
    threading.Thread(target=scrape_bg, daemon=True).start()
    return jsonify({"status": "success", "message": "Scraping started in background."})

@app.route('/api/leaderboard')
def api_leaderboard():
    return jsonify(scraper.get_leaderboard())


if __name__ == "__main__":
    threading.Thread(target=scraper.fetch_all_data, daemon=True).start()
    app.run(debug=False, port=5000, use_reloader=False)
