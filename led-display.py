#!/usr/bin/env python3

import colorsys
import json
import random
import requests
import time

from argparse import ArgumentParser
from datetime import datetime
from PIL import Image
from struct import unpack
from threading import Thread

HEADINGS = {"NB": "↑", "EB": "→", "SB": "↓", "WB": "←"}
HUE_OFFSET = {"transit": 0.2, "clock": 0, "weather": 0.1}
TEST_MODE = False

class FrfFont:
	def __init__(self, bmp, height):
		self.bmp = bmp
		self.height = height

class LedDisplay:
	def __init__(self, config, font):
		self.parseConfig(config)
		self.hue = 0.0
		self.drawCall = 0
		self.rainbow = True

		print(TEST_MODE)
		if TEST_MODE:
			self.font = self.parseFont(font)
		else:
			options = RGBMatrixOptions()
			options.cols = 64
			options.hardware_mapping = "adafruit-hat-pwm"

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
		file.read(4)  # Skip size
		if magic != b"CDAT":
			raise Exception("Failed to parse font (Missing CDAT)")

		tiles = []
		for _ in range(count):
			tiles.append(file.read(height))

		sectionSize = count * height
		padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
		file.read(padding)

		# Character widths
		magic = file.read(4)
		widths = []
		if magic == b"CWTH":
			file.read(4)  # Skip size
			for _ in range(count):
				widths.append(unpack("<B", file.read(1))[0])

			sectionSize = count
			padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
			file.read(padding)
		else:
			file.seek(-4, 1)
			widths = [width] * count

		# Character map
		magic = file.read(4)
		file.read(4)  # Skip size
		if magic != b"CMAP":
			raise Exception("Failed to parse font (Missing CMAP)")

		output = {}
		for i in range(count):
			codepoint, = unpack("<H", file.read(2))
			output[chr(codepoint)] = {
				"bitmap": tiles[i],
				"width": widths[i]
			}

		sectionSize = count * 2
		padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
		file.read(padding)

		return FrfFont(output, height)

	def getPalette(self, module):
		if self.rainbow:
			self.drawCall += 1
			hue = (self.hue - self.drawCall * 0.05) % 1.0
			if TEST_MODE:
				return tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(hue, 1.0, 1.0))
			else:
				return graphics.Color(*(int(round(x * 255)) for x in colorsys.hsv_to_rgb(hue, 1.0, 1.0)))

		hexColor = "#FFFFFF"  # default to white
		if module and "color" in self.config[module]:
			hexColor = self.config[module]["color"]

		return graphics.Color(*list(bytes.fromhex(hexColor[1:])))

	def print(self, module, x, y, string):
		if module:
			ofs = self.config[module]["position"]
			x += ofs[0]
			y += ofs[1]
		
		pal = self.getPalette(module)

		if TEST_MODE:
			for letter in string:
				# If letter missing, print '?'
				if letter not in self.font.bmp:
					letter = "?"

				width = self.font.bmp[letter]["width"]
				bitmap = self.font.bmp[letter]["bitmap"]

				# If we're going off screen, return
				if x + width > self.im.width or y + self.font.height > self.im.height:
					return

				for dy in range(self.font.height):
					for dx in range(width):
						if bitmap[dy] & (0x80 >> dx):
							self.im.putpixel((x + dx, y + dy), pal)

				x += width
		else:
			graphics.DrawText(self.canvas, self.font, x, y + self.font.height - 1, pal, string)


	def renderClock(self):
		t=time.time()
		blink = t - int(t) > 0.5
		self.print("clock", 0, 0, time.strftime(self.config["clock"]["date_format"]))
		self.print("clock", 0, self.font.height, time.strftime(self.config["clock"]["time_format"][blink]))

	def render(self, width, height):
		if TEST_MODE:
			self.im = Image.new("RGB", (width, height))
		else:
			self.canvas.Clear()

		if self.rainbow:
			self.hue = (self.hue + 0.01) % 1.0
			self.drawCall = 0

		if self.config["transit"]["enabled"]:
			if not self.busTracker.hasBusses() and not TEST_MODE:
				self.matrix.brightness = 40

			self.busTracker.render()

			if not TEST_MODE:
				self.matrix.brightness = 70

		if self.config["weather"]["enabled"]:
			self.weather.render()

		if self.config["clock"]["enabled"]:
			self.renderClock()

		if TEST_MODE:
			self.im.save("out.png")
		else:
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
		self.error = None

	def fetchDepartures(self, stop, route=None):
		print(f"[b] fetch {stop}")
		stopInfo = requests.get(f"{self.config['api']}/{stop}").json()

		departures = []
		for d in stopInfo["departures"]:
			if not route or int(d["route_id"]) == route:
				if d["schedule_relationship"] == "Scheduled":
					# Format bus name
					out = {
						"heading": HEADINGS[d["direction_text"]],
						"name": d["route_short_name"].replace("Line", "Li.") + (d["terminal"] if "terminal" in d else "")
					}

					if d["actual"]:
						out["time"] = departureTime = d["departure_text"].replace(" Min", "m")
					else:
						out["time"] = datetime.fromtimestamp(d["departure_time"]).strftime(":%M")
					departures.append(out)

		return departures

	def update(self):
		# Only update once every 30 seconds, if this somehow gets
		# below zero (probably a time sync) we don't want it getting stuck
		deltaTime = time.time() - self.lastUpdated
		if deltaTime < 30 and deltaTime >= 0:
			return

		print("[b] update")

		departures = []
		try:
			for stop in self.config["stops"]:
				if type(stop) is int:
					departure = self.fetchDepartures(stop)
				else:
					departure = self.fetchDepartures(*stop)

				if departure:
					departures.append(departure)
			self.error = None
		except:
			self.error = "Fetch failed"

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
		if (time.time() - self.lastUpdated) > 90:
			self.display.print("transit", 0, 0, "Loading...")
		if self.error:
			self.display.print("transit", 0, 0, 'API Error... "^_^')
			self.display.print("transit", 0, self.display.font.height, self.error)
		elif len(self.departures) > 0:
			for i, d in enumerate(self.departures):
				y = i * self.display.font.height
				self.display.print("transit", 0, y, d[0]["heading"] + d[0]["name"])
				self.display.print("transit", 20, y, "+".join(x["time"] for x in d[:2]))
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
		self.error = None

	def cToF(self, celsius):
		return celsius * 9 / 5 + 32

	def update(self):
		if (time.time() - self.nextUpdate) < 0:
			return
		
		print("[w] update")

		try:
			req = requests.get(f"https://api.weather.gov/stations/{self.config['station']}/observations/latest")
			self.data = req.json()["properties"]
			self.error = None
		except:
			self.error = "err"

		# self.nextUpdate = datetime.strptime(req.headers["Expires"], "%a, %d %b %Y %H:%M:%S %Z").timestamp()
		self.nextUpdate = time.time() + 600

	def render(self):
		if self.data == []:
			self.display.print("weather", 0, 0, "wait")
		elif self.error:
			self.display.print("weather", 0, 0, self.err)
		else:
			self.display.print("weather", 0, 0, f"{self.cToF(self.data['temperature']['value']):.0f}°F")


def main():
	"Pi LED display"

	parser = ArgumentParser(description=main.__doc__)
	parser.add_argument("config", type=str, help="config file")
	parser.add_argument("font", type=str, help="FRF font (proportional supported)")
	parser.add_argument("width", type=int, help="character width")
	parser.add_argument("height", type=int, help="character height")
	parser.add_argument("--testmode", "-t", action="store_const", const=True, help="output to an image for prototyping")
	args = parser.parse_args()

	if args.testmode:
		global TEST_MODE
		TEST_MODE = True
	else:
		from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

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
