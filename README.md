# LedDisplay

A little project for running an LED matrix from a Raspberry Pi. This is primarily intended for personal use, but I would be super excited to hear if anyone else thinks this is cool enough to use it! I'm happy to help with setting up, feel free to send me an email. Though I will admit the code is rather scratched together to do what I want it to.

## Features
- Bus display like at the stations
   - Compatible with [GTFS](https://gtfs.org/), but specifically tested with [Metro Transit](https://svc.metrotransit.org/)
   - Able to show multiple pages, toggled by a switch connected to GPIO
      - Note: Currently I have it configured for GPIO 0 since it was the first one I found that didn't cause *major* interference with the RGB HAT, however upon full set up I realized that it uh, does cause a problem. The bottom half of the screen turns blue while the button is held... This isn't a major issue however and I already soldered the wires so I just left it like that. There's probably a better GPIO pin to use, but I don't know which
- Clock
- Weather (currently just the temperature)

## Credits
- [hzeller](https://github.com/hzeller) for the [rpi-rpg-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library that this uses to interface with the display
