#!/usr/bin/env python3

import json
import random
import requests
import time

from argparse import ArgumentParser
from PIL import Image
from struct import unpack

HEADINGS = {"NB": "↑", "EB": "→", "SB": "↓", "WB": "←"}


class LedDisplay:
	def __init__(self, config, font):
		self.parseConfig(config)
		self.parseFont(font)

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

		self.fontHeight = height
		self.font = output

	def getColor(self, module):
		if module and "color" in self.config[module]:
			hexColor = self.config[module]["color"]
			r = int(hexColor[1:3], 16)
			g = int(hexColor[3:5], 16)
			b = int(hexColor[5:7], 16)
			return (r, g, b)
		
		return (255, 255, 255)  # Default to white

	def print(self, module, imx, imy, string):
		color = (255, 255, 255)
		if module:
			ofs = self.config[module]["position"]
			imx += ofs[0]
			imy += ofs[1]
			color = self.getColor(module)

		for letter in string:
			# If letter missing, print '?'
			if letter not in self.font:
				letter = "?"

			width = self.font[letter]["width"]
			bitmap = self.font[letter]["bitmap"]

			# If we're going off screen, return
			if imx + width > self.im.width or imy + self.fontHeight > self.im.height:
				return

			for y in range(self.fontHeight):
				for x in range(width):
					if bitmap[y] & (0x80 >> x):
						self.im.putpixel((imx + x, imy + y), color)

			imx += width

	def fetchDeparture(self, stop, route=None):
		stopInfo = requests.get(f"{self.config['transit']['api']}/{stop}").json()
		for departure in stopInfo["departures"]:
			if not route or departure["route_id"] == route:
				return departure

	def renderBusTracker(self):
		departures = []
		for stop in self.config["transit"]["stops"]:
			if type(stop) is int:
				departure = self.fetchDeparture(stop)
			else:
				departure = self.fetchDeparture(*stop)
			if departure:
				departures.append(departure)

		if len(departures) > 0:
			for i, d in enumerate(departures):
				heading = HEADINGS[d["direction_text"]]
				busName = d["route_short_name"] + (d["terminal"] if "terminal" in d else "")
				departureTime = d["departure_text"].replace(" Min", "m")

				self.print("transit", 0, i * self.fontHeight, busName + heading)
				self.print("transit", 20, i * self.fontHeight, departureTime)
		else:
			sky = "".join(random.sample(["\2", "\3"], counts=[3, 3], k=6)) + "\1" + "".join(random.sample(["\2", "\3"], counts=[2, 2], k=4))
			self.print("transit", 0, 0, sky)
			self.print("transit", 0, 1 * self.fontHeight, "Busses are done")
			self.print("transit", 0, 2 * self.fontHeight, "for the night...")

	def renderClock(self):
		self.print("clock", 0, 0, time.strftime(self.config["clock"]["format"]))

	def render(self, width, height):
		self.im = Image.new("RGB", (width, height))

		if self.config["transit"]["enabled"]:
			self.renderBusTracker()

		if self.config["clock"]["enabled"]:
			self.renderClock()

		return self.im


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

	im = display.render(args.width, args.height)

	im.save(args.output)


if __name__ == "__main__":
	main()
