#!/usr/bin/env python3

import colorsys
import json
import random
import requests
import time

from argparse import ArgumentParser
from datetime import datetime
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from struct import unpack
from threading import Thread

HEADINGS = {"NB": "↑", "EB": "→", "SB": "↓", "WB": "←"}


class LedDisplay:
	def __init__(self, config, font):
		self.parseConfig(config)
		self.hue = 0.0
		self.palette = graphics.Color(255, 255, 255)

		options = RGBMatrixOptions()
		options.cols = 64
		options.hardware_mapping = "adafruit-hat"  #-pwm

		self.matrix = RGBMatrix(options=options)
		self.canvas = self.matrix.CreateFrameCanvas()
		self.font = graphics.Font()
		self.font.LoadFont(font)

		self.matrix.brightness = 70

		if self.config["transit"]["enabled"]:
			self.busTracker = BusTracker(self)

		if self.config["weather"]["enabled"]:
			self.weather = Weather(self)

	def parseConfig(self, fileName):
		with open(fileName, "r") as f:
			self.config = json.load(f)

	def getPalette(self, module):
		if module and "color" in self.config[module]:
			hexColor = self.config[module]["color"]
			return graphics.Color(*list(bytes.fromhex(hexColor[1:])))

		return graphics.Color(255, 255, 255)  # Default to white

	def print(self, module, x, y, string):
		if module:
			ofs = self.config[module]["position"]
			x += ofs[0]
			y += ofs[1]
		
		pal = self.getPalette(module)

		graphics.DrawText(self.canvas, self.font, x, y + self.font.height - 1, pal, string)

	def renderClock(self):
		t=time.time()
		blink = t - int(t) > 0.5
		self.print("clock", 0, 0, time.strftime(self.config["clock"]["format"][blink]))

	def render(self, width, height):
		self.canvas.Clear()

#		# rainbow
#		self.hue += 0.005
#		if self.hue > 1.0:
#			self.hue -= 1.0
#		self.palette = graphics.Color(*[int(round(x * 255)) for x in colorsys.hsv_to_rgb(self.hue, 1.0, 1.0)])

		if self.config["transit"]["enabled"]:
			if not self.busTracker.hasBusses():
				self.matrix.brightness = 40

			self.busTracker.render()

			self.matrix.brightness = 70

		if self.config["weather"]["enabled"]:
			self.weather.render()

		if self.config["clock"]["enabled"]:
			self.renderClock()

		self.canvas = self.matrix.SwapOnVSync(self.canvas)

	def update(self):
		if self.config["transit"]["enabled"]:
			self.busTracker.update()

		if self.config["weather"]["enabled"]:
			self.weather.update()

class BusTracker(object):
	def __init__(self, display):
		self.display = display
		self.departures = []
		self.lastUpdated = 0
		self.config = display.config["transit"]
		self.skydelay = 0

	def fetchDeparture(self, stop, route=None):
		stopInfo = requests.get(f"{self.config['api']}/{stop}").json()
		for departure in stopInfo["departures"]:
			if not route or int(departure["route_id"]) == route:
				if departure["schedule_relationship"] == "Scheduled":
					return departure

	def update(self):
		if (time.time() - self.lastUpdated) < 30:
			return

		print("[b] update")

		departures = []
		for stop in self.config["stops"]:
			if type(stop) is int:
				departure = self.fetchDeparture(stop)
			else:
				departure = self.fetchDeparture(*stop)

			if departure:
				departures.append(departure)

		self.lastUpdated = time.time()
		self.departures = departures

	def stars(self, count):
		return "".join(random.sample(["★", "☆"], counts=[count, count], k=count * 2))

	def sky(self):
		if self.skydelay == 0:
			self.skycache = self.stars(3) + "☽" + self.stars(2)
			self.skydelay = 10
		self.skydelay -= 1

		return self.skycache

	def render(self):
		if len(self.departures) > 0:
			for i, d in enumerate(self.departures):
				heading = HEADINGS[d["direction_text"]]
				busName = d["route_short_name"] + (d["terminal"] if "terminal" in d else "")
				if d["actual"]:
					departureTime = d["departure_text"].replace(" Min", "m")
				else:
					departureTime = datetime.fromtimestamp(d["departure_time"]).strftime(":%M")

				self.display.print("transit", 0, i * self.display.font.height, heading + busName)
				self.display.print("transit", 25, i * self.display.font.height, departureTime)
		else:
			self.display.print("transit", 0, 0, self.sky())
			self.display.print("transit", 0, self.display.font.height, "Busses are done")
			self.display.print("transit", 0, 2 * self.display.font.height, "for the night...")

	def hasBusses(self):
		return len(self.departures) > 0


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
		
		print("[w] update")

		req = requests.get(f"https://api.weather.gov/stations/{self.config['station']}/observations/latest")
		self.data = req.json()["properties"]

		# self.nextUpdate = datetime.strptime(req.headers["Expires"], "%a, %d %b %Y %H:%M:%S %Z").timestamp()
		self.nextUpdate = time.time() + 3600

	def render(self):
		if self.data == []:
			self.display.print("weather", 0, 0, "wait")
			return

		self.display.print("weather", 0, 0, f"{self.cToF(self.data['temperature']['value']):.0f}°F")


def main():
	"Prototyping for Pi LED display"

	parser = ArgumentParser(description=main.__doc__)
	parser.add_argument("config", type=str, help="config file")
	parser.add_argument("font", type=str, help="FRF font (proportional supported)")
	parser.add_argument("width", type=int, help="character width")
	parser.add_argument("height", type=int, help="character height")
	args = parser.parse_args()

	display = LedDisplay(args.config, args.font)

	update = Thread(target=display.update)
	update.start()

	while True:
		display.render(args.width, args.height)
		if not update.is_alive():
			update = Thread(target=display.update)
			update.start()

		time.sleep(0.2)


if __name__ == "__main__":
	main()
