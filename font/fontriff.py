#!/usr/bin/env python3

from argparse import ArgumentParser
import struct
from os import path


def fontriff(input, width, height, mapPath=None, widthsPath=None):
	"""
	Creates an FRF font for GodMode9 from a PBM image
	Modified for LedDisplay -- Proportional font support
	"""

	if width < 1 or width > 8:
		raise ValueError("Font width is invalid (Maximum 8, minimum 1, current %d)" % width)

	if height < 1 or height > 10:
		raise ValueError("Font height is invalid (Maximum 10, minimum 1, current %d)" % height)

	# Read PBM
	with open(input, "rb") as f:
		pbm = f.read()
		split = pbm.split(b"\n")
		if split[0] != b"P4":
			raise ValueError("Input is not a PBM file")

	# Skip comments
	for i in range(1, len(split)):
		if split[i][0] != ord("#"):
			imgWidth = int(split[i].split()[0])
			imgHeight = int(split[i].split()[1])
			imgData = b"\n".join(split[i + 1:])
			break

	count = imgWidth * imgHeight // width // height
	columns = imgWidth // width
	fontMap = []

	# Prepare map
	if not mapPath:
		# If mapping file not specified, check if one with the same name as
		# the pbm exists and use it if found.
		inputTxt = input.replace(".pbm", ".txt")
		if path.exists(inputTxt):
			mapPath = inputTxt
			print("Info: Using %s for font mappings" % mapPath)

	if mapPath:
		with open(mapPath, "r") as fontMapFile:
			fontMapTemp = fontMapFile.read().split()
			if len(fontMapTemp) > count:
				raise ValueError("Font map has more items than possible in image (%d items in map)" % count)
			elif len(fontMapTemp) < count:
				count = len(fontMapTemp)
				print("Info: Font map has fewer items than possible in image, only using first %d" % count)

			for item in fontMapTemp:
				fontMap.append({"mapping": int(item, 16)})
	else:
		print("Warning: Font mapping not found, mapping directly to Unicode codepoints")
		for i in range(count):
			fontMap.append({"mapping": i})

	# Widths
	if widthsPath:
		with open(widthsPath, "r") as widthsFile:
			widthsTemp = widthsFile.read().split()
			if len(widthsTemp) > count:
				raise ValueError("Widths map has more items than possible in image (%d items in map)" % count)
			elif len(widthsTemp) < count:
				count = len(widthsTemp)
				print("Info: Widths map has fewer items than possible in image, only using first %d" % count)

			for i in range(count):
				fontMap[i]["width"] = int(widthsTemp[i], 10)

	# Add unsorted tiles to map
	for c in range(count):
		fontMap[c]["bitmap"] = bytearray()
		for row in range(height):
			ofs = ((c // columns * height + row) * (imgWidth + ((8 - (imgWidth % 8)) if imgWidth % 8 != 0 else 0)) // 8)
			bp0 = ((c % columns) * width) >> 3
			bm0 = ((c % columns) * width) % 8
			byte = (((imgData[ofs + bp0] << bm0) | ((imgData[ofs + bp0 + 1] >> (8 - bm0)) if ofs + bp0 + 1 < len(imgData) else 0)) & (0xFF << (8 - width))) & 0xFF
			fontMap[c]["bitmap"] += struct.pack("B", byte)

	# Remove duplicates
	fontMap = list({x["mapping"]: x for x in fontMap}.values())
	if len(fontMap) != count:
		print("Info: %d duplicate mappings were removed" % (count - len(fontMap)))
		count = len(fontMap)

	# Sort map
	fontMap = sorted(fontMap, key=lambda x: x["mapping"])

	# Create file
	output = bytearray()
	output += b"RIFF\0\0\0\0"  # The size is filled at the end

	# Metadata
	output += b"META"
	output += struct.pack("<LBBH", 4, width, height, count)

	# Character data
	output += b"CDAT"
	sectionSize = count * height
	padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
	output += struct.pack("<L", sectionSize + padding)
	for item in fontMap:
		output += item["bitmap"]
	output += b"\0" * padding

	# Character widths
	if widthsPath:
		output += b"CWTH"
		sectionSize = count
		padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
		output += struct.pack("<L", sectionSize + padding)
		for item in fontMap:
			output += struct.pack("<B", item["width"])
		output += b"\0" * padding

	# Character map
	output += b"CMAP"
	sectionSize = count * 2
	padding = 4 - sectionSize % 4 if sectionSize % 4 else 0
	output += struct.pack("<L", sectionSize + padding)
	for item in fontMap:
		output += struct.pack("<H", item["mapping"])
	output += b"\0" * padding

	# Set final size
	outSize = len(output)
	struct.pack_into("<L", output, 4, outSize - 8)

	return output


def main():
	parser = ArgumentParser(description=fontriff.__doc__)
	parser.add_argument("input", type=str, help="PBM image to convert from")
	parser.add_argument("output", type=str, help="out.to output to")
	parser.add_argument("width", type=int, help="character width")
	parser.add_argument("height", type=int, help="character height")
	parser.add_argument("-m", "--map", metavar="map.txt", type=str, help="character map (whitespace separated Unicode codepoints)")
	parser.add_argument("-w", "--widths", metavar="widths.txt", type=str, help="character width map (whitespace separated integers)")
	args = parser.parse_args()

	output = fontriff(args.input, args.width, args.height, args.map, args.widths)

	with open(args.output, "wb") as out:
		out.write(output)
		print("Info: %s created." % args.output)


if __name__ == "__main__":
	main()
