# -*- coding: utf-8 -*-

import datetime
import requests
import sys
import re

from flask import Flask, render_template, request
from pymongo import MongoClient
from beebotte import *
from time import sleep

import config

app = Flask(__name__)
mongo = MongoClient()

bclient = BBT(config.beebotte_apikey, config.beebotte_secret)

'''
clicks_regex = re.compile('<div class="clics"><span>(\d+)<br\/>', re.UNICODE)
meneos_regex = re.compile('<a id="a-votes-\d+" href=".*?">(\d+)<\/a>', re.UNICODE)
titulo_regex = re.compile('<h2> <a href="https:\/\/www.meneame.net\/story\/.*?" class=".*?">(.*?)</a>', re.UNICODE)
'''

clicks_regex = re.compile('<meneame:clicks>(\d+)</meneame:clicks>')
meneos_regex = re.compile('<meneame:karma>(\d+)</meneame:karma>')
titulo_regex = re.compile('<title>(.*?)<\/title', flags=re.UNICODE + re.MULTILINE)

def get_meneo():
	retries = 0
	while True:
		try:
			html = requests.get(config.random_url, headers={"User-Agent": "Mozilla"}).text
			break
		except:
			retries += 1
			print 'Request to meneame failed, retrying (%s)' % retries

	clicks = clicks_regex.search(html)
	meneos = meneos_regex.search(html)
	titulo = titulo_regex.findall(html)
	

	return {
		'clicks': int(clicks.group(1)),
		'meneos': int(meneos.group(1)),
		'titulo': titulo[3]
	}

def save_meneo(meneo):
	timestamp = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
	
	data = {
		'timestamp': timestamp,
	}
	data.update(meneo)

	save_to_local(data)
	save_to_remote(data)

def save_to_local(data):
	db = mongo.p1_meneame
	db.meneos.insert_one(data)

def save_to_remote(data):
	bclient.writeBulk(config.beebotte_channel, [
		{'resource': 'clicks', 'data': data['clicks']},
		{'resource': 'meneos', 'data': data['meneos']},
		{'resource': 'titulo', 'data': data['titulo']},
		{'resource': 'timestamp', 'data': data['timestamp']}
	])

def average_get_last_used():
	db = mongo.p1_numbers
	config_col = db.config

	d_config = config_col.find_one()
	if d_config is None:
		config_col.insert({
			"last_backend": config.BACKEND_LOCAL
			})
		return config.BACKEND_LOCAL
	else:
		return d_config['last_backend']

def average_set_last_used(backend):
	db = mongo.p1_numbers
	config_col = db.config

	config_col.update({}, {
			"last_backend": backend
		})

def get_local_average():
	db = mongo.p1_meneame
	meneos = db.meneos

	all_numbers = list(meneos.find())
	n_numbers = len(all_numbers)
	acc = 0

	if n_numbers == 0:
		return 0

	for n in all_numbers:
		acc += n['clicks']

	return acc / n_numbers

def get_remote_average():
	all_numbers = bclient.read(config.beebotte_channel, "clicks", limit=8888)
	acc = 0
	n_numbers = len(all_numbers)

	if n_numbers == 0:
		return 0

	for n in all_numbers:
		acc += n['data']

	return acc / n_numbers

def find_meneos_over_threshold(threshold, limit=None):
	db = mongo.p1_meneame
	meneos = db.meneos

	meneos_history = meneos.find({
			"clicks": {
				"$gte": threshold
			}
		}
	)

	if limit is not None:
		meneos_history = meneos_history.limit(limit)

	return list(meneos_history)

def get_average():
	backend = average_get_last_used()
	
	if backend == config.BACKEND_LOCAL:
		average = get_remote_average()
		next_backend = config.BACKEND_REMOTE
	else:
		average = get_local_average()
		next_backend = config.BACKEND_LOCAL

	average_set_last_used(next_backend)

	return {
		"source": {
			config.BACKEND_REMOTE: "remote",
			config.BACKEND_LOCAL: "local"
		}.get(backend),
		"average": average
	}

@app.route("/", methods=["GET"])
@app.route("/threshold", methods=["POST"])
def http_main(threshold=None):
	meneo = get_meneo()
	save_meneo(meneo)

	if 'threshold' in request.form:
		try:
			threshold = int(request.form['threshold'])
			limit = 10

		except Exception as e:
			meneos = []
			error = 'Invalid format'
			print error, e
	else:
		threshold = 0
		limit = None

	meneos = find_meneos_over_threshold(threshold, limit=limit)
	average = get_average()

	return render_template("index.html", meneos=meneos, average=average)

def meneo_daemon():
	while True:
		meneo = get_meneo()
		save_meneo(meneo)
		print '%s: %s' % ((datetime.datetime.now()), meneo)
		sleep(120)

if __name__ == '__main__':
	if len(sys.argv) >= 2 and sys.argv[1] == "--daemon":
		meneo_daemon()
	else:
		app.run(debug=True, host='0.0.0.0')	