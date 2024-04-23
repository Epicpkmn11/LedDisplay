#!/usr/bin/env python3

import json
import random
import requests
import time

from argparse import ArgumentParser
from datetime import datetime
from PIL import Image
from struct import unpack

HEADINGS = {"NB": "↑", "EB": "→", "SB": "↓", "WB": "←"}


class LedDisplay:
	def __init__(self, config, font):
		self.parseConfig(config)
		self.parseFont(font)

		if self.config["transit"]["enabled"]:
			self.busTracker = BusTracker(self)

		if self.config["weather"]["enabled"]:
			self.weather = Weather(self)

	def parseConfig(self, fileName):
		with open(fileName, "r") as f:
			self.config = json.load(f)

	def parseFont(self, fileName):
		file = open(fileName, "rb")
		file.seek(0, 2)
		fileSize = file.tell()
		file.seek(0)

		magic = file.read(4)
		if magic != b"RIFF":
			raise Exception("Failed to parse font (Not a RIFF)")

		size, = unpack("<I", file.read(4))
		if size + 8 != fileSize:
			raise Exception(f"Failed to parse font (Invalid size {size + 8} != {fileSize}")

		# Metadata
		magic = file.read(4)
		if magic != b"META":
			raise Exception("Failed to parse font (Missing META)")
		_, width, height, count = unpack("<LBBH", file.read(8))

		# Character data
		magic = file.read(4)
		if magic != b"CDAT":
			raise Exception("Failed to parse font (Missing CDAT)")

		# Read in character data, to parse in the next step
		sectionSize, = unpack("<L", file.read(4))
		cdatTemp = file.read(sectionSize)
		tiles = []

		# Character widths
		magic = file.read(4)
		if magic == b"CWTH":
			file.read(4)  # Skip size
			for i in range(count):
				tileWidth, = unpack("<B", file.read(1))

				tile = b"".join([bytes([1 if (line & (0x80 >> i)) else 0 for i in range(tileWidth)]) for line in cdatTemp[i * height:(i + 1) * height]])
				tiles.append(Image.frombytes("P", (tileWidth, height), tile))

			sectionSize = count
			padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
			file.read(padding)
		else:
			file.seek(-4, 1)
			widths = [width] * count

			# Parse tiles
			for i in range(count):
				tile = b"".join([bytes([1 if (line & (0x80 >> i)) else 0 for i in range(width)]) for line in cdatTemp[i * height:(i + 1) * height]])
				tiles.append(Image.frombytes("P", (width, height), tile))

		# Character map
		magic = file.read(4)
		file.read(4)  # Skip size
		if magic != b"CMAP":
			raise Exception("Failed to parse font (Missing CMAP)")

		output = {}
		for i in range(count):
			codepoint, = unpack("<H", file.read(2))
			output[chr(codepoint)] = tiles[i]

		sectionSize = count * 2
		padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
		file.read(padding)

		self.fontHeight = height
		self.font = output

	def getPalette(self, module):
		if module and "color" in self.config[module]:
			hexColor = self.config[module]["color"]
			return [0, 0, 0] + list(bytes.fromhex(hexColor[1:]))

		return [0, 0, 0, 255, 255, 255]  # Default to white

	def print(self, module, x, y, string):
		if module:
			ofs = self.config[module]["position"]
			x += ofs[0]
			y += ofs[1]
			pal = self.getPalette(module)

		for letter in string:
			# If letter missing, print '?'
			if letter not in self.font:
				letter = "?"

			bitmap = self.font[letter]
			bitmap.putpalette(pal)

			# If we're going off screen, return
			if x + bitmap.width > self.im.width or y + self.fontHeight > self.im.height:
				return

			self.im.paste(bitmap, (x, y))

			x += bitmap.width

	def renderClock(self):
		self.print("clock", 0, 0, time.strftime(self.config["clock"]["format"][int(time.time()) % 2]))

	def render(self, width, height):
		self.im = Image.new("RGB", (width, height))

		if self.config["transit"]["enabled"]:
			self.busTracker.update()
			self.busTracker.render()

		if self.config["weather"]["enabled"]:
			self.weather.update()
			self.weather.render()

		if self.config["clock"]["enabled"]:
			self.renderClock()

		return self.im


class BusTracker(object):
	def __init__(self, display):
		self.display = display
		self.departures = []
		self.lastUpdated = 0
		self.config = display.config["transit"]

	def fetchDeparture(self, stop, route=None):
		stopInfo = requests.get(f"{self.config['api']}/{stop}").json()
		for departure in stopInfo["departures"]:
			if not route or int(departure["route_id"]) == route:
				if departure["schedule_relationship"] == "Scheduled":
					return departure

	def update(self):
		if (time.time() - self.lastUpdated) < 30:
			return

		self.departures = []
		for stop in self.config["stops"]:
			if type(stop) is int:
				departure = self.fetchDeparture(stop)
			else:
				departure = self.fetchDeparture(*stop)

			if departure:
				self.departures.append(departure)

		self.lastUpdated = time.time()

	def render(self):
		if len(self.departures) > 0:
			for i, d in enumerate(self.departures):
				heading = HEADINGS[d["direction_text"]]
				busName = d["route_short_name"] + (d["terminal"] if "terminal" in d else "")
				if d["actual"]:
					departureTime = d["departure_text"].replace(" Min", "m")
				else:
					departureTime = datetime.fromtimestamp(d["departure_time"]).strftime(":%M")

				self.display.print("transit", 0, i * self.display.fontHeight, heading + busName)
				self.display.print("transit", 25, i * self.display.fontHeight, departureTime)
		else:
			sky = "".join(random.sample(["\2", "\3"], counts=[3, 3], k=6)) + "\1" + "".join(random.sample(["\2", "\3"], counts=[2, 2], k=4))
			self.display.print("transit", 0, 0, sky)
			self.display.print("transit", 0, 1 * self.display.fontHeight, "Busses are done")
			self.display.print("transit", 0, 2 * self.display.fontHeight, "for the night...")


class Weather(object):
	def __init__(self, display):
		self.display = display
		self.data = []
		self.nextUpdate = 0
		self.config = display.config["weather"]

	def cToF(self, celsius):
		return celsius * 9 / 5 + 32

	def update(self):
		if (time.time() - self.nextUpdate) < 0:
			return

		req = requests.get(f"https://api.weather.gov/stations/{self.config['station']}/observations/latest")
		self.data = req.json()["properties"]

		self.nextUpdate = datetime.strptime(req.headers["Expires"], "%a, %d %b %Y %H:%M:%S %Z").timestamp()

	def render(self):
		self.display.print("weather", 0, 0, f"{self.cToF(self.data['temperature']['value']):.0f}°F")


def main():
	"Prototyping for Pi LED display"

	parser = ArgumentParser(description=main.__doc__)
	parser.add_argument("config", type=str, help="config file")
	parser.add_argument("font", type=str, help="FRF font (proportional supported)")
	parser.add_argument("output", type=str, help="image to output")
	parser.add_argument("width", type=int, help="character width")
	parser.add_argument("height", type=int, help="character height")
	args = parser.parse_args()

	display = LedDisplay(args.config, args.font)

	while True:
		im = display.render(args.width, args.height)
		im.save(args.output)
		time.sleep(1)


if __name__ == "__main__":
	main()
