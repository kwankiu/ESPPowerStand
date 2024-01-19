from machine import Pin, SoftI2C, RTC
from neopixel import NeoPixel
import time
import ujson
import math
import async_urequests as requests
import urandom
import ssd1306
import uasyncio as asyncio
from umqtt.simple import MQTTClient
import network
import ubinascii

# Read MQTT settings from config.json
try:
    with open("config.json", "r") as config_file:
        config = ujson.load(config_file)
        MQTT_BROKER = config["mqtt_broker"]
        MQTT_PORT = config["mqtt_port"]
        MQTT_USER = config["mqtt_user"]
        MQTT_PASSWORD = config["mqtt_password"]
except OSError:
    print("Missing or incorrect configuration in config.json")
    
# Generate a unique ID from MAC address
MAC_ADDRESS = ubinascii.hexlify(network.WLAN().config('mac')).decode().replace(":", "")
UNIQUE_ID = "1us" + MAC_ADDRESS # suffix + MAC_ADDRESS
print("Device ID: "+UNIQUE_ID)

# Define MQTT Topic Path
MQTT_CONFIG_TOPIC="homeassistant/light/" + UNIQUE_ID + "/config"
MQTT_STATE_TOPIC="homeassistant/light/" + UNIQUE_ID + "/status"
MQTT_SET_TOPIC="homeassistant/light/" + UNIQUE_ID + "/set"
MQTT_BRIGHTNESS_TOPIC="homeassistant/light/" + UNIQUE_ID + "/brightness"

# Device properties
device_properties = {
    "name": "1us RGB Light",
    "unique_id": UNIQUE_ID,
    "state_topic": MQTT_STATE_TOPIC,
    "command_topic": MQTT_SET_TOPIC,
    "command_topic": MQTT_SET_TOPIC,
    "brightness_command_topic": MQTT_BRIGHTNESS_TOPIC,
    "brightness_scale": 100,
}

# Convert to JSON
device_json = ujson.dumps(device_properties)

# Using default address 0x3C
i2c = SoftI2C(sda=Pin(1), scl=Pin(0))
display = ssd1306.SSD1306_I2C(128, 64, i2c)

# Define the pin and number of NeoPixels
pin = Pin(12)
num_pixels = 30
np = NeoPixel(pin, num_pixels)

rtc = RTC()
wifi = network.WLAN(network.STA_IF)

neopixel_mode="rainbow"
neopixel_brightness=1.0
neopixel_speed=10

# MQTT callback function
def mqtt_callback(topic, msg):
    global neopixel_mode  # Declare as a global variable
    global neopixel_brightness  # Declare as a global variable
    current_payload = msg.decode()

    if topic == (MQTT_SET_TOPIC).encode() and current_payload == "ON":
        if neopixel_mode == "off":
            print("Light ON")
            neopixel_mode = "rainbow"
    elif topic == (MQTT_SET_TOPIC).encode() and current_payload == "OFF":
        print("Light OFF")
        neopixel_mode = "off"
    elif topic == (MQTT_BRIGHTNESS_TOPIC).encode():
        neopixel_brightness = int(current_payload) / 100.0
        print("Adjust brightness to ", neopixel_brightness * 100)
    elif topic != (MQTT_STATE_TOPIC).encode() and topic != (MQTT_CONFIG_TOPIC).encode():
        print("Received unprocessed message on topic:", topic.decode())
        print("Message:", current_payload)
            
mqtt_client = MQTTClient(UNIQUE_ID, MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD)
mqtt_client.set_callback(mqtt_callback)

month_names = {
    1: 'Jan',
    2: 'Feb',
    3: 'Mar',
    4: 'Apr',
    5: 'May',
    6: 'Jun',
    7: 'Jul',
    8: 'Aug',
    9: 'Sep',
    10: 'Oct',
    11: 'Nov',
    12: 'Dec',
}

# Neopixel Functions

# Helper Functions
def wheel(pos):
    # Input a value 0 to 255 to get a color value.
    # The colors are a transition from red to green to blue and back to red.
    if pos < 85:
        return (int(pos * 3), int(255 - pos * 3), 0)
    elif pos < 170:
        pos -= 85
        return (int(255 - pos * 3), 0, int(pos * 3))
    else:
        pos -= 170
        return (0, int(pos * 3), int(255 - pos * 3))

def scale_brightness(color, brightness):
    return (
        int(color[0] * brightness),
        int(color[1] * brightness),
        int(color[2] * brightness)
    )

def interpolate_color(color1, color2, ratio):
    # Interpolate between two colors based on the given ratio
    return (
        int(color1[0] + ratio * (color2[0] - color1[0])),
        int(color1[1] + ratio * (color2[1] - color1[1])),
        int(color1[2] + ratio * (color2[2] - color1[2]))
    )

def repeat_colors(colors, factor):
    repeated_colors = []
    
    for color in colors:
        for _ in range(factor):
            repeated_colors.append(color)
    
    return repeated_colors

def random_color():
    return (urandom.randint(0, 255), urandom.randint(0, 255), urandom.randint(0, 255))

# Color Effects

def static_color(color):
    np.fill(scale_brightness(color, neopixel_brightness))
    np.write()

async def color_breathing(color, duration, steps=100):
    r, g, b = color
    for step in range(steps):
        brightness_value = int(neopixel_brightness * 0.5 * (1 + math.sin(2 * math.pi * step / steps)) * 255)
        np.fill(scale_brightness((r, g, b), brightness_value / 255))
        np.write()
        await asyncio.sleep_ms(duration // steps)

async def random_flash(num_flashes, flash_duration, delay):
    for _ in range(num_flashes):
        np.fill(scale_brightness(random_color(), neopixel_brightness))
        np.write()
        await asyncio.sleep_ms(flash_duration)
        np.fill((0, 0, 0))  # Turn off the lights
        np.write()
        await asyncio.sleep_ms(delay)

async def rainbow_cycle(wait):
    for j in range(255):
        for i in range(num_pixels):
            pixel_index = (i * 256 // num_pixels) + j
            np[i] = scale_brightness(wheel(pixel_index & 255), neopixel_brightness)
        np.write()
        await asyncio.sleep_ms(wait)

async def watercolor_rainbow_cycle(wait):
    # Define a list of the Watercolors (CMYK)
    colors = [
        (255, 255, 255),
        (0, 255, 255),
        (255, 255, 255),
        (255, 0, 255),
        (255, 255, 255),
        (255, 255, 0),
    ]

    colors = repeat_colors(colors, 6)

    num_colors = len(colors)

    for j in range(-num_pixels * 2, num_pixels * 2):
        for i in range(num_pixels):
            color_index = (i + j) % (num_colors * 2)

            if color_index >= num_colors:
                color_index = (num_colors - 1) - (color_index - num_colors)

            # Calculate a smooth transition between colors
            ratio = abs(j) / (num_pixels * 2)

            # Interpolate between consecutive colors
            interpolated_color = interpolate_color(colors[color_index], colors[(color_index + 1) % num_colors], ratio)

            # Scale the brightness of the interpolated color
            interpolated_color = scale_brightness(interpolated_color, neopixel_brightness)

            np[i] = interpolated_color

        np.write()
        await asyncio.sleep_ms(wait * 10)

# Sync Network Clock
async def get_world_time():
    try:
        response = await requests.get("http://worldtimeapi.org/api/ip")
        data = response.json()
        return data["datetime"]
    except Exception as e:
        print("Error fetching time:", e)
        return None
    
# Helper function to parse the datetime string
def parse_datetime(datetime_str):
    year = int(datetime_str[0:4])
    month = int(datetime_str[5:7])
    day = int(datetime_str[8:10])
    hour = int(datetime_str[11:13])
    minute = int(datetime_str[14:16])
    second = int(datetime_str[17:19])

    return (year, month, day, hour, minute, second, 0, 0)
    
# Initial Splash Screen
display.fill(1)
display.fill_rect(4, 4, 32, 32, 0)
display.fill_rect(4, 8, 24, 16, 1)
display.text('1us', 4, 12, 0)
display.text('Power Stand', 38, 4, 0)
display.text('ESP32-C3', 38, 16, 0)
display.text('v0.1.1', 38, 28, 0)
display.text('STARTING ...', 16, 40, 0)
display.show()
display.fill(0)
    
# Main loop
async def main():
    while True:
        # Fetch current time and date
        current_time = await get_world_time()
        #current_time = None
        if current_time is not None:
            # Parse the datetime string into a tuple
            current_time_tuple = parse_datetime(current_time)

            # Convert the tuple to local time
            current_time = time.mktime(current_time_tuple)
            current_time = time.localtime(current_time)
            time_string = "{:02d}:{:02d}".format(current_time[3], current_time[4])
            date_string = "{:02d} {} {:04d}".format(current_time[2], month_names[current_time[1]], current_time[0])
        else:
            time_string = "00:00"
            date_string = "01 Jan 2000"
        
        # Clear the previous time and date
        display.fill_rect(28, 12, 72, 24, 0)  # Clear the time area
        display.fill_rect(16, 48, 96, 8, 0)  # Clear the date area
        
        # Display time and date
        display.overlap_wrap(time_string, 28, 16, 3)
        display.bold_text(date_string, 16, 48, 1)
        
        display.vline(9, 8, 40, 1)
        display.vline(16, 2, 40, 1)
        display.vline(23, 8, 40, 1)
        display.vline(105, 8, 40, 1)
        display.vline(112, 2, 40, 1)
        display.vline(119, 8, 40, 1)              
        display.show()
        
        # Allow other tasks to run by yielding control to the event loop
        await asyncio.sleep_ms(0)

# Separate loop for MQTT message checking
async def mqtt_message_checker():
    while True:
        try:
            mqtt_client.check_msg()
        except:
            pass # ignore any error so it wont spam the serial when no mqtt or wifi is available
        await asyncio.sleep_ms(0)  # Adjust the sleep time as needed

async def run_neopixel():
    last_neopixel=None
    while True:
        # Clear the previous text on the display
        display.fill_rect(24, 0, 80, 8, 0)

            #elif neopixel_mode == "random":
            # Random effect (randomly loop among all color effects)
            #display.text('Random', 40, 0, 1)
            # Implement random effect (Coming Soon)

        if neopixel_brightness <= 0.0 or neopixel_mode == "off":
            # Lights off (turn off the rgb light)
            display.text('Light Off', 30, 0, 1)
            static_color((0, 0, 0))  # Turn off the RGB light
        else:
            if neopixel_mode == "rainbow":
                # Rainbow wave effect
                display.text('Rainbow', 36, 0, 1)
                await rainbow_cycle(10)  # Adjust the value to control the speed of the rainbow wave
            elif neopixel_mode == "breathing":
                # Color breathing effect (e.g., breathing white)
                display.text('Breathing', 30, 0, 1)
                await color_breathing((255, 255, 255), 2000)  # Adjust the color and duration as needed
            elif neopixel_mode == "flashing":
                # Random color flashes
                display.text('Flashing', 32, 0, 1)
                await random_flash(5, 50, 500)  # Adjust the number of flashes, flash duration, and delay as needed
            elif neopixel_mode == "static":
                # Static color effect (e.g., static blue)
                display.text('Static', 40, 0, 1)
                static_color((0, 0, 255))  # Adjust the static color as needed
            elif neopixel_mode == "watercolor":
                # Watercolor rainbow cycle effect (Experimental, mostly working but not smooth enough like iCUE's)
                display.text('Watercolor', 26, 0, 1)
                await watercolor_rainbow_cycle(5)  # Adjust the value to control the speed of the watercolor rainbow cycle
        
        if last_neopixel != neopixel_mode:
            #print("Neopixel Mode Updated")
            
            try:
                if neopixel_brightness <= 0.0 or neopixel_mode == "off":
                    mqtt_client.publish((MQTT_STATE_TOPIC).encode(), b"OFF", retain=True)
                else:
                    mqtt_client.publish((MQTT_STATE_TOPIC).encode(), b"ON", retain=True)
            except:
                pass
            last_neopixel=neopixel_mode
        # Allow other tasks to run by yielding control to the event loop
        await asyncio.sleep(0)

async def check_wifi():
    last_state=None
    while True:
        current_state = wifi.isconnected()
        
        # Clear the previous text on the display
        display.fill_rect(16, 56, 96, 8, 0)
        
        if current_state:
            if last_state != current_state:
                print("WiFi Connected")
                # Synchronize with NTP server to get current time
                ntptime.settime()
                # Connect to MQTT broker
                mqtt_client.connect()
                # Subscribe to topics for light control
                mqtt_client.subscribe((MQTT_CONFIG_TOPIC).encode())
                mqtt_client.subscribe((MQTT_STATE_TOPIC).encode())
                mqtt_client.subscribe((MQTT_SET_TOPIC).encode())
                mqtt_client.subscribe((MQTT_BRIGHTNESS_TOPIC).encode())
                
                # Publish Config for Auto Discovery
                mqtt_client.publish((MQTT_CONFIG_TOPIC).encode(), device_json, retain=True)
                print("MQTT Broker connected.")
            ip_address = wifi.ifconfig()[0]
            display.text(ip_address, 16, 56, 1)

        else:
            if last_state != current_state:
                print("Waiting for WiFi Connection")
            display.text('Disconnected', 16, 56, 1)
        last_state=current_state
        await asyncio.sleep_ms(500)

# Start the WiFi checking task in the background
loop = asyncio.get_event_loop()
loop.create_task(run_neopixel())
loop.create_task(check_wifi())
loop.create_task(mqtt_message_checker())
loop.create_task(main())

# Run the event loop indefinitely
loop.run_forever()