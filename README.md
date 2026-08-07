# LedDisplay

A little project for running an LED matrix from a Raspberry Pi. This is primarily intended for personal use, but I would be super excited to hear if anyone else thinks this is cool enough to use it! I'm happy to help with setting up, feel free to send me an email. Though I will admit the code is rather scratched together to do what I want it to.

## Setup
1. From a clean DietPi install, install `python3 python3-dev python3-pip python3-pil python3-requests python3-rpi.gpio git gcc g++`
2. Run `pip install -r requirements.txt --break-system-packages`
   - If you don't want to 'break system packges', use a venv
3. Copy `config.sample.json` to `config.json` and fill it out to your needs
4. If you want a systemd service, copy `led-display.sample.service` to `/etc/systemd/system/led-display.service` and fill it out to your needs
5. `sudo systemctl enable --now led-display.service`

## Features
- Bus display like at the stations
   - Compatible with [GTFS](https://gtfs.org/), but specifically tested with [Metro Transit](https://svc.metrotransit.org/)
   - Able to show multiple pages, toggled by a switch connected to GPIO
      - Note: Currently I have it configured for GPIO 24 (pin 17) since it was the first one I found that didn't cause obvious interference with the RGB HAT
- Clock
- Weather (currently just the temperature)

## Credits
- [hzeller](https://github.com/hzeller) for the [rpi-rpg-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library that this uses to interface with the display
