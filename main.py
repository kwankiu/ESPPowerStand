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

# Load config.json
try:
    with open("config.json", "r") as config_file:
        config = ujson.load(config_file)
except OSError:
    print("Unable to load config.json, file may be missing")

# Read MQTT settings
try:
    MQTT_BROKER = config["mqtt_broker"]
    MQTT_PORT = config["mqtt_port"]
    MQTT_USER = config["mqtt_user"]
    MQTT_PASSWORD = config["mqtt_password"]
except KeyError:
    print("Missing or incorrect MQTT settings in config")

# Read Device configuarations
try:
    devices_config = config["devices"]
    DEVICE_NAME = devices_config["name"]
    DEVICE_TYPE = devices_config["type"]
except KeyError:
    print("Missing or incorrect Device configuration in config")    
    
# Generate a unique ID from MAC address
MAC_ADDRESS = ubinascii.hexlify(network.WLAN().config('mac')).decode().replace(":", "")
UNIQUE_ID = "1us" + MAC_ADDRESS # suffix + MAC_ADDRESS
print("Device ID: "+UNIQUE_ID)

# Define MQTT Topic Path
MQTT_CONFIG_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/config"
MQTT_STATE_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/status"
MQTT_SET_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/set"

MQTT_BRIGHTNESS_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/brightness"
MQTT_BRIGHTNESS_STATE_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/brightnessstatus"

MQTT_COLORTEMP_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/colortemp"
MQTT_COLORTEMP_STATE_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/colortempstatus"

MQTT_RGB_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/rgb"
MQTT_RGB_STATE_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/rgbstatus"

MQTT_EFFECT_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/effect"
MQTT_EFFECT_STATE_TOPIC = "homeassistant/" + DEVICE_TYPE + "/" + UNIQUE_ID + "/effectstatus"

# Device properties
device_properties = {
    "name": DEVICE_NAME,
    "unique_id": UNIQUE_ID,
    "state_topic": MQTT_STATE_TOPIC,
    "command_topic": MQTT_SET_TOPIC,
    "brightness_command_topic": MQTT_BRIGHTNESS_TOPIC,
    "brightness_state_topic": MQTT_BRIGHTNESS_STATE_TOPIC,
    "brightness_scale": 100,
    "color_temp_command_topic": MQTT_COLORTEMP_TOPIC,
    "color_temp_state_topic": MQTT_COLORTEMP_STATE_TOPIC,
    "rgb_command_topic": MQTT_RGB_TOPIC,
    "rgb_state_topic": MQTT_RGB_STATE_TOPIC,
    "effect_command_topic": MQTT_EFFECT_TOPIC,
    "effect_state_topic": MQTT_EFFECT_STATE_TOPIC,
    "effect_list": ["static", "breathing", "flashing", "fading", "colorloop", "rainbow", "watercolor", "random_flash", "random_breath", "random_fade"],
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

# Global variables for neopixel
try:
    neopixel_mode = devices_config["mode"]
except KeyError:
    neopixel_mode = "rainbow"
    devices_config["mode"] = neopixel_mode

try:
    neopixel_brightness = devices_config["brightness"]
except KeyError:
    neopixel_brightness = 1.0
    devices_config["brightness"] = neopixel_brightness

try:
    neopixel_rgb = devices_config["rgb"]
except KeyError:
    neopixel_rgb = "255,255,255"
    devices_config["rgb"] = neopixel_rgb

neopixel_speed=10
last_neopixel=None
last_brightness=None

# MQTT callback function
def mqtt_callback(topic, msg):
    global neopixel_mode, neopixel_brightness, neopixel_rgb, last_brightness  # Declare multiple global variables in one line
    current_payload = msg.decode()

    if topic == (MQTT_SET_TOPIC).encode() and current_payload == "ON":
        if neopixel_brightness <= 0.0:
            if last_brightness <= 0.0:
                neopixel_brightness = 100.0
            else:
                neopixel_brightness = last_brightness
            print("Light ON")
    elif topic == (MQTT_SET_TOPIC).encode() and current_payload == "OFF":
        print("Light OFF")
        last_brightness = neopixel_brightness
        neopixel_brightness = 0.0
    elif topic == (MQTT_BRIGHTNESS_TOPIC).encode():
        neopixel_brightness = int(current_payload) / 100.0
        print("Adjust brightness to", neopixel_brightness * 100)
    elif topic == (MQTT_EFFECT_TOPIC).encode():
        neopixel_mode = current_payload
        print("Change Neopixel Mode to", neopixel_mode)
    elif topic == (MQTT_RGB_TOPIC).encode():
        if neopixel_mode == "rainbow" or neopixel_mode == "watercolor":
            neopixel_mode = "static"
        neopixel_rgb = current_payload
        print("Set Color to", neopixel_rgb)
    elif topic == (MQTT_COLORTEMP_TOPIC).encode():
        if neopixel_mode == "rainbow" or neopixel_mode == "watercolor":
            neopixel_mode = "static"
        print("Set Temperature to", current_payload)
        neopixel_rgb = temp_to_rgb(int(current_payload))
    elif topic != (MQTT_CONFIG_TOPIC).encode() and "status" not in topic.decode():
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

def temp_to_rgb(color_temp, returnString=True):
    #Convert color temperature to RGB.
    #param color_temp: Color temperature in Kelvin or Mireds
    #return: RGB tuple

    if color_temp < 1000:
        # Assuming it's in Mireds
        kelvin = 1.0 / color_temp * 1e6
    else:
        # Assuming it's in Kelvin
        kelvin = color_temp

    temperature = kelvin / 100.0

    # Calculate red
    if temperature <= 66:
        red = 255
    else:
        red = 329.698727446 * ((temperature - 60) ** -0.1332047592)

    # Calculate green
    if temperature <= 66:
        green = 99.4708025861 * math.log(temperature) - 161.1195681661
    else:
        green = 288.1221695283 * ((temperature - 60) ** -0.0755148492)

    # Calculate blue
    if temperature >= 66:
        blue = 255
    elif temperature <= 19:
        blue = 0
    else:
        blue = 138.5177312231 * math.log(temperature - 10) - 305.0447927307

    rgb_values = (
        min(int(max(0, red)), 255),
        min(int(max(0, green)), 255),
        min(int(max(0, blue)), 255)
    )

    if returnString:
        rgb_string= "{},{},{}".format(*rgb_values)
        return rgb_string
    else:
        return rgb_values

# Color Effects

def static_color(color):
    np.fill(scale_brightness(color, neopixel_brightness))
    np.write()

async def color_breathing(duration, steps=100):
    for step in range(steps):
        brightness_value = int(neopixel_brightness * 0.5 * (1 + math.sin(2 * math.pi * step / steps)) * 255)
        color_values = [int(value) for value in neopixel_rgb.split(",")]
        np.fill(scale_brightness(color_values, brightness_value / 255))
        np.write()
        # Break the function for real time neopixel mode switch
        if last_neopixel != neopixel_mode:
            break  # Break out of the inner loop   
        await asyncio.sleep_ms(duration // steps)

async def color_flash(num_flashes, flash_duration, delay):
    for _ in range(num_flashes):
        color_values = [int(value) for value in neopixel_rgb.split(",")]
        np.fill(scale_brightness(color_values, neopixel_brightness))
        np.write()
        # Break the function for real time neopixel mode switch
        if last_neopixel != neopixel_mode:
            break  # Break out of the inner loop   
        await asyncio.sleep_ms(flash_duration)
        np.fill((0, 0, 0))  # Turn off the lights
        np.write()
        # Break the function for real time neopixel mode switch
        if last_neopixel != neopixel_mode:
            break  # Break out of the inner loop   
        await asyncio.sleep_ms(delay)

async def random_flash(num_flashes, flash_duration, delay):
    for _ in range(num_flashes):
        np.fill(scale_brightness(random_color(), neopixel_brightness))
        np.write()
        # Break the function for real time neopixel mode switch
        if last_neopixel != neopixel_mode:
            break  # Break out of the inner loop   
        await asyncio.sleep_ms(flash_duration)
        np.fill((0, 0, 0))  # Turn off the lights
        np.write()
        # Break the function for real time neopixel mode switch
        if last_neopixel != neopixel_mode:
            break  # Break out of the inner loop   
        await asyncio.sleep_ms(delay)

async def rainbow_cycle(wait):
    flag_break = False  # Flag to indicate if we should break out of loops
    for j in range(255):
        for i in range(num_pixels):
            pixel_index = (i * 256 // num_pixels) + j
            np[i] = scale_brightness(wheel(pixel_index & 255), neopixel_brightness)
            # Break the function for real time neopixel mode switch
            if last_neopixel != neopixel_mode:
                flag_break = True  # Set the flag to break out of loops
                break  # Break out of the inner loop                
        np.write()
        if flag_break:
            break  # Break out of the outer loop
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

    flag_break = False  # Flag to indicate if we should break out of loops
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

            # Break the function for real time neopixel mode switch
            if last_neopixel != neopixel_mode:
                flag_break = True  # Set the flag to break out of loops
                break  # Break out of the inner loop   

        np.write()
        if flag_break:
            break  # Break out of the outer loop
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

# Separate loop for MQTT message sending
async def mqtt_message_sender():
    #global neopixel_brightness, neopixel_mode, neopixel_rgb, neopixel_speed
    while True:

        # ON / OFF State
        try:
            if neopixel_brightness <= 0.0:
                mqtt_client.publish((MQTT_STATE_TOPIC).encode(), b"OFF")
            else:
                mqtt_client.publish((MQTT_STATE_TOPIC).encode(), b"ON")
        except:
            pass # ignore any error so it wont spam the serial when no mqtt or wifi is available

        if neopixel_brightness > 0.0:
            # Brightness State
            try:
                    scaled_brightness = int(neopixel_brightness*100)
                    mqtt_client.publish((MQTT_BRIGHTNESS_STATE_TOPIC).encode(), (str(scaled_brightness)).encode())
            except:
                pass # ignore any error so it wont spam the serial when no mqtt or wifi is available

            # RGB State
            try:
                if neopixel_mode != "rainbow" and neopixel_mode != "watercolor":
                    mqtt_client.publish((MQTT_RGB_STATE_TOPIC).encode(), (neopixel_rgb).encode())
            except:
                pass # ignore any error so it wont spam the serial when no mqtt or wifi is available

            # NeoPixel Mode State
            try:
                mqtt_client.publish((MQTT_EFFECT_STATE_TOPIC).encode(), (neopixel_mode).encode())
            except:
                pass # ignore any error so it wont spam the serial when no mqtt or wifi is available

        await asyncio.sleep_ms(100)  # Adjust the sleep time as needed

# Neopixel loop
async def run_neopixel():
    global last_neopixel
    while True:
        # Clear the previous text on the display
        display.fill_rect(24, 0, 80, 8, 0)

            #elif neopixel_mode == "random":
            # Random effect (randomly loop among all color effects)
            #display.text('Random', 40, 0, 1)
            # Implement random effect (Coming Soon)

        if neopixel_brightness <= 0.0:
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
                await color_breathing(2000)  # Adjust the duration as needed
            elif neopixel_mode == "flashing":
                # Random color flashes
                display.text('Flashing', 32, 0, 1)
                await color_flash(5, 50, 500)  # Adjust the number of flashes, flash duration, and delay as needed
            elif neopixel_mode == "static":
                # Static color effect
                display.text('Static', 40, 0, 1)
                color_values = [int(value) for value in neopixel_rgb.split(",")]
                static_color(color_values)
            elif neopixel_mode == "watercolor":
                # Watercolor rainbow cycle effect (Experimental, mostly working but not smooth enough like iCUE's)
                display.text('Watercolor', 26, 0, 1)
                await watercolor_rainbow_cycle(5)  # Adjust the value to control the speed of the watercolor rainbow cycle
            elif neopixel_mode == "random_flash":
                # Random color flashes
                display.text('R.Flashing', 25, 0, 1)
                await random_flash(5, 50, 500)  # Adjust the number of flashes, flash duration, and delay as needed
            else:
                # Unknown Values
                display.text('UnknownVal', 25, 0, 1)
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
                # Subscribe to topics for basic control
                mqtt_client.subscribe((MQTT_CONFIG_TOPIC).encode())
                mqtt_client.subscribe((MQTT_STATE_TOPIC).encode())
                mqtt_client.subscribe((MQTT_SET_TOPIC).encode())
                # Subscribe to topics for color temp and brightness light control
                mqtt_client.subscribe((MQTT_BRIGHTNESS_TOPIC).encode())
                mqtt_client.subscribe((MQTT_BRIGHTNESS_STATE_TOPIC).encode())
                mqtt_client.subscribe((MQTT_COLORTEMP_TOPIC).encode())
                mqtt_client.subscribe((MQTT_COLORTEMP_STATE_TOPIC).encode())
                # Subscribe to topics for rgb and effect light control
                mqtt_client.subscribe((MQTT_RGB_TOPIC).encode())
                mqtt_client.subscribe((MQTT_RGB_STATE_TOPIC).encode())
                mqtt_client.subscribe((MQTT_EFFECT_TOPIC).encode())
                mqtt_client.subscribe((MQTT_EFFECT_STATE_TOPIC).encode())
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

async def save_config(file_path="config.json"):
    global config  # Assume config is a global variable
    global devices_config  # Assume devices_config is a global variable

    while True:
        isChanged = False

        if devices_config["brightness"] != neopixel_brightness:
            devices_config["brightness"] = neopixel_brightness
            isChanged = True
        if devices_config["mode"] != neopixel_mode:
            devices_config["mode"] = neopixel_mode
            isChanged = True
        if devices_config["rgb"] != neopixel_rgb:
            devices_config["rgb"] = neopixel_rgb
            isChanged = True

        if isChanged:
            # Update devices_config to config["devices"]
            config["devices"] = devices_config

            # Convert Python object to JSON-formatted string with manual indentation
            json_string = ujson.dumps(config)
            indented_json = ""
            level = 0

            for char in json_string:
                if char in ('{', '['):
                    level += 1
                    indented_json += char + '\n' + ' ' * (level * 4)
                elif char in ('}', ']'):
                    level -= 1
                    indented_json = indented_json.rstrip() + '\n' + ' ' * (level * 4) + char
                elif char == ',':
                    indented_json += char + '\n' + ' ' * (level * 4)
                else:
                    indented_json += char

            # Save the updated config string to config.json
            try:
                with open(file_path, "w") as config_file:
                    config_file.write(indented_json)
            except OSError:
                print("Unable to update config.json. Check file permissions or disk space.")

        # Wait for 500 milliseconds before the next iteration
        await asyncio.sleep_ms(500)

# Start the WiFi checking task in the background
loop = asyncio.get_event_loop()
loop.create_task(run_neopixel())
loop.create_task(check_wifi())
loop.create_task(mqtt_message_checker())
loop.create_task(mqtt_message_sender())
loop.create_task(save_config())
loop.create_task(main())

# Run the event loop indefinitely
loop.run_forever()